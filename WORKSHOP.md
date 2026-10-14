# DAT416 speaker and facilitator brief

**Build governed agentic AI search with Aurora, RDS, & Bedrock AgentCore**

Level 400. 120 minutes. Four labs, eight hands-on tasks in nine marked regions.

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
| 3. Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore | Theo | "The assistant should remember our customers, but never let one see another's account." |
| 4. Govern Agent Actions with Cedar Policies and PostgreSQL Privileges | Jessica, with Nadia (staff) | "No AI moves money on its own, and when money moves, we must prove what happened." |

Every task runs the same way: it fails in the terminal, the participant fixes
the marked region, one command proves the fix, and then they look at it in the
app. Each check prints what was expected, what was observed and the evidence
(the row, the decision, the key), and ends with one pass token. Nothing a check
depends on happens in the app, except Lab 4's decisions: Nadia's approval and
the Operator's three buttons, whose proof comes back to the terminal.

## The session schedule

Times are elapsed minutes from the start of the session.

| Workshop minutes | Activity | Duration |
|---|---|---|
| 0-15 | Opening talk | 15 minutes |
| 15-25 | Introduction and Getting started | 10 minutes |
| 25-40 | Lab 1: Build and Measure PostgreSQL Hybrid Retrieval | 15 minutes |
| 40-55 | Lab 2: Build a PostgreSQL-Grounded Agent | 15 minutes |
| 55-80 | Lab 3: Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore | 25 minutes |
| 80-105 | Lab 4: Govern Agent Actions with Cedar Policies and PostgreSQL Privileges | 25 minutes |
| 105-110 | Wrap-up: export the evidence | 5 minutes |
| 110-120 | Unscheduled; recovery takes five of these minutes | 10 minutes |

Reading, deployment waits and checks share each lab's time. Lab 3's and
Lab 4's deploys are inside their budgets, and each of those labs runs its
worksheet task during the wait. An unrun check stays incomplete.

## What participants use

Code Editor opens `Pellier.code-workspace` and `START_HERE.md`. Its numbered Retrieve, Ground, Deploy and Govern groups point at `labs/01-retrieve` through `labs/04-govern`. Each contains links to the exercise files, a short check map and a solution README, such as `labs/01-retrieve/solution/README.md`. Two of the files are worksheets that deploy themselves: `labs/03-deploy/3B-row-ownership.sql` commits the participant's predicate as the live policy, and `labs/04-govern/4B-credit-writer.sql` commits the money role's privileges, each only when every probe matches. `labs/01-retrieve/go-deeper-fusion.sql` is Lab 1's optional worksheet; it recomputes recorded scores and changes nothing the app runs, and `scripts/lab_run.py solution` leaves it alone. The fifth group exposes the complete source; terminals start at the repository root. Source extraction validates every link before the editor starts and preserves participant edits on reruns.

To see where a stuck participant's files depart from the answer without overwriting them, run `python3 scripts/lab_run.py diff --lab N` from the repository root. '-' lines are the finished version that `scripts/lab_run.py` would write with `solution`; '+' lines are the participant's file as it is now. The guide does not show this command.

| Surface | Use | What it proves |
|---|---|---|
| Storefront (`/`) | Ask Pellier, the docked chat panel, where participants look at the turns `scripts/lab_run.py send` made for Anna, Marco and Theo. Choosing a shopper signs in with that shopper's demo account; Pellier trusts the signed token, not the choice. | The Builder view shows each turn's Router step, the tools the agent called and "How it ranked", after the check's token. It shows evidence; it does not replace the checks. |
| Operator (`/operator`) | Nadia, a staff account, investigates Jessica's case and approves or rejects the proposed credit. | A person's decision, recorded on the review before any credit is written. |
| Code Editor | The eight tasks, every See it fail and every check. | Source, SQL results, service responses and the evidence export. |

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
  grant has the catalog tools and not `check_stock`, until Lab 2B connects
  `check_stock` alone.
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
conversation, and AgentCore Memory extracts his preference from it. In Lab 3,
`scripts/lab3_check.py` reads that record the way the managed rail does and
prints its id; afterwards the Builder view of Theo's new-session turn names the
same record (`Remembered: AgentCore Memory record <id> (user preference)`). A
participant's own stated preference takes about two to two and a half minutes
to become readable, so it is a Go deeper tab, not the proof.

