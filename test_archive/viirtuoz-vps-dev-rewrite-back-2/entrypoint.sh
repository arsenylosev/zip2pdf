#!/bin/bash
set -euo pipefail

if [ -d "/docker-entrypoint.d" ]; then
  for f in /docker-entrypoint.d/*.sh; do
    [ -f "$f" ] && . "$f"
  done
fi

if [[ -f "/etc/juniper-secret/id_rsa" ]]; then
  mkdir -p /root/.ssh
  cp /etc/juniper-secret/id_rsa /root/.ssh/id_rsa
  cp /etc/juniper-secret/id_rsa.pub /root/.ssh/id_rsa.pub
  chmod 700 /root/.ssh
  chmod 600 /root/.ssh/id_rsa
  chmod 644 /root/.ssh/id_rsa.pub
fi

uv run uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --log-level "${LOG_LEVEL:-info}" \
  --proxy-headers \
  --forwarded-allow-ips="*" &
APP_PID=$!

nginx -g "daemon off;" &
NGINX_PID=$!

cleanup() {
  kill -TERM "$APP_PID" "$NGINX_PID" 2>/dev/null || true
}
trap cleanup INT TERM

wait -n "$APP_PID" "$NGINX_PID"
EXIT_CODE=$?

cleanup
wait "$APP_PID" "$NGINX_PID" 2>/dev/null || true
exit "$EXIT_CODE"