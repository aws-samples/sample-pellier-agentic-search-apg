#!/usr/bin/env bash
# =============================================================================
# health-gate.sh — one-shot post-boot readiness check for the Builder's Session
# =============================================================================
# Prints one PASS/FAIL line per check and a single overall verdict. Safe to
# re-run any time (read-only). Intended to run at the end of bootstrap and to
# be available to facilitators as the `health` alias.
#
# Checks:
#   1. Backend /api/health is green (DB connected)
#   2. Catalog row count == expected (40)
#   3. Warehouse inventory present (~120 rows)
#   4. node --version >= 20                       (warn — ROOT CAUSE diagnostic:
#      the @aws/agentcore CLI needs Node 20; on Node 18 every agentcore command
#      silently no-ops, so Runtime/Gateway/Policy never deploy and checks 6-7
#      below read empty. Surfacing the Node version turns "endpoints empty, why?"
#      into a named cause.)
#   5. AGENTCORE_MEMORY_ID set in .env            (required — Memory pillar)
#   6. AGENTCORE_RUNTIME_ENDPOINT set in .env     (required — Runtime pillar)
#   7. AGENTCORE_POLICY_ENGINE_ID set in .env     (warn — Policy pillar; the
#      Act II managed-Cedar exercise won't enforce at the Gateway without it)
#
# Exit 0 only if all REQUIRED checks pass. The Node check is a WARN (not a
# fail): the Boutique + the mandatory in-process path run fine on Node 18; only
# the optional managed beats need 20. It's a diagnostic, not a blocker.
# =============================================================================
set -uo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
EXPECTED_CATALOG="${EXPECTED_CATALOG:-40}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/health}"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}✓ PASS${NC}  %s\n" "$1"; }
fail() { printf "  ${RED}✗ FAIL${NC}  %s\n" "$1"; }
warn() { printf "  ${YEL}• WARN${NC}  %s\n" "$1"; }

ok=true

# Load env (safe: set -a + source, no word-splitting)
if [[ -f "$ENV_FILE" ]]; then
  set -a; # shellcheck source=/dev/null
  source "$ENV_FILE"; set +a
fi

echo "Pellier health gate — $(date '+%H:%M:%S')"
echo "------------------------------------------------------------"

# 1. Backend health
health_json="$(curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
if echo "$health_json" | grep -q '"status".*"healthy"'; then
  pass "Backend /api/health is healthy"
else
  fail "Backend /api/health not healthy (got: ${health_json:-no response})"
  ok=false
fi

# 1b. Frontend SPA actually built + served. The backend serves /api even when
# the Vite bundle is absent (it returns a JSON "bundle not found" note at /),
# so /api/health alone can read green while the Boutique + Atelier are blank.
# Check that / returns HTML, not that JSON note: this is what a participant
# sees in the browser. (Root cause when it fails: the frontend build failed,
# usually `npm run build` in pellier/frontend; recover with `rebuild-frontend`.)
root_body="$(curl -fs --max-time 5 "${ROOT_URL:-http://localhost:8000/}" 2>/dev/null || true)"
if echo "$root_body" | grep -qiE '<!doctype html|<div id="root"'; then
  pass "Frontend SPA built and served at / (Boutique + Atelier render)"
else
  fail "Frontend SPA not served at / - bundle missing (got: ${root_body:0:80}). Run 'rebuild-frontend' (builds pellier/frontend, restarts pellier)."
  ok=false
fi

# psql helper using env creds
_psql() {
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" \
    -tAc "$1" 2>/dev/null
}

# 2. Catalog count
catalog_n="$(_psql 'SELECT count(*) FROM pellier.product_catalog;' || echo '')"
if [[ "$catalog_n" == "$EXPECTED_CATALOG" ]]; then
  pass "Catalog seeded ($catalog_n products)"
else
  fail "Catalog count is '${catalog_n:-unknown}', expected $EXPECTED_CATALOG"
  ok=false
fi

# 3. Warehouse inventory
wh_n="$(_psql 'SELECT count(*) FROM pellier.warehouse_inventory;' || echo '')"
if [[ "${wh_n:-0}" =~ ^[0-9]+$ ]] && (( wh_n > 0 )); then
  pass "Warehouse inventory present ($wh_n rows)"
else
  fail "Warehouse inventory empty or missing (got: ${wh_n:-none})"
  ok=false
fi

# 4. Node version (warn — root-cause diagnostic for the managed pillars below).
# The @aws/agentcore CLI is Node-based and requires Node >= 20; on Node 18 it
# crashes at module load (regex `v`/unicodeSets flag) BEFORE doing any work, so
# `agentcore deploy` silently produces nothing and the Runtime/Gateway/Policy
# endpoints below stay empty. We surface the version here so an empty
# AGENTCORE_RUNTIME_ENDPOINT (check 6) reads as a consequence, not a mystery.
node_ver="$(node --version 2>/dev/null || true)"
node_major="$(echo "$node_ver" | sed 's/^v//' | cut -d. -f1)"
if [[ "$node_major" =~ ^[0-9]+$ ]] && (( node_major >= 20 )); then
  pass "Node $node_ver (>= 20 — @aws/agentcore CLI can run)"
else
  warn "Node ${node_ver:-not found} (< 20) — the @aws/agentcore CLI cannot run, so the managed Runtime/Gateway/Policy never deploy and checks below read empty. This is the ROOT CAUSE if those are FAIL. Recover: 'sudo dnf remove -y nodejs && curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - && sudo dnf install -y --allowerasing nodejs' then re-run scripts/deploy/deploy_all.sh."
fi

# 5. AgentCore Memory id (required)
if [[ -n "${AGENTCORE_MEMORY_ID:-}" ]]; then
  pass "AGENTCORE_MEMORY_ID set"
else
  fail "AGENTCORE_MEMORY_ID is empty — STM will fall back to Aurora session tables"
  ok=false
fi

# 5. AgentCore Runtime endpoint (required for Act II managed Runtime evidence)
if [[ -n "${AGENTCORE_RUNTIME_ENDPOINT:-}" ]]; then
  pass "AGENTCORE_RUNTIME_ENDPOINT set"
else
  fail "AGENTCORE_RUNTIME_ENDPOINT empty — Act II Runtime invoke cannot run"
  ok=false
fi

# 6. Managed AgentCore Policy engine (4th pillar). WARN, not fail: the backend
# and storefront run fine without it, but the Act II managed-Cedar exercise
# (process_return gated to reason=damaged at the Gateway) won't ENFORCE — so
# surface it loudly rather than report a false-green "READY".
if [[ -n "${AGENTCORE_POLICY_ENGINE_ID:-}" ]]; then
  pass "AGENTCORE_POLICY_ENGINE_ID set (managed Cedar policy attached)"
else
  warn "AGENTCORE_POLICY_ENGINE_ID empty — Gateway runs WITHOUT Cedar ENFORCE; the Act II policy ALLOW/DENY beat will not demonstrate. See /var/log/pellier-agentcore.log."
fi

echo "------------------------------------------------------------"
if $ok; then
  printf "${GREEN}● READY${NC} — all required checks passed.\n"
  exit 0
else
  printf "${RED}● NOT READY${NC} — see failed checks above.\n"
  exit 1
fi
