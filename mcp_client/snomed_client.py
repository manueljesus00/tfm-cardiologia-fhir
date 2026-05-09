"""
mcp_client/snomed_client.py — Cliente MCP Python para el servidor SNOMED IRBD.

Este cliente LANZA el servidor MCP como subproceso Python y mantiene la conexión
activa mientras dure la sesión de procesamiento. No depende de VS Code ni de
ningún cliente externo.

Arquitectura:
    main.py / api/app.py
        └─ MCPSnomedClient (este archivo)
             │  stdio (MCP Protocol)
             └─ mcp_servers/snomed_server.py  (subproceso Python)
                  └─ database/snomed_queries.py  (SQL contra PostgreSQL Docker)

Uso como context manager (síncrono):
    with MCPSnomedClient() as mcp:
        resultados = mcp.buscar_snomed("fibrilación auricular")
        valido = mcp.validar_snomed("49436004")
        reglas = mcp.obtener_reglas_cie10("49436004")

Uso async (para FastAPI):
    async with MCPSnomedClientAsync() as mcp:
        resultados = await mcp.buscar_snomed("fibrilación auricular")
"""
import asyncio
import threading
import json
import sys
import os
import logging
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

logger = logging.getLogger(__name__)

# Ruta absoluta al servidor MCP — no depende del cwd de ejecución
_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_servers",
    "snomed_server.py",
)


def _build_server_params() -> StdioServerParameters:
    """Construye los parámetros para lanzar el servidor MCP como subproceso."""
    return StdioServerParameters(
        command=sys.executable,   # El mismo Python del venv activo
        args=[_SERVER_SCRIPT, "--transport", "stdio"],
        env=None,                 # Hereda el entorno del proceso padre (.env incluido)
    )


# ─── Cliente Síncrono ────────────────────────────────────────────────────────

class MCPSnomedClient:
    """
    Cliente MCP síncrono con servidor persistente.

    Lanza el servidor MCP UNA SOLA VEZ al entrar en el context manager y
    mantiene la conexión stdio activa durante todo el procesamiento por lotes.
    Las llamadas síncronas se despachan al bucle de eventos del thread interno.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session: Optional[ClientSession] = None
        self._ready = threading.Event()
        self._error: Optional[Exception] = None
        # Guardamos los context managers para cerrarlos limpiamente
        self._stdio_cm = None
        self._session_cm = None

    # ── Ciclo de vida ──────────────────────────────────────────────────────

    def start(self) -> "MCPSnomedClient":
        """Inicia el servidor MCP en un thread dedicado y espera a que esté listo."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mcp-snomed")
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise TimeoutError("El servidor MCP SNOMED no arrancó en 15 segundos.")
        if self._error:
            raise self._error
        print("[MCP] Servidor SNOMED IRBD conectado y listo.")
        return self

    def stop(self):
        """Cierra la sesión MCP y detiene el thread interno limpiamente."""
        if self._loop and not self._loop.is_closed():
            future = asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
            try:
                future.result(timeout=5)
            except Exception as e:
                logger.warning(f"Error al desconectar MCP: {e}")
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        print("[MCP] Servidor SNOMED IRBD desconectado.")

    def __enter__(self) -> "MCPSnomedClient":
        return self.start()

    def __exit__(self, *args):
        self.stop()

    # ── Bucle de eventos interno ───────────────────────────────────────────

    def _run_loop(self):
        """Ejecuta el bucle asyncio en un thread dedicado."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect())
            self._ready.set()
            self._loop.run_forever()
        except Exception as e:
            self._error = e
            self._ready.set()  # Desbloquea start() para que pueda propagar el error

    async def _connect(self):
        """Establece la conexión con el servidor MCP via stdio."""
        params = _build_server_params()
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

    async def _disconnect(self):
        """Cierra la sesión y el subproceso del servidor."""
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._stdio_cm:
            await self._stdio_cm.__aexit__(None, None, None)

    # ── Dispatcher de herramientas ─────────────────────────────────────────

    def _sync_call(self, coro) -> Any:
        """Despacha una corrutina al loop interno y espera el resultado síncronamente."""
        if not self._loop or not self._session:
            raise RuntimeError("MCPSnomedClient no está iniciado. Usa 'with MCPSnomedClient() as mcp:'")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    async def _call_tool(self, name: str, arguments: dict) -> Any:
        result = await self._session.call_tool(name, arguments)
        text = result.content[0].text if result.content else "null"
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"MCP tool '{name}' devolvio JSON invalido: {text[:200]!r} - {e}")
            if name in ("buscar_snomed", "obtener_reglas_cie10"):
                return []
            if name == "validar_snomed":
                return {"activo": False}
            return None

    # ── API pública — herramientas SNOMED ─────────────────────────────────

    def buscar_snomed(self, texto: str, edition: str = "es", limite: int = 5) -> list:
        """Busca conceptos SNOMED CT por texto clínico en la IRBD."""
        return self._sync_call(self._call_tool(
            "buscar_snomed",
            {"texto": texto, "edition": edition, "limite": limite},
        ))

    def validar_snomed(self, concept_id: str) -> bool:
        """Verifica si un conceptId SNOMED CT existe y está activo."""
        data = self._sync_call(self._call_tool(
            "validar_snomed",
            {"concept_id": str(concept_id)},
        ))
        return data.get("activo", False) if isinstance(data, dict) else False

    def obtener_reglas_cie10(self, snomed_id: str) -> list:
        """Devuelve las MapRules SNOMED→CIE-10 para un conceptId."""
        return self._sync_call(self._call_tool(
            "obtener_reglas_cie10",
            {"snomed_id": str(snomed_id)},
        ))


# ─── Cliente Asíncrono (para FastAPI) ────────────────────────────────────────

class MCPSnomedClientAsync:
    """
    Cliente MCP asíncrono para uso con FastAPI (ya corre en un bucle asyncio).
    Se usa como async context manager en el lifespan de FastAPI.
    """

    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._stdio_cm = None
        self._session_cm = None

    async def __aenter__(self) -> "MCPSnomedClientAsync":
        params = _build_server_params()
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        print("[MCP] Servidor SNOMED IRBD conectado (modo async).")
        return self

    async def __aexit__(self, *args):
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._stdio_cm:
            await self._stdio_cm.__aexit__(None, None, None)
        print("[MCP] Servidor SNOMED IRBD desconectado (modo async).")

    async def _call_tool(self, name: str, arguments: dict) -> Any:
        result = await self._session.call_tool(name, arguments)
        text = result.content[0].text if result.content else "null"
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"MCP tool '{name}' devolvio JSON invalido: {text[:200]!r} - {e}")
            if name in ("buscar_snomed", "obtener_reglas_cie10"):
                return []
            if name == "validar_snomed":
                return {"activo": False}
            return None

    async def buscar_snomed(self, texto: str, edition: str = "es", limite: int = 5) -> list:
        return await self._call_tool("buscar_snomed", {"texto": texto, "edition": edition, "limite": limite})

    async def validar_snomed(self, concept_id: str) -> bool:
        data = await self._call_tool("validar_snomed", {"concept_id": str(concept_id)})
        return data.get("activo", False) if isinstance(data, dict) else False

    async def obtener_reglas_cie10(self, snomed_id: str) -> list:
        return await self._call_tool("obtener_reglas_cie10", {"snomed_id": str(snomed_id)})
