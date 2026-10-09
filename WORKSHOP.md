# DAT416 speaker and facilitator brief

**Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore**

Level 400. 100 minutes. Four labs, eight hands-on tasks in eight marked regions.

The task contract is [WORKSHOP-STORY-ARC.md](docs/WORKSHOP-STORY-ARC.md),
backed by `workshop/story-arc.json`. Workshop Studio holds the participant
guide: the commands, hints and recovery steps. This brief explains the teaching
plan. The schedule is a target until a timed fresh-account rehearsal confirms it.

## The outcome

Participants make a retail assistant answer from data, act under the right
identity, and prove what happened. Four customers each bring one worry a
store's leadership would have, and each lab answers one:

| Lab | Customer | Worry |
|---|---|---|
| 1. Build and Measure PostgreSQL Hybrid Retrieval | Anna | "Shoppers describe what they want, and our search only matches words." |
| 2. Build a PostgreSQL-Grounded Agent | Marco | "If the assistant guesses stock, we'll promise things we can't ship." |
| 3. Deploy and Operate Agents with Amazon Bedrock AgentCore | Theo | "The assistant should remember our customers, but never let one see another's account." |
| 4. Build Governed Agent Actions with Cedar | Jessica, with Nadia (staff) | "No AI moves money on its own, and when money moves, we must prove what happened." |

Every lab has the same rhythm: spot the failure live, predict, build, check,
challenge, explain. Each check prints what was expected, what was observed
and the evidence (the row, the decision, the key).

## The session schedule

Times are elapsed minutes from the start of the session.

| Workshop minutes | Activity | Duration |
|---|---|---|
| 0-15 | Presenter introduction | 15 minutes |
| 15-30 | Lab 1: Build and Measure PostgreSQL Hybrid Retrieval | 15 minutes |
| 30-45 | Lab 2: Build a PostgreSQL-Grounded Agent | 15 minutes |
| 45-65 | Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore | 20 minutes |
| 65-90 | Lab 4: Build Governed Agent Actions with Cedar | 25 minutes |
| 90-95 | Recovery buffer | 5 minutes |
| 95-100 | Summary: export the evidence | 5 minutes |

Reading, deployment waits and checks share each lab's time. Lab 3's and
Lab 4's deploys are inside their budgets. An unrun check stays incomplete.

## What participants use

Code Editor opens `Pellier.code-workspace` and `START_HERE.md`. Its numbered Retrieve, Ground, Deploy and Govern groups point at `labs/01-retrieve` through `labs/04-govern`. Each contains links to the live exercise files, a short check map and a solution README, such as `labs/01-retrieve/solution/README.md`. The fifth group exposes the complete source; terminals start at the repository root. Source extraction validates every link before the editor starts and preserves participant edits on reruns.

| Surface | Use | What it proves |
|---|---|---|
| Storefront (`/`) | Ask Pellier, the docked chat panel, for Anna's, Marco's and Theo's turns. Choosing a shopper signs in with that shopper's demo account; Pellier trusts the signed token, not the choice. | The Builder view shows each turn's Router step, the tools the agent called and "How it ranked". It shows evidence; it does not replace the checks. |
| Operator (`/operator`) | Nadia, a staff account, investigates Jessica's case and approves or rejects the proposed credit. | A person's decision, recorded on the review before any credit is written. |
| Code Editor | The eight tasks and every check. | Source, SQL results, service responses and the evidence export. |

Shoppers and staff sign in through Amazon Cognito and keep separate sessions.
Jessica's shopper identity and Nadia's staff account are different principals.
On the managed path, Runtime revalidates the access token and resolves the
shopper from its signed claims; conflicting payload identities are refused
before an agent is constructed. Runtime and Gateway both require access tokens.
Nadia's execution carries her own staff token directly to Gateway; it does not
borrow Jessica's identity. These controls are supplied infrastructure, outside
the participant edit regions.

## The system participants work in

- **Router and three agents.** A deterministic Router, with no model call,
  sends each shopper request to the Shopping, Stock or Support agent
  (Strands). Shopping and Support run on Claude Opus 5, Stock on Claude
  Sonnet 5. Each agent holds only its own tools; the Stock agent's starter
  grant is wider until Lab 2B narrows it.
- **Nine store tools.** `search_products`, `browse_department`,
  `compare_products`, `check_stock`, `get_orders`, `get_return_policy`,
  `get_tickets`, `give_store_credit` and `ask_a_person`. One implementation,
  `pellier/backend/services/store_tools.py`, serves the local agents and the
  Gateway Lambda.
