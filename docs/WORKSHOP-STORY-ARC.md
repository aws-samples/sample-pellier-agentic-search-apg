# Pellier: the four-lab workshop contract

Pellier is a retail store building an agentic system for product discovery and
customer support. Four customers each bring one leadership worry, and each lab
answers one: it opens with the worry happening live, the participant fixes it,
and a check proves the fix from the system of record.

**Respect the requirements → know the facts → establish the caller → govern the action.**

The source contract is `workshop/story-arc.json`. Workshop Studio owns the full
exercises. In `story-arc.json`, `title` is the lab name and `storyTitle` the
persona-led scenario; keep the technical titles as the headings.

| Lab | Customer | Worry |
|---|---|---|
| 1. Build and Measure PostgreSQL Hybrid Retrieval | Anna | "Shoppers describe what they want, and our search only matches words." |
| 2. Build a PostgreSQL-Grounded Agent | Marco | "If the assistant guesses stock, we'll promise things we can't ship." |
| 3. Deploy and Operate Agents with Amazon Bedrock AgentCore | Theo | "The assistant should remember our customers, but never let one see another's account." |
| 4. Build Governed Agent Actions with Cedar | Jessica and Nadia | "No AI moves money on its own, and when money moves, we must prove what happened." |

## Every lab: spot the failure, then fix and prove it

Each starter produces a visible, explainable failure in Ask Pellier or the
Operator, never an exception or a missing feature. One starter-failure test
per lab (`pellier/backend/tests/test_lab1_starter_failure.py` to
`test_lab4_starter_failure.py`) asserts the starter shows exactly that failure
and the solution does not.

| Lab | The live failure | The fix |
|---|---|---|
| 1 | Anna asks for a gift in stock, under $100, with no candles; her search, forced onto its fallback, returns a candle and a sold-out piece | 1A: the RRF expression. 1B: the fallback keeps her limits |
| 2 | Marco asks about a piece Pellier does not carry and hears it is sold out; the Builder view shows the Stock agent may call the catalog tools beside `check_stock` | 2A: `check_stock` keeps not carried apart from zero. 2B: the Stock agent holds `check_stock` alone |
| 3 | On the managed path the Support agent can't look up Theo's tickets; the Builder view names `get_tickets` as not published | 3A: publish `get_tickets` and bind it to the caller. 3B: deploy, then challenge |
| 4 | Nadia approves Jessica's $100.00 credit and the starter forbid, deployed at provisioning, still denies it | 4A: the $100 per-credit limit in Cedar. 4B: the RLS ownership predicate |

## Eight marked regions, one check per task

Paths under `services/` and `agents/` are in `pellier/backend/`.

| Task | Region | Check |
|---|---|---|
| 1A | `workshop/lab-1-rrf.sql`, `PostgreSQL RRF - fusion expression` | `psql -X -P pager=off -f workshop/lab-1-rrf.sql` |
| 1B | `services/search_plan.py`, `Search plan - preserve requirements` | `python3 scripts/lab1_compare.py` |
| 2A | `services/agent_tools.py`, `Stock agent - check_stock` | `python3 scripts/lab2_contract_check.py` |
| 2B | `agents/stock_agent.py`, `Stock agent - definition` | `python3 scripts/lab2_contract_check.py --task 2B` |
| 3A | `scripts/deploy/gateway_tool_schemas.py`, `Gateway catalogue - published tools`; `services/agentcore_gateway.py`, `Managed catalogue - support reconcile` | `python3 scripts/workshop_doctor.py --lab 3 --phase prerequisites` |
| 3B | none: deploy with `--mode participant` | the Builder view's `Remembered: AgentCore Memory record <id>` line, then `python3 scripts/lab3_check.py` |
| 4A | `policies/workshop_credit_limit.cedar`, the final `unless` block | `python3 scripts/lab4_policy_check.py` |
| 4B | `workshop/lab-4-rls.sql`, `Row ownership - predicate` | `psql -X -P pager=off -f workshop/lab-4-rls.sql`, then the supplied `workshop/lab-4-absence.sql` |

Every check prints three things: what was expected, what was observed, and the
evidence (the row, the decision, the key). A check that did not pass says what
to look at next. `python3 scripts/workshop_evidence.py` exports all eight
lines: 1B, 2A, 2B and 3B from rows alone, the others by running or reading the
participant's source, where a region that still holds its starter is never
proved.

## Acceptance and rejected implementations

- **1A:** a missing rank contributes zero, never rank zero.
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
  extracted from it, never permission.
- **4A:** the participant's rule is evaluated with the real Cedar engine
  (`cedarpy`) beside the rendered baseline: shopper $100 DENY (the baseline's
  doing, not the rule's), Nadia 1, 9999 and 10000 cents ALLOW, 10001 DENY, the
  same for a second staff member and other customers, three read tools still
  ALLOW and another customer's orders still DENY. The policy head must be
  unchanged and the file must hold one policy. The check rejects eight wrong
  rules (`false`, `true`, staff-only, `< 10000`, `<= 100`, one customer only,
  a lower bound, and the rule widened to every action) and shows that without
  the rule Nadia's 10001 cents is allowed.
  On the box it sends one over-limit credit of its own approved review through
  the Gateway: a Cedar DENY with no row for its key. A 401 or a business
  refusal is not Cedar evidence. Nadia's approval of Jessica's 10000-cent case
  executes once and a retry adds nothing.
- **4B:** one expression serves USING and WITH CHECK on `orders` and
  `support_tickets`. Theo's own rows are visible, Jessica's return 0, a ticket
  written in her name fails with 42501, the Investigator still reads her case,
  and everything rolls back. In process the customer comes from the token; on
  the Gateway it is the customer Cedar admitted. RLS contains a wrong query.
  The absence check is supplied: 0 and 0 for the denied key, 1 for the allowed
  key, so a search that always returns zero cannot pass.

## Timing

The event budgets 15 minutes for the presenter introduction, then 15, 15, 20
and 25 minutes for Labs 1 to 4, five for recovery and five for closing. These
are targets until a timed fresh-account rehearsal confirms them. Lab 3's and
Lab 4's deploy waits are inside their budgets.
