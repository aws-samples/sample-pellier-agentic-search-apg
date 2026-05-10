#!/bin/bash
# =============================================================================
# Workshop Auto-Start Service
# =============================================================================
# Builds the frontend once (vite production bundle) and starts a single
# uvicorn process that serves:
#
#   - the built SPA at /, /atelier, /storyboard, /discover, ...
#   - the FastAPI routes at /api/*
#   - self-hosted fonts + hashed JS/CSS at /assets/*, /fonts/*
#
# One port (8000), one process, zero Node runtime during the workshop.
# Kills the "npm run dev on Windows" class of failures (file-watcher
# limits, port 5173 conflicts, node_modules install behind corporate
# proxies, Vite proxy breaking SSE).
#
# Attendees reach the app at:
#
#   direct:         http://localhost:8000/
#   Workshop Studio: https://<cf-domain>/ports/8000/
#
# Idempotent — safe to re-run; kills stale uvicorn / Vite on 8000/5173
# before starting.
# =============================================================================

set -euo pipefail

WORKSHOP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${WORKSHOP_ROOT}/pellier/backend"
FRONTEND_DIR="${WORKSHOP_ROOT}/pellier/frontend"
LOG_DIR="/tmp/pellier"

mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Pellier — Starting workshop service...${NC}"

# -----------------------------------------------------------------------------
# Kill any existing processes on 8000 (current) and 5173 (legacy two-process)
# -----------------------------------------------------------------------------
for port in 8000 5173; do
  pid=$(lsof -ti:${port} 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "  Stopping existing process on port ${port} (PID: ${pid})"
    kill -9 $pid 2>/dev/null || true
    sleep 1
  fi
done

# -----------------------------------------------------------------------------
# Build the frontend (one-shot, production bundle)
# -----------------------------------------------------------------------------
# VITE_BASE_PATH controls the asset URL prefix baked into the built
# bundle. In Workshop Studio + CloudFront, code-server reverse-proxies
# /ports/8000/* to our FastAPI origin, so assets must resolve under
# that prefix. Default to "/ports/8000/" since that's the workshop
# path; override with VITE_BASE_PATH=/ for pure-local prod test.
echo -e "  ${GREEN}▸ Building frontend (production)${NC}"
cd "$FRONTEND_DIR"

export VITE_BASE_PATH="${VITE_BASE_PATH:-/ports/8000/}"
echo "    VITE_BASE_PATH=${VITE_BASE_PATH}"

if ! npm run build > "${LOG_DIR}/frontend-build.log" 2>&1; then
  echo -e "  ${RED}❌ Frontend build failed. Tail of log:${NC}"
  tail -30 "${LOG_DIR}/frontend-build.log" || true
  exit 1
fi

# -----------------------------------------------------------------------------
# Start uvicorn (serves API + SPA + assets + fonts on port 8000)
# -----------------------------------------------------------------------------
echo -e "  ${GREEN}▸ Starting uvicorn (port 8000, serves API + SPA)${NC}"

cd "$BACKEND_DIR"
python3 generate_mcp_config.py 2>/dev/null || true

# --reload is intentionally omitted. Production mode is deterministic
# — we want a single process that matches what runs in Workshop Studio.
# Developers who want auto-reload during iteration can run
# ``uvicorn app:app --reload`` directly instead of this script.
nohup uvicorn app:app \
  --host 0.0.0.0 \
  --port 8000 \
  > "${LOG_DIR}/uvicorn.log" 2>&1 &

UVICORN_PID=$!
echo "    PID: ${UVICORN_PID} | Log: ${LOG_DIR}/uvicorn.log"

# -----------------------------------------------------------------------------
# Wait for /api/health to return 200
# -----------------------------------------------------------------------------
echo ""
echo -n "  Waiting for /api/health..."
for i in $(seq 1 40); do
  if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e " ${GREEN}ready${NC}"
    break
  fi
  echo -n "."
  sleep 1
done

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}✅ Pellier is running${NC}"
echo ""

if [ -n "${CLOUDFRONT_URL:-}" ]; then
  echo "  🌐 App:     ${CLOUDFRONT_URL}/ports/8000/"
  echo "  🔧 API:     ${CLOUDFRONT_URL}/ports/8000/api/"
else
  echo "  🌐 App:     http://localhost:8000/"
  echo "  🔧 API:     http://localhost:8000/api/"
fi

echo ""
echo "  📝 Backend edits: re-run this script, or run uvicorn with --reload"
echo "  📝 Frontend edits: re-run this script (rebuilds + restarts)"
echo "  🔄 Reset client state: append ?reset=1 to the app URL"
echo ""
echo "  📋 Logs:    ${LOG_DIR}/"
echo ""