- **Ten Aurora tables.** The catalog, warehouse stock, customers, orders,
  return policies, support tickets, approvals, store credits, `tool_audit`
  and retrieval receipts (`scripts/migrations/001_schema.sql`).
- **Two rails.** Labs 1 and 2 run the agents in process, so participants prove
  their own code. Lab 3 moves the Storefront onto AgentCore Runtime, where the
  same Router and agents get their tools through AgentCore Gateway and Cedar
  decides each call before the Lambda runs.
- **The Operator's investigation.** A two-node Strands graph, Investigator then
  Planner, runs in process. It reads the case, proposes one store credit and
  stops. Nothing is written until Nadia approves and executes it.

## Aurora and AgentCore Memory

**Aurora owns business state. AgentCore Memory owns conversation context.**

| Question | Owner | Evidence |
|---|---|---|
| What does this product cost, and is it in stock now? | Aurora | Catalog and warehouse rows |
| Does this customer own the order, and was the return received? | Aurora | Order rows and their return status |
| What did the shopper say in a conversation? | AgentCore Memory | Events under the verified actor and session |
| What preference was extracted for later? | AgentCore Memory | The record and its id |
| What ran, for whom, with which build? | Aurora | `tool_audit` rows |

A remembered preference can guide a pick. It cannot establish a price, stock,
order ownership or permission to act. Provisioning records Theo's first
conversation, and AgentCore Memory extracts his preference from it. In Lab 3, a new session's Builder view names the record the agent
was given (`Remembered: AgentCore Memory record <id> (user preference)`), and
`scripts/lab3_check.py` reads the same record back.

## The four labs

### Lab 1: Build and Measure PostgreSQL Hybrid Retrieval

Anna wants a housewarming gift under $100, in stock, with no candles.

- **Spot:** forced onto its fallback, her search returns a candle and a
  sold-out piece.
- **Task 1A:** write the RRF fusion expression in `workshop/lab-1-rrf.sql`. A
  missing rank contributes zero, never rank zero.
- **Task 1B:** keep her limits on the fallback in
  `pellier/backend/services/search_plan.py`. A fallback may relax a
  preference; it keeps the budget, the stock rule and the exclusions.
- **Check:** the worksheet recomputes every recorded score from its two ranks;
  `python3 scripts/lab1_compare.py` shows the search that answered kept every
  limit she asked for, and every product it returned meets them.
- **Explain:** similarity decides the order; SQL decides what is eligible.
- **Managed path:** the Gateway's store tools Lambda is packaged at
  provisioning, and the Lab 3 and Lab 4 participant deploys look it up rather
  than repackage it. Task 1B therefore changes the in-process search only; a
  search through the Gateway keeps the starter fallback until a full
  provision.

### Lab 2: Build a PostgreSQL-Grounded Agent

Marco needs reliable stock and dispatch facts before his trip.

- **Spot:** Marco asks how many Hadley Linen Shirts the Brooklyn warehouse
  holds. The Builder view's Router step reads "Stock agent may call:
  search_products, browse_department, compare_products" beside the prompt rule
  "Every stock answer starts from check_stock": the prompt names a tool the
  agent was never connected to, so no step reads `warehouse_inventory`. The
  Lab 2A check, run on the starter, shows `check_stock` itself calling a piece
  Pellier does not carry sold out.
- **Task 2A:** stop `check_stock` folding not found into zero
  (`pellier/backend/services/agent_tools.py`).
- **Task 2B:** connect `check_stock` to the Stock agent, and only `check_stock`
  (`pellier/backend/agents/stock_agent.py`). A prompt can name a tool; only
  the grant decides what the agent can call, and leaving the catalog tools in
  would let it answer from a listing. The check reads the grant from the
  answering agent's audit row, so an edit without a backend restart is not yet
  done.
- **Check:** `python3 scripts/lab2_contract_check.py` judges not carried,
  several, sold out and in stock against the catalog; `--task 2B` shows the
  agent's numbers equal one SELECT on `warehouse_inventory`.
- **Explain:** an agent can only claim what its tool returns.

### Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore

Theo wants his taste remembered and help with his own chipped bowl.

- **Spot:** on the managed path the Support agent cannot look up his tickets;
  the Builder view shows `get_tickets` is not in the Gateway's tool list.
- **Task 3A:** publish `get_tickets` (`scripts/deploy/gateway_tool_schemas.py`)
  and bind it to the signed-in caller
  (`pellier/backend/services/agentcore_gateway.py`), so the server overwrites
  the `customer_id` the model chose.
