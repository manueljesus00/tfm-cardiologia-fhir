"""
benchmark_fases.py — Benchmark por fases del pipeline de codificación clínica.

Evalúa cada fase del pipeline de forma independiente con timeouts por documento
para evitar bloqueos causados por modelos lentos o sin respuesta.

  - Fase 1 : Extracción NER + generación de FHIR Bundle (homogeneización semántica)
  - Fase 2 : Inferencia CIE-10 a partir de FHIR Bundles pre-generados
  - Ambas  : ejecuta Fase 1 y alimenta automáticamente Fase 2 con los FHIR generados

MÉTRICAS EXTRA PARA EVALUACIÓN TFM:
  Fase 1 → completitud FHIR (%), entidades demográficas, diagnósticos por tipo,
            resolución SNOMED, throughput (tokens/s), coste/token.
  Fase 2 → reglas evaluadas vs disponibles, tasa de resolución por grupo,
            errores de JSON del LLM, categorías CIE-10, throughput.

USO:
    # Solo Fase 1 con todos los modelos (timeout 120s/doc)
    python benchmark_fases.py --fase 1

    # Solo Fase 2 usando FHIR ya existentes en un directorio
    python benchmark_fases.py --fase 2 --fhir-dir data/output_fhir

    # Ambas fases; Fase 2 consume los FHIR que genera Fase 1
    python benchmark_fases.py --fase ambas

    # Filtrar providers y ajustar timeout
    python benchmark_fases.py --fase 1 --providers gemini groq --timeout 180

    # Sin guardar en PostgreSQL
    python benchmark_fases.py --fase 1 --no-db

    # Ver tabla de precios
    python benchmark_fases.py --precios
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: F401 — carga dotenv y configura GOOGLE_API_KEY
from benchmark.providers import build_provider, ModelProvider
from benchmark.pricing import calcular_coste_usd, calcular_coste_eur, tabla_precios_markdown
from benchmark.llm_logger import LLMLogger
from fase1_homogeneizacion import AgenteExtractorNER, crear_fhir_base
from fase2_inferencia_cie10 import extraer_contexto_desde_fhir
from fase2_inferencia_cie10.rule_engine import AgenteCodificadorCardiologia
from database.snomed_queries import obtener_reglas_mapeo_cie10
from core.processing_result import ProcessingResult


# ─── Modelos a comparar ───────────────────────────────────────────────────────
# Edita esta lista para añadir o quitar modelos.
MODELS: list[dict] = [
    # Cloud - Google
    {"type": "gemini", "model_id": "gemini-3.1-flash-lite"},
    # Cloud gratuito - Groq
    {"type": "groq", "model_id": "llama-3.3-70b-versatile"},
    {"type": "groq", "model_id": "llama-3.1-8b-instant"},
    # Local - Ollama (todos los modelos disponibles)
    {"type": "ollama", "model_id": "phi4-mini"},
    {"type": "ollama", "model_id": "llama3.2:3b"},
    {"type": "ollama", "model_id": "gemma3:4b"},
    {"type": "ollama", "model_id": "qwen2.5:7b"},
    {"type": "ollama", "model_id": "meditron:7b"},
    {"type": "ollama", "model_id": "medllama2:latest"},
    {"type": "ollama", "model_id": "cniongolo/biomistral:latest"},
]

DEFAULT_TIMEOUT_F1 = 120   # segundos por documento en Fase 1
DEFAULT_TIMEOUT_F2 = 90    # segundos por documento en Fase 2


# ─── Dataclasses de métricas ──────────────────────────────────────────────────

@dataclass
class MetricasFase1:
    """Métricas detalladas de la Fase 1: Extracción NER + Generación FHIR."""
    archivo: str
    modelo: str
    provider: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Rendimiento temporal
    tiempo_s: float = 0.0
    timeout_ocurrido: bool = False

    # Consumo de tokens
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    tokens_por_segundo: float = 0.0    # throughput: tokens_total / tiempo_s

    # Coste estimado
    coste_usd: float = 0.0
    coste_eur: float = 0.0
    coste_por_token_usd: float = 0.0   # coste_usd / tokens_total

    # Calidad de la extracción
    confidence_level: str = ""
    snomed_id: Optional[str] = None
    snomed_resuelto: bool = False       # True si snomed_id presente y != "0"
    num_entidades_demo: int = 0         # campos demográficos no nulos (max 4)
    num_diagnosticos_total: int = 0
    num_diagnosticos_principal: int = 0
    num_diagnosticos_secundario: int = 0
    num_diagnosticos_antecedente: int = 0

    # Calidad del FHIR generado
    fhir_generado: bool = False
    fhir_completitud_pct: float = 0.0  # % hojas no nulas/vacías en el JSON FHIR
    fhir_num_recursos: int = 0          # nº recursos en el Bundle FHIR

    # Estado
    exito: bool = False
    error: str = ""
    ruta_fhir: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MetricasFase2:
    """Métricas detalladas de la Fase 2: Inferencia de código CIE-10."""
    archivo: str
    modelo: str
    provider: str
    fhir_origen_modelo: str             # modelo que generó el FHIR de entrada
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Rendimiento temporal
    tiempo_s: float = 0.0
    timeout_ocurrido: bool = False

    # Consumo de tokens
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    tokens_por_segundo: float = 0.0

    # Coste estimado
    coste_usd: float = 0.0
    coste_eur: float = 0.0

    # Calidad de la codificación
    snomed_id: Optional[str] = None
    num_reglas_disponibles: int = 0     # reglas en la IRBD para ese SNOMED
    num_reglas_evaluadas: int = 0       # llamadas LLM reales (para antes del 1er match)
    num_grupos_snomed: int = 0          # grupos de mapeo únicos
    num_codigos_encontrados: int = 0
    tasa_resolucion: float = 0.0        # codigos_encontrados / grupos_snomed
    json_errores_llm: int = 0           # respuestas LLM que no fueron JSON válido
    cie10_codes: str = ""
    cie10_categorias: str = ""          # prefijos de capítulo, ej. "I, I, J"

    # Estado
    exito: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Instrumentación de providers (captura de tokens) ────────────────────────

class _TrackingProvider:
    """Wrapper sobre ModelProvider que acumula tokens por llamada."""

    def __init__(self, provider: ModelProvider, phase_name: str = "?"):
        self._provider = provider
        self.phase_name = phase_name
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

    def generate_content(self, prompt):
        response = self._provider.generate_content(prompt)
        u = response.usage_metadata
        self.prompt_tokens     += u.prompt_token_count
        self.completion_tokens += u.candidates_token_count
        self.total_tokens      += u.total_token_count
        LLMLogger.log_call(
            model=self._provider.name,
            phase=self.phase_name,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            response=response.text,
            prompt_tokens=u.prompt_token_count,
            completion_tokens=u.candidates_token_count,
            latency_s=0.0,
        )
        return response

    def reset(self):
        self.prompt_tokens = self.completion_tokens = self.total_tokens = 0


# ─── Codificador CIE-10 instrumentado ────────────────────────────────────────

class _InstrumentedCodificador(AgenteCodificadorCardiologia):
    """
    Subclase de AgenteCodificadorCardiologia que registra métricas adicionales:
    número real de llamadas LLM, errores JSON y resultados por regla.
    """

    def __init__(self):
        super().__init__()
        self.llamadas_llm: int = 0
        self.json_errores: int = 0

    def llamar_llm(self, prompt_completo: str) -> str:
        self.llamadas_llm += 1
        respuesta = super().llamar_llm(prompt_completo)
        try:
            json.loads(respuesta)
        except (json.JSONDecodeError, ValueError):
            self.json_errores += 1
        return respuesta

    def reset_counters(self):
        self.llamadas_llm = 0
        self.json_errores = 0


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fhir_completitud(ruta_fhir: str) -> tuple[float, int]:
    """
    Calcula el porcentaje de hojas no nulas/vacías en el JSON FHIR y el
    número de recursos del Bundle.

    Returns:
        (completitud_pct, num_recursos)
    """
    try:
        with open(ruta_fhir, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0.0, 0

    num_recursos = sum(1 for e in data.get("entry", []) if e.get("resource"))

    total = filled = 0

    def _walk(obj):
        nonlocal total, filled
        if isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
        else:
            total += 1
            if obj not in (None, "", "unknown", "Desconocido"):
                filled += 1

    _walk(data)
    pct = round(100.0 * filled / total, 1) if total else 0.0
    return pct, num_recursos


def _cie10_categorias(codes: list[str]) -> str:
    """Devuelve las categorías principales CIE-10 (prefijo letra+número) deduplicadas."""
    cats = []
    seen = set()
    for c in codes:
        if c and len(c) >= 3:
            cat = c[:3]
            if cat not in seen:
                cats.append(cat)
                seen.add(cat)
    return ", ".join(cats)


def _ejecutar_con_timeout(fn, timeout_s: float, *args, **kwargs):
    """
    Ejecuta fn(*args, **kwargs) en un hilo con un timeout máximo.
    Devuelve (resultado, timed_out).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout_s), False
        except concurrent.futures.TimeoutError:
            return None, True
        # No cancelamos el future para no interrumpir un modelo en medio de una respuesta;
        # el hilo terminará de forma natural al completar la llamada bloqueante.


