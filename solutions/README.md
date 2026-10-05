# Governed Workshop Reference Implementations

These files are facilitator recovery paths and readable reference implementations. A participant who uses a reference still runs the same live proof.

## Lab 1: Build and Measure PostgreSQL Hybrid Retrieval

Task 1A's recovery restores the worksheet with the fusion expression written:

```bash
cp solutions/the-quiet-search/sql/lab-1-rrf-solution.sql workshop/lab-1-rrf.sql
```

Task 1B's recovery restores `search_plan.py` with a fallback that keeps the
shopper's limits:

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

Task 2B's recovery grants the Stock agent `check_stock` alone:

```bash
cp solutions/waking-the-stock-keeper/agents/stock_agent_solution.py \
  pellier/backend/agents/stock_agent.py
```

Restart, ask Marco's questions again, then run
`python3 scripts/lab2_contract_check.py` and
`python3 scripts/lab2_contract_check.py --task 2B`.

## Lab 3: Deploy and Operate the Managed Agent Path

Lab 3 has two bounded builds. 3a publishes `get_ticket_history` on the Gateway
and keeps `issue_credit` deferred; 3b reconciles the tools the Runtime asks the
Gateway for and binds that read to the authenticated caller. Copying either
still requires a deploy, because the published catalogue and the Runtime
package are both control-plane state:

```bash
cp solutions/the-ledger/gateway/gateway_tool_schemas_solution.py \
  scripts/deploy/gateway_tool_schemas.py
cp solutions/the-ledger/services/agentcore_gateway.py \
  pellier/backend/services/agentcore_gateway.py

python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD"
```

After the deploy, `/api/observatory/build-state` must report steps `3a` and
`3b` as `shipped`, and the managed receipt's build fingerprint must match this
checkout. A copy without a deploy leaves the source ahead of the deployed
package, which is exactly the drift the fingerprint exists to catch.

The managed Memory, Runtime, Gateway, and JWT path has no local substitute. Move a participant to a ready environment when that proof fails.

The forensic SQL is deterministic:

```bash
psql -v ON_ERROR_STOP=1 \
  -f solutions/the-ledger/sql/forensic_incident.sql
```

## Lab 4: Govern and Prove Agent Actions

Lab 4a is the Cedar identity rule; Lab 4b is the keyed absence query. The
OpenTelemetry trace contract (`workshop/lab-3-otel-contract.jq`) runs at the end
of Lab 3 and is a provided check with no recovery copy. The absence query's
recovery copy reads the same tables the participant's would; it cannot
manufacture the rows it counts:

```bash
cp solutions/the-ledger/observability/lab-4-absence-solution.sql \
  workshop/lab-4-absence.sql
```

It joins `governed_receipts` to `tool_audit` and resolves the authenticated Marco principal against the Theo customer named in tool input.

Copy the identity-aware Cedar rule after one failed validation, then add it
through the same pinned AgentCore CLI used by the workshop:

```bash
REPO=/workshop/sample-pellier-agentic-search-apg
PROJECT="$REPO/.agentcore-project/pellier"
cp "$REPO/solutions/the-concierge/policies/identity_match_forbid.cedar" \
  "$REPO/policies/workshop_identity_match_forbid.cedar"

cd "$PROJECT"
npx -y @aws/agentcore@0.26.0 add policy \
  --name workshop_identity_match_forbid \
  --engine pellier_policy_engine \
  --source "$REPO/policies/workshop_identity_match_forbid.cedar" \
  --validation-mode FAIL_ON_ANY_FINDINGS \
  --enforcement-mode ACTIVE \
  --json
npx -y @aws/agentcore@0.26.0 validate --json
npx -y @aws/agentcore@0.26.0 deploy --yes --json
```

The participant must still prove Marco-for-Jessica DENY, prove Jessica-for-Jessica
ALLOW, inspect both receipts, and remove the participant policy through the CLI.

## Bootstrap Reference

The one-hour builders format pre-applies selected reference files. The governed
format restores every participant region to its starter with
`scripts/reset_participant_exercises.py`: the RRF worksheet and the search-plan
fallback for Lab 1, the `check_stock` body and the Stock agent definition for
Lab 2, the Gateway catalogue and the Runtime support contract for Lab 3, and the
RLS worksheet, absence query and Cedar rule for Lab 4.
`scripts/bootstrap-labs.sh` is the source of truth for that branch-specific
behavior.

The remaining files under `solutions/` mirror production services or provide test/recovery fixtures. They are not additional workshop labs.
