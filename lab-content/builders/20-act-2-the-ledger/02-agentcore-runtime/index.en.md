---
title: "02: AgentCore Runtime + Aurora ledger"
weight: 20
---

:::alert{type="info"}
**Time:** ~6 min  
**Exercises:** 1 mandatory (Aurora SQL ledger) + 1 optional (`logger.info` seam)  
**Surface:** `/api/agent/chat` (Runtime) · `pellier.tool_audit` (Aurora)
:::

Bootstrap already deployed the Runtime through the `@aws/agentcore` CLI before you arrived. In-room you **read** the entrypoint, **invoke** the managed runtime, then **run one SELECT against `pellier.tool_audit`** to reconstruct what the agent did: arguments, result, latency, and timestamp from Aurora.

**You'll learn to:**

1. Read the **`@app.entrypoint`** contract in `agentcore_runtime.py`.
2. Invoke the managed runtime through `/api/agent/chat` and observe the SSE sequence: `session` → `chunk` → `done`.
3. Read the agent's audit ledger from Aurora: `SELECT … FROM pellier.tool_audit WHERE session_id = '…'`.
4. Use JSONB operators (`->`, `->>`) to extract structured fields from `args` and `result`.
5. Narrate the **`render templates → deploy → invoke`** lifecycle of the `@aws/agentcore` CLI and the **write-then-update audit pattern**.
6. Compare in-process execution (`/api/chat/stream`) with managed Runtime execution (`/api/agent/chat`) on the same orchestrator.

:::alert{type="info" header="New to AgentCore Runtime?"}
Runtime does not change the agent's reasoning. It changes the execution boundary. The same orchestrator code is packaged behind an endpoint the platform can invoke. In this lab, bootstrap rendered `agentcore.json` from Workshop Studio outputs and ran `agentcore deploy -y --json` (the Node CLI, `@aws/agentcore`); `/api/agent/chat` calls that managed path.
:::

In this page, "the ledger" is literal: a row in `pellier.tool_audit` keyed by `(session_id, created_at)`, with JSONB `args` and `result` columns you can query directly.

---

## Local code → managed runtime

| Phase | Who owns it | What it means |
|---|---|---|
| **Render templates** | Platform/bootstrap | `envsubst` injects CFN outputs into `agentcore.json` + `aws-targets.json` (runtime name, entrypoint, execution role, region, JWT issuer, env vars). |
| **Deploy** | Platform/bootstrap | `agentcore deploy -y --json` (Node CLI, `@aws/agentcore`) builds and publishes the Runtime; emits the runtime ARN. |
| **Invoke** | Application request path | FastAPI calls Runtime when `USE_AGENTCORE_RUNTIME=true`; every request lands on `@app.entrypoint`. |

The storefront Marco pills still use the **Dispatcher** on `/api/chat/stream`. Runtime is exercised on **`/api/agent/chat`** so you can compare local/in-process behavior with managed execution without changing the Boutique path.

:::alert{type="info" header="Where Gateway and MCP fit"}
Runtime hosts the agent. Gateway hosts or brokers tools. MCP is the protocol shape those tools can expose. Pellier keeps Gateway/MCP as an Act III operator read so Act II can stay focused: invoke the agent, prove the event stream, and query the Aurora evidence row.
:::

**Pattern:** Runtime is the managed invocation boundary. The orchestrator code is identical; what changes is who owns execution. In another organization, that boundary might be a regulated execution environment, an operations-owned deployment surface, or a compliance perimeter.

---

## 1. Confirm bootstrap wired Runtime

```bash
cd /workshop/sample-pellier-agentic-search-apg
grep -E 'AGENTCORE_RUNTIME_ENDPOINT|USE_AGENTCORE_RUNTIME' pellier/backend/.env
```

Expected:

- `AGENTCORE_RUNTIME_ENDPOINT=arn:aws:bedrock-agentcore:...:runtime/...`
- `USE_AGENTCORE_RUNTIME=true`

If the endpoint is empty, your table lead's bootstrap skipped launch. The demo still works **in-process** (`USE_AGENTCORE_RUNTIME=false`). Read the entrypoint below; the invoke step may return a fallback message.

Restart the app after any `.env` edit:

```bash
# builders: uvicorn reload usually picks up .env on next request; if not:
pkill -f 'uvicorn.*app:app' 2>/dev/null; sleep 1
cd pellier/backend && nohup uvicorn app:app --host 0.0.0.0 --port 8000 >> /tmp/pellier/uvicorn.log 2>&1 &
```

