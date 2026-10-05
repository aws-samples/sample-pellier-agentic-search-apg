#!/usr/bin/env bash
# =============================================================================
# workshop-start.sh [persona] -- open one participant's workshop
# =============================================================================
# Run once before Lab 1.
#
#   1. Check that the Pellier backend answers /api/health.
#   2. Say hello to the deployed AgentCore Runtime and record the build id it
#      reports. That is the predeployed baseline Lab 3 compares against, and it
#      puts managed execution in front of the room during orientation rather
#      than fifty minutes in. This step never fails the start: a box without a
#      token helper or a deployed Runtime is still a box that can start Lab 1.
#
# Exit status: 0 when the backend is healthy, 1 when it is not. bash 3.2 syntax
# only.
# =============================================================================
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/health}"
PERSONA="${1:-}"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}+ OK${NC}    %s\n" "$1"; }
fail() { printf "  ${RED}x FAIL${NC}  %s\n" "$1" >&2; }
warn() { printf "  ${YEL}- WARN${NC}  %s\n" "$1"; }
info() { printf "  %s\n" "$1"; }

# --- configuration: dotenv data, never executable shell --------------------
DOTENV_HELPER="${SCRIPT_DIR}/lib/dotenv.sh"
if [ ! -r "$DOTENV_HELPER" ]; then
  fail "Missing dotenv parser: $DOTENV_HELPER"
  exit 1
fi
# shellcheck source=lib/dotenv.sh
. "$DOTENV_HELPER"
if [ -f "$REPO/.env" ]; then
  pellier_load_dotenv "$REPO/.env"
elif [ -f "$REPO/pellier/backend/.env" ]; then
  pellier_load_dotenv "$REPO/pellier/backend/.env"
else
  fail "No environment file found: $REPO/.env or $REPO/pellier/backend/.env"
  exit 1
fi

if [ -n "$PERSONA" ] && ! [[ "$PERSONA" =~ ^[a-z][a-z0-9-]{0,31}$ ]]; then
  fail "persona must be a short lowercase slug (marco, anna, theo, jessica); got '$PERSONA'"
  exit 1
fi

echo "Pellier workshop start"
echo "------------------------------------------------------------"

# --- 1. the backend answers -------------------------------------------------
body="$(curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
if printf '%s' "$body" | grep -q '"status".*"healthy"'; then
  pass "Pellier backend is healthy"
else
  fail "Pellier backend is not healthy at $HEALTH_URL; run 'start-backend' and retry"
  exit 1
fi

# --- 2. one managed turn, so "deployed" is a thing they have seen ------------
RUNTIME_HELLO="$SCRIPT_DIR/runtime_hello.sh"
if [ -x "$RUNTIME_HELLO" ]; then
  echo "------------------------------------------------------------"
  echo "AgentCore Runtime hello"
  if bash "$RUNTIME_HELLO" --persona "${PERSONA:-marco}" --label baseline; then
    info "Lab 3 deploys your own build and this id changes."
  else
    warn "Runtime hello skipped. Labs 1 and 2 do not need it; Lab 3 sets it up."
  fi
fi

echo "------------------------------------------------------------"
pass "Ready for Lab 1"
exit 0
