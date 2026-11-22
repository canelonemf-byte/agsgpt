#!/usr/bin/env bash
set -euo pipefail

# En Docker el directorio es un tmpfs montado: no se puede borrar, solo vaciar.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus_metrics}"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -delete

exec gunicorn app.main:app -c gunicorn_conf.py
