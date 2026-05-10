"""
benchmark/runner.py — Orquestador multi-modelo del pipeline.

Ejecuta las dos fases del pipeline (NER + CIE-10) inyectando cualquier
ModelProvider, sin modificar el código original de los agentes.

Estrategia:
  - Fase 1 (NER): BenchmarkNER_Multi subclasifica AgenteExtractorNER y sustituye
    self.model por el provider. La lógica de extracción no cambia.
  - Fase 2 (CIE-10): BenchmarkCodificador_Multi subclasifica AgenteCodificador-
    Cardiologia (rule_engine.py, NO el agéntico) y sustituye self.model.
    Se usa la versión secuencial porque el modo agéntico usa Function Calling
    nativo de Gemini, que no es portable a otros proveedores.
"""
from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from benchmark.providers import ModelProvider
from benchmark.pricing import calcular_coste_usd, calcular_coste_eur
from fase1_homogeneizacion import AgenteExtractorNER, crear_fhir_base
from fase2_inferencia_cie10 import extraer_contexto_desde_fhir
from fase2_inferencia_cie10.rule_engine import AgenteCodificadorCardiologia
from database.snomed_queries import obtener_reglas_mapeo_cie10
from core.processing_result import ProcessingResult

logger = logging.getLogger(__name__)


# ─── Dataclass de métricas ────────────────────────────────────────────────────

@dataclass
class MultiModelMetrics:
    archivo: str
    modelo: str
    provider: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    # Fase 1
    tiempo_fase1_s: float = 0.0
    tokens_fase1_prompt: int = 0
    tokens_fase1_completion: int = 0
    tokens_fase1_total: int = 0
    # Fase 2
    tiempo_fase2_s: float = 0.0
    tokens_fase2_prompt: int = 0
    tokens_fase2_completion: int = 0
    tokens_fase2_total: int = 0
    # Totales
    tiempo_total_s: float = 0.0
    tokens_totales: int = 0
    coste_usd: float = 0.0
    coste_eur: float = 0.0
    # Resultado
    confidence_level: str = ""
    snomed_id: Optional[str] = None
    cie10_codes: str = ""
    exito: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Agentes instrumentados ───────────────────────────────────────────────────

class _BenchmarkNER(AgenteExtractorNER):
    """
    Extiende AgenteExtractorNER para aceptar cualquier ModelProvider.
    Sustituye self.model (GenerativeModel de Gemini) por el adaptador del provider.
    Acumula métricas de tokens de todas las llamadas.
    """
    def __init__(self, provider: ModelProvider):
        # Llamamos a __init__ de la clase base sin MCP (modo directo DB)
        super().__init__(mcp_client=None)
        # Reemplazamos el modelo de Gemini por el adaptador del provider
        self.model = provider  # generate_content() es compatible
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self._provider = provider

    def extraer_entidades(self, ruta_archivo: str):
        """Override para capturar usage_metadata tras la llamada."""
        result = super().extraer_entidades(ruta_archivo)
        # AgenteExtractorNER no expone usage directamente; usamos el hook de generate_content
        # La captura real ocurre en _capture_usage_hook (ver abajo)
        return result


class _TrackingProvider:
    """
    Wrapper sobre ModelProvider que captura usage_metadata en cada llamada.
    Diseñado para inyectarse como self.model en los agentes.
    """
    def __init__(self, provider: ModelProvider):
        self._provider = provider
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

    def generate_content(self, prompt):
        response = self._provider.generate_content(prompt)
        u = response.usage_metadata
        self.prompt_tokens     += u.prompt_token_count
        self.completion_tokens += u.candidates_token_count
        self.total_tokens      += u.total_token_count
        return response

    def reset(self):
        self.prompt_tokens = self.completion_tokens = self.total_tokens = 0


# ─── Runner por documento ─────────────────────────────────────────────────────

