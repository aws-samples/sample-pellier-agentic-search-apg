#!/usr/bin/env bash
# The welcome the workshop terminal prints when it opens. ~/.bashrc runs it in that terminal
# only (PELLIER_WORKSHOP_TERMINAL, set by the folderOpen task), after starting every Code
# Editor terminal at the repository root.
set -uo pipefail

REPO_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_PATH" || exit 0
cat <<'WELCOME'
Pellier: Retrieve → Ground → Deploy → Govern

Keep the Workshop Studio guide open beside this editor.
01 Retrieve: Anna       02 Ground: Marco
03 Deploy: Theo         04 Govern: Jessica and Nadia

Each numbered Explorer group has the files you edit, a README and solutions.
This terminal starts at the repository root. Follow the guide's checks.
WELCOME

# A deploy started in another window's terminal keeps running there; say so here.
"$(command -v python3.14 || command -v python3)" scripts/deploy_lock.py --notice 2>/dev/null || true
