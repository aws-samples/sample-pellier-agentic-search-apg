#!/usr/bin/env bash
# =============================================================================
# health-gate.sh — one-shot post-boot readiness check for the workshop
# =============================================================================
# Prints one PASS/FAIL line per check and a single overall verdict. Safe to
# re-run any time (read-only). Intended to run at the end of bootstrap and to
# be available to facilitators as the `health` alias.
#
# Checks:
#   1. Backend /api/health is green (DB connected)
#   2. Frontend SPA is served
#   3. Catalog row count == expected (40)
#   4. Warehouse inventory present (~120 rows)
#   5. Required schema migrations are present
#   6. Required Bedrock model preflight passed
#   7. Event-rehearsed Claude Code CLI is installed
#   8. uv is installed for the participant Python client
#   9. Required AgentCore Memory exists and reports ACTIVE
#
# Exit 0 only if the core one-hour path passes: backend, frontend, catalog,
# warehouse, schema, tools, model access, and AgentCore Memory.
# =============================================================================
set -uo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
EXPECTED_CATALOG="${EXPECTED_CATALOG:-40}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/health}"
MEMORY_STATUS_URL="${MEMORY_STATUS_URL:-http://localhost:8000/api/agentcore/memory/status}"

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

# 2. Frontend SPA actually built + served. The backend serves /api even when
# the Vite bundle is absent (it returns a JSON "bundle not found" note at /),
# so /api/health alone can read green while the storefront and Pellier Labs are blank.
# Check that / returns HTML, not that JSON note: this is what a participant
# sees in the browser. (Root cause when it fails: the frontend build failed,
# usually `npm run build` in pellier/frontend; recover with `rebuild-frontend`.)
root_body="$(curl -fs --max-time 5 "${ROOT_URL:-http://localhost:8000/}" 2>/dev/null || true)"
if echo "$root_body" | grep -qiE '<!doctype html|<div id="root"'; then
  pass "Frontend SPA built and served at / (storefront and Pellier Labs render)"
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

# 3. Catalog count
catalog_n="$(_psql 'SELECT count(*) FROM pellier.product_catalog;' || echo '')"
if [[ "$catalog_n" == "$EXPECTED_CATALOG" ]]; then
  pass "Catalog seeded ($catalog_n products)"
else
  fail "Catalog count is '${catalog_n:-unknown}', expected $EXPECTED_CATALOG"
  ok=false
fi

# 4. Warehouse inventory
wh_n="$(_psql 'SELECT count(*) FROM pellier.warehouse_inventory;' || echo '')"
if [[ "${wh_n:-0}" =~ ^[0-9]+$ ]] && (( wh_n > 0 )); then
  pass "Warehouse inventory present ($wh_n rows)"
else
  fail "Warehouse inventory empty or missing (got: ${wh_n:-none})"
  ok=false
fi

# 5. A healthy connection and seeded products do not prove migrations completed.
# These relations and functions are required by retrieval receipts, tool audit,
# and inventory writes, including migrations applied after the catalog seed.
schema_ready="$(_psql "
SELECT
  to_regclass('pellier.tool_audit') IS NOT NULL
  AND to_regclass('pellier.tools') IS NOT NULL
  AND to_regclass('pellier.governed_receipts') IS NOT NULL
  AND to_regclass('pellier.write_operations') IS NOT NULL
  AND to_regclass('pellier.retrieval_receipts') IS NOT NULL
  AND to_regclass('pellier.inventory_ledger') IS NOT NULL
  AND to_regprocedure('pellier.process_return_idempotent(text,text,text,text,text)') IS NOT NULL
  AND to_regprocedure('pellier.reconcile_inventory()') IS NOT NULL;
" || echo '')"
if [[ "$schema_ready" == "t" ]]; then
  pass "Required schema migrations are present"
else
  fail "Required schema migrations are incomplete; see /var/log/database-setup.log"
  ok=false
fi

# 6. Required Bedrock model access
if [[ "${BEDROCK_MODEL_ACCESS_READY:-}" == "true" ]]; then
  pass "Required Bedrock model-access preflight passed"
else
  fail "Required Bedrock model-access preflight did not pass"
  ok=false
fi

# 7. Claude Code CLI used by the recommended Lab 2 path
claude_version="$(claude --version 2>/dev/null || true)"
if [[ -n "$claude_version" ]]; then
  pass "Claude Code CLI installed (${claude_version})"
else
  fail "Claude Code CLI is missing or unusable"
  ok=false
fi

# 8. uv runs the checked-in participant Python client
uv_version="$(uv --version 2>/dev/null || true)"
if [[ -n "$uv_version" ]]; then
  pass "uv installed (${uv_version})"
else
  fail "uv is missing or unusable"
  ok=false
fi

# 9. Required AgentCore Memory is configured and ACTIVE
memory_json="$(curl -fs --max-time 10 "$MEMORY_STATUS_URL" 2>/dev/null || true)"
memory_ready="$(
  printf '%s' "$memory_json" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    print("false")
else:
    ready = (
        payload.get("live") is True
        and payload.get("source") == "agentcore-sdk"
        and payload.get("resource_status") == "ACTIVE"
        and bool(payload.get("memory_id"))
    )
    print("true" if ready else "false")
' 2>/dev/null || echo false
)"
if [[ "$memory_ready" == "true" ]]; then
  pass "AgentCore Memory is configured and ACTIVE"
else
  fail "AgentCore Memory is not ACTIVE (got: ${memory_json:-no response})"
  ok=false
fi

echo "------------------------------------------------------------"
if $ok; then
  printf "${GREEN}● READY${NC} — all required checks passed.\n"
  exit 0
else
  printf "${RED}● NOT READY${NC} — see failed checks above.\n"
  exit 1
fi
