#!/usr/bin/env bash
# Health-check con deduplicación: avisa al pasar de OK a FALLO, repite como mucho cada
# AGSGPT_ALERT_REPEAT_SECONDS (3600 por defecto) y avisa una vez al recuperarse.
# El correo sale de AGSGPT_ALERT_EMAIL (entorno o .env); sin correo o sin contraseña SMTP no envía nada.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_env_get() { [ -f "$REPO_DIR/.env" ] && sed -n "s/^$1=//p" "$REPO_DIR/.env" | tail -n 1 || true; }

URL="${AGSGPT_HEALTH_URL:-http://127.0.0.1:${AGSGPT_PORT:-8000}/health}"
TIMEOUT="${AGSGPT_HEALTH_TIMEOUT:-5}"
MAIL="${AGSGPT_ALERT_EMAIL:-$(_env_get AGSGPT_ALERT_EMAIL)}"
SMTP_PASS_FILE="${AGSGPT_SMTP_PASS_FILE:-$REPO_DIR/monitoring/secrets/smtp_password}"
SMTP_HOST="${AGSGPT_SMTP_HOST:-smtp.gmail.com}"
SMTP_PORT="${AGSGPT_SMTP_PORT:-587}"
REPEAT="${AGSGPT_ALERT_REPEAT_SECONDS:-3600}"
STATE_DIR="${AGSGPT_STATE_DIR:-$REPO_DIR/.state}"
STATE_FILE="$STATE_DIR/health_state"
HC_URL="${HEALTHCHECKS_URL:-}"
DRY_RUN="${AGSGPT_ALERT_DRY_RUN:-0}"

mkdir -p "$STATE_DIR"
NOW=$(date +%s)
PREV_STATUS="ok"; LAST_ALERT=0
if [ -f "$STATE_FILE" ]; then
  read -r PREV_STATUS LAST_ALERT < "$STATE_FILE" || true
  case "$LAST_ALERT" in ''|*[!0-9]*) LAST_ALERT=0 ;; esac
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$URL" || true)
[ -n "$HTTP_CODE" ] || HTTP_CODE="000"

notify() {  # $1 = asunto, $2 = cuerpo
  if [ "$DRY_RUN" = "1" ]; then echo "AVISO: $1"; return 0; fi
  [ -n "$MAIL" ] && [ -s "$SMTP_PASS_FILE" ] || return 0
  SUBJ="$1" BODY="$2" MAIL="$MAIL" PASS_FILE="$SMTP_PASS_FILE" SMTP_HOST="$SMTP_HOST" SMTP_PORT="$SMTP_PORT" \
  python3 - <<'PY' 2>/dev/null || true
import os, smtplib
from email.mime.text import MIMEText
msg = MIMEText(os.environ["BODY"])
msg["Subject"] = os.environ["SUBJ"]
msg["From"] = msg["To"] = os.environ["MAIL"]
with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), timeout=20) as s:
    s.starttls()
    s.login(os.environ["MAIL"], open(os.environ["PASS_FILE"]).read().strip())
    s.send_message(msg)
PY
}

if [ "$HTTP_CODE" = "200" ]; then
  [ -n "$HC_URL" ] && { curl -fsS -m 10 -o /dev/null "$HC_URL" 2>/dev/null || true; }
  if [ "$PREV_STATUS" = "fail" ]; then
    notify "[RESOLVED] agsgpt vuelve a responder" "$(printf 'Health check OK de nuevo.\nHost: %s\nFecha: %s' "$(hostname)" "$(date '+%F %T')")"
  fi
  echo "ok 0" > "$STATE_FILE"
  exit 0
fi

[ -n "$HC_URL" ] && { curl -fsS -m 10 -o /dev/null "$HC_URL/fail" 2>/dev/null || true; }
if [ "$PREV_STATUS" != "fail" ] || [ $((NOW - LAST_ALERT)) -ge "$REPEAT" ]; then
  notify "[CRITICAL] agsgpt DOWN — HTTP $HTTP_CODE" "$(printf 'Health check falló.\nHTTP: %s\nHost: %s\nFecha: %s' "$HTTP_CODE" "$(hostname)" "$(date '+%F %T')")"
  LAST_ALERT=$NOW
else
  echo "Fallo ya avisado; siguiente aviso en $((REPEAT - (NOW - LAST_ALERT))) s"
fi
echo "fail $LAST_ALERT" > "$STATE_FILE"
exit 1
