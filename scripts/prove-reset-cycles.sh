#!/usr/bin/env bash
# Two-cycle reset proof: reset, journey smoke, reset, journey smoke.
#
# One successful reset proves the reset works on whatever state the box happened to be
# in. Two prove it works on the state a workshop leaves behind: the smoke turn between
# them writes tool_audit rows, a retrieval receipt, Memory events and a conversation,
# which is exactly what the second reset has to clear. Exit 1 on any failure; the
# last line for a passing cycle is `CYCLE n PASS`.
#
# The journey smoke is:
#   1. validate_agentcore_receipt.py over the provisioning receipt, so the managed
#      Runtime, Gateway, Memory and Policy proof still holds after the reset;
#   2. one authenticated /api/chat turn with the first seeded shopper from the
#      participant credentials file (write-test-credentials.sh output).
#
# Usage: bash scripts/prove-reset-cycles.sh
#   PELLIER_REPO                   repo root (default /workshop/sample-pellier-agentic-search-apg)
#   PELLIER_TEST_CREDENTIALS       credentials file (default $HOME_FOLDER/test-credentials.txt)
#   AGENTCORE_MANAGED_OUTPUT_JSON  provisioning receipt (default /tmp/pellier-agentcore-managed.json)
#   PELLIER_BACKEND_PORT           backend port (default 8000)
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
HOME_FOLDER="${HOME_FOLDER:-/workshop}"
CREDENTIALS_FILE="${PELLIER_TEST_CREDENTIALS:-$HOME_FOLDER/test-credentials.txt}"
MANAGED_RECEIPT="${AGENTCORE_MANAGED_OUTPUT_JSON:-/tmp/pellier-agentcore-managed.json}"
BACKEND_PORT="${PELLIER_BACKEND_PORT:-8000}"
BASE_URL="http://localhost:${BACKEND_PORT}"
# The canonical Anna query: retrieval with a price and stock constraint, so the turn
# exercises hybrid search, the inventory tool and the receipt writers the reset clears.
SMOKE_MESSAGE='A housewarming gift under $100 that is currently in stock.'

GREEN='\033[32m'; RED='\033[31m'; NC='\033[0m'
pass() { printf "  ${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "  ${RED}[FAIL]${NC} %s\n" "$1"; }

# Cognito settings come from the same dotenv the health gate reads, parsed rather
# than sourced: a generated secret is data, not shell.
DOTENV_HELPER="${SCRIPT_DIR}/lib/dotenv.sh"
if [[ ! -r "$DOTENV_HELPER" ]]; then
  fail "Missing dotenv parser: $DOTENV_HELPER"
  exit 1
fi
# shellcheck source=lib/dotenv.sh
source "$DOTENV_HELPER"
if [[ -f "${REPO}/.env" ]]; then
  pellier_load_dotenv "${REPO}/.env"
elif [[ -f "${REPO}/pellier/backend/.env" ]]; then
  pellier_load_dotenv "${REPO}/pellier/backend/.env"
else
  fail "Missing env file: ${REPO}/.env (or pellier/backend/.env)"
  exit 1
fi
export PELLIER_REPO="$REPO"

# Prints the token on stdout, so every diagnostic here goes to stderr: the caller
# captures stdout, and a failure message captured as the token is a confusing 401.
_mint_token() {
  local username password pool client auth_parameters secret_hash token
  username="$(sed -n 's/^Username: //p' "$CREDENTIALS_FILE" 2>/dev/null | head -1)"
  password="$(sed -n 's/^Password: //p' "$CREDENTIALS_FILE" 2>/dev/null | head -1)"
  if [[ -z "$username" || -z "$password" ]]; then
    fail "No Username/Password pair in $CREDENTIALS_FILE (write-test-credentials.sh output)" >&2
    return 1
  fi
  pool="${COGNITO_USER_POOL_ID:-${COGNITO_POOL_ID:-}}"
  client="${COGNITO_CLIENT_ID:-}"
  if [[ -z "$pool" || -z "$client" ]]; then
    fail "COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID are required to mint a shopper token" >&2
    return 1
  fi
  auth_parameters="USERNAME=${username},PASSWORD=${password}"
  if [[ -n "${COGNITO_CLIENT_SECRET:-}" ]]; then
    secret_hash="$(python3 -c 'import sys,hmac,hashlib,base64;u,c,k=sys.argv[1:4];print(base64.b64encode(hmac.new(k.encode(),(u+c).encode(),hashlib.sha256).digest()).decode())' \
      "$username" "$client" "$COGNITO_CLIENT_SECRET" 2>/dev/null)"
    if [[ -z "$secret_hash" ]]; then
      fail "Could not derive the Cognito client SECRET_HASH for $username" >&2
      return 1
    fi
    auth_parameters="${auth_parameters},SECRET_HASH=${secret_hash}"
  fi
  token="$(aws cognito-idp admin-initiate-auth \
    --user-pool-id "$pool" --client-id "$client" \
    --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters "$auth_parameters" \
    --region "${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}" \
    --query 'AuthenticationResult.AccessToken' --output text 2>/dev/null)"
  if [[ -z "$token" || "$token" == "None" ]]; then
    fail "Seeded shopper $username cannot obtain a Cognito access token" >&2
    return 1
  fi
  printf '%s' "$token"
}

_smoke_turn() {
  local cycle="$1" token session body reply
  token="$(_mint_token)" || return 1
  session="reset-proof-cycle-${cycle}-$(date +%s)"
  body="$(python3 -c 'import json,sys;print(json.dumps({"message": sys.argv[1], "session_id": sys.argv[2]}))' \
    "$SMOKE_MESSAGE" "$session")"
  if ! reply="$(curl -fs --max-time 120 -X POST "${BASE_URL}/api/chat" \
      -H "Authorization: Bearer ${token}" \
      -H 'Content-Type: application/json' -d "$body" 2>/dev/null)"; then
    fail "Authenticated /api/chat turn failed (session ${session})"
    return 1
  fi
  if printf '%s' "$reply" | python3 -c 'import json,sys;d=json.load(sys.stdin);sys.exit(0 if d.get("success", True) and str(d.get("response", "")).strip() else 1)' 2>/dev/null; then
    pass "Authenticated /api/chat turn answered (session ${session})"
  else
    fail "Authenticated /api/chat turn returned no answer (first 200: ${reply:0:200})"
    return 1
  fi
}

run_cycle() {
  local cycle="$1"
  echo "============================================================"
  echo "CYCLE ${cycle}: reset"
  echo "============================================================"
  if ! bash "$REPO/scripts/reset-governed-workshop.sh"; then
    fail "CYCLE ${cycle}: reset exited non-zero"
    return 1
  fi
  echo "------------------------------------------------------------"
  echo "CYCLE ${cycle}: journey smoke"
  if python3 "$REPO/scripts/validate_agentcore_receipt.py" "$MANAGED_RECEIPT"; then
    pass "Managed provisioning receipt still validates: $MANAGED_RECEIPT"
  else
    fail "CYCLE ${cycle}: managed provisioning receipt failed validation"
    return 1
  fi
  _smoke_turn "$cycle" || return 1
  echo "CYCLE ${cycle} PASS"
}

run_cycle 1 || exit 1
run_cycle 2 || exit 1
pass "Both reset cycles passed: the reset clears the state a workshop leaves behind"
exit 0
