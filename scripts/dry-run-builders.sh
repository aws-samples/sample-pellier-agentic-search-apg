#!/usr/bin/env bash
# =============================================================================
# dry-run-builders.sh — end-to-end simulation of the participant path
# =============================================================================
# Run this before a 100-person room to catch breakage the health gate can't:
# it actually exercises the required lab path against the live backend.
#
#   1. Preconditions  — health gate must be READY
#   1b. Claude Code   — CLI present + pinned Bedrock model reachable
#   2. Apply solutions — complete Inventory Agent and wire check_inventory
#   3. Build + trace  — POST /api/chat/stream; assert Brooklyn, count, ship window
#   4. Retrieval      — run the exact four-strategy Lab 2 request
#   5. Audit ledger   — run initiate_return and query its exact session receipt
#   6. SQL claims     — Beeswax 40/30/30 split (pin run-of-show number) +
#                       pg_trgm index presence/plan (migration 008 claim)
#
# This applies both Lab 1 marker-scoped solutions temporarily and creates the
# same return and audit evidence rows as a participant. It backs both source
# files up and restores them on exit unless --keep is passed. Run it on a
# workshop environment, not a production database.
#
# Usage:
#   scripts/dry-run-builders.sh            # apply solution, test, restore stub
#   scripts/dry-run-builders.sh --keep     # leave the solution applied
# =============================================================================
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
BASE="${PELLIER_BASE_URL:-http://localhost:8000}"
TOOLS="${REPO}/pellier/backend/services/agent_tools.py"
TOOLS_REFERENCE="${REPO}/solutions/closing-marcos-gap/services/agent_tools_check_inventory_solution.py"
AGENT="${REPO}/pellier/backend/agents/inventory_agent.py"
AGENT_REFERENCE="${REPO}/solutions/waking-the-stock-keeper/agents/inventory_agent_solution.py"
BACKUP_SUFFIX=".dryrun.$$.bak"
# Participants edit only the two START/END blocks. The rehearsal mirrors that
# contract by copying each reference block into the live file; it never swaps a
# whole module or changes code outside the workshop markers.
KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
fail() { printf "  ${RED}✗${NC} %s\n" "$1"; FAILED=true; }
info() { printf "  ${YEL}…${NC} %s\n" "$1"; }
# warn: review-worthy but non-fatal (does NOT set FAILED / block the gate).
warn() { printf "  ${YEL}•${NC} %s\n" "$1"; }
FAILED=false

# Load values as data: participant dotenv text must not execute shell code.
# shellcheck source=lib/dotenv.sh
. "$REPO/scripts/lib/dotenv.sh"
[[ -f "$ENV_FILE" ]] && pellier_load_dotenv "$ENV_FILE"
GOVERNED=false
[[ "${WORKSHOP_FORMAT:-builders}" == "governed" ]] && GOVERNED=true

_psql() {
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" -tAc "$1" 2>/dev/null
}

restore() {
  local restored=false
  if $KEEP; then
    rm -f "${AGENT}${BACKUP_SUFFIX}" "${TOOLS}${BACKUP_SUFFIX}"
    return
  fi
  if [[ -f "${AGENT}${BACKUP_SUFFIX}" ]]; then
    mv "${AGENT}${BACKUP_SUFFIX}" "$AGENT"
    restored=true
  fi
  if [[ -f "${TOOLS}${BACKUP_SUFFIX}" ]]; then
    mv "${TOOLS}${BACKUP_SUFFIX}" "$TOOLS"
    restored=true
  fi
  if $restored; then
    info "Restored both Lab 1 source files. Backend will reload."
  fi
}
trap restore EXIT

