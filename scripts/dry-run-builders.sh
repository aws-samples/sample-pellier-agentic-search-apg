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
#   6. SQL claims     — Beeswax 40/30/30 split (pin run-of-show number) +
#                       pg_trgm index presence/plan (migration 008 claim)
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
# The participant fills ONLY the floor_check body between the START/END markers
# in the already-in-place agent_tools.py (the builders pre-apply variant, which
# defines process_return, escalate_to_stylist, etc.). The dry-run mirrors that
# exactly — it patches the body in place rather than swapping the whole file,
# so it can't drift from the live participant artifact. BODY is the canonical
# reference body (same one Module 02's paste-only escape hatch uses).
BODY="${REPO}/solutions/closing-marcos-gap/services/floor_check_tool_body.py"
KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
fail() { printf "  ${RED}✗${NC} %s\n" "$1"; FAILED=true; }
info() { printf "  ${YEL}…${NC} %s\n" "$1"; }
# warn: review-worthy but non-fatal (does NOT set FAILED / block the gate).
warn() { printf "  ${YEL}•${NC} %s\n" "$1"; }
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
echo "[1/6] Preconditions (health gate)"
if bash "${REPO}/scripts/health-gate.sh" >/tmp/dryrun-health.log 2>&1; then
  pass "Health gate READY"
else
  fail "Health gate NOT READY — see /tmp/dryrun-health.log; aborting"
  cat /tmp/dryrun-health.log
  exit 1
fi

# --- 2. Apply the solution (simulate the participant's build) ---------------
# Fill ONLY the floor_check body between the START/END markers in the live
# agent_tools.py — exactly what a participant does. This keeps every other tool
# (process_return, escalate_to_stylist, ...) intact, so the import graph the
# Experience Guide relies on is never broken. (A prior version swapped the whole
# file for a separate "solution" copy that had drifted — it was missing
# process_return, which crashed experience_guide.py's module-load import.)
echo "[2/6] Wire floor_check (fill the body between the markers)"
if [[ ! -f "$BODY" ]]; then
  fail "Reference body file missing: $BODY"; exit 1
fi
if ! grep -q "WORKSHOP_EXERCISE_STUB" "$TOOLS"; then
  info "floor_check already wired (no stub marker) — leaving agent_tools.py as-is"
else
  # Guard the backup explicitly: if it fails we must NOT patch the file in
  # place, or restore() (which keys on the .bak existing) would leave
  # agent_tools.py permanently in the patched state. (This script runs with
  # `set -uo pipefail`, not `-e`, by design – it accumulates FAILED and
  # reports a summary – so a bare cp failure would otherwise pass silently.)
  if ! cp "$TOOLS" "${TOOLS}.dryrun.bak"; then
    fail "Could not back up agent_tools.py (cp failed) – refusing to patch in place"; exit 1
  fi
  python3 - "$TOOLS" "$BODY" <<'PYEOF'
import sys, re
tools_path, body_path = sys.argv[1], sys.argv[2]
src = open(tools_path).read()
# Body file has a 2-line "# Paste inside ..." comment header; keep only the code.
body_lines = open(body_path).read().splitlines()
body = "\n".join(l for l in body_lines if not l.lstrip().startswith("# Paste"))
body = body.strip("\n")
start = "# === CHALLENGE · Stock Keeper · floor_check: START ==="
end   = "# === CHALLENGE · Stock Keeper · floor_check: END ==="
pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
repl = start + "\n" + body + "\n    " + end
new, n = pat.subn(repl, src)
if n != 1:
    sys.stderr.write(f"expected 1 marker block, replaced {n}\n"); sys.exit(1)
open(tools_path, "w").write(new)
PYEOF
  if [[ $? -ne 0 ]]; then fail "Could not patch floor_check body into agent_tools.py"; exit 1; fi
  pass "Filled floor_check body in agent_tools.py (other tools untouched)"
fi
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
echo "[3/6] Marco Turn 4 — POST /api/chat/stream"
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
echo "[4/6] AgentCore Runtime invoke — POST /api/agent/chat"
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

# --- 4c. Managed Policy on the AUTHENTICATED Gateway rail (Act II Exercise 2) -
# The reshaped Act II runs process_return through the Gateway (pattern=
# agents_as_tools) with a Cognito bearer token, where managed AgentCore Policy
# (Cedar, ENFORCE) ALLOWs reason=damaged and DENYs anything else. This step
# mints a test-user token and exercises BOTH outcomes so a fresh-account
# facilitator knows the policy beat will actually demonstrate. Degrades to
# `info` (never fails the run) when policy/creds aren't provisioned — the
# floor_check path above is the hard gate, not this.
echo "[4c/6] Managed Policy (Gateway rail) — process_return ALLOW vs DENY"
POLICY_TOKEN=""
if [[ -n "${COGNITO_POOL:-${COGNITO_POOL_ID:-}}" && -n "${COGNITO_CLIENT:-${COGNITO_CLIENT_ID:-}}" \
      && -n "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" && -n "${AGENTCORE_POLICY_ENGINE_ID:-}" ]]; then
  _pool="${COGNITO_POOL:-${COGNITO_POOL_ID}}"; _client="${COGNITO_CLIENT:-${COGNITO_CLIENT_ID}}"
  # Pull user[0] from the test-credentials secret and mint an access token.
  _creds="$(aws secretsmanager get-secret-value --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" \
    --query SecretString --output text 2>/dev/null || true)"
  _u="$(echo "$_creds" | python3 -c 'import sys,json;u=json.load(sys.stdin)["users"][0];print(u["username"])' 2>/dev/null || true)"
  _p="$(echo "$_creds" | python3 -c 'import sys,json;u=json.load(sys.stdin)["users"][0];print(u["password"])' 2>/dev/null || true)"
  if [[ -n "$_u" && -n "$_p" ]]; then
    POLICY_TOKEN="$(aws cognito-idp admin-initiate-auth --user-pool-id "$_pool" --client-id "$_client" \
      --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters "USERNAME=$_u,PASSWORD=$_p" \
      --query 'AuthenticationResult.AccessToken' --output text 2>/dev/null || true)"
  fi
