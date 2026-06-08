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

### Exercise 2 (mandatory) — SQL proof from `pellier.tool_audit` (Act II)

Generate a tool call, then read the Aurora ledger path by querying
`pellier.tool_audit`: raw row, JSONB extraction, and ALLOW-vs-DENY
evidence. This is SQL, not a code drop — there is no file to copy over a
runtime counterpart. The "⏩ out of time" escape hatch is a canned recap
query a facilitator can run live:

```bash
psql "$PG_URL" -f solutions/the-ledger/sql/tool_audit_recap.sql
```

It prints the most recent allowed `process_return` session, the raw
rows, a JSONB-extracted view, and instructions for checking a DENYed
session with `-v denied_session=...`.

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
`floor_check` tool body — participants edit only that one function.
Bootstrap copies these reference files into place at provision time; they
are listed here for transparency and manual recovery, not as in-room steps.

Retrieval + business logic:

```bash
cp solutions/the-quiet-search/services/hybrid_search.py    pellier/backend/services/hybrid_search.py
cp solutions/the-quiet-search/services/business_logic.py   pellier/backend/services/business_logic.py
```

Dispatcher + specialists (the agents Marco's turns 2/5 use):

```bash
cp solutions/closing-marcos-gap/agents/orchestrator.py     pellier/backend/agents/orchestrator.py
cp solutions/closing-marcos-gap/agents/curator.py          pellier/backend/agents/curator.py
cp solutions/closing-marcos-gap/agents/experience_guide.py pellier/backend/agents/experience_guide.py
cp solutions/closing-marcos-gap/agents/stock_keeper.py     pellier/backend/agents/stock_keeper.py
```

AgentCore production services (Runtime, Memory, Gateway, policy, identity):

```bash
cp solutions/the-ledger/services/agentcore_runtime.py        pellier/backend/services/agentcore_runtime.py
cp solutions/the-ledger/services/agentcore_memory.py         pellier/backend/services/agentcore_memory.py
cp solutions/the-ledger/services/agentcore_gateway.py        pellier/backend/services/agentcore_gateway.py
cp solutions/the-ledger/services/agentcore_policy.py         pellier/backend/services/agentcore_policy.py
cp solutions/the-ledger/services/agentcore_identity.py       pellier/backend/services/agentcore_identity.py
cp solutions/the-ledger/services/cognito_auth.py             pellier/backend/services/cognito_auth.py
cp solutions/the-ledger/services/otel_trace_extractor.py     pellier/backend/services/otel_trace_extractor.py
cp solutions/the-ledger/frontend/agentIdentity.ts            pellier/frontend/src/utils/agentIdentity.ts
```

The only file participants change in-room is the `floor_check` body in
`pellier/backend/services/agent_tools.py` (Exercise 1, with the
`agent_tools_floor_check_solution.py` escape hatch above).
