# Governed workshop: keep building after the session

For the participant entry point, open [Pellier.code-workspace](../Pellier.code-workspace). The numbered `labs/` groups link to these same files.

Workshop Studio holds the instructions and recovery answers for the four labs; this
directory is the source map for the **governed** track.

Every task runs the same way: it fails in the terminal, you fix the marked region, one check
proves the fix with one pass line, and then you look at it in the app. Every check prints what
it expected, what it observed and the evidence; `uv run scripts/workshop_evidence.py` exports
that proof for all four labs. The export reads 1B, 2A and 2B from recorded rows
(`pellier.retrieval_receipts`, `pellier.tool_audit`, the catalog and warehouse tables), so Lab 2's
lines pass only after Marco's requests are sent again on the finished lab. A supplied answer, an open page or a successful conversation
is not a completed task.

| Lab and task | Work you do | Check |
|---|---|---|
| 1A, Anna | Search by what she means (`services/store_tools.py`), applied with `scripts/lab_run.py solution --lab 1 --task 1A` | `uv run scripts/lab1_check.py --task 1A` |
| 1B, Anna | Keep her limits on the retry (`services/search_plan.py`) | `uv run scripts/lab1_check.py --task 1B` |
| 2A, Marco | Connect `check_stock` to the Stock agent, alone (`agents/stock_agent.py`), applied with `scripts/lab_run.py solution --lab 2 --task 2A` | `uv run scripts/lab2_check.py --task 2A` |
| 2B, Marco | Keep "not carried" distinct from sold out (`labs/02-ground/2B-check-stock.sql`) | `uv run scripts/lab2_check.py --task 2B` |
| 3A, Theo | Publish `get_tickets` and bind it to the caller, applied with `scripts/lab_run.py solution --lab 3 --task 3A` | `uv run scripts/lab3_check.py --task 3A` |
| 3B, Theo | Deploy, write the ownership rule (`labs/03-deploy/3B-row-ownership.sql`), then challenge it | `uv run scripts/lab3_check.py --task 3B` |
| 4A, Jessica and Nadia | Cap the credit at $100 in Cedar (`policies/workshop_credit_limit.cedar`), applied with `scripts/lab_run.py solution --lab 4 --task 4A` | `uv run scripts/lab4_check.py --task 4A` |
| 4B, Jessica and Nadia | Let the money role write only through the function (`labs/04-govern/4B-credit-writer.sql`) | `uv run scripts/lab4_check.py --task 4B` |

The two SQL files run during their labs' deploys and print their own lines:
`psql -f labs/03-deploy/3B-row-ownership.sql` ends
`Lab 3B predicate check passed` and
`psql -f labs/04-govern/4B-credit-writer.sql`
ends `Lab 4B privileges check passed`. Lab 4 closes with the supplied
`psql -f workshop/lab-4-absence.sql`.

Two more supplied SQL files read the agent from the database's side and change nothing.
After `Lab 3B check passed`, `psql -f workshop/lab-3-agent-workload.sql`
lists the statements each role ran, from `pg_stat_statements`, and one plan with the row
policy inside it; it ends `Lab 3 workload check passed`. At the Wrap-up,
`psql -f workshop/wrap-up-reconstruct.sql` rebuilds
Jessica's credit from her request to the row with joins, and ends
`Wrap-up reconstruction passed`.

In Task 1B, `psql -f workshop/lab-1-receipt.sql` prints Anna's latest search receipt as one
record: the limits she asked for, the limits the search kept, and the soft tags a retry
dropped. It only reads.

Optional, in Lab 1's Go deeper: `psql -f workshop/lab-1-words.sql` ranks her words with
full-text search; `psql -f workshop/lab-1-meaning.sql` measures eight products against one
product's own embedding, which sits at distance 0; `psql -f workshop/lab-1-fusion.sql`
recomputes the fused scores her search recorded; and `psql -f workshop/lab-1-index.sql`
compares exact and HNSW search, with and without the storefront filter. All four only read.

Only edit the lab's marked regions; there are nine. Python edits in Labs 1 and
2 need the guide's backend restart. Lab 3's edits and Lab 4's rule reach AWS
only through `uv run scripts/provision_agentcore_end_to_end.py --repo-path
"$PWD" --mode participant`: changing a local file does not update AWS.
Provisioning deploys Lab 4's starter rule, so the deploy updates it.

## One assistant, four growing responsibilities

**Respect the requirements → know the facts → establish the caller → govern the action.**

Each customer introduces the next responsibility. Keep the code and evidence from each lab,
with a separate identity and conversation for each customer.
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
- **Jessica and Nadia:** request → Investigator and Advisor → Nadia's approval
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
`uv run scripts/workshop_evidence.py --save <file>` and download the file. It
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