def _guardar_fila_csv(ruta: str, fila: dict, es_primera: bool):
    """Escribe una sola fila en el CSV (append). Crea cabecera si es la primera."""
    mode = "w" if es_primera else "a"
    with open(ruta, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fila.keys())
        if es_primera:
            writer.writeheader()
        writer.writerow(fila)


def cargar_providers(filtro: list[str] | None = None) -> list[ModelProvider]:
    providers = []
    for cfg in MODELS:
        if filtro and cfg["type"] not in filtro:
            continue
        try:
            p = build_provider(cfg)
            providers.append(p)
            print(f"  [✓] {p.name} ({p.provider})")
        except (ValueError, ImportError) as e:
            print(f"  [✗] {cfg.get('model_id', '?')} — omitido: {e}")
    return providers


# ─── Ejecución Fase 1 ─────────────────────────────────────────────────────────

def _run_fase1(ruta_archivo: str, provider: ModelProvider, output_dir: str) -> MetricasFase1:
    """Ejecuta la Fase 1 (NER + FHIR) para un documento y un provider."""
    nombre = Path(ruta_archivo).name
    m = MetricasFase1(archivo=nombre, modelo=provider.name, provider=provider.provider)

    tracker = _TrackingProvider(provider, phase_name="Fase1-NER")
    agente = AgenteExtractorNER(mcp_client=None)
    agente.model = tracker

    t0 = time.perf_counter()
    try:
        datos = agente.extraer_entidades(ruta_archivo)
    except Exception as e:
        m.error = f"Fase1 NER: {e}"
        m.tiempo_s = round(time.perf_counter() - t0, 3)
        return m

    m.tiempo_s = round(time.perf_counter() - t0, 3)

    # Tokens
    m.tokens_prompt     = tracker.prompt_tokens
    m.tokens_completion = tracker.completion_tokens
    m.tokens_total      = tracker.total_tokens
    if m.tiempo_s > 0:
        m.tokens_por_segundo = round(m.tokens_total / m.tiempo_s, 1)

    # Coste
    m.coste_usd = round(calcular_coste_usd(provider.model_id, m.tokens_prompt, m.tokens_completion), 6)
    m.coste_eur = round(calcular_coste_eur(provider.model_id, m.tokens_prompt, m.tokens_completion), 6)
    if m.tokens_total > 0:
        m.coste_por_token_usd = round(m.coste_usd / m.tokens_total, 9)

    if not datos:
        m.error = "Fase1: el modelo no devolvió entidades"
        return m

    # Calidad de extracción
    result = ProcessingResult.from_llm_output(datos)
    m.confidence_level = result.confidence_level.value
    m.snomed_id        = result.snomed_id
    m.snomed_resuelto  = bool(result.snomed_id and result.snomed_id not in ("0", ""))

    # Conteo demográfico
    demo_fields = [result.nombre, result.apellidos, result.genero if result.genero not in ("unknown", "") else None, result.fecha_nacimiento]
    m.num_entidades_demo = sum(1 for v in demo_fields if v)

    # Diagnósticos
    diags = getattr(result, "_diagnosticos_completos", [])
    m.num_diagnosticos_total      = len(diags)
    m.num_diagnosticos_principal  = sum(1 for d in diags if d.get("tipo") == "PRINCIPAL")
    m.num_diagnosticos_secundario = sum(1 for d in diags if d.get("tipo") == "SECUNDARIO")
    m.num_diagnosticos_antecedente= sum(1 for d in diags if d.get("tipo") == "ANTECEDENTE")

    if not result.can_proceed_phase2:
        m.error = f"Confianza insuficiente ({result.confidence_level.value})"
        return m

    # Generar FHIR
    nombre_base  = Path(ruta_archivo).stem
    modelo_slug  = provider.model_id.replace("/", "_").replace(":", "_")
    ruta_fhir    = os.path.join(output_dir, f"{nombre_base}_{modelo_slug}_fhir.json")
    try:
        bundle = crear_fhir_base(result.to_fhir_dict())
        with open(ruta_fhir, "w", encoding="utf-8") as f:
            f.write(bundle.json(indent=2))
        m.fhir_generado = True
        m.ruta_fhir = ruta_fhir
        m.fhir_completitud_pct, m.fhir_num_recursos = _fhir_completitud(ruta_fhir)
    except Exception as e:
        m.error = f"FHIR build: {e}"
        return m

    m.exito = True
    return m


