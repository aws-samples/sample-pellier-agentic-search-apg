#!/usr/bin/env bash
# Rebuild the Vite SPA, then restart the pellier systemd unit so the
# fresh dist/ is served. Only needed after editing pellier/frontend/src/
# (the lab itself is backend Python — most participants never run this).
set -euo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
export PATH="${HOME}/.local/bin:${PATH}"

cd "${REPO}/pellier/frontend"
VITE_BASE_PATH=/ports/8000/ npm run build

# systemd owns the backend. A restart re-runs ExecStartPre (which also
# builds), but we build here too so a failed build surfaces directly to
# the participant instead of being swallowed by the best-effort ExecStartPre.
sudo systemctl restart pellier
echo "rebuild-frontend: SPA rebuilt, pellier restarted (journalctl -fu pellier)"
