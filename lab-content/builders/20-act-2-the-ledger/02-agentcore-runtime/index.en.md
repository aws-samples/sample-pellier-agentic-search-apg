---
title: "Platform · AgentCore Runtime (Demo)"
weight: 20
---

:::alert{type="info"}
**Time:** ~5 min  ·  **Page:** 2 of 2 in Act II  ·  **Exercises on this page:** 1 (the only build moment in this act)

Bootstrap already ran `agentcore configure` and `agentcore launch`
before you arrived. In-room you **read** the entrypoint, **add one
`logger.info(...)` line** so every managed invoke is visible in
`uvicorn.log`, then **invoke** the managed runtime and watch your
log line land.
:::

**You'll learn to:**

1. Read the **`@app.entrypoint`** contract — the function every
   `InvokeRuntime` call lands on — in `agentcore_runtime.py`.
2. **Add one observability hook** to `services/agentcore_runtime.py`
   so every `InvokeRuntime` call shows up in `uvicorn.log` — the
   smallest seam that proves the request really left the local
   process.
3. **Invoke the managed runtime** through `/api/agent/chat` and
   observe the SSE event sequence: `session` → `chunk` → `done`.
4. Narrate the **`configure → launch → invoke` lifecycle** to your
   table — what bootstrap did, what you'd run yourself.
5. Compare **in-process** (`/api/chat/stream`, dispatcher) vs
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

## 3 · Exercise 2 · Wire the observability hook

:::alert{type="warning" header="Exercise 2 of 2 — the build moment in Act II"}
Add **one `logger.info(...)` line** to the managed Runtime client so
every `InvokeRuntime` call is visible in `uvicorn.log`. This is the
smallest seam that proves the request really left the local process.

**⏩ Out of time?** A one-line `cp` from `solutions/the-ledger/`
swaps in the reference implementation — see the escape hatch at the
end of this section.
:::

Open:

```text
pellier/backend/services/agentcore_runtime.py
```

Find `run_agent_on_runtime()`. Just below the `payload = {...}` dict
and **above** the `try: import boto3` block, add this log line:

```python
logger.info(
    "agentcore.invoke session=%s user=%s prompt_len=%d endpoint=%s",
    session_id,
    user_id or "anonymous",
    len(message),
    endpoint.split("/")[-1] if endpoint else "unset",
)
```

Save. Uvicorn's reload will pick it up on the next request. If reload
is off:

```bash
pkill -f 'uvicorn.*app:app' 2>/dev/null; sleep 1
cd pellier/backend && nohup uvicorn app:app --host 0.0.0.0 --port 8000 >> /tmp/pellier/uvicorn.log 2>&1 &
```

### Verify your line lands

In one terminal, tail the log:

```bash
tail -f /tmp/pellier/uvicorn.log | grep agentcore.invoke
```

Then re-run the invoke from §4 below — you should see one
`agentcore.invoke session=... user=... prompt_len=... endpoint=...`
line per call. That line is your proof the request crossed the
boundary into the managed Runtime.

::::expand{header="⏩ Out of time? Drop in the solution"}

```bash
cp solutions/the-ledger/services/agentcore_runtime_with_invoke_log.py \
   pellier/backend/services/agentcore_runtime.py
```

That swaps in the reference file with the `logger.info(...)` line in
place. Save your work first if you've made unrelated edits.

::::

---

## 4 · Invoke managed runtime

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

## 5 · What configure + launch did (instructor narrative)

Bootstrap ran (simplified — substitute your account's region):

```bash
cd pellier/backend
agentcore configure --name pellier-agent \
  --entrypoint agentcore_runtime.py \
  --execution-role <runtime-execution-role-arn> \
  --non-interactive --region "$AWS_REGION"  # e.g. us-east-1, us-west-2
agentcore launch --agent pellier-agent
```

That produced the ARN in `.env`. **`services/agentcore_runtime.py`** is the
client: `run_agent_on_runtime()` calls `bedrock-agentcore:InvokeRuntime` with
payload `{"prompt", "session_id", "user_id"}`.

> **Region note for DC Summit attendees:** the workshop instance runs in
> `us-west-2` (where Cohere Embed v4 and Rerank v3.5 ship in this
> tranche). When you replicate this in your own account, pick whichever
> region has both Bedrock model access AND your Aurora/RDS cluster —
> AgentCore Runtime invocations are cross-region-capable, but every
> hop costs latency.

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
- **One log line is the smallest observability seam that matters.**
  Your `logger.info("agentcore.invoke ...")` is the proof — without
  it, a managed call is indistinguishable from a local one.
- **SSE makes the managed boundary inspectable.** `event: session →
  event: chunk → event: done` is the contract you can log, replay,
  and page on.

:::alert{type="success" header="Act III · The Concierge"}
[Operator View · Routing Patterns →](/30-act-3-the-concierge/01-routing-patterns/)
:::
