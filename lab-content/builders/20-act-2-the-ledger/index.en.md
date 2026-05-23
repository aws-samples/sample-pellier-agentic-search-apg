---
title: "Act II · The Ledger"
weight: 20
---

*Evidence view. ~11 minutes — one observability hook, two production proofs.*

:::alert{type="info" header="Act II · The Ledger"}
**Time:** ~11 min  ·  **Exercise:** 1 (the observability hook on the managed Runtime path)  ·  **Surfaces:** `/api/agent/session/{id}` (STM) · `/api/agent/chat` (Runtime)

Every good boutique keeps a ledger — a quiet, inspectable record of
what happened, in order, that anyone can reopen later. **Act I shipped
the agent on your laptop. Act II is the same agent in production** —
same orchestrator, same tools, same prompts — reached through Bedrock
AgentCore.

Bootstrap already ran `agentcore configure` and `agentcore launch`
before you sat down. Your job is to **read the ledger** the platform
keeps for you, then **add the one log line** that makes every
`InvokeRuntime` call visible in `uvicorn.log` — the second build
moment of the session.
:::

The Boutique's ledger is **Bedrock AgentCore**. Two artifacts make it
real:

1. **Short-term memory (STM)** — Marco's turns, in order, recoverable
   from a single API call. Survives a page reload. Bounded by design.
2. **Managed Runtime** — the same orchestrator behind a managed
   endpoint. The architecture stays constant; only the execution
   boundary moves.

---

## The arc · ~11 minutes

```text
   Memory (STM)            Runtime
   ~6 min                  ~5 min
   read session timeline   wire one log line, invoke
   from /api/agent/        managed endpoint, watch
   session/{id}            uvicorn.log
   ▲                       ▲
   evidence                Exercise 2 + production seam
```

---

## Learning objectives

By the end of Act II you will be able to:

1. **Prove that AgentCore Memory persists** Marco's turns within a
   session and survives a page reload, by reading the same conversation
   back through `/api/agent/session/{session_id}`.
2. **Distinguish session-scoped STM** (cheap, bounded, 30-day expiry)
   from **long-term taste memory** that lives in Aurora pgvector
   profile embeddings — and know which to reach for when.
3. **Invoke a pre-launched AgentCore Runtime** through the same
   FastAPI surface, observe SSE events (`session` → `chunk` → `done`),
   and read the `@app.entrypoint` that made it possible.
4. **Add one `logger.info(...)` line** to the managed Runtime path
   (Exercise 2) so every `InvokeRuntime` call is visible in
   `uvicorn.log` — the smallest observability seam that proves the
   request really left the local process.
5. **Narrate `configure → launch → invoke`** to your table — what
   bootstrap did *for* you, and what you'd run *yourself* in your own
   pipeline.

---

## Core concepts ladder

The platform territory underneath the verification, in the order you'll
meet it:

| Concept | What you'll see |
|---|---|
| **AgentCore Memory namespaces** | `anon:{session_id}` for unauthenticated shoppers; `user:{cognito_sub}:session:{session_id}` for signed-in flows |
| **STM as timeline, not summary** | Ordered `turns` array — user/assistant pairs preserved in arrival order |
| **Session continuity** | `pellier-session-id` in Local Storage rehydrates state on reload |
| **Two memory systems, one agent** | STM (bounded, session-scoped) ≠ long-term taste (Aurora pgvector profile embeddings) |
| **Runtime entrypoint contract** | `@app.entrypoint def invoke(payload)` — the function that every `InvokeRuntime` call lands on |
| **Local code → managed microVM** | `agentcore configure` declares entrypoint · `agentcore launch` builds image · `bedrock-agentcore:InvokeRuntime` reaches it |

---

## What you'll do

| Page | Activity | Time | Exercise |
|---|---|---|---|
| 01 · [AgentCore Memory (STM)](01-agentcore-memory-stm/) | Generate two turns, read them back from API, prove continuity on reload | ~6 min | — |
| 02 · [AgentCore Runtime (demo)](02-agentcore-runtime/) | Add one `logger.info(...)` line, invoke the managed endpoint, watch the call land in `uvicorn.log` | ~5 min | **Exercise 2** |

---

## What you'll have proved

```text
   STM persists              → /api/agent/session/{id} returns ordered turns
   STM survives reload        → conversation rehydrates from same session id
   Runtime is reachable       → SSE: event: session → event: chunk → event: done
   Exercise 2 lands           → grep "agentcore.invoke" uvicorn.log shows your line
   Same agent, two surfaces   → /api/chat/stream (in-process) ≡ /api/agent/chat (managed)
```

---

:::alert{type="warning" header="Exercise 2 — the build moment in Act II"}

**`logger.info(...)` on the managed Runtime path**  *(in 02-agentcore-runtime)*
Add one line in `pellier/backend/services/agentcore_runtime.py` so
every `InvokeRuntime` call is visible in `uvicorn.log`. This is the
smallest observability seam that proves the request really left the
local process.
**⏩ Out of time?** A one-line `cp` from `solutions/the-ledger/`
swaps in the reference implementation — the act still completes.

:::

:::alert{type="success" header="Begin Act II"}
[Platform · AgentCore Memory (STM) →](01-agentcore-memory-stm/)
:::
