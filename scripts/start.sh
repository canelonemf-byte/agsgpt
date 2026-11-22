#!/usr/bin/env bash
set -euo pipefail

rm -rf /tmp/prometheus_metrics
mkdir -p /tmp/prometheus_metrics
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_metrics

exec gunicorn app.main:app -c gunicorn_conf.py
