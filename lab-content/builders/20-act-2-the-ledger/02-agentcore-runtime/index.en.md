---
title: "Platform · AgentCore Runtime (Demo)"
weight: 20
---

:::alert{type="info"}
**Time:** ~5 min  ·  **Page:** 2 of 2 in Act II  ·  **Exercises on this page:** 0

Bootstrap already ran `agentcore configure` and `agentcore launch`
before you arrived. In-room you **read** the entrypoint and
**invoke** the managed runtime — you do not launch again. **One-hour
option:** keep this to one invoke plus one takeaway (managed runtime
keeps architecture constant, moves execution boundary).
:::

**You'll learn to:**

1. Read the **`@app.entrypoint`** contract — the function every
   `InvokeRuntime` call lands on — in `agentcore_runtime.py`.
2. **Invoke the managed runtime** through `/api/agent/chat` and
   observe the SSE event sequence: `session` → `chunk` → `done`.
3. Narrate the **`configure → launch → invoke` lifecycle** to your
   table — what bootstrap did, what you'd run yourself.
4. Compare **in-process** (`/api/chat/stream`, dispatcher) vs
   **managed** (`/api/agent/chat`, Runtime) execution boundaries on
   the same orchestrator.

In this page, "the ledger" means a second concrete artifact: managed
invoke events from `/api/agent/chat` (`session`, `chunk`, `done`).

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
discovers tools via MCP Gateway (re:Invent advanced track). This builder lab uses
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

If you completed [Build — Wire `floor_check`](/10-act-1-the-boutique/02-wire-floor-check/),
the answer should mention Brooklyn
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

---

## What you've learned

- **The same orchestrator can be reached two ways** — in-process via
  `/api/chat/stream` (dispatcher) and managed via `/api/agent/chat`
  (Runtime). Architecture stays constant; only the execution boundary
  moves.
- **The entrypoint is the contract.** `@app.entrypoint def invoke(payload)`
  is what `agentcore configure` declared and what every
  `InvokeRuntime` call hits.
- **`configure → launch → invoke` is a three-step lifecycle.** The
  first two are platform/build concerns (one-time, ops-owned); the
  third is what your application does on every request.
- **SSE makes the managed boundary inspectable.** `event: session →
  event: chunk → event: done` is the contract you can log, replay,
  and page on.

:::alert{type="success" header="Act III · The Concierge"}
[Operator View · Routing Patterns →](/30-act-3-the-concierge/01-routing-patterns/)
:::
