#!/usr/bin/env bash
# =============================================================================
# lab3-start.sh [--verify-only | --lab-4] [persona] -- move the storefront onto the managed rail, proved
# =============================================================================
# Labs 1 and 2 run the in-process rail so the participant proves their own
# Stock agent and hybrid retrieval. Lab 3 switches the storefront to the
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
#   5. Mint a Cognito token for the persona (default theo, the Lab 3 anchor);
#      PELLIER_TOKEN is used only where no token helper exists. Run one authenticated turn on
#      /api/chat/stream, and require the complete event's rail to read
#      gateway-mcp. Anything else exits 1 and prints the rail decision.
#
# --verify-only runs steps 1, 2 and 5 against the application that is running, and
# changes nothing: no setting is written and nothing restarts. It prints nothing on
# success and one line on failure. The participant deploy uses it before it says
# Pellier is already using AgentCore, because USE_AGENTCORE_RUNTIME=true alone
# proves only that a switch was started: step 3 writes it before the restart and
# the turn that steps 4 and 5 make. A failure sends the deploy to the full switch.
# --lab-4 performs the same full switch for a credit-rule deploy and prints that lab's context.
#
# bash 3.2 syntax only.
# =============================================================================
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

VERIFY_ONLY=false
heading="Pellier Lab 3 start: managed rail"
closing="Lab 3 may proceed. Theo's requests now travel Runtime -> Gateway -> Aurora."
case "${1:-}" in
  --verify-only) VERIFY_ONLY=true; shift ;;
  --lab-4)
    heading="Checking AgentCore for Lab 4"
    closing="The check request ran on AgentCore Runtime and Gateway."
    shift
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
RUN_ENV_FILE="${PELLIER_RUN_ENV:-/etc/pellier/run.env}"
PYTHON="${PELLIER_PYTHON:-python3}"
BASE="${BASE_URL:-http://localhost:8000}"
HEALTH_URL="${HEALTH_URL:-$BASE/api/health}"
MANAGED_RECEIPT="${AGENTCORE_MANAGED_OUTPUT_JSON:-/tmp/pellier-agentcore-managed.json}"
PARTICIPANT_RECEIPT="${AGENTCORE_PARTICIPANT_OUTPUT_JSON:-/tmp/pellier-agentcore-participant.json}"
# /tmp is memory-backed and empty after a stop/start; use the copies kept under /var/lib/pellier.
if [ ! -f "$MANAGED_RECEIPT" ] && [ -f /var/lib/pellier/managed-receipt.json ]; then
  MANAGED_RECEIPT=/var/lib/pellier/managed-receipt.json
fi
if [ ! -f "$PARTICIPANT_RECEIPT" ] && [ -f /var/lib/pellier/participant-receipt.json ]; then
  PARTICIPANT_RECEIPT=/var/lib/pellier/participant-receipt.json
fi
RECEIPT_VALIDATOR="$SCRIPT_DIR/validate_agentcore_receipt.py"
TOKEN_HELPER="${PELLIER_TOKEN_HELPER:-$HOME/pellier-token.sh}"
PERSONA="${1:-theo}"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
VERIFY_FAILURE=""
# Pellier's own plumbing checks are kept, not printed: a success prints two plain lines at the
# end, and a failure prints the checks that passed first, so the failing one reads last.
PASS_BUFFER=""
pass() { $VERIFY_ONLY || PASS_BUFFER="${PASS_BUFFER}  ${GREEN}+ OK${NC}    $1"$'\n'; }
_flush_passes() {
  if [ -n "$PASS_BUFFER" ]; then printf '%s' "$PASS_BUFFER"; fi
  PASS_BUFFER=""
}
fail() {
  $VERIFY_ONLY || _flush_passes
  if $VERIFY_ONLY; then VERIFY_FAILURE="$1"; else printf "  ${RED}x FAIL${NC}  %s\n" "$1" >&2; fi
}
warn() { $VERIFY_ONLY || { _flush_passes; printf "  ${YEL}- WARN${NC}  %s\n" "$1"; }; }
info() { $VERIFY_ONLY || { _flush_passes; printf "  %s\n" "$1"; }; }
# A verification that fails says why in one line. The full switch that follows prints the
# detail, so the participant reads the reason and then the recovery.
_verify_report() {
  local status=$?
  if $VERIFY_ONLY && [ "$status" -ne 0 ]; then
    printf "  Pellier did not answer on AgentCore (%s); running the switch again.\n" \
      "${VERIFY_FAILURE:-no reason recorded}"
  fi
}
trap _verify_report EXIT

DOTENV_HELPER="${SCRIPT_DIR}/lib/dotenv.sh"
if [ ! -r "$DOTENV_HELPER" ]; then
  fail "Missing dotenv parser: $DOTENV_HELPER"
  exit 1
