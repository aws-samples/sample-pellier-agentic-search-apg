# DAT416 speaker and facilitator brief

**Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore**

Level 400. 100 minutes. Four labs, eight bounded builds, two participant workflows.

This brief explains the teaching plan. Workshop Studio contains the participant
commands, marked exercises, hints, and recovery steps. The schedule is a target
until a fresh-account rehearsal establishes actual reading, editing, deployment,
Memory extraction, and trace-ingestion times.

## The outcome

Participants build a retail agent and explain its behavior from evidence. A
Strands dispatcher selects a specialist. Aurora PostgreSQL supplies catalog,
inventory, orders, and customer records. Bedrock AgentCore provides Runtime,
Memory, Gateway, and Policy. Each lab asks a different engineering question:

1. Which database facts support the answer?
2. Why did these products rank, and do they satisfy the constraints?
3. Which build ran, and did a new conversation use context learned earlier?
4. Who was allowed to act, what executed, and what changed?

The small code edits leave time for L400 reasoning: choose the right authority,
predict a failure, inspect independent evidence, and explain what that evidence
can establish. Participants should be comfortable reading Python and SQL, using
a terminal, and working with AWS identity and permissions. The guide introduces
the Cedar syntax and service commands needed here.

## The session schedule

Times are elapsed minutes from the beginning of the session.

| Workshop minutes | Activity | Duration |
|---|---|---|
| 0-5 | Introduction and Theo's first conversation | 5 minutes |
| 5-25 | Lab 1: Build a PostgreSQL-Grounded Agent | 20 minutes |
| 25-50 | Lab 2: Build and Measure PostgreSQL Hybrid Retrieval | 25 minutes |
| 50-75 | Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore | 25 minutes |
| 75-95 | Lab 4: Build Governed Agent Actions with Cedar | 20 minutes |
| 95-100 | Summary and policy cleanup | 5 minutes |

Opening context and orientation share minutes 0-5. Participants follow the complete guide and all three app surfaces. Use catch-up by minute 15 for Lab 1 and minute 40 for Lab 2; start managed deployment by minute 55 and policy deployment by minute 80. Reading, explanation, and recovery share the lab allocations. Rehearse the full path with a clock before release.

## Introduction

Participants open Code Editor and Pellier, record a run ID, check Aurora, and
observe a turn on the predeployed Runtime. They then save Theo's first conversation
so AgentCore can extract preferences while they complete Labs 1 and 2.

Pellier gives each exercise a concrete reason to exist. Marco needs inventory
facts, Anna needs a measured recommendation, Theo needs continuity and support,
and Jessica needs a governed service decision.

| Surface | Participant use | Authority |
|---|---|---|
| Storefront | Marco, Anna, and Theo's shopping conversations | Displays results grounded by tools |
| Code Editor | Eight marked edits and the supplied proof commands | Source, service responses, SQL results, and saved evidence |
| Operator | Jessica's investigation under the separate staff account | Staff access and an explicit human decision boundary |
| Observatory | Optional inspection of the same requests | Projects evidence; an interface badge alone does not prove a claim |

Selecting a scenario does not sign in as that customer. Cognito establishes the
principal. Aurora maps the verified subject to a customer; the token's customer
claim supports the Cedar ownership check. The `operator` account is separate
from Jessica's shopper identity.

Storefront turns follow a deterministic dispatcher and one of five specialists:
search, recommendation, pricing, inventory, or support. Each specialist receives
a bounded tool list. The other participant workflow is the Operator Concierge
graph, where Case Investigator runs before Resolution Planner. Other Strands
reference implementations in the repository are outside the required journey.

Use the guide's exact prompts for the measured path. Each Storefront thread
contains three turns with 0, 2, and 4 prior dialogue messages. Keep Anna's fixed
benchmark request separate from her natural-language Storefront conversation.
Paraphrasing and alternative prompts are useful extensions after the checks pass.

## Aurora and AgentCore Memory

**Aurora owns business state. AgentCore Memory owns conversation context.**
Both can persist information, but persistence alone does not give information the
same authority.