def ejecutar_fase1(
    archivos: list[Path],
    providers: list[ModelProvider],
    output_dir: str,
    csv_output: str,
    timeout_s: float,
) -> list[MetricasFase1]:
    """Ejecuta la Fase 1 para todos los archivos × providers con timeout por doc."""
    all_m: list[MetricasFase1] = []
    es_primera_fila = not Path(csv_output).exists()

    total = len(archivos) * len(providers)
    idx = 0
    for archivo in archivos:
        for provider in providers:
            idx += 1
            print(f"\n[F1 {idx}/{total}] {provider.name} × {archivo.name} ...", flush=True)

            resultado, timed_out = _ejecutar_con_timeout(
                _run_fase1, timeout_s, str(archivo), provider, output_dir
            )

            if timed_out or resultado is None:
                nombre = archivo.name
                resultado = MetricasFase1(
                    archivo=nombre,
                    modelo=provider.name,
                    provider=provider.provider,
                    tiempo_s=timeout_s,
                    timeout_ocurrido=True,
                    error=f"Timeout tras {timeout_s}s",
                )
                print(f"  ⏱️  Timeout ({timeout_s}s) — se continúa con el siguiente.")
            else:
                status = "✅" if resultado.exito else f"❌ {resultado.error}"
                print(
                    f"  → {status}  |  {resultado.tiempo_s:.1f}s  |  "
                    f"{resultado.tokens_total} tok  |  "
                    f"{resultado.tokens_por_segundo:.0f} tok/s  |  "
                    f"FHIR {resultado.fhir_completitud_pct:.0f}%"
                )

            all_m.append(resultado)
            _guardar_fila_csv(csv_output, resultado.to_dict(), es_primera_fila)
            es_primera_fila = False

    return all_m