fi
# shellcheck source=lib/dotenv.sh
. "$DOTENV_HELPER"
# shellcheck source=lib/progress.sh
. "${SCRIPT_DIR}/lib/progress.sh"
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

# One ordinary turn per persona. Anna's is her Lab 1 request from
# data/scenarios.json, not the canonical query the eval harness measures.
# Theo's turn states no taste: live turns write to his Memory, and a stated
# preference would be merged into his seeded record, replacing the record a
# Task 3B turn reads just before the check looks for it.
case "$PERSONA" in
  marco)   CUSTOMER_ID="CUST-MARCO";   MESSAGE="What linen do you have for 10 days in Goa?" ;;
  anna)    CUSTOMER_ID="CUST-ANNA";    MESSAGE="A housewarming gift for a friend who loves slow mornings. In stock, under \$100, and no candles." ;;
  jessica) CUSTOMER_ID="CUST-JESSICA"; MESSAGE="Which of my recent orders are still open?" ;;
  *)       CUSTOMER_ID="CUST-THEO";    MESSAGE="What is your return policy?" ;;
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

# Where the rail switch belongs. The unit loads the repo .env, then
# /etc/pellier/run.env when it exists. Workshop hosts ship no /etc/pellier, so
# the switch goes straight into the repo .env there instead of failing to
# create a root-owned directory and warning about it. A host that ships
# /etc/pellier, or a caller that names PELLIER_RUN_ENV, keeps run.env.
_rail_target() {
  local run_env="$1" env_file="$2" explicit="$3"
  if [ -n "$explicit" ] || [ -d "$(dirname "$run_env")" ]; then
    printf '%s\n' "$run_env"
  else
    printf '%s\n' "$env_file"
  fi
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

# The AgentCore data plane can answer a completed turn with an empty body (a test event, 25 Nov
# 2026). The app reports that on the stream as request_failed, the code it also gives any failure
# it does not classify (an entrypoint refusal, for one). This check turn only reads, so a
# request_failed is asked again, each time in a new session, and kept where the health gate
# reports it; nothing is printed for it. Four asks, as in the provisioner: a failure that
# persists is then reported with its code up to about a minute later rather than at once.
TURN_ASKS=4
_record_reply_retry() {
  local dir="$REPO/.agentcore-project"
  [ -d "$dir" ] || return 0
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$dir/runtime-reply-retries.log" 2>/dev/null || true
}

# Every failure below step 3 leaves the box already switched. Say so, and say
# what puts it back, rather than leaving a half-configured storefront unnamed.
_revert_hint() {
  fail "$1"
  # A verification writes no setting, so there is nothing to revert.
  $VERIFY_ONLY && return 0
  info "Already written to $rail_target: USE_AGENTCORE_RUNTIME=true."
  info "That setting survives this failure, so the storefront keeps asking for"
  info "the managed rail on every restart."
  info "To put it back on the local agents, run:"
  info "  uv run scripts/lab_run.py local"
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
  local started deadline body
  started="$(date +%s)"
  deadline=$(( started + ${1:-90} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    body="$(curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q '"status".*"healthy"'; then
      pellier_progress_clear
      return 0
    fi
    pellier_progress_draw "Waiting for Pellier to restart" 15 "$started"
    sleep 2
  done
  pellier_progress_clear
  return 1
}

if ! $VERIFY_ONLY; then
  echo "$heading"
  echo "------------------------------------------------------------"
fi

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
if [ -z "${AGENTCORE_OPERATOR_RUNTIME_ENDPOINT:-}" ]; then
  fail "AGENTCORE_OPERATOR_RUNTIME_ENDPOINT is empty; the staff Runtime is not provisioned"
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

if $VERIFY_ONLY; then
  # The running application is the evidence, so the flag in a file is not read and the
  # service is not restarted. An application that is down or still on the in-process rail
  # fails the turn in step 5.
  if ! curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -q '"status".*"healthy"'; then
    fail "$HEALTH_URL is not healthy"
    exit 1
  fi
else
  # --- 3. select the managed rail -----------------------------------------------
  # resolve_rail() reads USE_AGENTCORE_RUNTIME and AGENTCORE_RUNTIME_ENDPOINT and
  # nothing else. Step 1 verified the endpoint and the Gateway URL, so this one
  # setting is the whole switch.
  rail_target="$(_rail_target "$RUN_ENV_FILE" "$ENV_FILE" "${PELLIER_RUN_ENV:-}")"
  if ! _upsert_env "$rail_target" "USE_AGENTCORE_RUNTIME" "true"; then
    if [ "$rail_target" = "$ENV_FILE" ]; then
      fail "Could not write the rail switch to $rail_target"
      exit 1
    fi
    warn "Could not write $RUN_ENV_FILE; writing the rail switch to $ENV_FILE instead"
    rail_target="$ENV_FILE"
    if ! _upsert_env "$rail_target" "USE_AGENTCORE_RUNTIME" "true"; then
      fail "Could not write the rail switch to $rail_target"
      exit 1
    fi
  fi
  pass "USE_AGENTCORE_RUNTIME=true in $rail_target (Runtime ARN already present)"

  # --- 4. restart and wait -------------------------------------------------------
  _restart_service &
  if ! pellier_progress_wait_for "$!" "Restarting Pellier" 15; then
    _revert_hint "'systemctl restart pellier' failed; run 'start-backend' and retry"
    exit 1
  fi
  if _wait_healthy 90; then
    pass "pellier service healthy on the managed rail configuration"
  else
    _revert_hint "$HEALTH_URL not healthy 90s after restart; check: journalctl -u pellier"
    exit 1
  fi
fi

# --- 5. one authenticated turn, and the rail it reports -----------------------
# A token left in the participant's shell by `source ~/pellier-token.sh` expires after an hour
# and may belong to another shopper. Either makes this turn run unsigned, which reads below as
# an AgentCore fault, so mint one for this persona whenever the helper exists.
token_line="Cognito token minted for $PERSONA"
if [ -r "$TOKEN_HELPER" ]; then
  # shellcheck disable=SC1090
  . "$TOKEN_HELPER" "$PERSONA" >/dev/null 2>&1 || true
elif [ -z "${PELLIER_TOKEN:-}" ]; then
  _revert_hint "No PELLIER_TOKEN and no token helper at $TOKEN_HELPER; the managed rail needs a signed-in caller"
  exit 1
else
  token_line="No token helper at $TOKEN_HELPER; using the PELLIER_TOKEN supplied"
fi
if [ -z "${PELLIER_TOKEN:-}" ] || [ "${PELLIER_TOKEN:-}" = "None" ]; then
  _revert_hint "Could not mint a Cognito token for '$PERSONA'; an unsigned turn cannot reach the Runtime authorizer"
  exit 1
fi
pass "$token_line"

for ask in $(seq 1 "$TURN_ASKS"); do
  SESSION_ID="lab3-start-$(date +%s)-$ask"
  body="$(printf '{"message":"%s","session_id":"%s","customer_id":"%s"}' \
    "$MESSAGE" "$SESSION_ID" "$CUSTOMER_ID")"
  reply_file="$(mktemp "${TMPDIR:-/tmp}/pellier-lab3-start.XXXXXX")"
  curl -sN --max-time 240 -X POST "$BASE/api/chat/stream" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $PELLIER_TOKEN" \
    -d "$body" >"$reply_file" 2>/dev/null &
  pellier_progress_wait_for "$!" "Running one turn on AgentCore" 15 || true
  reply="$(cat "$reply_file")"
  rm -f "$reply_file"
  if [ -z "$reply" ]; then
    _revert_hint "No response from $BASE/api/chat/stream"
    exit 1
  fi

  verdict="$(printf '%s\n' "$reply" | "$PYTHON" -c '
import json, sys
rail, reason, turn_id, error = "", "", "", ""
for line in sys.stdin.read().splitlines():
    if not line.startswith("data:"):
        continue
    try:
        event = json.loads(line[5:].strip())
    except ValueError:
        continue
    if event.get("type") == "error":
        error = str(event.get("code") or "error")
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
print(error)
')"
  rail="$(printf '%s\n' "$verdict" | sed -n 1p)"
  turn_id="$(printf '%s\n' "$verdict" | sed -n 2p)"
  reason="$(printf '%s\n' "$verdict" | sed -n 3p)"
  error_code="$(printf '%s\n' "$verdict" | sed -n 4p)"
  if [ "$rail" = "gateway-mcp" ] || [ "$error_code" != "request_failed" ] || [ "$ask" -eq "$TURN_ASKS" ]; then
    break
  fi
  _record_reply_retry "lab3-start check turn, ask $ask of $TURN_ASKS, session $SESSION_ID: request_failed"
  sleep 10
done

if [ "$rail" = "gateway-mcp" ]; then
  pass "Turn ${turn_id:-?} executed on rail gateway-mcp (session $SESSION_ID)"
else
  _revert_hint "Turn ${turn_id:-?} reported rail '${rail:-none}' not gateway-mcp${reason:+ (reason: $reason)}${error_code:+ (error: $error_code)}"
  info "Fix the cause and rerun this script, or revert as above."
  exit 1
fi

if ! $VERIFY_ONLY; then
  PASS_BUFFER=""
  persona_name="$(printf '%s' "$PERSONA" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')"
  printf "  ${GREEN}+${NC} Pellier is set up for AgentCore: Gateway and Runtime found, deploy receipt checked.\n"
  printf "  ${GREEN}+${NC} Pellier is running on AgentCore. A test turn as %s went through the Gateway.\n" \
    "$persona_name"
  echo "------------------------------------------------------------"
fi
info "$closing"
exit 0