patch_marker_block() {
  local live_path="$1"
  local reference_path="$2"
  local start_marker="$3"
  local end_marker="$4"
  local label="$5"

  if [[ ! -f "$live_path" ]]; then
    fail "Live source file missing: $live_path"; return 1
  fi
  if [[ ! -f "$reference_path" ]]; then
    fail "Reference source file missing: $reference_path"; return 1
  fi
  if ! cp "$live_path" "${live_path}${BACKUP_SUFFIX}"; then
    fail "Could not back up $live_path; refusing to patch it"; return 1
  fi

  python3 - "$live_path" "$reference_path" "$start_marker" "$end_marker" <<'PYEOF'
from pathlib import Path
import sys

live_path = Path(sys.argv[1])
reference_path = Path(sys.argv[2])
start_marker = sys.argv[3]
end_marker = sys.argv[4]
live = live_path.read_text()
reference = reference_path.read_text()


def marker_span(text: str, source: Path) -> tuple[int, int]:
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise SystemExit(
            f"{source}: expected exactly one {start_marker!r} / {end_marker!r} block"
        )
    if text.find(start_marker, start + len(start_marker)) >= 0:
        raise SystemExit(f"{source}: duplicate start marker {start_marker!r}")
    if text.find(end_marker, end + len(end_marker)) >= 0:
        raise SystemExit(f"{source}: duplicate end marker {end_marker!r}")
    return start, end + len(end_marker)


live_start, live_end = marker_span(live, live_path)
reference_start, reference_end = marker_span(reference, reference_path)
replacement = reference[reference_start:reference_end]
live_path.write_text(live[:live_start] + replacement + live[live_end:])
PYEOF
  if [[ $? -ne 0 ]]; then
    fail "Could not apply the $label marker block"; return 1
  fi
  pass "Applied the $label marker block"
}

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

# --- 1b. Claude Code preflight (Lab 1's recommended participant path) --------
#
# Lab 1 recommends Claude Code as the default build lane, so the release gate
# has to prove the lane can start. This checks the two things that actually
# drift between accounts — the CLI package and Bedrock model access under the
# participant instance role — before a room discovers them.
#
# Model selection is left to ANTHROPIC_MODEL on purpose. Passing `--model
# sonnet` would override the pin with the CLI's floating alias and could test
# a different model than participants use. bootstrap-labs.sh pins the same
# variable, so this exercises the participant path.
#
# What this deliberately does NOT do: drive a real Claude Code edit. A
# generated diff is nondeterministic, and the deterministic contract is the
# tool implementation plus its proof — which stage 2 applies and stage 3
# verifies through the same commands a participant runs. The AI edit path
# itself is a manual fresh-account check; see the facilitator notes.
echo "[1b/6] Claude Code preflight (Lab 1 recommended lane)"
CLAUDE_MODEL_PIN="${ANTHROPIC_MODEL:-global.anthropic.claude-sonnet-5}"
if ! command -v claude >/dev/null 2>&1; then
  fail "Claude Code CLI not on PATH — Lab 1's recommended lane cannot start"
else
  pass "Claude Code CLI present ($(claude --version 2>/dev/null | head -1))"
  claude_smoke="$(
    CLAUDE_CODE_USE_BEDROCK=1 \
    ANTHROPIC_MODEL="$CLAUDE_MODEL_PIN" \
    AWS_REGION="${AWS_REGION:-us-east-1}" \
    timeout 75 claude -p \
      "Reply with exactly PELLIER_CLAUDE_READY and no other text." \
      2>/tmp/dryrun-claude.err || true
  )"
  if [[ "$claude_smoke" == *"PELLIER_CLAUDE_READY"* ]]; then
    pass "Claude Code reached ${CLAUDE_MODEL_PIN} through Amazon Bedrock"
  else
    fail "Claude Code Bedrock smoke failed for ${CLAUDE_MODEL_PIN} — see /tmp/dryrun-claude.err"
  fi
fi

# --- 2. Apply the solutions (simulate both participant edits) ----------------
echo "[2/6] Complete Inventory Agent and wire check_inventory"
if grep -q '^_INVENTORY_AGENT_STUBBED = True$' "$AGENT"; then
  patch_marker_block \
    "$AGENT" "$AGENT_REFERENCE" \
    "# === WORKSHOP · Inventory Agent · definition: START ===" \
    "# === WORKSHOP · Inventory Agent · definition: END ===" \
    "Inventory Agent definition" || exit 1
else
  info "Inventory Agent definition already complete — leaving inventory_agent.py as-is"
fi

if grep -q "check_inventory is in stub state" "$TOOLS"; then
  patch_marker_block \
    "$TOOLS" "$TOOLS_REFERENCE" \
    "# === WORKSHOP · Inventory Agent · check_inventory: START ===" \
    "# === WORKSHOP · Inventory Agent · check_inventory: END ===" \
    "check_inventory body" || exit 1
else
  info "check_inventory already wired — leaving agent_tools.py as-is"
fi
info "Waiting 4s for uvicorn --reload to pick up the change…"
sleep 4

