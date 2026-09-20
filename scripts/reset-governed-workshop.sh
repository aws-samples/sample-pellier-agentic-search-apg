#!/usr/bin/env bash
# Reset the governed two-hour Pellier workshop evidence path.
#
# Safe to re-run, and idempotent: a second run produces no semantic delta.
#
# THE LIFECYCLE, in order. Each step exists because skipping it produced a defect:
#
#   1. Quiesce the application.        A truncate underneath a live turn can clear an
#                                      idempotency claim after its write committed.
#   2. Prove nothing is executing.     No active Pellier database session.
#   3. Reset Aurora runtime state.     TRUNCATE, never DELETE: DELETE fires the ledger
#                                      and receipt-immutability triggers, writing new
#                                      history while trying to clear history.
#   4. Clean AgentCore Memory runtime. Aurora is not the whole workshop; preference
#                                      records are actor-scoped and outlive a session.
#   5. Restore participant Cedar state through the CLI project.
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
# `pip install --user`, and the systemd unit runs the ambient interpreter. So `python3`
# there IS the validated interpreter, carrying the same pinned botocore 1.43.51 as a
# developer venv. Do not "fix" this fallback away: `deploy_all.sh` resolves it the same
# way for the same reason.
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

# This script TRUNCATEs the evidence tables, so it must never guess which
# database to talk to. Require DB_NAME/DB_USER from the sourced .env rather
# than silently defaulting to the `postgres` maintenance database.
: "${DB_NAME:?DB_NAME is not set in $ENV_FILE — refusing to run a destructive reset against a guessed database}"
: "${DB_USER:?DB_USER is not set in $ENV_FILE — refusing to run a destructive reset against a guessed role}"

# -X on every invocation. A developer's ~/.psqlrc printed "Null display is (null). Timing
# is on." into the scalar reads below, so an in-flight count of 0 parsed as noise and the
# reset refused a database with nothing running at all. A workshop box has no .psqlrc,
# which is precisely why a defect like this only ever appears off-box.
_psql_file() {
  local file="$1"
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "$DB_USER" -d "$DB_NAME" \
    -X -v ON_ERROR_STOP=1 \
    -f "$file"
}

_psql_exec() {
  local sql="$1"
  PGPASSWORD="${DB_PASSWORD:-}" psql \
    -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
    -U "$DB_USER" -d "$DB_NAME" \
    -X -v ON_ERROR_STOP=1 \
    -c "$sql"
}

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
# The reset TRUNCATEs the evidence and runtime tables. Postgres will not corrupt
# anything while the application is running, but "not corrupt" is not the property this
# workshop needs. A turn in flight during the truncate can leave a half-story that is
# worse than either outcome:
#
#   * a `write_operations` idempotency claim cleared after its domain write committed,
#     so a replay applies the effect a second time;
#   * an `approvals` row cleared after the execution it authorized, so an execution
#     receipt references a review that no longer exists;
#   * a conversation or Memory event written a moment after the truncate, so the
#     "clean" baseline starts with one shopper's residue in it.
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
# unit as already stopped, and the TRUNCATE would run underneath a live application.
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
    # TRUNCATE ends up running underneath a live application. Redirect instead.
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

