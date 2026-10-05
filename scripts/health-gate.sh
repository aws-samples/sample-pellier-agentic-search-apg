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
#   2. Catalog row count == expected (100 by default)
#   3. Warehouse inventory present (300 rows: 100 curated x 3 warehouses)
#   3b. The ten tables, the evidence triggers, the pellier_agent role and its
#       row-level security policies, and the seeded customers and orders
#   4. node --version is 24 LTS                   (required for governed format;
#      warning for builders format; CLI minimum compatibility alone does not
#      establish a supported workshop release runtime)
#   5. Required Bedrock model preflight passed     (required)
#   6. AGENTCORE_MEMORY_ID set and SDK-backed
#   7. AGENTCORE_RUNTIME_ENDPOINT set and the workshop starts on its intended rail
#   8. AGENTCORE_GATEWAY_URL + ARN set
#   9. AGENTCORE_POLICY_ENGINE_ID set
#  10. Provisioning receipt proves managed resources, Runtime smoke, and traces
#  11. Operator group authorizes the desk, and no shopper is in it
#  12. Hosted UI sign-in is configured and the seeded Operator can mint a token
#
# In WORKSHOP_FORMAT=governed, all managed AgentCore checks are required because
# Labs 3 and 4 and the session abstract depend on them. The separate one-hour
# builders format retains warning-only managed checks.
# =============================================================================
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
EXPECTED_CATALOG="${EXPECTED_CATALOG:-100}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/health}"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}✓ PASS${NC}  %s\n" "$1"; }
fail() { printf "  ${RED}✗ FAIL${NC}  %s\n" "$1"; }
warn() { printf "  ${YEL}• WARN${NC}  %s\n" "$1"; }

ok=true

# Load configuration as dotenv data, never as executable shell. A fresh
# Workshop Studio root `.env` is shell-safe today, but local and recovery
# paths also read backend dotenv files where generated passwords may not be.
# Keeping this entrypoint parser-based makes the health result about service
# readiness, not punctuation in a secret.
DOTENV_HELPER="${SCRIPT_DIR}/lib/dotenv.sh"
if [[ ! -r "$DOTENV_HELPER" ]]; then
  fail "Missing dotenv parser: $DOTENV_HELPER"
  exit 1
fi
# shellcheck source=lib/dotenv.sh
source "$DOTENV_HELPER"
env_file_loaded=false
if [[ -f "$ENV_FILE" ]]; then
  pellier_load_dotenv "$ENV_FILE"
  env_file_loaded=true
elif [[ -f "${REPO}/pellier/backend/.env" ]]; then
  ENV_FILE="${REPO}/pellier/backend/.env"
  pellier_load_dotenv "$ENV_FILE"
  env_file_loaded=true
fi

# Default to the strict workshop, not the lenient one.
#
# This read used to default to `builders`, the inverse of bootstrap-labs.sh,
# which defaults to `governed`. The two disagreeing is not a style difference:
# in the lenient branch every managed AgentCore check downgrades from fail to
# warn AND the whole Aurora verification block below is skipped -- the ten
# tables, the evidence triggers and the row-level security Labs 1-4 query. The gate then exits 0 and prints READY, so bootstrap's governed fatal
# check never fires. Defaulting the other way makes an unset variable produce a
# noisy failure instead of a quiet, green, wrong answer.
#
# `pellier/backend/.env` (the fallback file above) carries no WORKSHOP_FORMAT
# key at all, so this default decides the outcome on every local run.
if [[ -z "${WORKSHOP_FORMAT:-}" ]]; then
  if $env_file_loaded; then
    warn "WORKSHOP_FORMAT is not set in ${ENV_FILE}; assuming governed."
  else
    warn "No environment file found (looked for \$PELLIER_ENV_FILE and ${REPO}/pellier/backend/.env); assuming WORKSHOP_FORMAT=governed."
  fi
fi

managed_required=false
if [[ "${WORKSHOP_FORMAT:-governed}" == "governed" ]]; then
  managed_required=true
fi

managed_missing() {
  local message="$1"
  if $managed_required; then
    fail "$message"
    ok=false
  else
    warn "$message"
  fi
}

