# Solutions — Drop-in Replacements

Copy a solution file over the challenge file and the backend auto-restarts.

## Module 1: Smart Search

```bash
cp solutions/module1/services/hybrid_search.py pellier/backend/services/hybrid_search.py
cp solutions/module1/services/business_logic.py pellier/backend/services/business_logic.py
```

## Module 2: Agentic AI

```bash
cp solutions/module2/services/agent_tools.py pellier/backend/services/agent_tools.py
cp solutions/module2/agents/recommendation_agent.py pellier/backend/agents/recommendation_agent.py
cp solutions/module2/agents/orchestrator.py pellier/backend/agents/orchestrator.py
```

## Module 3: Production Patterns

```bash
cp solutions/module3/services/agentcore_runtime.py pellier/backend/agentcore_runtime.py
cp solutions/module3/services/agentcore_memory.py pellier/backend/services/agentcore_memory.py
cp solutions/module3/services/agentcore_gateway.py pellier/backend/services/agentcore_gateway.py
cp solutions/module3/services/otel_trace_extractor.py pellier/backend/services/otel_trace_extractor.py
cp solutions/module3/frontend/agentIdentity.ts pellier/frontend/src/utils/agentIdentity.ts
```
