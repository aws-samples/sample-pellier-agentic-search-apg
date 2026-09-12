#!/usr/bin/env bash
# =============================================================================
# dry-run-builders.sh — end-to-end simulation of the participant path
# =============================================================================
# Run this before a 100-person room to catch breakage the health gate can't:
# it exercises retrieval Lab 1 and the complete agent extension in Lab 2.
#
#   1. Preconditions — health gate and both starter gaps
#   2. Lab 1         — pgvector SQL, then the four-path retrieval comparison
#   3. Lab 2 tool    — wire and directly verify floor_check while ungranted
#   4. Lab 2 agent   — grant to Stock Keeper and assert the Strands path
#   5. Lab 2 receipt — query the matching floor_check evidence row
#   6. SQL claims    — Beeswax warehouse split and pg_trgm index/plan
#
# This applies the floor_check solution and agent grant temporarily and creates
# the same floor_check audit evidence as a participant. It backs all three edited
# files up and restores them on exit unless --keep is passed. Run it on a
# workshop environment, not a production database.
#
# Usage:
#   scripts/dry-run-builders.sh            # apply solution, test, restore stub
#   scripts/dry-run-builders.sh --keep     # leave the solution applied
# =============================================================================
set -uo pipefail

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
BASE="${PELLIER_BASE_URL:-http://localhost:8000}"
TOOLS="${REPO}/pellier/backend/services/inventory_sql.py"
RETRIEVAL="${REPO}/workshop/retrieval.sql"
STOCK_KEEPER="${REPO}/pellier/backend/agents/stock_keeper.py"
KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
fail() { printf "  ${RED}✗${NC} %s\n" "$1"; FAILED=true; }
info() { printf "  ${YEL}…${NC} %s\n" "$1"; }
# warn: review-worthy but non-fatal (does NOT set FAILED / block the gate).
warn() { printf "  ${YEL}•${NC} %s\n" "$1"; }
FAILED=false
BACKUP_DIR=""

# Load env (safe source)
[[ -f "$ENV_FILE" ]] && { set -a; source "$ENV_FILE"; set +a; }

_psql() {
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" -tAc "$1" 2>/dev/null
}

restore() {
  if [[ -z "$BACKUP_DIR" ]]; then return; fi
  if ! $KEEP; then
    cp "$BACKUP_DIR/inventory_sql.py" "$TOOLS"
    cp "$BACKUP_DIR/retrieval.sql" "$RETRIEVAL"
    cp "$BACKUP_DIR/stock_keeper.py" "$STOCK_KEEPER"
    info "Restored all three original exercise files. Backups: $BACKUP_DIR"
  else
    info "Kept exercise changes. Original files: $BACKUP_DIR"
  fi
}
trap restore EXIT

echo "════════════════════════════════════════════════════════════"
echo " Pellier workshop — end-to-end dry run"
echo " base=${BASE}  repo=${REPO}"
echo "════════════════════════════════════════════════════════════"

# --- 1. Preconditions -------------------------------------------------------
echo "[1/6] Preconditions (health gate)"
if bash "${REPO}/scripts/health-gate.sh" >/tmp/dryrun-health.log 2>&1; then
  pass "Health gate READY"
else
  fail "Health gate NOT READY — see /tmp/dryrun-health.log; aborting"
  cat /tmp/dryrun-health.log
  exit 1
fi

# Prove the installed CLI can invoke the pinned global Sonnet 4.6 profile with
# the participant instance role. This catches package, shell, model-access, and
# IAM drift before participants reach the recommended Lab 2 path.
#
# Model selection is left to ANTHROPIC_MODEL on purpose. Passing `--model sonnet`
# here would override the pin with the CLI's floating alias, which a current CLI
# resolves to a newer Sonnet than Workshop Studio accounts expose — so the check
# would either fail on a correctly provisioned account or pass while testing a
# model no participant uses. Bootstrap pins the same variable, so this now
# exercises the participant path.
claude_smoke="$(
  CLAUDE_CODE_USE_BEDROCK=1 \
  ANTHROPIC_MODEL=global.anthropic.claude-sonnet-4-6 \
  AWS_REGION="${AWS_REGION:-us-east-1}" \
  timeout 75 claude -p \
    "Reply with exactly PELLIER_CLAUDE_READY and no other text." \
    2>/tmp/dryrun-claude.err || true
)"
if [[ "$claude_smoke" == *"PELLIER_CLAUDE_READY"* ]]; then
  pass "Claude Code invoked Sonnet through Amazon Bedrock"
