# AgentCore implementation and task map

This is the maintainer contract for the governed workshop. Workshop Studio owns
the participant instructions. Provisioning establishes the baseline; each
participant still runs the checks for their own changes.

## Services in the required path

| AgentCore capability | Supplied implementation | Where participants prove it |
|---|---|---|
| **Runtime** | One Python CodeZip runtime, `pellier_orchestrator` (with the deployment suffix when one is set), entrypoint `pellier/backend/agentcore_runtime.py`. It runs the same Router and three agents as the app and gets every tool through Gateway. Invocation requires a Cognito access token (`CUSTOM_JWT`). The package carries a build fingerprint over `RUNTIME_SOURCE_FILES` (`pellier/backend/services/build_fingerprint.py`). | Lab 3 switches the Storefront to the managed rail (`scripts/lab3-start.sh`), deploys the 3A edits with `--mode participant`, and `scripts/lab3_check.py` compares the executed build with the checkout's. |
| **Gateway** | One Lambda target, `pellier-store-tools`, with nine tool schemas: eight published at baseline and nine after Lab 3A publishes `get_tickets` (`scripts/deploy/gateway_tool_schemas.py`). Discovery is filtered by policy per caller. Managed turns fail closed when Gateway is unavailable. | Lab 3A publishes `get_tickets` and binds it to the caller; `scripts/workshop_doctor.py --lab 3 --phase prerequisites` reads the catalogue. |
| **Policy** | A managed Cedar engine attached to Gateway in `ENFORCE` mode. Baseline permits: an exact allow-list of the five shopper-safe reads, `get_orders_owner_only` (and `get_tickets_owner_only` once published), `ask_a_person_caller_bound`, and `give_store_credit_staff_scope` with no amount condition. Provisioning also deploys the Lab 4 starter forbid `workshop_credit_limit`, which denies every credit. A managed output guardrail can suppress a credit response after execution. | Lab 3B's direct probe: Theo's token for Jessica's tickets is denied. Lab 4A: `scripts/lab4_check.py --task 4A` evaluates the rule with `cedarpy`, then gets a Gateway DENY for an over-limit credit with no row for its key. |
| **Memory** | Conversation events with 30-day expiry and four extraction strategies (below). Provisioning records Theo's first conversation. Turns read Memory for an authenticated shopper; a failed read is reported in the turn and the turn continues. | Lab 3B: a new session's Builder view names the user-preference record the agent was given, and `scripts/lab3_check.py` reads it back. |
| **Observability** | Runtime, Gateway and Memory log delivery, OpenTelemetry agent, model and tool spans, CloudWatch Transaction Search, KMS-encrypted Runtime logs with bounded retention, and control-plane audit. Transaction Search activates beside the Lambda and AgentCore deploys; both trace log groups are protected before Gateway or Memory tracing starts or the Runtime is invoked. | Not a required lab check. `workshop/lab-3-otel-contract.jq` checks span structure on a downloaded trace; the lab checks read Aurora's `tool_audit` as execution evidence. |
| **Identity** | Cognito person identity for shoppers and staff. A pre-token trigger (`scripts/deploy/cognito_customer_claim.py`) stamps `custom:customer_id` on a shopper's access token from a map rendered from `pellier.customers`, and `custom:staff_scope` on a member of the operator group. Runtime and Gateway use service-managed workload identities. | Throughout Labs 3 and 4. There is no outbound credential-provider exercise. |

The Operator's investigation (Investigator, then Advisor) runs in process in
the app, not on Runtime. Nadia's Execute calls Gateway with her own token, so
Cedar authorizes a person.

## Identity and authority contract

The browser sends Secure, HttpOnly session cookies to FastAPI. The backend
verifies the access token's signature, issuer, client, expiry and token use,
then maps the verified username to a customer using Aurora's server-owned map.
It derives the Runtime session ID from the verified subject and conversation.
The Runtime independently verifies the original token with a pinned Cognito
issuer and client; `services/runtime_identity.py` derives both the audit subject
and the customer from signed claims and rejects conflicting payload fields.
The verifier is included in the deployed source fingerprint. Runtime and
Gateway authorizers also require `token_use=access`; Cognito access tokens use
`client_id`, so an ID-token audience is not used as an access-token audience.
The entrypoint accepts a nonempty text prompt and text-only user/assistant
history. It rejects structured `toolUse` content before creating a dispatcher;
submitted JSON cannot become a direct framework tool invocation.

Cedar remains the customer authorization boundary for direct Gateway callers.
Its owner-only permits for `get_orders` and `get_tickets` match
`custom:customer_id` to the requested customer. `ask_a_person` may name no
customer, or only the caller's own, so a direct caller cannot open a credit
request on someone else's case.
The Lambda receives the admitted arguments, not a JWT or a verified principal.
Its Data API transaction switches to the non-owner, NOBYPASSRLS `pellier_agent`
role and binds that customer's username. RLS contains an incorrect query within
that scope; it does not independently authenticate the Lambda's caller or an
arbitrary database session. The Gateway role must be limited to the configured
target Lambda, and principals able to invoke or modify that Lambda are trusted
deployment administrators, outside the shopper boundary.

