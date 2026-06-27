#!/bin/bash
set -e

echo "Restaurando dump de SNOMED-CT IRBD..."

# Esperar a que PostgreSQL esté listo
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
  echo "Esperando a PostgreSQL..."
  sleep 2
done

# Restaurar el dump usando pg_restore
pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v /docker-entrypoint-initdb.d/IRBD_Multibase_PostgreSQL_snapshot_20251201.sql

echo "Dump restaurado exitosamente"
