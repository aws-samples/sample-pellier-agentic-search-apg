#!/usr/bin/env bash
# Reset the governed two-hour Pellier workshop evidence path.
#
# Safe to re-run, and idempotent: a second run produces no semantic delta.
#
# THE LIFECYCLE, in order. Each step exists because skipping it produced a defect:
#
#   1. Quiesce the application.        Dropping the schema underneath a live turn
#                                      fails that turn half way through.
#   2. Prove nothing is executing.     No active Pellier database session.
#   3. Rebuild Aurora.                 Drop the pellier schema and build it again with
#                                      the same three steps as a fresh database, so a
#                                      reset database and a fresh one cannot differ.
#   4. Clean AgentCore Memory runtime. Aurora is not the whole workshop; preference
#                                      records are actor-scoped and outlive a session.
#   5. Restore participant AgentCore state. After a participant deploy, redeploy
#      the managed project from the restored starters (Lab 3's tool and permit
#      retired); then Lab 4's Cedar policy and live enforcement mode.
#   6. Restart the application.        On a trap, so a mid-script failure cannot leave
#                                      the box with the backend down.
#   7. Verify the baseline, then run the health gate.
#
# DOES RESET REQUIRE SERVICES TO BE STOPPED? Yes. On a workshop box this script stops
# and restarts `pellier.service` itself, so the answer costs the operator nothing. On a
# host with no such unit it refuses while a backend is listening, rather than racing.
# Four escape hatches, all explicit:
#
#   PELLIER_RESET_ALLOW_LIVE=1   proceed without quiescing (accepts the race)
#   PELLIER_BACKEND_PORT=8003    probe a different port; a governed dev stack does not
#                                run on :8000, and the default would otherwise detect an
#                                unrelated backend and refuse
#   PELLIER_RESET_SKIP_MEMORY=1  data-only reset on a box with no AWS credentials
#   PELLIER_RESET_SKIP_AGENTCORE=1  leave the control plane exactly as it is

set -euo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

REPO="${PELLIER_REPO:-/workshop/sample-pellier-agentic-search-apg}"
ENV_FILE="${REPO}/.env"
# The systemd unit's EnvironmentFile. `lab3-start.sh` writes the managed-rail
# switch here first and falls back to ENV_FILE, so a reset that clears only one
# of the two leaves the box on whichever copy it missed.
RUN_ENV_FILE="${PELLIER_RUN_ENV:-/etc/pellier/run.env}"
PYTHON="${REPO}/pellier/backend/.venv/bin/python"

