# L400 exercise brief: Aurora PostgreSQL search and AgentCore

Updated direction from the workshop owner, September 12, 2026. This is the
source brief implemented in the sibling Workshop Studio draft, not a published release.

## Proposed session framing

**Level:** 400

**Title:** Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore

Keep the approved RDS framing in the abstract. The background callout explains that this deployment uses Aurora RDS Data API and an RDS for PostgreSQL adaptation uses native connections. Participants do not deploy a second database.

**Proposed abstract:**

Build and troubleshoot a governed retail search application using Aurora
PostgreSQL, the Strands Agents SDK, and Amazon Bedrock AgentCore. Write
database-backed tools, combine PostgreSQL full-text search with pgvector, and
use Cohere Rerank to order retrieved candidates. Diagnose missing results with
SQL query plans and controlled comparisons. Deploy a dispatcher and specialist
agents to AgentCore Runtime, retrieve scoped conversation context with Memory,
and publish tools through Gateway. Write Cedar policies in AgentCore Policy,
then verify allowed and denied tool calls against service traces and Aurora's
JSONB audit ledger. Work from a prepared application and leave with reusable
retrieval, deployment, and governance patterns. Bring your laptop; experience
with Python, SQL, and AWS is expected.

This replaces passive exploration with observable participant work. It scopes
policy enforcement to tool calls, rather than claiming that every model
interaction passes through Cedar. Strands owns the application routing and
agent behavior; Runtime, Memory, Gateway, and Policy have separate jobs.

## Audience and scope

Design for advanced AWS customers in a 100-minute session. Participants write
code, investigate PostgreSQL search behavior, and deploy and inspect the
managed agent path. Use clear instructions and concrete expected results.

Do not ask participants to build an evaluation framework. That requirement
belongs to AgentEats. Small provided query sets, SQL assertions, result
comparisons, and query-plan measurements can prove a change without becoming
a separate framework-building exercise.

Search and retrieval are the required thread. Theo's interrupted replacement
remains a product scenario and possible extension; fulfillment and recovery
must not displace the core search work.

## Candidate 100-minute path

Validate these budgets in a timed rehearsal before changing the published guide.

| Minutes | Case | Participant work | Evidence of completion |
| --- | --- | --- | --- |
| 0–5 | Orientation | Read the architecture and follow one request across Storefront, Operator, and Observatory. Start Theo's supplied Memory conversation so extraction can run during Labs 1 and 2. | Identify which component retrieves data, which authorizes a tool, and which holds authoritative records. Retain the Memory actor and event IDs. |
| 5–25 | Marco: grounded PostgreSQL retrieval | Begin with a supplied, working stock query. Complete the bounded database tool and Inventory Agent selected by the dispatcher. Preserve the typed input contract, eligibility rules, and exact warehouse facts. | Distinguish an unknown product from a known product with zero stock. Trace the selected specialist and verify its answer against SQL and the tool execution record. |
| 25–50 | Anna: hybrid search that respects constraints | Complete a live RRF or candidate-selection code path. Inspect lexical and vector candidates, compare hybrid and Cohere-reranked results, and diagnose one missing result under a selective filter. | Use a small supplied query set. Record returned IDs, filter correctness, and `EXPLAIN (ANALYZE, BUFFERS)` evidence. Explain the candidate-pool tradeoff and what the reranker cannot recover. |
| 50–75 | Theo: deploy and inspect managed retrieval | Publish a customer-scoped retrieval tool through Gateway, reconcile the specialist's tool catalog, and deploy the Runtime change. Work through one deliberate catalog mismatch. | Invoke the deployed path, verify its build and tool identity, and connect the result to Aurora records. Use a preference extracted from the supplied earlier conversation in a new session, then recheck current business facts in Aurora. |
| 75–95 | Jessica: scoped retrieval and governed actions | Investigate a conflicting support claim. Complete the Cedar identity-to-customer condition and a keyed SQL absence query. Run the permitted and out-of-scope return requests against the managed tool. | Show the actual policy result, the matching positive control, and the committed or absent database effect. Use the provided refusal and replay checks to distinguish authorization, business validity, and idempotency. |
| 95–100 | Close | Explain one design decision using the evidence collected. | State what changed, why it helped, and the condition under which a different choice would be appropriate. |

## Progressive difficulty

Start with a result participants can recognize, then increase the number of
boundaries they must reason about. The first lab should make them confident in
the tools; later labs should require them to diagnose the system.

| Stage | First step | New challenge | What carries forward |
| --- | --- | --- | --- |
| Marco | Run a working stock query and predict its result. | Turn database facts into a typed tool response. Handle missing and zero stock correctly. | SQL evidence, a bounded tool contract, and a request ID. |
| Anna | Run the same request through the supplied lexical and vector queries. | Change live fusion or candidate selection. Explain a missing candidate with a query plan, then compare the reranked result. | The same constraints, product IDs, and evidence discipline. |
| Theo | Discover the deployed tool catalog and identify the missing capability. | Repair the catalog contract, deploy the change, and prove which build ran. Use scoped Memory across sessions without treating it as current stock or order truth. | The same tool behavior across a managed boundary. |
| Jessica | Read one support assertion beside the authoritative order and return rows. | Write the ownership policy and prove that an out-of-scope attempt did not execute. Explain an authorized business refusal separately from a policy denial. | Retrieval, identity, deployment, and database evidence combined in one case. |