fi
if [[ -n "$POLICY_TOKEN" ]]; then
  # ALLOW: damaged return should succeed via the Gateway rail.
  allow_body='{"message":"My Wabi-Sabi Bowl arrived chipped. Please file a damaged return (my customer id is '"'"'theo'"'"').","pattern":"agents_as_tools"}'
  allow_reply="$(curl -fsN --max-time 90 -X POST "${BASE}/api/chat/stream" \
    -H "Authorization: Bearer ${POLICY_TOKEN}" -H 'Content-Type: application/json' -d "$allow_body" 2>/dev/null || true)"
  if echo "$allow_reply" | grep -qiE 'return|filed|refund|process'; then
    pass "Managed Policy ALLOW — damaged return processed on the Gateway rail"
  else
    warn "ALLOW turn returned nothing obvious (first 200: ${allow_reply:0:200}) — check Gateway/token"
  fi
  # DENY: a non-damaged reason should be blocked by Cedar at the Gateway.
  deny_body='{"message":"My Wabi-Sabi Bowl does not match my shelf. Please file a return (my customer id is '"'"'theo'"'"').","pattern":"agents_as_tools"}'
  curl -fsN --max-time 90 -X POST "${BASE}/api/chat/stream" \
    -H "Authorization: Bearer ${POLICY_TOKEN}" -H 'Content-Type: application/json' -d "$deny_body" >/dev/null 2>&1 || true
  info "DENY turn fired (non-damaged) — verified by the tool_audit count check in step 5."
else
  info "Skipped — managed Policy + Cognito test creds not all present (AGENTCORE_POLICY_ENGINE_ID / COGNITO_*). On a provisioned account this is the Act II proof; here the in-process path still covers floor_check."
fi

# --- 4b. Gateway wiring (Atelier Card 7 demo + JWT passthrough) --------------
echo "[4b/6] AgentCore Gateway wiring — GET /api/agentcore/gateway/status"
gw="$(curl -fsN --max-time 30 "${BASE}/api/agentcore/gateway/status" 2>/dev/null || true)"
if echo "$gw" | grep -q '"configured"[[:space:]]*:[[:space:]]*true'; then
  pass "Gateway configured (AGENTCORE_GATEWAY_URL set; source=mcp-discovery)"
else
  # Not fatal: in-process is the default execution path for the room. But on a
  # provisioned account this should be true, or the Atelier Card 7 Gateway
  # demo and JWT passthrough won't have anything live to show.
  info "Gateway NOT configured (source=in-process-imports) — Card 7 shows the 'skipped' panel."
  info "  Expected the live demo? Check AGENTCORE_GATEWAY_URL in pellier/backend/.env"
  info "  Raw: ${gw:0:200}"
fi

# --- 5. Audit ledger --------------------------------------------------------
echo "[5/6] Audit ledger — pellier.tool_audit"
n="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE tool='floor_check' AND session_id LIKE 'dryrun-%';")"
if [[ "${n:-0}" =~ ^[0-9]+$ ]] && (( n > 0 )); then
  pass "tool_audit has $n floor_check row(s) for this dry run"
else
  fail "No tool_audit row for floor_check — audit writer not firing"
fi

# 5b. Managed-Policy evidence (only when step 4c ran the Gateway rail). Proves
# the Act II beat: an ALLOWed damaged return wrote a process_return row keyed by
# customer_id='theo' with reason='damaged'; a DENYed non-damaged return wrote
# NONE (the absence is the proof — Cedar blocked it at the Gateway).
if [[ -n "$POLICY_TOKEN" ]]; then
  pr_allowed="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE tool='process_return' AND args->>'customer_id'='theo' AND args->>'reason'='damaged';")"
  pr_denied="$(_psql "SELECT count(*) FROM pellier.tool_audit WHERE tool='process_return' AND args->>'customer_id'='theo' AND args->>'reason'<>'damaged';")"
  if [[ "${pr_allowed:-0}" =~ ^[0-9]+$ ]] && (( pr_allowed > 0 )); then
    pass "Managed Policy ALLOW evidence — ${pr_allowed} damaged process_return row(s) for theo"
  else
    fail "No damaged process_return row for theo — Gateway rail or policy ALLOW not landing in tool_audit"
  fi
  if [[ "${pr_denied:-0}" == "0" ]]; then
    pass "Managed Policy DENY proof — zero non-damaged process_return rows (Cedar blocked at the Gateway)"
  else
    warn "Found ${pr_denied} non-damaged process_return row(s) for theo — Cedar DENY may not be enforcing (engine attached in ENFORCE mode?)"
  fi
else
  info "Policy ledger checks skipped (step 4c did not run)."
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