# Confirm both independent build markers flipped to shipped.
bs="$(curl -fs --max-time 5 "${BASE}/api/observatory/build-state" 2>/dev/null || true)"
if echo "$bs" | grep -q '"Inventory Agent"[[:space:]]*:[[:space:]]*"shipped"'; then
  pass "build-state reports Inventory Agent = shipped"
else
  fail "build-state did not flip Inventory Agent to shipped (got: ${bs:0:200})"
fi
if echo "$bs" | grep -q '"check_inventory"[[:space:]]*:[[:space:]]*"shipped"'; then
  pass "build-state reports check_inventory = shipped"
else
  fail "build-state did not flip check_inventory to shipped (got: ${bs:0:200})"
fi

# --- 3. Marco Turn 4 via the dispatcher path --------------------------------
echo "[3/6] Marco Turn 4 — POST /api/chat/stream"
SESSION="dryrun-$(date +%s)"
turn4='{"message":"How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?","session_id":"'"$SESSION"'","customer_id":"CUST-MARCO"}'
reply="$(curl -fsN --max-time 60 -X POST "${BASE}/api/chat/stream" \
  -H 'Content-Type: application/json' -d "$turn4" 2>/dev/null || true)"
if echo "$reply" | grep -qiE 'brooklyn|BK-01' \
    && echo "$reply" | grep -qiE '[0-9]+[^[:cntrl:]]*(unit|shirt|available|stock|floor)|"quantity"[[:space:]]*:[[:space:]]*[0-9]+' \
    && echo "$reply" | grep -qiE 'ship|business day|[0-9]+[[:space:]]*(-|to)[[:space:]]*[0-9]+[[:space:]]*day'; then
  pass "Reply names Brooklyn with a quantity and ship window"
else
  fail "Reply did not prove Brooklyn + quantity + ship window"
  info "First 300 chars: ${reply:0:300}"
fi
if echo "$reply" | grep -qi 'check_inventory is in stub state'; then
  fail "Stub envelope still present — solution did not take effect"
fi

# --- 4a. Lab 2 retrieval comparison ----------------------------------------
echo "[4a/6] Lab 2 — GET /api/observatory/search-strategies/compare"
QUERY='A milestone gift for a new homeowner'
retrieval=""
if retrieval="$(curl --fail --silent --show-error --max-time 75 \
    --get --data-urlencode "query=${QUERY}" \
    "${BASE}/api/observatory/search-strategies/compare" 2>/tmp/dryrun-retrieval.err)"; then
  printf '%s\n' "$retrieval" > /tmp/retrieval-comparison.json
  if printf '%s' "$retrieval" | jq -e '
      (.strategies | length) == 4
      and all(.strategies[];
        (.observedMs | type) == "number"
        and (.modeledCostPerThousandUsd | type) == "number"
        and (.products | type) == "array")
      and (.strategies[-1].extractedFilters | type) == "object"
      and (.measurementAssumptions.latency | contains("not a percentile"))
    ' >/dev/null 2>&1; then
    pass "Four retrieval rows returned with observed latency and modeled cost"
  else
    fail "Retrieval comparison response contract is incomplete"
    info "First 300 chars: ${retrieval:0:300}"
  fi
else
  fail "Lab 2 comparison failed — see /tmp/dryrun-retrieval.err"
fi

# --- 4b. Ledger write rail --------------------------------------------------
LEDGER_SESSION=""
if $GOVERNED; then
  echo "[4b/6] Audit Agent Actions with SQL — governed write runs through Gateway in step 4d"
  info "Skipping local initiate_return; governed mutations require gateway-mcp"
else
  echo "[4b/6] Audit Agent Actions with SQL — initiate_return on the builders dispatcher rail"
  LEDGER_SESSION="dryrun-ledger-$(date +%s)-$$"
  ledger_body='{"message":"My Wabi-Sabi Bowl arrived chipped. Please file a damaged return (my customer id is '"'"'theo'"'"').","session_id":"'"$LEDGER_SESSION"'","pattern":"dispatcher"}'
  if curl --fail --silent --show-error --no-buffer --max-time 75 \
      -X POST "${BASE}/api/chat/stream" \
      -H 'Content-Type: application/json' \
      -d "$ledger_body" > /tmp/pellier-ledger-turn.sse; then
    pass "Builders initiate_return stream completed for session ${LEDGER_SESSION}"
  else
    fail "Builders initiate_return request failed"
  fi
