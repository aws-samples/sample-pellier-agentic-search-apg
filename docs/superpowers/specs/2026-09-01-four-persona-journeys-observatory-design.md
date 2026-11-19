# Pellier Governed: Four Persona Journeys and Observatory Design

> **Historical design record.** This document describes the plan at the date above, not the current
> workshop. For the four labs as they ship, see [the story arc](../../WORKSHOP-STORY-ARC.md) and
> [workshop/story-arc.json](../../../workshop/story-arc.json).

Date: 2026-09-01
Status: Approved design, implementation in progress
Source branch: `governed`

## Purpose

Make the four lab personas a single participant journey rather than four
loosely related demonstrations:

1. Marco grounds a live answer in Aurora PostgreSQL.
2. Anna builds and measures bounded PostgreSQL hybrid retrieval.
3. Theo proves a multi-turn managed AgentCore path.
4. Jessica proves identity, authorization, database scope, non-execution, and
   operator evidence as separate boundaries.

The Storefront, Observatory, proof drivers, tests, and Workshop Studio guides
must use the same prompts and describe the same evidence. The Observatory
remains optional and reads the same evidence as `psql` and the AgentCore CLI; it
does not become a second completion system.

## Architectural Boundaries

The workshop must keep these responsibilities distinct:

| Boundary | Owns | Does not prove |
|---|---|---|
| Browser conversation context | The bounded prior dialogue sent with the next request | Durable recall or authorization |
| AgentCore short-term memory | Session continuity and managed fresh-process recall | Customer facts or database ownership |
| Aurora procedural context | Skills, tool contracts, catalog, inventory, retrieval configuration | Who is allowed to invoke a governed action |
| Aurora episodic context | Customer facts, orders, and durable business history | The current caller's identity |
| Cognito | Verified user identity and immutable subject | Permission to act on a requested customer |
| Cedar | Whether the verified principal may attempt the requested action | Whether a database row can be read or changed |
| PostgreSQL RLS | Row ownership for reads and writes | Whether the upstream policy decision was correct |
| OTEL and receipts | What path and execution were observed | Permission or successful business effect by themselves |
| Human review | Confirmation of a prepared consequential action | Identity, Cedar authorization, or RLS scope |

Every surface must label unavailable evidence as unavailable. It must not
replace a missing managed receipt with a local fixture or infer authorization
from a successful answer.

## Canonical Three-Turn Journeys

### Marco: Lab 1, PostgreSQL Grounding

| Turn | Prompt | Boundary and expected proof |
|---|---|---|
| 1 | `What linen do you have for 10 days in Goa?` | Search Agent reads the live Aurora catalog and returns named products with current identifiers and prices. The request begins with zero prior dialogue messages. |
| 2 | `What would go with the Hadley shirt?` | The next request carries the exact turn-one user and assistant messages. The agent resolves "the Hadley shirt" without substitution and uses the related-products tool or a directly grounded catalog query. |
| 3 | `Is the Hadley shirt at the Brooklyn warehouse, and can it still ship in time?` | The request carries four prior messages. The Inventory Agent calls `check_inventory`; Aurora owns the warehouse quantity and ship window; one session-scoped execution receipt identifies the call. |

Lab 1 proves grounding and tool construction. It does not claim managed Runtime,
Gateway, Cedar, or RLS.

### Anna: Lab 2, Bounded Hybrid Retrieval

| Turn | Prompt | Boundary and expected proof |
|---|---|---|
| 1 | `A thoughtful gift for someone who loves morning rituals` | Personalization uses Aurora episodic context and the live catalog to establish a gift intent. |
| 2 | `Keep the gift under $100 and show me the strongest two options.` | The request carries two prior messages. PostgreSQL hybrid retrieval applies the explicit budget and stock constraints before display. No recommended product may exceed the stated limit. |
| 3 | `Which one should I choose, and prove it stayed in budget and in stock?` | The request carries four prior messages. The response preserves the exact two prior product identities, chooses one, and links the retrieval receipt used to reconstruct vector rank, FTS rank, RRF, rerank, price, stock, and eligibility. |

Lab 2 proves ranking and SQL enforcement. A model may propose relevance signals;
PostgreSQL owns hard eligibility.

### Theo: Lab 3, Managed AgentCore Path

