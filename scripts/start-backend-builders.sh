#!/usr/bin/env bash
# Foreground uvicorn with --reload for Builder's Session (stops prior nohup uvicorn first).
set -euo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
export PATH="${HOME}/.local/bin:${PATH}"

if [[ -f /tmp/pellier/uvicorn.pid ]]; then
  pid="$(tr -d '[:space:]' </tmp/pellier/uvicorn.pid || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" || true
    sleep 2
  fi
fi

cd "${REPO}/pellier/backend"
set -a
# shellcheck source=/dev/null
source "${REPO}/.env"
set +a

exec uvicorn app:app --host 0.0.0.0 --port 8000 --reload
