#!/usr/bin/env bash
# Restore participant-changed execution and AgentCore state to what the workshop ships.
#
# Sourced by scripts/reset-governed-workshop.sh (the whole workshop) and by
# scripts/reset-agentcore-lab.sh (one lab, run by `lab_run.py reset --lab N`), so both
# restore the same state with the same commands.
#
# The caller defines before sourcing or calling:
#   REPO PYTHON ENV_FILE RUN_ENV_FILE        paths and the interpreter
#   pass fail warn                           one-line reporters
# Each function returns 0 on success. On failure it reports with `fail`, sets
# PELLIER_RESET_FAILED_STEP to a short name and returns 1; the caller decides whether that
# quarantines the box (a whole-workshop reset) or only stops this lab's reset.

PELLIER_RESET_FAILED_STEP=""

# ---------------------------------------------------------------------------
# Execution rail
# ---------------------------------------------------------------------------
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

pellier_restore_execution_rail() {
  local file restored=0
  for file in "$RUN_ENV_FILE" "$ENV_FILE"; do
    [[ -f "$file" ]] || continue
    if ! _reset_upsert_env "$file" "USE_AGENTCORE_RUNTIME" "false"; then
      fail "Could not clear USE_AGENTCORE_RUNTIME in ${file}."
      fail "The next participant would edit Lab 1 locally while the storefront answered from the deployed Runtime."
      PELLIER_RESET_FAILED_STEP="execution-rail"
      return 1
    fi
    restored=$((restored + 1))
  done
  # Assert the RESULT, not the writes. A file this script never saw -- an
  # operator's own copy, a path override -- would otherwise pass silently.
  for file in "$RUN_ENV_FILE" "$ENV_FILE"; do
    if _env_declares_managed_rail "$file"; then
      fail "Baseline: ${file} still enables the managed rail after the reset wrote to it"
      PELLIER_RESET_FAILED_STEP="execution-rail"
      return 1
    fi
  done
  if [[ "$restored" -eq 0 ]]; then
    warn "No env file found at $RUN_ENV_FILE or $ENV_FILE; execution rail left as configured"
  else
    pass "Execution rail restored to in-process (USE_AGENTCORE_RUNTIME=false in ${restored} file(s))"
  fi
}

# ---------------------------------------------------------------------------
# The AgentCore CLI project
# ---------------------------------------------------------------------------
pellier_agentcore_init() {
  local helper="$REPO/scripts/deploy/resolve_agentcore_identity.py"
  AGENTCORE_PROJECT="$("$PYTHON" "$helper" --repo "$REPO" --field project-root)" || return 1
  AGENTCORE_CONFIG="$AGENTCORE_PROJECT/agentcore/agentcore.json"
  POLICY_ENGINE_NAME="$("$PYTHON" "$helper" --repo "$REPO" --field policy-engine-name)" || return 1
  GATEWAY_NAME="$("$PYTHON" "$helper" --repo "$REPO" --field gateway-name)" || return 1
  if [[ ! -f "$AGENTCORE_CONFIG" ]]; then
    fail "AgentCore CLI project missing: $AGENTCORE_CONFIG"
    PELLIER_RESET_FAILED_STEP="agentcore-project"
    return 1
  fi
}

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

# Lab 3 goes back to its starter too. A participant deploy (Lab 3 or Lab 4) renders
# the whole managed project from source - the Gateway's tool schemas, the Runtime
# package and the Cedar policies - and records it in the participant receipt. The
# files were restored above, but the live Gateway still publishes get_tickets with its
# owner-only permit, and the receipt still names that catalogue, so lab3-start.sh
# (which Lab 3's deploy runs) and the health gate both refused the reset box. The same deploy
# from the restored starters puts the live project back to what provisioning built;
# --reset-to-starters lets it retire the permit the starters no longer render, permit
# first and schema second. Before any participant deploy there is no receipt, and the
# live project is already provisioning's own render of these starters.
#
# The deploy renders every managed file as it stands in the tree, so a lab-only reset
# leaves another lab's edits (Lab 4's Cedar rule) as the participant wrote them.
pellier_restore_lab3_agentcore() {
  local receipt="${AGENTCORE_PARTICIPANT_OUTPUT_JSON:-/tmp/pellier-agentcore-participant.json}" rc=0
  if [[ ! -f "$receipt" ]]; then
    pass "No participant deploy since provisioning; the managed project is already the starters'"
    return 0
  fi
  (cd "$REPO" && "$PYTHON" "$REPO/scripts/provision_agentcore_end_to_end.py" \
      --repo-path "$REPO" --mode participant --reset-to-starters \
      --output-json "$receipt") \
    >/tmp/pellier-governed-reset-starter-deploy.log 2>&1 || rc=$?
  if [[ "$rc" -ne 0 ]]; then
    fail "Could not redeploy the managed project from the starters (see /tmp/pellier-governed-reset-starter-deploy.log)"
    PELLIER_RESET_FAILED_STEP="starter-deploy"
    return 1
  fi
  pass "Managed project redeployed from the starters: Lab 3's tool and permit retired"
}

