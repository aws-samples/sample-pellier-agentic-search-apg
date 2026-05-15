---
title: "Part II · AgentCore Runtime (demo)"
weight: 21
---

:::alert{type="info"}
**Part II of III — AgentCore platform** (sublab 21). About nine minutes.
Bootstrap already ran `agentcore configure` and `agentcore launch` (~5 min
before you arrived). In-room you read the entrypoint and **invoke** the
managed runtime — you do not launch again.*
:::

## Local code → managed runtime

| Phase | Who | What |
|-------|-----|------|
| **Build** | Platform (bootstrap) | `agentcore configure` + `agentcore launch` from `pellier/backend/` |
| **Entrypoint** | You (read) | `pellier/backend/agentcore_runtime.py` — `@app.entrypoint` wraps the orchestrator |
| **Invoke** | You (curl) | FastAPI calls `run_agent_on_runtime` when `USE_AGENTCORE_RUNTIME=true` |

The storefront Marco pills still use the **Dispatcher** on `/api/chat/stream`
(production pattern). Runtime is exercised on **`/api/agent/chat`** — the
same path the re:Invent workshop uses for managed execution.

---

## 1 · Confirm bootstrap wired runtime

```bash
cd /workshop/sample-pellier-agentic-search-apg
grep -E 'AGENTCORE_RUNTIME_ENDPOINT|USE_AGENTCORE_RUNTIME' pellier/backend/.env
```

Expected:

- `AGENTCORE_RUNTIME_ENDPOINT=arn:aws:bedrock-agentcore:...:runtime/...`
- `USE_AGENTCORE_RUNTIME=true`

If the endpoint is empty, your table lead's bootstrap skipped launch — the
demo still works **in-process** (`USE_AGENTCORE_RUNTIME=false`). Read the
entrypoint below; invoke step will return a fallback message.

Restart the app after any `.env` edit:

```bash
# builders: uvicorn reload usually picks up .env on next request; if not:
pkill -f 'uvicorn.*app:app' 2>/dev/null; sleep 1
cd pellier/backend && nohup uvicorn app:app --host 0.0.0.0 --port 8000 >> /tmp/pellier/uvicorn.log 2>&1 &
```

---

## 2 · Read the entrypoint (no edit required)

Open `pellier/backend/agentcore_runtime.py`.

```python
@app.entrypoint
def invoke(payload):
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "runtime-session")
    ...
    orchestrator = create_orchestrator()
    response = orchestrator(prompt)
    return {"response": str(response), "products": []}
```

**Narrative for your table:** configure declared this file as the container
entry; launch built the image; every `InvokeRuntime` call hits `invoke()`.

Compare with `scripts/deploy/agentcore_runtime_adapter.py` — that variant
discovers tools via MCP Gateway (re:Invent advanced track). Builder's uses
the in-repo orchestrator so the box works without Gateway Lambdas.

---

## 3 · Invoke managed runtime

```bash
SESSION="builders-runtime-$(date +%s)"
curl -sN -X POST http://localhost:8000/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d "{\"message\": \"Is the Hadley shirt at the Brooklyn warehouse?\", \"session_id\": \"${SESSION}\"}"
```

**Look for:** SSE events — `event: session` (session id + namespace), then
`event: chunk` with warehouse/stock language, then `event: done`.

If you wired `floor_check` in section 02, the answer should mention Brooklyn
(BK-01). If not, you'll still see a response from the orchestrator path.

---

## 4 · What configure + launch did (instructor narrative)

Bootstrap ran (simplified):

```bash
cd pellier/backend
agentcore configure --name pellier-agent \
  --entrypoint agentcore_runtime.py \
  --execution-role <runtime-execution-role-arn> \
  --non-interactive --region us-west-2
agentcore launch --agent pellier-agent
```

That produced the ARN in `.env`. **`services/agentcore_runtime.py`** is the
client: `run_agent_on_runtime()` calls `bedrock-agentcore:InvokeRuntime` with
payload `{"prompt", "session_id", "user_id"}`.

---

## See in the Atelier

- **Architecture → Runtime** — managed vs in-process
- **Routing** — why the Boutique stays on Dispatcher while Runtime serves
  `/api/agent/chat`

[Part III · Routing patterns →](/30-routing-patterns/)
