#!/usr/bin/env bash
set -euo pipefail

# Prefer workshop aliases without changing the operating system interpreter.
export PATH="/opt/pellier/bin:$PATH"

# Recovery entrypoint for Pellier's managed AgentCore deployment.
#
# scripts/provision_agentcore_end_to_end.py is the only implementation. It
# packages the external Lambda tools, renders one pinned AgentCore CLI project,
# runs validate/deploy in two phases, and verifies the live managed path.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_JSON="${PELLIER_AGENTCORE_OUTPUT:-/tmp/pellier-agentcore-managed.json}"

# Do not execute generated dotenv values as shell. The provisioner already
# treats its fallback dotenv input as data; this wrapper must offer the same
# guarantee before it checks required inputs.
# shellcheck source=../lib/dotenv.sh
source "$REPO_ROOT/scripts/lib/dotenv.sh"

for env_file in "$REPO_ROOT/.provision.env" "$REPO_ROOT/.env"; do
  if [[ -f "$env_file" ]]; then
    pellier_load_dotenv "$env_file"
  fi
done

export REPO_PATH="${REPO_PATH:-$REPO_ROOT}"
export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$AWS_REGION}"
export DB_CLUSTER_ARN="${DB_CLUSTER_ARN:-${PGHOSTARN:-}}"
export DB_SECRET_ARN="${DB_SECRET_ARN:-${PGSECRET:-}}"
export DB_NAME="${DB_NAME:-${PGDATABASE:-pellier}}"
export COGNITO_POOL="${COGNITO_POOL:-${COGNITO_POOL_ID:-${COGNITO_USER_POOL_ID:-}}}"
export COGNITO_CLIENT="${COGNITO_CLIENT:-${COGNITO_CLIENT_ID:-}}"

required=(
  AWS_REGION
  DB_CLUSTER_ARN
  DB_SECRET_ARN
  DB_NAME
  COGNITO_POOL
  COGNITO_CLIENT
  COGNITO_TEST_CREDENTIALS_SECRET_ARN
  WORKSHOP_ID
  AGENT_MODEL_ID
  AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN
  AGENTCORE_RUNTIME_LOG_RETENTION_DAYS
)
missing=()
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done

if (( ${#missing[@]} > 0 )); then
  printf 'Missing required AgentCore provisioning inputs: %s\n' "${missing[*]}" >&2
  printf 'Restore .provision.env/.env or export the missing values, then rerun.\n' >&2
  return 1 2>/dev/null || exit 1
fi

PYTHON="$REPO_ROOT/pellier/backend/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

printf 'Deploying Pellier through the pinned AgentCore CLI project...\n'
"$PYTHON" "$REPO_ROOT/scripts/provision_agentcore_end_to_end.py" \
  --repo-path "$REPO_ROOT" \
  --output-json "$OUTPUT_JSON"

if [[ "$(jq -r '.status // "failed"' "$OUTPUT_JSON")" != "ready" ]]; then
  printf 'AgentCore provisioning did not reach ready; inspect %s.\n' "$OUTPUT_JSON" >&2
  return 1 2>/dev/null || exit 1
fi

export AGENTCORE_RUNTIME_ENDPOINT
AGENTCORE_RUNTIME_ENDPOINT="$(jq -r '.runtime.runtime_arn' "$OUTPUT_JSON")"
export AGENTCORE_MEMORY_ID
AGENTCORE_MEMORY_ID="$(jq -r '.memory.memory_id' "$OUTPUT_JSON")"
export AGENTCORE_GATEWAY_ID
AGENTCORE_GATEWAY_ID="$(jq -r '.gateway.gateway_id' "$OUTPUT_JSON")"
export AGENTCORE_GATEWAY_ARN
AGENTCORE_GATEWAY_ARN="$(jq -r '.gateway.gateway_arn' "$OUTPUT_JSON")"
export AGENTCORE_GATEWAY_URL
AGENTCORE_GATEWAY_URL="$(jq -r '.gateway.gateway_url' "$OUTPUT_JSON")"
export MCP_GATEWAY_URL="$AGENTCORE_GATEWAY_URL"
export AGENTCORE_POLICY_ENGINE_ID
AGENTCORE_POLICY_ENGINE_ID="$(jq -r '.policy.policy_engine_id' "$OUTPUT_JSON")"

printf 'AgentCore ready.\n'
printf '  Runtime: %s\n' "$AGENTCORE_RUNTIME_ENDPOINT"
printf '  Memory:  %s\n' "$AGENTCORE_MEMORY_ID"
printf '  Gateway: %s\n' "$AGENTCORE_GATEWAY_URL"
printf '  Policy:  %s\n' "$AGENTCORE_POLICY_ENGINE_ID"
