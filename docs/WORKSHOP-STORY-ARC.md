# Pellier: the four-lab workshop contract

Pellier is a retail store building an agentic system for product discovery and
customer support. Four customers each bring one leadership worry, and each lab
answers one: the participant sees the worry fail in the terminal, fixes the
marked region, proves the fix with one command, and only then looks at it in
the app.

**Respect the requirements → know the facts → establish the caller → govern the action.**

The source contract is `workshop/story-arc.json`. Workshop Studio owns the full
exercises. In `story-arc.json`, `title` is the lab name and `storyTitle` the
persona-led scenario; keep the technical titles as the headings.

| Lab | Customer | Worry |
|---|---|---|
| 1. Build and Measure PostgreSQL Hybrid Retrieval | Anna | "Shoppers describe what they want, and our search only matches words." |
| 2. Build a PostgreSQL-Grounded Agent | Marco | "If the assistant guesses stock, we'll promise things we can't ship." |
| 3. Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore | Theo | "The assistant should remember our customers, but never let one see another's account." |
| 4. Govern Agent Actions with Cedar Policies and PostgreSQL Privileges | Jessica and Nadia | "No AI moves money on its own, and when money moves, we must prove what happened." |

## Every task: fail in the terminal, fix the region, prove it, then look

See it fail is a command in the Code Editor terminal that prints the failure as
evidence: a worksheet, a check, or `python3 scripts/lab_run.py send`, which
sends the customer's exact sentence. Build is the edit in the named region.
Prove it is one command and one pass token. The Storefront's Builder view, the
Operator and the AgentCore console come after the token and show what the
terminal proved; nothing the proof depends on happens there. Lab 4's decisions
are the exception: Nadia's approval and the Operator's **Execute**, **Execute
again** and **Retry execution** happen in the Operator, and their proof comes
back to the terminal.

One starter-failure test per lab (`pellier/backend/tests/test_lab1_vector.py`,
`test_lab1_starter_failure.py` to `test_lab4_starter_failure.py`) asserts the
starter fails the way See it fail shows and the solution does not.

| Lab | See it fail, in the terminal | The fix |
|---|---|---|
| 1 | `workshop/lab-1-words.sql` shows what Anna's sentence finds by words alone, because the starter's vector branch ranks nothing by meaning; after her request is sent, `lab1_retry.py` shows the retry dropped her limits | 1A: rank the eligible products by meaning. 1B: the fallback keeps her limits |
| 2 | `lab2_check.py` shows `check_stock` calling a piece Pellier does not carry sold out; after Marco's requests, `--task 2B` shows the answering Stock agent held only catalog tools | 2A: `check_stock` keeps "not carried" apart from sold out. 2B: connect `check_stock` to the Stock agent, alone |
| 3 | `lab3_check.py --task 3A` shows `get_tickets` withheld from the Gateway; `workshop/lab-3-row-ownership.sql` shows the starter's `false` predicate hiding Theo's own rows | 3A: publish `get_tickets` and bind it to the caller. 3B: deploy, write the ownership rule, then challenge it |
| 4 | `lab4_policy.py` shows the starter forbid denying Nadia's approved credits; `workshop/lab-4-credit-writer.sql` shows the starter's grants letting the money role raise an approved credit directly | 4A: the $100 per-credit limit in Cedar. 4B: the money role writes only through the credit function |

## Nine marked regions, one check per task

Paths under `services/` and `agents/` are in `pellier/backend/`. A task's
check prints `Lab NB check passed`; a worksheet a task's Build runs prints
`Lab NB <thing> check passed`; a worksheet that belongs to no task carries no
task letter.

| Task | Region | Check | Pass token |
|---|---|---|---|
| 1A | `services/store_tools.py`, `Vector branch - order by meaning` | `python3 scripts/lab1_check.py --task 1A` | `Lab 1A check passed` |
| 1B | `services/search_plan.py`, `Search plan - preserve requirements` | `python3 scripts/lab1_check.py --task 1B` | `Lab 1B check passed` |
| 2A | `services/agent_tools.py`, `Stock agent - check_stock` | `python3 scripts/lab2_check.py --task 2A` | `Lab 2A check passed` |
| 2B | `agents/stock_agent.py`, `Stock agent - definition` | `python3 scripts/lab2_check.py --task 2B` | `Lab 2B check passed` |
| 3A | `scripts/deploy/gateway_tool_schemas.py`, `Gateway catalogue - published tools`; `services/agentcore_gateway.py`, `Support agent - Gateway tools` | `python3 scripts/lab3_check.py --task 3A`, which sends a forged ticket read for Jessica through the checkout's binding | `Lab 3A check passed` |
| 3B | `workshop/lab-3-row-ownership.sql`, `Row ownership - predicate` (its worksheet prints `Lab 3B predicate check passed`) | `python3 scripts/lab3_check.py --task 3B` | `Lab 3B check passed` |
| 4A | `policies/workshop_credit_limit.cedar`, the final `unless` block | `python3 scripts/lab4_check.py --task 4A` | `Lab 4A check passed` |
| 4B | `workshop/lab-4-credit-writer.sql`, `Credit writer - privileges` (its worksheet prints `Lab 4B privileges check passed`) | `python3 scripts/lab4_check.py --task 4B` | `Lab 4B check passed` |

