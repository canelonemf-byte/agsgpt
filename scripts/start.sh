#!/usr/bin/env bash
set -euo pipefail

# En Docker el directorio es un tmpfs montado: no se puede borrar, solo vaciar.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus_metrics}"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -delete

# El estado del circuit breaker se comparte entre workers; se reinicia en cada arranque.
rm -f "${AGSGPT_CIRCUIT_DB:-/tmp/agsgpt_circuit.sqlite3}"*

exec gunicorn app.main:app -c gunicorn_conf.py
