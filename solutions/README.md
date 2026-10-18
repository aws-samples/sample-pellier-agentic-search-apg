# Governed Workshop Reference Implementations

These files are facilitator recovery paths and readable reference implementations. A participant who uses a reference still runs the same live proof.

The commands below recover one task. To recover a whole lab, `uv run scripts/lab_run.py solution --lab N` copies its tasks' answers, and after the restart or deployment `uv run scripts/lab_run.py send --lab N` makes that lab's requests. Each guide's "Running behind?" block chains them with the lab's SQL files and checks.

## Lab 1: Build and Measure PostgreSQL Hybrid Retrieval

Task 1A's recovery restores `pellier/backend/services/store_tools.py` with a
vector branch that ranks the eligible products by meaning:

```bash
cp solutions/the-quiet-search/retrieval/store_tools_solution.py \
  pellier/backend/services/store_tools.py
```

Task 1B's recovery restores `pellier/backend/services/search_plan.py` with a
fallback that keeps the shopper's limits:

```bash
cp solutions/the-quiet-search/retrieval/search_plan_solution.py \
  pellier/backend/services/search_plan.py
```

Restart the backend after the copies. The checks are unchanged:
`uv run scripts/lab1_check.py --task 1A` runs the vector branch, and after
`uv run scripts/lab_run.py send --lab 1` writes a receipt,
`uv run scripts/lab1_check.py --task 1B` reads that search's products.

The optional Go deeper Build's answer is
`solutions/the-quiet-search/sql/lab-1-fusion-solution.sql`; `scripts/lab_run.py solution`
leaves `workshop/lab-1-fusion.sql` alone.

## Lab 2: Build a PostgreSQL-Grounded Agent

Task 2A's recovery connects `check_stock` to the Stock agent, alone:

```bash
cp solutions/waking-the-stock-keeper/agents/stock_agent_solution.py \
  pellier/backend/agents/stock_agent.py
```

Task 2B's recovery restores a SQL file whose `pellier.check_stock` tests for
the product before it aggregates, so a piece Pellier does not carry returns no
row. Run it to commit the function:

```bash
cp solutions/closing-marcos-gap/sql/lab-2-check-stock-solution.sql \
  workshop/lab-2-check-stock.sql
psql -f workshop/lab-2-check-stock.sql
```

Restart, send Marco's requests again with
`uv run scripts/lab_run.py send --lab 2`, then run
`uv run scripts/lab2_check.py --task 2A` and
`uv run scripts/lab2_check.py --task 2B`.

## Lab 3: Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore

Task 3A's recovery publishes `get_tickets` and binds it to the signed-in
caller. A copy changes nothing in AWS until it is deployed, because the
published catalogue and the Runtime package are both control-plane state:

```bash
cp solutions/the-ledger/gateway/gateway_tool_schemas_solution.py \
  scripts/deploy/gateway_tool_schemas.py
cp solutions/the-ledger/services/agentcore_gateway.py \
  pellier/backend/services/agentcore_gateway.py
uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
```

Task 3B's recovery is the ownership predicate:

```bash
cp solutions/the-ledger/sql/lab-3-row-ownership-solution.sql workshop/lab-3-row-ownership.sql
psql -f workshop/lab-3-row-ownership.sql
```

The checks are unchanged: `uv run scripts/lab3_check.py --task 3A` reads
"9 tools published" and the forged call bound to Theo, and after
`uv run scripts/lab_run.py send --lab 3`, `uv run scripts/lab3_check.py --task 3B`
compares the executed build with this checkout's, asks Cedar to refuse his
direct read of Jessica's tickets, and probes the live row policies. The managed
Memory, Runtime, Gateway and JWT path has no local substitute; move a
participant to a ready environment when it fails.

`solutions/the-ledger/sql/forensic_incident.sql` reconstructs Jessica's
credit after Lab 4: who asked, who investigated, who approved, what the
Gateway answered, and what was paid. It only reads:

```bash
psql -f solutions/the-ledger/sql/forensic_incident.sql
```

## Lab 4: Govern Agent Actions with Cedar Policies and PostgreSQL Privileges

Task 4A's recovery is the $100 per-credit limit. Provisioning deployed the
starter as the policy `workshop_credit_limit`, so the deploy updates it:

```bash
cp solutions/the-concierge/policies/workshop_credit_limit.cedar \
  policies/workshop_credit_limit.cedar
uv run scripts/lab4_check.py --task 4A
uv run scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
uv run scripts/lab4_check.py --task 4A
```

The first check evaluates the rule with Cedar here; the second, after the
deploy, also sends one over-limit credit of its own through the Gateway.

Task 4B's recovery is the credit writer's privileges, committed once every
probe matches; the check then reads the live function and probes both paths:

```bash
cp solutions/the-concierge/sql/lab-4-credit-writer-solution.sql \
  workshop/lab-4-credit-writer.sql
psql -f workshop/lab-4-credit-writer.sql
uv run scripts/lab4_check.py --task 4B
```

The keyed absence check, `workshop/lab-4-absence.sql`, is supplied and has no
recovery copy: it reads the over-limit review and Jessica's credit itself. The
reset (`scripts/reset-governed-workshop.sh`) restores the starter rule on the
deployed engine, so the next participant opens Lab 4 with the live DENY.

## Bootstrap Reference

The one-hour builders format pre-applies selected reference files. The governed
format restores every participant region to its starter with
`scripts/reset_participant_exercises.py`: the vector branch and the search-plan
fallback for Lab 1 (and its optional RRF fusion file), the `check_stock` body and
the Stock agent definition for Lab 2, the Gateway catalogue, the Runtime support
contract and the RLS SQL file for Lab 3, and the Cedar rule and the credit
writer SQL file for Lab 4: nine regions and ten starters. Its `--check` holds
every live region to its starter, and a test requires an entry for every file
under `workshop/starters/`.
`scripts/bootstrap-labs.sh` is the source of truth for that branch-specific
behavior.

The remaining files under `solutions/` mirror production services or provide test/recovery fixtures. They are not additional workshop labs.