# ─── Ejecución Fase 2 ─────────────────────────────────────────────────────────

def _run_fase2(
    ruta_fhir: str,
    provider: ModelProvider,
    fhir_origen_modelo: str,
) -> MetricasFase2:
    """Ejecuta la Fase 2 (inferencia CIE-10) para un FHIR y un provider."""
    nombre = Path(ruta_fhir).name
    m = MetricasFase2(
        archivo=nombre,
        modelo=provider.name,
        provider=provider.provider,
        fhir_origen_modelo=fhir_origen_modelo,
    )

    tracker = _TrackingProvider(provider, phase_name="Fase2-CIE10")
    codificador = _InstrumentedCodificador()
    codificador.model = tracker

    t0 = time.perf_counter()
    try:
        contexto = extraer_contexto_desde_fhir(ruta_fhir)
        if not contexto:
            m.error = "FHIR inválido o vacío"
            return m

        snomed_id = contexto.get("snomed_id")
        m.snomed_id = snomed_id
        reglas = obtener_reglas_mapeo_cie10(snomed_id) if snomed_id and snomed_id != "0" else []
        m.num_reglas_disponibles = len(reglas)
        m.num_grupos_snomed = len({r["mapGroup"] for r in reglas}) if reglas else 0

        resultado_cie10 = codificador.procesar_historial(contexto["resumen_razonamiento"], reglas)
    except Exception as e:
        m.error = f"Fase2: {e}"
        m.tiempo_s = round(time.perf_counter() - t0, 3)
        return m

    m.tiempo_s = round(time.perf_counter() - t0, 3)

    # Tokens
    m.tokens_prompt     = tracker.prompt_tokens
    m.tokens_completion = tracker.completion_tokens
    m.tokens_total      = tracker.total_tokens
    if m.tiempo_s > 0:
        m.tokens_por_segundo = round(m.tokens_total / m.tiempo_s, 1)

    # Coste
    m.coste_usd = round(calcular_coste_usd(provider.model_id, m.tokens_prompt, m.tokens_completion), 6)
    m.coste_eur = round(calcular_coste_eur(provider.model_id, m.tokens_prompt, m.tokens_completion), 6)

    # Calidad
    m.num_reglas_evaluadas  = codificador.llamadas_llm
    m.json_errores_llm      = codificador.json_errores
    codes = [v.get("selected_code") for v in resultado_cie10.values() if v.get("selected_code")]
    m.num_codigos_encontrados = len(codes)
    m.cie10_codes = ", ".join(filter(None, codes))
    m.cie10_categorias = _cie10_categorias(codes)
    if m.num_grupos_snomed > 0:
        m.tasa_resolucion = round(m.num_codigos_encontrados / m.num_grupos_snomed, 3)

    m.exito = bool(codes)
    return m


