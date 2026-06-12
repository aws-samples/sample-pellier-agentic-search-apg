#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Pellier — Deploy All to AgentCore (workshop end-to-end script)
# =============================================================================
#
# Walks the full production deploy in eight steps. Each step prints a banner
# so participants can follow along in the terminal:
#
#   1–4. Four Lambda MCP servers (search / pricing / recommendations / experience).
#        These are the "tools" the agent will discover at runtime. Search now
#        carries `find_pieces_hybrid` (vector + FTS + Cohere Rerank) alongside
#        the basic vector path; experience carries `process_return` and
#        `escalate_to_stylist` — every backend `@tool` is reachable over Gateway.
#     5. AgentCore Gateway — fronts the four Lambdas with Cognito JWT auth
#        and exposes them over MCP streamable HTTP for tool discovery.
#        Docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html
#     6. Render `agentcore.json` + `aws-targets.json` from `.template` files.
#        The new @aws/agentcore Node CLI takes ZERO config flags — region,
#        role ARN, JWT settings, and env vars all live in those two JSON
#        files. We use envsubst to splice in CFN outputs at deploy time.
#     7. `agentcore deploy` — packages the orchestrator and creates an
#        AgentCore Runtime that participants can invoke as a managed agent.
#        Docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html
#     8. Three smoke-test invocations (search, trending, pricing) to confirm
#        the deployed Runtime can route through Gateway → Lambda → Aurora.
#
# Prerequisites — these MUST be exported before sourcing this script. They
# all come from CloudFormation outputs of the workshop stack:
#
#   PGHOSTARN          Aurora cluster ARN (search/pricing/rec Lambdas need it)
#   PGSECRET           Secrets Manager ARN holding the Aurora master credentials
#   PGDATABASE         Database name (typically `postgres`)
#   AWS_REGION         AgentCore GA region — `us-east-1` for this workshop
#   COGNITO_POOL       Cognito User Pool id (Gateway auth + Runtime auth)
#   COGNITO_CLIENT     Cognito User Pool *client* id (allowed on the Runtime JWT)
#   AGENTCORE_ROLE_ARN Execution role with trust on bedrock-agentcore.amazonaws.com
#   STACKNAME          CFN stack name (used for the smoke-test user lookup)
#
# Usage:
#   source deploy_all.sh
#
# The `source` form is intentional — later steps consume env vars exported
# by earlier steps (SEARCH_LAMBDA_ARN, MCP_GATEWAY_URL, etc.). Running with
# `bash deploy_all.sh` would silently lose those exports.
# =============================================================================

SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"

echo ""
echo "=============================================="
echo "  Pellier — Deploy to AgentCore"
echo "=============================================="
echo ""

# ------------------------------------------------------------------
# 0. Resolve provisioning inputs (operator-friendly recovery)
# ------------------------------------------------------------------
# This script needs 8 CFN-output vars that bootstrap had in scope but that are
# NOT in an interactive operator's shell. bootstrap-labs.sh STEP 16 writes them
# to ../../.provision.env; auto-source it so a manual re-run "just works" after
# a failed unattended deploy. Then validate and, if anything is still missing,
# print precise guidance and exit cleanly instead of crashing on `set -u` with
# an opaque "PGHOSTARN: unbound variable".
_REPO_ROOT="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd || echo "")"
if [ -n "$_REPO_ROOT" ] && [ -f "$_REPO_ROOT/.provision.env" ]; then
    echo "Sourcing provisioning inputs from $_REPO_ROOT/.provision.env ..."
    # shellcheck disable=SC1091
    set +u; . "$_REPO_ROOT/.provision.env"; set -u
fi

_missing=()
for _v in PGHOSTARN PGSECRET PGDATABASE AWS_REGION COGNITO_POOL COGNITO_CLIENT AGENTCORE_ROLE_ARN STACKNAME; do
    # `set -u` is active, so test via indirect default-expansion (no crash).
    if [ -z "$(eval "printf '%s' \"\${$_v:-}\"")" ]; then
        _missing+=("$_v")
    fi
