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

   Docs: [Gateway overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)

3. **AgentCore Runtime** — The orchestrator agent deployed as a managed runtime:
   - Discovers tools via Gateway
   - Routes queries to specialist agents
   - Persistent memory via AgentCore Memory

   Docs: [Runtime overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)

## Prerequisites

The Workshop Studio AMI ships with the `@aws/agentcore` Node CLI preinstalled. Verify before starting:

```bash
which agentcore && agentcore --version   # /usr/local/bin/agentcore, v1.x
node --version                           # >= 20.x
```

If the CLI is missing (or you're testing a fresh AMI build):

```bash
npm install -g @aws/agentcore
```

CLI repo: https://github.com/aws/agentcore-cli

## Quick Deploy (15 min workshop version)

```bash
source deploy_all.sh
```

The `source` form is required — later steps consume env vars (`SEARCH_LAMBDA_ARN`, `MCP_GATEWAY_URL`, etc.) exported by earlier steps. Running with `bash deploy_all.sh` would silently lose those exports.

## Step-by-Step Deploy

```bash
# 1. Deploy Lambda MCP servers
uv run deploy_lambda.py --server-name pellier-search-server \
  --mcp-server-path pellier_search_server.py \
  --handler pellier_search_server.lambda_handler \
  --db-cluster-arn $PGHOSTARN --secret-arn $PGSECRET --database $PGDATABASE

# 2. Deploy Gateway (calls bedrock-agentcore-control:CreateGateway)
uv run deploy_gateway.py --gateway-name pellier-gateway \
  --search-lambda-arn $SEARCH_LAMBDA_ARN \
  --pricing-lambda-arn $PRICING_LAMBDA_ARN \
  --recommendation-lambda-arn $RECOMMENDATION_LAMBDA_ARN \
  --cognito-user-pool-id $COGNITO_POOL \
  --cognito-client-id $COGNITO_CLIENT

# 3. Scaffold + deploy via the @aws/agentcore Node CLI (0.18, CDK-based).
#    0.18 is a STATEFUL project model: create -> add agent -> deploy.
#    `add agent` sets entrypoint/protocol/CUSTOM_JWT via flags; executionRoleArn
#    + envVars have no flags, so we JSON-patch agentcore/agentcore.json after.
#    `deploy` runs from the PROJECT ROOT (dir containing agentcore/) and is
#    CDK-based, so the account must be `cdk bootstrap`-ed first.
#    The project roots at REPO level (../../.agentcore-project), NEVER inside
#    pellier/backend: the CodeZip packager copies the whole code-location, so a
#    project inside it copies itself recursively until ENAMETOOLONG.
#    deploy_all.sh automates all of this (steps 6-7); the manual gist:
ROOT=../../.agentcore-project/pellier
npx -y @aws/agentcore@0.18.0 create --project-name pellier --no-agent --defaults \
  --build CodeZip --language Python --framework Strands --model-provider Bedrock \
  --protocol HTTP --skip-git --skip-python-setup --skip-install \
  --output-dir ../../.agentcore-project --json
( cd "$ROOT" && npx -y @aws/agentcore@0.18.0 add agent --name pellier_orchestrator \
  --type byo --build CodeZip --language Python --framework Strands \
  --model-provider Bedrock --protocol HTTP \
  --code-location ../../pellier/backend --entrypoint agentcore_runtime.py \
  --authorizer-type CUSTOM_JWT --discovery-url "$OAUTH_ISSUER_URL/.well-known/openid-configuration" \
  --allowed-clients "$COGNITO_CLIENT" --json )
# patch executionRoleArn + envVars + runtimeVersion into agentcore/agentcore.json, then:
( cd "$ROOT" && npx -y @aws/agentcore@0.18.0 deploy -y --json )

# 4. Test the deployed Runtime
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
| `agentcore_runtime_adapter.py`    | Gateway-aware runtime entrypoint (alternate; not the deployed one) |
| `../../pellier/backend/agentcore_runtime.py` | **Deployed** BYO runtime entrypoint (in-process orchestrator) |
| `../../pellier/backend/pyproject.toml` | CodeZip deps for the BYO agent (0.18 uses uv, not requirements.txt) |
| `deploy_all.sh`                   | End-to-end deployment script                   |
| `test_runtime.py`                 | Smoke tests for deployed agent                 |
| `requirements.txt`                | Runtime dependencies                           |

## Where to look when something breaks

- **`agentcore deploy` fails with `AccessDenied` on `iam:PassRole`** — the calling principal needs permission to pass the AgentCore execution role. Workshop Studio CFN grants this; outside Workshop Studio, attach a policy that allows `iam:PassRole` on the role ARN in `agentcore.json`.
- **Gateway returns `401`** — Cognito access token expired (1-hour default). Re-run the `cognito-idp initiate-auth` block from `deploy_all.sh` step 7.
- **Runtime says `MCP_GATEWAY_URL not configured`** — the env-var patch into `agentcore/agentcore.json` ran before `MCP_GATEWAY_URL` was set. Re-export it and re-run the patch + `agentcore deploy` (deploy_all.sh step 6c-7).
- **`agentcore deploy` fails on a missing CDKToolkit / `cdk-hnb659fds` stack** — the account isn't CDK-bootstrapped. Run `npx -y aws-cdk@2 bootstrap aws://<account>/<region>` (bootstrap-environment.sh does this automatically on fresh accounts).
- **CloudWatch logs** — runtime invocations land in `/aws/bedrock-agentcore/runtimes/<runtime-id>`. Search by `session.id` to follow a single multi-step turn.

For the full step-by-step workshop testing guide (Runtime + Gateway + Memory), see `lab-content-audit.md` §20.
