#!/usr/bin/env bash
# =============================================================================
# lab3-start.sh [persona] -- move the storefront onto the managed rail, proved
# =============================================================================
# Labs 1 and 2 run the in-process rail so the participant proves their own
# Inventory Agent and hybrid retrieval. Lab 3 switches the storefront to the
# already-provisioned AgentCore Runtime and Gateway. This is the one command
# that does the switch and refuses to claim it happened without evidence.
#
#   1. Require AGENTCORE_GATEWAY_URL and AGENTCORE_RUNTIME_ENDPOINT (the
#      Runtime ARN) in the environment file. Either missing: refuse.
#   2. Validate the provisioning receipt with validate_agentcore_receipt.py,
#      which proves Gateway targets, Policy, and the gateway-mcp smoke.
#   3. Write USE_AGENTCORE_RUNTIME=true into /etc/pellier/run.env; fall back
#      to the repo .env when that path is not writable. That setting plus the
#      AGENTCORE_RUNTIME_ENDPOINT verified in step 1 are the only two the
#      backend reads to select a rail (services/execution_rail.py::resolve_rail).
#   4. Restart the pellier service and wait for /api/health.
#   5. Mint a Cognito token for the persona (default theo, the Lab 3 anchor)
#      unless PELLIER_TOKEN is already set, run one authenticated turn on
#      /api/chat/stream, and require the complete event's rail to read
#      gateway-mcp. Anything else exits 1 and prints the rail decision.
#
# bash 3.2 syntax only.
# =============================================================================
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
RUN_ENV_FILE="${PELLIER_RUN_ENV:-/etc/pellier/run.env}"
PYTHON="${PELLIER_PYTHON:-python3}"
BASE="${BASE_URL:-http://localhost:8000}"
HEALTH_URL="${HEALTH_URL:-$BASE/api/health}"
MANAGED_RECEIPT="${AGENTCORE_MANAGED_OUTPUT_JSON:-/tmp/pellier-agentcore-managed.json}"
PARTICIPANT_RECEIPT="${AGENTCORE_PARTICIPANT_OUTPUT_JSON:-/tmp/pellier-agentcore-participant.json}"
RECEIPT_VALIDATOR="$SCRIPT_DIR/validate_agentcore_receipt.py"
TOKEN_HELPER="${PELLIER_TOKEN_HELPER:-$HOME/pellier-token.sh}"
PERSONA="${1:-theo}"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}+ OK${NC}    %s\n" "$1"; }
fail() { printf "  ${RED}x FAIL${NC}  %s\n" "$1" >&2; }
warn() { printf "  ${YEL}- WARN${NC}  %s\n" "$1"; }
info() { printf "  %s\n" "$1"; }

DOTENV_HELPER="${SCRIPT_DIR}/lib/dotenv.sh"
if [ ! -r "$DOTENV_HELPER" ]; then
  fail "Missing dotenv parser: $DOTENV_HELPER"
  exit 1
fi
# shellcheck source=lib/dotenv.sh
. "$DOTENV_HELPER"
ENV_FILE=""
if [ -f "$REPO/.env" ]; then
  ENV_FILE="$REPO/.env"
elif [ -f "$REPO/pellier/backend/.env" ]; then
  ENV_FILE="$REPO/pellier/backend/.env"
else
  fail "No environment file found: $REPO/.env or $REPO/pellier/backend/.env"
  exit 1
fi
pellier_load_dotenv "$ENV_FILE"
if [ -f "$RUN_ENV_FILE" ]; then
  pellier_load_dotenv "$RUN_ENV_FILE"
fi

if ! [[ "$PERSONA" =~ ^[a-z][a-z0-9-]{0,31}$ ]]; then
  fail "persona must be a short lowercase slug (marco, anna, theo, jessica); got '$PERSONA'"
  exit 1
fi

# Each smoke message is that persona's shipped first storefront turn, pinned by
# frontend/src/observatory/__tests__/persona-turn-alignment.test.ts. Anna's opener
# is the morning-ritual request, not the canonical Lab 2 comparison query: that one
# is what the retrieval comparison and the eval harness measure, not what she says
# first. Keep these in step with the fixtures rather than with a lab guide.
case "$PERSONA" in
  marco)   CUSTOMER_ID="CUST-MARCO";   MESSAGE="What linen do you have for 10 days in Goa?" ;;
  anna)    CUSTOMER_ID="CUST-ANNA";    MESSAGE="A housewarming gift for someone who loves slow morning rituals." ;;
  jessica) CUSTOMER_ID="CUST-JESSICA"; MESSAGE="Which of my recent orders are still open?" ;;
  *)       CUSTOMER_ID="CUST-THEO";    MESSAGE="Hand-thrown ceramics for a slower morning routine" ;;