# Run AFTER quiescing. Before that, an unfinished claim may be a live execution; after
# it, the only sessions left are ones this script does not control, and an unfinished
# claim is residue that the TRUNCATE correctly clears.
_assert_no_active_execution() {
  local active claims recovery_installed recovery_records
  active="$(_psql_scalar "
    SELECT count(*) FROM pg_stat_activity
     WHERE datname = current_database()
       AND pid <> pg_backend_pid()
       AND state = 'active'
       AND query ILIKE '%pellier.%'
       AND query NOT ILIKE '%pg_stat_activity%';
  " 2>/dev/null | tr -d '[:space:]')" || active=""
  # An unreadable probe is not quiescence. Converting a failed read into "" and
  # then reporting PASS is how a truncate ends up running underneath a live
  # application: the one condition this function exists to rule out is exactly
  # the one an empty string cannot rule out. Refuse before mutating.
  if [[ -z "$active" ]]; then
    fail "Could not read pg_stat_activity; quiescence is unestablished, not proven."
    fail "Reset refuses to truncate on an unverified box. Check the database connection and re-run."
    exit 1
  fi
  if [[ "$active" != "0" ]]; then
    fail "${active} database session(s) are actively running Pellier statements."
    fail "Reset refuses to truncate underneath them. Stop the application and re-run."
    exit 1
  fi
  pass "No active Pellier database session; nothing is mid-execution"

  claims="$(_psql_scalar "
    SELECT count(*) FROM pellier.write_operations WHERE completed_at IS NULL;
  " 2>/dev/null | tr -d '[:space:]')" || claims=""
  if [[ -z "$claims" ]]; then
    fail "Could not count unfinished idempotency claims; this box's write state is unknown."
    exit 1
  fi
  if [[ "$claims" != "0" ]]; then
    warn "${claims} idempotency claim(s) never completed. They are interrupted residue and the reset clears them."
  else
    pass "No unfinished idempotency claim"
  fi

  # A quiet database does not quiesce a scheduled Lambda or a waiting Standard
  # execution. This local reset cannot retire their durable operation identity.
  recovery_installed="$(_psql_scalar "
    SELECT to_regclass('pellier.replacements') IS NOT NULL;
  " 2>/dev/null | tr -d '[:space:]')" || recovery_installed=""
  if [[ "$recovery_installed" == "t" ]]; then
    recovery_records="$(_psql_scalar "
      SELECT count(*) FROM pellier.replacements;
    " 2>/dev/null | tr -d '[:space:]')" || recovery_records=""
    if [[ "$recovery_records" != "0" ]]; then
      fail "Replacement recovery records exist or could not be counted."
      fail "This reset cannot quiesce the recovery worker and Step Functions executions."
      fail "Preserve their records and use a fresh workshop deployment."
      exit 1
    fi
  elif [[ "$recovery_installed" != "f" ]]; then
    fail "Could not establish whether replacement recovery is installed; reset refused."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Restore the STARTING execution path.
#
# `lab3-start.sh` switches the storefront onto the managed Runtime by writing
# USE_AGENTCORE_RUNTIME=true (run.env first, ENV_FILE on fallback), and
# `services/execution_rail.py::resolve_rail` reads that setting and nothing
# else. A reset that restores Lab 1's starter code but leaves the switch on
# hands the next participant a box where their local edit cannot change the
# answer: the storefront keeps executing the previously deployed Runtime
# package. Source state and execution state are two different resets, and this
# is the second one.
_env_declares_managed_rail() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  grep -qiE '^[[:space:]]*(export[[:space:]]+)?USE_AGENTCORE_RUNTIME[[:space:]]*=[[:space:]]*"?(1|true|yes|on)"?[[:space:]]*$' "$file"
}

# Same contract as lab3-start.sh's `_upsert_env`: never evaluate, never widen the
# mode, never truncate on a read failure. Falls back to `sudo -n` because run.env
# lives under /etc and a participant shell may not own it.
_reset_upsert_env() {
  local file="$1" key="$2" value="$3" dir tmp status
  dir="$(dirname "$file")"
  [[ -d "$dir" ]] || mkdir -p "$dir" 2>/dev/null || sudo -n mkdir -p "$dir" 2>/dev/null || return 1
  tmp="$(mktemp "${TMPDIR:-/tmp}/pellier-env.XXXXXX")" || return 1
  if [[ -f "$file" ]]; then
    grep -v -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" > "$tmp"
    status=$?
    if [[ "$status" -gt 1 ]]; then rm -f "$tmp"; return 1; fi
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp" || { rm -f "$tmp"; return 1; }
  chmod 600 "$tmp" 2>/dev/null
  if cat "$tmp" > "$file" 2>/dev/null; then rm -f "$tmp"; return 0; fi
  if sudo -n tee "$file" < "$tmp" >/dev/null 2>&1; then
    sudo -n chmod 600 "$file" 2>/dev/null
    rm -f "$tmp"; return 0
  fi
  rm -f "$tmp"; return 1
}