done

if [ "${#_missing[@]}" -gt 0 ]; then
    echo ""
    echo "❌ Missing required provisioning inputs: ${_missing[*]}"
    echo ""
    echo "These come from the workshop CloudFormation outputs. On a Workshop"
    echo "Studio box bootstrap writes them to ${_REPO_ROOT:-<repo>}/.provision.env"
    echo "automatically — if that file is absent, provisioning never reached"
    echo "STEP 16. Recover by exporting them, then re-run 'source deploy_all.sh':"
    echo ""
    for _v in "${_missing[@]}"; do
        echo "  export $_v=<value-from-CloudFormation-Outputs>"
    done
    echo ""
    echo "(PGHOSTARN = Aurora cluster ARN, PGSECRET = master-secret ARN,"
    echo " AGENTCORE_ROLE_ARN = the bedrock-agentcore execution role.)"
    # Return (sourced) or exit (executed) without the ugly unbound-variable trap.
    return 1 2>/dev/null || exit 1
fi
echo "✅ Provisioning inputs validated."
echo ""

# ------------------------------------------------------------------
# 1. Deploy Search Lambda MCP Server
# ------------------------------------------------------------------
# `deploy_lambda.py` zips the MCP server + dependencies, creates (or
# updates) a Lambda function, and grants `lambda:InvokeFunction` to the
# AgentCore Gateway service principal. The Lambda speaks MCP over its
# function URL — Gateway will register it as a target in step 4.
echo "=== [1/8] Deploying Search Lambda ==="
uv run "$SCRIPT_DIR/deploy_lambda.py" \
  --server-name pellier-search-server \
  --db-cluster-arn "$PGHOSTARN" \
  --secret-arn "$PGSECRET" \
  --database "$PGDATABASE" \
  --mcp-server-path "$SCRIPT_DIR/pellier_search_server.py" \
  --handler pellier_search_server.lambda_handler \
  --region "$AWS_REGION"

export SEARCH_LAMBDA_ARN=$(aws lambda get-function \
  --function-name pellier-search-server-function \
  --region "$AWS_REGION" \
  --query 'Configuration.FunctionArn' --output text)
echo "  SEARCH_LAMBDA_ARN=$SEARCH_LAMBDA_ARN"

# ------------------------------------------------------------------
# 2. Deploy Pricing Lambda MCP Server
# ------------------------------------------------------------------
echo ""
echo "=== [2/8] Deploying Pricing Lambda ==="
uv run "$SCRIPT_DIR/deploy_lambda.py" \
  --server-name pellier-pricing-server \
  --db-cluster-arn "$PGHOSTARN" \
  --secret-arn "$PGSECRET" \
  --database "$PGDATABASE" \
  --mcp-server-path "$SCRIPT_DIR/pellier_pricing_server.py" \
  --handler pellier_pricing_server.lambda_handler \
  --region "$AWS_REGION"

export PRICING_LAMBDA_ARN=$(aws lambda get-function \
  --function-name pellier-pricing-server-function \
  --region "$AWS_REGION" \
  --query 'Configuration.FunctionArn' --output text)
echo "  PRICING_LAMBDA_ARN=$PRICING_LAMBDA_ARN"

# ------------------------------------------------------------------
# 3. Deploy Recommendation Lambda MCP Server
# ------------------------------------------------------------------
echo ""
echo "=== [3/8] Deploying Recommendation Lambda ==="
uv run "$SCRIPT_DIR/deploy_lambda.py" \
  --server-name pellier-recommend-server \
  --db-cluster-arn "$PGHOSTARN" \
  --secret-arn "$PGSECRET" \
  --database "$PGDATABASE" \
  --mcp-server-path "$SCRIPT_DIR/pellier_recommend_server.py" \
  --handler pellier_recommend_server.lambda_handler \
  --region "$AWS_REGION"

