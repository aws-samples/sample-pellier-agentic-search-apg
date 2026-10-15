#!/usr/bin/env bash
# Restore one lab's execution and AgentCore state. Run by `lab_run.py reset --lab N`.
#
#   bash scripts/reset-agentcore-lab.sh 1|2   execution rail back to in-process
#   bash scripts/reset-agentcore-lab.sh 3     managed project redeployed from the starters
#   bash scripts/reset-agentcore-lab.sh 4     Lab 4 Cedar rule and live enforcement mode
#
# The functions are the ones scripts/reset-governed-workshop.sh runs for the whole
# workshop (scripts/lib/agentcore-reset.sh). It does not stop the application: the lab's
# files and database pieces are restored by lab_run.py, which also restarts the backend.
# Exits non-zero on the first failure, naming the step.
set -euo pipefail

LAB="${1:-}"
case "$LAB" in 1 | 2 | 3 | 4) ;; *) echo "usage: reset-agentcore-lab.sh 1|2|3|4" >&2; exit 2 ;; esac

export PATH="/opt/pellier/bin:$PATH"
REPO="${PELLIER_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${REPO}/.env"
[[ -f "$ENV_FILE" ]] || ENV_FILE="${REPO}/pellier/backend/.env"
RUN_ENV_FILE="${PELLIER_RUN_ENV:-/etc/pellier/run.env}"
PYTHON="${REPO}/pellier/backend/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1" >&2; }
warn() { printf '  [WARN] %s\n' "$1"; }

# shellcheck source=lib/dotenv.sh
. "$REPO/scripts/lib/dotenv.sh"
# shellcheck source=lib/agentcore-reset.sh
. "$REPO/scripts/lib/agentcore-reset.sh"
[[ -f "$ENV_FILE" ]] && pellier_load_dotenv "$ENV_FILE"
cd "$REPO"

case "$LAB" in
  1 | 2) pellier_restore_execution_rail ;;
  3) pellier_agentcore_init && pellier_restore_lab3_agentcore ;;
  4) pellier_agentcore_init && pellier_restore_lab4_agentcore ;;
esac || {
  fail "Lab ${LAB} AgentCore state was not restored (step: ${PELLIER_RESET_FAILED_STEP:-unknown}). Run the whole-workshop reset instead."
  exit 1
}
