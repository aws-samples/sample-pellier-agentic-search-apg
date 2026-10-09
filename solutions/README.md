# Governed Workshop Reference Implementations

These files are facilitator recovery paths and readable reference implementations. A participant who uses a reference still runs the same live proof.

The commands below recover one task. To recover a whole lab, `python3 scripts/lab_run.py solution --lab N` copies both of its answers, and after the restart or deployment `python3 scripts/lab_run.py send --lab N` makes that lab's requests. Each guide's "Short on time?" block chains them with the lab's checks.

## Lab 1: Build and Measure PostgreSQL Hybrid Retrieval

Task 1A's recovery restores the worksheet with the fusion expression written:

```bash
cp solutions/the-quiet-search/sql/lab-1-rrf-solution.sql workshop/lab-1-rrf.sql
```

Task 1B's recovery restores `pellier/backend/services/search_plan.py` with a
fallback that keeps the shopper's limits:

```bash
cp solutions/the-quiet-search/retrieval/search_plan_solution.py \
  pellier/backend/services/search_plan.py
```

Restart the backend after the second copy. The checks are unchanged:
`psql -X -P pager=off -f workshop/lab-1-rrf.sql` reads Anna's latest search
receipt, and `python3 scripts/lab1_compare.py` reads the same search's products.
Neither copy writes a receipt; Anna's request in Ask Pellier does.

## Lab 2: Build a PostgreSQL-Grounded Agent

Task 2A's recovery restores a `check_stock` that passes the shared answer on
unchanged, so not_found stays not_found:

```bash
cp solutions/closing-marcos-gap/services/agent_tools_check_stock_solution.py \
  pellier/backend/services/agent_tools.py
```

Task 2B's recovery connects `check_stock` to the Stock agent, alone:

```bash
cp solutions/waking-the-stock-keeper/agents/stock_agent_solution.py \
  pellier/backend/agents/stock_agent.py
```

Restart, ask Marco's questions again, then run
`python3 scripts/lab2_contract_check.py` and
`python3 scripts/lab2_contract_check.py --task 2B`.

## Lab 3: Deploy Agents and Bind the Caller with Amazon Bedrock AgentCore

Task 3A's recovery publishes `get_tickets` and binds it to the signed-in
caller. A copy changes nothing in AWS until it is deployed, because the
published catalogue and the Runtime package are both control-plane state:

```bash
cp solutions/the-ledger/gateway/gateway_tool_schemas_solution.py \
  scripts/deploy/gateway_tool_schemas.py
cp solutions/the-ledger/services/agentcore_gateway.py \
  pellier/backend/services/agentcore_gateway.py
python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
```

The checks are unchanged: `python3 scripts/workshop_doctor.py --lab 3 --phase
prerequisites` reads "9 tools published, get_tickets bound to the signed-in
caller", and after Theo's turns `python3 scripts/lab3_check.py` compares the
executed build with this checkout's and asks Cedar to refuse his direct read of
Jessica's tickets. The managed Memory, Runtime, Gateway and JWT path has no
local substitute; move a participant to a ready environment when it fails.

`solutions/the-ledger/sql/forensic_incident.sql` reconstructs Jessica's
credit after Lab 4: who asked, who investigated, who approved, what the
Gateway answered, and what was paid. It only reads:

```bash
psql -X -P pager=off -f solutions/the-ledger/sql/forensic_incident.sql
```

## Lab 4: Govern Agent Actions with Cedar and PostgreSQL Row-Level Security

Task 4A's recovery is the $100 per-credit limit. Provisioning deployed the
starter as the policy `workshop_credit_limit`, so the deploy updates it:

```bash
cp solutions/the-concierge/policies/workshop_credit_limit.cedar \
  policies/workshop_credit_limit.cedar
python3 scripts/lab4_policy_check.py
python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD" --mode participant
python3 scripts/lab4_policy_check.py
```

The first check evaluates the rule with Cedar here; the second, after the
deploy, also sends one over-limit credit of its own through the Gateway.

Task 4B's recovery is the ownership predicate:

```bash
cp solutions/the-concierge/sql/lab-4-rls-solution.sql workshop/lab-4-rls.sql
psql -X -P pager=off -f workshop/lab-4-rls.sql
```

The keyed absence check, `workshop/lab-4-absence.sql`, is supplied and has no
recovery copy: it reads the over-limit review and Jessica's credit itself. The
reset (`scripts/reset-governed-workshop.sh`) restores the starter rule on the
deployed engine, so the next participant opens Lab 4 with the live DENY.

## Bootstrap Reference

The one-hour builders format pre-applies selected reference files. The governed
format restores every participant region to its starter with
`scripts/reset_participant_exercises.py`: the RRF worksheet and the search-plan
fallback for Lab 1, the `check_stock` body and the Stock agent definition for
Lab 2, the Gateway catalogue and the Runtime support contract for Lab 3, and the
RLS worksheet and Cedar rule for Lab 4: eight regions.
`scripts/bootstrap-labs.sh` is the source of truth for that branch-specific
behavior.

The remaining files under `solutions/` mirror production services or provide test/recovery fixtures. They are not additional workshop labs.
