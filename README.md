# Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore

<div align="center">

_A retail search workshop where every answer has evidence and every sensitive action has a boundary._

<br/>

[![Workshop: Level 400](https://img.shields.io/badge/Workshop-Level_400-7A263A?style=flat-square)](#workshop-path)
[![Aurora PostgreSQL 18.3](https://img.shields.io/badge/Aurora_PostgreSQL-18.3_and_pgvector-2D72D9?style=flat-square&logo=postgresql&logoColor=white)](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
[![Bedrock AgentCore](https://img.shields.io/badge/Bedrock-AgentCore-FF9900?style=flat-square)](https://aws.amazon.com/bedrock/agentcore/)
[![Strands Agents](https://img.shields.io/badge/Strands-Agents_SDK-232F3E?style=flat-square)](https://strandsagents.com)
[![MCP](https://img.shields.io/badge/MCP-postgres--mcp--server-4A154B?style=flat-square)](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server)
[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![React and TypeScript](https://img.shields.io/badge/React-TypeScript-3178C6?style=flat-square&logo=react&logoColor=white)](pellier/frontend/package.json)
[![Governed quality](https://github.com/aws-samples/sample-pellier-agentic-search-apg/actions/workflows/quality.yml/badge.svg?branch=governed)](https://github.com/aws-samples/sample-pellier-agentic-search-apg/actions/workflows/quality.yml?query=branch%3Agoverned)
[![Deployment E2E](https://github.com/aws-samples/sample-pellier-agentic-search-apg/actions/workflows/e2e.yml/badge.svg?branch=governed)](https://github.com/aws-samples/sample-pellier-agentic-search-apg/actions/workflows/e2e.yml?query=branch%3Agoverned)

[![License: MIT](https://img.shields.io/badge/License-MIT-54644D?style=flat-square)](LICENSE)

</div>

> Educational reference implementation for a governed agentic AI search workshop.
> Not intended for production deployment without security hardening.

**Contents:** [Workshop abstract](#workshop-abstract); [Who this is for](#who-this-is-for); [What this is](#what-this-is); [Closed loop](#shopper-to-operator-closed-loop); [Governance model](#governance-model); [Personas](#personas-reshape-everything); [Quick start](#quick-start-local-dev); [Workshop path](#workshop-path); [Architecture](#architecture); [Quality gates](#quality-gates); [Repository layout](#repository-layout); [Resources](#resources)

Start with the [four-lab teaching map](WORKSHOP.md). It connects each person,
question, and build to the evidence you should inspect. The **`governed` branch**
is the 100-minute workshop; `main` serves the shorter builders session.

The quality badge reports GitHub's branch checks. Deployment E2E is a separate,
manually triggered check against a real Workshop Studio environment. Neither
badge reports the health of your local preview.

---

## Workshop abstract

Build a retail assistant that finds relevant products, checks live stock, and
knows when a person must review an action. A Strands dispatcher sends each
shopper question to a specialist. Aurora PostgreSQL combines full-text search,
pgvector, and Cohere Rerank, and stores the inventory, orders, customer records,
and JSONB audit ledger behind each answer.

Use AgentCore Runtime to run agents, Memory to preserve conversation context,
Gateway to expose tools, and Policy to authorize published tool calls with
Cedar. Follow a proposed action through human review, database enforcement,
and recorded evidence. Leave with patterns you can reuse and a clear way to
prove what each layer did. Bring your laptop to participate.

---

## Workshop Studio and Pellier

Workshop Studio owns the participant instructions, commands, checkpoints,
recovery steps, and cleanup. Pellier's Lab Collection is a concise launchpad
for the four customer scenarios and their evidence. It opens each lab in
Workbench; it does not duplicate the Studio guides.

Workbench shows the request, evidence ledger, and answer side by side when
space allows. On narrower screens it uses panel navigation automatically.
Both layouts expose the same capabilities and evidence.

## Who this is for

This is a **Level 400 (expert)** workshop. The code edits are small; the reasoning
is deep. You will compare retrieval quality, trace identity across services,
test authorization boundaries, and prove whether an action reached the database.

**You will be comfortable here if you:**
- Read Python and SQL (you don't need to write much of either)
- Have used a REST API and a terminal before
- Know, at a high level, what an LLM and a vector embedding are

**You do *not* need to:** build a search system from scratch, know Strands/AgentCore/MCP in advance, or have prior agentic-AI experience. We teach those during the session.

**What you will build.** Each lab contains two coding exercises, `a` and `b`: eight builds in total. You edit a marked region in a supplied application, then run checks against its services and database. The environment is deployed before the workshop so you can focus on retrieval, identity, memory, and controlled actions. Each build includes a catch-up reference under `solutions/`. The L400 work is deciding which component owns a decision and checking the evidence that supports it.

| Build | You author | In |
|---|---|---|
| **1a** | the Inventory Agent definition | `pellier/backend/agents/inventory_agent.py` |
| **1b** | the `check_inventory` tool body | `pellier/backend/services/agent_tools.py` |
| **2a** | the Reciprocal Rank Fusion expression | `workshop/lab-2-rrf.sql` |
| **2b** | the live pre-rerank candidate budget | `pellier/backend/services/planned_hybrid_retrieval.py` |
| **3a** | publishing the Gateway tool the specialist needs | `scripts/deploy/gateway_tool_schemas.py` |
| **3b** | reconciling the Runtime catalogue with the Gateway | `pellier/backend/services/agentcore_gateway.py` |
| **4a** | the identity-to-customer Cedar rule | `policies/workshop_identity_match_forbid.cedar` |
| **4b** | the keyed absence query that proves a denial did nothing | `workshop/lab-4-absence.sql` |

`workshop/lab-4-rls.sql` is a **proof** artifact, not a build: Lab 4 runs it to
show PostgreSQL refusing another shopper's rows. `scripts/build_receipt.py`
grades all eight regions above, so `receipt` is the fastest check on which ones
are still starters.

Each lab has two small builds and a documented recovery path. Predict what
should happen, run the request, and check the evidence. A convincing answer
alone does not prove retrieval quality, authorization, or a completed write.

---

## What this is

**Pellier is a fictional artisan retailer** with one promise: a shopper asks
for something in their own words, and the search understands what they mean.
Behind the storefront, specialist agents ground answers in retrieved catalog
data, read live inventory through deterministic tools, preserve useful context,
cite sources, and hand off to a human stylist when they should.

The application has three connected surfaces:

- **Pellier** (`/`) – the customer-facing storefront. Editorial photography, AI search, persona-aware recommendations, and a conversational drawer.
- **Pellier Operator** (`/operator`) – the authenticated client desk. A two-agent Strands graph separates case investigation from resolution planning; durable reviews, human decisions, and governed execution stay outside the graph invocation.
- **Pellier Observatory** (`/observatory`) – the live inspection surface. It exposes both production orchestration paths and reconstructs the shopper handoff, pending review, graph artifact, human decision, and execution evidence from their owning records.

Both Operator sign-in buttons lead to one dedicated **Pellier sign-in page**
(`/signin`). The signed-out Operator welcome remains the entry point; it does
not contain a second password form. After sign-in, the app returns you to the
client or review you opened.

The Observatory Workbench adapts to the available screen width. The Lab Collection
opens each lab’s scenario and evidence; Workshop Studio owns the instructions. Guided questions
include a prediction to make and a result to inspect; they are prompts to run,
not prerecorded proof.

The surfaces share design tokens and a typed agent vocabulary, so an attendee
crossing between them sees the same system rather than three unrelated demos.

The storefront also includes a dismissible, once-per-session four-step
orientation covering browse, profile, concierge, and evidence inspection. It
never mounts over Pellier Observatory, where the proof surface itself provides the
workshop orientation.

### What it demonstrates

Every claim in the workshop abstract maps to something runnable in this repo:

| Claim | Where it lives |
|---|---|
| **Grounded retrieval** on **Aurora PostgreSQL** | `pellier.product_catalog.embedding vector(1024)`; pgvector 0.8.1; HNSW index; `<=>` cosine operator; hybrid (FTS + RRF) merge; Cohere Rerank v3.5 |
| **Agentic AI – reasoning + tool use** | Strands Agents SDK; deterministic Storefront Dispatcher routes intent to one of 5 specialists; each specialist receives an explicit tool allowlist; Operator Concierge uses `GraphBuilder` for an ordered Case Investigator -> Resolution Planner graph |
| **Model Context Protocol (MCP)** | [`awslabs.postgres-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server) installed via `uvx`, read-only against the Aurora cluster ARN; `pellier/config/mcp-server-config.json` is the literal contract; any MCP host (VS Code chat extension, Claude Code, Strands `MCPClient`, AgentCore Gateway) consumes the same JSON |
| **Managed tool catalog (AgentCore Gateway)** | `services/agentcore_gateway.py` lists the Gateway catalog via `MCPClient.list_tools_sync()`, then selects the routed specialist's explicit allowlist; governed Runtime requests pass the shopper's access token through (`Authorization: Bearer`) and fail closed if Gateway is unavailable |
| **Memory and personalization** | The [Memory experiment](docs/MEMORY_SHOWCASE.md) uses an extracted preference in a new conversation in Lab 3. Participants inspect facts, preferences, and summaries; episodic extraction is optional. Aurora supplies current business records, and reviewed runtime skills supply instructions. |
| **Managed AgentCore path** | One `@aws/agentcore@0.29.0` project owns Runtime, Memory, Gateway, four Lambda target registrations, AgentCore-managed service roles, the Policy engine, and Cedar policies; `deploy_lambda.py` separately creates the external Lambda functions and their Lambda execution roles; `@app.entrypoint` in `pellier/backend/agentcore_runtime.py`; CUSTOM_JWT invocation must return `rail=gateway-mcp`; encrypted, retention-bounded Runtime and trace log groups carry correlated agent, model, and structured tool spans |
| **Durable human handoff** | The shopper turn stores an immutable, explicitly untrusted `handoff_context` beside its terminal receipt; `pellier.approvals` owns the pending review and exact action hash; the graph persists only operator-safe artifacts; confirmation and execution are later authenticated requests |

### Shopper-to-operator closed loop

The customer and operator experiences share durable business state, not model
memory or an in-process callback. A storefront specialist can prepare a bounded
proposal, but it cannot approve or execute it:

```text
shopper request
  -> Storefront Dispatcher selects one specialist
  -> PostgreSQL stores an immutable, untrusted handoff
  -> PostgreSQL stores a pending review and exact action hash

authorized operator opens the review
  -> Case Investigator Agent reads current evidence
  -> Resolution Planner Agent proposes a bounded resolution
  -> PostgreSQL stores the operator-safe graph artifact

separate authenticated requests
  -> human confirms or declines the exact action hash
  -> a confirmed, published action enters AgentCore Gateway and Policy
  -> PostgreSQL enforces the write and stores the outcome evidence
  -> Observatory reconstructs the complete lineage
```

This is intentionally not one long-running agent invocation. The Strands graph
ends after investigation and planning; human decision, policy authorization,
database enforcement, and outcome evidence remain separate, replayable
boundaries. `initiate_return` follows that complete managed path.
`issue_credit` is published for the operator desk only: its Cedar permit requires
the staff scope claim, no shopper permit names it, and no shopper-facing
specialist binds it. The desk executes an approved credit through the Gateway
with the operator's own token. See [WORKSHOP.md](WORKSHOP.md) for the Marco,
Anna, Theo, Jessica, and guest journeys that teach this pattern.

## Governance model

Pellier treats governance as several enforcement and evidence boundaries, not
as one policy engine:

| Boundary | Current implementation | What it proves |
|---|---|---|
| Identity | Cognito JWT verified on the managed rail | Which authenticated human initiated the request |
| Managed execution | AgentCore Runtime with JWT passthrough | Which orchestrator ran and on which managed rail |
| Tool contract | AgentCore Gateway defines 18 target-qualified MCP tools, 16 published at the start and 17 after Lab 3a; discovery is caller-scoped | Which callable capability and input schema the agent received |
| Authorization | AgentCore Policy evaluates Cedar before Gateway target execution | Which of five states the call reached: `ALLOW`, `DENY`, `WOULD_DENY` (a real LOG_ONLY decision flip), `EVALUATION_INCOMPLETE` (the engine could not be read), or `POLICY_INFERRED` (a match against policy text, which is never presented as a decision) |
| Output control | A managed `suppressOutput` policy checks the staff credit response for email addresses | A withheld response does not undo the tool's committed effect. The configured MCP output path and provider response require fresh-account rehearsal. |
| Data authorization | Aurora SQL functions validate ownership and write invariants | Which records the permitted tool could actually read or mutate |
| Row-level authorization | PostgreSQL RLS policies on `orders` and `returns`, enforced against the `pellier_agent` and `pellier_query` roles (neither holds `BYPASSRLS`) and scoped by the `pellier.principal_sub` GUC through `pellier.principal_customers` | That a permitted tool holding a valid token still cannot read another shopper's rows, enforced by the database rather than by application code |
| Generated-SQL authorization | `services/governed_query.py` wraps model-generated SQL as a subquery, inspects the plan with `EXPLAIN (FORMAT JSON, VERBOSE)`, and executes read-only under a statement timeout, fixed `search_path`, schema allowlist, and row cap | That structure and privilege, not prompt wording, decide what a natural-language question may reach |
| Application evidence | `pellier.governed_receipts`, `pellier.tool_audit`, `pellier.governed_turn_receipts`, `pellier.governed_query_receipts`, `pellier.retrieval_receipts`, `pellier.policy_decisions`, `pellier.workshop_runs`, and the inventory ledger | Which decision was made, which tool ran, and what reached Aurora |
| Evidence immutability | Migration 047 makes `governed_receipts` and `execution_receipts` append-only by trigger, and lets `tool_audit` and `write_operations` be filled exactly once, with the unrestricted UPDATE grant revoked | That a receipt cannot be edited after the fact by the application that wrote it |
| Fail-closed writes | In governed format a write refuses when the Gateway URL, the access token, or the policy engine is missing, recording a receipt with rail `refused` and returning HTTP 409 | That an ungoverned write is refused and recorded, rather than quietly falling back to the in-process rail |
| Commerce execution | Aurora quotes, confirmation grants, reservations, payment events, outbox rows, and immutable commerce receipts | Which authenticated shopper confirmed which total, what inventory moved, and which payment state completed |

Pellier is not merely conversational commerce. It is proof-carrying commerce:
an agent can recommend pieces and prepare a cart, but it cannot complete a
purchase. Cognito identity, a short-lived server-priced quote, explicit shopper
consent, deterministic shipping and tax rules, idempotent execution, sandbox
payment state, and durable Aurora evidence determine what actually executes.
Each idempotency key is bound to one confirmation grant, and the immutable
receipt hashes the purchased line snapshot alongside identity, consent,
inventory, payment, and outbox evidence. The API recomputes that hash when the
receipt is read. The sandbox adapter is intentionally labeled in the API and
storefront; this sample does not claim to process cards or move money.

Glue Data Catalog, Amazon DataZone, and SageMaker governance are deliberately
outside this execution boundary. They can govern analytical data products,
catalog metadata, and model development, but they do not prove that a shopper
confirmed a specific total or that an order, payment state, and inventory
movement agree. Adding them to the required path would broaden the architecture
without strengthening the transaction claim.

The observability provisioner changes account-level X-Ray Transaction Search
delivery and creates three workshop log groups. Inspect the bounded cleanup plan
before an event account is retired, then run it while the workshop role still
exists:

```bash
python3 scripts/teardown_agentcore_observability.py --dry-run
python3 scripts/teardown_agentcore_observability.py --confirm-workshop-cleanup
```

The receipt records the prior account-level destination, resource policy, KMS,
and retention state. Cleanup restores resources that already existed and
deletes only log groups or policy state created by this workshop run.

### Memory model

Pellier uses conversation context, business records, and reviewed instructions.
Each has a different owner and identity scope. A remembered preference can guide
a recommendation; its price, stock, and permitted actions require current evidence.

| Records | Owner | Keyed by | Lifetime | What participants check |
|---|---|---|---|---|
| **Conversation events** | AgentCore Memory | actor and session | 30-day event expiry | The first conversation is recorded; the new conversation has zero prior chat events |
| **Learned preferences and facts** | AgentCore Memory `USER_PREFERENCE` and `SEMANTIC` strategies | actor | stored beyond one session | An extracted preference is supplied to the new conversation and used in a recommendation |
| **Summaries and optional episodes** | AgentCore Memory `SUMMARIZATION` and `EPISODIC` strategies | configured actor and session namespaces | stored beyond one session | Returned records and their IDs; an active strategy alone does not establish extraction |
| **Business records and execution evidence** | Aurora products, inventory, orders, returns, and audit tables | product, customer, action, and turn identifiers | database retention policy | Current product facts, authorized business changes, and keyed evidence |
| **Runtime instructions** | Checked-in skills and MCP tool schemas | file path | changes with the deployed artifact | Reviewed instructions and accepted tool arguments |

Lab 3 keeps one verified actor across two different session IDs. It retrieves
extracted records without loading the earlier conversation. Regular Storefront
calls retain their existing conversation-specific actor scope; this exercise
makes the separate identity choices visible.

Extraction runs asynchronously. Check strategy state, namespace, and returned
record IDs before claiming a preference was learned. The optional AgentCore
`EPISODIC` strategy is separate from Aurora's curated `customer_episodic_seed`
rows. Memory supplies context; authorization and database checks still control
which records a caller can read and which actions can commit.

`pellier.tool_audit` is intentionally outside that table. It records what
executed and how long it took; it does not teach the agent how to work. When
managed Runtime is enabled, AgentCore Memory reads fail closed before
invocation. A post-invocation Memory write failure is surfaced as partial
evidence without recasting an action that may already have executed as failed.
The governed path never substitutes a process-local store for managed proof.

Pellier Observatory provides the operator reconstruction layer: one correlated policy,
execution, trace, and Aurora data story for a selected turn.

The durable join is intentionally small. `session_id` follows the conversation
and managed invocation, `turn_id` follows an application turn, `receipt_id`
identifies the policy record, and `audit_id` links an ALLOW to the Aurora tool
row. A DENY has no `audit_id`; the absence is proof only after the receipt
helper verifies that no matching execution row exists.

Column protection, pgAudit, CloudTrail, and Dogwood temporal policy are
documented production layers, not hidden claims about this sample. The required
workshop does not configure them. Row-Level Security is the exception and is
**not** in that list: migration `016_runtime_roles_rls.sql` ships it, and Lab 4
step 5 runs `workshop/lab-4-rls.sql` to prove PostgreSQL refuses another
shopper's rows even for a permitted tool holding a valid token. The checked-in
[`advanced_verified_customer_context.dogwood`](policies/advanced_verified_customer_context.dogwood)
shows how a session-history rule could require a successful context lookup
before a sensitive write. It also states the critical permit interaction:
Pellier's broad workshop permit must be narrowed before that rule can enforce
the sequence.

---

## Personas reshape everything

Choose Marco, Anna, or Theo to change the storefront's photograph, suggestions,
featured piece, curated products, and concierge greeting. **Choosing a scenario
does not sign you in as that customer.** Account reads and actions require the
matching verified Cognito identity.

| Persona  | Profile                          | Signature piece              |
| -------- | -------------------------------- | ---------------------------- |
| *Marco*  | Natural fibers, travel, linen    | Italian Linen Camp Shirt     |
| *Anna*   | Gifts, milestones, candles       | Beeswax Taper Candles        |
| *Theo*   | Slow craft, ceramics, ritual     | Stoneware Pour-Over Set      |

Jessica is the Lab 4 service-recovery case in Operator. She is not a fourth
storefront scenario. A separate account in the `pellier-operators` Cognito group
opens the staff desk.

The **signed-out state** is the editorial baseline – a nine-piece grid anchored by the Nocturne Leather Weekender, no prior context, no profile embedding. It is the hero state, not a fourth persona.

Each of the three personas ships with 10 curated products carrying real Cohere
Embed v4 1024-dim embeddings, alongside 10 pieces for the signed-out edit, 10
house pieces the client book owns, and 10 signature investment pieces. Those 60
story products stay stable for persona
grids, orders, inventory, and policy exercises. The governed retrieval lab
expands `pellier.product_catalog` to 1,000 rows with generated high-ID archive
distractors and deterministic derived vectors. The extra rows create enough
near-miss candidates to compare retrieval strategies without adding 940 images
or concepts for participants to learn. They are excluded from shopper-facing
tools and included only by the evaluation path.

This split is deliberate, not a scale benchmark: 60 products are the
participant-facing domain; 1,000 rows are a compact retrieval test corpus.
Pellier does not use that corpus to teach HNSW capacity planning. That deeper
retrieval-engineering work belongs in the separate Mosaic Builder Session.

---

## Quick start (local dev)

Start from the repository root with Python 3.14, Node.js 20 or newer, `psql`,
and AWS credentials for the workshop account. A private Aurora connection also
needs AWS CLI, the Session Manager plugin, `jq`, and `lsof`.

The production flow is a single FastAPI process on `:8000` serving both the built React SPA and the API. For interactive frontend work, `npm run dev` starts an isolated Pellier API on `:8003`, waits for it to become healthy, then starts Vite on `:5173` with a same-origin API proxy. When the configured Aurora cluster is private and its security group names a Pellier SSM tunnel, the launcher opens that approved tunnel and reads its database credentials from the configured Secrets Manager ARN. This keeps Aurora private and prevents another local workshop using `:8000` from being mistaken for Pellier.

The local launcher reconnects the Aurora tunnel when a Session Manager session
ends, including after inactivity. It retries with a delay of 5–60 seconds and
keeps the same local database port. AWS credentials must remain valid; failures
and retry delays appear in the development log.
The backend checks pooled connections before use, replacing stale sockets before
handing them to a query.
The launcher reads the database secret at startup. If the Aurora password rotates
while it is running, stop and restart `npm run dev` to load the current secret.

```bash
# 1. Install dependencies in the local environments
(cd pellier/backend && python3 -m venv .venv && \
  ./.venv/bin/python -m pip install --require-hashes -r requirements.lock)
(cd pellier/frontend && npm ci)

# 2. Aurora + Bedrock credentials
cp pellier/backend/.env.example pellier/backend/.env
# edit DB_HOST, DB_USER, DB_PASSWORD, AWS_REGION, BEDROCK_*
set -a; source pellier/backend/.env; set +a

# 3. Apply schema + seed catalog + required workshop tables (one-time)
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
  -U "$DB_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 \
  -f scripts/migrations/001_schema.sql
pellier/backend/.venv/bin/python scripts/seed_pellier_catalog.py --from-cache
for migration in \
  002_workshop_telemetry.sql \
  003_persona_seed.sql \
  004_anna_hybrid_search.sql \
  005_theo_returns.sql \
  006_warehouse_inventory.sql \
  007_chat_session_tables.sql \
  008_search_performance_indexes.sql \
  009_return_policies.sql \
  010_governed_receipts.sql \
  011_governed_write_integrity.sql \
  012_retrieval_receipts.sql \
  013_inventory_ledger.sql \
  014_governed_turn_receipts.sql \
  015_proof_carrying_commerce.sql \
  016_runtime_roles_rls.sql \
  017_governed_query_receipts.sql \
  018_client_book.sql \
  019_operator_desk.sql \
  020_operator_review.sql \
  021_governed_execution.sql \
  022_write_operation_vocabulary.sql \
  023_idempotency_claims_release_on_failure.sql \
  024_operator_episodes.sql \
  025_execution_receipts.sql \
  026_episode_outcome_lineage.sql \
  027_canonical_span_table.sql \
  028_shopper_operator_handoff.sql \
  029_live_surface_data.sql \
  030_storefront_editorial_order.sql \
  031_refine_fresh_storefront_edit.sql \
  032_restore_fresh_runner_edit.sql \
  033_extend_curated_inventory.sql \
  034_refine_persona_personalities.sql \
  035_expand_persona_discovery_grids.sql \
  036_refresh_persona_hero_alt_text.sql \
  037_serve_persona_hero_masters.sql \
  038_principal_customer_cardinality.sql \
  039_return_replay_scope.sql \
  040_resequence_theo_governed_turn.sql \
  041_align_theo_pairing_preview.sql \
  042_align_anna_guided_previews.sql \
  043_evidence_ledger.sql \
  044_operator_lifecycle_ledger.sql \
  045_persona_blurbs.sql \
  046_retrieval_citation_snapshots.sql \
  047_evidence_immutability.sql \
  048_policy_decisions.sql \
  049_workshop_runs.sql \
  050_refine_guided_questions.sql
do
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f "scripts/migrations/$migration"
done

# 4. HMR development stack
cd pellier/frontend
npm run dev        # API on :8003, Vite on :5173
```

For a production-style local run, build the frontend, then start FastAPI on
`:8000`:

```bash
cd pellier/frontend
npm run build
cd ../backend
./.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

With the production build, open <http://localhost:8000>,
<http://localhost:8000/operator>, or <http://localhost:8000/observatory>.
With `npm run dev`, use the same paths on <http://127.0.0.1:5173>.

To keep this preview separate from another frontend, run from `pellier/frontend`:

```bash
npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

Then open <http://127.0.0.1:5175>. Vite forwards `/api` to the isolated backend
on port 8003.

### Sign-in setup

Configure the backend's `COGNITO_POOL_ID`, `COGNITO_CLIENT_ID`, and
`COGNITO_DOMAIN`. The dedicated page uses Cognito's `USER_PASSWORD_AUTH` flow;
the app client must enable `ALLOW_USER_PASSWORD_AUTH`. Password recovery stays
with Cognito. Accounts that need another challenge can continue through the
hosted sign-in flow.

For the port-5175 preview, set `APP_BASE_URL=http://127.0.0.1:5175` and
`OAUTH_REDIRECT_URI=http://127.0.0.1:5175/api/auth/callback`. Register that callback
and the corresponding sign-out URL on the Cognito app client. Use HTTPS for
deployed sites; authentication uses Secure, HttpOnly cookies.

Use the account supplied by your facilitator. Operator access requires membership
in `pellier-operators`; a successful customer sign-in does not grant staff access.
Passwords and access tokens do not belong in the README or committed files.

### Local PostgreSQL journey rehearsal

After migrations `001-030` and the catalog seed have been applied to a local
`pellier_dev` database, prepare the Theo shopper-to-operator checkpoint and
survey Jessica's deliberately contradictory evidence:

```bash
# Read-only survey of the current local state.
python3 scripts/seed_local_golden_journeys.py

# Add only Theo's pending review and immutable shopper handoff.
python3 scripts/seed_local_golden_journeys.py --apply

# Verify the resulting local state.
python3 scripts/seed_local_golden_journeys.py
```

The helper refuses non-loopback hosts and database names that do not end in
`_dev`. It never confirms or executes the review and never writes an AgentCore
or Cedar verdict. Local PostgreSQL proves the application workflow and durable
lineage; the managed Runtime, Gateway, Memory, and Policy proofs still require
the workshop AWS environment.

### AgentCore CLI (pinned)

Pellier uses the Node-based AgentCore CLI (`@aws/agentcore`, Node.js ≥ 20), **pinned to the version this workshop is tested against**:

```bash
npx -y @aws/agentcore@0.29.0 --version
cd .agentcore-project/pellier
npx -y @aws/agentcore@0.29.0 validate --json
npx -y @aws/agentcore@0.29.0 deploy --yes --json
```

The workshop bootstrap installs the same pin globally and provides an
`agentcore` shell function for inspection and participant policy changes. The
CLI is the only control-plane authority for AgentCore resources in this repo.
`deploy_lambda.py` separately creates the external Lambda functions and their
Lambda execution roles. Other Python and AWS CLI helpers remain limited to
authentication, Memory data seeding, and post-deploy verification.

Claude Code is a separate participant helper. Bootstrap installs the latest
CLI release without a package-version pin and uses its `sonnet` alias through
Amazon Bedrock, so the helper follows the current Sonnet model available at
workshop time. Pellier's application model IDs remain explicit because the
preflight invokes those exact profiles before declaring the environment ready.

### Facilitator note: `SPA_MOUNT_PATH`

By default the SPA is served at `/`. The nginx layer ([`scripts/bootstrap-environment.sh:339-340`](scripts/bootstrap-environment.sh#L315-L324)) strips the `/app/` prefix (`proxy_pass http://127.0.0.1:8000/`) before forwarding to FastAPI, so root-mount works behind both Workshop Studio's `/ports/8000/*` proxy and the `/app/*` shortcut. If you ever deploy behind a proxy that forwards `/app/*` verbatim (no prefix-stripping), set:

```bash
SPA_MOUNT_PATH=/app
VITE_BASE_PATH=/app/   # bake the prefix into the bundle at build time
```

The app moves to `/app/`, `GET /app` 307-redirects to `/app/`, and the real API stays at `/api/*`. Do not register new FastAPI routes below the SPA catch-all – its `{full_path:path}` pattern shadows everything under the mount.

---

## Workshop path

This repo contains the application for the **Level 400 governed agentic AI search workshop**. Participants build a grounded agent, measure hybrid retrieval, deploy through AgentCore, and govern actions with Cedar. They verify each outcome against service responses and database records, including a learned preference used in a new conversation. Workshop Studio holds the participant instructions and timing.

The session content (lab manual, CloudFormation, prereq images) lives in the separate Workshop Studio repository, which is the single source of truth for everything under its `content/`, `assets/`, and `static/` trees. This repo holds the running application the session is built on. The flagship path is structured as:

| Section | What attendees do |
|---|---|
| Introduction | Open Code Editor and Pellier, record a run ID, check Aurora and the predeployed Runtime, and save Theo's first conversation for AgentCore Memory extraction. |
| Lab 1: Build a PostgreSQL-Grounded Agent | Complete Inventory Agent and `check_inventory`, then prove Marco's answer against live inventory and `tool_audit`. |
| Lab 2: Build and Measure PostgreSQL Hybrid Retrieval | Read the SQL query plan, reconstruct RRF, and widen the live candidate budget. Compare exact candidate IDs before and after, retain SQL eligibility, and justify the tradeoff. |
| Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore | Publish a customer-scoped read, reconcile the Runtime tool list, and deploy. Use Theo's extracted preferences in a new conversation, verify current products in Aurora, inspect Memory from a separate process, compare build fingerprints, and run the trace contract. |
| Lab 4: Build Governed Agent Actions with Cedar | Author the Cedar ownership rule and keyed absence query. Prove authentication failure, Cedar denial, business refusal, commit, and managed output suppression. Test replay and Aurora RLS independently; complete one Operator investigation and stop before a consequential action. |
| Summary | Export evidence, restore the policy baseline, explain what each boundary establishes, and map the pattern to your application. |

The Lab 4 driver, `scripts/prove_governance_outcomes.py --json /tmp/pellier-evidence/lab-4-boundaries.json`,
runs the existing return/RLS matrix once and issues two one-cent credits in the
synthetic workshop dataset. It compares a benign response with an email canary,
then replays the suppressed credit's key. No real payment or human approval is
claimed. Migration 055 stores sanitized CLI observations and exact-key Aurora
snapshots separately from policy receipts. Observatory reads them at
`/observatory/govern/verification`; authentication failures never acquire a
fictional principal or Cedar decision. Local tests verify the implementation,
not live Guardrail behavior. Publish only after fresh-account rehearsal proves
the deployed output path, benign control, suppression envelope, and unchanged
credit cardinality.

Make canonical edits to the lab manual in the Workshop Studio repo, not here.

The app's reference directory follows the same four lab questions. Workbench
shows the current lab's references first; each view states what to inspect,
what its evidence can establish, and how to return to the saved lab and step.
Search pipeline runs an unconstrained mechanism experiment. Retrieval comparison
runs the four strategies explicitly and exposes the comparison ID and persistence status;
it does not require existing telemetry or seed results from fixture scores.
Evaluations, production patterns, and replacement recovery are extensions after
the labs. They do not add required steps to the Workshop Studio path.

### Workshop run tooling

Four commands carry a participant through that path. Bootstrap aliases each one,
and every one of them is scoped to a single run.

| Command | Script | What it does |
|---|---|---|
| `workshop-start [persona]` | `scripts/workshop-start.sh` | Mints one run id, records it in `pellier.workshop_runs`, exports `PELLIER_RUN_ID` to the service, and restarts. Idempotent: a second call reuses the existing id. |
| `doctor --lab N --phase prerequisites` / `--phase proof` | `scripts/workshop_doctor.py` | Separates source/config prerequisites from recorded outcomes. Proof is the default; every failed check names the gap. |
| `lab3-start` | `scripts/lab3-start.sh` | Verifies Gateway and Runtime, validates the provisioning receipt, switches the storefront to the managed rail, restarts, and proves one authenticated turn reported `gateway-mcp`. Refuses if either resource is missing. |
| `receipt` | `scripts/build_receipt.py` | Assembles the portable evidence receipt for the run. `--strict` exits 1 unless every lab's contract is proved **and** the evidence was scoped to that run, so an unapplied migration 049 fails rather than grading someone else's rows; the default reports honestly and exits 0. |

`scripts/prove-reset-cycles.sh` is the release check behind those commands: it
runs the governed reset, a journey smoke, then both again, and exits non-zero
unless both cycles pass. A reset that only works once is not a reset.

Migration 049 gives every evidence table a `run_id` column defaulted from the
`pellier.run_id` session setting, which `services/database.py` binds on each
pooled connection from `services/workshop_run.py`. No writer names the column,
so one participant's evidence is separable from a seeded incident or a previous
run without changing a single INSERT. The Gateway CLI helper binds the same run setting before writing its policy receipt.
Other rows written outside the pool remain unattributed unless their writer binds a run;
recent timestamps alone cannot satisfy a run-scoped proof.

### Boundary with Mosaic

Pellier treats hybrid retrieval as one existing agent capability. Its retrieval
lab asks builders to choose among vector, hybrid, reranked, and agent-planned
strategies, then moves on to managed execution, policy, and evidence. Mosaic is
the deep retrieval-engineering session for lexical and semantic retrieval,
RRF, reranking, filters, typo tolerance, HNSW tuning, evaluation, and search
performance. Neither workshop depends on the other.

---

## Architecture

### Agents

Five specialist agents sit behind one deterministic Dispatcher. Pellier and the
managed AgentCore Runtime both use that routing contract; Pellier Observatory runs it
live and reports the route actually observed.

| Agent              | Role                                            | Model            |
| ------------------ | ----------------------------------------------- | ---------------- |
| **Search Agent**      | Interprets intent, runs semantic search         | Claude Opus 4.6  |
| **Personalization Agent**            | Pairing, palette, occasion, editorial picks     | Claude Opus 4.6  |
| **Pricing Agent**      | Price intelligence, deals, percentile context   | Claude Sonnet 4.6 |
| **Inventory Agent**       | Warehouse stock and low-inventory alerts        | Claude Sonnet 4.6 |
| **Customer Service Agent**   | Returns, care, post-purchase                    | Claude Opus 4.6  |

The Operator Concierge adds two bounded graph nodes:

| Graph node | Responsibility |
|---|---|
| **Case Investigator Agent** | Reconstruct current customer, order, ticket, review, and handoff evidence without treating shopper text as authoritative |
| **Resolution Planner Agent** | Turn the investigation artifact into a constrained recommendation tied to the pending review |

`GraphBuilder` orders those nodes and persists the graph result. Neither node
decides the review, invokes the governed write, or substitutes for AgentCore
Policy where it applies or PostgreSQL enforcement.

Per-agent model choice is an architectural decision – Inventory Agent's terse warehouse answers run on Sonnet; the Personalization Agent's editorial prose earns Opus. Factories load **`BEDROCK_OPUS_MODEL`** for editorial agents, **`BEDROCK_REPORTING_MODEL`** for reporting specialists, **`BEDROCK_ROUTER_MODEL`** for routing, and **`BEDROCK_FAST_MODEL`** for the explicit Fast response mode – see `pellier/backend/config.py`. The fast profile is Claude Haiku 4.5 (`global.anthropic.claude-haiku-4-5-20251001-v1:0`) and is preflighted before the workshop is marked ready. **`BEDROCK_SONNET_MODEL`** is the canonical Sonnet profile (`global.anthropic.claude-sonnet-4-6`); the model-access preflight may also write it into `BEDROCK_OPUS_MODEL` when Opus 4.6 is not reachable on the account. **`BEDROCK_CHAT_MODEL`** is the legacy alias kept only for older scripts. Pellier Observatory surfaces the configured mix and the exact model used by each live run.

### Tools

The canonical Gateway catalog defines 18 tools, including the staff replacement
operation. This iteration publishes 16 at the start and 17 once Lab 3a publishes
`get_ticket_history`. `restock_inventory` remains deferred. `issue_credit` and
`replace_damaged_item` are published for staff only; no shopper specialist binds
them. Discovery returns the subset permitted for the caller's claims, not the
entire published catalog. The 16 initially published names are:

`search_products`; `search_products_hybrid`; `get_related_products`; `get_trending_products`; `get_price_analysis`; `browse_category`; `compare_products`; `check_inventory`; `get_low_stock`; `get_return_policy`; `initiate_return`; `get_customer_preferences`; `get_audit_trail`; `escalate_to_human`; `issue_credit`; `replace_damaged_item`

#### One search executor

`services/planned_hybrid_retrieval.execute_search_plan` is the single pipeline
behind the shipped path: a typed plan, hard predicates pushed into **both**
branches, vector and full-text retrieval, RRF, a bounded rerank, a final
eligibility recheck, then the rows returned. The storefront's
`search_products_hybrid`, the Observatory's strategy comparison, the Lab 2
receipt and `scripts/eval_retrieval_harness.py` all call it, which is what lets
the evaluation speak for the shipped path rather than for a parallel copy of it.

Two surfaces keep their own pipelines on purpose and say so at the top of each
file: `services/replacement_search.find_replacements` enforces predicates the
executor has no parameter for and exits its relaxation ladder on a different
signal, and `app.explain_search` exists to expose the stages the executor
collapses.

`GET /api/observatory/search-strategies/micro-eval` compares rerank pool sizes
on one canonical query and reports candidate coverage, context precision,
reciprocal rank, hard-constraint violations, short-result rate, citation
coverage, and p50/p95 latency. Its cost is bounded: repetitions are capped,
deterministic metrics are scored once, and a request may compare at most four
pool sizes.

Retrieval receipts cite the rows the shopper actually received, not the whole
rerank pool, and freeze the cited text, source URI and revision with a SHA-256
snapshot at retrieval time, so a later catalog edit cannot rewrite what an
answer was based on.

A separate governed natural-language query capability was removed because no
specialist could call it. Its underlying query lane remains exercised by
`scripts/compare_query_lanes.py` and live tests.

The lane is off the Gateway for separate reasons, and not because the Gateway
path is incapable. The RDS Data API is single-statement
per `execute_statement` call ("Multistatements aren't supported", box-verified:
a prepended `SET` once killed every read tool on the Gateway path), but it does
support explicit transactions, and session-local state persists across calls
that share a `transactionId`. Measured on the live cluster:

```
begin_transaction()
  SET LOCAL ROLE pellier_query          -> current_user becomes pellier_query
  SET TRANSACTION READ ONLY             -> a subsequent write is refused
  set_config('pellier.principal_sub',…) -> readable in the next call
  SELECT DISTINCT customer_id FROM pellier.orders
      as CUST-THEO -> ['CUST-THEO']     (own row visible)
      as CUST-ANNA -> []                (someone else's row invisible)
```

So the owner identity behind the fixed `--secret_arn` is not the obstacle
either: `SET LOCAL ROLE` drops into a role that holds neither `BYPASSRLS` nor
superuser, and RLS then applies to the rest of the transaction.

It stays off the Gateway for two other reasons. First, cost shape: each
statement is one HTTPS round trip, so a governed query needs seven where the
existing read tools need one. Second, and decisive, publishing the lane would
mean a second copy of the boundary (subquery wrap, plan inspection, schema allowlist,
row cap, receipt write) living in a Lambda deploy artifact, reviewed and tested
apart from `services/governed_query.py`. These same Lambdas already record two
drift incidents against the in-process rail: column names (`42703`) and
`hnsw.iterative_scan` tuning. Duplicating a query is a bug; duplicating a
security boundary is a class of bug. If it is ever published, the target should
call the reviewed boundary rather than restate it.

`tests/test_managed_gateway_tool_contract.py` pins the in-process set against
the canonical catalog, so a tool added on one rail and not the other fails
rather than silently diverging, and `tests/test_tool_ownership.py` fails for
any tool no specialist binds unless the reason is written down.

Aurora also stores a semantic tool registry for the retrieval-strategy teaching
surface. It is not the governed execution selector. The managed Dispatcher
classifies intent, chooses one specialist, lists Gateway tools, and filters that
catalog against the specialist's checked-in allowlist.

### Governed natural-language data access

A shopper question becomes SQL only through a boundary the model cannot argue
with. Generation is constrained (approved schema context, temperature 0,
explicit read-only contract), but generation is not the security boundary.
Every statement is wrapped as a subquery, planned before it runs, and executed
as `pellier_query`:

```
READ ONLY; statement_timeout = 3s; fixed search_path
SET LOCAL ROLE pellier_query; pellier.principal_sub bound for RLS
schema allowlist from the plan; implementation-owned row cap
```

A write, a utility statement, a data-modifying CTE, or a stacked statement
fails on the planner's grammar rather than on a keyword blocklist. Every
attempt writes a row to `pellier.governed_query_receipts`, refusals included,
because a rejected statement leaves no trace anywhere else: it never reached
the database. The receipt is written by `run_governed_query` itself, so no
caller can produce an unreceipted attempt.

`scripts/compare_query_lanes.py` runs the same question through this lane and
through the Postgres MCP lane and reports what each leaves behind. The point is
not that one is better. The MCP lane's credential is the table owner, so it
sees every customer and can read the authorization map itself; the governed
lane answers to a shopper's identity. Choosing between them is a governance
decision, and the difference is visible in the evidence.

### Observability and reconstruction

Evidence spans carry `turn_id`, identity, policy verdict, and execution
outcome, and export collectorless to the CloudWatch X-Ray OTLP endpoint. The
endpoint accepts SigV4 only, and signing happens in a `requests` auth hook so
the bytes signed are the bytes sent, with refreshable credentials so a rotating
instance role keeps exporting. Spans land in the `aws/spans` log group through
Transaction Search at 100% indexing, because the reconstruction exercise asks a
participant to find one specific turn and a sampled turn cannot be found by
`turn_id`.

Model prompts and completions are withheld: Strands' attribute redaction is
installed before the tracer is constructed, so `gen_ai.input.messages` and its
siblings export as `[REDACTED]` while `pellier.*` correlation attributes pass
through untouched. Spans locate a turn. Aurora proves what it did.

| Script | What it does |
|---|---|
| `scripts/reconstruct_turn.py <turn_id>` | Reconstructs one turn from exported spans. `--aurora` adds the correlated Aurora artifacts, which is the answer key for the forensic exercise. Prints the Aurora side even when a turn has no spans, since the seeded turns are Aurora-only |
| `scripts/policy_mode.py` | Reads live Cedar modes, and changes them through the AgentCore CLI project rather than boto3. `--restore-shipped` resets. Refuses to edit a declaration it cannot deploy |
| `scripts/prove_governance_windows.py` | Runs the same forbidden request in both enforcement windows. Restores the shipped mode in a `finally` block so a crashed run cannot leave the account in monitor mode |
| `scripts/score_governance_evidence.py` | Scores the governance invariants from evidence alone, with no model and no managed evaluation service |
| `scripts/seed_forensic_dataset.py` | Seeds the three reconstruction turns: allowed, enforce-denied, and log-only dual refusal |
| `scripts/seed_principal_mappings.py` | Maps each named shopper's Cognito subject to their customer id. An empty mapping denies every signed-in shopper their own orders, so `--check` runs during reset |

Cedar enforcement has two independent scopes with different vocabularies, and
conflating them is the usual mistake: a policy carries
`UpdatePolicy.enforcementMode` (`ACTIVE` or `LOG_ONLY`), while the gateway
attachment carries `policyEngineConfiguration.mode` (`ENFORCE` or `LOG_ONLY`).
The "on" value differs by scope, `UpdatePolicyEngine` carries no mode at all,
and effective behavior is the conjunction: `LOG_ONLY` at either scope means no
denial.

### Skills

Five skills loaded per turn by the SkillRouter to shape voice, handling, proof, and care language without changing product selection:

[`skills/the-packing-list/`](skills/the-packing-list/) (Marco); [`skills/the-gift-table/`](skills/the-gift-table/) (Anna); [`skills/the-makers-shelf/`](skills/the-makers-shelf/) (Theo); [`skills/the-care-card/`](skills/the-care-card/) (shared care/returns); [`skills/the-proof-counter/`](skills/the-proof-counter/) (shared proof/audit)

### Claude Code instructions and project skills

The repo deliberately demonstrates a layered coding-agent setup:

| Layer | Purpose |
|---|---|
| `~/.claude/CLAUDE.md` | Participant-global safety and workshop defaults, installed idempotently by `scripts/bootstrap-labs.sh` |
| [`CLAUDE.md`](CLAUDE.md) | Project contract, branch ownership, participant versus maintainer mode, and release gates |
| [`pellier/backend/CLAUDE.md`](pellier/backend/CLAUDE.md), [`pellier/frontend/CLAUDE.md`](pellier/frontend/CLAUDE.md), [`skills/CLAUDE.md`](skills/CLAUDE.md) | Nearest-scope engineering rules |
| [`.claude/skills/`](.claude/skills/) | On-demand Claude Code workflows for workshop verification and Pellier copy |
| [`VOICE.md`](VOICE.md) | Shared editorial voice and grounding contract |
| [`skills/*/SKILL.md`](skills/) | Pellier runtime prompt overlays loaded at backend start and selected per turn; these are application data, not Claude Code instructions |

Claude Code resolves `CLAUDE.md` guidance by scope. The backend separately loads root `skills/*/SKILL.md` at startup, and its `SkillRouter` selects from that registry during shopper turns. Keeping those systems distinct prevents a coding workflow from accidentally becoming model prompt data, or vice versa.

### Stack

| Layer            | Technology                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Database         | **Aurora PostgreSQL Serverless v2** (engine 18.3); elastic ACU scaling; standard PostgreSQL primitives throughout (extension, schemas, SQL) |
| Vector retrieval | pgvector 0.8.1; `vector(1024)` column; HNSW (m=16, ef_construction=64, `vector_cosine_ops`); `<=>` cosine operator |
| Lexical retrieval | Postgres FTS – `tsvector` + GIN + `ts_rank_cd` (no native BM25; `pg_trgm` for fuzzy match) |
| Hybrid merge     | Reciprocal Rank Fusion (RRF) – fuses pgvector + FTS rank lists without normalizing raw scores |
| Models           | Claude Opus 4.6 (`global.anthropic.claude-opus-4-6-v1`, editorial); Claude Sonnet 4.6 (`global.anthropic.claude-sonnet-4-6`, routing/reporting, no temperature override); Claude Haiku 4.5 (`global.anthropic.claude-haiku-4-5-20251001-v1:0`, explicit Fast response mode); Cohere Embed v4 (`us.cohere.embed-v4:0`, 1024-dim via output_dimension, inference profile); Cohere Rerank v3.5 (`cohere.rerank-v3-5:0`) |
| Agent framework  | Strands Agents SDK – `Agent`, `@tool`, deterministic Storefront Dispatcher, bounded Operator Concierge `GraphBuilder`, and before/after tool-call hooks |
| Agent infra      | Bedrock AgentCore Runtime (CUSTOM_JWT and governed Gateway MCP calls); Memory (conversation events and four configured extraction strategies, with episodic extraction optional); Gateway (16 published tools at baseline, 17 after Lab 3a, from 18 defined schemas; token-scoped discovery); Policy (Cedar ENFORCE); Identity |
| MCP              | [`awslabs.postgres-mcp-server`](https://github.com/awslabs/mcp/tree/main/src/postgres-mcp-server) pinned to `==1.1.6` and installed via `uvx`, registered against the Aurora cluster ARN over `--connection_method RDS_API --db_type APG` (enum-name flag, not the lowercase value; read-only by default; writes require opting in via `--allow_write_query`); `pellier/config/mcp-server-config.json` is the literal contract; AgentCore Gateway is the managed-host counterpart |
| Backend          | FastAPI; Python 3.14; psycopg3; boto3; SSE streaming                                                  |
| Frontend         | React 18; TypeScript 5; Vite 6; Tailwind CSS 3; Framer Motion 12                                                      |
| Editorial system | Fraunces Variable and Instrument Serif (display); Instrument Sans (body); JetBrains Mono (code); self-hosted fonts     |

---

## Quality gates

The `governed-quality` workflow runs on pushes and pull requests to `governed`.
Its backend job runs the test suite and validates every shell script; its
frontend job runs the tests, type-check, lint, build and production dependency
audit. Copy compliance is not a separate CI step: `test_copy_compliance.py`
defines a test and is collected by `pytest -q` like any other. `git diff --check`
is a local habit rather than a gate.

Run the whole thing locally with:

```bash
cd pellier/backend
./.venv/bin/python -m pytest -q

cd ../frontend
npm test -- --run
npm run type-check
npm run lint
npm run build
npm audit --omit=dev --audit-level=high

cd ../..
git diff --check
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
```

The `e2e` workflow is a manual release gate for a newly provisioned Workshop
Studio deployment. It runs the storefront, operator, Observatory, persona,
streaming, reset, and Cognito checks against that real URL; it does not start
a simulated local data plane or claim to validate Aurora and AgentCore without
them.

Before calling a workshop deployment ready, also run the documented reset-cycle
check and the run-scoped `doctor` / `receipt` proofs. Unit tests and a working UI
do not establish a current Runtime build, durable Memory, a Cedar ALLOW/DENY
pair, or Aurora's refusal of an unauthorized write. Keep those results separate
from local code quality checks.

---

## Repository layout

```
sample-pellier-agentic-search-apg/
├── .claude/
│   └── skills/                             Claude Code project workflows
├── CLAUDE.md                               Project and branch contract
├── WORKSHOP.md                             Teaching map and golden journeys
├── VOICE.md                                Pellier editorial voice contract
├── pellier/
│   ├── backend/                           FastAPI server, agents, services
│   │   ├── CLAUDE.md                        Backend and Lab 1 rules
│   │   ├── agents/                          Search Agent, Personalization Agent, Inventory Agent, ...
│   │   ├── services/                        Dispatcher, Operator graph, handoff, tools, AgentCore, database
│   │   ├── routes/                          FastAPI routers (agent, auth, commerce,
│   │   │                                    observatory, operator, products, search,
│   │   │                                    storefront, user, workshop)
│   │   └── app.py
│   └── frontend/                          React 18 + TS + Vite SPA
│       ├── CLAUDE.md                        Storefront and Pellier Observatory rules
│       └── src/
│           ├── components/                  PellierHero, ChatDrawer, ProductCard, ...
│           ├── operator/                    Client desk, concierge graph, reviews, actions
│           ├── shared/                      Cross-surface atoms – TraceChip, PresencePill
│           ├── observatory/                 Shopper and operator orchestration evidence
│           └── data/                        36 displayed product records + persona curation
│
├── workshop/                              Participant build surface: lab-2-rrf.sql,
│                                          lab-4-absence.sql, lab-4-rls.sql, the provided
│                                          lab-3-otel-contract.jq,
│                                          starters/, architecture-diagrams/
├── policies/                              Cedar policy set applied to the policy engine
├── skills/                                Strands runtime skills (5) + scoped guidance
├── solutions/                             Reference implementations (drop-in escape hatches)
│   ├── waking-the-stock-keeper/             Lab 1 Inventory Agent reference
│   ├── closing-marcos-gap/                  Lab 1 check_inventory reference
│   ├── the-quiet-search/                    Lab 2 RRF reference
│   ├── the-ledger/                          Lab 3 forensic SQL + OTEL contract reference
│   ├── the-concierge/                       Lab 4 MCP and Gateway reference
│   └── retrieval-eval/                      Retrieval evaluation reference
│
└── scripts/
    ├── migrations/                         Ordered fresh-cluster SQL (001-049)
    ├── seed_pellier_catalog.py             60 story products + 940 retrieval distractors
    ├── seed_local_golden_journeys.py       Local Theo handoff + Jessica evidence rehearsal
    ├── bootstrap-environment.sh             Code Editor + nginx + systemd
    └── bootstrap-labs.sh                    DB seed + frontend build + service start
```

The lab manual, CloudFormation templates, and prereq images live in the separate Workshop Studio repository, which is the source of truth for all session content.

---

## Resources

- [Aurora PostgreSQL with pgvector](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Model Context Protocol (MCP) specification](https://modelcontextprotocol.io/)
- [Strands Agents SDK](https://strandsagents.com/latest/)
- [pgvector 0.8.1 performance on Aurora](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql/)

---

## Credits and license

Built and curated by **Shayon Sanyal** (<shayons@amazon.com>).

Licensed under the [MIT License](LICENSE), copyright 2026 Amazon Web Services.
The license requires the copyright and permission notice to remain in copies or
substantial portions of the software. See [NOTICE](NOTICE) for the project's
requested attribution format for derived workshops, talks, and other reuse.