| Turn | Prompt | Boundary and expected proof |
|---|---|---|
| 1 | `Hand-thrown ceramics for a slower morning routine` | Runtime receives a Theo-scoped request and Gateway-visible tools return live Aurora products. |
| 2 | `What goes well with the pour-over set?` | The request carries two prior messages. The agent resolves the prior ritual and exact product while AgentCore short-term memory records the managed session. |
| 3 | `Without asking me to repeat the ritual or material, which pairing should I choose and why?` | The request carries four prior messages. A fresh process recalls the session, the answer preserves the products from turn two, and one correlated trace contains Runtime, model, Gateway/tool, and memory evidence. |

Lab 3 proves the managed rail only when Runtime reports the managed path, the
fresh-process memory verifier succeeds, and the expected OTEL predicates pass.
A Storefront-only success is not equivalent proof.

### Jessica: Lab 4, Identity and Governed Non-Execution

Jessica is a Cognito customer principal and an Operator client case. She is not
a fourth Storefront selector. The Operator signs in as the separate `operator`
principal, which alone belongs to `pellier-operators`.

The participant exercises a four-case identity matrix:

| Case | Verified principal | Requested customer | Expected result |
|---|---|---|---|
| 1 | Marco | Jessica | Cedar `DENY`; zero tool execution, zero canonical write, zero business ledger rows |
| 2 | Anna | Jessica | Cedar `DENY`; zero tool execution, zero canonical write, zero business ledger rows |
| 3 | Jessica | Jessica | Cedar `ALLOW`; exactly one execution and one canonical write owned by `CUST-JESSICA` |
| 4 | Jessica replay | Jessica | Same idempotency key; canonical write count remains exactly one |

PostgreSQL RLS is proved independently: Marco cannot read or write Jessica's
rows, while Jessica can operate only within her mapped customer scope.

The Operator case then uses three guided requests:

| Turn | Operator request | Boundary and expected proof |
|---|---|---|
| 1 | `Investigate Jessica's open service issue (TKT-2026-3015) and recommend the next fair step. Distinguish what the records establish from what a source reports.` | The Case Investigator separates authoritative Aurora rows from the ticket assertion. |
| 2 | `Which customer, order, return, and identity records are authoritative for this decision?` | The response identifies the owning Aurora records and explains that Jessica's customer principal, the operator principal, Cedar, and RLS answer different questions. It exposes no raw token or subject value. |
| 3 | `Prepare the fairest next step for human review without executing it.` | The Resolution Planner may prepare one exact review candidate. The UI must state that no action is authorized or executed until a person confirms it and Cedar plus Aurora independently permit it. |

### Required Lab 4 Delivery Shape

Lab 4 must fit the workshop's 25-minute room clock without making the strongest
governance proofs optional.

The required path is:

1. **Build:** author, validate, and deploy the Cedar identity-to-customer rule.
2. **Exercise:** run `scripts/prove_identity_boundary.py` once. Its Marco DENY,
   Anna DENY, Jessica ALLOW, and Jessica replay cases are the canonical managed
   exercise.
3. **Prove:** inspect the exact-key execution/write matrix, then run both the
   RLS read filter and RLS `WITH CHECK` write-refusal assertions.
4. **Synthesize:** complete Jessica's three-turn Operator investigation and
   stop at the human-review boundary.
5. **Reset:** remove the participant policy and prove the baseline is restored.

The two verbose hand-written Gateway calls and the full SQL notebook remain
available as optional decomposition and recovery material. They must not
duplicate the required path or make participants repeat the same proof twice.

The final participant-facing matrix must keep these states visible as separate
columns:

```text
Cognito identity
-> Cedar authorization
-> tool execution
-> PostgreSQL RLS
-> durable effect
-> OTEL / receipt
-> human approval
```

## Conversation and Product Artifact Contract

The frontend sends at most the bounded recent dialogue plus the product cards
that were actually rendered for assistant turns. The expected progression for
each three-turn journey is:

```text
turn 1 request: 0 prior messages
turn 2 request: 2 prior messages
turn 3 request: 4 prior messages
```

Rendered product identity is context, not current truth. Price, stock, and
eligibility are refreshed through tools when the current request depends on
them.

The final prose and rendered product cards must share one grounded product set:

- A product named as a recommendation must have the same identifier and price
  in the rendered artifact.
- A card may not show a similar or previously purchased product when the prose
  recommends a different product.
- A budget-constrained response may not recommend or render an item above the
  limit.
- Follow-up turns must preserve prior product identities unless the response
  explicitly says it is replacing one and explains why.
- Intermediate tool-planning narration must not appear as a completed shopper
  answer.

## Source-of-Truth and Cross-Repo Alignment

The governed source repository owns:

- canonical Storefront and Operator prompt strings;
- the `0 -> 2 -> 4` conversation-history contract;
- tool, memory, identity, policy, RLS, receipt, and OTEL behavior;
- the Lab Collection and Workbench presentation.