def ejecutar_fase2(
    fhir_entries: list[tuple[str, str]],   # [(ruta_fhir, modelo_origen), ...]
    providers: list[ModelProvider],
    csv_output: str,
    timeout_s: float,
) -> list[MetricasFase2]:
    """Ejecuta la Fase 2 para todos los FHIR × providers con timeout por doc (producto cruzado)."""
    all_m: list[MetricasFase2] = []
    es_primera_fila = not Path(csv_output).exists()

    total = len(fhir_entries) * len(providers)
    idx = 0
    for ruta_fhir, modelo_origen in fhir_entries:
        for provider in providers:
            idx += 1
            nombre_corto = Path(ruta_fhir).name
            print(f"\n[F2 {idx}/{total}] {provider.name} × {nombre_corto} ...", flush=True)

            resultado, timed_out = _ejecutar_con_timeout(
                _run_fase2, timeout_s, ruta_fhir, provider, modelo_origen
            )

            if timed_out or resultado is None:
                resultado = MetricasFase2(
                    archivo=Path(ruta_fhir).name,
                    modelo=provider.name,
                    provider=provider.provider,
                    fhir_origen_modelo=modelo_origen,
                    tiempo_s=timeout_s,
                    timeout_ocurrido=True,
                    error=f"Timeout tras {timeout_s}s",
                )
                print(f"  ⏱️  Timeout ({timeout_s}s) — se continúa con el siguiente.")
            else:
                status = "✅" if resultado.exito else f"❌ {resultado.error}"
                print(
                    f"  → {status}  |  {resultado.tiempo_s:.1f}s  |  "
                    f"{resultado.tokens_total} tok  |  "
                    f"Reglas {resultado.num_reglas_evaluadas}/{resultado.num_reglas_disponibles}  |  "
                    f"CIE-10: {resultado.cie10_codes or '—'}"
                )

            all_m.append(resultado)
            _guardar_fila_csv(csv_output, resultado.to_dict(), es_primera_fila)
            es_primera_fila = False

    return all_m


def ejecutar_fase2_pareado(
    pares: list[tuple[str, ModelProvider, str]],  # [(ruta_fhir, provider, modelo_origen), ...]
    csv_output: str,
    timeout_s: float,
) -> list[MetricasFase2]:
    """
    Modo pareado: cada FHIR se evalúa ÚNICAMENTE con el provider que lo generó.
    No hay producto cruzado: N_docs × N_modelos combinaciones en total.
    Esto permite medir el pipeline completo de cada modelo de forma independiente,
    incluyendo modelos locales (Ollama), sin depender de un FHIR de referencia externo.
    """
    all_m: list[MetricasFase2] = []
    es_primera_fila = not Path(csv_output).exists()

    for idx, (ruta_fhir, provider, modelo_origen) in enumerate(pares, start=1):
        nombre_corto = Path(ruta_fhir).name
        print(f"\n[F2-pareado {idx}/{len(pares)}] {provider.name} × {nombre_corto} ...", flush=True)

        resultado, timed_out = _ejecutar_con_timeout(
            _run_fase2, timeout_s, ruta_fhir, provider, modelo_origen
        )

        if timed_out or resultado is None:
            resultado = MetricasFase2(
                archivo=Path(ruta_fhir).name,
                modelo=provider.name,
                provider=provider.provider,
                fhir_origen_modelo=modelo_origen,
                tiempo_s=timeout_s,
                timeout_ocurrido=True,
                error=f"Timeout tras {timeout_s}s",
            )
            print(f"  ⏱️  Timeout ({timeout_s}s) — se continúa con el siguiente.")
        else:
            status = "✅" if resultado.exito else f"❌ {resultado.error}"
            print(
                f"  → {status}  |  {resultado.tiempo_s:.1f}s  |  "
                f"{resultado.tokens_total} tok  |  "
                f"Reglas {resultado.num_reglas_evaluadas}/{resultado.num_reglas_disponibles}  |  "
                f"CIE-10: {resultado.cie10_codes or '—'}"
            )

        all_m.append(resultado)
        _guardar_fila_csv(csv_output, resultado.to_dict(), es_primera_fila)
        es_primera_fila = False

    return all_m


# ─── Tablas resumen en consola ────────────────────────────────────────────────

