"""
database/patient_repository.py — Capa de persistencia clínica normalizada.

Gestiona la inserción de Pacientes, Informes y Diagnósticos en la base de datos
propia del proyecto (distinta de la IRBD SNOMED, que es de solo lectura).

Flujo de identidad del paciente:
  1. El LLM extrae identificadores (DNI/NIE/Pasaporte/NASS/NUSS) del informe.
  2. upsert_paciente() busca en BD por CUALQUIER identificador conocido.
  3. Si existe → enriquece el registro con los nuevos identificadores.
  4. Si no existe → crea nuevo paciente.
  5. El informe y sus diagnósticos se vinculan siempre al paciente resuelto.
"""
import json
import uuid
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from database.connection import get_engine

logger = logging.getLogger(__name__)


def ejecutar_migracion(ruta_sql: str = "database/migrations/002_clinical_schema.sql"):
    """
    Ejecuta las migraciones SQL en orden para crear y mantener el esquema clínico.
    Idempotente: usa IF NOT EXISTS y ALTER tolerante a errores.
    """
    migraciones = [
        "database/migrations/002_clinical_schema.sql",
        "database/migrations/004_widen_identifier_columns.sql",
    ]
    engine = get_engine()
    for ruta in migraciones:
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                sql = f.read()
            with engine.begin() as conn:
                conn.execute(text(sql))
            logger.info(f"Migración aplicada: {ruta}")
        except FileNotFoundError:
            logger.warning(f"Archivo de migración no encontrado: {ruta}")
        except Exception as e:
            # ALTER puede fallar si la columna ya tiene el tipo correcto; se ignora
            logger.warning(f"Migración {ruta} omitida (posiblemente ya aplicada): {e}")


# ─── Resolución de entidad ────────────────────────────────────────────────────

def upsert_paciente(
    nombre: Optional[str] = None,
    apellidos: Optional[str] = None,
    fecha_nacimiento: Optional[str] = None,
    genero: str = "unknown",
    dni: Optional[str] = None,
    nie: Optional[str] = None,
    pasaporte: Optional[str] = None,
    nass: Optional[str] = None,
    nuss: Optional[str] = None,
) -> str:
    """
    Resuelve la identidad del paciente y devuelve su UUID.

    Busca por CUALQUIER identificador español antes de insertar.
    Si el paciente existe, actualiza solo los campos que lleguen nuevos.

    Returns:
        UUID del paciente (nuevo o existente) como string.
    """
    # Normalizar la fecha (el LLM puede devolver "Desconocido" o None)
    fecha = None
    if fecha_nacimiento and fecha_nacimiento not in ("Desconocido", "", "null"):
        try:
            fecha = date.fromisoformat(fecha_nacimiento)
        except ValueError:
            pass

    # Normalizar identificadores: None si llegan vacíos o como "Desconocido".
    # Límites máximos defensivos alineados con el esquema DB (VARCHAR(12) tras migr. 004).
    _MAX_LEN = {"dni": 12, "nie": 12, "pasaporte": 20, "nass": 12, "nuss": 12}

    def _clean(v: Optional[str], campo: str = "") -> Optional[str]:
        if not v or str(v).strip().lower() in ("desconocido", "null", "none", ""):
            return None
        valor = str(v).strip().upper()
        max_len = _MAX_LEN.get(campo, 255)
        return valor[:max_len]  # truncar como última línea de defensa

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT upsert_paciente(:nombre, :apellidos, :fecha_nacimiento, "
                 ":genero, :dni, :nie, :pasaporte, :nass, :nuss)"),
            {
                "nombre":           nombre,
                "apellidos":        apellidos,
                "fecha_nacimiento": fecha,
                "genero":           genero or "unknown",
                "dni":              _clean(dni, "dni"),
                "nie":              _clean(nie, "nie"),
                "pasaporte":        _clean(pasaporte, "pasaporte"),
                "nass":             _clean(nass, "nass"),
                "nuss":             _clean(nuss, "nuss"),
            },
        )
        paciente_id = str(result.scalar())

    logger.info(f"Paciente resuelto: {paciente_id}")
    return paciente_id


# ─── Inserción de informe ─────────────────────────────────────────────────────

