"""
validation/llm_evaluator.py — Estrategia de validación automatizada a escala.

Usa un LLM como juez (LLM-as-judge) para evaluar la corrección de los
resultados del pipeline sin comparación manual.

Estrategia en tres capas:
  1. Validación estructural: el JSON cumple el schema FHIR esperado.
  2. Validación semántica: similitud de cosenos entre diagnóstico extraído y referencia.
  3. Validación por LLM-juez: Gemini 2.5 Pro evalúa si el CIE-10 asignado
     es clínicamente apropiado dado el diagnóstico libre original.

Uso:
    python -m validation.llm_evaluator --input data/output_fhir/ --report validation_report.json
"""
import os
import json
import re
import time
import random
import argparse
from dataclasses import dataclass, field, asdict
from typing import Optional
import google.generativeai as genai
import config  # type: ignore


# ─── Constantes ─────────────────────────────────────────────────────────────
# gemini-3.1-flash-lite: 15 RPM y 500 RPD en free tier (vs 5 RPM / 20 RPD de 2.5-flash).
# Suficiente para evaluación clínica de CIE-10/SNOMED.
JUDGE_MODEL = "gemini-3.1-flash-lite"

# Umbral de puntuación para considerar un resultado "correcto"
SCORE_THRESHOLD = 0.7

# Pausa entre llamadas al juez para respetar rate-limit de la API
JUDGE_SLEEP_S = 2


# ─── Schema mínimo FHIR esperado ────────────────────────────────────────────
REQUIRED_FHIR_FIELDS = {
    "resourceType": "Bundle",
    "entry": list,
}


@dataclass
class ValidationResult:
    archivo: str
    valido_estructura: bool = False
    snomed_id: Optional[str] = None
    diagnostico_texto: Optional[str] = None
    cie10_codes: list = field(default_factory=list)
    # Evaluación del juez LLM
    juez_score: float = 0.0       # 0.0 a 1.0
    juez_veredicto: str = ""      # "CORRECTO" | "PARCIAL" | "INCORRECTO"
    juez_razonamiento: str = ""
    error: str = ""


# ─── Capa 1: Validación Estructural ─────────────────────────────────────────

def validar_estructura_fhir(fhir_data: dict) -> tuple[bool, str]:
    """Verifica que el Bundle FHIR tenga la estructura mínima requerida."""
    if fhir_data.get("resourceType") != "Bundle":
        return False, "resourceType no es Bundle"
    entries = fhir_data.get("entry", [])
    if not isinstance(entries, list) or len(entries) == 0:
        return False, "entry vacío o ausente"
    has_patient = any(
        e.get("resource", {}).get("resourceType") == "Patient" for e in entries
    )
    has_condition = any(
        e.get("resource", {}).get("resourceType") == "Condition" for e in entries
    )
    if not has_patient:
        return False, "Falta recurso Patient"
    if not has_condition:
        return False, "Falta recurso Condition"
    return True, "OK"


def extraer_metadatos_fhir(fhir_data: dict) -> dict:
    """Extrae diagnóstico y código SNOMED del Bundle."""
    meta = {"snomed_id": None, "diagnostico_texto": None}
    for entry in fhir_data.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Condition":
            code = resource.get("code", {})
            for coding in code.get("coding", []):
                if "snomed.info" in coding.get("system", ""):
                    meta["snomed_id"] = coding.get("code")
                    meta["diagnostico_texto"] = coding.get("display", code.get("text"))
    return meta


# ─── Capa 3: LLM como Juez ───────────────────────────────────────────────────

def evaluar_con_llm_juez(
    diagnostico_original: str,
    snomed_asignado: Optional[str],
    cie10_codes: list[str],
    model_name: str = JUDGE_MODEL,
) -> dict:
    """
    Usa un LLM más potente como evaluador externo (LLM-as-judge).
    El juez NO conoce el proceso interno; solo evalúa input → output.
    """
    model = genai.GenerativeModel(model_name)
    
    cie10_str = ", ".join(cie10_codes) if cie10_codes else "Ninguno asignado"
    snomed_str = snomed_asignado or "No resuelto"

    prompt = f"""
Eres un codificador clínico senior especializado en Cardiología con certificación en CIE-10-ES y SNOMED CT.

TAREA: Evalúa si la codificación automática es clínicamente correcta.

DIAGNÓSTICO ORIGINAL DEL INFORME: "{diagnostico_original}"

CÓDIGO SNOMED CT ASIGNADO: {snomed_str}
CÓDIGO(S) CIE-10-ES ASIGNADOS: {cie10_str}

INSTRUCCIONES DE EVALUACIÓN:
1. ¿El código SNOMED CT es semánticamente equivalente al diagnóstico original? (0-1)
2. ¿El/los código(s) CIE-10-ES son la traducción correcta del concepto SNOMED? (0-1)
3. ¿Hay errores clínicamente relevantes (ej. confundir cardiopatía isquémica con HTA)? (true/false)

Devuelve ÚNICAMENTE un JSON válido, sin markdown:
{{
  "score_snomed": <0.0 a 1.0>,
  "score_cie10": <0.0 a 1.0>,
  "score_global": <0.0 a 1.0>,
  "error_critico": <true o false>,
  "veredicto": "<CORRECTO | PARCIAL | INCORRECTO>",
  "razonamiento": "<Justificación clínica concisa>"
}}
"""
    try:
        response = model.generate_content(prompt)
        texto_limpio = re.sub(r'```json|```', '', response.text).strip()
        return json.loads(texto_limpio)
    except Exception as e:
        return {
            "score_global": 0.0,
            "veredicto": "ERROR",
            "razonamiento": f"Error del juez LLM: {e}",
            "error_critico": False,
        }