fi

# Mint one real Cognito token for the managed Runtime and Gateway checks.
POLICY_TOKEN=""
TOKEN_HELPER="/home/${CODE_EDITOR_USER:-participant}/pellier-token.sh"
if [[ -f "$TOKEN_HELPER" ]]; then
  # shellcheck source=/dev/null
  source "$TOKEN_HELPER" marco >/tmp/dryrun-token.log 2>&1 || true
  POLICY_TOKEN="${PELLIER_TOKEN:-}"
fi

# --- 4c. Managed Runtime invoke ----------------------------------------------
echo "[4c/6] AgentCore Runtime invoke — POST /api/agent/chat"
if [[ -n "${AGENTCORE_RUNTIME_ENDPOINT:-}" && "${USE_AGENTCORE_RUNTIME:-false}" == "true" \
      && -n "$POLICY_TOKEN" ]]; then
  rt='{"message":"Find linen travel pieces for a warm-weather trip.","session_id":"'"$SESSION"'-rt"}'
  rtreply="$(curl -fsN --max-time 90 -X POST "${BASE}/api/agent/chat" \
    -H "Authorization: Bearer ${POLICY_TOKEN}" \
    -H 'Content-Type: application/json' -d "$rt" 2>/dev/null || true)"
  runtime_rail="$(printf '%s\n' "$rtreply" | sed -n 's/^data: //p' \
    | jq -r 'select(.trace != null) | .trace.rail // empty' 2>/dev/null \
    | tail -1)"
  if [[ "$runtime_rail" == "gateway-mcp" ]]; then
    pass "Managed Runtime returned rail=gateway-mcp with Cognito JWT passthrough"
  else
    fail "Runtime smoke did not prove gateway-mcp (rail=${runtime_rail:-missing}; first 200: ${rtreply:0:200})"
  fi
else
  if $GOVERNED; then
    fail "Managed Runtime proof unavailable (endpoint, switch, or Cognito token missing)"
  else
    info "Skipped — managed Runtime or Cognito token unavailable (optional for builders)"
  fi
fi

# --- 4d. Managed Policy on the authenticated Gateway rail --------------------
# Call the Gateway MCP tool directly. The helper classifies only an actual
# authorization failure as DENY and verifies ALLOW creates a tool_audit row
# while DENY creates none.
echo "[4d/6] Managed Policy (Gateway rail) — initiate_return ALLOW vs DENY"
POLICY_ALLOW_SESSION="dryrun-policy-allow-$(date +%s)-$$"
POLICY_DENY_SESSION="dryrun-policy-deny-$(date +%s)-$$"
if [[ -n "$POLICY_TOKEN" && -n "${AGENTCORE_POLICY_ENGINE_ID:-}" \
      && -n "${AGENTCORE_GATEWAY_URL:-}" ]]; then
  export PELLIER_TOKEN
  if python3 "$REPO/scripts/deploy/gateway_initiate_return.py" \
      --product-id 31 --reason damaged --expect allow --record-receipt \
      --session-id "$POLICY_ALLOW_SESSION" \
      >/tmp/dryrun-policy-allow.json 2>/tmp/dryrun-policy-allow.err; then
    pass "Managed Policy ALLOW executed and wrote current-session audit evidence"
  else
    fail "Managed Policy ALLOW proof failed — see /tmp/dryrun-policy-allow.err"
  fi
  if python3 "$REPO/scripts/deploy/gateway_initiate_return.py" \
      --product-id 31 --reason changed_mind --expect deny --record-receipt \
      --session-id "$POLICY_DENY_SESSION" \
      >/tmp/dryrun-policy-deny.json 2>/tmp/dryrun-policy-deny.err; then
    pass "Managed Policy DENY blocked before Lambda execution"
  else
    fail "Managed Policy DENY proof failed — see /tmp/dryrun-policy-deny.err"
  fi
else
  if $GOVERNED; then
    fail "Managed Policy proof unavailable (Policy, Gateway, or Cognito token missing)"
  else
    info "Skipped — managed Policy or Cognito token unavailable (optional for builders)"
  fi
fi

