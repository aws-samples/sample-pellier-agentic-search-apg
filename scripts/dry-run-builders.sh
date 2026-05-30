#!/usr/bin/env bash
# =============================================================================
# dry-run-builders.sh — end-to-end simulation of the participant path
# =============================================================================
# Run this before a 100-person room to catch breakage the health gate can't:
# it actually exercises the FULL Act I → Act II flow against the live backend.
#
#   1. Preconditions  — health gate must be READY
#   2. Apply solution — wire floor_check (the participant's one build)
#   3. Marco Turn 4   — POST /api/chat/stream, assert Brooklyn / BK-01 in reply
#   4. Runtime invoke — POST /api/agent/chat (managed path, if configured)
#   5. Audit ledger   — assert a pellier.tool_audit row for floor_check exists
#
# Non-destructive to data, but it DOES modify agent_tools.py (applies the
# solution). It backs the file up and restores it on exit unless --keep is
# passed. Safe to re-run.
#
# Usage:
#   scripts/dry-run-builders.sh            # apply solution, test, restore stub
#   scripts/dry-run-builders.sh --keep     # leave the solution applied
# =============================================================================
set -uo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
BASE="${PELLIER_BASE_URL:-http://localhost:8000}"
TOOLS="${REPO}/pellier/backend/services/agent_tools.py"
SOLUTION="${REPO}/solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py"
KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
fail() { printf "  ${RED}✗${NC} %s\n" "$1"; FAILED=true; }
info() { printf "  ${YEL}…${NC} %s\n" "$1"; }
FAILED=false

# Load env (safe source)
[[ -f "$ENV_FILE" ]] && { set -a; source "$ENV_FILE"; set +a; }

_psql() {
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" -tAc "$1" 2>/dev/null
}

restore() {
  if ! $KEEP && [[ -f "${TOOLS}.dryrun.bak" ]]; then
    mv "${TOOLS}.dryrun.bak" "$TOOLS"
    info "Restored original agent_tools.py (stub). Backend will reload."
  fi
}
trap restore EXIT

echo "════════════════════════════════════════════════════════════"
echo " Pellier Builder's Session — end-to-end dry run"
echo " base=${BASE}  repo=${REPO}"
echo "════════════════════════════════════════════════════════════"

# --- 1. Preconditions -------------------------------------------------------
echo "[1/5] Preconditions (health gate)"
if bash "${REPO}/scripts/health-gate.sh" >/tmp/dryrun-health.log 2>&1; then
  pass "Health gate READY"
else
  fail "Health gate NOT READY — see /tmp/dryrun-health.log; aborting"
  cat /tmp/dryrun-health.log
  exit 1
fi

# --- 2. Apply the solution (simulate the participant's build) ---------------
echo "[2/5] Wire floor_check (apply reference solution)"
if [[ ! -f "$SOLUTION" ]]; then
  fail "Solution file missing: $SOLUTION"; exit 1
fi
cp "$TOOLS" "${TOOLS}.dryrun.bak"
cp "$SOLUTION" "$TOOLS"
pass "Applied agent_tools_floor_check_solution.py"
info "Waiting 4s for uvicorn --reload to pick up the change…"
sleep 4

# Confirm the strip flipped to shipped via build-state
bs="$(curl -fs --max-time 5 "${BASE}/api/atelier/build-state" 2>/dev/null || true)"
if echo "$bs" | grep -q '"floor_check"[[:space:]]*:[[:space:]]*"shipped"'; then
  pass "build-state reports floor_check = shipped"
else
  fail "build-state did not flip floor_check to shipped (got: ${bs:0:200})"
fi

# --- 3. Marco Turn 4 via the dispatcher path --------------------------------
echo "[3/5] Marco Turn 4 — POST /api/chat/stream"
SESSION="dryrun-$(date +%s)"
turn4='{"message":"Is the Hadley shirt at the Brooklyn warehouse?","session_id":"'"$SESSION"'","customer_id":"CUST-MARCO"}'
reply="$(curl -fsN --max-time 60 -X POST "${BASE}/api/chat/stream" \
  -H 'Content-Type: application/json' -d "$turn4" 2>/dev/null || true)"
if echo "$reply" | grep -qiE 'brooklyn|BK-01'; then
  pass "Reply names Brooklyn / BK-01 (floor_check reached live warehouse data)"
else
  fail "Reply did not mention Brooklyn/BK-01 — floor_check may not be wired"
  info "First 300 chars: ${reply:0:300}"
fi
if echo "$reply" | grep -qi 'floor_check is in stub state'; then
  fail "Stub envelope still present — solution did not take effect"
fi

# --- 4. Managed Runtime invoke (optional) -----------------------------------
echo "[4/5] AgentCore Runtime invoke — POST /api/agent/chat"
if [[ -n "${AGENTCORE_RUNTIME_ENDPOINT:-}" && "${USE_AGENTCORE_RUNTIME:-false}" == "true" ]]; then
  rt='{"message":"Is the Hadley shirt at the Brooklyn warehouse?","session_id":"'"$SESSION"'-rt"}'
  rtreply="$(curl -fsN --max-time 90 -X POST "${BASE}/api/agent/chat" \
    -H 'Content-Type: application/json' -d "$rt" 2>/dev/null || true)"
  if echo "$rtreply" | grep -qiE 'brooklyn|BK-01|event:|chunk'; then
    pass "Managed Runtime returned a traceable response"
  else
    fail "Runtime invoke returned nothing usable (first 200: ${rtreply:0:200})"
  fi
else
  info "Skipped — USE_AGENTCORE_RUNTIME not true / endpoint unset (in-process fallback is fine for builders)"
fi

# --- 5. Audit ledger --------------------------------------------------------
echo "[5/5] Audit ledger — pellier.tool_audit"
n="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE tool='floor_check' AND session_id LIKE 'dryrun-%';")"
if [[ "${n:-0}" =~ ^[0-9]+$ ]] && (( n > 0 )); then
  pass "tool_audit has $n floor_check row(s) for this dry run"
else
  fail "No tool_audit row for floor_check — audit writer or policy hook not firing"
fi

echo "════════════════════════════════════════════════════════════"
if $FAILED; then
  printf "${RED}● DRY RUN FAILED${NC} — fix the ✗ items before the room opens.\n"
  exit 1
else
  printf "${GREEN}● DRY RUN PASSED${NC} — the participant path works end to end.\n"
  exit 0
fi