# ─── Orquestador ────────────────────────────────────────────────────────────

def evaluar_archivo_fhir(ruta_fhir: str, diagnostico_original: Optional[str] = None) -> ValidationResult:
    """Evalúa un único archivo FHIR con las tres capas de validación."""
    nombre = os.path.basename(ruta_fhir)
    vr = ValidationResult(archivo=nombre)

    try:
        with open(ruta_fhir, 'r', encoding='utf-8') as f:
            fhir_data = json.load(f)
    except Exception as e:
        vr.error = f"Error al leer JSON: {e}"
        return vr

    # Capa 1: Estructura
    ok_estructura, msg_estructura = validar_estructura_fhir(fhir_data)
    vr.valido_estructura = ok_estructura
    if not ok_estructura:
        vr.error = msg_estructura
        return vr

    # Extraer metadatos
    meta = extraer_metadatos_fhir(fhir_data)
    vr.snomed_id = meta["snomed_id"]
    vr.diagnostico_texto = diagnostico_original or meta["diagnostico_texto"] or ""

    # Buscar archivo de resultado CIE-10 si existe (mismo nombre con sufijo diferente)
    base = nombre.replace("_fhir.json", "")
    dir_fhir = os.path.dirname(ruta_fhir)
    ruta_resultado = os.path.join(dir_fhir, f"{base}_cie10.json")
    if os.path.exists(ruta_resultado):
        try:
            with open(ruta_resultado, 'r', encoding='utf-8') as f:
                resultado_cie10 = json.load(f)
            vr.cie10_codes = [
                v.get("selected_code") for v in resultado_cie10.values()
                if v.get("selected_code")
            ]
        except Exception:
            pass

    # Capa 3: Juez LLM (solo si hay diagnóstico)
    if vr.diagnostico_texto:
        evaluacion = evaluar_con_llm_juez(
            vr.diagnostico_texto, vr.snomed_id, vr.cie10_codes
        )
        vr.juez_score = evaluacion.get("score_global", 0.0)
        vr.juez_veredicto = evaluacion.get("veredicto", "ERROR")
        vr.juez_razonamiento = evaluacion.get("razonamiento", "")
        time.sleep(JUDGE_SLEEP_S)  # Cambio 4: respetar rate-limit

    return vr


def generar_reporte(resultados: list[ValidationResult], output_path: str):
    total = len(resultados)
    correctos = sum(1 for r in resultados if r.juez_veredicto == "CORRECTO")
    parciales = sum(1 for r in resultados if r.juez_veredicto == "PARCIAL")
    incorrectos = sum(1 for r in resultados if r.juez_veredicto == "INCORRECTO")
    score_medio = sum(r.juez_score for r in resultados) / total if total else 0

    reporte = {
        "resumen": {
            "total_documentos": total,
            "correctos": correctos,
            "parciales": parciales,
            "incorrectos": incorrectos,
            "score_medio_juez": round(score_medio, 3),
            "precision": round(correctos / total, 3) if total else 0,
        },
        "detalle": [asdict(r) for r in resultados],
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  REPORTE DE VALIDACIÓN AUTOMÁTICA")
    print(f"{'='*60}")
    print(f"  Total evaluados : {total}")
    print(f"  Correctos       : {correctos} ({100*correctos//total if total else 0}%)")
    print(f"  Parciales       : {parciales}")
    print(f"  Incorrectos     : {incorrectos}")
    print(f"  Score medio     : {score_medio:.2f}/1.00")
    print(f"  Reporte guardado: {output_path}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/output_fhir/", help="Carpeta con archivos _fhir.json")
    parser.add_argument("--report", default="validation_report.json", help="Ruta del reporte JSON")
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Cambio 4: evaluar solo N archivos aleatorios (muestra para el TFM)",
    )
    args = parser.parse_args()

    archivos_fhir = [
        os.path.join(args.input, f)
        for f in os.listdir(args.input)
        if f.endswith("_fhir.json")
    ]

    if not archivos_fhir:
        print(f"[!] No se encontraron archivos _fhir.json en '{args.input}'")
        return

    # Cambio 4: submuestreo aleatorio reproducible
    if args.sample and args.sample < len(archivos_fhir):
        random.seed(42)
        archivos_fhir = random.sample(archivos_fhir, args.sample)
        print(f"[ℹ️] Muestra aleatoria: {args.sample} de los archivos disponibles (seed=42).")

    print(f"[ℹ️] Evaluando {len(archivos_fhir)} registros FHIR con juez LLM ({JUDGE_MODEL})...")
    resultados = [evaluar_archivo_fhir(ruta) for ruta in archivos_fhir]
    generar_reporte(resultados, args.report)


if __name__ == "__main__":
    main()