_restore_execution_rail() {
  local file restored=0
  for file in "$RUN_ENV_FILE" "$ENV_FILE"; do
    [[ -f "$file" ]] || continue
    if ! _reset_upsert_env "$file" "USE_AGENTCORE_RUNTIME" "false"; then
      fail "Could not clear USE_AGENTCORE_RUNTIME in ${file}."
      fail "The next participant would edit Lab 1 locally while the storefront answered from the deployed Runtime."
      exit 1
    fi
    restored=$((restored + 1))
  done
  # Assert the RESULT, not the writes. A file this script never saw -- an
  # operator's own copy, a path override -- would otherwise pass silently.
  for file in "$RUN_ENV_FILE" "$ENV_FILE"; do
    if _env_declares_managed_rail "$file"; then
      fail "Baseline: ${file} still enables the managed rail after the reset wrote to it"
      exit 1
    fi
  done
  if [[ "$restored" -eq 0 ]]; then
    warn "No env file found at $RUN_ENV_FILE or $ENV_FILE; execution rail left as configured"
  else
    pass "Execution rail restored to in-process (USE_AGENTCORE_RUNTIME=false in ${restored} file(s))"
  fi
}

# `workshop_runs` is truncated below, so the run id cached on disk names a run
# the database no longer has. Leaving it makes every later evidence query scope
# to an id with no rows and report NOT YET for work that was really done.
# `workshop-start` mints a fresh one.
_clear_local_run_state() {
  local f cleared=0
  for f in "$HOME/.pellier/run_id" "$HOME/.pellier/run_persona"; do
    [[ -e "$f" ]] || continue
    if rm -f "$f" 2>/dev/null; then cleared=$((cleared + 1)); else
      fail "Could not clear stale run state at $f"
      exit 1
    fi
  done
  if [[ "$cleared" -gt 0 ]]; then
    pass "Stale local run state cleared; workshop-start will mint a fresh run id"
  else
    pass "No stale local run state to clear"
  fi
}

echo "Pellier governed reset - $(date '+%H:%M:%S')"
echo "------------------------------------------------------------"

_quiesce_services
_assert_no_active_execution
_restore_execution_rail
_clear_local_run_state

if ! "$PYTHON" "$REPO/scripts/reset_participant_exercises.py" \
    --repo "$REPO" >/tmp/pellier-governed-reset-exercises.log 2>&1; then
  fail "Participant exercise reset failed; see /tmp/pellier-governed-reset-exercises.log"
  exit 1
fi
pass "Labs 1-4 restored to their incomplete participant starters"

if ! "$PYTHON" "$REPO/scripts/seed_pellier_catalog.py" \
    --from-cache >/tmp/pellier-governed-reset-catalog.log 2>&1; then
  fail "Deterministic catalog reset failed; see /tmp/pellier-governed-reset-catalog.log"
  exit 1
fi
pass "Catalog quantities restored from committed embedding cache"

for migration in \
  006_warehouse_inventory.sql \
  011_governed_write_integrity.sql \
  012_retrieval_receipts.sql \
  013_inventory_ledger.sql \
  014_governed_turn_receipts.sql \
  015_proof_carrying_commerce.sql \
  016_runtime_roles_rls.sql \
  017_governed_query_receipts.sql \
  018_client_book.sql \
  019_operator_desk.sql \
  020_operator_review.sql \
  021_governed_execution.sql \
  022_write_operation_vocabulary.sql \
  023_idempotency_claims_release_on_failure.sql \
  024_operator_episodes.sql \
  025_execution_receipts.sql \
  026_episode_outcome_lineage.sql \
  027_canonical_span_table.sql \
  028_shopper_operator_handoff.sql \
  029_live_surface_data.sql \
  030_storefront_editorial_order.sql \
  031_refine_fresh_storefront_edit.sql \
  032_restore_fresh_runner_edit.sql \
  033_extend_curated_inventory.sql \
  034_refine_persona_personalities.sql \
  035_expand_persona_discovery_grids.sql \
  036_refresh_persona_hero_alt_text.sql \
  037_serve_persona_hero_masters.sql \
  038_principal_customer_cardinality.sql \
  039_return_replay_scope.sql \
  040_resequence_theo_governed_turn.sql \
  041_align_theo_pairing_preview.sql \
  042_align_anna_guided_previews.sql \
  043_evidence_ledger.sql \
  044_operator_lifecycle_ledger.sql \
  045_persona_blurbs.sql \
  046_retrieval_citation_snapshots.sql \
  047_evidence_immutability.sql \
  048_policy_decisions.sql \
  049_workshop_runs.sql \
  050_refine_guided_questions.sql \
  051_review_requester.sql \
  052_replacement_recovery.sql \
  053_replacement_follow_up.sql \
  054_query_statistics.sql \
  055_governance_boundary_observations.sql
