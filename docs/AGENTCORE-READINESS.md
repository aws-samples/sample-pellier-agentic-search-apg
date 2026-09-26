# AgentCore implementation and exercise map

This is the maintainer contract for the governed workshop. Workshop Studio owns
the participant instructions. The supplied infrastructure and exercise starters
are intentionally different: a successful bootstrap establishes the baseline;
each participant must still run the checks for their own changes.

## Services in the required path

| AgentCore capability | Supplied implementation | Participant progression and proof |
|---|---|---|
| **Runtime** | Two Python CodeZip runtimes: shopper dispatcher/specialists and a separate staff investigation graph. Shopper invocation uses Cognito `CUSTOM_JWT`; the backend invokes the staff runtime with IAM after authenticating staff. Both packages have build fingerprints. | Lab 3 deploys the changed support adapter and proves the executing shopper build and `gateway-mcp` rail. Lab 4 investigates Jessica through the staff runtime and checks its fingerprint and graph order. |
| **Gateway** | Four Lambda targets; 18 defined tool schemas, 16 published at baseline and 17 after Lab 3A. MCP discovery is scoped to the authenticated caller. Managed execution fails closed when Gateway is unavailable. | Lab 3A publishes `get_ticket_history` and repairs the support adapter's binding. Lab 3B deploys, discovers the catalog, checks owned/foreign customer access and compares build fingerprints. `restock_inventory` stays unpublished. |
| **Memory** | Conversation events with 30-day expiry; four real extraction strategies, listed below. Configuration, extraction and retrieval are separate checks. | Introduction records Theo's source conversation. Extraction runs during Labs 1–2. Lab 3 inspects all four record types and recalls them in a new session with no prior chat events. Product recommendations are checked against current Aurora records. |
| **Observability** | OpenTelemetry agent/model/tool spans, CloudWatch Runtime and Gateway delivery, Transaction Search, encrypted logs with bounded retention, and control-plane audit. Aurora separately stores queryable application execution evidence. | Lab 1 retains a structured tool result; Lab 2 reconstructs ranking from recorded candidates; Lab 3 requires correlated managed traces and matching builds; Lab 4 reconciles policy, execution and committed effects. The Observatory reads evidence; a UI indicator is not a provider decision. |
| **Policy** | Gateway-attached managed Cedar engine in `ENFORCE`. Explicit catalog permits, owner-scoped customer reads, staff-scoped writes, and a managed output guardrail. The shopper return permit deliberately leaves ownership for Lab 4. | Lab 4A supplies the bounded ownership forbid. Lab 4B distinguishes authentication failure, policy denial, tool refusal, committed effect and output suppression; direct SQL proves RLS and keyed absence with an allowed positive control. |
| **Identity** | Runtime/Gateway service-managed workload identities, Cognito person identity and IAM service authentication. Verified customer/staff claims drive the caller boundary. | Identity is exercised throughout Labs 3–4. There is no separate outbound OAuth/API-key credential-provider exercise; the rendered project's `credentials` list is empty. |

AgentCore Browser, Code Interpreter, managed Evaluations, Harness and Payments
are not configured on the required path. The project's `evaluators` and
`onlineEvalConfigs` lists are empty. Application evaluation tooling and
after-workshop extensions must not be presented as deployed AgentCore Evaluations.
Amazon Bedrock inference, embeddings, reranking and output guardrails; Strands;
Cognito; Lambda; Aurora/RDS; CloudWatch; CloudTrail; IAM and KMS are supporting
services or libraries, not additional AgentCore components.

## Memory contract

| Strategy | Name | Namespace | Required evidence |
|---|---|---|---|
| `USER_PREFERENCE` | `PellierUserPreferences` | `/pellier/preferences/{actorId}/` | Extracted preference record and retrieval by the same actor |
| `SEMANTIC` | `PellierFacts` | `/pellier/facts/{actorId}/` | Extracted fact record and retrieval by the same actor |
| `SUMMARIZATION` | `PellierSessionSummary` | `/pellier/summaries/{actorId}/{sessionId}/` | Extracted source-session summary and retrieval |
| `EPISODIC` | `PellierEpisodes` | `/pellier/episodes/{actorId}/{sessionId}/` | A completed episode with situation, intent, assessment and justification, plus retrieval |

Episodic reflections use `/pellier/episodes/{actorId}/`. Their configuration and
real read path are supplied. Reflection generation is asynchronous and is an
optional follow-up; a partial episode or reflection cannot replace the required
completed episode. Strategy names, namespaces and expiry come from
`pellier/backend/services/memory_contract.py`.