esac

# The mode an env file must end up with after a rewrite. bootstrap-labs.sh
# creates the repo .env 0600 because it holds DB_PASSWORD and the Cognito
# client secret; replacing it with a 0644 file would hand both to every local
# account on the code-editor box.
_env_target_mode() {
  local file="$1" mode=""
  if [ -e "$file" ]; then
    mode="$(stat -c '%a' "$file" 2>/dev/null)"
    if [ -z "$mode" ]; then
      mode="$(stat -f '%Lp' "$file" 2>/dev/null)"
    fi
  fi
  # No readable mode (new file, or a stat this box does not speak): owner only.
  case "$mode" in
    ''|*[!0-7]*) mode="600" ;;
  esac
  case "$file" in
    .env|*/.env)
      # A dotenv stays owner-readable even if it arrived wider than that.
      case "$mode" in
        *00) : ;;
        *) mode="600" ;;
      esac
      ;;
  esac
  printf '%s\n' "$mode"
}

# Replace or append KEY=value in an env file without evaluating anything,
# without widening the target's mode, and without truncating it on a read
# failure.
_upsert_env() {
  local file="$1" key="$2" value="$3" dir tmp mode status
  dir="$(dirname "$file")"
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir" 2>/dev/null || return 1
  fi
  mode="$(_env_target_mode "$file")"
  tmp="$(mktemp "$dir/.env.XXXXXX" 2>/dev/null)" || return 1
  if [ -f "$file" ]; then
    # Drop `KEY=` and the `export KEY=` form the shared dotenv parser also
    # accepts, so a stale export cannot outlive the value written below.
    grep -v -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" > "$tmp"
    status=$?
    # grep exits 1 when it filtered every line away, which a single-key file
    # legitimately does. Anything higher is a read failure, and moving the
    # near-empty temp file over the target would destroy the file.
    if [ "$status" -gt 1 ]; then
      rm -f "$tmp"
      return 1
    fi
  fi
  if ! printf '%s=%s\n' "$key" "$value" >> "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  chmod "$mode" "$tmp" 2>/dev/null
  if ! mv "$tmp" "$file"; then
    rm -f "$tmp"
    return 1
  fi
}

# Every failure below step 3 leaves the box already switched. Say so, and say
# what puts it back, rather than leaving a half-configured storefront unnamed.
_revert_hint() {
  fail "$1"
  info "Already written to $rail_target: USE_AGENTCORE_RUNTIME=true."
  info "That setting survives this failure, so the storefront keeps asking for"
  info "the managed rail on every restart."
  info "To put it back on the in-process rail, set in $rail_target:"
  info "  USE_AGENTCORE_RUNTIME=false"
  info "then run: sudo -n systemctl restart pellier"
}

_restart_service() {
  if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemctl not found; restart the backend yourself with USE_AGENTCORE_RUNTIME=true"
    return 0
  fi
  if [ "$(id -u)" -eq 0 ]; then
    systemctl restart pellier
  else
    sudo -n systemctl restart pellier
  fi
}

