#!/usr/bin/env bash
set -euo pipefail

REPO_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_PATH"
cat <<'WELCOME'
Pellier: Retrieve → Ground → Deploy → Govern

Start with START_HERE.md and keep the Workshop Studio guide open.
01 Retrieve: Anna       02 Ground: Marco
03 Deploy: Theo         04 Govern: Jessica and Nadia

Each numbered Explorer group has the files you edit, a README and solutions.
This terminal starts at the repository root. Follow the guide's checks.
WELCOME

# Each new Code Editor window opens a new terminal; say so when a deploy runs in an older one.
"$(command -v python3.14 || command -v python3)" scripts/deploy_lock.py --notice 2>/dev/null || true

# Retry on the next terminal if the editor CLI was not ready on first open.
if [ ! -f .local/code-editor-started ]; then
    if code --reuse-window "$REPO_PATH/START_HERE.md" >/dev/null 2>&1; then
        mkdir -p .local
        touch .local/code-editor-started
    fi
fi
exec bash -l
