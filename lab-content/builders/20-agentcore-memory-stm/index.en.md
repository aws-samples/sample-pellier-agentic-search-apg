---
title: "Part II · AgentCore Memory (STM)"
weight: 20
---

:::alert{type="info"}
**Part II of III — AgentCore platform** (sublabs 20–21). About ten minutes.
No new code to ship — verify that short-term memory persists across turns.
Bootstrap already created `PellierSTM` and wrote `AGENTCORE_MEMORY_ID` to `.env`.*
:::

## What STM is doing here

**Short-term memory (STM)** holds the last turns of a session — Marco's
questions, the agent's answers, in order. AgentCore Memory stores those
events; the Boutique also mirrors each dispatcher turn into the same
namespace so you can read history from one API.

Namespaces (demo mode):

- `anon:{session_id}` — anonymous shoppers (this session)
- `user:{cognito_sub}:session:{session_id}` — after sign-in (re:Invent workshop)

---

## 1 · Confirm memory is provisioned

```bash
cd /workshop/sample-pellier-agentic-search-apg
grep AGENTCORE_MEMORY_ID pellier/backend/.env
```

You should see a non-empty memory id. If it's blank, STM falls back to an
in-memory dict — tell your table lead.

---

## 2 · Create two turns in the Boutique

1. Open the **Boutique** tab and the chat drawer (`⌘K` / **Ask Pellier**).
2. As **Marco**, click pill 1 (*linen for Goa*) — wait for the answer.
3. Click pill 3 (*price range for linen shirts*) — wait for the answer.

Each completed turn is appended to STM under your session id.

---

## 3 · Read session history from the API

Open browser DevTools → **Application** → **Local Storage** on the Boutique
origin → copy **`pellier-session-id`**, then in Code Editor terminal:

```bash
SESSION="<paste-session-id-here>"
curl -s "http://localhost:8000/api/agent/session/${SESSION}" | python3 -m json.tool
```

**Look for:** a `turns` array with at least four entries (two user, two
assistant) from the pills you clicked. Order matters — STM is a timeline,
not a summary.

---

## 4 · Continuity check (reload)

1. Hard-refresh the Boutique tab.
2. Open the chat drawer again — greeting plus hydrated history from STM
   (if localStorage was empty except the greeting).

**Teaching point:** STM is **session-scoped** and **bounded** (30-day expiry
on the AgentCore resource). It's cheap to read on every request; long-term
taste still lives in Aurora pgvector (Atelier **Memory** orbit).

---

## See in the Atelier

Click **Memory** in the sidebar. The orbit is illustrative; the API you just
called is the operational source of truth.

[Part II · AgentCore Runtime →](/21-agentcore-runtime/)