Bootstrap's `scripts/deploy/verify_memory_readiness.py` writes an isolated source
conversation using `CreateEvent`. It requires all four strategies to be ACTIVE
with the expected configuration, source-event readback, `ListMemoryRecords`,
`GetMemoryRecord` and `RetrieveMemoryRecords` agreement on actual record IDs and
namespaces, an empty recall session, and an empty retrieval for a different fresh
actor. It never inserts long-term records. Missing evidence fails after a bounded
20-minute configuration/extraction wait; AWS latency is not guaranteed by that
deadline. Each run has a new actor/session, so old evidence cannot pass a new run.

The detailed result is saved under `memory.seed.acceptance` in the managed
provisioning receipt. `scripts/validate_agentcore_receipt.py` rejects the old
seed-only receipt and missing or inconsistent record evidence.
`scripts/health-gate.sh` also checks the current four-strategy configuration.
Theo's participant experiment uses its own actor/session and independently proves
that retrieved context reaches the managed recommendation; bootstrap's extraction
probe is not a substitute for that application-level test.

The staff Runtime bootstrap smoke runs both real graph nodes against an explicitly
labelled synthetic deployment brief and verifies the executing package. It proves
managed execution and graph order, not Jessica's case or a reviewed business action.
Lab 4 and fresh-event acceptance must use actual scoped Aurora records and complete
the proposal, confirmation and execution checks for the same review.

## Progressive exercises and escape hatches

There are four labs, eight tasks and nine authoring regions. Recovery provides
the missing implementation and converges on the same checks. It cannot produce
AWS evidence, approve a staff action or mark an unrun check complete.

| Task | Intentionally incomplete surface / supplied operation | Acceptance after an attempt or recovery |
|---|---|---|
| **1A** | Inventory envelope in `services/agent_tools.py` | Direct tool contract distinguishes unknown product, zero stock and stocked product; independent current SQL confirms inventory. |
| **1B** | Inventory specialist tool list in `agents/inventory_agent.py` | Agent calls the intended tool and its answer agrees with the retained result. |
| **2A** | RRF expression in `workshop/lab-2-rrf.sql` | Participant reconstructs fusion scores from recorded candidate ranks. |
| **2B** | Requirement preservation in `services/search_plan.py` | Local contract check plus live Aurora eligibility for exact returned product IDs; fallback relaxes preferences without losing requirements. |
| **3A** | Published tools in `scripts/deploy/gateway_tool_schemas.py` and caller binding in `services/agentcore_gateway.py` | Required support tool is published and bound to the verified customer's input. |
| **3B** | Deploy/investigate the 3A changes; no additional authoring region | Live discovery, scope challenge, executing fingerprint, all-four Memory recall, Aurora product check and trace contract. |
| **4A** | Final `unless` in `policies/workshop_identity_match_forbid.cedar` | CLI deployment followed by real owned/foreign caller outcomes; retained denial is attributed to the participant's policy. |
| **4B** | Ownership predicate in `workshop/lab-4-rls.sql` and absence counts in `workshop/lab-4-absence.sql`; supplied Operator workflow | Direct RLS probes roll back; denied-key counts are zero and the allowed-key control is one. One staff review preserves source turn, action hash and write key across proposal, confirmation and execution. |

The Lab 1 wrapper and Lab 2 search-plan implementation run in the application
process; they are not moved into Runtime by Lab 3. The managed search Lambda is
supplied separately and does not implement Lab 2's exclusion/preference ladder.
The progression builds connected contracts and evidence across one application;
guides must not claim that every prior participant edit migrates unchanged.
Lab 3 packages the support adapter; the Lambda tool implementations are supplied.
Lab 4's RLS exercise is a rollback-only policy experiment, not a persistent
replacement of the deployed RLS baseline.

Hints, bounded recovery references and the catch-up commands remain in Workshop
Studio. Managed-service failure remains a failed/incomplete managed check. The
participant keeps the error and evidence, tries the documented recovery once,
then uses the continuation checkpoint if support cannot resolve it.

## Release and fresh-event acceptance

Local source tests and Studio validators check contracts, starter boundaries,
recovery compilation/parity and receipt rejection. They do not prove AWS delivery
or participant timing. Publish source first, update Studio's source and
infrastructure pins, sync S3 assets, sync static URLs to **In sync**, then push
Studio and verify the resulting build before creating the test event.

In that fresh event, require CloudFormation completion, successful bootstrap
signal, `E2E_PROVED`, the health gate and a valid managed receipt. Rehearse all
eight tasks with participant identities, including browser authentication, both
runtimes, all four Memory record types, policy/output controls, SQL positive
controls and the full staff review lifecycle. Repeat a bounded recovery on an
exercise copy and run the same acceptance. Record cold provisioning and lab
timings, failed attempts, source SHA, Studio build and account/Region. A prior
account's pass does not establish this event's readiness.
