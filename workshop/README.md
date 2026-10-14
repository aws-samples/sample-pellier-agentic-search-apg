# Governed workshop: keep building after the session

For the participant entry point, open [START_HERE.md](../START_HERE.md) and [Pellier.code-workspace](../Pellier.code-workspace). The numbered `labs/` groups link to these same files.

Workshop Studio contains the instructions and recovery answers for the four labs.
This directory is the source map and portable notebook for the **governed** track.
The Builders event informed its pacing and exercises; `main` is a different track.

Every task runs the same way: it fails in the terminal, you fix the marked region,
one command proves the fix with one pass token, and then you look at it in the app.
Every check prints what was expected, what was observed, and the evidence behind
it. `python3 scripts/workshop_evidence.py` exports that proof for all four labs.
Tasks 1B, 2A and 2B are read from rows alone (`pellier.retrieval_receipts`,
`pellier.tool_audit`, the catalog and warehouse tables), so no code of yours
runs: Lab 2's lines pass only after the restart and Marco's requests sent again.
1A runs your vector branch, 3A reads the Gateway catalogue and binding in
source, 3B reads Theo's turns, his Memory record and your live row policies, 4A
evaluates your Cedar rule beside its stored Gateway denial and Jessica's credit,
and 4B reads your live credit function and probes the money role; a region that
still holds its starter is NOT YET there. The Wrap-up's cleanup restores the
Cedar starter, so save the export before it. A supplied answer, an open page,
or a successful conversation is not a completed task; a recovered task keeps
the same checks.

| Lab and task | Work you do | Check |
|---|---|---|
| 1A, Anna | Search by what she means (`services/store_tools.py`) | `python3 scripts/lab1_check.py --task 1A` |
| 1B, Anna | Keep her limits on the retry (`services/search_plan.py`) | `python3 scripts/lab1_check.py --task 1B` |
| 2A, Marco | Keep "not carried" distinct from sold out (`services/agent_tools.py`) | `python3 scripts/lab2_check.py --task 2A` |
| 2B, Marco | Connect `check_stock` to the Stock agent, alone (`agents/stock_agent.py`) | `python3 scripts/lab2_check.py --task 2B` |
| 3A, Theo | Publish `get_tickets` and bind it to the caller | `python3 scripts/lab3_check.py --task 3A` |
| 3B, Theo | Deploy, write the ownership rule (`workshop/lab-3-row-ownership.sql`), then challenge it | `python3 scripts/lab3_check.py --task 3B` |
| 4A, Jessica and Nadia | Cap the credit at $100 in Cedar (`policies/workshop_credit_limit.cedar`) | `python3 scripts/lab4_check.py --task 4A` |
| 4B, Jessica and Nadia | Let the money role write only through the function (`workshop/lab-4-credit-writer.sql`) | `python3 scripts/lab4_check.py --task 4B` |

The two worksheets run during their labs' deploys and print their own lines:
`psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-3-row-ownership.sql` ends
`Lab 3B predicate check passed` and
`psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-4-credit-writer.sql`
ends `Lab 4B privileges check passed`. Lab 4 closes with the supplied
`psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-4-absence.sql`.

Before Task 1A's edit, `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-meaning.sql` measures eight products against
a product's own stored embedding: that product sits at distance 0, and the rows come
in name order, so the ranking and its direction stay Task 1A's to write. The HNSW
index names its operator class. It only reads.

Optional in Lab 1: `psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-fusion.sql`
recomputes the fused scores Anna's search recorded from their two ranks, and
`psql -X -v ON_ERROR_STOP=1 -P pager=off -f workshop/lab-1-index.sql` shows whether
Aurora uses the HNSW index at this catalog's size, and what a filter does to the
index when it is used. Both only read.

Only edit the lab's marked regions; there are nine. Python edits in Labs 1 and
2 need the guide's backend restart. Lab 3's edits and Lab 4's rule reach AWS
only through `python3 scripts/provision_agentcore_end_to_end.py --repo-path
"$PWD" --mode participant`: changing a local file does not update AWS.
Provisioning deploys Lab 4's starter rule, so the deploy updates it.

## One assistant, four growing responsibilities

**Respect the requirements → know the facts → establish the caller → govern the action.**

Each customer introduces the next responsibility. Keep the code and evidence from
each chapter, while using a separate identity and conversation for each customer.
See [the task contract](../docs/WORKSHOP-STORY-ARC.md) for edit locations, rejected
implementations and evidence boundaries.

## Follow the request, then challenge the result

- **Anna:** in-process retrieval → SQL eligibility → lexical and vector ranks →
  RRF → rerank. A fallback may relax a preference, but it carries the budget,
  the stock rule and the exclusions into every attempt.
- **Marco:** his request → Router → Stock agent → `check_stock` → Aurora.
  Compare the tool's envelope with one SELECT on `warehouse_inventory`.
- **Theo:** verified identity → Runtime → Gateway and Cedar → the Lambda's
  read as `pellier_agent` under his row policy. The server binds the caller
  onto every customer-scoped call; Memory is context, not proof of a purchase.
- **Jessica and Nadia:** request → Investigator and Planner → Nadia's approval
  → Cedar on the Gateway → `apply_store_credit` as `pellier_credit_writer`.
  One approval is worth one credit; a retry under the same key returns the
  same credit.

## Revisit Lab 1 with the retrieval harness

For an advanced follow-up, author a new `GoldenQuery` in
`scripts/eval_retrieval_harness.py`: label products and exclusions before running,
include a paraphrase and a no-eligible-result case, then run the harness. It needs a
deployed environment and incurs service use. Candidate coverage, Recall@5, MRR@5,
and Hit@1 answer different questions. Unchanged and worse results are valid
observations, not reasons to relabel the products. SQL still establishes
eligibility.

## Keep a useful continuation checkpoint

Before the sandbox closes, save the evidence export with
`python3 scripts/workshop_evidence.py --save <file>` and download the file. It
names the last passing check, the first failed one, and what to look at next. Keep the public source link and save or print the Studio
guides if you need them offline. Do not archive `.env`, tokens, credential files,
or the generated deployment directory. Review evidence files for private values
before sharing them. Sandbox lifetime is set by the event; these files do not
extend it.

A 409 alone does not identify the cause. Save the route, response detail, and
exact receipt or operation ID privately. A starter-state warning needs the
bounded edit and reload; a managed-path warning needs deployment readiness; a
review conflict needs the stored review and operation state. Do not disable a
control or issue a fresh write key to make the error disappear.
