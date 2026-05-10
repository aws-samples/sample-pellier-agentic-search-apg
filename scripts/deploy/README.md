# Module 05 — Ship It: Deploy to AgentCore

Deploy Pellier's multi-agent system to production using Amazon Bedrock AgentCore.

## What Gets Deployed

1. **3 Lambda MCP Servers** — Specialist tools packaged as Lambda functions:
   - `pellier-search-server` — Semantic search + inventory tools
   - `pellier-pricing-server` — Price analysis + deal finding
   - `pellier-recommend-server` — Personalized product recommendations

2. **AgentCore Gateway** — MCP Gateway that registers all 3 Lambda targets with:
   - Cognito JWT authentication
   - Semantic tool discovery
   - Tool schemas for each server

3. **AgentCore Runtime** — The orchestrator agent deployed as a managed runtime:
   - Discovers tools via Gateway
   - Routes queries to specialist agents
   - Persistent memory via AgentCore Memory

## Quick Deploy (15 min workshop version)

```bash
source deploy_all.sh
```

## Step-by-Step Deploy

```bash
# 1. Deploy Lambda MCP servers
uv run deploy_lambda.py --server-name pellier-search-server \
  --mcp-server-path pellier_search_server.py \
  --handler pellier_search_server.lambda_handler \
  --db-cluster-arn $PGHOSTARN --secret-arn $PGSECRET --database $PGDATABASE

# 2. Deploy Gateway
uv run deploy_gateway.py --gateway-name pellier-gateway \
  --search-lambda-arn $SEARCH_LAMBDA_ARN \
  --pricing-lambda-arn $PRICING_LAMBDA_ARN \
  --recommendation-lambda-arn $RECOMMENDATION_LAMBDA_ARN \
  --cognito-user-pool-id $COGNITO_POOL \
  --cognito-client-id $COGNITO_CLIENT

# 3. Configure + launch AgentCore Runtime
uv run agentcore configure --name pellier_orchestrator ...
uv run agentcore launch --agent pellier_orchestrator ...

# 4. Test
uv run test_runtime.py --prompt "Find me running shoes under $50"
```

## Files

| File                              | Purpose                                        |
| --------------------------------- | ---------------------------------------------- |
| `pellier_search_server.py`         | Lambda MCP server for search + inventory       |
| `pellier_pricing_server.py`        | Lambda MCP server for pricing                  |
| `pellier_recommend_server.py` | Lambda MCP server for recommendations          |
| `deploy_lambda.py`                | Lambda deployment script (adapted from DAT403) |
| `deploy_gateway.py`               | AgentCore Gateway deployment                   |
| `agentcore_runtime_adapter.py`    | Runtime entrypoint for AgentCore               |
| `deploy_all.sh`                   | End-to-end deployment script                   |
| `test_runtime.py`                 | Smoke tests for deployed agent                 |
| `requirements.txt`                | Runtime dependencies                           |
