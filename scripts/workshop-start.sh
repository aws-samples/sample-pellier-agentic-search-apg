#!/usr/bin/env bash
# =============================================================================
# workshop-start.sh [persona] -- start one participant's workshop run
# =============================================================================
# Run once before Lab 1. Every evidence row the labs leave (tool_audit,
# retrieval_receipts, governed_turn_receipts, execution_receipts,
# write_operations, governed_receipts, policy_decisions) carries a run_id
# column whose DEFAULT reads the session setting pellier.run_id. The backend
# binds that setting from ~/.pellier/run_id or $PELLIER_RUN_ID on every pooled
# connection. This script mints the id and gets it in front of the service.
#
#   1. Mint ~/.pellier/run_id through services/workshop_run.py, or reuse the
#      id already there. A second invocation is a no-op on the id.
#   2. Record the run in pellier.workshop_runs (ON CONFLICT DO NOTHING).
#   3. Write PELLIER_RUN_ID to /etc/pellier/run.env for the pellier unit.
#      When that path is not writable the file fallback still reaches the
#      service, because it runs as this user and reads ~/.pellier/run_id.
#   4. Restart the pellier service so its pool binds the setting.
#   5. Say hello to the deployed AgentCore Runtime and record the build id it
#      reports. That is the predeployed baseline Lab 3 compares against, and it
#      puts managed execution in front of the room during orientation rather
#      than fifty minutes in. This step never fails the run: a box without a
#      token helper or a deployed Runtime is still a box that can start Lab 1.
#   6. Print the id.
#
# Exit status: 0 when the id is minted, recorded, and the service is back;
# 1 when the id could not be minted or recorded, or the service did not
# come back. bash 3.2 syntax only.
# =============================================================================
set -uo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PELLIER_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
RUN_ENV_FILE="${PELLIER_RUN_ENV:-/etc/pellier/run.env}"
PYTHON="${PELLIER_PYTHON:-python3}"
WORKSHOP_RUN="$REPO/pellier/backend/services/workshop_run.py"
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

_psql() {
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-postgres}" -d "${DB_NAME:-postgres}" \
    -X -q -v ON_ERROR_STOP=1 -tAc "$1"
}

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

_restart_service() {
  if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemctl not found; restart the backend yourself so its pool binds pellier.run_id"
    return 0
  fi
  if [ "$(id -u)" -eq 0 ]; then
    systemctl restart pellier
  else
    sudo -n systemctl restart pellier
  fi
}

_wait_healthy() {
  local deadline=$(( $(date +%s) + ${1:-60} )) body
  while [ "$(date +%s)" -lt "$deadline" ]; do
    body="$(curl -fs --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q '"status".*"healthy"'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

echo "Pellier workshop start"
echo "------------------------------------------------------------"

# --- 1. mint or reuse --------------------------------------------------------
RUN_ID=""
if RUN_ID="$("$PYTHON" "$WORKSHOP_RUN" current 2>/dev/null)" && [ -n "$RUN_ID" ]; then
  pass "Reusing run id $RUN_ID (already minted on this box)"
else
  if [ -n "$PERSONA" ]; then
    RUN_ID="$("$PYTHON" "$WORKSHOP_RUN" mint --persona "$PERSONA")" || RUN_ID=""
  else
    RUN_ID="$("$PYTHON" "$WORKSHOP_RUN" mint)" || RUN_ID=""
  fi
  if [ -z "$RUN_ID" ]; then
    fail "Could not mint a run id (python3 $WORKSHOP_RUN mint)"
    exit 1
  fi
  pass "Minted run id $RUN_ID"
fi
if ! [[ "$RUN_ID" =~ ^run-[0-9a-f]{12}$ ]]; then
  fail "Run id '$RUN_ID' does not match run-<12 hex>; refusing to record it"
  exit 1
fi

# --- 2. record the run -------------------------------------------------------
if [ -n "$PERSONA" ]; then
  persona_sql="'$PERSONA'"
else
  persona_sql="NULL"
fi
record_sql="INSERT INTO pellier.workshop_runs (run_id, persona)"
record_sql="$record_sql VALUES ('$RUN_ID', $persona_sql)"
record_sql="$record_sql ON CONFLICT (run_id) DO NOTHING;"
if _psql "$record_sql" >/dev/null; then
  pass "Recorded in pellier.workshop_runs"
else
  fail "Could not record the run in pellier.workshop_runs (is migration 049 applied? is Aurora reachable?)"
  exit 1
fi

# --- 3. export to the service environment ------------------------------------
if _upsert_env "$RUN_ENV_FILE" "PELLIER_RUN_ID" "$RUN_ID"; then
  pass "Wrote PELLIER_RUN_ID to $RUN_ENV_FILE"
else
  warn "Could not write $RUN_ENV_FILE; the service will read ~/.pellier/run_id instead"
fi

# --- 4. restart so the pool binds pellier.run_id -----------------------------
if _restart_service; then
  if _wait_healthy 60; then
    pass "pellier service restarted and healthy"
  else
    fail "pellier service restarted but $HEALTH_URL is not healthy after 60s"
    exit 1
  fi
else
  fail "Run id recorded, but 'systemctl restart pellier' failed; run 'start-backend' and retry"
  exit 1
fi

# --- 5. one managed turn, so "deployed" is a thing they have seen ------------
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
echo "PELLIER_RUN_ID=$RUN_ID"
info "Every evidence row this box writes from now on carries run_id = $RUN_ID."
info "Scope tooling to it with: export PELLIER_RUN_ID=$RUN_ID"
exit 0
