# Solutions — drop-in replacements

Copy a solution file over its runtime counterpart and the backend
auto-restarts. Three editorial-named directories, one per workshop
module:

```
solutions/
├── the-quiet-search/   → Module 1 reference (semantic search)
├── closing-marcos-gap/ → Module 2 (Stock Keeper + agent tools)
└── the-ledger/    → Module 3 (AgentCore production plumbing)
```

## Module 1 — *The Quiet Search*

```bash
cp solutions/the-quiet-search/services/hybrid_search.py    pellier/backend/services/hybrid_search.py
cp solutions/the-quiet-search/services/business_logic.py   pellier/backend/services/business_logic.py
```

## Module 2 — *Closing Marco's Gap*

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
that one function. If a table is short on time, copy the full
`agent_tools_floor_check_solution.py` file, or paste only
`closing-marcos-gap/services/floor_check_tool_body.py`.

## Module 3 — *The Ledger*

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