export RECOMMENDATION_LAMBDA_ARN=$(aws lambda get-function \
  --function-name pellier-recommend-server-function \
  --region "$AWS_REGION" \
  --query 'Configuration.FunctionArn' --output text)
echo "  RECOMMENDATION_LAMBDA_ARN=$RECOMMENDATION_LAMBDA_ARN"

# ------------------------------------------------------------------
# 4. Deploy Experience Lambda MCP Server
# ------------------------------------------------------------------
# Carries the two Theo-flow tools: process_return (atomic ownership +
# INSERT + conditional quantity decrement against pellier.returns) and
# escalate_to_stylist (UI-only handoff, no DB write). These previously
# stayed in-process because they took rich Python objects or triggered
# human handoff; the Lambda mirrors the in-process JSON envelopes so the
# orchestrator's prompt is identical on either path.
echo ""
echo "=== [4/8] Deploying Experience Lambda ==="
uv run "$SCRIPT_DIR/deploy_lambda.py" \
  --server-name pellier-experience-server \
  --db-cluster-arn "$PGHOSTARN" \
  --secret-arn "$PGSECRET" \
  --database "$PGDATABASE" \
  --mcp-server-path "$SCRIPT_DIR/pellier_experience_server.py" \
  --handler pellier_experience_server.lambda_handler \
  --region "$AWS_REGION"

export EXPERIENCE_LAMBDA_ARN=$(aws lambda get-function \
  --function-name pellier-experience-server-function \
  --region "$AWS_REGION" \
  --query 'Configuration.FunctionArn' --output text)
echo "  EXPERIENCE_LAMBDA_ARN=$EXPERIENCE_LAMBDA_ARN"

# ------------------------------------------------------------------
# 5. Deploy AgentCore Gateway
# ------------------------------------------------------------------
# Gateway is a managed MCP front-door for tool catalogs. It enforces
# Cognito JWT auth on every tool call, then proxies to the registered
# Lambda targets. Once it's up, the orchestrator can discover all 13
# tools dynamically via `MCPClient.list_tools_sync()` instead of
# importing them from `services.agent_tools`.
#
# Control-plane API: bedrock-agentcore-control:CreateGateway
#   https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CreateGateway.html
echo ""
echo "=== [5/8] Deploying AgentCore Gateway ==="
uv run "$SCRIPT_DIR/deploy_gateway.py" \
  --gateway-name pellier-gateway \
  --search-lambda-arn "$SEARCH_LAMBDA_ARN" \
  --pricing-lambda-arn "$PRICING_LAMBDA_ARN" \
  --recommendation-lambda-arn "$RECOMMENDATION_LAMBDA_ARN" \
  --experience-lambda-arn "$EXPERIENCE_LAMBDA_ARN" \
  --cognito-user-pool-id "$COGNITO_POOL" \
  --cognito-client-id "$COGNITO_CLIENT" \
  --region "$AWS_REGION"

export GATEWAY_ID=$(aws bedrock-agentcore-control list-gateways \
  --region "$AWS_REGION" \
  --query "items[?name=='pellier-gateway'].gatewayId | [0]" --output text)
export GATEWAY_ARN=$(aws bedrock-agentcore-control get-gateway \
  --gateway-identifier "$GATEWAY_ID" --region "$AWS_REGION" \
  --query 'gatewayArn' --output text)
export MCP_GATEWAY_URL=$(aws bedrock-agentcore-control get-gateway \
  --gateway-identifier "$GATEWAY_ID" --region "$AWS_REGION" \
  --query 'gatewayUrl' --output text)
echo "  GATEWAY_ID=$GATEWAY_ID"
echo "  MCP_GATEWAY_URL=$MCP_GATEWAY_URL"

