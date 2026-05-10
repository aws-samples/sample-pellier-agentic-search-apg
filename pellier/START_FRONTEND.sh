#!/bin/bash
# =============================================================================
# Start Frontend for Pellier — single-process model
# =============================================================================
# In the current architecture, FastAPI on port 8000 serves BOTH the
# built SPA and /api. There's no longer a separate Vite/http-server
# process on port 5173. This script is kept as a convenience wrapper
# that builds the frontend once and then points the user at
# workshop-autostart.sh (which runs the single uvicorn process).
#
# If you're coming here expecting to start something on port 5173,
# that's the old two-process model — see workshop-autostart.sh or
# systemctl start pellier instead.
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/frontend"

# Load nvm (harmless if not installed)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# VITE_BASE_PATH bakes the asset URL prefix into the built bundle so
# Workshop Studio's /ports/8000/* reverse-proxy prefix matches. Use
# "/" for a pure-local prod test; leave as default for workshop runs.
export VITE_BASE_PATH="${VITE_BASE_PATH:-/ports/8000/}"

echo "🛠️  Building frontend for production (VITE_BASE_PATH=${VITE_BASE_PATH})..."
npm run build

echo ""
echo "✅ Build complete."
echo ""
echo "The built bundle lives in pellier/frontend/dist/ and is"
echo "served by FastAPI on port 8000 alongside /api. To actually run"
echo "the app, start the backend:"
echo ""
echo "  ./pellier/START_BACKEND.sh           # interactive dev"
echo "  or"
echo "  scripts/workshop-autostart.sh              # workshop-style"
echo "  or"
echo "  systemctl start pellier              # Workshop Studio"
echo ""
if [ -n "${CLOUDFRONT_URL:-}" ]; then
    echo "🌐 App URL: ${CLOUDFRONT_URL}/ports/8000/"
else
    echo "🌐 App URL: http://localhost:8000/"
fi
