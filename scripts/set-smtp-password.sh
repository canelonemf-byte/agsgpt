#!/usr/bin/env bash
# Guarda la app password de Gmail sin mostrarla ni dejarla en el historial de la shell.
set -euo pipefail
mkdir -p monitoring/secrets
read -rs -p "App password de Gmail (no se muestra): " PASS
echo
printf '%s' "$PASS" > monitoring/secrets/smtp_password
chmod 600 monitoring/secrets/smtp_password
unset PASS
echo "Guardada en monitoring/secrets/smtp_password"
