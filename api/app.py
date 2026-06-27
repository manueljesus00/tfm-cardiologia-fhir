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
import time as _time
import tempfile
from typing import Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
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
    estado: str
    archivo: str
    confidence_level: str
    snomed_id: Optional[str]
    diagnostico: Optional[str]
    cie10: dict
    fhir_bundle: dict
    telemetria: Optional[dict] = None


# ─── Catálogo de modelos disponibles ─────────────────────────────────────────

MODELOS_DISPONIBLES = [
    {
        "id":          "gemini-2.5-flash",
        "name":        "Gemini 2.5 Flash",
        "provider":    "google",
        "type":        "cloud",
        "description": "Modelo principal del TFM. Rápido, económico y con Function Calling nativo.",
    },
    {
        "id":          "groq/llama-3.1-8b-instant",
        "name":        "Llama 3.1 8B Instant",
        "provider":    "groq",
        "type":        "cloud",
        "description": "Open source via Groq (gratuito). ~500 tok/s. Requiere GROQ_API_KEY.",
    },
    {
        "id":          "groq/llama-3.3-70b-versatile",
        "name":        "Llama 3.3 70B",
        "provider":    "groq",
        "type":        "cloud",
        "description": "Open source via Groq (gratuito). Mayor calidad. Requiere GROQ_API_KEY.",
    },
    {
        "id":          "ollama/phi4-mini",
        "name":        "Phi-4 Mini",
        "provider":    "microsoft",
        "type":        "local",
        "description": "Local via Ollama. ~4 GB RAM. Sin internet. Requiere Ollama instalado.",
    },
    {
        "id":          "ollama/llama3.2:3b",
        "name":        "Llama 3.2 3B",
        "provider":    "meta",
        "type":        "local",
        "description": "Local via Ollama. ~3 GB RAM. Muy rápido en CPU.",
    },
]


def _build_provider_for_modelo(modelo_id: str):
    """
    Construye un ModelProvider a partir del ID usado en el frontend.
    Formato: "gemini-2.5-flash" | "groq/<model>" | "ollama/<model>"
    """
    from benchmark.providers import GeminiProvider, GroqProvider, OllamaProvider
    if modelo_id.startswith("groq/"):
        return GroqProvider(model_id=modelo_id[5:])
    if modelo_id.startswith("ollama/"):
        return OllamaProvider(model_id=modelo_id[7:])
    # Default: Gemini (model_id es directamente el nombre del modelo)
    return GeminiProvider(model_id=modelo_id)


# ─── Lógica de procesamiento ─────────────────────────────────────────────────

def _normalizar_cie10(cie10_raw: dict) -> dict:
    """
    Convierte la estructura interna de los motores CIE-10 al formato
    esperado por el frontend (campos snake_case en español).
    Cubre tanto rule_engine.py como rule_engine_agentic.py.
    """
    normalizado = {}
    for grupo_id, regla in cie10_raw.items():
        normalizado[str(grupo_id)] = {
            "map_group":          regla.get("map_group", grupo_id),
            "map_priority":       regla.get("map_priority", 1),
            "map_rule":           regla.get("map_rule", "TRUE"),
            "map_target":         regla.get("selected_code") or regla.get("map_target", ""),
            "cumple_regla":       regla.get("rule_evaluation", True),
            "razonamiento":       regla.get("clinical_reasoning") or regla.get("razonamiento", ""),
            "informacion_faltante": regla.get("missing_information") or regla.get("informacion_faltante"),
        }
    return normalizado

