# Deploy to AgentCore

Deploy Pellier's governed agent path using Amazon Bedrock AgentCore.

The pinned AgentCore CLI is the only control-plane deployment path for Runtime,
Memory, Gateway, Gateway target registrations, AgentCore-managed service roles,
the Policy engine, and Cedar policies. `deploy_lambda.py` creates the one
external Lambda function and its execution role; other Python helpers seed
Memory, authenticate test users, and verify the deployed path.

## What Gets Deployed

1. **One Lambda MCP server**, `pellier-store-tools-server`, behind the one
   Gateway target `pellier-store-tools`: nine tool schemas, eight published at
   baseline and nine after Lab 3A publishes `get_tickets`. The tools are the
   same `services/store_tools.py` functions the in-process agents call; the
   Lambda hands them the RDS Data API instead of the psycopg pool.

2. **AgentCore Memory**: short-term conversation events with 30-day expiry,
   plus `USER_PREFERENCE`, `SEMANTIC`, `SUMMARIZATION` and `EPISODIC` strategies.
   Bootstrap writes an isolated conversation, then requires extracted records
   to pass list, get-by-ID and retrieval checks in all four namespaces. Missing
   records, incomplete episodes, namespace drift or timeout fail readiness.
   The check does not write long-term records or reuse participant evidence.

3. **AgentCore Gateway**: an MCP Gateway that registers the one Lambda target with:
   - Cognito JWT authentication
   - Runtime tool discovery over MCP streamable HTTP
   - Discovery filtered by policy for the authenticated caller

   Docs: [Gateway overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)

4. **AgentCore Policy**: a managed Cedar engine attached to Gateway in
   `ENFORCE` mode:
   - Explicit permits for the six shopper-safe catalog reads and the
     owner-scoped customer reads (`get_orders`, and `get_tickets` once
     Lab 3A publishes it)
   - One staff-scoped permit for `give_store_credit`, with no amount limit
   - Lab 4's starter forbid, `workshop_credit_limit`, deployed from
     `workshop/starters/workshop_credit_limit.cedar` so every credit is denied
     until the participant writes the $100 limit; `--mode participant`
     refuses a rule `scripts/lab4_policy_check.py` marks CONTRADICTED
   - A managed output guardrail can suppress a tool response after execution
   - Provisioning's live policy proof calls the Gateway as Theo through
     `gateway_policy_probe.py`: a catalog read is allowed with its audit row,
     and a store credit is denied with no row

5. **AgentCore Runtime**: one managed runtime, `pellier_orchestrator`, running
   the Router and the Shopping, Stock and Support agents:
   - Invocation requires a Cognito access token through `CUSTOM_JWT`
   - The executing package carries a build fingerprint
   - Discovers tools via Gateway
   - Fails closed if identity or Gateway is unavailable
   - Uses AgentCore Memory context supplied by the application request path

   The Operator's investigation runs in the app, not on Runtime.

   Docs: [Runtime overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)

6. **AgentCore Observability**: Runtime and Gateway delivery, correlated agent,
   model and tool spans, CloudWatch Transaction Search, encrypted bounded logs,
   and control-plane audit. Readiness requires actual trace delivery.

Runtime and Gateway have service-managed workload identities. The workshop does
not configure outbound credential providers or managed AgentCore Evaluations.
See the [implementation and exercise map](../../docs/AGENTCORE-READINESS.md).

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

## Deployment and recovery

```bash
source deploy_all.sh
```

Use `source` for interactive recovery so the final Runtime, Memory, Gateway,
and Policy identifiers remain in the current shell. Bootstrap invokes the
canonical Python provisioner directly and persists the same values to the
backend environment.

## Deployment Sequence

`scripts/provision_agentcore_end_to_end.py` is the canonical orchestrator.
`deploy_all.sh` calls it. The full provisioning path runs these phases:

1. Package and deploy the store-tools Lambda function, with
   `services/store_tools.py` and its two retrieval modules staged into the zip.
2. Scaffold one stateful `@aws/agentcore@0.29.0` project with
   `agentcore create`.
3. Render Runtime, Memory, Gateway, the one Lambda target registration, and
   the Policy engine into the CLI project. AgentCore role ARNs are intentionally
   omitted so CLI/CDK creates the managed service roles.