| Question | Owner | Evidence |
|---|---|---|
| What does this product cost, and is it available now? | Aurora PostgreSQL | Current catalog and warehouse rows |
| Does this customer own the order, and did the return commit? | Aurora PostgreSQL | Order, return, principal, and transaction records |
| What did the shopper say in a conversation? | AgentCore Memory short-term events | Event IDs under the verified actor and session |
| What preferences or facts were extracted for later use? | AgentCore Memory long-term records | Retrieved record IDs and their content |
| What does an agent do with a tool? | Reviewed source | Tool schemas, instructions, and the executed build fingerprint |
| What tool ran and what effect followed? | Aurora audit, write, and domain tables | Correlated attempt and transaction evidence |

A remembered preference can guide a recommendation. It cannot establish current
price, stock, order ownership, or permission to write. An extracted statement
about a past purchase must be checked against Aurora before it supports a return.
`tool_audit` records execution; it is not evidence that AgentCore retained or
learned conversation context. Aurora order history is not AgentCore episodic memory.

The source configures `SEMANTIC`, `USER_PREFERENCE`, `SUMMARIZATION`, and `EPISODIC`
strategies. The required experiment waits for extracted facts, preferences, and a
session summary. A consolidated episode is optional. Resource or strategy status
`ACTIVE` does not establish that extraction has produced any records.

### The required cross-session experiment

1. During Introduction, record Theo's supplied first conversation. Preserve its
   actor and event IDs. The conversation is scripted; the long-term records are
   extracted by AgentCore rather than seeded by the application.
2. Continue Labs 1 and 2 while extraction runs. Do not restart the experiment or
   wait at the Introduction screen for long-term records.
3. In Lab 3, retrieve those records into a new conversation with no prior chat
   events. Pass the retrieved context to the deployed agent and invoke current
   catalog tools.
4. Inspect the preference record IDs, identify a preference actually used in the
   answer, and read a recommended product's current price and stock from Aurora.
   Merely receiving records does not prove correct use of them.
5. Preserve the proof separately from the Storefront conversation-history check.
   Learning here means extracting and retrieving context; model weights do not change.

The experiment derives one actor from a verified subject and an isolated run ID.
Both conversations share it but have different session IDs. Ordinary Storefront conversations retain their
conversation-specific actor, `user-{sub}-session-{sid}`. They do not silently
acquire cross-session preference sharing. A production design must choose actor
continuity and enforce access to its namespaces; a naming convention is not an
access-control policy.

## Four labs, eight builds

### Lab 1: Build a PostgreSQL-Grounded Agent

Marco needs a reliable answer about warehouse stock.

**Predict:** an unknown product and a known product with zero stock require
different answers.

**Build 1a:** define the Inventory Agent so the dispatcher can select it.
**Build 1b:** implement the bounded inventory tool against the warehouse tables.

**Check:** compare the Storefront answer with Aurora and the execution row written
after the baseline. The supplied contract check invokes the participant's own
body for a product absent from the catalog and a sold-out product. The unknown
product carries no count. The sold-out product returns zero with every warehouse
accounted for.

**Explain:** the tool contract determines what the agent may conclude. A fluent
answer cannot turn missing data into a verified zero.

### Lab 2: Build and Measure PostgreSQL Hybrid Retrieval

Anna needs relevant products that satisfy her budget and stock constraints.

**Predict:** changing the rerank pool may change quality, latency, and cost.
Ranking cannot make an ineligible product eligible.

**Build 2a:** reconstruct the reciprocal rank fusion expression in a SQL worksheet
and compare it with recorded ranks and scores. This verifies the calculation; it
does not replace the application's live search implementation.
**Build 2b:** change `DEFAULT_RERANK_POOL_K` inside the candidate-budget markers. The starter sends only three fused candidates to reranking. Keep explicit overrides and the configured ceiling.

**Check:** save the before/after comparison for one fixed request. Read `EXPLAIN (ANALYZE, BUFFERS)`, locate a candidate removed before reranking, and trace its exact ID after the edit. Recompute the receipt’s RRF scores and check price, stock, and archive predicates. A sequential scan can be appropriate on the small catalog; a single timing is not a production benchmark.

**Explain:** retrieval budgets and eligibility solve different problems. A reranker cannot recover a candidate outside its input pool. No evaluation-framework build is required.

### Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore

Theo returns for recommendations without repeating his preferences, then needs
customer-scoped support through the managed agent.

