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
#   4. AGENTCORE_MEMORY_ID set in .env            (required — Memory pillar)
#   5. AGENTCORE_RUNTIME_ENDPOINT set in .env     (required — Runtime pillar)
#   6. AGENTCORE_POLICY_ENGINE_ID set in .env     (warn — Policy pillar; the
#      Act II managed-Cedar exercise won't enforce at the Gateway without it)
#
# Exit 0 only if all REQUIRED checks pass.
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

# 4. AgentCore Memory id (required)
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