def insertar_informe(
    paciente_id: str,
    nombre_archivo: str,
    confidence_level: str,
    fhir_bundle: dict,
) -> str:
    """
    Inserta un nuevo informe vinculado al paciente y devuelve su UUID.
    """
    informe_id = str(uuid.uuid4())
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO informes (id, paciente_id, nombre_archivo, confidence_level, fhir_bundle)
                VALUES (:id, :paciente_id, :nombre_archivo, :confidence_level, CAST(:fhir_bundle AS jsonb))
            """),
            {
                "id":               informe_id,
                "paciente_id":      paciente_id,
                "nombre_archivo":   nombre_archivo,
                "confidence_level": confidence_level,
                "fhir_bundle":      json.dumps(fhir_bundle, ensure_ascii=False),
            },
        )
    logger.info(f"Informe insertado: {informe_id} → paciente {paciente_id}")
    return informe_id


# ─── Inserción de diagnósticos ────────────────────────────────────────────────

def insertar_diagnosticos(informe_id: str, diagnosticos: list[dict]):
    """
    Inserta la lista de diagnósticos vinculados al informe.

    Cada diagnóstico debe tener al menos:
        tipo (PRINCIPAL|SECUNDARIO|ANTECEDENTE), texto, orden
    Y opcionalmente:
        snomed_id, snomed_descripcion, snomed_validado,
        cie10_codigo, cie10_descripcion, cie10_confidence, cie10_razonamiento
    """
    if not diagnosticos:
        return

    engine = get_engine()
    with engine.begin() as conn:
        for diag in diagnosticos:
            conn.execute(
                text("""
                    INSERT INTO diagnosticos (
                        informe_id, tipo, orden, texto,
                        snomed_id, snomed_descripcion, snomed_validado,
                        cie10_codigo, cie10_descripcion, cie10_confidence, cie10_razonamiento
                    ) VALUES (
                        :informe_id, CAST(:tipo AS tipo_diagnostico), :orden, :texto,
                        :snomed_id, :snomed_descripcion, :snomed_validado,
                        :cie10_codigo, :cie10_descripcion, :cie10_confidence, :cie10_razonamiento
                    )
                """),
                {
                    "informe_id":         informe_id,
                    "tipo":               diag.get("tipo", "SECUNDARIO"),
                    "orden":              diag.get("orden", 0),
                    "texto":              diag.get("texto", ""),
                    "snomed_id":          diag.get("snomed_id"),
                    "snomed_descripcion": diag.get("snomed_descripcion"),
                    "snomed_validado":    diag.get("snomed_validado", False),
                    "cie10_codigo":       diag.get("cie10_codigo"),
                    "cie10_descripcion":  diag.get("cie10_descripcion"),
                    "cie10_confidence":   diag.get("cie10_confidence"),
                    "cie10_razonamiento": diag.get("cie10_razonamiento"),
                },
            )
    logger.info(f"Insertados {len(diagnosticos)} diagnósticos → informe {informe_id}")


# ─── Función compuesta: persiste todo de una vez ─────────────────────────────

def persistir_resultado_clinico(
    datos_paciente: dict,
    nombre_archivo: str,
    confidence_level: str,
    fhir_bundle: dict,
    diagnosticos: list[dict],
) -> dict:
    """
    Función de alto nivel que:
      1. Resuelve/crea el paciente (upsert por identificador)
      2. Inserta el informe vinculado
      3. Inserta todos los diagnósticos clasificados

    Returns:
        {"paciente_id": "...", "informe_id": "..."}
    """
    ids = datos_paciente.get("identificadores", {})

    paciente_id = upsert_paciente(
        nombre=datos_paciente.get("nombre"),
        apellidos=datos_paciente.get("apellidos"),
        fecha_nacimiento=datos_paciente.get("fecha_nacimiento"),
        genero=datos_paciente.get("genero", "unknown"),
        dni=ids.get("dni"),
        nie=ids.get("nie"),
        pasaporte=ids.get("pasaporte"),
        nass=ids.get("nass"),
        nuss=ids.get("nuss"),
    )

    informe_id = insertar_informe(
        paciente_id=paciente_id,
        nombre_archivo=nombre_archivo,
        confidence_level=confidence_level,
        fhir_bundle=fhir_bundle,
    )

    insertar_diagnosticos(informe_id, diagnosticos)

    return {"paciente_id": paciente_id, "informe_id": informe_id}