echo "Pellier health gate — $(date '+%H:%M:%S')"
echo "------------------------------------------------------------"

# 0. Lifecycle markers. Both live under /var/lib/pellier on a box; the env
# overrides exist so the contract tests can point them at a sandbox.
#
# The quarantine marker is written by reset-governed-workshop.sh when it could
# not clean AgentCore Memory or restore Cedar enforcement. Either leaves the box
# with someone else's residue or with denials that silently do not happen, and
# a green gate on top of that is exactly the lie this check exists to refuse.
# Only a full, successful reset removes it.
QUARANTINE_FILE="${PELLIER_QUARANTINE_FILE:-/var/lib/pellier/quarantine}"
if [[ -f "$QUARANTINE_FILE" ]]; then
  fail "Box is quarantined: $(cat "$QUARANTINE_FILE")"
  ok=false
fi

# The provisioning state file records how far bootstrap actually got:
# PROVISIONING -> APP_READY -> MANAGED_READY -> E2E_PROVED, or FAILED. In the
# governed format a box is ready only at E2E_PROVED. Bootstrap itself runs this
# gate twice before it can write that state (inside the governed reset and at
# STEP 19), and marks those runs with PELLIER_PROVISION_PHASE=bootstrap; a
# FAILED state is refused even then.
PROVISION_STATE_FILE="${PELLIER_PROVISION_STATE_FILE:-/var/lib/pellier/provision-state}"
provision_state="$(tr -d '[:space:]' 2>/dev/null < "$PROVISION_STATE_FILE" || true)"
echo "  Provision state: ${provision_state:-absent}"
if $managed_required && [[ -n "$provision_state" ]]; then
  if [[ "$provision_state" == "E2E_PROVED" ]]; then
    pass "Provisioning reached E2E_PROVED"
  elif [[ "$provision_state" != "FAILED" && "${PELLIER_PROVISION_PHASE:-}" == "bootstrap" ]]; then
    pass "Provisioning at ${provision_state} during bootstrap's own proving run"
  else
    fail "Provision state is ${provision_state}, expected E2E_PROVED. Re-run bootstrap-labs.sh; see /var/log/bootstrap-labs.log."
    ok=false
  fi
