#!/bin/bash
# =============================================================================
# Start Frontend for Pellier — single-process model
# =============================================================================
# In the current architecture, FastAPI on port 8000 serves BOTH the
# built SPA and /api. There's no longer a separate Vite/http-server
# process on port 5173. This script just builds the frontend once; the
# backend (which serves the bundle) is started separately.
#
# If you're coming here expecting to start something on port 5173,
# that's the old two-process model — start the backend instead
# (START_BACKEND.sh for local dev, or `systemctl start pellier` on a
# provisioned instance).
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/frontend"

# Keep the release runtime when it is already active. Loading NVM normally
# selects its default, which may silently replace Node 24 with an older major.
node_version="$(node --version 2>/dev/null || true)"
if [[ "$node_version" != v24.* ]]; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        # Select only an installed Node 24; this entrypoint never installs it.
        if ! . "$NVM_DIR/nvm.sh" --no-use || ! nvm use 24 >/dev/null 2>&1; then
            echo "Node.js 24 is required. NVM could not activate an installed Node 24. Select Node 24 and rerun this script." >&2
            exit 1
        fi
    fi
    node_version="$(node --version 2>/dev/null || true)"
fi
if [[ "$node_version" != v24.* ]]; then
    printf 'Node.js 24 is required; found %s. Select Node 24 and rerun this script.\n' "${node_version:-no usable Node executable}" >&2
    exit 1
fi

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
echo "  ./pellier/START_BACKEND.sh           # interactive local dev (uvicorn --reload)"
echo "  or"
echo "  sudo systemctl start pellier         # provisioned instance (Workshop Studio)"
echo ""
if [ -n "${CLOUDFRONT_URL:-}" ]; then
    echo "🌐 App URL: ${CLOUDFRONT_URL}/ports/8000/"
else
    echo "🌐 App URL: http://localhost:8000/"
fi