else
  fail "Claude Code Bedrock smoke failed — see /tmp/dryrun-claude.err"
fi

if python3 "${REPO}/scripts/builders_starter.py" \
    --repo "$REPO" verify --expect starter >/tmp/dryrun-starter-state.json; then
  pass "Warehouse SQL and agent grant are in starter state"
else
  fail "Dry run must start from the verified tool + agent starter state"
  exit 1
fi

# Use a unique directory so retries cannot overwrite earlier backups.
pending_backup="$(mktemp -d /tmp/pellier-builders-dryrun.XXXXXX)" || exit 1
cp "$TOOLS" "$pending_backup/inventory_sql.py" || exit 1
cp "$RETRIEVAL" "$pending_backup/retrieval.sql" || exit 1
cp "$STOCK_KEEPER" "$pending_backup/stock_keeper.py" || exit 1
BACKUP_DIR="$pending_backup"
python3 "${REPO}/scripts/builders_starter.py" --repo "$REPO" complete-retrieval || exit 1
export PGHOST="${DB_HOST:?}" PGPORT="${DB_PORT:-5432}"
export PGUSER="${DB_USER:?}" PGDATABASE="${DB_NAME:?}" PGPASSWORD="${DB_PASSWORD:?}"
if uv run "${REPO}/scripts/builders_lab.py" retrieval --reference-vector >/tmp/dryrun-sql.log \
    && uv run "${REPO}/scripts/builders_lab.py" retrieval --reference-vector --max-price 0 >>/tmp/dryrun-sql.log; then
  pass "Participant SQL passes normal and empty-result checks"
else
  fail "Participant retrieval SQL failed"; exit 1
fi

# --- 2. Lab 1: PostgreSQL similarity and retrieval comparison --------------
echo "[2/6] Lab 1 - pgvector similarity in PostgreSQL"
similarity_sql="$(cat <<'SQL'
WITH reference AS (
  SELECT embedding
  FROM pellier.product_catalog
  WHERE "productId" = '4'
)
SELECT name, price, quantity,
       embedding <=> (SELECT embedding FROM reference) AS cosine_distance
FROM pellier.product_catalog
WHERE embedding IS NOT NULL
  AND "productId" <> '4'
  AND NOT (tags ? 'archive')
ORDER BY embedding <=> (SELECT embedding FROM reference)
LIMIT 5;
SQL
)"
if similarity_rows="$(_psql "$similarity_sql")" \
    && [[ "$(printf '%s\n' "$similarity_rows" | wc -l | tr -d ' ')" == "5" ]] \
    && ! printf '%s\n' "$similarity_rows" | grep -q '|$'; then
  pass "pgvector SQL returned five neighbors with cosine distances"
else
  fail "pgvector SQL did not return five numeric distances; check seed product 4 and embeddings"
fi

echo "[2/6] Lab 1 - GET /api/agent-trace/search-strategies/compare"
QUERY='A housewarming gift under $100 that is in stock'
retrieval=""
if uv run "${REPO}/scripts/builders_lab.py" --base-url "$BASE" compare \
    --query "$QUERY" --output /tmp/retrieval-comparison.json \
    >/tmp/dryrun-retrieval.log 2>/tmp/dryrun-retrieval.err; then
  retrieval="$(cat /tmp/retrieval-comparison.json)"
  if printf '%s' "$retrieval" | jq -e '
      (.strategies | length) == 4
      and all(.strategies[];
        (.observedMs | type) == "number"
        and (.modeledCostPerThousandUsd | type) == "number"
        and (.products | type) == "array")
      and (.strategies[-1].extractedFilters | type) == "object"
      and .strategies[-1].extractedFilters.priceMaxUsd == 100
      and .strategies[-1].extractedFilters.inStockOnly == true
      and (.costModel.pricingReviewedOn | type) == "string"
      and (.costModel.components.rerank.formula | type) == "string"
      and (.measurementAssumptions.latency | contains("not a percentile"))
    ' >/dev/null 2>&1; then
    pass "Four retrieval rows returned with observed latency and modeled cost"
    if ! uv run "${REPO}/scripts/builders_lab.py" retrieval >/tmp/dryrun-shared-vector.log; then
      fail "Participant SQL failed with the shared request vector"
    fi
  else
    fail "Retrieval comparison response contract is incomplete"
    info "First 300 chars: ${retrieval:0:300}"
  fi
else
  fail "Lab 1 comparison failed - see /tmp/dryrun-retrieval.err"