The application carries Nadia's verified subject in the approval record; Cedar
checks her staff-scope claim and the participant's amount policy on execution.
The database checks the approved arguments and idempotency key. A JWT, an agent
workload identity, a customer ID, memory and a human approval are distinct facts.
None substitutes for the others.

These choices follow AWS's [Runtime security guidance](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-security-best-practices.html),
[inbound JWT contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html),
[Policy principal model](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html),
and [Lambda target context](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html).
This remains an educational deployment with participant provisioning permissions
and CLI-managed service roles. It is not a production IAM boundary against an
attendee who administers the account. Production deployment requires separate
deployment and serving roles with resource-scoped IAM and its own acceptance.

AgentCore Browser, Code Interpreter, managed Evaluations, Harness and Payments
are not configured. Amazon Bedrock models, Strands, Cognito, Lambda, Aurora,
CloudWatch, CloudTrail, IAM and KMS are supporting services, not additional
AgentCore components.

## Baseline authorization on a fresh stack

4 policies, all permits, no forbid; 5 once Lab 3A publishes `get_tickets` and
its owner-only permit lands in the same deployment. Provisioning deploys Lab 4's
starter forbid, `workshop_credit_limit`, beside them. The source is
`scripts/deploy/render_agentcore_project.py`, and
`pellier/backend/tests/test_fresh_policy_set.py` checks this table against it.
Every statement types the principal as `AgentCore::OAuthUser`, pins the
resource to the deployed Gateway ARN, and names actions
`pellier-store-tools___<tool>`.

| Policy | Effect | Shape |
|---|---|---|
| `baseline_permit_workshop_tools` | permit | An exact list of the five reads that expose no customer data: `search_products`, `browse_department`, `compare_products`, `check_stock`, `get_return_policy`. No wildcard, so a tool published later is denied by default. |
| `get_orders_owner_only` | permit | Only when the token's `custom:customer_id` equals `context.input.customer_id`. `get_tickets_owner_only` has the same shape once Lab 3A publishes that read. |
| `ask_a_person_caller_bound` | permit | When the input names no customer, or when the token's `custom:customer_id` equals `context.input.customer_id`. The handoff can open a credit request on the named customer's case. |
| `give_store_credit_staff_scope` | permit | A principal whose `custom:staff_scope` is `returns`. No amount condition: the $100 per-credit limit is the Lab 4 rule, and no shopper permit names this action. |

A token with neither claim may read the catalogue and ask for a person without
naming a customer, and nothing else.

## Memory contract

| Strategy | Name | Namespace |
|---|---|---|
| `USER_PREFERENCE` | `PellierUserPreferences` | `/pellier/preferences/{actorId}/` |
| `SEMANTIC` | `PellierFacts` | `/pellier/facts/{actorId}/` |
| `SUMMARIZATION` | `PellierSessionSummary` | `/pellier/summaries/{actorId}/{sessionId}/` |
| `EPISODIC` | `PellierEpisodes` | `/pellier/episodes/{actorId}/{sessionId}/` |

Names, namespaces and expiry come from
`pellier/backend/services/memory_contract.py`. Shopper turns and Lab 3 read the
`USER_PREFERENCE` record only; the other three serve the appendix's deep dive.

`scripts/deploy/verify_memory_readiness.py` writes an isolated conversation
with `CreateEvent`, requires every strategy to be ACTIVE with the expected
configuration, and waits until list, get and retrieve agree on real record ids
and namespaces for `REQUIRED_STRATEGIES` (user preferences). Another strategy's
records found by then pass the same checks. It never writes long-term records.
`scripts/deploy/seed_agentcore_memory.py` writes the persona conversations
first, so Theo's preference extracts while that proof waits. Provisioning starts
the proof right after the first `agentcore deploy`, beside the policy deploys.
`scripts/health-gate.sh` checks the same configuration.

Facts, the session summary and the episode can form long after provisioning,
an episode sometimes more than ten minutes after its conversation, so they do not
hold a box. `scripts/deploy/check_memory_deep_dive.py` reads Theo's provisioning
conversation in the background after handout and writes
`/var/lib/pellier/memory-deep-dive.json`; `scripts/event_readiness.py` reports it
as an `i  Memory deep dive` line that never changes READY FOR LAB 1.

## Tasks and recovery

Four labs, eight tasks, nine marked regions. Recovery copies a reference into
the region and converges on the same checks. It cannot produce AWS evidence,
approve a credit or mark an unrun check complete.

