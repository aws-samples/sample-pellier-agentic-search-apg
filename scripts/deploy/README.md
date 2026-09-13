# Deploy to AgentCore

Deploy Pellier's governed agent path using Amazon Bedrock AgentCore.

The pinned AgentCore CLI is the only control-plane deployment path for Runtime,
Memory, Gateway, Gateway target registrations, AgentCore-managed service roles,
the Policy engine, and Cedar policies. `deploy_lambda.py` creates the four
external Lambda functions and their Lambda execution roles; other Python
helpers seed Memory, authenticate test users, and verify the deployed path.

## What Gets Deployed

1. **4 Lambda MCP Servers** — 15 canonical tools packaged as Lambda functions:
   - `pellier-search-server` — Hybrid search + inventory tools
   - `pellier-pricing-server` — Price analysis + deal finding
   - `pellier-recommend-server` — Curation, preferences, and audit reads
   - `pellier-experience-server` — Returns and stylist escalation

2. **AgentCore Memory** — Short-term session events plus a
   `USER_PREFERENCE` semantic strategy.

3. **AgentCore Gateway** — MCP Gateway that registers all four Lambda targets with:
   - Cognito JWT authentication
   - Runtime tool discovery over MCP streamable HTTP
   - Exact parity with the governed 15-tool Gateway subset

   Docs: [Gateway overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)

4. **AgentCore Policy** — A managed Cedar engine attached to Gateway in
   `ENFORCE` mode:
   - Baseline permit for this Gateway's tool catalog
   - `initiate_return` allowed only for `reason == "damaged"`
   - Provisioning executes a real ALLOW and DENY before reporting ready

5. **AgentCore Runtime** — The orchestrator deployed as a managed HTTP runtime:
   - Requires a Cognito access token through `CUSTOM_JWT`
   - Discovers tools via Gateway
   - Fails closed if identity or Gateway is unavailable
   - Uses AgentCore Memory context supplied by the application request path

   Docs: [Runtime overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)

## Prerequisites

The Workshop Studio AMI ships with the pinned `@aws/agentcore` Node CLI. Verify before starting:

```bash
npx -y @aws/agentcore@0.29.0 --version
node --version  # >= 20.x
```

If the CLI is missing (or you're testing a fresh AMI build):

```bash
npm install -g @aws/agentcore@0.29.0
```

CLI repo: https://github.com/aws/agentcore-cli

## Quick Deploy (15 min workshop version)

```bash
source deploy_all.sh
```

Use `source` for interactive recovery so the final Runtime, Memory, Gateway,
and Policy identifiers remain in the current shell. Bootstrap invokes the
canonical Python provisioner directly and persists the same values to the
backend environment.

## Deployment Sequence

`deploy_all.sh` is the executable source of truth. It runs these phases:

1. Package and deploy the search, pricing, recommendation, and experience
   Lambda functions.
2. Scaffold one stateful `@aws/agentcore@0.29.0` project with
   `agentcore create`.
3. Render Runtime, Memory, Gateway, four Lambda target registrations, and the
   Policy engine into the CLI project. AgentCore role ARNs are intentionally
   omitted so CLI/CDK creates the managed service roles.
4. Run `agentcore validate` and `agentcore deploy`.
5. After Gateway has published its action catalog, render the baseline Cedar
   set and run the same validate/deploy sequence again.
6. Authenticate with Cognito, discover all 15 live MCP tools, seed Memory,
   prove Policy ALLOW/DENY, and invoke Runtime with `rail=gateway-mcp`.

For unattended bootstrap, use
`scripts/provision_agentcore_end_to_end.py`; it adds target/tool verification,
live Policy ALLOW/DENY proof, a customer-managed KMS key plus bounded retention
for the Runtime log group, and a structured readiness receipt. Its required
inputs include `AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN` and
`AGENTCORE_RUNTIME_LOG_RETENTION_DAYS` (a finite CloudWatch Logs retention
value, `30` in the workshop template).

## Files

| File                              | Purpose                                        |
| --------------------------------- | ---------------------------------------------- |
| `pellier_search_server.py`         | Lambda MCP server for search + inventory       |
| `pellier_pricing_server.py`        | Lambda MCP server for pricing                  |
| `pellier_recommend_server.py`      | Lambda MCP server for curation + evidence      |
| `pellier_experience_server.py`     | Lambda MCP server for returns + escalation     |
| `deploy_lambda.py`                | Lambda deployment script (adapted from DAT403) |
| `gateway_tool_schemas.py`         | Governed four-target, 15-tool Gateway subset   |
| `render_agentcore_project.py`     | Writes the declarative AgentCore CLI project   |
| `seed_agentcore_memory.py`        | Seeds managed preference records after deploy  |
| `gateway_initiate_return.py`       | Live ALLOW/DENY and JWT-bound receipt proof    |
| `../../pellier/backend/agentcore_runtime.py` | **Deployed** BYO Runtime entrypoint; JWT + Gateway required |
| `../../pellier/backend/pyproject.toml` | CodeZip dependencies for the BYO agent         |
| `deploy_all.sh`                   | Thin recovery wrapper around the provisioner   |
| `../provision_agentcore_end_to_end.py` | Canonical deploy and proof orchestration |
| `requirements.txt`                | Pinned deployment-helper dependencies          |

## Where to look when something breaks

- **`agentcore deploy` fails in CDK/IAM** — the CLI project deliberately omits
  `executionRoleArn`; CDK creates the Runtime and Gateway roles. Confirm the
  account is CDK-bootstrapped and the caller can assume/pass the
  `cdk-hnb659fds-*` deployment roles.
- **Gateway returns `401`** — Cognito access token expired (1-hour default). Re-run the `cognito-idp initiate-auth` block from `deploy_all.sh` step 7.
- **Runtime returns `managed_gateway_unavailable`** — `AGENTCORE_GATEWAY_URL` was absent or Gateway discovery failed. Repair the generated Runtime environment, redeploy, and rerun `npx -y @aws/agentcore@0.29.0 invoke --runtime pellier_orchestrator --bearer-token "$PELLIER_TOKEN" --prompt "Find linen pieces" --json`; do not enable a local fallback.
- **`agentcore deploy` fails on a missing CDKToolkit / `cdk-hnb659fds` stack** — the account isn't CDK-bootstrapped. Run `npx -y aws-cdk@2 bootstrap aws://<account>/<region>` (bootstrap-environment.sh does this automatically on fresh accounts).
- **Runtime traces** — run `npx -y @aws/agentcore@0.29.0 traces list --runtime pellier_orchestrator --limit 10 --since 1h --json`, then correlate on the session ID. Readiness requires correlated agent, model, and tool spans, per-step latency, matching Runtime builds, and content handling that matches the configured redaction mode. Redacted traces must not expose model or tool payloads.

Run `bash scripts/health-gate.sh` for the governed readiness verdict. It also
requires active Memory, exactly 180 warehouse rows, Policy `ENFORCE`, and the
structured provisioning receipt.
