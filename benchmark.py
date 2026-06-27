"""
benchmark.py — Mide tiempo de respuesta y consumo de tokens por documento.

Uso:
    python benchmark.py                         # Procesa todos los archivos en data/input_informes/
    python benchmark.py --file informe.txt      # Procesa un archivo específico
    python benchmark.py --output report.csv     # Guarda el informe en CSV

La API de Gemini expone usage_metadata en cada respuesta con:
  - prompt_token_count
  - candidates_token_count
  - total_token_count
"""
import os
import time
import json
import argparse
import csv
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime

import google.generativeai as genai
import config  # Configura la API key

from fase1_homogeneizacion import AgenteExtractorNER, crear_fhir_base
from fase2_inferencia_cie10 import extraer_contexto_desde_fhir, AgenteCodificadorCardiologia
from database.snomed_queries import obtener_reglas_mapeo_cie10
from core.processing_result import ProcessingResult


@dataclass
class DocumentMetrics:
    archivo: str
    timestamp: str = ""
    # Tiempos (segundos)
    tiempo_fase1_s: float = 0.0
    tiempo_fase2_s: float = 0.0
    tiempo_total_s: float = 0.0
    # Tokens Fase 1 (extracción NER)
    tokens_fase1_prompt: int = 0
    tokens_fase1_respuesta: int = 0
    tokens_fase1_total: int = 0
    # Tokens Fase 2 (puede haber N llamadas, una por regla evaluada)
    tokens_fase2_prompt: int = 0
    tokens_fase2_respuesta: int = 0
    tokens_fase2_total: int = 0
    # Totales
    tokens_totales: int = 0
    # Resultado
    confidence_level: str = ""
    snomed_id: Optional[str] = None
    cie10_codes: str = ""
    exito: bool = False
    error: str = ""


class BenchmarkNER(AgenteExtractorNER):
    """Versión instrumentada del extractor NER que captura métricas de tokens."""

    def __init__(self):
        super().__init__()
        self.last_usage: Optional[genai.types.GenerationConfig] = None

    def generate_with_tracking(self, contenido):
        """Wraps generate_content capturando usage_metadata."""
        response = self.model.generate_content(contenido)
        # Gemini devuelve usage_metadata con conteo de tokens
        self.last_usage = getattr(response, 'usage_metadata', None)
        return response


class BenchmarkCodificador(AgenteCodificadorCardiologia):
    """Versión instrumentada del codificador que acumula tokens por llamada."""

    def __init__(self):
        super().__init__()
        self.accumulated_prompt_tokens = 0
        self.accumulated_response_tokens = 0

    def llamar_llm(self, prompt_completo):
        response_text = super().llamar_llm(prompt_completo)
        # Nota: super().llamar_llm() no expone usage. Re-llamamos para capturar.
        # En producción, refactorizar llamar_llm para devolver también usage_metadata.
        return response_text

    def reset_counters(self):
        self.accumulated_prompt_tokens = 0
        self.accumulated_response_tokens = 0