# ------------------------------------------------------------------
# 5b. Managed AgentCore Policy — the 4th pillar (Cedar at the Gateway)
# ------------------------------------------------------------------
# Create a managed Cedar policy engine, gate process_return to damaged-only,
# and attach to the gateway in ENFORCE mode. From here, the Gateway evaluates
# every tool call against Cedar BEFORE the Lambda runs (default-deny,
# forbid-wins) — the managed replacement for the old local BeforeToolCall hook.
#   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html
echo ""
echo "=== [5b/8] Attaching managed AgentCore Policy (Cedar, ENFORCE) ==="
uv run "$SCRIPT_DIR/deploy_policy.py" \
  --gateway-id "$GATEWAY_ID" \
  --gateway-arn "$GATEWAY_ARN" \
  --region "$AWS_REGION" \
  --mode ENFORCE

# ------------------------------------------------------------------
# 6. Scaffold the AgentCore project (create + add BYO agent)
# ------------------------------------------------------------------
#
# The @aws/agentcore CLI (Node) is the canonical deploy tool for AgentCore
# Runtime. As of 0.18 it is a STATEFUL, CDK-based project model — NOT the
# old flat-config `deploy` that read a bare agentcore.json. The verbs are:
#
#   agentcore create   — scaffold a project (writes <root>/<proj>/agentcore/)
#   agentcore add agent — register a runtime (BYO points at our entrypoint)
#   agentcore deploy    — CDK synth + deploy from the PROJECT ROOT
#
# `add agent` sets name/entrypoint/protocol/CUSTOM_JWT via flags, but has NO
# flags for executionRoleArn or envVars — those are JSON-patched into
# agentcore/agentcore.json after. aws-targets.json is now an ARRAY
# ([{name,account,region}]) and no longer carries the role.
#
# Pin the version: @latest drifted contracts mid-development; pinning keeps
# every participant account on identical, tested behavior.
#
# CLI repo: https://github.com/aws/agentcore-cli
#
AGENTCORE_CLI="@aws/agentcore@0.18.0"
RUNTIME_NAME="pellier_orchestrator"
RUNTIME_PYTHON_VERSION="PYTHON_3_12"   # CLI defaults to PYTHON_3_14 (unsupported by the build)

echo ""
echo "=== [6/8] Scaffolding AgentCore project (create + add BYO agent) ==="

# Fail fast if a caller-set prerequisite is missing.
: "${AGENTCORE_ROLE_ARN:?AGENTCORE_ROLE_ARN must be set (CFN output)}"
: "${COGNITO_POOL:?COGNITO_POOL must be set (CFN output)}"
: "${COGNITO_CLIENT:?COGNITO_CLIENT must be set (CFN output)}"
: "${AWS_REGION:?AWS_REGION must be set}"

# Cognito's OIDC discovery URL — the Runtime's JWT authorizer fetches
# /.well-known/openid-configuration from here to validate incoming tokens.
export OAUTH_ISSUER_URL="https://cognito-idp.${AWS_REGION}.amazonaws.com/${COGNITO_POOL}"
DISCOVERY_URL="${OAUTH_ISSUER_URL}/.well-known/openid-configuration"

# Default model the orchestrator uses inside the Runtime.
export AGENT_MODEL_ID="${AGENT_MODEL_ID:-global.anthropic.claude-opus-4-6-v1}"
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

BACKEND_DIR="$(cd "$SCRIPT_DIR/../../pellier/backend" && pwd)"   # absolute (code-location)
PROJECT_ROOT="$BACKEND_DIR/.agentcore-project/pellier"          # dir that CONTAINS agentcore/
CONFIG_PATH="$PROJECT_ROOT/agentcore/agentcore.json"
mkdir -p "$BACKEND_DIR/.agentcore-project"