---

## 2. Read the entrypoint: no edit required

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

**Narrative for your table:** `agentcore.json` declared this function as the container entrypoint; `agentcore deploy` published it; every `InvokeRuntime` call lands on `invoke(payload)`.

Compare with `scripts/deploy/agentcore_runtime_adapter.py` if you want the advanced track. That variant discovers tools through MCP Gateway. This Builder Session uses the in-repo orchestrator so the room can finish without deploying Gateway-backed tool hosting.

---

## 3. Exercise 2: Read the agent's audit ledger from Aurora

:::alert{type="warning" header="Exercise 2 of 2: the Aurora read path"}
Fire one policy-gated turn – Theo's damaged-return flow – then run **one SELECT** against `pellier.tool_audit` to reconstruct what the agent did. Logs can prove a request crossed a process boundary. The Aurora ledger proves the tool action: arguments, result, latency, and timestamp from a durable database row.
:::

### Why Theo's damaged return?

`process_return` is Cedar-gated on `reason='damaged'`, so this turn exercises policy and audit evidence in one short path. If Cedar allows the action, the tool runs and the audit row is written. If Cedar denies the action, the tool does not run; the denial belongs in the policy decision surface, not in `tool_audit`. Read tools such as `floor_check` are also audited when they run; the real asymmetry is **ALLOW vs DENY**, not read vs write.

:::alert{type="info" header="New to Cedar?"}
Cedar is the policy language used here to decide whether a tool action is allowed. Think of it as the gate between *the agent wants to act* and *the system of record is allowed to change*. This workshop does not make you write Cedar policy; it shows you where policy affects tool execution and evidence.
:::

### Generate a row: Theo's damaged-return turn

```bash
SESSION="builders-ledger-$(date +%s)"
echo "$SESSION"   # save this; you'll paste it into the SQL below

curl -sN -X POST http://localhost:8000/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d "{\"message\": \"My Wabi-Sabi Bowl arrived chipped. Please file a damaged return (my customer id is 'theo').\", \"session_id\": \"${SESSION}\"}"
```

Look for SSE events that end with the agent confirming the return was filed. The required row to prove is **`process_return`**.

### Run the SELECT

Connect with the credentials from `pellier/backend/.env`:

```bash
PGPASSWORD="$DB_PASSWORD" psql \
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"
```

Then paste, substituting your `$SESSION` from above:

```sql
SELECT
  tool,
  caller,
  args,
  result,
  latency_ms,
  created_at
FROM pellier.tool_audit
WHERE session_id = 'builders-ledger-...'   -- your session id
ORDER BY created_at;
```

**Expected shape:** at least one row for `process_return`, plus any read tools the turn used before the mutation. `tool_audit` records every Cedar-allowed tool call that actually runs, reads and writes alike. The mandatory proof remains the policy-gated `process_return` row because it exercises policy and durable audit evidence in one short path.

```text
      tool      | caller |                          args                          |                result                | latency_ms |          created_at
----------------+--------+--------------------------------------------------------+---------------------------------------+------------+-------------------------------
 process_return | agent  | {"customer_id":"theo","product_id":7,"reason":"damaged"} | {"return_id":42,"status":"pending",…} |        184 | 2026-05-20 14:23:11.214829+00
```

If the row's `result` column is `NULL`, the tool started but did not finish. That is a useful production signal, not just a workshop failure.

### What this proves

- **Tool evidence is durable.** Arguments, result, latency, and timestamp are queryable after the turn completes.
- **Policy affects execution.** ALLOW means the tool can run. DENY means no tool call, so there is no successful tool row to replay.
- **Latency is per-tool, not per-turn.** `latency_ms` is the tool's round trip, not the full LLM response time.
- **Aurora is more than the vector store.** It is also the system-of-record for operational evidence.

### Bonus: JSONB extraction

`reason` is the Cedar-gated field. Extract it, plus the inserted `return_id`, without parsing JSON in application code:

```sql
SELECT
  args->>'customer_id'  AS customer,
  args->>'reason'       AS reason,
  result->>'return_id'  AS return_id,
  latency_ms
FROM pellier.tool_audit
WHERE session_id = 'builders-ledger-...'   -- your session id
  AND tool = 'process_return';
```

The `->>` operator returns the JSONB field as text. `->` returns JSONB. JSONB keeps the ledger flexible when tool argument shapes evolve.

::::expand{header="Out of time? Drop in the canned query + sample row"}

