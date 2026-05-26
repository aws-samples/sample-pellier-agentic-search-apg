---
title: "01: Memory – four substrates"
weight: 10
---

:::alert{type="info"}
**Time:** ~6 min  
**Exercises:** 0  
**Surface:** `/api/agent/session/{id}` · Boutique chat · Atelier Memory panel
:::

No code to ship. The hands-on is a **working-memory readback**: create two turns, read the ordered timeline from `/api/agent/session/{id}`, reload the Boutique, and confirm the same session comes back. Bootstrap already created `PellierMemory` and wrote `AGENTCORE_MEMORY_ID` to `.env`.

**You'll learn to:**

1. Confirm the platform-provisioned **AgentCore Memory resource** is wired by reading `AGENTCORE_MEMORY_ID` from `.env`.
2. Read a session timeline back from `/api/agent/session/{session_id}` and recognize it as **an ordered list of turns**, not a summary.
3. Verify **session continuity on page reload** from the same `pellier-session-id` in Local Storage.
4. Locate the other three memory substrates Pellier wires alongside working memory: *semantic*, *episodic*, and *procedural*.

:::alert{type="info" header="New to AgentCore Memory?"}
For this lab, think of AgentCore Memory as the managed place where the agent stores and retrieves conversation state. The browser has a session id. The backend writes each completed turn into a namespace under that id. On the next request, or after a page reload, the backend can read the same ordered timeline back. You are not building the memory service here; you are proving that Pellier is wired to it.
:::

In this page, "the ledger" means one concrete artifact: the session timeline returned by `/api/agent/session/{session_id}`. The other three substrates each have their own surface, named below.

---

## The four memory substrates

Memory in an agent system is not one bucket. Pellier wires four substrates with different lifetimes and write cadences:

| Substrate | What it answers | Storage | Lifetime | Write cadence |
|---|---|---|---|---|
| **Working** | What happened in this conversation, in order? | AgentCore Memory session events under `anon-{sid}` or `user-{cognito_sub}-session-{sid}` | Last K turns | Every turn |
| **Semantic** | What stable preferences do we know? | AgentCore Memory KV under `user:{id}:preferences` | Durable | When the customer tells us something stable |
| **Episodic** | What customer events are relevant now? | Aurora `pellier.customer_episodic_seed`, `pellier.orders`, `pellier.returns` | Durable | When the turn earns the latency |
| **Procedural** | Which tools win for which intents, and how fast? | Aurora `pellier.tool_audit` aggregate | Append-only | After allowed tool calls |

The required proof below is only for **working memory**. The other three are visible in the Atelier's Memory surface and named in section 5.

:::alert{type="info" header="Pattern to borrow"}
Session memory is not a durable customer, patient, account, or asset profile. Keep lifetimes separate: current support chat versus account history, current intake versus longitudinal member record, current troubleshooting session versus asset maintenance history. Pellier makes that separation visible in four substrates.
:::

---

## 1. Confirm memory is provisioned

```bash
cd /workshop/sample-pellier-agentic-search-apg
grep AGENTCORE_MEMORY_ID pellier/backend/.env
```

You should see a non-empty memory id. If it is blank, tell your table lead before continuing; the app may fall back to a local store, but that would not prove the AgentCore path.

---

## 2. Create two turns in the Boutique

1. Open the **Boutique** tab and the chat drawer (`⌘K` / **Ask Pellier**).
2. Confirm **Marco** is selected.
3. Click pill 1: `What linen do you have for 10 days in Goa?`
4. Wait for the answer.
5. Click pill 3: `What is the price range for linen shirts?`
6. Wait for the answer.

Each completed turn is appended to working memory under your session id.

---

## 3. Read session history from the API

Open browser DevTools → **Application** → **Local Storage** on the Boutique origin → copy **`pellier-session-id`**.

Then run:

```bash
SESSION="<paste-session-id-here>"
curl -s "http://localhost:8000/api/agent/session/${SESSION}" | python3 -m json.tool
```