4. Run `agentcore validate` and `agentcore deploy`.
5. After Gateway has published its action catalog, render the baseline Cedar
   set and run the same validate/deploy sequence again.
6. Authenticate with Cognito, verify the caller-scoped live catalog, prove
   extraction and retrieval for all four Memory strategies, invoke the
   Runtime, run the live policy proof, and verify correlated trace delivery.

For unattended bootstrap, use
`scripts/provision_agentcore_end_to_end.py`; it adds target/tool verification,
a customer-managed KMS key plus bounded retention
for the Runtime log group, and a structured readiness receipt. Its required
inputs include `AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN` and
`AGENTCORE_RUNTIME_LOG_RETENTION_DAYS` (a finite CloudWatch Logs retention
value, `30` in the workshop template).

## Files

| File                              | Purpose                                        |
| --------------------------------- | ---------------------------------------------- |
| `pellier_store_tools.py`          | The one Lambda MCP server: nine store tools on one target |
| `gateway_policy_probe.py`         | Calls one Gateway tool as a named Cognito user and reports the Cedar outcome and its rows |
| `gateway_client.py`               | Cognito tokens and the shared policy-denial classifier |
| `cognito_customer_claim.py`       | Pre-token trigger that stamps the customer and staff claims |
| `common/dataapi.py`               | RDS Data API runner and Bedrock embed/rerank for the Lambda |
| `deploy_lambda.py`                | Lambda deployment script (adapted from DAT403) |
| `gateway_tool_schemas.py`         | One-target catalog and participant publication boundary   |
| `render_agentcore_project.py`     | Writes the declarative AgentCore CLI project   |
| `seed_agentcore_memory.py`        | Proves all-four extraction, then seeds source conversations  |
| `verify_memory_readiness.py`    | Isolated real extraction, record-ID and namespace proof |
| `../../pellier/backend/agentcore_runtime.py` | **Deployed** BYO Runtime entrypoint; JWT + Gateway required |
| `../../pellier/backend/pyproject.toml` | CodeZip dependencies for the BYO agent         |
| `deploy_all.sh`                   | Thin recovery wrapper around the provisioner   |
| `../provision_agentcore_end_to_end.py` | Canonical deploy and proof orchestration |
| `requirements.txt`                | Pinned deployment-helper dependencies          |

## Where to look when something breaks

- **`agentcore deploy` fails in CDK/IAM**: the CLI project deliberately omits
  `executionRoleArn`; CDK creates the Runtime and Gateway roles. Confirm the
  account is CDK-bootstrapped and the caller can assume/pass the
  `cdk-hnb659fds-*` deployment roles.
- **Gateway returns `401`**: the Cognito access token expired (1-hour default). Mint a fresh one with `source ~/pellier-token.sh <user>`. A 401 is not a Cedar DENY.
- **Runtime returns `managed_gateway_unavailable`**: `AGENTCORE_GATEWAY_URL` was absent or Gateway discovery failed. Repair the generated Runtime environment, redeploy, and rerun `npx -y @aws/agentcore@0.29.0 invoke --runtime pellier_orchestrator --bearer-token "$PELLIER_TOKEN" --prompt "Find linen pieces" --json`; do not enable a local fallback.
- **`agentcore deploy` fails on a missing CDKToolkit / `cdk-hnb659fds` stack**: the account isn't CDK-bootstrapped. Run `npx -y aws-cdk@2 bootstrap aws://<account>/<region>` (bootstrap-environment.sh does this automatically on fresh accounts).
- **Runtime traces**: run `npx -y @aws/agentcore@0.29.0 traces list --runtime pellier_orchestrator --limit 10 --since 1h --json`, then correlate on the session ID. Readiness requires correlated agent, model, and tool spans, per-step latency, matching Runtime builds, and content handling that matches the configured redaction mode. Redacted traces must not expose model or tool payloads.

Run `bash scripts/health-gate.sh` for the governed readiness verdict. It also
requires all four Memory strategies with the expected configuration and a
complete extraction receipt, exactly 300 warehouse rows, Policy `ENFORCE`,
and the structured provisioning receipt.