GREEN='\033[32m'; RED='\033[31m'; YEL='\033[33m'; NC='\033[0m'
pass() { printf "  ${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "  ${RED}[FAIL]${NC} %s\n" "$1"; }
warn() { printf "  ${YEL}[WARN]${NC} %s\n" "$1"; }

# A workshop box has $REPO/.env, written by bootstrap and shell-safe. A local clone has
# only pellier/backend/.env, and refusing to run there sends anyone testing the reset to
# hand-rolled SQL - which is exactly how a trigger-firing manual reset gets written.
#
# The fallback is PARSED, not sourced. A dotenv file is not a shell script: a password
# containing "(" makes `source` fail with a syntax error, and a value containing "$"
# would be expanded. `declare -x "k=v"` assigns the bytes verbatim.
_load_dotenv() {
  local file="$1" line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    # Strip one matched pair of surrounding quotes, as dotenv does.
    if [[ "$value" == \"*\" && ${#value} -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && ${#value} -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    fi
    # `export k=v`, not `declare -gx`: macOS ships bash 3.2, where -g does not exist.
    # Both assign the bytes verbatim without expanding them.
    export "$key=$value"
  done < "$file"
}

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
elif [[ -f "${REPO}/pellier/backend/.env" ]]; then
  ENV_FILE="${REPO}/pellier/backend/.env"
  _load_dotenv "$ENV_FILE"
else
  fail "Missing env file: ${REPO}/.env (or pellier/backend/.env)"
  exit 1
fi

cd "$REPO"
# A WORKSHOP BOX HAS NO VENV. `bootstrap-environment.sh` installs
# `pellier/backend/requirements.lock` into the participant's `~/.local` with
# `python3.14 -m pip install --user`, and systemd runs /usr/bin/python3.14.
# The private workshop PATH alias resolves `python3` to that interpreter, with the
# same pinned botocore 1.43.51 as a developer venv. `deploy_all.sh` uses the
# same venv-first, private-PATH fallback.
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi
# Whether it resolves at all is a separate question from which path it is. `[[ -x name ]]`
# is a file test relative to the working directory and performs no PATH lookup, so
# testing the bare string "python3" is always false and would silently skip every step
# guarded by it.
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  fail "No usable Python interpreter (tried the backend venv, then python3)."
  exit 1
fi
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

# This script drops and rebuilds the pellier schema, so it must never guess which
# database to talk to. Require DB_NAME/DB_USER from the sourced .env rather
# than silently defaulting to the `postgres` maintenance database.
: "${DB_NAME:?DB_NAME is not set in $ENV_FILE — refusing to run a destructive reset against a guessed database}"
: "${DB_USER:?DB_USER is not set in $ENV_FILE — refusing to run a destructive reset against a guessed role}"

# -X on every invocation, here and in scripts/setup/database-reset.sh. A developer's
# ~/.psqlrc printed "Null display is (null). Timing is on." into the scalar reads below,
# so an in-flight count of 0 parsed as noise and the reset refused a database with nothing
# running at all. A workshop box has no .psqlrc, which is precisely why a defect like this
# only ever appears off-box.
#
# One value, no headers, no padding. The lifecycle checks below compare counts, and a
# formatted table would make every comparison a string-trimming exercise.
_psql_scalar() {
  local sql="$1"
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "$DB_USER" -d "$DB_NAME" \
    -X -v ON_ERROR_STOP=1 -t -A \
    -c "$sql"
}

# ---------------------------------------------------------------------------
# SERVICE STATE CONTRACT
#
# The reset drops and rebuilds the pellier schema. A turn in flight during the rebuild
# leaves a half-story that is worse than either outcome:
#
#   * a store credit or its tool_audit row written a moment after the rebuild, so the
#     "clean" baseline starts with one participant's residue in it;
#   * a Memory event written after the Memory leg, so the next shopper inherits it.
#
# So reset OWNS the service state: it stops the application, proves nothing is
# executing, resets, and starts it again. One box, one unit, one database. That does not
# need a distributed lock, and building one would add a failure mode the workshop does
# not have.
#
# Documented answer to "does reset require services to be stopped": YES, and the script
# does it for you where it has the authority. Where it does not (a developer clone with
# no systemd), it REFUSES rather than racing, unless PELLIER_RESET_ALLOW_LIVE=1 says the
# operator accepts the risk.
PELLIER_SERVICE="${PELLIER_SERVICE:-pellier}"
BACKEND_PORT="${PELLIER_BACKEND_PORT:-8000}"
_service_was_running=false

# Every service call goes through here. The `reset-governed` alias runs as the
# participant, not root, and the sudoers drop-in bootstrap writes permits exactly
# `systemctl start|stop|restart|is-active|status pellier` without a password. A bare
# `systemctl stop` from that account returns "Access denied", the script would treat the
# unit as already stopped, and the rebuild would run underneath a live application.
# `-n` never prompts: a missing sudoers entry fails loudly instead of hanging bootstrap.
_systemctl() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then systemctl "$@"; else sudo -n systemctl "$@"; fi
}

_have_systemd_unit() {
  # BARE systemctl on purpose, and the only bare call in this file. `list-unit-files`
  # reads unit metadata and needs no privilege; the sudoers drop-in does not name that
  # vector, and sudo matches the whole vector, so routing it through `_systemctl` gets
  # it DENIED - this function returns false on a box that has the unit, `_quiesce_services`
  # takes the no-unit branch, finds the backend listening, and the reset aborts.
  command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files "${PELLIER_SERVICE}.service" >/dev/null 2>&1
}

_backend_listening() {
  curl -fs --max-time 3 "http://localhost:${BACKEND_PORT}/api/health" >/dev/null 2>&1
}

# Restore the service even when a later step fails. Without this, one failing psql on a
# workshop box leaves the participant with a stopped backend and no message that says so.
_resume_services() {
  if [[ "$_service_was_running" == true ]]; then
    if _systemctl start "$PELLIER_SERVICE" >/dev/null 2>&1; then
      pass "Application service restarted: ${PELLIER_SERVICE}"
    else
      fail "Could not restart ${PELLIER_SERVICE}; run: sudo systemctl start ${PELLIER_SERVICE}"
    fi
    _service_was_running=false
  fi
}
trap _resume_services EXIT

_quiesce_services() {
  if _have_systemd_unit; then
    # `is-active`, not `is-active --quiet`. The sudoers drop-in grants the exact
    # vector `systemctl is-active pellier`; the flag makes it a different vector,
    # sudo denies it, and a denial reads here as "already stopped" - which is how a
    # rebuild ends up running underneath a live application. Redirect instead.
    if _systemctl is-active "$PELLIER_SERVICE" >/dev/null 2>&1; then
      if _systemctl stop "$PELLIER_SERVICE" >/dev/null 2>&1; then
        _service_was_running=true
        pass "Application quiesced: ${PELLIER_SERVICE} stopped for the reset"
      else
        fail "Could not stop ${PELLIER_SERVICE}. Reset refuses to race live writes."
        exit 1
      fi
    else
      pass "Application already stopped: ${PELLIER_SERVICE}"
    fi
    return 0
  fi

  # No unit to manage. Either nothing is serving, which is fine, or something is, which
  # is the race this contract exists to prevent.
  if ! _backend_listening; then
    pass "No application serving on :${BACKEND_PORT}; nothing to quiesce"
    return 0
  fi
  if [[ "${PELLIER_RESET_ALLOW_LIVE:-0}" == "1" ]]; then
    warn "Backend is live on :${BACKEND_PORT} and PELLIER_RESET_ALLOW_LIVE=1 was set; proceeding without quiescing"
    return 0
  fi
  fail "A backend is serving on :${BACKEND_PORT} and this host has no ${PELLIER_SERVICE}.service to stop."
  fail "Stop it first, or set PELLIER_RESET_ALLOW_LIVE=1 to accept a racing reset."
  exit 1
}

_restart_services_and_wait() {
  local attempt
  if _have_systemd_unit; then
    if ! _systemctl start "$PELLIER_SERVICE" >/dev/null 2>&1; then
      fail "Could not restart ${PELLIER_SERVICE}; the reset is not ready for a participant."
      return 1
    fi
    _service_was_running=false
    pass "Application restart requested: ${PELLIER_SERVICE}"
  elif ! _backend_listening; then
    fail "No ${PELLIER_SERVICE}.service exists and no backend is listening on :${BACKEND_PORT}."
    return 1
  fi

  for ((attempt = 1; attempt <= 30; attempt++)); do
    if _backend_listening; then
      pass "Application readiness endpoint responds on :${BACKEND_PORT}"
      return 0
    fi
    sleep 2
  done
  fail "Application did not become ready on :${BACKEND_PORT} after restart."
  return 1
}

_run_health_gate() {
  if [[ ! -x "$REPO/scripts/health-gate.sh" ]]; then
    fail "health-gate.sh missing; reset cannot claim a ready workshop."
    return 1
  fi
  echo "------------------------------------------------------------"
  PELLIER_REPO="$REPO" bash "$REPO/scripts/health-gate.sh"
}

# ---------------------------------------------------------------------------
# QUARANTINE MARKER
#
# A reset that could not clean AgentCore Memory leaves the next participant with
# someone else's preferences on their first turn. One that could not restore Cedar
# enforcement leaves denials that silently do not happen. Both used to exit 1 into a
# log nobody reads while the next `health` read green. The marker is durable: the
# health gate refuses the box while it exists, and only a full, successful reset
# removes it. /var/lib/pellier is group-writable by the participant (bootstrap sets
# root:<participant> 0775), so no sudoers line names this path; `sudo -n tee` is the
# fallback for a host that never ran bootstrap.
#
# QUARANTINE IS FOR A FAILURE, NOT FOR AN ABSENT SUBSYSTEM. A box that never
# provisioned AgentCore Memory or AgentCore Policy has no residue to clean and no
# enforcement to restore; that leg is NOT_EVALUATED, not broken. Marking such a box
# strands it, because only a full successful reset lifts the marker and that reset can
# never happen there - `health` would then fail forever. Both legs read a dedicated
# exit code for "not provisioned" and treat every other non-zero as the real failure.
QUARANTINE_FILE="${PELLIER_QUARANTINE_FILE:-/var/lib/pellier/quarantine}"
# True once the Memory leg reached a conclusion of its own: cleaned, or legitimately
# absent. False means an operator SKIPPED it, which is not a full reset, so the marker
# stays where it is.
_memory_leg_settled=false

_write_lifecycle_file() {
  local target="$1" content="$2" dir
  dir="$(dirname "$target")"
  if [[ -w "$dir" || ( -e "$target" && -w "$target" ) ]]; then
    printf '%s\n' "$content" > "$target"
  else
    printf '%s\n' "$content" | sudo -n tee "$target" >/dev/null
  fi
}

_quarantine() {
  local step="$1" reason="$2" at payload
  at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  payload="$(printf '{"reason": "%s", "step": "%s", "at": "%s"}' "$reason" "$step" "$at")"
  if _write_lifecycle_file "$QUARANTINE_FILE" "$payload" 2>/dev/null; then
    fail "Box quarantined until a full reset succeeds: $QUARANTINE_FILE"
  else
    fail "Could not write the quarantine marker at $QUARANTINE_FILE; treat this box as quarantined"
  fi
}

_clear_quarantine() {
  [[ -e "$QUARANTINE_FILE" ]] || return 0
  if rm -f "$QUARANTINE_FILE" 2>/dev/null || sudo -n rm -f "$QUARANTINE_FILE" 2>/dev/null; then
    pass "Quarantine marker cleared: $QUARANTINE_FILE"
  else
    fail "Could not clear the quarantine marker at $QUARANTINE_FILE"
    return 1
  fi
}

# Run AFTER quiescing. After it, the only sessions left are ones this script does not
# control, and the rebuild must not run underneath them.
_assert_no_active_execution() {
  local active
  active="$(_psql_scalar "
    SELECT count(*) FROM pg_stat_activity
     WHERE datname = current_database()
       AND pid <> pg_backend_pid()
       AND state = 'active'
       AND query ILIKE '%pellier.%'
       AND query NOT ILIKE '%pg_stat_activity%';
  " 2>/dev/null | tr -d '[:space:]')" || active=""
  # An unreadable probe is not quiescence. Converting a failed read into "" and
  # then reporting PASS is how a rebuild ends up running underneath a live
  # application: the one condition this function exists to rule out is exactly
  # the one an empty string cannot rule out. Refuse before mutating.
  if [[ -z "$active" ]]; then
    fail "Could not read pg_stat_activity; quiescence is unestablished, not proven."
    fail "Reset refuses to rebuild on an unverified box. Check the database connection and re-run."
    exit 1
  fi
  if [[ "$active" != "0" ]]; then
    fail "${active} database session(s) are actively running Pellier statements."
    fail "Reset refuses to rebuild underneath them. Stop the application and re-run."
    exit 1
  fi
  pass "No active Pellier database session; nothing is mid-execution"
}

# ---------------------------------------------------------------------------
# Repair, then shared restore functions.
#
# A workshop box has no git checkout, so a file a participant edited or deleted outside
# the marked regions has nothing to be restored from. repair_workshop_files.py downloads
# the revision the box was built from (.workshop-ref.json) and writes back what differs.
# It runs after the application is quiet and BEFORE the database rebuild, so the
# migrations, starters and these functions all come from the repaired tree.
#
# No network is not a reason to leave the box half reset: the repair says so and the rest
# of the reset continues from the files as they are.
_repair_workshop_files() {
  local rc=0
  if [[ ! -f "$REPO/scripts/repair_workshop_files.py" ]]; then
    warn "scripts/repair_workshop_files.py is missing, so workshop files were NOT repaired"
    return 0
  fi
  "$PYTHON" "$REPO/scripts/repair_workshop_files.py" --repo "$REPO" \
    >/tmp/pellier-governed-reset-repair.log 2>&1 || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    pass "Workshop files: $(grep -E ' file\(s\) restored to the pin' /tmp/pellier-governed-reset-repair.log | head -1)"
  elif [[ "$rc" -eq 3 ]]; then
    warn "Workshop files NOT repaired (the pinned revision was unavailable): $(tail -1 /tmp/pellier-governed-reset-repair.log)"
    warn "Continuing the reset from the files as they are"
  else
    fail "Workshop file repair failed; see /tmp/pellier-governed-reset-repair.log"
    exit 1
  fi
}

_load_restore_functions() {
  if [[ ! -f "$REPO/scripts/lib/agentcore-reset.sh" ]]; then
    fail "scripts/lib/agentcore-reset.sh is missing and the workshop files could not be repaired."
    fail "Re-run once the box can reach GitHub, or run: python3 scripts/repair_workshop_files.py"
    exit 1
  fi
  # shellcheck source=lib/agentcore-reset.sh
  . "$REPO/scripts/lib/agentcore-reset.sh"
}


echo "Pellier governed reset - $(date '+%H:%M:%S')"
echo "------------------------------------------------------------"

_quiesce_services
_assert_no_active_execution
_repair_workshop_files
_load_restore_functions
pellier_restore_execution_rail || exit 1

if ! "$PYTHON" "$REPO/scripts/reset_participant_exercises.py" \
    --repo "$REPO" >/tmp/pellier-governed-reset-exercises.log 2>&1; then
  fail "Participant exercise reset failed; see /tmp/pellier-governed-reset-exercises.log"
  exit 1
fi
pass "Labs 1-4 restored to their incomplete participant starters"

# Aurora: drop the pellier schema, then the schema, the catalog and the seed, exactly as
# a fresh database is built. scripts/setup/database-reset.sh owns that sequence; the
# fresh-setup test harness runs the same script against PostgreSQL 18 with pgvector.
if ! env DB_HOST="${DB_HOST:-localhost}" DB_PORT="${DB_PORT:-5432}" \
    DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASSWORD="${DB_PASSWORD:-}" \
    PYTHON="$PYTHON" REPO="$REPO" bash "$REPO/scripts/setup/database-reset.sh" \
    >/tmp/pellier-governed-reset-db.log 2>&1; then
  fail "Database reset failed; see /tmp/pellier-governed-reset-db.log"
  exit 1
fi
pass "Schema rebuilt from scripts/migrations/001_schema.sql: ten tables, pellier_agent and its row-level security"
pass "Catalog reloaded from the committed embedding cache"
pass "Seed reloaded: stock, four customers and their orders, return policies, tickets"
# The tables are empty again, so every lab's reset point (see workshop_check.py) is moot.
rm -f "$REPO/.local/lab-reset-points.json"

# The token claim is rendered from customers.cognito_username, the column row-level
# security reads, so it is refreshed here rather than trusted to still match. It fails
# closed: a token without the customer claim denies every owner-scoped Gateway read,
# which presents as a broken application, and only at the first shopper turn.
# Idempotent: same function, same pool.
if "$PYTHON" "$REPO/scripts/deploy/deploy_customer_claim_trigger.py" \
     >/tmp/pellier-governed-reset-claim-trigger.log 2>&1; then
  pass "Customer claim trigger matches the customers' sign-in names"
else
  fail "Customer claim trigger not refreshed — shopper tokens would carry no customer claim (see /tmp/pellier-governed-reset-claim-trigger.log)"
  _quarantine claim-trigger "Customer claim trigger not refreshed"
  exit 1
fi

# The AgentCore leg restores participant-mutated Cedar state through the CLI project,
# which means `agentcore deploy`. That is right on a workshop box a participant has been
# editing, and wrong on a deployment whose canonical policies were applied outside the
# CLI project: a deploy would push the project's declarations over them.
#
# So a DATA reset does not require control-plane authority. Set
# ---------------------------------------------------------------------------
# STEP 4: AgentCore Memory runtime state.
#
# Aurora is not the whole workshop. AgentCore Memory holds actor-scoped
# USER_PREFERENCE records under /pellier/preferences/{actorId}/, and a new session id
# does NOT isolate an actor-scoped namespace. Measured on 2026-08-27: the authenticated
# Operator subject held four preference records extracted from engineering Concierge
# runs, phrased as the operator's own tastes. A reset that left them behind hands the
# next participant someone else's client situation on their first turn.
#
# This used to be a separate manual command, which means it was a step someone had to
# remember. It is part of the lifecycle now. `reset_memory_runtime.py` preserves the
# three seeded persona actors, deletes per event and per record rather than per
# namespace, and never touches the Memory RESOURCE.
#
# Skippable, because it needs AWS credentials and a data-only reset on a box without
# them must still complete.
if [[ "${PELLIER_RESET_SKIP_MEMORY:-0}" == "1" ]]; then
  pass "AgentCore Memory runtime left untouched (PELLIER_RESET_SKIP_MEMORY=1)"
else
  _memory_rc=0
  "$PYTHON" "$REPO/scripts/reset_memory_runtime.py" --apply \
    >/tmp/pellier-governed-reset-memory.log 2>&1 || _memory_rc=$?
  if [[ "$_memory_rc" -eq 0 ]]; then
    pass "AgentCore Memory runtime cleaned; seeded persona actors preserved"
    _memory_leg_settled=true
  elif [[ "$_memory_rc" -eq 3 ]]; then
    # `reset_memory_runtime.py` reserves exit 3 for "no AGENTCORE_MEMORY_ID": a box
    # with no Memory resource, not one this script failed to clean.
    pass "AgentCore Memory not provisioned here; no runtime residue to clean"
    _memory_leg_settled=true
  else
    # Exit 2 means residue survived a completed delete pass, printed as RESIDUE
    # lines in the log; anything else is a delete that failed. Either way the box
    # is not clean.
    fail "Could not clean AgentCore Memory runtime (see /tmp/pellier-governed-reset-memory.log)"
    _quarantine memory "Could not clean AgentCore Memory runtime"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# STEP 7: baseline verification.
#
# The reset above asserts each step it performs. This asserts the RESULT, which is a
# different claim: every table the labs write to is empty, and the seeded tables hold
# exactly the dataset a fresh database holds. A reset that reported every step passing
# and left a stray review behind would otherwise look complete.
_verify_baseline() {
  local table count expected bad=0
  for table in approvals store_credits tool_audit retrieval_receipts; do
    count="$(_psql_scalar "SELECT count(*) FROM pellier.${table};" 2>/dev/null | tr -d '[:space:]')"
    if [[ "$count" != "0" ]]; then
      fail "Baseline: pellier.${table} should be empty, has ${count:-unknown}"
      bad=$((bad + 1))
    fi
  done
  for expected in product_catalog:100 warehouse_inventory:300 customers:4 orders:21 support_tickets:3; do
    table="${expected%%:*}"
    count="$(_psql_scalar "SELECT count(*) FROM pellier.${table};" 2>/dev/null | tr -d '[:space:]')"
    if [[ "$count" != "${expected##*:}" ]]; then
      fail "Baseline: pellier.${table} should hold ${expected##*:} seeded rows, has ${count:-unknown}"
      bad=$((bad + 1))
    fi
  done
  # Lab 4 starts from Jessica's two received returns with no credit on them. A stray
  # credit here makes the Operator's Planner find nothing left to propose.
  count="$(_psql_scalar "SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-JESSICA' AND return_status = 'received' AND store_credit_id IS NULL;" 2>/dev/null | tr -d '[:space:]')"
  if [[ "$count" != "2" ]]; then
    fail "Baseline: CUST-JESSICA should have two received, uncredited returns, has ${count:-unknown}"
    bad=$((bad + 1))
  fi

  if [[ "$bad" -gt 0 ]]; then
    fail "Baseline verification failed on ${bad} check(s); this reset did not land a clean state"
    return 1
  fi
  pass "Baseline verified: lab tables empty, seed intact, Jessica's case open"
}

if ! _verify_baseline; then
  exit 1
fi

# PELLIER_RESET_SKIP_AGENTCORE=1 to reset rows only and leave the control plane exactly
# as it is. The Aurora reset above has already completed either way.
if [[ "${PELLIER_RESET_SKIP_AGENTCORE:-0}" == "1" ]]; then
  pass "AgentCore control plane left untouched (PELLIER_RESET_SKIP_AGENTCORE=1)"
  _restart_services_and_wait || exit 1
  _run_health_gate || exit 1
  exit 0
fi

_quarantine_for_failed_step() {
  case "$PELLIER_RESET_FAILED_STEP" in
    starter-deploy) _quarantine starter-deploy "Could not redeploy the managed project from the starters" ;;
    policy-mode) _quarantine policy "Could not restore live Cedar enforcement mode" ;;
  esac
}

pellier_agentcore_init || exit 1
pellier_restore_lab3_agentcore || { _quarantine_for_failed_step; exit 1; }
pellier_restore_lab4_agentcore || { _quarantine_for_failed_step; exit 1; }

# Both legs that can quarantine the box have now settled - each either succeeded or
# is legitimately absent - so the marker is lifted before the gate runs; a gate that
# refused a quarantined box could otherwise never pass again. A data-only reset
# (PELLIER_RESET_SKIP_MEMORY=1) is not a full reset and leaves the marker where it is.
if [[ "$_memory_leg_settled" == true ]]; then
  _clear_quarantine
elif [[ -e "$QUARANTINE_FILE" ]]; then
  warn "Quarantine marker left in place: the Memory leg was skipped, so this was not a full reset"
fi

_restart_services_and_wait || exit 1
_run_health_gate || exit 1
