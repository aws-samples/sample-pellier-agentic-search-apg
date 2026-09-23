# Pellier: Build a governed agentic retail system

Pellier is a premium retail boutique building an agentic system for product discovery
and customer support. Its concierge connects customer requests to specialist agents,
current business data, and governed tools. Participants develop four connected retail
workflows: ground answers in facts, preserve requirements, establish caller identity,
and govern actions with evidence that staff can verify. Each customer retains a
separate identity and conversation. Each lab adds a responsibility and its evidence; Lab 3 introduces a separate managed execution path.

**Know the facts → respect the requirements → establish the caller → govern the action.**

The source contract is `workshop/story-arc.json`. Workshop Studio owns full
exercises. The application orients participants and shows their execution evidence.
The presenter deck introduces the same decisions through progressive diagrams.

Keep the technical lab titles as the primary headings. In `story-arc.json`,
`title` is the lab name and `storyTitle` describes the persona-led scenario.
Use the story wording in activities and transitions, not as a replacement lab name.

| Lab | Main title | Scenario |
|---|---|---|
| 1 | Build a PostgreSQL-Grounded Agent | Marco: Know the facts |
| 2 | Build and Measure PostgreSQL Hybrid Retrieval | Anna: Respect the requirements |
| 3 | Deploy and Operate Agents with Amazon Bedrock AgentCore | Theo: Establish the caller |
| 4 | Build Governed Agent Actions with Cedar | Jessica: Govern the action |

## Four labs, two participant tasks each

| Lab | Task A | Task B | Handoff |
|---|---|---|---|
| 1: Marco | Connect inventory to Aurora | Make the agent use the facts | You can check a product. Next, help Anna find the right product without changing her requirements. |
| 2: Anna | Explain the ranking | Relax preferences, keep requirements | You can find suitable products. Next, deploy Theo’s support capability and preserve the caller’s identity across the tool boundary. |
| 3: Theo | Connect the customer-scoped tool | Deploy and challenge the conversation | You can read under the right identity. Next, follow Jessica’s action through authorization, database effects and staff review. |
| 4: Jessica | Write the ownership rule | Test ownership and reconcile the case | Bring the four claims together: facts, requirements, caller and effect. Save your evidence and the next production question. |

Eight participant tasks are not eight arbitrary source edits. Task 3A spans
publication and caller binding; 3B is a deployed investigation. Task 4B includes
two SQL edits and independent results. Do not infer completion from marker removal.

## The common learning loop

The overarching story is **preserving business meaning across facts, requirements,
identity and action**. Every lab runs the same four participant steps: **Spot the
mistake → Build the contract → Challenge it → Explain the evidence.** "Challenge it"
is the lab's existing verification step plus one decision the participant makes:

| Lab | Participant decision | Independent evidence |
|---|---|---|
| Marco | The unknown, ambiguous and sold-out queries | The checker classifies each from the catalog before judging the tool |
| Anna | The preference that forces a strict-empty search | Counts before the request; the receipt records the chosen tag |
| Theo | A request, through the agent, for another customer's tickets | Lambda-written audit rows bound to Theo; direct probe denied by Cedar |
| Jessica | Which ticket item to record, with which stated reason, and what stays open | Three review snapshots; a return request is not proof of receipt |

Keep exact files, markers, commands and acceptance criteria visible. Hints reveal
reasoning progressively; worked recovery stays collapsed and is never stated in
visible prose. Record authored, recovered-and-verified, and incomplete results
separately.

## Acceptance and rejected implementations

- **1A / 1B:** Preserve the business tool envelope and use it in a real agent turn.
  Reject unknown products represented as stock zero, invented stock, or a tool
  grant treated as database authorization. Supply model/prompt boilerplate.
- **2A:** Reconstruct recorded RRF with zero contribution from a missing branch.
  Reject integer division and a missing branch becoming rank zero.
- **2B:** Every attempt keeps the original hard constraints and exclusions. Only
  the declared preference changes; preserve the original plan and the recorded
  relaxation. Reject dropping budget, availability or exclusions to obtain hits,
  mutating the original request, and an unrecorded widening. The local checker
  proves the plan contract; live receipt/SQL checks prove different boundaries.
- **3A / 3B:** Reconcile Gateway publication and caller-bound support tools,
  deploy once, then use a fresh session. Reject staff credit exposed to shopper
  support, caller-supplied foreign identity, local edits presented as deployment,
  and a remembered preference presented as permission. Runtime packages the support
  adapter, not the Lab 1 inventory wrapper or Lab 2 planner. The reused Lambda
  retrieval tool has a different input contract; do not imply fallback parity. Existing policy is active
  before Lab 4; Lab 4 authors an additional ownership rule.
- **4A:** Distinguish authentication, Cedar, business rejection, commit and output.
  Reject a 401 called Cedar DENY or suppressed output called a rollback.
- **4B:** Author an ownership predicate used by USING and WITH CHECK; test actual
  runtime roles with owned, foreign, missing and unmapped identities and rollback.
  Separately query denied-key effects with an allowed-key positive control.
  Reject all-zero queries without the control, owner-role RLS proof, and Gateway
  denial treated as proof of RLS. RLS trusts application-established context; it
  does not independently validate a Cognito token. Investigate as the separate
  operator account. Jessica's ticket names two pieces and asserts both were
  received; Aurora holds neither. Record only the robe, with the reason she stated,
  through proposal, confirmation and governed execution. Reject a preselected
  reason, confirmation treated as execution, and a return request treated as proof
  of receipt. The catchall, the receipt claim and the refund dispute stay open.
  The authored RLS predicate is rollback-only; later tool calls use the supplied policy.

## Presenter timing, separate from participant guides

The 100-minute event budgets 15 minutes for the presenter introduction, then
75 minutes for labs (15 / 15 / 20 / 25), five for recovery and five for closing.
Setup belongs at the beginning of Lab 1. Seed the supplied Memory experiment then,
so asynchronous extraction overlaps other work. Participant guides show lab
budgets and a hands-on clock only; do not add the presentation to their tasks.
These are targets pending a timed fresh-account rehearsal. Recovery does not waive
proof, and a reference walkthrough is not participant completion.

## Four accumulating claims

1. This answer came from these facts and this tool invocation.
2. These results followed this ranking and preserved these requirements.
3. This deployed build handled this request under this caller.
4. This control acted, this tool did or did not run, and these effects remain.

Storefront exposes the customer experience. Observatory inspects the evidence.
Operator uses it to support a human decision. An architecture image is not a
runtime receipt. Source edits, local tests, source release, Studio publication and
fresh-account rehearsal remain separate milestones.