# --- 4e. Gateway wiring -------------------------------------------------------
echo "[4e/6] AgentCore Gateway wiring — GET /api/agentcore/gateway/status"
gw="$(curl -fsN --max-time 30 "${BASE}/api/agentcore/gateway/status" 2>/dev/null || true)"
if echo "$gw" | grep -q '"configured"[[:space:]]*:[[:space:]]*true'; then
  pass "Gateway configured (AGENTCORE_GATEWAY_URL set; source=mcp-discovery)"
else
  if $GOVERNED; then
    fail "Gateway NOT configured — governed Runtime/Policy proof is unavailable"
  else
    info "Gateway NOT configured — optional managed inspection is unavailable."
  fi
  info "  Expected the live demo? Check AGENTCORE_GATEWAY_URL in pellier/backend/.env"
  info "  Raw: ${gw:0:200}"
fi

# --- 5. Audit ledger --------------------------------------------------------
echo "[5/6] Audit ledger — pellier.tool_audit"
n="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE tool='check_inventory' AND session_id LIKE 'dryrun-%';")"
if [[ "${n:-0}" =~ ^[0-9]+$ ]] && (( n > 0 )); then
  pass "tool_audit has $n check_inventory row(s) for this dry run"
else
  fail "No tool_audit row for check_inventory — audit writer not firing"
fi

if $GOVERNED; then
  info "Governed initiate_return ledger row is verified with its receipt below"
else
  ledger_rows="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE session_id='${LEDGER_SESSION}' AND tool='initiate_return' AND caller='agent' AND args->>'customer_id'='theo' AND args->>'reason'='damaged' AND result->>'return_id' IS NOT NULL;")"
  if [[ "${ledger_rows:-0}" =~ ^[0-9]+$ ]] && (( ledger_rows > 0 )); then
    pass "Session-specific initiate_return receipt is complete for ${LEDGER_SESSION}"
  else
    fail "No complete initiate_return receipt for session ${LEDGER_SESSION}"
  fi
fi

# 5b. Managed-Policy evidence, keyed to this dry run's unique receipt sessions.
if [[ -n "$POLICY_TOKEN" && -n "${AGENTCORE_POLICY_ENGINE_ID:-}" ]]; then
  pr_allowed="$(_psql "SELECT count(*) FROM pellier.governed_receipts gr JOIN pellier.tool_audit ta ON ta.audit_id = gr.audit_id WHERE gr.session_id='${POLICY_ALLOW_SESSION}' AND gr.decision='ALLOW' AND gr.identity_source='cognito' AND gr.verified_subject IS NOT NULL AND gr.token_fingerprint_sha256 IS NOT NULL AND ta.tool='initiate_return' AND ta.caller='gateway' AND ta.args->>'reason'='damaged' AND ta.result->>'return_id' IS NOT NULL;")"
  pr_denied="$(_psql "SELECT count(*) FROM pellier.governed_receipts WHERE session_id='${POLICY_DENY_SESSION}' AND decision='DENY' AND audit_id IS NULL AND identity_source='cognito' AND verified_subject IS NOT NULL AND token_fingerprint_sha256 IS NOT NULL AND args->>'absence_verified'='true';")"
  if [[ "${pr_allowed:-0}" == "1" ]]; then
    pass "Managed Policy ALLOW receipt is Cognito-bound and joins its Gateway audit row"
  else
    fail "Current-session ALLOW receipt is not bound to Cognito plus Gateway audit evidence"
  fi
  if [[ "${pr_denied:-0}" == "1" ]]; then
    pass "Managed Policy DENY receipt proves no execution row was written"
  else
    fail "Current-session DENY receipt did not prove pre-execution blocking"
  fi
else
  info "Policy ledger checks skipped (step 4d did not run)."
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

if $GOVERNED; then
  echo "[reset] Restore canonical governed state"
  if PELLIER_REPO="$REPO" bash "$REPO/scripts/reset-governed-workshop.sh" \
      >/tmp/dryrun-governed-reset.log 2>&1; then
    pass "Governed database, evidence, and Policy state restored"
  else
    fail "Governed reset failed — see /tmp/dryrun-governed-reset.log"
  fi
fi

echo "════════════════════════════════════════════════════════════"
if $FAILED; then
  printf "${RED}● DRY RUN FAILED${NC} — fix the ✗ items before the room opens.\n"
  exit 1
else
  printf "${GREEN}● DRY RUN PASSED${NC} — the participant path works end to end.\n"
  exit 0
fi