Within every lab, use **predict, build, run, inspect, explain**. Give one worked
example, one bounded edit, and one result the participant must interpret. Keep
the second edit or challenge close to the first. Increase reasoning depth
rather than the number of unfamiliar commands.

For the 100-minute rehearsal:

- Pre-provision resources and seed data. Participants deploy the relevant
  application change, not an entire environment from an empty account.
- Start asynchronous Memory extraction in the opening exercise. Inspect it
  during the later deployment wait rather than making the room wait twice.
- Use one required retrieval defect and one required catalog mismatch. Extra
  HNSW tuning, larger corpora, and fulfillment recovery are extensions.
- Put a catch-up checkpoint before the Runtime deployment and before policy
  proof. Restoring a prepared edit does not replace running its evidence checks.
- Keep ten of the scheduled lab minutes available for reading and recovery
  within their budgets. A rehearsal that consumes all 100 minutes with ideal
  execution has failed the timing target.

## What makes the hands-on work substantial

- Give each lab a useful failure to diagnose: an eligible result missed by
  filtered vector search, a lexical match outranking a better hybrid result,
  a stale tool schema, or an out-of-scope request.
- Make each change alter observable behavior. Avoid edits that only rename a
  variable or reproduce a completed implementation.
- Separate eligibility from ranking. A relevant product can still be
  ineligible because of stock, archive status, or caller scope.
- Require participants to inspect at least one real PostgreSQL query plan.
  Explain what the plan says about rows considered, filtering, index use,
  buffers, and latency. Do not prescribe one latency number for every account.
- Keep a small retrieval comparison worksheet: request, expected constraints,
  returned IDs, and one relevant measurement. No model judge or generic
  scoring infrastructure is required.
- Include one deliberate deployment mismatch with a bounded repair. The
  participant should identify whether the problem is the tool contract,
  published catalog, deployed build, or authorization.
- Make the JSONB audit ledger useful: filter by the exact request or turn,
  inspect the attempted tool and outcome, and join to the relevant business
  record. A policy denial and the absence of a matching business effect are
  separate checks.
- Use exact request, turn, and record IDs to connect the application to
  evidence. Opening a page or receiving fluent prose is not completion proof.

## Gaps to close before publishing this abstract

- The current Lab 2 RRF worksheet reconstructs recorded scores; it does not
  modify the application's live retrieval implementation. The revised lab
  needs a bounded live code or SQL build to support the stronger promise.
- Include Cohere Rerank explicitly in Anna's experiment. Keep retrieval,
  fusion, and reranking visible as distinct stages.
- Keep Strands specialist dispatch, the new-session Memory check, the deployed
  Runtime build, and the Gateway tool contract as observable outcomes.
- Retain a real sensitive action in Jessica's path. Retrieval scoping alone
  does not fulfill the abstract's Cedar authorization promise.
- Keep the required path within 100 minutes in rehearsal. Pre-stage
  infrastructure and data; provide the comparison queries and replay checks.
  Do not turn the closing lab into a new fulfillment implementation.

## Guide structure and architecture

Use the [architecture package](architecture/README.md) for the overview and
background. It includes an editable PowerPoint deck, a managed application
overview, a retrieval detail diagram, and PNG/SVG exports using the supplied
AWS July 31, 2026 dark-background icon deck.

Start each persona lab with a two-column table: **Component** and **Its job in
this case**. Follow it with that lab's architecture diagram. Show the current
execution boundary and explain why each component is needed.

Use precise labels: Aurora PostgreSQL owns catalog and business records;
AgentCore Runtime runs the managed shopper path; Gateway exposes tools;
Memory supplies scoped conversation or preference context; Cedar authorizes
the relevant invocation. The existing Bedrock-backed Operator graph runs in
a separate IAM-authenticated AgentCore Runtime after Lab 3. The backend reads scoped evidence and owns human checkpoints; the graph recommends without business tools.

Each task should use this sequence:

1. State the customer problem and the expected system behavior.
2. Point to the exact file or SQL section to change.
3. Explain the contract the participant must preserve.
4. Give the request or command that exercises the change.
5. Show what to inspect and how to distinguish success from failure.
6. Explain the design decision and its tradeoff in a short paragraph.

Provide bounded starting points, prepared data, and catch-up artifacts so
participants spend the session reasoning and coding. Keep readiness checks
with the facilitator. Workshop Studio publication, source pinning, and
screenshots follow the completed implementation and timed rehearsal.

## Application journey acceptance

The application is the shared customer story throughout the session.
Observatory is a required part of that story; commands, service responses, and
SQL remain the completion evidence.

Before the lab guide is finalized, walk the following path at desktop and
workshop widths:

1. Open a fresh Storefront, dismiss orientation, choose Marco, Anna, or Theo,
   and return to the same conversation after switching surfaces.
2. Submit a grounded request, inspect its returned products, and follow the
   exact turn into Observatory. Preserve the request identity in the link.
3. Enter Operator with the separate staff sign-in, open the client book or
   action queue, and open that client's Concierge chat without searching for a
   hidden feature.
4. Read the investigation, service sources, and proposed remedy. Keep human
   confirmation, policy authorization, and the durable outcome distinct.
5. Follow the case or operation into Observatory, then return to the same
   client record. An unrecorded result remains unknown.
6. Check loading, empty, expired identity, policy denial, unavailable service,
   and retry states. Preserve the question draft when submission fails.

A fixture can verify navigation, layout, and recovery controls. It cannot prove
live authentication, managed tool execution, Memory retrieval, or an Aurora
commit. Record those as separate rehearsal checks.