def _imprimir_resumen_f1(metrics: list[MetricasFase1]):
    if not metrics:
        return
    print("\n" + "=" * 110)
    print(f"  RESUMEN FASE 1 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 110)
    print(
        f"  {'Modelo':<32} {'Docs':>4}  {'OK':>4}  {'TO':>3}  "
        f"{'T_med(s)':>8}  {'tok/s':>7}  {'FHIR%':>6}  "
        f"{'SNOMED%':>7}  {'€_total':>9}"
    )
    print("  " + "-" * 108)
    modelos: dict[str, list[MetricasFase1]] = {}
    for m in metrics:
        modelos.setdefault(m.modelo, []).append(m)
    for modelo, mlist in modelos.items():
        ok     = sum(1 for m in mlist if m.exito)
        to_cnt = sum(1 for m in mlist if m.timeout_ocurrido)
        t_med  = sum(m.tiempo_s for m in mlist) / len(mlist)
        tok_s  = sum(m.tokens_por_segundo for m in mlist if m.tokens_por_segundo) / max(1, sum(1 for m in mlist if m.tokens_por_segundo))
        fhir_p = sum(m.fhir_completitud_pct for m in mlist) / len(mlist)
        snomed = sum(1 for m in mlist if m.snomed_resuelto)
        eur    = sum(m.coste_eur for m in mlist)
        print(
            f"  {modelo:<32} {len(mlist):>4}  {ok:>4}  {to_cnt:>3}  "
            f"{t_med:>8.1f}  {tok_s:>7.0f}  {fhir_p:>5.1f}%  "
            f"{100*snomed//len(mlist):>6}%  €{eur:>8.4f}"
        )
    print("=" * 110)


def _imprimir_resumen_f2(metrics: list[MetricasFase2]):
    if not metrics:
        return
    print("\n" + "=" * 110)
    print(f"  RESUMEN FASE 2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 110)
    print(
        f"  {'Modelo':<32} {'Docs':>4}  {'OK':>4}  {'TO':>3}  "
        f"{'T_med(s)':>8}  {'tok/s':>7}  {'Res%':>5}  "
        f"{'JSONErr':>7}  {'€_total':>9}"
    )
    print("  " + "-" * 108)
    modelos: dict[str, list[MetricasFase2]] = {}
    for m in metrics:
        modelos.setdefault(m.modelo, []).append(m)
    for modelo, mlist in modelos.items():
        ok      = sum(1 for m in mlist if m.exito)
        to_cnt  = sum(1 for m in mlist if m.timeout_ocurrido)
        t_med   = sum(m.tiempo_s for m in mlist) / len(mlist)
        tok_s   = sum(m.tokens_por_segundo for m in mlist if m.tokens_por_segundo) / max(1, sum(1 for m in mlist if m.tokens_por_segundo))
        res_pct = 100 * sum(m.tasa_resolucion for m in mlist) / len(mlist)
        jerr    = sum(m.json_errores_llm for m in mlist)
        eur     = sum(m.coste_eur for m in mlist)
        print(
            f"  {modelo:<32} {len(mlist):>4}  {ok:>4}  {to_cnt:>3}  "
            f"{t_med:>8.1f}  {tok_s:>7.0f}  {res_pct:>4.0f}%  "
            f"{jerr:>7}  €{eur:>8.4f}"
        )
    print("=" * 110)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark por fases del pipeline de codificación clínica FHIR/CIE-10.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fase",
        choices=["1", "2", "ambas"],
        default="ambas",
        help="Fase a ejecutar: '1' (NER+FHIR), '2' (CIE-10), 'ambas' (default).",
    )
    parser.add_argument(
        "--file",
        help="Procesar solo este archivo (en data/input_informes/). Sin flag: todos.",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=["gemini", "groq", "openai", "anthropic", "ollama"],
        help="Filtrar por tipo de provider.",
    )
    parser.add_argument(
        "--fhir-dir",
        default="data/output_fhir",
        help="Directorio con FHIR pre-generados para Fase 2 (default: data/output_fhir).",
    )
    parser.add_argument(
        "--fhir-modelo-ref",
        default=None,
        help=(
            "Cuando --fase 2: slug del modelo cuyo FHIR se usa como entrada "
            "(ej. 'gemini-3.1-flash-lite'). Sin este flag se usan todos los FHIR del directorio."
        ),
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="Procesar solo los primeros N archivos de entrada (útil para pruebas rápidas).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help=(
            f"Timeout en segundos por documento. "
            f"Default: {DEFAULT_TIMEOUT_F1}s para F1, {DEFAULT_TIMEOUT_F2}s para F2."
        ),
    )
    parser.add_argument(
        "--output-f1",
        default="data/benchmark_fase1.csv",
        help="CSV de salida para métricas de Fase 1 (default: data/benchmark_fase1.csv).",
    )
    parser.add_argument(
        "--output-f2",
        default="data/benchmark_fase2.csv",
        help="CSV de salida para métricas de Fase 2 (default: data/benchmark_fase2.csv).",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="No guardar resultados en PostgreSQL.",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Desactivar el monitor web de tráfico LLM.",
    )
    parser.add_argument(
        "--monitor-port",
        type=int,
        default=9999,
        help="Puerto del monitor web (default: 9999).",
    )
    parser.add_argument(
        "--pareado",
        action="store_true",
        help=(
            "Modo pareado (solo con --fase ambas): cada modelo evalúa en Fase 2 "
            "únicamente el FHIR que él mismo generó en Fase 1. "
            "Elimina el producto cruzado y permite medir modelos locales end-to-end."
        ),
    )
    parser.add_argument(
        "--precios",
        action="store_true",
        help="Mostrar tabla de precios de referencia y salir.",
    )
    args = parser.parse_args()

    if args.precios:
        print("\nTABLA DE PRECIOS LLM\n")
        print(tabla_precios_markdown())
        return

    if not args.no_monitor:
        LLMLogger.start(port=args.monitor_port)

    # ── Directorios ───────────────────────────────────────────────────────────
    input_dir  = Path("data") / "input_informes"
    output_dir = Path("data") / "output_fhir"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Archivos de entrada ───────────────────────────────────────────────────
    if args.file:
        archivos = [input_dir / args.file]
    else:
        archivos = sorted(f for f in input_dir.iterdir() if f.suffix.lower() in (".txt", ".pdf"))
        if args.max_files:
            archivos = archivos[:args.max_files]
            print(f"[--max-files] Limitado a los primeros {args.max_files} archivos.")

    if not archivos and args.fase in ("1", "ambas"):
        print(f"[!] No hay archivos en '{input_dir}'.")
        return

    # ── Providers ─────────────────────────────────────────────────────────────
    print("\nCargando providers...")
    providers = cargar_providers(args.providers)
    if not providers:
        print("[!] No hay providers disponibles. Revisa las API Keys en .env.")
        return

    # ── Fase 1 ────────────────────────────────────────────────────────────────
    metricas_f1: list[MetricasFase1] = []
    if args.fase in ("1", "ambas"):
        timeout_f1 = args.timeout or DEFAULT_TIMEOUT_F1
        print(f"\n{'='*60}")
        print(f"  FASE 1 — NER + FHIR")
        print(f"  Modelos: {len(providers)}  |  Archivos: {len(archivos)}")
        print(f"  Timeout: {timeout_f1}s/doc  |  CSV: {args.output_f1}")
        print(f"{'='*60}")

        metricas_f1 = ejecutar_fase1(
            archivos=archivos,
            providers=providers,
            output_dir=str(output_dir),
            csv_output=args.output_f1,
            timeout_s=timeout_f1,
        )
        _imprimir_resumen_f1(metricas_f1)
        print(f"\n[📊] CSV Fase 1 guardado: {args.output_f1}")

    # ── Preparar entradas para Fase 2 ─────────────────────────────────────────
    fhir_entries: list[tuple[str, str]] = []   # (ruta_fhir, modelo_origen)

    if args.fase == "ambas":
        # Usar los FHIR generados en Fase 1 (solo los exitosos)
        fhir_entries = [
            (m.ruta_fhir, m.modelo)
            for m in metricas_f1
            if m.fhir_generado and m.ruta_fhir
        ]
        if not fhir_entries:
            print("\n[!] Ningún FHIR generado en Fase 1 — Fase 2 omitida.")
            return

        # Modo pareado: construir mapa modelo_nombre → provider para el enlace
        if args.pareado:
            provider_map = {p.name: p for p in providers}
            pares_pareados: list[tuple[str, ModelProvider, str]] = [
                (m.ruta_fhir, provider_map[m.modelo], m.modelo)
                for m in metricas_f1
                if m.fhir_generado and m.ruta_fhir and m.modelo in provider_map
            ]

    elif args.fase == "2":
        fhir_dir = Path(args.fhir_dir)
        if not fhir_dir.exists():
            print(f"[!] Directorio FHIR no encontrado: {fhir_dir}")
            return
        candidatos = sorted(fhir_dir.glob("*_fhir.json"))
        if args.fhir_modelo_ref:
            slug = args.fhir_modelo_ref.replace("/", "_").replace(":", "_")
            candidatos = [p for p in candidatos if slug in p.stem]
        for ruta in candidatos:
            # Intentar inferir el modelo origen desde el nombre del archivo
            # Formato: {nombre_base}_{modelo_slug}_fhir.json
            stem = ruta.stem[:-5]  # quitar "_fhir"
            # El slug del modelo es la última parte después del primer "_"
            partes = stem.split("_", 1)
            modelo_origen = partes[1] if len(partes) > 1 else "desconocido"
            fhir_entries.append((str(ruta), modelo_origen))

        if not fhir_entries:
            print(f"[!] No se encontraron FHIR en '{fhir_dir}' con los filtros aplicados.")
            return

    # ── Fase 2 ────────────────────────────────────────────────────────────────
    if args.fase in ("2", "ambas"):
        timeout_f2 = args.timeout or DEFAULT_TIMEOUT_F2
        modo_str = "pareado" if (args.fase == "ambas" and args.pareado) else "producto cruzado"
        n_combinaciones = len(pares_pareados) if (args.fase == "ambas" and args.pareado) else len(fhir_entries) * len(providers)  # type: ignore[possibly-undefined]
        print(f"\n{'='*60}")
        print(f"  FASE 2 — INFERENCIA CIE-10  [{modo_str}]")
        print(f"  Combinaciones: {n_combinaciones}  |  Timeout: {timeout_f2}s")
        print(f"  CSV: {args.output_f2}")
        print(f"{'='*60}")

        if args.fase == "ambas" and args.pareado:
            metricas_f2 = ejecutar_fase2_pareado(
                pares=pares_pareados,  # type: ignore[possibly-undefined]
                csv_output=args.output_f2,
                timeout_s=timeout_f2,
            )
        else:
            metricas_f2 = ejecutar_fase2(
                fhir_entries=fhir_entries,
                providers=providers,
                csv_output=args.output_f2,
                timeout_s=timeout_f2,
            )
        _imprimir_resumen_f2(metricas_f2)
        print(f"\n[📊] CSV Fase 2 guardado: {args.output_f2}")

        # ── Persistencia en PostgreSQL ─────────────────────────────────────
        if not args.no_db:
            _guardar_db_fases(metricas_f1 if args.fase == "ambas" else [], metricas_f2)

    elif args.fase == "1" and not args.no_db:
        _guardar_db_fases(metricas_f1, [])


