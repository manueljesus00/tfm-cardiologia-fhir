"""
mcp_servers/snomed_server.py — Custom MCP Server para la IRBD SNOMED CT Española.

Este servidor expone las herramientas de terminología clínica como MCP tools,
permitiendo que cualquier cliente MCP (VS Code Copilot, Claude Desktop, agentes
programáticos) las invoque de forma segura y tipada.

Arranque (stdio — modo estándar MCP):
    python mcp_servers/snomed_server.py

El cliente MCP (VS Code / main.py) lanza este proceso como subproceso y
se comunica con él mediante stdio siguiendo el protocolo JSON-RPC de MCP.

Alternativa SSE (para uso desde navegador o clientes remotos):
    python mcp_servers/snomed_server.py --transport sse --port 8001
"""
import sys
import asyncio
import argparse
import json
import logging
import builtins

# ── CRÍTICO: redirigir print() a stderr ANTES de cualquier import del proyecto ──
# El protocolo MCP usa stdout para JSON-RPC. Cualquier print() que llegue a
# stdout corrompe el protocolo y provoca JSONDecodeError en el cliente.
_original_print = builtins.print
def _stderr_print(*args, **kwargs):
    kwargs['file'] = sys.stderr
    _original_print(*args, **kwargs)
builtins.print = _stderr_print
# ─────────────────────────────────────────────────────────────────────────────

# Añadimos el directorio raíz al path para importar los módulos del proyecto
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__file__)))

import config  # noqa: F401 — configura GOOGLE_API_KEY y entorno
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from database.snomed_queries import (
    buscar_concepto_snomed,
    validar_concepto_snomed,
    obtener_reglas_mapeo_cie10,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("snomed-mcp-server")

# ─── Servidor MCP ────────────────────────────────────────────────────────────

app = Server("snomed-irbd")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """
    Declara las herramientas disponibles en este servidor MCP.
    El cliente MCP descubre estas herramientas automáticamente al conectarse.
    """
    return [
        types.Tool(
            name="buscar_snomed",
            description=(
                "Busca conceptos SNOMED CT en la IRBD española por texto clínico libre. "
                "Devuelve una lista de conceptos candidatos con su conceptId y descripción. "
                "Si la búsqueda en edición española ('es') no devuelve resultados, "
                "prueba con edition='int' para buscar en la edición internacional."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Diagnóstico o término clínico en texto libre (español o inglés)",
                    },
                    "edition": {
                        "type": "string",
                        "enum": ["es", "int"],
                        "default": "es",
                        "description": "'es' = Edición Española IRBD, 'int' = Edición Internacional",
                    },
                    "limite": {
                        "type": "integer",
                        "default": 5,
                        "description": "Número máximo de conceptos candidatos a devolver",
                    },
                },
                "required": ["texto"],
            },
        ),
        types.Tool(
            name="validar_snomed",
            description=(
                "Verifica si un conceptId SNOMED CT existe y está activo en la IRBD. "
                "Úsalo para confirmar que un código SNOMED sugerido por el LLM es real "
                "antes de incluirlo en un registro FHIR."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "concept_id": {
                        "type": "string",
                        "description": "Identificador numérico SNOMED CT (SCTID)",
                    }
                },
                "required": ["concept_id"],
            },
        ),
        types.Tool(
            name="obtener_reglas_cie10",
            description=(
                "Devuelve las reglas de mapeo SNOMED CT → CIE-10-ES (Extended Map RefSet) "
                "de la OMS para un conceptId dado, ordenadas por mapGroup y mapPriority. "
                "Llama a esta herramienta ANTES de intentar codificar a CIE-10."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "snomed_id": {
                        "type": "string",
                        "description": "ConceptId SNOMED CT a mapear a CIE-10",
                    }
                },
                "required": ["snomed_id"],
            },
        ),
        types.Tool(
            name="evaluar_regla_mapeo",
            description=(
                "Registra la evaluación de una regla de mapeo SNOMED→CIE-10 por parte del agente. "
                "El agente llama a esta herramienta para cada regla que evalúa, indicando si "
                "se cumple o no según el contexto clínico del paciente."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "map_group": {
                        "type": "integer",
                        "description": "Número de grupo de mapeo SNOMED",
                    },
                    "map_priority": {
                        "type": "integer",
                        "description": "Prioridad dentro del grupo (menor = mayor prioridad)",
                    },
                    "map_rule": {
                        "type": "string",
                        "description": "Texto de la regla condicional (ej. 'IFA 44054006 | Diabetes mellitus |')",
                    },
                    "map_target": {
                        "type": "string",
                        "description": "Código CIE-10-ES candidato para esta regla",
                    },
                    "cumple_regla": {
                        "type": "boolean",
                        "description": "True si el contexto clínico satisface la condición de la regla",
                    },
                    "razonamiento": {
                        "type": "string",
                        "description": "Justificación clínica de por qué se cumple o no la regla",
                    },
                    "informacion_faltante": {
                        "type": "string",
                        "description": "Dato clínico ausente que impide confirmar la regla, o null si no aplica",
                    },
                },
                "required": [
                    "map_group", "map_priority", "map_rule",
                    "map_target", "cumple_regla", "razonamiento"
                ],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """
    Despacha las llamadas a herramientas desde el cliente MCP.
    Cada herramienta ejecuta lógica real contra la base de datos IRBD.
    """
    logger.info(f"Tool llamada: {name} con args: {list(arguments.keys())}")

    if name == "buscar_snomed":
        resultados = buscar_concepto_snomed(
            texto_busqueda=arguments["texto"],
            limite=arguments.get("limite", 5),
            edition=arguments.get("edition", "es"),
        )
        return [types.TextContent(
            type="text",
            text=json.dumps(resultados, ensure_ascii=False, indent=2)
        )]

    if name == "validar_snomed":
        existe = validar_concepto_snomed(arguments["concept_id"])
        return [types.TextContent(
            type="text",
            text=json.dumps({"concept_id": arguments["concept_id"], "activo": existe})
        )]

    if name == "obtener_reglas_cie10":
        reglas = obtener_reglas_mapeo_cie10(arguments["snomed_id"])
        return [types.TextContent(
            type="text",
            text=json.dumps(reglas, ensure_ascii=False, indent=2)
        )]

    if name == "evaluar_regla_mapeo":
        # Esta herramienta es "semántica": el LLM la usa para estructurar su razonamiento.
        # El servidor simplemente confirma el registro y devuelve el resultado tal como llegó.
        return [types.TextContent(
            type="text",
            text=json.dumps({
                "registrado": True,
                "map_group": arguments["map_group"],
                "map_target": arguments["map_target"],
                "cumple_regla": arguments["cumple_regla"],
            })
        )]

    raise ValueError(f"Herramienta desconocida: '{name}'")


# ─── Punto de entrada ────────────────────────────────────────────────────────

async def main_stdio():
    """Modo stdio: el cliente MCP lanza este proceso como subproceso."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SNOMED IRBD MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Protocolo de transporte MCP (default: stdio)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(main_stdio())
    else:
        # SSE requiere mcp[sse] — útil para clientes remotos
        print("SSE transport: instala 'mcp[sse]' y configura un servidor ASGI.", file=sys.stderr)
        sys.exit(1)