fi

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
# so /api/health alone can read green while Pellier and Pellier Observatory are blank.
# Check that / returns HTML, not that JSON note: this is what a participant
# sees in the browser. (Root cause when it fails: the frontend build failed,
# usually `npm run build` in pellier/frontend; recover with `rebuild-frontend`.)
root_body="$(curl -fs --max-time 5 "${ROOT_URL:-http://localhost:8000/}" 2>/dev/null || true)"
if echo "$root_body" | grep -qiE '<!doctype html|<div id="root"'; then
  pass "Frontend SPA built and served at / (Pellier + Pellier Observatory render)"
else
  fail "Frontend SPA not served at / - bundle missing (got: ${root_body:0:80}). Run 'rebuild-frontend' (builds pellier/frontend, restarts pellier)."
  ok=false
fi

# psql helper using env creds
_psql() {
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" \
    -X -q -tAc "$1" 2>/dev/null
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
if [[ "$wh_n" == "300" ]]; then
  pass "Warehouse inventory has exactly 300 curated rows"
else
  fail "Warehouse inventory row count is ${wh_n:-none}, expected exactly 300"
  ok=false
fi

inventory_drift="$(_psql "
/* inventory_consistency_check */
SELECT count(*)
  FROM pellier.product_catalog pc
 WHERE pc.\"productId\" ~ '^[0-9]+$'
   AND pc.\"productId\"::int BETWEEN 1 AND 100
   AND pc.quantity <> (
       SELECT COALESCE(sum(wi.quantity), 0)
         FROM pellier.warehouse_inventory wi
        WHERE wi.product_id = pc.\"productId\"
   );" || echo '')"
if [[ "$inventory_drift" == "0" ]]; then
  pass "Catalog quantity matches warehouse aggregate for all 100 curated products"
else
  fail "Catalog/warehouse inventory drift detected (${inventory_drift:-unknown} products)"
  ok=false
fi

# 3b. The governed schema. scripts/migrations/001_schema.sql builds exactly ten
# tables, the two evidence triggers, one application role and two row-level
# security policies; scripts/migrations/002_seed.sql loads the four customers
# and their orders. The labs query all of it, so a box missing any of it is not
# ready. Each query carries a /* tag */ so a reader of the log can tell them apart.
if $managed_required; then
  table_n="$(_psql "
/* schema_tables_check */
SELECT count(*) FROM pg_tables
 WHERE schemaname = 'pellier'
   AND tablename IN ('product_catalog', 'warehouse_inventory', 'customers', 'orders',
                     'return_policies', 'support_tickets', 'approvals', 'store_credits',
                     'tool_audit', 'retrieval_receipts');" || echo '')"
  if [[ "$table_n" == "10" ]]; then
    pass "The ten Pellier tables are installed"
  else
    fail "Pellier schema incomplete (${table_n:-unknown} of 10 tables). Run 'reset-governed' to rebuild it from scripts/migrations/001_schema.sql."
    ok=false
  fi

  trigger_n="$(_psql "
/* evidence_triggers_check */
SELECT count(*) FROM pg_trigger
 WHERE NOT tgisinternal
   AND tgname IN ('tool_audit_fill_once', 'retrieval_receipts_append_only',
                  'store_credits_require_approval');" || echo '')"
  if [[ "$trigger_n" == "3" ]]; then
    pass "tool_audit is fill-once, receipts are append-only, credits need an approved review"
  else
    fail "Evidence triggers missing (${trigger_n:-unknown} of 3). Run 'reset-governed'."
    ok=false
  fi

  # The role must not bypass row-level security, and both owner policies must
  # bind it, or the customer-scoped tools read every customer's rows.
  rls_n="$(_psql "
/* row_security_check */
SELECT count(*) FROM pg_policies p
  JOIN pg_roles r ON r.rolname = 'pellier_agent' AND NOT r.rolbypassrls
 WHERE p.schemaname = 'pellier'
   AND p.policyname IN ('orders_owner', 'support_tickets_owner')
   AND 'pellier_agent' = ANY (p.roles);" || echo '')"
  if [[ "$rls_n" == "2" ]]; then
    pass "Row-level security binds pellier_agent to the signed-in customer's orders and tickets"
  else
    fail "Row-level security incomplete (${rls_n:-unknown} of 2 owner policies on pellier_agent). Run 'reset-governed'."
    ok=false
  fi

  customer_n="$(_psql 'SELECT count(*) FROM pellier.customers;' || echo '')"
  if [[ "$customer_n" == "4" ]]; then
    pass "The four customers are seeded"
  else
    fail "Customer records incomplete (got: ${customer_n:-none}, expected 4)"
    ok=false
  fi

  order_n="$(_psql 'SELECT count(*) FROM pellier.orders;' || echo '')"
  if [[ "${order_n:-0}" =~ ^[0-9]+$ ]] && (( order_n >= 21 )); then
    pass "Orders queryable and fully seeded ($order_n rows)"
  else
    fail "Orders incomplete or missing (got: ${order_n:-none}, expected at least 21)"
    ok=false
  fi
fi

# 4. Node version: use the same supported LTS major as bootstrap and CI.
node_ver="$(node --version 2>/dev/null || true)"
node_major="$(echo "$node_ver" | sed 's/^v//' | cut -d. -f1)"
if [[ "$node_major" =~ ^[0-9]+$ ]] && (( node_major == 24 )); then
  pass "Node $node_ver (workshop Node 24 LTS runtime)"
else
  managed_missing "Node ${node_ver:-not found} is not the workshop's Node 24 LTS runtime. Recover: 'sudo dnf remove -y nodejs && curl -fsSL https://rpm.nodesource.com/setup_24.x | sudo bash - && sudo dnf install -y --allowerasing nodejs' then re-run bootstrap-labs.sh."
fi

# 5. Required Bedrock model access
if [[ "${BEDROCK_MODEL_ACCESS_READY:-}" == "true" ]]; then
  pass "Required Bedrock model-access preflight passed"
else
  fail "Required Bedrock model-access preflight did not pass"
  ok=false
fi

# 6. AgentCore Memory id and live SDK path
if [[ -n "${AGENTCORE_MEMORY_ID:-}" ]]; then
  pass "AGENTCORE_MEMORY_ID set"
else
  managed_missing "AGENTCORE_MEMORY_ID empty — managed Memory unavailable"
fi

memory_json="$(curl -fs --max-time 5 "${MEMORY_STATUS_URL:-http://localhost:8000/api/agentcore/memory/status}" 2>/dev/null || true)"
if echo "$memory_json" | grep -q '"live"[[:space:]]*:[[:space:]]*true' \
    && echo "$memory_json" | grep -q '"source"[[:space:]]*:[[:space:]]*"agentcore-sdk"' \
    && echo "$memory_json" | grep -q '"resource_status"[[:space:]]*:[[:space:]]*"ACTIVE"' \
    && echo "$memory_json" | grep -q '"strategies_ready"[[:space:]]*:[[:space:]]*true'; then
  pass "AgentCore Memory resource and all four strategies are ready through the SDK path"
else
  managed_missing "AgentCore Memory resource or four-strategy configuration is not ready through the SDK path (got: ${memory_json:-no response})"
fi

# 7. AgentCore Runtime endpoint and intended starting rail
if [[ -n "${AGENTCORE_RUNTIME_ENDPOINT:-}" ]]; then
  pass "AGENTCORE_RUNTIME_ENDPOINT set"
else
  managed_missing "AGENTCORE_RUNTIME_ENDPOINT empty — managed Runtime unavailable"
fi
if $managed_required; then
  if [[ "${USE_AGENTCORE_RUNTIME:-false}" == "false" ]]; then
    pass "USE_AGENTCORE_RUNTIME=false (Labs 1-2 start in-process; Lab 3 switches to the provisioned Runtime)"
  else
    pass "USE_AGENTCORE_RUNTIME=true (Lab 3 managed storefront rail selected)"
  fi
elif [[ "${USE_AGENTCORE_RUNTIME:-false}" == "true" ]]; then
  pass "USE_AGENTCORE_RUNTIME=true"
else
  warn "USE_AGENTCORE_RUNTIME is not true — the optional managed chat rail is disabled"
fi

# 8. AgentCore Gateway endpoint and ARN
if [[ -n "${AGENTCORE_GATEWAY_URL:-${MCP_GATEWAY_URL:-}}" ]]; then
  pass "AGENTCORE_GATEWAY_URL set"
else
  managed_missing "AGENTCORE_GATEWAY_URL empty — managed Gateway unavailable"
fi

if [[ -n "${AGENTCORE_GATEWAY_ARN:-${GATEWAY_ARN:-}}" ]]; then
  pass "AGENTCORE_GATEWAY_ARN set"
else
  managed_missing "AGENTCORE_GATEWAY_ARN empty — the Cedar apply helper cannot target the Gateway"
fi

# 9. Managed AgentCore Policy engine
if [[ -n "${AGENTCORE_POLICY_ENGINE_ID:-}" ]]; then
  pass "AGENTCORE_POLICY_ENGINE_ID set (managed Cedar policy attached)"
else
  managed_missing "AGENTCORE_POLICY_ENGINE_ID empty — managed Cedar enforcement unavailable. See /var/log/pellier-agentcore.log."
fi

gateway_identifier="${AGENTCORE_GATEWAY_ARN:-${GATEWAY_ARN:-}}"
gateway_identifier="${gateway_identifier##*/}"
policy_mode=""
if [[ -n "$gateway_identifier" ]] && command -v aws >/dev/null 2>&1; then
  policy_mode="$(aws bedrock-agentcore-control get-gateway \
    --gateway-identifier "$gateway_identifier" \
    --region "${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}" \
    --query 'policyEngineConfiguration.mode' \
    --output text 2>/dev/null || true)"
fi
if [[ "$policy_mode" == "ENFORCE" ]]; then
  pass "Gateway Policy is currently in ENFORCE mode"
else
  managed_missing "Gateway Policy mode is ${policy_mode:-unavailable}, expected ENFORCE"
fi

# 10. Structured provisioning receipt. This is stronger than checking env vars:
# it proves all Gateway targets were attached, Policy attached successfully, the
# authenticated Runtime smoke returned through Gateway MCP, the Runtime payload
# log group uses a customer-managed KMS key with bounded retention, and unified
# telemetry delivered agent/model/tool spans, redacted tool I/O, and step latency.
managed_receipt="${AGENTCORE_MANAGED_OUTPUT_JSON:-/tmp/pellier-agentcore-managed.json}"
participant_receipt="${AGENTCORE_PARTICIPANT_OUTPUT_JSON:-/tmp/pellier-agentcore-participant.json}"
receipt_args=("$managed_receipt")
if [[ -f "$participant_receipt" ]]; then
  receipt_args+=(--participant "$participant_receipt")
fi
receipt_validator="$SCRIPT_DIR/validate_agentcore_receipt.py"
if [[ -f "$managed_receipt" ]] && [[ -f "$receipt_validator" ]] \
    && command -v python3 >/dev/null 2>&1; then
  if receipt_error="$(python3 "$receipt_validator" "${receipt_args[@]}" 2>&1)"; then
    pass "Managed receipt proves AgentCore resources, Policy ALLOW/DENY, gateway-mcp Runtime smoke, encrypted bounded Runtime logs, and sanitized trace delivery"
  else
    managed_missing "Managed provisioning receipt is incomplete or degraded: ${receipt_error:-unknown contract failure}"
  fi
else
  managed_missing "Managed provisioning receipt, validator, or python3 unavailable: $managed_receipt"
fi

echo "------------------------------------------------------------"
# 11–12. The operator authorization group and sign-in contract.
#
# The Pellier Operator desk is authorized by membership in one Cognito group. Two failure
# modes, and both must be loud rather than latent:
#
#   group missing / operator not a member  -> the desk refuses every caller with 403
#   a SHOPPER is in the group              -> authentication is authorization again
#
# The second is the finding this check exists for. `require_operator` used to accept any
# valid token, so `marco` could confirm, decline and execute any review. A shopper
# accidentally added to the group restores exactly that, and nothing else would notice.
#
# A successful group lookup does not prove participants can sign in. The initial
# deployment used to announce READY after that lookup while a missing Hosted UI
# domain, client setting, or permanent Operator password only surfaced in a
# browser. The stack custom resource proves the CloudFront callback is
# registered; this gate proves the bootstrap half by minting a real access
# token with the Operator account and checking who Cognito says it belongs to.
if [[ -n "${COGNITO_USER_POOL_ID:-${COGNITO_POOL_ID:-}}" ]]; then
  operator_pool="${COGNITO_USER_POOL_ID:-${COGNITO_POOL_ID:-}}"
  operator_group="pellier-operators"
  operator_user="${PELLIER_OPERATOR_USERNAME:-nadia}"
  operator_client="${COGNITO_CLIENT_ID:-}"
  operator_domain="${COGNITO_DOMAIN:-}"
  operator_password="${PELLIER_OPERATOR_PASSWORD:-}"
  if [[ -z "$operator_password" && -n "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ]]; then
    operator_password="$(aws secretsmanager get-secret-value \
      --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" \
      --region "${AWS_REGION:-us-east-1}" --query SecretString --output text 2>/dev/null \
      | jq -er --arg username "$operator_user" \
        '[.users[] | select(.username == $username)] | if length == 1 then .[0].password else error("ambiguous staff credential") end' \
        2>/dev/null || true)"
  fi
  in_group() {
    local groups
    if ! groups="$(aws cognito-idp admin-list-groups-for-user \
      --user-pool-id "$operator_pool" --username "$1" \
      --region "${AWS_REGION:-us-east-1}" \
      --query "Groups[?GroupName=='${operator_group}'].GroupName" \
      --output text 2>/dev/null)"; then
      return 2
    fi
    printf '%s\n' "$groups" | grep -q "$operator_group"
  }
  if in_group "$operator_user"; then
    pass "Operator group ${operator_group} authorizes ${operator_user}"
  else
    group_status=$?
    if [[ "$group_status" == "2" ]]; then
      managed_missing "Could not verify Cognito group membership for ${operator_user}"
    else
      managed_missing "${operator_user} is not in ${operator_group} — the Operator desk refuses every caller with 403"
    fi
  fi
  shopper_in_group=""
  shopper_groups_verified=true
  for shopper in marco anna theo jessica; do
    if in_group "$shopper"; then
      shopper_in_group="$shopper_in_group $shopper"
    elif [[ "$?" == "2" ]]; then
      shopper_groups_verified=false
      managed_missing "Could not verify Cognito group membership for ${shopper}"
    fi
  done
  if [[ -n "$shopper_in_group" ]]; then
    fail "shopper(s) in ${operator_group}:${shopper_in_group} — a valid shopper token would authorize the desk"
    ok=false
  elif $shopper_groups_verified; then
    pass "No shopper is in ${operator_group}"
  fi

  if [[ -z "$operator_client" || -z "$operator_domain" ]]; then
    managed_missing "Hosted UI sign-in config incomplete: COGNITO_CLIENT_ID and COGNITO_DOMAIN are both required"
  else
    oauth_flows="$(aws cognito-idp describe-user-pool-client \
      --user-pool-id "$operator_pool" --client-id "$operator_client" \
      --region "${AWS_REGION:-us-east-1}" \
      --query 'UserPoolClient.AllowedOAuthFlows' --output text 2>/dev/null || true)"
    oauth_scopes="$(aws cognito-idp describe-user-pool-client \
      --user-pool-id "$operator_pool" --client-id "$operator_client" \
      --region "${AWS_REGION:-us-east-1}" \
      --query 'UserPoolClient.AllowedOAuthScopes' --output text 2>/dev/null || true)"
    if [[ "$oauth_flows" == *"code"* && "$oauth_scopes" == *"openid"* ]]; then
      pass "Hosted UI client is configured for OAuth authorization-code sign-in"
    else
      managed_missing "Hosted UI client must allow OAuth code flow with openid scope"
    fi

    auth_parameters="USERNAME=${operator_user},PASSWORD=${operator_password}"
    if [[ -n "${COGNITO_CLIENT_SECRET:-}" ]]; then
      secret_hash="$(python3 -c 'import sys,hmac,hashlib,base64;u,c,k=sys.argv[1:4];print(base64.b64encode(hmac.new(k.encode(),(u+c).encode(),hashlib.sha256).digest()).decode())' \
        "$operator_user" "$operator_client" "$COGNITO_CLIENT_SECRET" 2>/dev/null || true)"
      if [[ -z "$secret_hash" ]]; then
        managed_missing "Could not derive the Cognito client SECRET_HASH for Operator sign-in"
      else
        auth_parameters="${auth_parameters},SECRET_HASH=${secret_hash}"
      fi
    fi
    operator_token="$(aws cognito-idp admin-initiate-auth \
      --user-pool-id "$operator_pool" --client-id "$operator_client" \
      --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters "$auth_parameters" \
      --region "${AWS_REGION:-us-east-1}" \
      --query 'AuthenticationResult.AccessToken' --output text 2>/dev/null || true)"
    if [[ -z "$operator_token" || "$operator_token" == "None" ]]; then
      managed_missing "Seeded Operator cannot obtain a Cognito access token"
    else
      token_username="$(aws cognito-idp get-user --access-token "$operator_token" \
        --region "${AWS_REGION:-us-east-1}" --query Username --output text 2>/dev/null || true)"
      # `tr`, not `${var,,}`: the case-folding expansion is bash 4 only, and the
      # macOS test runner executes this gate under /bin/bash 3.2.
      if [[ "$(printf '%s' "$token_username" | tr '[:upper:]' '[:lower:]')" \
          == "$(printf '%s' "$operator_user" | tr '[:upper:]' '[:lower:]')" ]]; then
        pass "Seeded Operator can complete Cognito sign-in"
      else
        managed_missing "Operator access token did not resolve to ${operator_user}"
      fi
    fi
  fi

  # 13. Shopper tokens carry the customer claim. The owner-scoped Cedar permits
  # read custom:customer_id from the access token, stamped by the pre-token
  # trigger from pellier.customers.cognito_username. A detached trigger, a stale
  # mapping, or a pool plan change drops the claim silently, and every
  # owner-scoped Gateway read is then denied for the whole session while
  # sign-in itself still works. Proved the same way the Operator check is: mint
  # a real token for a seeded shopper and read the claim Cognito put in it.
  shopper_credentials=""
  if [[ -n "${COGNITO_TEST_CREDENTIALS_SECRET_ARN:-}" ]]; then
    shopper_credentials="$(aws secretsmanager get-secret-value \
      --secret-id "$COGNITO_TEST_CREDENTIALS_SECRET_ARN" \
      --region "${AWS_REGION:-us-east-1}" --query SecretString --output text 2>/dev/null || true)"
  fi
  shopper_user="$(printf '%s' "$shopper_credentials" | python3 -c 'import json,sys
d=json.load(sys.stdin); u=[x for x in d.get("users",[]) if str(x.get("username","")).lower()!=sys.argv[1].lower()]
print(u[0]["username"] if u else "")' "$operator_user" 2>/dev/null || true)"
  shopper_password="$(printf '%s' "$shopper_credentials" | python3 -c 'import json,sys
d=json.load(sys.stdin); u=[x for x in d.get("users",[]) if str(x.get("username","")).lower()!=sys.argv[1].lower()]
print(u[0]["password"] if u else "")' "$operator_user" 2>/dev/null || true)"
  if [[ -z "$shopper_user" || -z "$shopper_password" ]]; then
    managed_missing "No seeded shopper credentials; the customer claim on shopper tokens is unverified"
  else
    shopper_auth="USERNAME=${shopper_user},PASSWORD=${shopper_password}"
    if [[ -n "${COGNITO_CLIENT_SECRET:-}" ]]; then
      shopper_hash="$(python3 -c 'import sys,hmac,hashlib,base64;u,c,k=sys.argv[1:4];print(base64.b64encode(hmac.new(k.encode(),(u+c).encode(),hashlib.sha256).digest()).decode())' \
        "$shopper_user" "$operator_client" "$COGNITO_CLIENT_SECRET" 2>/dev/null || true)"
      [[ -n "$shopper_hash" ]] && shopper_auth="${shopper_auth},SECRET_HASH=${shopper_hash}"
    fi
    shopper_token="$(aws cognito-idp admin-initiate-auth \
      --user-pool-id "$operator_pool" --client-id "$operator_client" \
      --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters "$shopper_auth" \
      --region "${AWS_REGION:-us-east-1}" \
      --query 'AuthenticationResult.AccessToken' --output text 2>/dev/null || true)"
    if [[ -z "$shopper_token" || "$shopper_token" == "None" ]]; then
      managed_missing "Seeded shopper ${shopper_user} cannot obtain a Cognito access token"
    else
      shopper_claim="$(printf '%s' "$shopper_token" | python3 -c 'import sys,json,base64
p=sys.stdin.read().strip().split(".")[1]; p+="="*(-len(p)%4)
print(json.loads(base64.urlsafe_b64decode(p)).get("custom:customer_id",""))' 2>/dev/null || true)"
      # Usernames are lowercase letters; anything else never reaches the SQL.
      shopper_name="$(printf '%s' "$shopper_user" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
      mapped_customer="$(_psql "/* customer_claim_check */ SELECT id FROM pellier.customers WHERE cognito_username = '${shopper_name}';" 2>/dev/null || echo '')"
      if [[ -z "$shopper_claim" ]]; then
        managed_missing "Shopper ${shopper_user}'s access token carries no custom:customer_id; run scripts/deploy/deploy_customer_claim_trigger.py"
      elif [[ "$shopper_claim" == "$mapped_customer" ]]; then
        pass "Shopper ${shopper_user}'s access token carries custom:customer_id=${shopper_claim}, matching the mapping"
      else
        managed_missing "Shopper ${shopper_user}'s claim ${shopper_claim} does not match the mapping (${mapped_customer:-none})"
      fi
    fi
  fi
else
  managed_missing "No Cognito pool id — operator group authorization is unverified"
fi

if $ok; then
  printf "${GREEN}● READY${NC} — all required checks passed.\n"
  exit 0
else
  printf "${RED}● NOT READY${NC} — see failed checks above.\n"
  exit 1
fi