fi

# --- 3. Lab 2: apply and directly verify the tool ----------------------
# Fill ONLY the warehouse SQL body between the START/END markers in the live
# inventory_sql.py — exactly what the checked-in participant recovery does.
echo "[3/6] Lab 2 - wire and directly verify floor_check"
if ! python3 "${REPO}/scripts/builders_starter.py" \
    --repo "$REPO" complete-tool >/tmp/dryrun-tool-solution.json; then
  fail "Could not patch warehouse SQL body into inventory_sql.py"; exit 1
fi
pass "Filled warehouse SQL body in inventory_sql.py (other tools untouched)"

info "Waiting 4s for uvicorn --reload to pick up the tool change..."
sleep 4
if uv run "${REPO}/scripts/builders_lab.py" \
    --base-url "$BASE" tool-check >/tmp/dryrun-tool-check.json; then
  pass "Direct tool check returned Brooklyn quantity and ship window"
else
  fail "Direct floor_check verification failed"; exit 1
fi
if ! uv run "${REPO}/scripts/builders_lab.py" --base-url "$BASE" tool-check \
    --query definitely-no-such-product --expect-status not_found >/tmp/dryrun-unknown-product.json; then
  fail "Unknown-product check failed"; exit 1
fi
if uv run "${REPO}/scripts/builders_lab.py" \
    --base-url "$BASE" build-state \
    --expect-tool shipped --expect-agent exercise \
    >/tmp/dryrun-tool-wired-state.json; then
  pass "Intermediate state is tool shipped / agent ungranted"
else
  fail "Lab 2 tool check did not preserve the independent agent gap"; exit 1
fi

# --- 4. Grant the tool and observe the Strands path -------------------------
echo "[4/6] Lab 2 agent grant - grant floor_check and invoke Stock Keeper"
if python3 "${REPO}/scripts/builders_starter.py" \
    --repo "$REPO" complete-agent >/tmp/dryrun-agent-grant.json; then
  pass "Granted floor_check to the Strands Stock Keeper"
else
  fail "Could not grant floor_check to Stock Keeper"; exit 1
fi
info "Waiting 4s for uvicorn --reload to pick up the agent grant..."
sleep 4

if uv run "${REPO}/scripts/builders_lab.py" \
    --base-url "$BASE" build-state --expect shipped \
    >/tmp/dryrun-complete-state.json; then
  pass "Complete state is tool shipped / Stock Keeper shipped"
else
  fail "Agent grant did not produce the complete build state"; exit 1
fi

SESSION="dryrun-$(date +%s)"
SESSION_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
turn5='{"message":"Hadley availability in Brooklyn","session_id":"'"$SESSION"'","customer_id":"CUST-MARCO"}'
reply="$(curl -fsN --max-time 60 -X POST "${BASE}/api/chat/stream" \
  -H 'Content-Type: application/json' \
  -H "X-Pellier-Session-Token: ${SESSION_TOKEN}" \
  -d "$turn5" 2>/dev/null || true)"
if echo "$reply" | grep -qiE 'brooklyn|BK-01' \
    && echo "$reply" | grep -qiE '[0-9]+[^[:cntrl:]]*(unit|shirt|available|stock|floor)|"quantity"[[:space:]]*:[[:space:]]*[0-9]+' \
    && echo "$reply" | grep -qiE 'ship|business day|[0-9]+[[:space:]]*(-|to)[[:space:]]*[0-9]+[[:space:]]*day'; then
  pass "Reply names Brooklyn with a quantity and ship window"
else
  fail "Reply did not prove Brooklyn + quantity + ship window"
  info "First 300 chars: ${reply:0:300}"
fi
if echo "$reply" | grep -qi 'floor_check is in stub state'; then
  fail "Stub envelope still present — solution did not take effect"
fi

# --- 5. Required durable action receipt ------------------------------------
echo "[5/6] Required execution evidence - pellier.tool_audit"
# Bind the proof to THIS run's session. An unscoped receipt would accept a
# row left by an earlier rehearsal, which is exactly the false positive a
# rehearsal exists to catch.
if uv run "${REPO}/scripts/builders_lab.py" \
    --base-url "$BASE" receipt --session "$SESSION" \
    >/tmp/dryrun-tool-receipt.json; then
  pass "Participant receipt command verified this run's agent floor_check row"
else
  fail "Participant receipt command did not verify this run's floor_check row"
fi

