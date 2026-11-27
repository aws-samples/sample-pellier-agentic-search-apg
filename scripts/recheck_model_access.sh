#!/usr/bin/env bash
# Run the Bedrock model-access preflight again, and move the Catalog and Support agents back to
# Claude Opus 5.5 once it answers.
#
# A new account's Bedrock access can still be switching on when bootstrap first checks it
# (check_model_access.py names a 15-minute wait). That first run lets Sonnet 5.5 stand in for a
# denied Opus 5.5 by writing BEDROCK_OPUS_MODEL, and the workshop runs on Opus 5.5 (owner,
# 2026-11-25). Bootstrap runs this just before its health gate. A facilitator runs it on a box
# whose readiness says the agents are not on Opus 5.5, then records readiness again:
#
#   bash scripts/recheck_model_access.sh && uv run scripts/event_readiness.py --live
#
# It never makes a box worse: a box already on Opus 5.5 with a passed preflight is left alone,
# the preflight writes a copy of .env, and the copy replaces .env only when that run passed and
# put the agents on Opus 5.5. A retry verifies the model the running backend actually loaded.
#
# This moves the agents that run in Pellier, which is where they run until Lab 3. An AgentCore
# Runtime that bootstrap deployed while Sonnet stood in keeps Sonnet until its next deploy:
# Lab 3's deploy, lab_run.py finish --lab 3 and the whole-workshop reset all read .env again.
#
# Exit status: 0 the agents use Opus 5.5; 1 the preflight did not pass, or Pellier did not come
# back healthy; 3 the preflight passed but Opus 5.5 still does not answer.
set -uo pipefail

REPO="${PELLIER_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="$REPO/pellier/backend/.env"
PYTHON="${PELLIER_PYTHON:-python3.14}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/health}"
HEALTH_TRIES="${HEALTH_TRIES:-150}"
HEALTH_PAUSE="${HEALTH_PAUSE:-2}"

setting() {  # setting FILE KEY: the last KEY=value in FILE, unquoted
  grep -E "^$2=" "$1" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d "\"'"
}

running_on_default_model() {
  curl -fs --max-time 3 "$HEALTH_URL" 2>/dev/null |
    python3 -c 'import json, sys
health = json.load(sys.stdin)
sys.exit(0 if health.get("status") == "healthy" and health.get("editorial_model_is_default") is True else 1)' 2>/dev/null
}

OPUS_ID_CODE='import sys
sys.path.insert(0, sys.argv[1])
import check_model_access
print(next(m["model_id"] for m in check_model_access.MODELS if m["name"] == "Claude Opus 5.5"))'
opus="$("$PYTHON" -c "$OPUS_ID_CODE" "$REPO/scripts")" || {
  echo "Could not read the Opus 5.5 model ID from scripts/check_model_access.py."
  exit 1
}
before="$(setting "$ENV_FILE" BEDROCK_OPUS_MODEL)"
before="${before:-$opus}"
if [ "$before" = "$opus" ] && [ "$(setting "$ENV_FILE" BEDROCK_MODEL_ACCESS_READY)" = "true" ]; then
  if running_on_default_model; then
    echo "The Catalog and Support agents already use Claude Opus 5.5 ($opus); nothing to recheck."
    exit 0
  fi
  echo "The model settings are saved. Restarting Pellier to load and verify them."
else
  copy="$(mktemp)" || exit 1
  trap 'rm -f "$copy"' EXIT
  cat "$ENV_FILE" > "$copy" || exit 1
  if ! "$PYTHON" "$REPO/scripts/check_model_access.py" --write-env "$copy"; then
    echo "The second preflight did not pass, so the box keeps its current model settings."
    exit 1
  fi
  after="$(setting "$copy" BEDROCK_OPUS_MODEL)"
  if [ "$after" != "$opus" ]; then
    echo "Claude Opus 5.5 still does not answer, so the Catalog and Support agents stay on $after."
    exit 3
  fi
  # Write through backend/.env's link to the root .env.
  cat "$copy" > "$ENV_FILE" || {
    echo "Could not write $ENV_FILE, so Pellier keeps its current model settings."
    exit 1
  }
  echo "The preflight passed. Restarting Pellier to load the model settings."
fi
if [ "$(id -u)" -eq 0 ]; then
  systemctl restart pellier
else
  sudo -n systemctl restart pellier
fi || {
  echo "Pellier did not restart (systemctl restart pellier)."
  exit 1
}
for _ in $(seq 1 "$HEALTH_TRIES"); do
  if running_on_default_model; then
    echo "Pellier answers /api/health again, on Claude Opus 5.5."
    exit 0
  fi
  sleep "$HEALTH_PAUSE"
done
echo "Pellier did not answer /api/health with a healthy backend on Claude Opus 5.5. Check journalctl -u pellier."
exit 1
