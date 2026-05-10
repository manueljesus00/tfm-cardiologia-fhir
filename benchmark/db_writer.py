"""
benchmark/db_writer.py — Persiste resultados multi-modelo en PostgreSQL.

Usa la conexión existente del proyecto (database/connection.py).
Requiere haber ejecutado antes: database/migrations/003_benchmark_multimodel.sql
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmark.runner import MultiModelMetrics

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_multimodel (
    id              SERIAL PRIMARY KEY,
    run_id          UUID DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    archivo         TEXT NOT NULL,
    modelo          TEXT NOT NULL,
    provider        TEXT NOT NULL,
    -- Fase 1
    tiempo_fase1_s       FLOAT,
    tokens_fase1_prompt  INT,
    tokens_fase1_completion INT,
    tokens_fase1_total   INT,
    -- Fase 2
    tiempo_fase2_s       FLOAT,
    tokens_fase2_prompt  INT,
    tokens_fase2_completion INT,
    tokens_fase2_total   INT,
    -- Totales
    tiempo_total_s  FLOAT,
    tokens_totales  INT,
    coste_usd       FLOAT,
    coste_eur       FLOAT,
    -- Resultado
    confidence_level TEXT,
    snomed_id        TEXT,
    cie10_codes      TEXT,
    exito            BOOLEAN,
    error            TEXT
);
"""

INSERT_SQL = """
INSERT INTO benchmark_multimodel (
    archivo, modelo, provider,
    tiempo_fase1_s, tokens_fase1_prompt, tokens_fase1_completion, tokens_fase1_total,
    tiempo_fase2_s, tokens_fase2_prompt, tokens_fase2_completion, tokens_fase2_total,
    tiempo_total_s, tokens_totales, coste_usd, coste_eur,
    confidence_level, snomed_id, cie10_codes, exito, error
) VALUES (
    %(archivo)s, %(modelo)s, %(provider)s,
    %(tiempo_fase1_s)s, %(tokens_fase1_prompt)s, %(tokens_fase1_completion)s, %(tokens_fase1_total)s,
    %(tiempo_fase2_s)s, %(tokens_fase2_prompt)s, %(tokens_fase2_completion)s, %(tokens_fase2_total)s,
    %(tiempo_total_s)s, %(tokens_totales)s, %(coste_usd)s, %(coste_eur)s,
    %(confidence_level)s, %(snomed_id)s, %(cie10_codes)s, %(exito)s, %(error)s
);
"""


def _get_connection():
    """Reutiliza la configuración de conexión del proyecto."""
    import os
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "snomed_irbd"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "snomed_password"),
    )


def ensure_table_exists():
    """Crea la tabla si no existe (idempotente)."""
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE_SQL)
        conn.close()
        logger.info("Tabla benchmark_multimodel lista.")
    except Exception as e:
        logger.warning(f"No se pudo crear/verificar la tabla benchmark_multimodel: {e}")


def guardar_metricas(metrics_list: list["MultiModelMetrics"]) -> int:
    """
    Inserta una lista de MultiModelMetrics en PostgreSQL.

    Returns:
        Número de filas insertadas.
    """
    if not metrics_list:
        return 0

    inserted = 0
    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                for m in metrics_list:
                    cur.execute(INSERT_SQL, m.to_dict())
                    inserted += 1
        conn.close()
        logger.info(f"[DB] {inserted} métricas guardadas en benchmark_multimodel.")
    except Exception as e:
        logger.error(f"[DB] Error al guardar métricas: {e}")

    return inserted


def leer_resultados(limit: int = 200) -> list[dict]:
    """
    Lee los últimos resultados del benchmark para el dashboard del portal.

    Returns:
        Lista de dicts con las métricas (ordenados por timestamp DESC).
    """
    try:
        conn = _get_connection()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    modelo, provider, archivo, timestamp,
                    tiempo_fase1_s, tiempo_fase2_s, tiempo_total_s,
                    tokens_fase1_total, tokens_fase2_total, tokens_totales,
                    coste_usd, coste_eur,
                    confidence_level, snomed_id, cie10_codes, exito, error
                FROM benchmark_multimodel
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,),
            )
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"[DB] Error al leer benchmark_multimodel: {e}")
        return []