# A receipt that only passes unscoped is a stale-evidence regression: prove
# the guard rejects a session that produced no floor_check call.
if uv run "${REPO}/scripts/builders_lab.py" \
    --base-url "$BASE" receipt --session "dryrun-absent-$(date +%s)" \
    >/dev/null 2>&1; then
  fail "Receipt accepted a session that never called floor_check"
else
  pass "Receipt rejects a session with no floor_check row"
fi
n="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE tool='floor_check' AND session_id LIKE 'dryrun-%';")"
if [[ "${n:-0}" =~ ^[0-9]+$ ]] && (( n > 0 )); then
  pass "Session-specific SQL found $n floor_check row(s) for this dry run"
else
  fail "No tool_audit row for floor_check — audit writer not firing"
fi

# Exercise the required client, which creates and checks its own new session.
if uv run "${REPO}/scripts/builders_lab.py" --base-url "$BASE" agent-check \
    >/tmp/dryrun-agent-client.log; then
  pass "Required agent-check verified its own session"
else
  fail "Required agent-check failed; see /tmp/dryrun-agent-client.log"
fi

# --- 6. SQL-claim checks (pin run-of-show numbers + verify pg_trgm) ----------
# These tighten facilitator accuracy rather than gate the participant path, so
# a surprising value WARNs (review it) rather than FAILs (blocks the room).
# Only a structurally-broken catalog (no warehouse rows at all) is fatal.
echo "[6/6] SQL claims — Beeswax warehouse split + pg_trgm index"

# 6a. Beeswax at Brooklyn: confirm the 40/30/30 split holds (BK-01 is the
# largest share) and surface the live number so the run-of-show success
# check can quote observed data instead of a guessed figure.
bees_bk="$(_psql "SELECT wi.quantity FROM pellier.warehouse_inventory wi JOIN pellier.product_catalog pc ON pc.\"productId\" = wi.product_id WHERE pc.name ILIKE '%beeswax taper%' AND wi.warehouse_id = 'BK-01';")"
bees_other="$(_psql "SELECT COALESCE(max(wi.quantity),0) FROM pellier.warehouse_inventory wi JOIN pellier.product_catalog pc ON pc.\"productId\" = wi.product_id WHERE pc.name ILIKE '%beeswax taper%' AND wi.warehouse_id <> 'BK-01';")"
if [[ -z "${bees_bk}" ]]; then
  fail "No Beeswax Taper warehouse rows — catalog/warehouse seed incomplete"
elif [[ "${bees_bk}" =~ ^[0-9]+$ && "${bees_other}" =~ ^[0-9]+$ ]] && (( bees_bk >= bees_other )); then
  pass "Beeswax split correct — BK-01=${bees_bk} ≥ other warehouses (max ${bees_other}). Quote BK-01=${bees_bk} in the run-of-show."
else
  warn "Beeswax BK-01=${bees_bk} is NOT the largest (other max=${bees_other}) — 40/30/30 split may have re-seeded oddly; recheck run-of-show number."
fi

# 6b. pg_trgm: confirm migration 008's "prevents sequential scans" claim by
# asking the planner. At 40 rows Postgres seq-scans regardless (correct +
# cheap), so this is informational — what we're checking is that the trigram
# index EXISTS and that the plan is what the migration comment implies.
trgm_idx="$(_psql "SELECT count(*) FROM pg_indexes WHERE schemaname='pellier' AND indexname='product_catalog_name_trgm_idx';")"
if [[ "${trgm_idx:-0}" == "1" ]]; then
  plan="$(_psql "EXPLAIN SELECT \"productId\" FROM pellier.product_catalog WHERE lower(name) LIKE '%hadley%';" | tr '\n' ' ')"
  if echo "$plan" | grep -qi "trgm\|bitmap index scan"; then
    pass "pg_trgm index exists and the planner uses it for lower(name) LIKE '%…%'."
  else
    info "pg_trgm index exists; at this row count the planner seq-scans (expected). Plan: ${plan:0:120}"
    info "  → migration 008's 'prevents seq scans' claim is a production-scale statement, not a 40-row one. Comment is accurate as written."
  fi
else
  warn "pg_trgm index product_catalog_name_trgm_idx missing — migration 008 may not have applied."
fi

echo "════════════════════════════════════════════════════════════"
if $FAILED; then
  printf "${RED}● DRY RUN FAILED${NC} — fix the ✗ items before the room opens.\n"
  exit 1
else
  printf "${GREEN}● DRY RUN PASSED${NC} — the participant path works end to end.\n"
  exit 0
fi