Workshop Studio owns participant instructions, but its validator must compare
the four persona anchors and canonical prompts against the governed source
checkout. Studio may explain the prompts; it must not invent alternate ones.

## Participant Exercise Contract

Every lab begins with one deliberately incomplete artifact in both a local
governed checkout and a freshly provisioned Workshop Studio account:

| Lab | Incomplete starter | Participant-authored boundary | Escape hatch |
|---|---|---|---|
| 1 | Inventory Agent definition and `check_inventory` tool body | A bounded Strands specialist and typed Aurora tool | Two marker-preserving Python reference files |
| 2 | `workshop/lab-2-rrf.sql` | The PostgreSQL RRF expression | A complete psql worksheet |
| 3 | `workshop/lab-3-otel-contract.jq` | Four OTEL acceptance predicates | A complete jq contract |
| 4 | `policies/workshop_identity_match_forbid.cedar` | The fail-closed identity-to-customer condition | A complete Cedar rule |

Provisioning and `scripts/reset-governed-workshop.sh` must restore the same
starter state. They must never copy the Lab 1 solutions or the Lab 2-4 reference
artifacts over the live participant files. A shared reset helper owns the
mapping so bootstrap, reset, tests, and guide recovery commands cannot drift.

Each lab guide presents the build in two adjacent learning lanes:

1. **Build it yourself:** the exact marker, acceptance criteria, and progressive
   hints without the final answer.
2. **Use Claude Code:** one bounded prompt that may edit only the named artifact
   and must show the participant the diff before acceptance.

The deterministic solution copy remains an optional pacing fallback after one
failed attempt or the lab's stated timebox. Taking the fallback does not waive
the live exercise or proof.

Every lab keeps one required proof command, one expected result, and one named
evidence artifact. Detailed psql notebooks and architecture rationale live in
optional expanders.

`WORKSHOP.md` is a co-presenter brief. It should summarize:

- the four persona anchors;
- the Storefront, Operator, Observatory, and Workshop Studio surfaces;
- what participants build, exercise, and prove in each lab;
- the distinction between local validation and live AWS proof;
- that the material remains a work in progress.

## Observatory Visual Design

Reading the surface as a technical evidence workbench for workshop
participants, with the Storefront's premium editorial language and a quieter,
more operational density.

Design dials:

```text
DESIGN_VARIANCE: 6
MOTION_INTENSITY: 3
VISUAL_DENSITY: 6
```

### Lab Collection

- Remove the botanical background treatment and floating framed hero.
- Use an unframed, full-width editorial band with the title, one primary
  command, and four large persona/lab images.
- Use real 960px AVIF/WebP derivatives. Jessica must be generated from the
  original portrait source, not enlarged from the 480px derivative.
- Keep the Storefront display and body font families.
- Use one filled burgundy primary command. Secondary navigation uses text plus
  an arrow; status is not styled as another competing button.
- Present the four labs as quiet collection rows or a restrained asymmetric
  grid. Cards use at most an 8px radius and are never nested inside another
  card.
- The selected lab opens in the same Workbench and carries its persona,
  prompts, acceptance target, and evidence links with it.

### Shell and Workbench

- Reduce pill-shaped controls and decorative badges.
- Give icon buttons consistent dimensions, tooltips, focus states, and active
  states.
- Use thin rules, stable columns, and restrained status color so evidence is
  easier to scan.
- Keep the header to one line at desktop and provide an explicit mobile
  collapse.
- Preserve live loading, empty, unavailable, and contradiction states.
- References remain concise contextual links inside Labs and Workbench rather
  than a fifth product surface.

## Validation

Implementation is complete only after:

1. Backend tests prove the bounded history, product/prose identity, budget
   enforcement, identity matrix, receipt counts, and RLS behavior.
2. Frontend tests prove canonical prompts, Lab 1-4 persona alignment, responsive
   images, and product-card continuity.
3. Studio validation proves all four lab guides use the source prompts and
   correct persona.
4. Browser runs complete all three Storefront turns for Marco, Anna, and Theo,
   all three Operator turns for Jessica, and the Lab Collection/Workbench path.
5. Desktop and mobile screenshots show no broken media, overflow, overlap, or
   unreadable controls.
6. Full backend, frontend, type-check, lint, production build, Studio validator,
   Python compilation, shell syntax, and `git diff --check` gates pass.
7. Live AWS behavior is described as unproven unless Cognito, Runtime, Gateway,
   Policy, Memory, OTEL, and Aurora were actually exercised in the target
   account.