| Task | Region | Acceptance |
|---|---|---|
| **1A** | Vector branch in `pellier/backend/services/store_tools.py` | `scripts/lab1_check.py --task 1A`: products searched with their own embeddings come back first, similarity is 1 minus the distance, and Anna's limits keep the candle out. |
| **1B** | Fallback in `pellier/backend/services/search_plan.py` | `scripts/lab1_check.py --task 1B`: the search that answered kept every limit the shopper asked for, and every product meets them. |
| **2A** | Stock agent grant in `pellier/backend/agents/stock_agent.py` | `scripts/lab2_check.py --task 2A`: the answering Stock agent held `check_stock` alone, and its counts for the pieces Pellier carries equal `warehouse_inventory`. |
| **2B** | Not-carried test in `pellier.check_stock` (`workshop/lab-2-check-stock.sql`) | `--task 2B`: through the live function, not carried, several, sold out and in stock stay distinct. |
| **3A** | Published tools in `scripts/deploy/gateway_tool_schemas.py`; caller binding in `pellier/backend/services/agentcore_gateway.py` | `scripts/lab3_check.py --task 3A`: nine tools published, `get_tickets` bound to the signed-in caller: a forged read for `CUST-JESSICA` leaves the checkout as `CUST-THEO`, and is refused with no signed-in customer. |
| **3B** | Ownership predicate in `workshop/lab-3-row-ownership.sql`, written during the `--mode participant` deploy | `scripts/lab3_check.py`: executed build, the Memory record, every ticket read bound to Theo, Cedar's denial of his direct read of Jessica's tickets, and the live row policies stopping a wrong query as Theo in process and through the Gateway Lambda's Data API binding. |
| **4A** | Final `unless` in `policies/workshop_credit_limit.cedar` | `scripts/lab4_check.py --task 4A`: Cedar matrix, eight wrong rules rejected, then the Gateway DENY; Nadia's credit executes once and a retry adds nothing. |
| **4B** | Credit writer privileges in `workshop/lab-4-credit-writer.sql`; `scripts/lab4_check.py --task 4B` and `workshop/lab-4-absence.sql` supplied | Eight probes in one transaction that commits only when all match; the money role writes only through `pellier.apply_store_credit`, in process and through the Gateway Lambda's Data API; the absence check prints 0, 0 and 1. |

The Gateway Lambda is packaged at provisioning from the finished copies of
`services/store_tools.py` and `services/search_plan.py`, and Lab 3's deploy
reuses it, so the Gateway's search runs the finished Lab 1 code whatever the
participant's files hold. The store tools are one implementation, so the Lambda
runs the same search and stock code as the in-process agents.

## Fresh-event acceptance

Local tests check contracts, starter boundaries, recovery parity and receipt
validation. They do not prove AWS delivery or timing. Publish the source,
update the Workshop Studio pins, sync assets, then build and verify the
Studio package before creating a test event.

In that event, require CloudFormation and bootstrap completion, the health
gate and a valid provisioning receipt. Rehearse all eight tasks with the
participant identities, Lab 3's deploy and Lab 4's deploy, one Operator
investigation and the cleanup. Record source SHA, Studio build, account,
Region, cold provisioning time and each lab's time. A previous account's pass
does not establish this event's readiness.

Proved at test event 6 (2026-10-19, source e853c80f, Studio cb247a0, a new
account in us-east-1):

- Transaction Search activated beside the Lambda and AgentCore deploys: ACTIVE
  after 361 s, inside the managed stage. Bootstrap reached E2E_PROVED, and the
  managed receipt records the activation, its resource policy and both trace
  log groups (`aws/spans`, `/aws/application-signals/data`) under the event's
  KMS key with 30-day retention.
- The managed stage took 9 minutes (APP_READY 12:43:44 to MANAGED_READY
  12:52:48 UTC), against 34 minutes on 2026-10-18. E2E_PROVED came 38 minutes
  after the stack started.
- `/var/lib/pellier/memory-deep-dive.json` reached `ready` 500 s after the
  check started. `uv run scripts/event_readiness.py` on the box first crashed
  with an AccessDenied traceback: it took the box for a laptop, because
  Workshop Studio hosts have no `/etc/pellier`. With that fixed, it prints
  `i  Memory deep dive (optional appendix): every strategy holds a record`.

Open for the next fresh event:

- The Studio template's `WorkshopReadyGate`, in the first Studio build pinned
  after this commit, takes the bootstrap signal instead of the editor instance:
  `BrowserVpcOrigin` starts within a minute of the instance launching, the
  distribution and the Cognito callback registration finish while bootstrap
  runs, and the nested and root stacks complete within about a minute of the
  signal. CodeEditorURL and Hosted UI sign-in work. Event 6 on 2026-10-19 took
  51 minutes to CREATE_COMPLETE, 12 of them CloudFront after `E2E_PROVED`;
  expect about 39.
- Shopper sign-in names the step and cause of a failure (`network_error:csrf`,
  `http_403:csrf`, ...) in the browser console, retries a dropped CSRF request
  once, and shows its own sentence when the edge limits requests. On event 6 a
  sign-in failed once with no request reaching the backend; the new code is
  what would name it.
- The Studio WAF rule allows 1,000 `/api` requests per IP in 5 minutes and
  answers a block with 429 `{"detail":"requests_limited"}`. One participant
  makes about 140 in a heavy 5 minutes; the capture tooling crossed the old
  limit of 300.
