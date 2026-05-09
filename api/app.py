"""
api/app.py — FastAPI REST para el pipeline de codificación clínica.

Instalación:
    pip install fastapi uvicorn python-multipart

Arranque:
    uvicorn api.app:app --reload

Endpoints:
    POST /procesar        — Sube un informe (.txt o .pdf) y devuelve FHIR + CIE-10
    GET  /resultado/{id}  — Recupera el resultado por ID de procesamiento
    GET  /health          — Healthcheck

El servidor MCP SNOMED se lanza automáticamente al arrancar FastAPI
y se cierra al apagarlo. No depende de VS Code.
"""
import os
import uuid
import json
import tempfile
from typing import Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config  # Carga GOOGLE_API_KEY

from fase1_homogeneizacion import AgenteExtractorNER, crear_fhir_base
from fase2_inferencia_cie10 import extraer_contexto_desde_fhir, AgenteCodificadorCardiologia
from database.snomed_queries import obtener_reglas_mapeo_cie10
from core.processing_result import ProcessingResult, ConfidenceLevel
from mcp_client import MCPSnomedClient


# ─── Ciclo de vida — MCP sube y baja con FastAPI ─────────────────────────────

# Estado global de la aplicación
_app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lanza el servidor MCP SNOMED al arrancar FastAPI y lo cierra al apagarse.
    Usamos MCPSnomedClient (síncrono) porque los agentes son código síncrono.
    El cliente gestiona su propio thread interno, compatible con asyncio.
    """
    print("[FastAPI] Conectando con servidor MCP SNOMED IRBD...")
    mcp = MCPSnomedClient()
    mcp.start()
    try:
        _app_state["mcp"] = mcp
        _app_state["agente_ner"] = AgenteExtractorNER(mcp_client=mcp)
        _app_state["agente_cod"] = AgenteCodificadorCardiologia()
        print("[FastAPI] Agentes inicializados. API lista.")
        yield  # La aplicación corre aquí
    finally:
        mcp.stop()
        print("[FastAPI] Servidor MCP SNOMED desconectado.")


# ─── Inicialización ──────────────────────────────────────────────────────────
app = FastAPI(
    title="TFM Cardiología FHIR — API de Codificación Clínica",
    description="Pipeline automatizado de extracción y codificación de informes cardiológicos.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorios de trabajo
OUTPUT_DIR = Path("data/output_fhir")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Almacén en memoria de resultados (en producción: Redis o base de datos)
_resultados: dict[str, dict] = {}


def get_agentes():
    """Devuelve los agentes inicializados en el lifespan."""
    agente_ner = _app_state.get("agente_ner")
    agente_cod = _app_state.get("agente_cod")
    if not agente_ner or not agente_cod:
        raise RuntimeError("Los agentes no están inicializados. El servidor MCP puede no estar conectado.")
    return agente_ner, agente_cod


# ─── Modelos de respuesta ────────────────────────────────────────────────────

class ProcesarResponse(BaseModel):
    job_id: str
    estado: str
    mensaje: str


class ResultadoResponse(BaseModel):
    job_id: str
    archivo: str
    confidence_level: str
    snomed_id: Optional[str]
    diagnostico: Optional[str]
    cie10: dict
    fhir_bundle: dict


# ─── Lógica de procesamiento ─────────────────────────────────────────────────

def _procesar_en_background(job_id: str, ruta_tmp: str, extension: str):
    """Tarea de fondo: ejecuta el pipeline completo y almacena el resultado."""
    _resultados[job_id]["estado"] = "procesando"
    agente_ner, agente_cod = get_agentes()

    try:
        datos = agente_ner.extraer_entidades(ruta_tmp)
        if not datos:
            _resultados[job_id].update({"estado": "error", "error": "Fase 1 falló (LLM no respondió)"})
            return

        result = ProcessingResult.from_llm_output(datos)
        if not result.can_proceed_phase2:
            _resultados[job_id].update({"estado": "error", "error": "Confianza insuficiente"})
            return

        ruta_fhir = OUTPUT_DIR / f"{job_id}_fhir.json"
        bundle = crear_fhir_base(result.to_fhir_dict())
        bundle_json = json.loads(bundle.json())
        with open(ruta_fhir, 'w', encoding='utf-8') as f:
            json.dump(bundle_json, f, indent=2, ensure_ascii=False)

        contexto = extraer_contexto_desde_fhir(str(ruta_fhir))
        snomed_id = contexto.get('snomed_id')
        reglas = obtener_reglas_mapeo_cie10(snomed_id) if snomed_id and snomed_id != '0' else []
        cie10 = agente_cod.procesar_historial(contexto['resumen_razonamiento'], reglas)

        _resultados[job_id].update({
            "estado": "completado",
            "confidence_level": result.confidence_level.value,
            "snomed_id": result.snomed_id,
            "diagnostico": result.diagnostico_texto,
            "cie10": cie10,
            "fhir_bundle": bundle_json,
        })

    except Exception as e:
        _resultados[job_id].update({"estado": "error", "error": str(e)})
    finally:
        if os.path.exists(ruta_tmp):
            os.remove(ruta_tmp)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/procesar", response_model=ProcesarResponse)
async def procesar_informe(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Sube un informe médico (.txt o .pdf) y lo procesa de forma asíncrona.
    Devuelve un job_id para consultar el resultado con GET /resultado/{job_id}.
    """
    extension = Path(file.filename).suffix.lower()
    if extension not in (".txt", ".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos .txt o .pdf")

    job_id = str(uuid.uuid4())

    # Guardar archivo temporal con extensión correcta para que el NER lo identifique
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        tmp.write(await file.read())
        ruta_tmp = tmp.name

    _resultados[job_id] = {"estado": "encolado", "archivo": file.filename}
    background_tasks.add_task(_procesar_en_background, job_id, ruta_tmp, extension)

    return ProcesarResponse(
        job_id=job_id,
        estado="encolado",
        mensaje=f"Informe en procesamiento. Consulta el resultado en /resultado/{job_id}",
    )


@app.get("/resultado/{job_id}")
def obtener_resultado(job_id: str):
    """Devuelve el estado y resultado del procesamiento de un informe."""
    if job_id not in _resultados:
        raise HTTPException(404, "Job ID no encontrado")

    data = _resultados[job_id]

    if data["estado"] in ("encolado", "procesando"):
        return JSONResponse({"job_id": job_id, "estado": data["estado"]})

    if data["estado"] == "error":
        raise HTTPException(500, detail={"job_id": job_id, "error": data.get("error")})

    return ResultadoResponse(job_id=job_id, **{k: v for k, v in data.items() if k != "estado"})


# ─── Opcional: servir UI estática ────────────────────────────────────────────
# Si creas un directorio api/static/ con un index.html, puedes servir la UI aquí.
# app.mount("/", StaticFiles(directory="api/static", html=True), name="static")