# 6a. create (idempotent — skip if the project already exists)
if [ ! -f "$CONFIG_PATH" ]; then
  npx -y "$AGENTCORE_CLI" create \
    --project-name pellier --no-agent --defaults \
    --build CodeZip --language Python --framework Strands \
    --model-provider Bedrock --protocol HTTP \
    --skip-git --skip-python-setup --skip-install \
    --output-dir "$BACKEND_DIR/.agentcore-project" --json
fi

# 6b. add our in-repo orchestrator as a BYO agent (clean re-add for re-runs)
npx -y "$AGENTCORE_CLI" remove agent --name "$RUNTIME_NAME" --yes 2>/dev/null || true
( cd "$PROJECT_ROOT" && npx -y "$AGENTCORE_CLI" add agent \
    --name "$RUNTIME_NAME" --type byo \
    --build CodeZip --language Python --framework Strands \
    --model-provider Bedrock --protocol HTTP \
    --code-location "$BACKEND_DIR" --entrypoint agentcore_runtime.py \
    --authorizer-type CUSTOM_JWT \
    --discovery-url "$DISCOVERY_URL" \
    --allowed-clients "$COGNITO_CLIENT" --json )

# 6c. patch the fields `add agent` has no flags for, and write aws-targets.json
#     in the 0.18 ARRAY shape. Field spellings match the WORKING dat403 config
#     (modules/05/strands/deploy/setup_deploy.sh:90-113): roleArn (NOT
#     executionRoleArn — add agent has no role flag, so this is the only role
#     setter), networkMode PUBLIC, requestHeaderAllowlist ["Authorization"].
python3 - "$CONFIG_PATH" "$RUNTIME_NAME" "$AGENTCORE_ROLE_ARN" \
  "$RUNTIME_PYTHON_VERSION" "$MCP_GATEWAY_URL" "$AGENT_MODEL_ID" \
  "$AWS_ACCOUNT" "$AWS_REGION" "$DISCOVERY_URL" "$COGNITO_CLIENT" <<'PYEOF'
import json, sys
cfg_path, name, role, pyver, gw_url, model_id, account, region, discovery, client = sys.argv[1:11]
cfg = json.load(open(cfg_path))
runtimes = cfg.get("runtimes") or []
target = next((r for r in runtimes if isinstance(r, dict) and r.get("name") == name), None)
if target is None and len(runtimes) == 1 and isinstance(runtimes[0], dict):
    target = runtimes[0]
if target is None:
    sys.exit(f"Could not find runtime '{name}' to patch in {[r.get('name') for r in runtimes]}")
target["roleArn"] = role                       # NOT executionRoleArn (dat403-proven key)
target["runtimeVersion"] = pyver
target["networkMode"] = "PUBLIC"
target["requestHeaderAllowlist"] = ["Authorization"]
target["envVars"] = [
    {"name": "MCP_GATEWAY_URL", "value": gw_url},
    {"name": "AGENT_MODEL_ID", "value": model_id},
]
# Re-assert CUSTOM_JWT authorizer in dat403's proven shape if add-agent didn't.
if discovery and client and not target.get("authorizerConfiguration"):
    target["authorizerType"] = "CUSTOM_JWT"
    target["authorizerConfiguration"] = {
        "customJwtAuthorizer": {"discoveryUrl": discovery, "allowedClients": [client]}
    }
json.dump(cfg, open(cfg_path, "w"), indent=2)
import os
targets_path = os.path.join(os.path.dirname(cfg_path), "aws-targets.json")
json.dump([{"name": "default", "account": account, "region": region}],
          open(targets_path, "w"), indent=2)
print(f"  Patched {cfg_path} + wrote {targets_path}")
PYEOF

echo "  Project ready at $PROJECT_ROOT"

# ------------------------------------------------------------------
# 7. Deploy AgentCore Runtime via @aws/agentcore CLI (CDK, ~5 min)
# ------------------------------------------------------------------
echo ""
echo "=== [7/8] Deploying AgentCore Runtime (CDK; this takes ~5 minutes) ==="