**Look for:** a `turns` array with at least four entries: two user messages and two assistant replies from the pills you clicked. Order matters. Working memory is a timeline, not a summary.

::::expand{header="What a healthy response shape looks like"}

The exact text will vary, but the response should look structurally similar to this:

```json
{
    "session_id": "...",
  "namespace": "anon-...",
  "turns": [
    {"role": "user", "content": "What linen do you have for 10 days in Goa?"},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "What is the price range for linen shirts?"},
    {"role": "assistant", "content": "..."}
  ]
}
```

If the array exists and the turn order is intact, the working-memory readback passed.

::::

---

## 4. Continuity check: reload

1. Hard-refresh the Boutique tab.
2. Open the chat drawer again.
3. Confirm the prior turns are still present.

If history is missing, confirm `pellier-session-id` is still present in Local Storage and repeat the API readback.

**Teaching point:** working memory is **session-scoped** and **bounded**. It is cheap to read on every request. The other three substrates answer different questions, on different cadences, in different stores.

---

## 5. The other three substrates, in the Atelier

Click **Memory** in the Atelier sidebar. The four-panel viewer at `/atelier/architecture/memory` shows each substrate with a provenance pill such as `Live`, `Fixture`, or `Sketch`.

| Panel | Where Pellier reads it | What you should see for Marco |
|---|---|---|
| **Working** | `/api/agent/session/{id}` | The two turns you just made |
| **Semantic** | AgentCore Memory `GetMemoryRecord` against `user:{id}:preferences` | Stable taste signals such as linen, warm neutrals, natural fibers, travel-ready pieces |
| **Episodic** | `SELECT * FROM pellier.customer_episodic_seed WHERE customer_id = 'marco'` plus `pellier.orders` / `pellier.returns` joins | Lisbon-trip browsing rows and prior customer events |
| **Procedural** | `SELECT tool, count(*), avg(latency_ms) FROM pellier.tool_audit GROUP BY tool` | Per-tool activity and latency signals |

The API you called in section 3 is the operational source of truth for the working panel. The other three panels name their SQL or key-value read so a builder can reproduce the evidence outside the UI.

---

## Identity: the namespace seam

Marco's session id can stay the same whether he is anonymous or signed in. What changes is the namespace that prefixes it. AgentCore session IDs must match `[a-zA-Z0-9][a-zA-Z0-9-_]*`, so the canonical form uses dashes, not colons.

| Mode | Namespace | In this lab |
|---|---|---|
| Anonymous | `anon-{session_id}` | Default builder path |
| Signed in | `user-{cognito_sub}-session-{session_id}` | Production sign-in path, not wired in the room |

This is the place where production identity lands. In a real shopper-facing deployment, the app would attach the end user's identity to the memory namespace, while AgentCore Identity would let the agent use its own workload identity for AWS calls. You do not wire Cognito or Identity here; you learn where the seam belongs.

:::alert{type="info" header="If you're new to auth terminology"}
The user identity answers *who is the shopper?* The workload identity answers *what is the agent allowed to call in AWS?* Production systems keep those separate. Pellier shows the boundary with `anon:` and `user:` namespaces without making authentication a hands-on exercise.
:::

---

## What you've learned

- **Memory is four substrates, not two tiers.** Working, semantic, episodic, and procedural each answer a different operator question.
- **Working memory is a timeline, not a summary.** Order matters because the `turns` array is what the agent can use on the next request.
- **Session continuity is platform-backed.** A page reload preserves the conversation because the same `pellier-session-id` rehydrates from `AGENTCORE_MEMORY_ID`.
- **The API is the operational source of truth.** The Atelier viewer explains the system, but `/api/agent/session/{id}` is the proof you can script.
- **Identity is a seam, not a rewrite.** `anon-{sid}` versus `user-{cognito_sub}-session-{sid}` changes the trust boundary without changing the agent's core logic.

:::alert{type="success" header="Next: Runtime"}
[AgentCore Runtime + Aurora ledger →](/20-act-2-the-ledger/02-agentcore-runtime/)
:::