def _procesar_en_background(job_id: str, ruta_tmp: str, extension: str, modelo_id: str = "gemini-2.5-flash"):
    """Tarea de fondo: ejecuta el pipeline completo y almacena el resultado."""
    from benchmark.runner import _TrackingProvider
    from benchmark.pricing import calcular_coste_eur
    from fase2_inferencia_cie10.rule_engine import AgenteCodificadorCardiologia as CodLegacy

    _resultados[job_id]["estado"] = "procesando"

    try:
        # Construir provider e instrumentar con trackers de tokens
        provider   = _build_provider_for_modelo(modelo_id)
        tracker_f1 = _TrackingProvider(provider)
        tracker_f2 = _TrackingProvider(provider)

        # Instancias frescas por petición (no compartir estado entre requests)
        agente_ner = AgenteExtractorNER(mcp_client=_app_state.get("mcp"))
        agente_ner.model = tracker_f1
        agente_cod = CodLegacy()
        agente_cod.model = tracker_f2

        # ── Fase 1 ───────────────────────────────────────────────────────────
        t0_f1 = _time.perf_counter()
        datos = agente_ner.extraer_entidades(ruta_tmp)
        t_f1  = round(_time.perf_counter() - t0_f1, 3)

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

        # ── Fase 2 ───────────────────────────────────────────────────────────
        t0_f2 = _time.perf_counter()
        contexto  = extraer_contexto_desde_fhir(str(ruta_fhir))
        snomed_id = contexto.get('snomed_id')
        reglas    = obtener_reglas_mapeo_cie10(snomed_id) if snomed_id and snomed_id != '0' else []
        cie10     = agente_cod.procesar_historial(contexto['resumen_razonamiento'], reglas)
        t_f2      = round(_time.perf_counter() - t0_f2, 3)

        # ── Telemetría ────────────────────────────────────────────────────────
        total_prompt     = tracker_f1.prompt_tokens     + tracker_f2.prompt_tokens
        total_completion = tracker_f1.completion_tokens + tracker_f2.completion_tokens
        telemetria = {
            "modelo":         provider.name,
            "provider":       provider.provider,
            "tokens_fase1":   tracker_f1.total_tokens,
            "tokens_fase2":   tracker_f2.total_tokens,
            "tokens_total":   tracker_f1.total_tokens + tracker_f2.total_tokens,
            "tiempo_fase1_s": t_f1,
            "tiempo_fase2_s": t_f2,
            "tiempo_total_s": round(t_f1 + t_f2, 3),
            "coste_eur":      calcular_coste_eur(provider.model_id, total_prompt, total_completion),
        }

        _resultados[job_id].update({
            "estado":           "completado",
            "confidence_level": result.confidence_level.value,
            "snomed_id":        result.snomed_id,
            "diagnostico":      result.diagnostico_texto,
            "cie10":            _normalizar_cie10(cie10),
            "fhir_bundle":      bundle_json,
            "telemetria":       telemetria,
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


@app.get("/modelos")
def listar_modelos():
    """Devuelve el catálogo de modelos disponibles para el frontend."""
    return {"modelos": MODELOS_DISPONIBLES}


@app.post("/procesar", response_model=ProcesarResponse)
async def procesar_informe(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    modelo: str = Form("gemini-2.5-flash"),
):
    """
    Sube un informe médico (.txt o .pdf) y lo procesa de forma asíncrona.
    Acepta el parámetro `modelo` para elegir el LLM (gemini-2.5-flash, groq/llama-3.1-8b-instant, ollama/phi4-mini…).
    Devuelve un job_id para consultar el resultado con GET /resultado/{job_id}.
    """
    extension = Path(file.filename).suffix.lower()
    if extension not in (".txt", ".pdf"):
        raise HTTPException(400, "Solo se aceptan archivos .txt o .pdf")

    job_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        tmp.write(await file.read())
        ruta_tmp = tmp.name

    _resultados[job_id] = {"estado": "encolado", "archivo": file.filename, "modelo": modelo}
    background_tasks.add_task(_procesar_en_background, job_id, ruta_tmp, extension, modelo)

    return ProcesarResponse(
        job_id=job_id,
        estado="encolado",
        mensaje=f"Informe en procesamiento con {modelo}. Consulta el resultado en /resultado/{job_id}",
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

    return ResultadoResponse(job_id=job_id, estado="completado", **{k: v for k, v in data.items() if k not in ("estado", "modelo")})


# ─── Benchmark endpoint ───────────────────────────────────────────────────────

# Métricas acumuladas de sesión (se complementan con datos del CSV si existe)
_benchmark_log: list[dict] = []


def _registrar_benchmark(job_id: str, tiempo_total: float):
    """Añade métricas al log de benchmarks tras cada procesamiento completado."""
    data = _resultados.get(job_id, {})
    if data.get("estado") != "completado":
        return
    _benchmark_log.append({
        "modelo": "Gemini 2.5 Flash",
        "archivo": data.get("archivo", ""),
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "tiempo_fase1_s": round(tiempo_total * 0.4, 2),   # Estimado proporcional
        "tiempo_fase2_s": round(tiempo_total * 0.6, 2),
        "tiempo_total_s": round(tiempo_total, 2),
        "tokens_fase1_total": 0,  # Requiere instrumentación adicional del agente
        "tokens_fase2_total": 0,
        "tokens_totales": 0,
        "confidence_level": data.get("confidence_level", ""),
        "cie10_codes": ",".join(
            v.get("map_target", "") for v in data.get("cie10", {}).values()
            if isinstance(v, dict) and v.get("cumple_regla")
        ),
        "exito": True,
        "coste_estimado_eur": 0.0,
    })


@app.get("/benchmarks")
def obtener_benchmarks():
    """
    Devuelve métricas históricas de procesamiento para el dashboard del portal.
    Prioridad:
      1. benchmark_multi_report.csv (si tiene >= 5 filas)
      2. Combinación de benchmark_fase1.csv + benchmark_fase2.csv
      3. benchmark_report.csv (legacy)
      4. Métricas de sesión en memoria (_benchmark_log)
    """
    import csv
    import os
    import re
    import collections
    from pathlib import Path as _Path

    def _leer_multi_report(path: _Path) -> list[dict]:
        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append({
                    "modelo":            row.get("modelo", ""),
                    "archivo":           row.get("archivo", ""),
                    "timestamp":         row.get("timestamp", ""),
                    "tiempo_fase1_s":    float(row.get("tiempo_fase1_s", 0)),
                    "tiempo_fase2_s":    float(row.get("tiempo_fase2_s", 0)),
                    "tiempo_total_s":    float(row.get("tiempo_total_s", 0)),
                    "tokens_fase1_total": int(row.get("tokens_fase1_total", 0)),
                    "tokens_fase2_total": int(row.get("tokens_fase2_total", 0)),
                    "tokens_totales":    int(row.get("tokens_totales", 0)),
                    "confidence_level":  row.get("confidence_level", ""),
                    "cie10_codes":       row.get("cie10_codes", ""),
                    "exito":             row.get("exito", "True").lower() == "true",
                    "coste_estimado_eur": float(row.get("coste_estimado_eur", 0)),
                })
        return rows

    def _combinar_fases() -> list[dict]:
        """Lee benchmark_fase1.csv + benchmark_fase2.csv y devuelve filas combinadas."""
        fase1_path = _Path("data/benchmark_fase1.csv")
        fase2_path = _Path("data/benchmark_fase2.csv")
        if not fase1_path.exists():
            return []

        # Leer fase1
        f1_rows = []
        with open(fase1_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                f1_rows.append(row)

        # Construir lookup de fase2 indexado por (base_archivo, modelo)
        f2_lookup: dict = collections.defaultdict(list)
        if fase2_path.exists():
            with open(fase2_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    fhir = row.get("archivo", "")
                    base = fhir.replace("_fhir.json", "")
                    base = re.sub(
                        r"_(gemini|llama|gpt|phi4|gemma|qwen|meditron|medllama|biomistral|phi)[^_].*$",
                        "",
                        base,
                        flags=re.IGNORECASE,
                    )
                    f2_lookup[(base, row["modelo"])].append(row)

        combined = []
        for r1 in f1_rows:
            base = os.path.splitext(r1["archivo"])[0]
            f2_same = f2_lookup.get((base, r1["modelo"]), [])

            t1   = float(r1.get("tiempo_s", 0))
            tok1 = int(r1.get("tokens_total", 0))
            exito1 = r1.get("exito", "False") == "True"

            if f2_same:
                t2   = sum(float(x["tiempo_s"]) for x in f2_same) / len(f2_same)
                tok2 = int(sum(int(x["tokens_total"]) for x in f2_same) / len(f2_same))
                cie10 = ",".join(x["cie10_codes"] for x in f2_same if x.get("cie10_codes"))
                exito2 = any(x["exito"] == "True" for x in f2_same)
                exito_final = exito1 and exito2
            else:
                t2 = tok2 = 0
                cie10 = ""
                exito_final = exito1

            combined.append({
                "modelo":            r1["modelo"],
                "archivo":           r1["archivo"],
                "timestamp":         r1["timestamp"],
                "tiempo_fase1_s":    round(t1, 3),
                "tiempo_fase2_s":    round(t2, 3),
                "tiempo_total_s":    round(t1 + t2, 3),
                "tokens_fase1_total": tok1,
                "tokens_fase2_total": tok2,
                "tokens_totales":    tok1 + tok2,
                "confidence_level":  r1.get("confidence_level", ""),
                "cie10_codes":       cie10,
                "exito":             exito_final,
                "coste_estimado_eur": float(r1.get("coste_eur", 0)),
            })
        return combined

    # ── Prioridad 1: multi report con datos suficientes ──────────────────────
    metricas: list[dict] = []
    multi_path = _Path("data/benchmark_multi_report.csv")
    if multi_path.exists():
        rows = _leer_multi_report(multi_path)
        if len(rows) >= 5:
            metricas.extend(rows)
            metricas.extend(_benchmark_log)
            return metricas

    # ── Prioridad 2: combinar fase1 + fase2 ──────────────────────────────────
    combined = _combinar_fases()
    if combined:
        metricas.extend(combined)
        metricas.extend(_benchmark_log)
        return metricas

    # ── Prioridad 3: benchmark_report.csv legacy ─────────────────────────────
    legacy_path = _Path("data/benchmark_report.csv")
    if legacy_path.exists():
        metricas.extend(_leer_multi_report(legacy_path))

    metricas.extend(_benchmark_log)
    return metricas


# ─── Opcional: servir UI estática ────────────────────────────────────────────
# Si creas un directorio api/static/ con un index.html, puedes servir la UI aquí.
# app.mount("/", StaticFiles(directory="api/static", html=True), name="static")