def ejecutar_con_modelo(
    ruta_archivo: str,
    provider: ModelProvider,
    output_dir: str,
) -> MultiModelMetrics:
    """
    Procesa un documento con un provider concreto y devuelve las métricas.

    Args:
        ruta_archivo: Ruta al .txt o .pdf del informe clínico.
        provider:     ModelProvider instanciado (Gemini, OpenAI, Ollama, etc.)
        output_dir:   Directorio donde guardar el FHIR Bundle intermedio.
    """
    nombre = os.path.basename(ruta_archivo)
    metrics = MultiModelMetrics(
        archivo=nombre,
        modelo=provider.name,
        provider=provider.provider,
    )

    # Wrapping del provider para capturar tokens
    tracker_f1 = _TrackingProvider(provider)
    tracker_f2 = _TrackingProvider(provider)

    agente_ner = AgenteExtractorNER(mcp_client=None)
    agente_ner.model = tracker_f1  # inyección del tracker

    agente_cod = AgenteCodificadorCardiologia()
    agente_cod.model = tracker_f2  # inyección del tracker

    # ── FASE 1: Extracción NER ────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        datos = agente_ner.extraer_entidades(ruta_archivo)
    except Exception as e:
        metrics.error = f"Fase1: {e}"
        return metrics
    metrics.tiempo_fase1_s = round(time.perf_counter() - t0, 3)

    metrics.tokens_fase1_prompt     = tracker_f1.prompt_tokens
    metrics.tokens_fase1_completion = tracker_f1.completion_tokens
    metrics.tokens_fase1_total      = tracker_f1.total_tokens

    if not datos:
        metrics.error = "Fase1: el modelo no devolvió entidades"
        return metrics

    result = ProcessingResult.from_llm_output(datos)
    metrics.confidence_level = result.confidence_level.value
    metrics.snomed_id = result.snomed_id

    if not result.can_proceed_phase2:
        metrics.error = f"Confianza insuficiente ({result.confidence_level.value})"
        return metrics

    # Guardar FHIR intermedio
    nombre_base = os.path.splitext(nombre)[0]
    modelo_slug = provider.model_id.replace("/", "_").replace(":", "_")
    ruta_fhir = os.path.join(output_dir, f"{nombre_base}_{modelo_slug}_fhir.json")
    try:
        bundle = crear_fhir_base(result.to_fhir_dict())
        with open(ruta_fhir, "w", encoding="utf-8") as f:
            f.write(bundle.json(indent=2))
    except Exception as e:
        metrics.error = f"FHIR build: {e}"
        return metrics

    # ── FASE 2: Codificación CIE-10 ──────────────────────────────────────────
    t1 = time.perf_counter()
    try:
        contexto = extraer_contexto_desde_fhir(ruta_fhir)
        snomed_id = contexto.get("snomed_id")
        reglas = obtener_reglas_mapeo_cie10(snomed_id) if snomed_id and snomed_id != "0" else []
        resultado_cie10 = agente_cod.procesar_historial(contexto["resumen_razonamiento"], reglas)
    except Exception as e:
        metrics.error = f"Fase2: {e}"
        metrics.tiempo_fase2_s = round(time.perf_counter() - t1, 3)
        return metrics
    metrics.tiempo_fase2_s = round(time.perf_counter() - t1, 3)

    metrics.tokens_fase2_prompt     = tracker_f2.prompt_tokens
    metrics.tokens_fase2_completion = tracker_f2.completion_tokens
    metrics.tokens_fase2_total      = tracker_f2.total_tokens

    # ── Totales ───────────────────────────────────────────────────────────────
    metrics.tokens_totales = metrics.tokens_fase1_total + metrics.tokens_fase2_total
    metrics.tiempo_total_s = round(metrics.tiempo_fase1_s + metrics.tiempo_fase2_s, 3)

    metrics.coste_usd = round(
        calcular_coste_usd(
            provider.model_id,
            metrics.tokens_fase1_prompt + metrics.tokens_fase2_prompt,
            metrics.tokens_fase1_completion + metrics.tokens_fase2_completion,
        ), 6
    )
    metrics.coste_eur = round(
        calcular_coste_eur(
            provider.model_id,
            metrics.tokens_fase1_prompt + metrics.tokens_fase2_prompt,
            metrics.tokens_fase1_completion + metrics.tokens_fase2_completion,
        ), 6
    )

    codes = [v.get("selected_code") for v in resultado_cie10.values() if v.get("selected_code")]
    metrics.cie10_codes = ", ".join(filter(None, codes))
    metrics.exito = bool(codes)

    return metrics


# ─── Informe de resultados ────────────────────────────────────────────────────

def imprimir_tabla_comparativa(all_metrics: list[MultiModelMetrics]):
    """Imprime una tabla comparativa multi-modelo en consola."""
    if not all_metrics:
        print("[!] Sin métricas que mostrar.")
        return

    print("\n" + "=" * 100)
    print(f"  BENCHMARK MULTI-MODELO — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 100)
    print(
        f"  {'Modelo':<32} {'Archivo':<22} {'T(s)':>6}  "
        f"{'Tokens':>7}  {'Coste EUR':>10}  {'Nivel':>8}  {'CIE-10'}"
    )
    print("-" * 100)
    for m in all_metrics:
        status = "✅" if m.exito else "❌"
        coste = f"€{m.coste_eur:.4f}" if m.coste_eur else "€0.0000"
        print(
            f"  {status} {m.modelo:<30} {m.archivo:<22} {m.tiempo_total_s:>6.2f}  "
            f"{m.tokens_totales:>7}  {coste:>10}  {m.confidence_level:>8}  "
            f"{m.cie10_codes or m.error or '—'}"
        )
    print("=" * 100)

    # Resumen agrupado por modelo
    modelos = {}
    for m in all_metrics:
        modelos.setdefault(m.modelo, []).append(m)

    print("\n  RESUMEN POR MODELO")
    print(f"  {'Modelo':<32} {'Docs':>4}  {'OK':>4}  {'T_med(s)':>8}  {'Tok_med':>8}  {'€_total':>9}")
    print("  " + "-" * 68)
    for modelo, mlist in modelos.items():
        ok = sum(1 for m in mlist if m.exito)
        t_med = sum(m.tiempo_total_s for m in mlist) / len(mlist)
        tok_med = sum(m.tokens_totales for m in mlist) / len(mlist)
        eur_total = sum(m.coste_eur for m in mlist)
        print(
            f"  {modelo:<32} {len(mlist):>4}  {ok:>4}  "
            f"{t_med:>8.2f}  {tok_med:>8.0f}  €{eur_total:>8.4f}"
        )
    print()
