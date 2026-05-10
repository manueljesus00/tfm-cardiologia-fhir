"""
benchmark_multi.py — Script de benchmarking multi-modelo.

Envía el mismo informe clínico a todos los modelos configurados,
mide tiempo/tokens/coste y guarda los resultados en CSV y PostgreSQL.

USO:
    # Ejecutar con todos los modelos configurados en MODELS (abajo)
    python benchmark_multi.py

    # Solo un archivo específico
    python benchmark_multi.py --file informe.txt

    # Solo ciertos providers
    python benchmark_multi.py --providers gemini openai

    # Incluir modelos locales (requiere Ollama corriendo)
    python benchmark_multi.py --providers gemini ollama

    # Guardar CSV en ruta específica
    python benchmark_multi.py --output data/benchmark_multi_report.csv

    # Sin guardar en PostgreSQL
    python benchmark_multi.py --no-db

    # Mostrar tabla de precios de referencia
    python benchmark_multi.py --precios

CONFIGURACIÓN DE MODELOS:
    Edita la lista MODELS de este archivo para añadir/quitar modelos.
    Necesitas las API Keys correspondientes en .env.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# Aseguramos que el root del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent))

import config  # Carga GOOGLE_API_KEY y otros dotenv
from benchmark.providers import build_provider, ModelProvider
from benchmark.runner import ejecutar_con_modelo, imprimir_tabla_comparativa, MultiModelMetrics
from benchmark.pricing import tabla_precios_markdown


# ─── Modelos a comparar ───────────────────────────────────────────────────────
# Edita esta lista para añadir o quitar modelos del benchmark.
# type: "gemini" | "openai" | "anthropic" | "ollama"

MODELS: list[dict] = [
    # ── Cloud: Google ──────────────────────────────────────────────────────────
    {
        "type":     "gemini",
        "model_id": "gemini-2.5-flash",
    },

    # ── Cloud: OpenAI ─────────────────────────────────────────────────────────
    # Requiere OPENAI_API_KEY en .env
    # {"type": "openai", "model_id": "gpt-4o-mini"},

    # ── Local: Ollama (CPU — 16 GB RAM, sin GPU dedicada) ─────────────────────
    # Antes de usar: docker compose up ollama -d
    # Descargar modelo: docker exec -it ollama ollama pull <model_id>
    #
    # ✅ RECOMENDADOS para CPU con 16 GB RAM:
    # {"type": "ollama", "model_id": "phi4-mini"},     # ~4 GB RAM · ~12-15 tok/s · mejor opción
    # {"type": "ollama", "model_id": "llama3.2:3b"},   # ~3 GB RAM · ~15-20 tok/s · más rápido
    # {"type": "ollama", "model_id": "gemma3:4b"},     # ~3 GB RAM · ~12-18 tok/s · buena alternativa
    #
    # ⚠️  VIABLES pero lentos en CPU (varios minutos/informe):
    # {"type": "ollama", "model_id": "mistral:7b"},    # ~5 GB RAM · ~5-8 tok/s
    # {"type": "ollama", "model_id": "llama3.1:8b"},   # ~6 GB RAM · ~4-7 tok/s
    # {"type": "ollama", "model_id": "deepseek-r1:7b"},# ~5 GB RAM · ~4-6 tok/s (muy lento)
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def cargar_providers(filtro_providers: list[str] | None = None) -> list[ModelProvider]:
    """Instancia los providers de MODELS, opcionalmente filtrando por tipo."""
    providers = []
    for cfg in MODELS:
        if filtro_providers and cfg["type"] not in filtro_providers:
            continue
        try:
            p = build_provider(cfg)
            providers.append(p)
            print(f"  [✓] {p.name} ({p.provider})")
        except (ValueError, ImportError) as e:
            print(f"  [✗] {cfg.get('model_id', '?')} — omitido: {e}")
    return providers


def guardar_csv(all_metrics: list[MultiModelMetrics], output_path: str):
    if not all_metrics:
        return
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_metrics[0].to_dict().keys())
        writer.writeheader()
        for m in all_metrics:
            writer.writerow(m.to_dict())
    print(f"[📊] CSV guardado: {output_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark multi-modelo del pipeline de homogeneización clínica."
    )
    parser.add_argument(
        "--file",
        help="Archivo específico (en data/input_informes/). Sin este flag procesa todos.",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=["gemini", "groq", "openai", "anthropic", "ollama"],
        help="Filtrar por tipo de provider (por defecto: todos los configurados en MODELS).",
    )
    parser.add_argument(
        "--output",
        default="data/benchmark_multi_report.csv",
        help="Ruta de salida del CSV (default: data/benchmark_multi_report.csv).",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="No guardar resultados en PostgreSQL.",
    )
    parser.add_argument(
        "--precios",
        action="store_true",
        help="Mostrar tabla de precios de referencia y salir.",
    )
    args = parser.parse_args()

    if args.precios:
        print("\nTABLA DE PRECIOS LLM (Mayo 2026)\n")
        print(tabla_precios_markdown())
        return

    # ── Directorios ───────────────────────────────────────────────────────────
    input_dir  = Path("data") / "input_informes"
    output_dir = Path("data") / "output_fhir"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.file:
        archivos = [input_dir / args.file]
    else:
        archivos = sorted(
            f for f in input_dir.iterdir() if f.suffix.lower() in (".txt", ".pdf")
        )

    if not archivos:
        print(f"[!] No hay archivos en '{input_dir}'. Añade informes clínicos en TXT o PDF.")
        return

    # ── Providers ─────────────────────────────────────────────────────────────
    print(f"\nCargando providers configurados...")
    providers = cargar_providers(args.providers)
    if not providers:
        print("[!] No hay providers disponibles. Revisa las API Keys en .env.")
        return

    print(f"\nModelos: {len(providers)} | Archivos: {len(archivos)}")
    print(f"Combinaciones a procesar: {len(providers) * len(archivos)}\n")

    # ── Ejecución ─────────────────────────────────────────────────────────────
    all_metrics: list[MultiModelMetrics] = []

    for archivo in archivos:
        for provider in providers:
            print(f"▶ {provider.name} × {archivo.name} ...")
            try:
                m = ejecutar_con_modelo(str(archivo), provider, str(output_dir))
                all_metrics.append(m)
                status = "✅" if m.exito else f"❌ {m.error}"
                print(
                    f"  → {status}  |  {m.tiempo_total_s:.2f}s  |  "
                    f"{m.tokens_totales} tokens  |  €{m.coste_eur:.4f}"
                )
            except Exception as e:
                print(f"  → 💥 Error inesperado: {e}")

    # ── Resultados ────────────────────────────────────────────────────────────
    imprimir_tabla_comparativa(all_metrics)
    guardar_csv(all_metrics, args.output)

    # ── Persistencia en PostgreSQL ────────────────────────────────────────────
    if not args.no_db:
        from benchmark.db_writer import ensure_table_exists, guardar_metricas
        ensure_table_exists()
        inserted = guardar_metricas(all_metrics)
        if inserted:
            print(f"[🗄️ ] {inserted} filas guardadas en PostgreSQL (tabla: benchmark_multimodel).")
        else:
            print("[⚠️ ] No se guardaron filas en PostgreSQL (¿DB disponible?).")
    else:
        print("[ℹ️ ] Modo --no-db: resultados no persistidos en PostgreSQL.")


if __name__ == "__main__":
    main()