Lab 1's Go deeper keeps the RRF worksheet (`workshop/lab-1-fusion.sql`, region
`PostgreSQL RRF - fusion expression`, `Lab 1 fusion check passed`); it is not a
task. Lab 4's "What you proved" runs the supplied `workshop/lab-4-absence.sql`
(`Lab 4 absence check passed`).

Every check prints three things: what was expected, what was observed, and the
evidence (the row, the decision, the key). A check that did not pass asks one
question that points at its region. `python3 scripts/workshop_evidence.py`
exports all eight lines: 1B, 2A and 2B from rows alone, the others by running
or reading the participant's source, where a region that still holds its
starter is never proved.

## Acceptance and rejected implementations

- **1A:** the vector branch orders the eligible rows by cosine distance to the
  query embedding, closest first, reports similarity as 1 minus that distance,
  and returns as many rows as the search asked for. A product searched with its
  own embedding comes back first; the Sunday Morning Candle, searched with its
  own embedding under Anna's limits, does not come back at all.
- **1B:** every fallback attempt keeps the budget, the stock rule and the
  exclusions; only a preference changes, and the receipt records it.
- **2A / 2B:** not carried, several and sold out stay three answers; the
  Stock agent's numbers equal one SELECT on `warehouse_inventory`. 2B is least
  privilege: the risk is what the agent can call. Its prompt, not its grant, is
  what keeps today's model on `check_stock`, so the grant is read from the
  answering agent's audit row, never from the source, and an edit without a
  restart is not yet done.
- **3A / 3B:** the Support agent asks only for published tools, and the server
  overwrites the model's `customer_id` on `get_tickets`. A model refusal is not
  a control. The deployed build is read from `tool_audit.build_fingerprint`
  beside this checkout's digest. Theo's own token, naming Jessica's customer
  directly at the Gateway, is denied by `get_tickets_owner_only`. Memory is
  context: Theo's provisioning conversation and the preference record
  extracted from it, never permission. One ownership expression serves USING
  and WITH CHECK on `orders` and `support_tickets`: Theo's own rows are
  visible, Jessica's return 0, a ticket written in her name fails with 42501,
  and every customer sees exactly their own rows; only then does the worksheet
  commit the predicate as the live policy, after undoing its probe writes.
  The live check reads the policy's stamp and probes both database paths.
- **4A:** the participant's rule is evaluated with the real Cedar engine
  (`cedarpy`) beside the rendered baseline: shopper $100 DENY (the baseline's
  doing, not the rule's), Nadia 1, 9999 and 10000 cents ALLOW, 10001 DENY, the
  same for a second staff member and other customers, three read tools still
  ALLOW and another customer's orders still DENY. The policy head must be
  unchanged and the file must hold one policy. The check rejects eight wrong
  rules (`false`, `true`, staff-only, `< 10000`, `<= 100`, one customer only,
  a lower bound, and the rule widened to every action) and shows that without
  the rule Nadia's 10001 cents is allowed. On the box it sends one over-limit
  credit of its own approved review through the Gateway: a Cedar DENY with no
  row for its key. A 401 or a business refusal is not Cedar evidence. Nadia's
  approval of Jessica's 10000-cent case executes once and a retry adds nothing.
- **4B:** `pellier_credit_writer` may execute `pellier.apply_store_credit`,
  which runs with its owner's rights and a pinned `search_path`, and nothing
  else. The worksheet's probes, on a probe case of its own, show the function
  refusing a credit no one approved and a direct insert or a direct `UPDATE` of
  an approved $25 credit to $500 refused with 42501; only then does it commit
  the privileges. The live check confirms the function carries the file's
  statements, then probes the role in process and through the Gateway Lambda's
  Data API. The absence check is supplied: 0 and 0 for the denied key, 1 for the
  allowed key, so a search that always returns zero cannot pass.

## Timing

The schedule is 15 minutes for the opening talk, 10 for the Introduction and
Getting started, then 15, 15, 25 and 25 minutes for Labs 1 to 4, and 5 for the
Wrap-up: 110 of the 120-minute slot, with recovery taking its five minutes from
the remaining ten. These are targets until a timed fresh-account rehearsal
confirms them. Lab 3's and Lab 4's deploy waits are inside their budgets, and
each of those labs runs its worksheet task during its wait.
