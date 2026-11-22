#!/usr/bin/env bash
set -euo pipefail

URL="http://127.0.0.1:8000/health"
TIMEOUT=5
MAIL="canelone.mf@gmail.com"
SMTP_PASS_FILE="/workspace/agsgpt/monitoring/secrets/smtp_password"
HC_URL="${HEALTHCHECKS_URL:-}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$URL" || echo "000")

if [ "$HTTP_CODE" -eq 200 ]; then
  if [ -n "$HC_URL" ]; then
    curl -fsS -m 10 -o /dev/null "$HC_URL" 2>/dev/null || true
  fi
  exit 0
fi

if [ -n "$HC_URL" ]; then
  curl -fsS -m 10 -o /dev/null "$HC_URL/fail" 2>/dev/null || true
fi

if [ -f "$SMTP_PASS_FILE" ]; then
  python3 -c "
import smtplib, sys
from email.mime.text import MIMEText

msg = MIMEText('Health check falló.\nHTTP: $HTTP_CODE\nHost: $(hostname)\nFecha: $(date '+%F %T')')
msg['Subject'] = f'[CRITICAL] agsgpt DOWN — HTTP $HTTP_CODE'
msg['From'] = '$MAIL'
msg['To'] = '$MAIL'

with smtplib.SMTP('smtp.gmail.com', 587) as s:
    s.starttls()
    s.login('$MAIL', open('$SMTP_PASS_FILE').read().strip())
    s.send_message(msg)
" 2>/dev/null || true
fi

exit 1