# Lab 4's policy goes back to its starter, not away: provisioning deployed the
# starter forbid (`unless { false }`), and the next participant's Lab 4 opens
# with its live DENY. The participant files must already be restored, so the
# starter is declared from workshop/starters and the CLI converges it.
pellier_restore_lab4_policy() {
  local policy_changed=false policy_name=workshop_credit_limit declare_rc=0
  "$PYTHON" - "$AGENTCORE_CONFIG" "$POLICY_ENGINE_NAME" \
      "$REPO/workshop/starters/workshop_credit_limit.cedar" "$REPO/scripts/deploy" <<'PY' || declare_rc=$?
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[4])
from render_agentcore_project import declare_credit_limit

changed = declare_credit_limit(Path(sys.argv[1]), engine_name=sys.argv[2], source=Path(sys.argv[3]))
raise SystemExit(0 if changed else 10)
PY
  if [[ "$declare_rc" -eq 0 ]]; then
    policy_changed=true
  elif [[ "$declare_rc" -ne 10 ]]; then
    fail "Could not declare the Lab 4 starter policy ($policy_name) in $AGENTCORE_CONFIG"
    PELLIER_RESET_FAILED_STEP="policy-declare"
    return 1
  fi

  if [[ "$policy_changed" == true ]]; then
    _agentcore validate --json >>/tmp/pellier-governed-reset-policy.log || {
      fail "Lab 4 starter policy did not validate; see /tmp/pellier-governed-reset-policy.log"
      PELLIER_RESET_FAILED_STEP="policy-validate"
      return 1
    }
    _agentcore deploy --yes --json >>/tmp/pellier-governed-reset-policy.log || {
      fail "Lab 4 starter policy did not deploy; see /tmp/pellier-governed-reset-policy.log"
      PELLIER_RESET_FAILED_STEP="policy-deploy"
      return 1
    }
    pass "Lab 4 policy $policy_name restored to its starter through AgentCore CLI"
  else
    pass "Lab 4 policy $policy_name already declares its starter"
  fi

  if [[ "$(jq -r \
      --arg name "$GATEWAY_NAME" \
      '.agentCoreGateways[] | select(.name == $name) | .policyEngineConfiguration.mode' \
      "$AGENTCORE_CONFIG")" != "ENFORCE" ]]; then
    fail "AgentCore project no longer pins Gateway Policy mode to ENFORCE"
    PELLIER_RESET_FAILED_STEP="policy-pin"
    return 1
  fi
  pass "Gateway Policy remains configured in ENFORCE mode"
}

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
pellier_restore_policy_mode() {
  local rc=0
  "$PYTHON" "$REPO/scripts/policy_mode.py" --restore-shipped \
    >/tmp/pellier-governed-reset-policy-mode.log 2>&1 || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    pass "Live Cedar enforcement mode restored at both scopes"
  elif [[ "$rc" -eq 2 ]]; then
    # `policy_mode.py` reserves exit 2 for "AGENTCORE_POLICY_ENGINE_ID is not set, so
    # there is no engine to read".
    pass "AgentCore Policy not provisioned here; live enforcement is NOT_EVALUATED"
  else
    fail "Could not restore live Cedar enforcement mode (see /tmp/pellier-governed-reset-policy-mode.log)"
    PELLIER_RESET_FAILED_STEP="policy-mode"
    return 1
  fi
}

pellier_restore_lab4_agentcore() {
  pellier_restore_lab4_policy && pellier_restore_policy_mode
}