## The four labs

### Lab 1: Build and Measure PostgreSQL Hybrid Retrieval

Anna wants a housewarming gift under $100, in stock, with no candles.

- **See it fail:** `workshop/lab-1-words.sql` shows what her sentence finds by
  words alone, because the starter's vector branch ranks nothing by meaning.
- **Task 1A:** first run the supplied `workshop/lab-1-meaning.sql`, which ranks
  the catalog by meaning with the Stoneware Mugs' own embedding, the way the
  check does. Then rank the eligible products by meaning in the `Vector branch -
  order by meaning` region of `pellier/backend/services/store_tools.py`: order
  by cosine distance to the query embedding and report similarity as 1 minus
  it. `python3 scripts/lab1_check.py --task 1A` ends `Lab 1A check passed`.
- **Task 1B:** after `python3 scripts/lab_run.py send --lab 1`,
  `python3 scripts/lab1_check.py --task 1B` shows the retry dropped her limits. Keep
  them in `pellier/backend/services/search_plan.py`: a retry may relax a
  preference, never the budget, the stock rule or the exclusions. The check
  ends `Lab 1B check passed`.
- **Lesson:** similarity decides the order; SQL decides what is eligible.
- **Managed path:** the Gateway's store tools Lambda is packaged at
  provisioning from the finished copies of
  `pellier/backend/services/store_tools.py` and
  `pellier/backend/services/search_plan.py`, and the Lab 3 and Lab 4
  participant deploys reuse it. The
  Gateway's search therefore runs the finished 1A and 1B whatever the
  participant's files hold; Lab 1's tasks change the in-process search.

### Lab 2: Build a PostgreSQL-Grounded Agent

Marco needs reliable stock and dispatch facts before his trip.

- **See it fail:** `python3 scripts/lab2_check.py --task 2A` shows
  `check_stock` calling a piece Pellier does not carry sold out. After
  `python3 scripts/lab_run.py send --lab 2`, `--task 2B` shows the Stock agent
  that answered held only the catalog tools, so no step read
  `warehouse_inventory`.
- **Task 2A:** stop `check_stock` folding not found into zero
  (`pellier/backend/services/agent_tools.py`); the check ends `Lab 2A check
  passed`.
- **Task 2B:** connect `check_stock` to the Stock agent, and only `check_stock`
  (`pellier/backend/agents/stock_agent.py`). A prompt can name a tool; only
  the grant decides what the agent can call. The check reads the grant from the
  answering agent's audit row, so an edit without a backend restart is not yet
  done; it ends `Lab 2B check passed`.
- **Lesson:** an agent can only claim what its tool returns.

### Lab 3: Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore

Theo wants his taste remembered and help with his own chipped bowl.

- **See it fail:** after `bash scripts/lab3-start.sh theo`,
  `python3 scripts/lab3_check.py --task 3A` prints one line per rule before any
  deploy: `get_tickets` is withheld from the Gateway, and the starter Support
  agent, which answers returns questions with `get_return_policy` and hands off
  with `ask_a_person`, lacks the reads Theo's household request needs.
- **Task 3A:** assemble the Support agent. Publish `get_tickets`
  (`scripts/deploy/gateway_tool_schemas.py`); in
  `pellier/backend/services/agentcore_gateway.py`, add the reads his request
  needs to `SUPPORT_GATEWAY_TOOLS` and bind every tool that takes a
  `customer_id` in `SUPPORT_CALLER_BOUND_TOOLS`, so the server overwrites the
  `customer_id` the model chose. The check's four rules: `get_tickets`
  published; `get_orders` and `get_tickets` asked for; both bound, by a forged
  read for Jessica that must leave as `CUST-THEO`; and `give_store_credit`
  refused on a shopper agent (published is not permitted). It ends
  `Lab 3A check passed`.