do
  if [[ ! -f "$REPO/scripts/migrations/$migration" ]]; then
    fail "Missing scripts/migrations/$migration"
    exit 1
  fi
  _psql_file "$REPO/scripts/migrations/$migration" \
    >>/tmp/pellier-governed-reset-db.log
done
pass "Exactly three warehouse rows per curated product reseeded"

_psql_exec "
TRUNCATE TABLE
    -- The guard above requires these to be empty. Naming every child keeps
    -- TRUNCATE referentially complete without CASCADE or a cloud-workflow reset.
    pellier.replacement_callbacks,
    pellier.replacement_simulator_operations,
    pellier.replacement_events,
    pellier.replacement_outbox,
    pellier.replacements,
    pellier.commerce_payment_events,
    pellier.commerce_receipts,
    pellier.commerce_outbox,
    pellier.commerce_inventory_reservations,
    pellier.commerce_payment_attempts,
    pellier.commerce_order_lines,
    pellier.commerce_orders,
    pellier.commerce_confirmation_grants,
    pellier.commerce_quote_lines,
    pellier.commerce_quotes,
    pellier.governed_receipts,
    pellier.governed_turn_receipts,
    pellier.governed_query_receipts,
    pellier.model_invocation_receipts,
    pellier.tool_audit,
    pellier.retrieval_receipts,
    pellier.inventory_ledger,
    pellier.write_operations,
    pellier.returns,
    pellier.store_credits,
    pellier.support_tickets,
    pellier.semantic_cache,
    -- Evidence and memory tables added after this script was first written. Each was
    -- absent from the list, so a reset cluster kept rows a fresh one has never had:
    --   execution_receipts  policy verdicts from engineering runs (migration 025)
    --   operator_episodes   derived memories of those runs (024/026)
    --   conversations       shopper AND Operator Concierge threads (007). Nothing
    --   messages            seeds these, so the fresh baseline is zero and every row
    --                       here is runtime state.
    --   observatory_spans   OTEL spans (002)
    --   session_metadata    per-session scratch (007)
    --   tool_uses           per-turn tool records (007)
    pellier.execution_receipts,
    pellier.operator_episodes,
    pellier.messages,
    pellier.conversations,
    pellier.observatory_spans,
    pellier.session_metadata,
    -- Persona profiles and workshop scenarios are provisioned source data.
    -- Shopper sessions are runtime state and must not survive a reset.
    pellier.shopper_sessions,
    pellier.tool_uses,
    -- Per-run evidence added by 048 and 049. Gateway Policy decision events are
    -- ingested per turn and a workshop run is minted per participant, so a fresh
    -- box has neither. (No semicolon in this comment: the contract test reads
    -- the statement up to the first one.)
    pellier.policy_decisions,
    pellier.governance_boundary_observations,
    pellier.workshop_runs,
    -- LAST in the list, because execution_receipts and operator_episodes reference it.
    -- One TRUNCATE covers them together, so no CASCADE is needed and nothing is
    -- orphaned. TRUNCATE also fires no row-level triggers: a DELETE here would run
    -- record_inventory_movement and reject_governed_turn_receipt_mutation, writing
    -- new ledger history while trying to clear history.
    pellier.approvals
RESTART IDENTITY;
" >/tmp/pellier-governed-reset-evidence.log
pass "Cleared: returns, stock movements, write keys, audits, receipts, episodes, conversations, spans, and operator reviews"

_psql_file "$REPO/scripts/migrations/013_inventory_ledger.sql" \
  >>/tmp/pellier-governed-reset-db.log
pass "Inventory ledger reseeded from deterministic warehouse state"

# 019 is re-applied after the TRUNCATE above for the same reason 013 and 015
# are: the truncate empties the operator desk, and the seeded tickets plus
# Sarah's credit on file are the starting state the client book describes. The
# semantic cache is deliberately left empty, so the first paraphrase of the
# run is a real miss and the second is a real hit.
_psql_file "$REPO/scripts/migrations/019_operator_desk.sql" \
  >>/tmp/pellier-governed-reset-db.log
pass "Operator desk reseeded: support tickets, credit on file, empty semantic cache"