_wait_healthy() {
  local deadline=$(( $(date +%s) + ${1:-90} )) body
  while [ "$(date +%s)" -lt "$deadline" ]; do
    body="$(curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q '"status".*"healthy"'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

echo "Pellier Lab 3 start: managed rail"
echo "------------------------------------------------------------"

# --- 1. both managed resources, or refuse ------------------------------------
refused=false
if [ -n "${AGENTCORE_GATEWAY_URL:-}" ]; then
  pass "AGENTCORE_GATEWAY_URL set"
else
  fail "AGENTCORE_GATEWAY_URL is empty in $ENV_FILE; Gateway is not provisioned"
  refused=true
fi
if [ -n "${AGENTCORE_RUNTIME_ENDPOINT:-}" ]; then
  pass "AGENTCORE_RUNTIME_ENDPOINT (Runtime ARN) set"
else
  fail "AGENTCORE_RUNTIME_ENDPOINT is empty in $ENV_FILE; Runtime is not provisioned"
  refused=true
fi
if $refused; then
  fail "Refusing to switch rails: the storefront would degrade to in-process and call it managed"
  exit 1
fi

# --- 2. the provisioning receipt must validate --------------------------------
if [ ! -f "$MANAGED_RECEIPT" ]; then
  fail "Managed provisioning receipt not found: $MANAGED_RECEIPT"
  exit 1
fi
receipt_args=("$MANAGED_RECEIPT")
if [ -f "$PARTICIPANT_RECEIPT" ]; then
  receipt_args+=(--participant "$PARTICIPANT_RECEIPT")
fi
if receipt_error="$("$PYTHON" "$RECEIPT_VALIDATOR" "${receipt_args[@]}" 2>&1)"; then
  pass "Provisioning receipt validates (Gateway targets, Policy, gateway-mcp smoke)"
else
  fail "Provisioning receipt is incomplete: ${receipt_error:-unknown contract failure}"
  exit 1
fi

# --- 3. select the managed rail -----------------------------------------------
# resolve_rail() reads USE_AGENTCORE_RUNTIME and AGENTCORE_RUNTIME_ENDPOINT and
# nothing else. Step 1 verified the endpoint and the Gateway URL, so this one
# setting is the whole switch.
rail_target="$RUN_ENV_FILE"
if ! _upsert_env "$rail_target" "USE_AGENTCORE_RUNTIME" "true"; then
  warn "Could not write $RUN_ENV_FILE; writing the rail switch to $ENV_FILE instead"
  rail_target="$ENV_FILE"
  if ! _upsert_env "$rail_target" "USE_AGENTCORE_RUNTIME" "true"; then
    fail "Could not write the rail switch to $rail_target"
    exit 1
  fi
fi
pass "USE_AGENTCORE_RUNTIME=true in $rail_target (Runtime ARN already present)"

# --- 4. restart and wait -------------------------------------------------------
if ! _restart_service; then
  _revert_hint "'systemctl restart pellier' failed; run 'start-backend' and retry"
  exit 1
fi
if _wait_healthy 90; then
  pass "pellier service healthy on the managed rail configuration"
else
  _revert_hint "$HEALTH_URL not healthy 90s after restart; check: journalctl -u pellier"
  exit 1
fi

# --- 5. one authenticated turn, and the rail it reports -----------------------
if [ -z "${PELLIER_TOKEN:-}" ]; then
  if [ ! -r "$TOKEN_HELPER" ]; then
    _revert_hint "No PELLIER_TOKEN and no token helper at $TOKEN_HELPER; the managed rail needs a signed-in caller"
    exit 1
  fi
  # shellcheck disable=SC1090
  . "$TOKEN_HELPER" "$PERSONA" >/dev/null 2>&1 || true
fi
if [ -z "${PELLIER_TOKEN:-}" ] || [ "${PELLIER_TOKEN:-}" = "None" ]; then
  _revert_hint "Could not mint a Cognito token for '$PERSONA'; an unsigned turn cannot reach the Runtime authorizer"
  exit 1
fi
pass "Cognito token minted for $PERSONA"

SESSION_ID="lab3-start-$(date +%s)"
body="$(printf '{"message":"%s","session_id":"%s","customer_id":"%s"}' \
  "$MESSAGE" "$SESSION_ID" "$CUSTOMER_ID")"
reply="$(curl -sN --max-time 240 -X POST "$BASE/api/chat/stream" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $PELLIER_TOKEN" \
  -d "$body" 2>/dev/null || true)"
if [ -z "$reply" ]; then
  _revert_hint "No response from $BASE/api/chat/stream"
  exit 1
fi

verdict="$(printf '%s\n' "$reply" | "$PYTHON" -c '
import json, sys
rail, reason, turn_id = "", "", ""
for line in sys.stdin.read().splitlines():
    if not line.startswith("data:"):
        continue
    try:
        event = json.loads(line[5:].strip())
    except ValueError:
        continue
    if event.get("type") != "complete":
        continue
    response = event.get("response") or {}
    rail = str(response.get("rail") or "")
    turn_id = str(response.get("turn_id") or "")
    decision = response.get("railDecision") or {}
    reason = str(decision.get("reason") or (response.get("degradation") or {}).get("reason") or "")
print(rail)
print(turn_id)
print(reason)
')"
rail="$(printf '%s\n' "$verdict" | sed -n 1p)"
turn_id="$(printf '%s\n' "$verdict" | sed -n 2p)"
reason="$(printf '%s\n' "$verdict" | sed -n 3p)"

if [ "$rail" = "gateway-mcp" ]; then
  pass "Turn ${turn_id:-?} executed on rail gateway-mcp (session $SESSION_ID)"
else
  _revert_hint "Turn ${turn_id:-?} reported rail '${rail:-none}' not gateway-mcp${reason:+ (reason: $reason)}"
  info "Fix the cause and rerun this script, or revert as above."
  exit 1
fi

echo "------------------------------------------------------------"
info "Lab 3 may proceed. Theo's three turns now travel Runtime -> Gateway -> Aurora."
exit 0