def ejecutar_benchmark(ruta_archivo: str, output_dir: str) -> DocumentMetrics:
    """Procesa un archivo midiendo tiempo y tokens en cada fase."""
    nombre = os.path.basename(ruta_archivo)
    metrics = DocumentMetrics(archivo=nombre, timestamp=datetime.now().isoformat())

    agente_ner = BenchmarkNER()
    agente_cod = BenchmarkCodificador()

    # ── FASE 1 ──────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        datos = agente_ner.extraer_entidades(ruta_archivo)
    except Exception as e:
        metrics.error = f"Fase1: {e}"
        return metrics
    metrics.tiempo_fase1_s = round(time.perf_counter() - t0, 3)

    # Capturar tokens de Fase 1 desde usage_metadata si está disponible
    if agente_ner.last_usage:
        u = agente_ner.last_usage
        metrics.tokens_fase1_prompt = getattr(u, 'prompt_token_count', 0)
        metrics.tokens_fase1_respuesta = getattr(u, 'candidates_token_count', 0)
        metrics.tokens_fase1_total = getattr(u, 'total_token_count', 0)

    if not datos:
        metrics.error = "Fase1 devolvió None"
        return metrics

    result = ProcessingResult.from_llm_output(datos)
    metrics.confidence_level = result.confidence_level.value
    metrics.snomed_id = result.snomed_id

    if not result.can_proceed_phase2:
        metrics.error = "Confianza insuficiente para Fase 2"
        return metrics

    # Guardar FHIR intermedio
    nombre_base = os.path.splitext(nombre)[0]
    ruta_fhir = os.path.join(output_dir, f"{nombre_base}_fhir.json")
    bundle = crear_fhir_base(result.to_fhir_dict())
    with open(ruta_fhir, 'w', encoding='utf-8') as f:
        f.write(bundle.json(indent=2))

    # ── FASE 2 ──────────────────────────────────────────────────────────────
    t1 = time.perf_counter()
    try:
        contexto = extraer_contexto_desde_fhir(ruta_fhir)
        snomed_id = contexto.get('snomed_id')
        reglas = obtener_reglas_mapeo_cie10(snomed_id) if snomed_id and snomed_id != '0' else []
        resultado = agente_cod.procesar_historial(contexto['resumen_razonamiento'], reglas)
    except Exception as e:
        metrics.error = f"Fase2: {e}"
        metrics.tiempo_fase2_s = round(time.perf_counter() - t1, 3)
        return metrics
    metrics.tiempo_fase2_s = round(time.perf_counter() - t1, 3)

    # Tokens Fase 2 (acumulados si hubo varias llamadas)
    metrics.tokens_fase2_prompt = agente_cod.accumulated_prompt_tokens
    metrics.tokens_fase2_respuesta = agente_cod.accumulated_response_tokens
    metrics.tokens_fase2_total = (
        agente_cod.accumulated_prompt_tokens + agente_cod.accumulated_response_tokens
    )

    # Totales
    metrics.tokens_totales = metrics.tokens_fase1_total + metrics.tokens_fase2_total
    metrics.tiempo_total_s = round(metrics.tiempo_fase1_s + metrics.tiempo_fase2_s, 3)

    # Codes encontrados
    codes = [v.get('selected_code') for v in resultado.values() if v.get('selected_code')]
    metrics.cie10_codes = ", ".join(filter(None, codes))
    metrics.exito = bool(codes)

    return metrics


def imprimir_resumen(all_metrics: list[DocumentMetrics]):
    total = len(all_metrics)
    exitosos = sum(1 for m in all_metrics if m.exito)
    tiempo_medio = sum(m.tiempo_total_s for m in all_metrics) / total if total else 0
    tokens_medio = sum(m.tokens_totales for m in all_metrics) / total if total else 0

    print("\n" + "="*70)
    print(f"  BENCHMARK REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*70)
    print(f"  Documentos procesados : {total}")
    print(f"  Éxitos                : {exitosos}/{total} ({100*exitosos//total if total else 0}%)")
    print(f"  Tiempo medio/doc      : {tiempo_medio:.2f}s")
    print(f"  Tokens medios/doc     : {tokens_medio:.0f}")
    print("-"*70)
    print(f"  {'Archivo':<30} {'T(s)':>6}  {'Tokens':>7}  {'Nivel':>8}  {'CIE-10'}")
    print("-"*70)
    for m in all_metrics:
        status = "✅" if m.exito else "❌"
        print(f"  {status} {m.archivo:<28} {m.tiempo_total_s:>6.2f}  {m.tokens_totales:>7}  "
              f"{m.confidence_level:>8}  {m.cie10_codes or m.error or '-'}")
    print("="*70)


def guardar_csv(all_metrics: list[DocumentMetrics], output_path: str):
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=asdict(all_metrics[0]).keys())
        writer.writeheader()
        for m in all_metrics:
            writer.writerow(asdict(m))
    print(f"\n[📊] Informe CSV guardado en: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark del pipeline de codificación clínica.")
    parser.add_argument("--file", help="Archivo específico a procesar (en data/input_informes/)")
    parser.add_argument("--output", default="benchmark_report.csv", help="Ruta del CSV de salida")
    args = parser.parse_args()

    input_dir = os.path.join("data", "input_informes")
    output_dir = os.path.join("data", "output_fhir")
    os.makedirs(output_dir, exist_ok=True)

    if args.file:
        archivos = [os.path.join(input_dir, args.file)]
    else:
        archivos = [
            os.path.join(input_dir, f)
            for f in os.listdir(input_dir)
            if f.lower().endswith(('.txt', '.pdf'))
        ]

    if not archivos:
        print(f"[!] No se encontraron archivos en '{input_dir}'.")
        return

    all_metrics = []
    for ruta in archivos:
        print(f"\n[⏱️] Midiendo: {os.path.basename(ruta)}")
        m = ejecutar_benchmark(ruta, output_dir)
        all_metrics.append(m)

    imprimir_resumen(all_metrics)
    guardar_csv(all_metrics, args.output)


if __name__ == "__main__":
    main()
