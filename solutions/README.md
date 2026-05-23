# Solutions — drop-in replacements

Copy a solution file over its runtime counterpart and the backend
auto-restarts. Two formats consume this directory:

- **60-min Builder's Session (DC Summit)** — two exercises, one stretch.
- **120-min Workshop (re:Invent)** — three modules, multiple challenges.

```
solutions/
├── the-quiet-search/   → Workshop Module 1 (semantic search)
├── closing-marcos-gap/ → Workshop Module 2 + Builder's Exercise 1
└── the-ledger/         → Workshop Module 3 + Builder's Exercise 2
```

---

## Builder's Session — 60 min

Two exercises, one optional stretch. The cp commands below are the
"⏩ out of time" escape hatches referenced from each lab page.

### Exercise 1 — `floor_check` body (Act I)

Replaces the stubbed `floor_check` tool body with the working
implementation that calls `BusinessLogic.floor_check()` against
`pellier.warehouse_inventory`.

```bash
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py \
   pellier/backend/services/agent_tools.py
```

Paste-only option (just the 9-line body, between `START` / `END`
markers): `solutions/closing-marcos-gap/services/floor_check_tool_body.py`.

### Exercise 2 — `logger.info` observability hook (Act II)

Adds one `logger.info("agentcore.invoke ...")` line to
`run_agent_on_runtime()` so every managed `InvokeRuntime` call shows up
in `uvicorn.log`.

```bash
cp solutions/the-ledger/services/agentcore_runtime_with_invoke_log.py \
   pellier/backend/services/agentcore_runtime.py
```

### Stretch — Anna skill edit (Act I, optional)

The "stretch" on the *Prove rerank* page asks attendees to change one
guidance line in `skills/the-gift-table/SKILL.md` and prove the edit
landed with SQL against `pellier.tool_uses`. **There is no solution
file** — the change is a single rule in the skill markdown, and the
proof is a `SELECT`, not a code drop.

---

## Workshop Module 1 — *The Quiet Search*

```bash
cp solutions/the-quiet-search/services/hybrid_search.py    pellier/backend/services/hybrid_search.py
cp solutions/the-quiet-search/services/business_logic.py   pellier/backend/services/business_logic.py
```

## Workshop Module 2 — *Closing Marco's Gap*

```bash
# Current agent-tools file (every @tool, including a finished floor_check)
cp solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py    pellier/backend/services/agent_tools.py

# The dispatcher + the two specialists turns 2/5 use
cp solutions/closing-marcos-gap/agents/orchestrator.py     pellier/backend/agents/orchestrator.py
cp solutions/closing-marcos-gap/agents/curator.py          pellier/backend/agents/curator.py
cp solutions/closing-marcos-gap/agents/experience_guide.py pellier/backend/agents/experience_guide.py
cp solutions/closing-marcos-gap/agents/stock_keeper.py     pellier/backend/agents/stock_keeper.py
```

The 60-min Builder's Session pre-applies everything **except** the
`floor_check` tool body in `agent_tools.py`. Participants edit only
that one function.

## Workshop Module 3 — *The Ledger*

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

For the 60-min Builder's Session, only `agentcore_runtime_with_invoke_log.py`
(see Exercise 2 above) is copied — the rest of these files ship
pre-applied by bootstrap.