# Row-Level Security authorization mapping.
#
# `pellier.principal_customers` is authorization configuration, not turn
# evidence, so it is deliberately absent from the TRUNCATE above. It still
# gets verified here: an empty mapping denies every signed-in shopper their
# own orders, which presents as a broken application rather than as
# governance, and reset is where a deterministic starting state is asserted.
# Both identity steps fail closed. A warning here used to let the reset report a
# healthy box while every signed-in shopper was denied their own rows (empty
# mapping) or every owner-scoped Gateway read was denied (token without the
# customer claim). Neither presents as governance; both present as a broken
# application, and only at the first shopper turn.
if "$PYTHON" "$REPO/scripts/seed_principal_mappings.py" --check \
     >/tmp/pellier-governed-reset-principals.log 2>&1; then
  pass "RLS principal mappings intact for every named shopper"
else
  fail "RLS principal mappings incomplete — run scripts/seed_principal_mappings.py (see /tmp/pellier-governed-reset-principals.log)"
  _quarantine principal-mappings "RLS principal mappings incomplete"
  exit 1
fi

# The token claim is rendered from the same table, so it is refreshed here
# rather than trusted to still match. Idempotent: same function, same pool.
if "$PYTHON" "$REPO/scripts/deploy/deploy_customer_claim_trigger.py" \
     >/tmp/pellier-governed-reset-claim-trigger.log 2>&1; then
  pass "Customer claim trigger matches the principal mappings"
else
  fail "Customer claim trigger not refreshed — shopper tokens would carry no customer claim (see /tmp/pellier-governed-reset-claim-trigger.log)"
  _quarantine claim-trigger "Customer claim trigger not refreshed"
  exit 1
fi

_psql_file "$REPO/scripts/migrations/015_proof_carrying_commerce.sql" \
  >>/tmp/pellier-governed-reset-db.log
pass "Proof-carrying commerce lifecycle restored"

if [[ ! -f "$REPO/scripts/migrations/010_governed_receipts.sql" ]]; then
  fail "Missing scripts/migrations/010_governed_receipts.sql"
  exit 1
fi
_psql_file "$REPO/scripts/migrations/010_governed_receipts.sql" \
  >>/tmp/pellier-governed-reset-db.log
pass "Canonical governed forensic incident reseeded"

