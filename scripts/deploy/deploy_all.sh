#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Pellier — Deploy All to AgentCore
#
# Deploys 3 Lambda MCP servers, creates AgentCore Gateway, configures and
# launches the orchestrator agent on AgentCore Runtime.
#
# Prerequisites (set by CloudFormation outputs):
#   PGHOSTARN, PGSECRET, PGDATABASE, AWS_REGION,
#   COGNITO_POOL, COGNITO_CLIENT, AGENTCORE_ROLE_ARN, STACKNAME
#
# Usage:
#   source deploy_all.sh
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
echo "=== [1/7] Deploying Search Lambda ==="
uv run "$SCRIPT_DIR/../05/deploy_lambda.py" \
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
echo "=== [2/7] Deploying Pricing Lambda ==="
uv run "$SCRIPT_DIR/../05/deploy_lambda.py" \
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
echo "=== [3/7] Deploying Recommendation Lambda ==="
uv run "$SCRIPT_DIR/../05/deploy_lambda.py" \
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
# 4. Deploy AgentCore Gateway
# ------------------------------------------------------------------
echo ""
echo "=== [4/7] Deploying AgentCore Gateway ==="
uv run "$SCRIPT_DIR/deploy_gateway.py" \
  --gateway-name pellier-gateway \
  --search-lambda-arn "$SEARCH_LAMBDA_ARN" \
  --pricing-lambda-arn "$PRICING_LAMBDA_ARN" \
  --recommendation-lambda-arn "$RECOMMENDATION_LAMBDA_ARN" \
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
# 5. Configure AgentCore Runtime
# ------------------------------------------------------------------
echo ""
echo "=== [5/7] Configuring AgentCore Runtime ==="

# Get OAuth issuer URL for Cognito
export OAUTH_ISSUER_URL="https://cognito-idp.${AWS_REGION}.amazonaws.com/${COGNITO_POOL}"

uv run agentcore configure \
  --name pellier_orchestrator \
  --protocol HTTP \
  --entrypoint "$SCRIPT_DIR/agentcore_runtime_adapter.py" \
  --requirements-file "$SCRIPT_DIR/requirements.txt" \
  --non-interactive \
  --region "$AWS_REGION" \
  --execution-role "$AGENTCORE_ROLE_ARN" \
  --authorizer-config "{\"customJWTAuthorizer\": {\"discoveryUrl\": \"$OAUTH_ISSUER_URL\", \"allowedClients\": [\"$COGNITO_CLIENT\"]}}"

# ------------------------------------------------------------------
# 6. Launch AgentCore Runtime (~5 min)
# ------------------------------------------------------------------
echo ""
echo "=== [6/7] Launching AgentCore Runtime (this takes ~5 minutes) ==="
uv run agentcore launch \
  --agent pellier_orchestrator \
  --env MCP_GATEWAY_URL="$MCP_GATEWAY_URL" \
  --env AGENT_MODEL_ID="global.anthropic.claude-opus-4-6-v1"

echo "  ✅ Agent deployed!"

# ------------------------------------------------------------------
# 7. Smoke Tests
# ------------------------------------------------------------------
echo ""
echo "=== [7/7] Running Smoke Tests ==="

# Get Cognito credentials
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
