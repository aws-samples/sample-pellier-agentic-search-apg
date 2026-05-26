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
#   AWS_REGION         AgentCore GA region — `us-west-2` for this workshop
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

export MCP_GATEWAY_URL=$(aws bedrock-agentcore-control list-gateways \
  --region "$AWS_REGION" \
  --query "items[?name=='pellier-gateway'].gatewayId | [0]" --output text \
  | xargs -I {} aws bedrock-agentcore-control get-gateway \
    --gateway-identifier {} --region "$AWS_REGION" \
    --query 'gatewayUrl' --output text)
echo "  MCP_GATEWAY_URL=$MCP_GATEWAY_URL"

# ------------------------------------------------------------------
# 6. Render AgentCore CLI configs (agentcore.json + aws-targets.json)
# ------------------------------------------------------------------
#
# The @aws/agentcore CLI (Node) is the canonical deploy tool for
# AgentCore Runtime. It replaces the older Python
# `bedrock-agentcore-starter-toolkit` (which exposed `agentcore configure`
# + `agentcore launch` as two flag-driven verbs). The Node CLI takes a
# single `agentcore deploy` verb and reads ALL configuration from two
# JSON files in the current directory:
#
#   agentcore.json    — runtime definition, JWT auth, env vars
#   aws-targets.json  — target account + region
#
# There is no flag for region / role ARN / JWT config / env vars; if it
# isn't in those files it doesn't reach AgentCore. We ship both as
# `.template` files with `${VAR}` placeholders, then use envsubst to
# splice in CloudFormation outputs at deploy time. This keeps the
# templates committable (no secrets) while the rendered files reflect
# the live workshop account.
#
# CLI repo:    https://github.com/aws/agentcore-cli
# Install:     npm install -g @aws/agentcore
#
echo ""
echo "=== [6/8] Rendering AgentCore CLI config ==="

# Fail fast if a caller-set prerequisite is missing — envsubst would
# otherwise substitute an empty string and `agentcore deploy` would only
# error at the AWS-call stage, which is much harder to triage. The
# `${VAR:?message}` form makes bash exit immediately with the message.
: "${AGENTCORE_ROLE_ARN:?AGENTCORE_ROLE_ARN must be set (CFN output)}"
: "${COGNITO_POOL:?COGNITO_POOL must be set (CFN output)}"
: "${COGNITO_CLIENT:?COGNITO_CLIENT must be set (CFN output)}"
: "${AWS_REGION:?AWS_REGION must be set}"

# Cognito's OIDC discovery URL is derived from the pool id. The Runtime's
# JWT authorizer fetches `/.well-known/openid-configuration` from this
# URL on every cold start to validate incoming tokens.
export OAUTH_ISSUER_URL="https://cognito-idp.${AWS_REGION}.amazonaws.com/${COGNITO_POOL}"

# Default model the orchestrator uses inside the Runtime. Override via
# the env before sourcing this script if you want to test a different
# model — the value flows into agentcore.json:envVars.AGENT_MODEL_ID.
export AGENT_MODEL_ID="global.anthropic.claude-opus-4-6-v1"

# AgentCore deploy needs the account id in `aws-targets.json`. STS
# `GetCallerIdentity` is the canonical way to read it without hardcoding.
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

BACKEND_DIR="$SCRIPT_DIR/../../pellier/backend"

envsubst < "$BACKEND_DIR/agentcore.json.template" > "$BACKEND_DIR/agentcore.json"
envsubst < "$BACKEND_DIR/aws-targets.json.template" > "$BACKEND_DIR/aws-targets.json"

echo "  Rendered $BACKEND_DIR/agentcore.json"
echo "  Rendered $BACKEND_DIR/aws-targets.json"

# ------------------------------------------------------------------
# 7. Deploy AgentCore Runtime via @aws/agentcore CLI (~5 min)
# ------------------------------------------------------------------
echo ""
echo "=== [7/8] Deploying AgentCore Runtime (this takes ~5 minutes) ==="

pushd "$BACKEND_DIR" > /dev/null

# `agentcore deploy` reads agentcore.json + aws-targets.json from the
# current working directory — that's why we pushd into pellier/backend.
#   -y      skips the interactive confirmation prompt
#   --json  emits a machine-readable result envelope on stdout, useful
#           if a CI pipeline wants to capture the runtime ARN with jq
#
# Behind the scenes this calls bedrock-agentcore-control:CreateAgentRuntime
# which packages our Python entrypoint, uploads it to AgentCore-managed
# infrastructure, and registers it under the JWT authorizer in our config.
#   https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CreateAgentRuntime.html
agentcore deploy -y --json

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

export TOKEN=$(aws cognito-idp initiate-auth \
  --client-id "$COGNITO_CLIENT" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters "{\"USERNAME\":\"$USER\",\"PASSWORD\":\"$PASSWORD\"}" \
  --region "$AWS_REGION" | jq -r '.AuthenticationResult.AccessToken')

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