_psql_exec '
CREATE INDEX IF NOT EXISTS product_catalog_embedding_hnsw
    ON pellier.product_catalog
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
ANALYZE pellier.product_catalog;
' >/tmp/pellier-governed-reset-index.log
pass "HNSW index present: product_catalog_embedding_hnsw"

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
# different claim: every table that should be empty is empty, and the tables that carry
# the deterministic forensic incident carry exactly one row each. A reset that reported
# eleven passes and left a stray review behind would otherwise look complete.
_verify_baseline() {
  local empty_tables=(
    approvals execution_receipts operator_episodes write_operations
    conversations messages observatory_spans semantic_cache
    session_metadata tool_uses retrieval_receipts model_invocation_receipts
    policy_decisions governance_boundary_observations workshop_runs
  )
  local table count bad=0
  for table in "${empty_tables[@]}"; do
    count="$(_psql_scalar "SELECT count(*) FROM pellier.${table};" 2>/dev/null | tr -d '[:space:]')"
    if [[ "$count" != "0" ]]; then
      fail "Baseline: pellier.${table} should be empty, has ${count}"
      bad=$((bad + 1))
    fi
  done
  # The migration 010 forensic incident is the ONE intentional row in each of these.
  # It is the fixture the Observatory reconstructs, so zero is as wrong as two.
  for table in returns tool_audit governed_receipts; do
    count="$(_psql_scalar "SELECT count(*) FROM pellier.${table};" 2>/dev/null | tr -d '[:space:]')"
    if [[ "$count" != "1" ]]; then
      fail "Baseline: pellier.${table} should hold exactly the forensic incident (1 row), has ${count}"
      bad=$((bad + 1))
    fi
  done
  # The Operator service-recovery walkthrough is built on Jessica's ticket
  # asserting a return that the authoritative table does not carry. The count
  # above says one return exists; it does not say whose. Assert the customer
  # explicitly, because a stray row here empties the human checkpoint and the
  # symptom (a section that renders nothing) points nowhere near the cause.
  count="$(_psql_scalar "SELECT count(*) FROM pellier.returns WHERE customer_id = 'CUST-JESSICA';" 2>/dev/null | tr -d '[:space:]')"
  if [[ "$count" != "0" ]]; then
    fail "Baseline: CUST-JESSICA should have no authoritative returns, has ${count}. The Operator human checkpoint reads this as a resolved dispute."
    bad=$((bad + 1))
  fi

  if [[ "$bad" -gt 0 ]]; then
    fail "Baseline verification failed on ${bad} table(s); this reset did not land a clean state"
    return 1
  fi
  pass "Baseline verified: runtime tables empty, forensic incident intact"
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

AGENTCORE_PROJECT="$REPO/.agentcore-project/pellier"
AGENTCORE_CONFIG="$AGENTCORE_PROJECT/agentcore/agentcore.json"
POLICY_ENGINE_NAME="pellier_policy_engine"

if [[ ! -f "$AGENTCORE_CONFIG" ]]; then
  fail "AgentCore CLI project missing: $AGENTCORE_CONFIG"
  exit 1
fi

_agentcore() {
  (
    cd "$AGENTCORE_PROJECT"
    # The CLI expects an endpoint alias; Pellier's parent environment stores an ARN.
    export AGENTCORE_RUNTIME_ENDPOINT=DEFAULT
    if command -v agentcore >/dev/null 2>&1; then
      command agentcore "$@"
    else
      npx -y @aws/agentcore@0.29.0 "$@"
    fi
  )
}

policy_changed=false
policy_name=workshop_identity_match_forbid
  if jq -e \
      --arg engine "$POLICY_ENGINE_NAME" \
      --arg policy "$policy_name" \
      '.policyEngines[] | select(.name == $engine) | .policies[]? | select(.name == $policy)' \
      "$AGENTCORE_CONFIG" >/dev/null; then
    _agentcore remove policy \
      --name "$policy_name" \
      --engine "$POLICY_ENGINE_NAME" \
      --yes \
      --json >>/tmp/pellier-governed-reset-policy.log
    policy_changed=true
  fi

if [[ "$policy_changed" == true ]]; then
  _agentcore validate --json >>/tmp/pellier-governed-reset-policy.log
  _agentcore deploy --yes --json >>/tmp/pellier-governed-reset-policy.log
  pass "Participant Cedar rule removed through AgentCore CLI"
else
  pass "Participant Cedar rule absent; shipped CLI project already restored"
fi

if [[ "$(jq -r \
    --arg name pellier-gateway \
    '.agentCoreGateways[] | select(.name == $name) | .policyEngineConfiguration.mode' \
    "$AGENTCORE_CONFIG")" != "ENFORCE" ]]; then
  fail "AgentCore project no longer pins Gateway Policy mode to ENFORCE"
  exit 1
fi
pass "Gateway Policy remains configured in ENFORCE mode"

# The check above reads the CLI project file, which is the declared intent. The
# live engine can disagree: a participant who switches a policy to LOG_ONLY
# during the monitor-mode exercise leaves enforcement off while the file still
# says ENFORCE. Restoring only the file would report a reset workshop whose
# denials silently do not happen, so the live mode is restored at both scopes
# (per-policy `enforcementMode`, gateway `policyEngineConfiguration.mode`).
#
# Non-fatal for a box with no AgentCore Policy engine provisioned: there the policy
# leg is legitimately NOT_EVALUATED rather than broken, and `policy_mode.py` says so
# with a dedicated exit code rather than in prose.
_policy_rc=0
"$PYTHON" "$REPO/scripts/policy_mode.py" --restore-shipped \
  >/tmp/pellier-governed-reset-policy-mode.log 2>&1 || _policy_rc=$?
if [[ "$_policy_rc" -eq 0 ]]; then
  pass "Live Cedar enforcement mode restored at both scopes"
elif [[ "$_policy_rc" -eq 2 ]]; then
  # `policy_mode.py` reserves exit 2 for "AGENTCORE_POLICY_ENGINE_ID is not set, so
  # there is no engine to read". Its other exit-2 path, a missing CLI project, cannot
  # be reached here: this script already hard-failed above if $AGENTCORE_CONFIG were
  # absent, and that is the same project directory.
  pass "AgentCore Policy not provisioned here; live enforcement is NOT_EVALUATED"
else
  fail "Could not restore live Cedar enforcement mode (see /tmp/pellier-governed-reset-policy-mode.log)"
  _quarantine policy "Could not restore live Cedar enforcement mode"
  exit 1
fi

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