# `deploy` MUST run from the PROJECT ROOT (the dir containing agentcore/),
# not from inside agentcore/. It CDK-synths and deploys the runtime stack.
#   -y      auto-confirm prompts, read credentials from env
#   --json  machine-readable result envelope on stdout
pushd "$PROJECT_ROOT" > /dev/null
npx -y "$AGENTCORE_CLI" deploy -y --json
popd > /dev/null

echo "  ✅ Agent deployed!"

# ------------------------------------------------------------------
# 8. Smoke Tests
# ------------------------------------------------------------------
# Quick end-to-end verification: get a Cognito access token for the
# workshop user, look up the deployed Runtime by name, and invoke it
# three times with representative prompts. Each invocation streams the
# response so participants see tokens land live in the terminal.
echo ""
echo "=== [8/8] Running Smoke Tests ==="

# Cognito user-pool client secret (used by USER_PASSWORD_AUTH flow).
# We read it dynamically because Workshop Studio rotates it per account.
export CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client \
  --user-pool-id "$COGNITO_POOL" --client-id "$COGNITO_CLIENT" \
  --region "$AWS_REGION" --query 'UserPoolClient.ClientSecret' --output text)

export USER=$(aws cloudformation describe-stacks \
  --stack-name "$STACKNAME" --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationUserEmail`].OutputValue' --output text)

export PASSWORD=$(aws cloudformation describe-stacks \
  --stack-name "$STACKNAME" --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationUserPassword`].OutputValue' --output text)

# Cognito app clients with a secret require SECRET_HASH =
# base64(HMAC-SHA256(client_secret, username + client_id)) on every auth
# call. Without it, initiate-auth rejects with "Unable to verify secret
# hash" and TOKEN comes back "null" – the smoke test then silently passes
# nothing. Compute it so the auth actually succeeds, and guard the result.
SECRET_HASH=$(printf '%s' "${USER}${COGNITO_CLIENT}" \
  | openssl dgst -sha256 -hmac "$CLIENT_SECRET" -binary | base64)

export TOKEN=$(aws cognito-idp initiate-auth \
  --client-id "$COGNITO_CLIENT" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters "{\"USERNAME\":\"$USER\",\"PASSWORD\":\"$PASSWORD\",\"SECRET_HASH\":\"$SECRET_HASH\"}" \
  --region "$AWS_REGION" | jq -r '.AuthenticationResult.AccessToken')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "ERROR: Failed to obtain a Cognito access token for the smoke test." >&2
  echo "       Check COGNITO_CLIENT / CLIENT_SECRET and the ApplicationUser* stack outputs." >&2
  exit 1
fi

export AGENT_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
  --region "$AWS_REGION" \
  --query "agentRuntimes[?agentRuntimeName=='pellier_orchestrator'].agentRuntimeId | [0]" --output text)

echo ""
echo "  Test 1: Product search"
uv run "$SCRIPT_DIR/test_runtime.py" \
  --runtime-id "$AGENT_RUNTIME_ID" \
  --prompt "Find me comfortable running shoes under \$80" \
  --token "$TOKEN" --stream

echo "  Test 2: Trending products"
uv run "$SCRIPT_DIR/test_runtime.py" \
  --runtime-id "$AGENT_RUNTIME_ID" \
  --prompt "What's trending right now?" \
  --token "$TOKEN" --stream

echo "  Test 3: Price comparison"
uv run "$SCRIPT_DIR/test_runtime.py" \
  --runtime-id "$AGENT_RUNTIME_ID" \
  --prompt "Show me the best laptop deals" \
  --token "$TOKEN" --stream

echo ""
echo "=============================================="
echo "  ✅ Pellier deployed to AgentCore!"
echo ""
echo "  Gateway:  $MCP_GATEWAY_URL"
echo "  Runtime:  $AGENT_RUNTIME_ID"
echo "=============================================="