def _guardar_db_fases(
    metricas_f1: list[MetricasFase1],
    metricas_f2: list[MetricasFase2],
):
    """Persiste métricas de ambas fases en PostgreSQL."""
    try:
        from benchmark.db_writer import _get_connection
        conn = _get_connection()

        # Crear tablas si no existen
        with conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_F1_SQL)
                cur.execute(_CREATE_F2_SQL)

        inserted = 0
        with conn:
            with conn.cursor() as cur:
                for m in metricas_f1:
                    d = m.to_dict()
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join(f"%({k})s" for k in d)
                    cur.execute(f"INSERT INTO benchmark_fase1 ({cols}) VALUES ({placeholders})", d)
                    inserted += 1
                for m in metricas_f2:
                    d = m.to_dict()
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join(f"%({k})s" for k in d)
                    cur.execute(f"INSERT INTO benchmark_fase2 ({cols}) VALUES ({placeholders})", d)
                    inserted += 1
        conn.close()
        print(f"[🗄️ ] {inserted} filas guardadas en PostgreSQL.")
    except Exception as e:
        print(f"[⚠️ ] No se pudo guardar en PostgreSQL: {e}")


_CREATE_F1_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_fase1 (
    id                          SERIAL PRIMARY KEY,
    run_id                      UUID DEFAULT gen_random_uuid(),
    archivo                     TEXT,
    modelo                      TEXT,
    provider                    TEXT,
    timestamp                   TEXT,
    tiempo_s                    FLOAT,
    timeout_ocurrido            BOOLEAN,
    tokens_prompt               INT,
    tokens_completion           INT,
    tokens_total                INT,
    tokens_por_segundo          FLOAT,
    coste_usd                   FLOAT,
    coste_eur                   FLOAT,
    coste_por_token_usd         FLOAT,
    confidence_level            TEXT,
    snomed_id                   TEXT,
    snomed_resuelto             BOOLEAN,
    num_entidades_demo          INT,
    num_diagnosticos_total      INT,
    num_diagnosticos_principal  INT,
    num_diagnosticos_secundario INT,
    num_diagnosticos_antecedente INT,
    fhir_generado               BOOLEAN,
    fhir_completitud_pct        FLOAT,
    fhir_num_recursos           INT,
    exito                       BOOLEAN,
    error                       TEXT,
    ruta_fhir                   TEXT
);
"""

_CREATE_F2_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_fase2 (
    id                      SERIAL PRIMARY KEY,
    run_id                  UUID DEFAULT gen_random_uuid(),
    archivo                 TEXT,
    modelo                  TEXT,
    provider                TEXT,
    fhir_origen_modelo      TEXT,
    timestamp               TEXT,
    tiempo_s                FLOAT,
    timeout_ocurrido        BOOLEAN,
    tokens_prompt           INT,
    tokens_completion       INT,
    tokens_total            INT,
    tokens_por_segundo      FLOAT,
    coste_usd               FLOAT,
    coste_eur               FLOAT,
    snomed_id               TEXT,
    num_reglas_disponibles  INT,
    num_reglas_evaluadas    INT,
    num_grupos_snomed       INT,
    num_codigos_encontrados INT,
    tasa_resolucion         FLOAT,
    json_errores_llm        INT,
    cie10_codes             TEXT,
    cie10_categorias        TEXT,
    exito                   BOOLEAN,
    error                   TEXT
);
"""


if __name__ == "__main__":
    main()
