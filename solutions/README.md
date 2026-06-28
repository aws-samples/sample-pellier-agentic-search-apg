# Solutions — drop-in replacements

Copy a solution file over its runtime counterpart and the backend
auto-restarts. These are the reference implementations and "⏩ out of
time" escape hatches for the 60-min Builder's Session.

```
solutions/
├── the-quiet-search/   → semantic search reference (observe-only)
├── closing-marcos-gap/ → floor_check + Stock Keeper (Exercise 1)
└── the-ledger/         → AgentCore production + audit ledger (Exercise 2)
```

---

## Builder's Session — 60 min

**One mandatory code build, one mandatory SQL proof, two optional
fast-finishers.** The cp commands below are the "⏩ out of time" escape
hatches referenced from each lab page.

### Exercise 1 (mandatory) — `floor_check` body (Act I)

Replaces the stubbed `floor_check` tool body with the working
implementation that calls `BusinessLogic.floor_check()` against
`pellier.warehouse_inventory`.

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only option (just the 9-line body, between `START` / `END`
markers): `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

### Exercise 2 (mandatory) — author three queries against `pellier.tool_audit` (Act II)

Generate a tool call, then **author** three queries that interrogate the
Aurora ledger, building in difficulty: the raw row (`SELECT`), JSONB
extraction (`->>` pulls `reason`/`return_id` out as columns), and
rail-boundary reasoning (`COUNT` by caller and reason → explain where a
Gateway-denied call would stop before a row exists). This is SQL the
participant writes, not a code drop — there is no file to copy over a
runtime counterpart. The required path is in-process (`caller='agent'`);
no-row behavior is a Gateway-rail/Cedar property. The "⏩ stuck on the SQL"
escape hatch is a canned recap query a facilitator can run live:

```bash
psql -f solutions/the-ledger/sql/tool_audit_recap.sql
```

Bare `psql` picks up the `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` /
`PGDATABASE` variables bootstrap already exports, so no connection string
is needed. It prints the most recent allowed `process_return` session, the
raw rows, and a JSONB-extracted view; pass an optional customer override
with `-v customer=<customer_id>` (e.g. `-v customer=theo`).

### Optional fast-finisher A — Anna skill edit (Act I)

The fast-finisher on the *Prove rerank* page asks attendees to change
one guidance line in `skills/the-gift-table/SKILL.md` and prove the
edit landed with SQL against `pellier.tool_audit`. **There is no
solution file** — the change is a single rule in the skill markdown,
and the proof is a `SELECT`, not a code drop.

### Optional fast-finisher B — `logger.info` observability hook (Act II)

Adds one `logger.info("agentcore.invoke ...")` line to
`run_agent_on_runtime()` so every managed `InvokeRuntime` call shows up
in `uvicorn.log`.

```bash
cp solutions/the-ledger/services/agentcore_runtime_with_invoke_log.py \
   pellier/backend/services/agentcore_runtime.py
```

---

## What bootstrap pre-applies (reference)

The Builder's Session ships with everything **already wired except** the
`floor_check` tool body — participants edit only that one function. At
provision time `scripts/bootstrap-labs.sh` (the `WORKSHOP_FORMAT=builders`
block) copies the reference files below into place. This list mirrors the
actual `copy_solution` calls in that script — it is for transparency and
manual recovery, not an in-room step. (Keep it in sync if you add a
pre-apply.)

Dispatcher + specialists (the agents Marco's turns 2/5 use) — note Stock
Keeper is **not** copied here; it ships live in the repo:

```bash
cp solutions/closing-marcos-gap/agents/curator.py          pellier/backend/agents/curator.py
cp solutions/closing-marcos-gap/agents/experience_guide.py pellier/backend/agents/experience_guide.py
cp solutions/closing-marcos-gap/agents/orchestrator.py     pellier/backend/agents/orchestrator.py
```

The builders variant of `agent_tools.py` — wires everything Stock
Keeper-adjacent (`restock_shelf`, `running_low`) **except** the
`floor_check` body, which participants add in Exercise 1:

```bash
cp solutions/closing-marcos-gap/services/agent_tools_builders_preapply.py \
   pellier/backend/services/agent_tools.py
```

AgentCore production services (Runtime, Memory, Gateway, identity, auth,
OTEL) plus the frontend identity hook:

```bash
cp solutions/the-ledger/services/agentcore_runtime.py        pellier/backend/services/agentcore_runtime.py
cp solutions/the-ledger/services/agentcore_memory.py         pellier/backend/services/agentcore_memory.py
cp solutions/the-ledger/services/agentcore_gateway.py        pellier/backend/services/agentcore_gateway.py
# Policy is managed (Cedar at the Gateway, provisioned by scripts/deploy/deploy_policy.py).
# The backend ships services/managed_policy.py in-tree — there is no local policy file to copy.
cp solutions/the-ledger/services/agentcore_identity.py       pellier/backend/services/agentcore_identity.py
cp solutions/the-ledger/services/cognito_auth.py             pellier/backend/services/cognito_auth.py
cp solutions/the-ledger/services/otel_trace_extractor.py     pellier/backend/services/otel_trace_extractor.py
cp solutions/the-ledger/frontend/agentIdentity.ts            pellier/frontend/src/utils/agentIdentity.ts
```

The `the-quiet-search/` retrieval references (`hybrid_search.py`,
`business_logic.py`, `hybrid_search_with_rerank.py`) and the
`the-concierge/` MCP references are **observe-only** — bootstrap does not
copy them, because those files already ship live in the repo. They are
here as readable reference implementations for the Act I rerank
comparison and the Act III MCP read.

The only file participants change in-room is the `floor_check` body in
`pellier/backend/services/agent_tools.py` (Exercise 1, with the
`agent_tools_floor_check_solution.py` escape hatch above).