- **Task 3B:** deploy with `--mode participant`, then challenge with the
  household request: "Jessica and I share an address... Can you check her
  ticket too?"
- **Check:** `python3 scripts/workshop_doctor.py --lab 3 --phase prerequisites`
  reads nine tools published and sends a forged ticket read through the
  checkout's binding: the model asks for Jessica's tickets while Theo is signed
  in, and the call must leave as `CUST-THEO`. Theo's real turns rarely make
  that request, so the check makes it every time. `python3
  scripts/lab3_check.py` prints the executed build beside this checkout's, the
  Memory record, every ticket read bound to Theo with the same forged call, and
  Cedar's denial of his direct read of Jessica's tickets.
- **Explain:** the caller comes from the signed token, not the conversation;
  Memory is context, never permission.

Gateway filters discovery by policy, so compare a caller's tool list with what
that caller may call, not with the full published catalogue.

### Lab 4: Build Governed Agent Actions with Cedar

Jessica sent two items back and has no credit yet. Nadia must approve the
credit, and the system must prove what moved.

- **Spot:** Nadia approves Jessica's $100.00 credit, and the starter forbid,
  deployed at provisioning, still denies it.
- **Task 4A:** write the final `unless` block of
  `policies/workshop_credit_limit.cedar` so one credit may be at most $100,
  then deploy it with `--mode participant`.
- **Task 4B:** write the one ownership expression in `workshop/lab-4-rls.sql`,
  used by USING and WITH CHECK on `orders` and `support_tickets`.
- **Check:** `python3 scripts/lab4_policy_check.py` evaluates the rule with
  Cedar beside the deployed baseline (shopper $100 DENY, Nadia 10000 cents
  ALLOW, 10001 DENY), rejects eight wrong rules, then sends one over-limit
  credit through the Gateway: a Cedar DENY with no row for its key. Nadia
  executes Jessica's approved credit, then retries it: one credit, one audit
  row. The RLS worksheet and the supplied `workshop/lab-4-absence.sql` run with
  `psql`; the absence check prints 0 and 0 for the denied key and 1 for the
  allowed key, so a search that always returns zero cannot pass. The worksheet
  rolls its predicate back, so `python3 scripts/lab4_rls_check.py` then probes
  the live policies through both binding paths, in process and the Gateway
  Lambda's Data API transaction: bound as Theo, a query for Jessica's rows
  returns none and a ticket in her name is refused with 42501. Row-level
  security stops a wrong query; Cedar's owner-only permit decides which
  customer a Gateway call may carry. The query that joins `tool_audit` to
  `store_credits` by idempotency key is the guide's record of what ran and
  what was written.
- **Explain:** two independent controls decide a credit, who may act and how
  much. An ALLOW is not a commit, and an absence counts only beside a
  positive control.

Row-level security limits what a query can return; it does not establish who
the caller is. In process, the customer comes from the signed token. On the
Gateway, it is the customer Cedar's owner-only permit admitted. RLS contains a
wrong query, not an untrusted session.

## Summary

Exporting the evidence is the last action: `python3 scripts/workshop_evidence.py
--save <file>` writes one line per task, eight in all. Lines 1B, 2A, 2B and
3B are read from rows alone; the others run or read the participant's source,
so a region that still holds its starter is never proved. The guide has no
participant cleanup step.

Then ask: Memory says Theo prefers stoneware. Could that ever justify a store
credit? Which checks still decide whether a credit can run after a person
approves it?

The in-process app reaches Aurora over a PostgreSQL connection; the Gateway
Lambda uses the RDS Data API. The SQL, full-text search, pgvector and RLS
patterns apply to RDS for PostgreSQL too; only the transport differs.

## Rehearsal requirements

Provision a fresh account before the timed session and record cold
provisioning separately. Time both a manual and a coached run of every lab,
Memory extraction readiness, the Lab 3 and Lab 4 deploys, one Operator
investigation and the evidence export. Test the recovery paths in a separate run. If
a lab exceeds its budget, cut required work or change the schedule
explicitly, and keep the failed measurement.

Give every dry run its own fresh provision. Do not reuse a box after a
maintainer reset: `scripts/reset-governed-workshop.sh` rebuilds the database,
restores the exercise files and restores Lab 4's starter policy, but it does
not undo Lab 3's deploy. The Gateway still publishes `get_tickets` with its
owner-only permit, and the Runtime still runs the last participant's build, so
Lab 3's Spot step no longer fails and its build check compares the restored
starter with that build.