- **Task 3B:** deploy with `--mode participant`. During the deploy, write the
  row-ownership predicate in `workshop/lab-3-row-ownership.sql`; its worksheet commits
  the predicate as the live policy once every probe matches and ends `Lab 3B
  predicate check passed`. Then `python3 scripts/lab_run.py send --lab 3` sends
  Theo's three sentences, including the household request ("Jessica and I
  share an address... Can you check her ticket too?"), and
  `python3 scripts/lab3_check.py --task 3B` prints the executed build beside this
  checkout's, the Memory record, every ticket read bound to Theo, Cedar's
  denial of his direct read of Jessica's tickets, and his row policies holding
  on both database paths. It ends `Lab 3B check passed`.
- **Lesson:** the caller comes from the signed token, not the conversation;
  Memory is context, never permission.

Gateway filters discovery by policy, so compare a caller's tool list with what
that caller may call, not with the full published catalogue.

Row-level security limits what a query can return; it does not establish who
the caller is. In process, the customer comes from the signed token. On the
Gateway, it is the customer Cedar's owner-only permit admitted. RLS contains a
wrong query, not an untrusted session.

### Lab 4: Govern Agent Actions with Cedar Policies and PostgreSQL Privileges

Jessica sent two items back and has no credit yet. Nadia must approve the
credit, and the system must prove what moved.

- **See it fail:** `python3 scripts/lab4_check.py --task 4A` shows the starter
  forbid denying Nadia's approved credits. `python3 scripts/lab_run.py send
  --lab 4 --shopper-only` sends Jessica's request; in the Operator, Nadia
  approves her $100.00 credit and **Execute** reads DENY.
- **Task 4A:** write the final `unless` block of
  `policies/workshop_credit_limit.cedar` so one credit may be at most $100,
  then deploy it with `--mode participant`.
- **Task 4B:** during the deploy, write the money role's privileges in
  `workshop/lab-4-credit-writer.sql`. The starter over-grants: its probes show
  `pellier_credit_writer` raising an approved $25 credit to $500 with a direct
  `UPDATE`. The worksheet commits the privileges once all eight probes match
  and ends `Lab 4B privileges check passed`.
- **The decision:** Nadia selects **Execute again** (ALLOW, recorded once),
  then **Retry execution** (nothing written twice).
- **Proof, back in the terminal:** `python3 scripts/lab4_check.py --task 4A`
  evaluates the rule with Cedar beside the deployed baseline (shopper $100 DENY,
  Nadia 10000 cents ALLOW, 10001 DENY), rejects eight wrong rules, then sends
  one over-limit credit through the Gateway: a Cedar DENY with no row for its
  key, ending `Lab 4A check passed`. `python3 scripts/lab4_check.py --task 4B`
  confirms the live function carries the participant's statements, then probes
  the money role in process and through the Gateway Lambda's Data API: the
  function refuses a credit no one approved and a direct insert or update is
  refused with 42501, ending `Lab 4B check passed`. The supplied
  `workshop/lab-4-absence.sql` prints 0 and 0 for the denied key and 1 for the
  allowed key, so a search that always returns zero cannot pass.
- **Lesson:** Cedar decides who may move money and how much; the database
  decides what the money role can touch. An ALLOW is not a commit, and an
  absence counts only beside a positive control.

## Summary

Exporting the evidence is the last action: `python3 scripts/workshop_evidence.py
--save <file>` writes one line per task, eight in all. Lines 1B, 2A and 2B
are read from rows alone; the others run or read the participant's source, so a
region that still holds its starter is never proved. The guide has no
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
Lab 3's See it fail no longer fails and its build check compares the restored
starter with that build.
