#!/usr/bin/env bash
# Rebuild the Vite SPA and restart uvicorn for Builder's Session (no systemd).
# Invoked by the rebuild-frontend alias when WORKSHOP_FORMAT=builders.
set -euo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
export PATH="${HOME}/.local/bin:${PATH}"

cd "${REPO}/pellier/frontend"
VITE_BASE_PATH=/ports/8000/ npm run build

if [[ -f /tmp/pellier/uvicorn.pid ]]; then
  pid="$(tr -d ' \n' </tmp/pellier/uvicorn.pid || true)"
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

nohup uvicorn app:app --host 0.0.0.0 --port 8000 --reload \
  >>/tmp/pellier/uvicorn.log 2>&1 &
echo $! >/tmp/pellier/uvicorn.pid
echo "rebuild-frontend: uvicorn PID $(</tmp/pellier/uvicorn.pid) (log: /tmp/pellier/uvicorn.log)"
