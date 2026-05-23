---
title: "Platform · AgentCore Memory (STM)"
weight: 10
---

:::alert{type="info"}
**Time:** ~6 min  ·  **Page:** 1 of 2 in Act II  ·  **Exercises on this page:** 0

No code to ship — you'll **verify** that short-term memory persists
across turns. Bootstrap already created `PellierSTM` and wrote
`AGENTCORE_MEMORY_ID` to `.env`. **One-hour option:** skim sections 1
and 3 only, then continue to Runtime.
:::

**You'll learn to:**

1. Confirm the platform-provisioned **AgentCore Memory resource** is
   wired by reading `AGENTCORE_MEMORY_ID` from `.env`.
2. Read a session timeline back from `/api/agent/session/{session_id}`
   and recognize it as **an ordered list of turns**, not a summary.
3. Verify **session continuity on page reload** — STM rehydrates
   from the same `pellier-session-id` in Local Storage.
4. Distinguish **session-scoped STM** (cheap, bounded, 30-day expiry)
   from **long-term taste memory** in Aurora pgvector profile
   embeddings.

In this page, "the ledger" means one concrete artifact: the session
timeline returned by `/api/agent/session/{session_id}`.

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
2. Open the chat drawer again. You should still see your prior turns
   because session history rehydrates from STM for the same session id.
   If history is missing, confirm `pellier-session-id` is still present
   in Local Storage, then repeat step 3.

**Teaching point:** STM is **session-scoped** and **bounded** (30-day expiry
on the AgentCore resource). It's cheap to read on every request; long-term
taste still lives in Aurora pgvector (Atelier **Memory** orbit).

---

## 5 · See long-term memory (Aurora) — the second memory system

Where STM is *transient turns*, **long-term memory is durable taste** —
the customer's prior orders, preferences, and episodic facts that
should outlive any single chat. In Pellier those live in two
Aurora-backed tables, queryable from the same `psql` you've been
running:

```bash
psql <<'SQL'
-- Persona-level preferences (the strings the agents read at turn start)
SELECT id, name, preferences_summary
  FROM pellier.customers
 WHERE id IN ('CUST-MARCO', 'CUST-ANNA', 'CUST-THEO');

-- Episodic facts the memory surface returns (most recent first)
SELECT customer_id, ts_offset_days, summary_text
  FROM pellier.customer_episodic_seed
 WHERE customer_id = 'CUST-MARCO'
 ORDER BY ts_offset_days DESC
 LIMIT 5;
SQL
```

**Read the rows out loud at your table.** Marco's "prefers natural
fibers, oat tones, warm neutrals" is the literal context that makes
Turn 1 (*"linen for Goa"*) feel personalized — not a model fine-tune,
just a row.

Where do **vector embeddings** of taste live? In the same
`pellier.product_catalog.embedding` column you've already inspected:
the agents read a customer's order history, then run pgvector cosine
queries against the catalog anchored on those purchases. **One vector
column powers both product search and taste personalization** — that
is the design payoff of putting the catalog in pgvector.

| Memory | Where | Bounded? | Survives session? | TTL |
|---|---|---|---|---|
| **STM (turns)** | AgentCore Memory | Yes (30-day) | No (per-session) | 30 days |
| **Long-term taste** | Aurora `pellier.customers` + `pellier.customer_episodic_seed` | No | Yes | Until you delete |
| **Catalog vectors** | Aurora `pellier.product_catalog.embedding` | No | Yes | Until you re-embed |

---

## See in the Atelier

Click **Memory** in the sidebar. The orbit is illustrative; the API you just
called is the operational source of truth.

---

## What you've learned

- **STM is a timeline, not a summary.** Order matters. The `turns`
  array is what the agent sees on every request.
- **Session continuity is a property of the platform, not your code.**
  A page reload preserves the conversation because the same
  `pellier-session-id` rehydrates from `AGENTCORE_MEMORY_ID`.
- **Two memory systems coexist in one agent.** Session-scoped STM
  (bounded, 30-day expiry) is cheap to read every turn; long-term
  taste lives in Aurora pgvector profile embeddings and survives
  the session.
- **The API is the operational source of truth.** The Atelier orbit
  is illustrative; `/api/agent/session/{id}` is what you'd page on
  in production.

:::alert{type="success" header="Runtime next"}
[Platform · AgentCore Runtime (Demo) →](/20-act-2-the-ledger/02-agentcore-runtime/)
:::