```bash
psql "$PG_URL" -f solutions/the-ledger/sql/tool_audit_recap.sql
```

That runs the SELECT against the most recent session id automatically and prints both the raw and JSONB-extracted views.

::::

---

## 3a. Optional: the `logger.info` observability seam

If you finish early and want a second receipt, add one `logger.info(...)` line to `services/agentcore_runtime.py` so every Runtime invoke appears in `uvicorn.log`. The Aurora ledger above tells you what the agent **did**; this log line tells you the request **crossed the managed boundary**.

::::expand{header="Optional: wire the log line"}

Open `pellier/backend/services/agentcore_runtime.py`, find `run_agent_on_runtime()`. Just below the `payload = {...}` dict and above the `try: import boto3` block, add:

```python
logger.info(
    "agentcore.invoke session=%s user=%s prompt_len=%d endpoint=%s",
    session_id,
    user_id or "anonymous",
    len(message),
    endpoint.split("/")[-1] if endpoint else "unset",
)
```

Tail the log:

```bash
tail -f /tmp/pellier/uvicorn.log | grep agentcore.invoke
```

Re-run section 4 below. You should see one `agentcore.invoke session=...` line per call.

Or skip the manual edit:

```bash
cp solutions/the-ledger/services/agentcore_runtime_with_invoke_log.py \
   pellier/backend/services/agentcore_runtime.py
```

::::

---

## 4. Invoke managed Runtime: read-path comparison

Section 3 exercised a policy-gated write. This call exercises Marco's `floor_check` through the same managed endpoint to confirm the Runtime path is healthy for a read-oriented turn too.

```bash
SESSION="builders-runtime-$(date +%s)"
curl -sN -X POST http://localhost:8000/api/agent/chat \
  -H 'Content-Type: application/json' \
  -d "{\"message\": \"Is the Hadley shirt at the Brooklyn warehouse?\", \"session_id\": \"${SESSION}\"}"
```

**Look for:** `event: session`, then `event: chunk` with warehouse or stock language, then `event: done`.

If you completed [Wire `floor_check`](/10-act-1-the-boutique/02-wire-floor-check/), the answer should mention Brooklyn (`BK-01`). If not, you should still see a response from the orchestrator path.

---

## 5. What bootstrap actually ran

Bootstrap ran a simplified version of this before the room opened, using the **Node-based `@aws/agentcore` CLI** (`npm install -g @aws/agentcore`). The CLI takes no flag overrides – every value previously passed as a flag now lives in `agentcore.json` and `aws-targets.json`, rendered from CFN outputs at deploy time:

```bash
cd pellier/backend

# 1. Render the two config files from Workshop Studio outputs
envsubst < agentcore.json.template     > agentcore.json
envsubst < aws-targets.json.template   > aws-targets.json

# 2. Deploy. The CLI reads both JSON files and creates the Runtime.
agentcore deploy -y --json
```

That produced the Runtime ARN in `.env`. The client path in `services/agentcore_runtime.py` sends payload fields such as `prompt`, `session_id`, and `user_id` to `bedrock-agentcore:InvokeRuntime`. The runtime Python SDK (`bedrock-agentcore>=1.4.3`) is unchanged; only the deploy CLI moved from the deprecated Python `bedrock-agentcore-starter-toolkit` to the Node-based `@aws/agentcore`.

---

## See in the Atelier

- **Architecture → Runtime:** managed vs in-process execution.
- **Memory:** the session timeline and the other memory substrates.
- **Policy / evidence surfaces:** where ALLOW/DENY and tool evidence are explained.

---

## What you've learned

- **Runtime is an invocation boundary, not a new agent.** The same orchestrator can be reached in-process through `/api/chat/stream` and managed through `/api/agent/chat`.
- **The entrypoint is the contract.** `@app.entrypoint def invoke(payload)` is what Runtime calls.
- **`render templates → deploy → invoke` separates build-time and request-time concerns.** Rendering and deploy are platform work (`@aws/agentcore` CLI, one-shot); invoke is what the application does per request.
- **Aurora is the agent's evidence ledger.** `tool_audit` records tool behavior with JSONB arguments and results that are queryable from SQL.
- **Cedar is the policy seam.** It decides whether a sensitive tool action may run before Aurora can record its result.
- **SSE makes the managed boundary visible.** `event: session → event: chunk → event: done` is the response contract you can log, replay, and debug.

:::alert{type="success" header="Act III: The Concierge"}
[Routing patterns →](/30-act-3-the-concierge/01-routing-patterns/)
:::