**Predict:** a successful response could still come from the previous Runtime
package. A repeated preference could still come from copied chat history.

**Build 3a:** publish the customer-scoped `get_ticket_history` read. Keep
`restock_inventory` deferred. The separately published `issue_credit` remains
staff-only.
**Build 3b:** reconcile the support specialist's managed tool list and bind the
read to the authenticated customer.

**Check:** start deployment by minute 55. Complete the new-session Memory experiment, then
run Theo's signed-in Storefront thread against the deployed path. Read its Memory
events from a separate Python process. Compare the executed and expected build
fingerprints, and run the supplied trace contract on the thread's downloaded
trace. Runtime redacts prompt and tool content, so this contract checks span
structure and correlation instead.

Publication and discovery are different checks: Gateway filters the tool list by
policy. A tool visible to a caller still needs authorization for its actual
arguments. Do not compare a shopper's listing with the full published catalog.

**Explain:** deployment status, executed build, Memory events, learned context,
and traces each establish a separate fact. The new-session experiment supplements
the three-turn continuity check; the two should not be described as the same proof.

### Lab 4: Build Governed Agent Actions with Cedar

Jessica's return requires the correct identity, an eligible order, and one effect.

**Predict:** the same return workflow can be denied by policy, refused by a
business rule, committed, or replayed without another effect.

**Build 4a:** complete the Cedar identity-to-customer condition. Compare the
verified customer claim with the requested customer. Keep Aurora's independent
row-level security intact.
**Build 4b:** author the keyed absence query beside its positive control.

| Attempt | Expected outcome | Evidence |
|---|---|---|
| Marco requests Jessica's return | Policy denial | Denied key absent from execution and effect tables |
| Jessica requests a product she never ordered | Business refusal after authorization | Tool attempt with no committed return |
| Jessica requests her returnable product | Allowed and committed | Finalized write and the Jessica-owned return row |
| Jessica repeats the allowed write key | Allowed replay | Another audit attempt, the same finalized write and return |

The business-refusal case changes the product intentionally. Do not claim that
identity is the only input that varies across all four cases. The policy denial
must have a matching positive control; four zeros alone could mean the query
searched the wrong run or key.

**Check:** run the four cases, the independent RLS read/write probes, and the
participant's absence query. Sign in as `operator` and investigate Jessica's
service issue. The exploratory turn runs Case Investigator and Resolution
Planner. It does not itself promise a new approval record. Stop before any
consequential action; additional proposal prompts are optional.

**Explain:** authentication, Cedar authorization, business validity, RLS,
execution, idempotency, and human approval are separate controls. A direct Gateway
proof is not evidence of human approval. A previous credit replay does not prove
the return replay required here.

## Summary

Start policy cleanup after exporting the evidence. While it runs, ask: Memory
says a shopper bought an item, but Aurora has no matching order. Which source
establishes return eligibility, and which controls still decide whether it can
execute?

The build receipt checks eight source artifacts and run-scoped Aurora evidence.
Keep the separate Memory, trace, retrieval evaluation, identity, and RLS artifacts.
A marker edit alone does not prove behavior; an unreadable evidence source remains
unchecked. Download the evidence before the event account closes.

This deployment uses RDS Data API against Aurora PostgreSQL. PostgreSQL SQL,
JSONB, transactions, full-text search, RLS, and supported pgvector patterns also
apply to RDS for PostgreSQL. An adaptation requires database connections,
networking, and pooling instead of the Aurora Data API transport.

## Release and rehearsal requirements

The guides depend on the memory-showcase work and four-strategy configuration
being included in the published governed source. Preserve the release order:
intended source commit and push, immutable Workshop Studio pin, release validation,
S3 asset synchronization, Studio commit and push. Keep application validation,
published source, Studio publication, deployed proof, and rehearsal as distinct
claims.

Provision a fresh environment before the timed session and record cold provisioning
separately. Use fresh returnable data. Measure both manual and coached participant
paths, actual extraction readiness, the Lab 3 deployment, trace delivery, the four
return attempts, one Operator investigation, and cleanup. Test the documented
catch-up paths in a separate run.

Do not present earlier release-candidate results as proof of this revised Memory
journey or its timing. If the sequence exceeds its budget, reduce required work or
change the schedule explicitly. Keep the failed measurement visible.
