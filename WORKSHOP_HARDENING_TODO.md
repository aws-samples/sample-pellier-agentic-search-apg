# Pellier — Roadmap & Hardening

This repo ships a **60-minute Level 400 Builder's Session**. A **2-hour
re:Invent expansion** is planned that up-levels it from "demonstrate agentic
search" to "**operate, debug, and govern** agentic search like a real search
team." This doc is the forward-looking backlog for that expansion, plus the
production-hardening track that rides alongside it.

> Source of truth for what's *currently built* is the code and
> `content/`. This doc is intentionally about what's **next**.

---

## Shipped (60-min Builder's Session)

The current session is hardened and stable. In brief, already done:

- One-build flow (`floor_check`) + one-SELECT recovery (`tool_audit`),
  systemd backend with live reload, resilient bootstrap, post-boot health
  gate + dry-run, model-access preflight.
- **Embeddings: Cohere Embed English v3** (`cohere.embed-english-v3`),
  **Rerank: Cohere Rerank v3.5** (`us.cohere.rerank-v3-5:0`), chat on Claude
  Opus 4.6 / routing on Haiku 4.5. Aurora PostgreSQL 17.9 + pgvector 0.8.0.
- Content: references appendix, tip taxonomy, exercise table, run-of-show.

If you're hardening the 60-min session specifically, the only standing gate
is the pre-event smoke test (see **Pre-event checklist** at the bottom).

---

## re:Invent 2-hour expansion — the thesis

The 60-min session proves *agentic search leaves evidence*. The 2-hour
version proves you can **operate** it: choose the right retrieval strategy
per query, never silently violate a hard constraint, measure quality with
real metrics, tune Aurora indexes with feedback, and govern tool/identity/
memory behavior. Same Boutique/Atelier grammar, same Aurora + Bedrock +
AgentCore stack — more depth, more hands-on, search still the star.

**Guardrails for scoping the 2-hour version:**
- Search-on-Aurora stays the hero. AgentCore deepens but does not take over.
- Every new module needs a *visible* payoff in the Atelier (the evidence loop).
- Prefer "make the existing pipeline visible/tunable" over "add net-new infra."
- Keep a synced floor (everyone finishes the core) + stretch ceiling (experts).

---

## Expansion backlog (curated, highest-signal first)

Each item notes: **why it's 400-level**, **build size** (S/M/L for a 2hr
budget), and **whether it extends existing code** or is net-new.

### A. Search Strategy Router + Search Ladder  ·  build: M  ·  extends existing
The session already runs 4 strategies (vector / hybrid RRF / hybrid+rerank /
agentic). Promote that into a first-class `SearchStrategyRouter` that *chooses*
per query shape, and surface an **Atelier "Search Ladder"** showing the query
moving through extract → embed → vector + FTS → RRF → validate → rerank, with
per-stage latency. **400-level:** strategy selection as an architectural
decision, not a slogan. **Exercise:** participant adds one routing rule
(e.g. exact-identifier → lexical) and watches the ladder change.

### B. Candidate Lens (rank-movement view)  ·  build: S  ·  extends existing
Show how one product moved: `vector rank 8 → FTS 3 → RRF 2 → rerank 1`. The
most visceral way to prove "rerank earns its cost." Read-only over data the
pipeline already produces. **400-level:** makes ranking debuggable.
*(This is also a candidate cosmetic enhancement for the 60-min session.)*

### C. Hard-constraint correctness layer  ·  build: M  ·  extends existing
Add an explicit candidate-validation stage after generation, before rerank:
price/stock/size/material/category checked, violations labeled, never
silently relaxed. **400-level:** the trust boundary of semantic search —
"plausible but wrong" is the #1 production failure. **Exercise:** participant
adds a `quantity > 0` validator and watches an out-of-stock candidate get
filtered (or labeled "closest match, slightly over budget").

### D. Search Quality Lab / Eval Studio  ·  build: L  ·  partly exists (evals spike landed)
Golden query sets (vibe / exact / price-constrained / typo / persona /
adversarial) + offline metrics (Recall@K, MRR, NDCG@K, zero-result rate,
hard-constraint-violation rate, rerank lift) + a Failure Explorer. Wire to
the AgentCore Evals sidecar already spiked. **400-level:** quality governed
by numbers, not vibes. **Exercise:** run an eval set across two strategies,
read the regression.

### E. Aurora Index Tuning Workbench  ·  build: L  ·  extends existing
Interactive `ef_search` / `k` / RRF-constant / `rerank_top_n` / iterative-scan
controls with `EXPLAIN ANALYZE`, buffers, p50/p95/p99, and **result-drift**
(ef=20 vs ef=80: which top-10 changed). **400-level:** the recall/latency
tradeoff made tangible — the most "Aurora-star" module. **Exercise:** tune to
hit a p95 target without dropping recall@10 below a threshold.

### F. Query understanding made visible  ·  build: S  ·  extends existing
The agentic pipeline already emits `{categories, tags, price_max, in_stock,
soft_signal}` via Haiku-extract. Surface the parsed JSON + a "which field was
used in SQL vs vector vs FTS vs rerank" table. **400-level:** demystifies the
query-understanding step. *(Also a 60-min cosmetic candidate.)*

### G. "Why this result?" + memory-aware ranking  ·  build: M  ·  extends existing
Boutique drawer: constraint pass/fail badges + signal summary (semantic /
lexical / rerank / memory boost) + anonymous-vs-personalized compare + a
"trace in Atelier" deep link. **400-level:** explainability + the
personalization contribution to rank. *(Drawer is a 60-min cosmetic candidate.)*

### H. Multi-vector product representation  ·  build: L  ·  net-new
`product_vectors` table: separate title / attribute / review / image / use-case
embeddings, late-fusion scoring. **400-level:** the frontier of commerce search
— one embedding collapses too many meanings. **Heavy** — likely a "show, don't
build" module even at 2 hours.

### I. AgentCore governance, made visible  ·  build: M  ·  extends existing
Tool source (local / Gateway / MCP), identity propagation, Cedar policy
decision, allowlist match, memory r/w, trace ID — all in one Atelier panel.
Plus a production-mode switch (in-process ↔ Gateway ↔ hybrid fallback).
**400-level:** governance as a first-class operational concern.
**Observe-heavy** by design (keeps AgentCore from eating the clock).

### J. Full trace replay + candidate lens  ·  build: L  ·  net-new
Persist a `search_trace` per query; replay with overrides (different strategy,
no rerank, no personalization, stricter filters). **400-level:** reproducible
search debugging. Pairs with B.

---

## Production-hardening track (rides alongside)

These are the "now teach the path to production" items. Good as a final
2-hour module *or* as appendix reading. Grouped by surface.

### Aurora
- Row-level security for tenant/customer data; read-only search role vs
  writer role for inventory/orders.
- `pg_stat_statements` + slow-query capture; query-timeout policy.
- Connection-pool sizing; embedding-dimension guard; index-bloat monitoring.
- Migration drift checks; backup/restore playbook.

### Bedrock
- Model-access preflight (done in 60-min) → region-aware model/profile
  resolver + fallback model chain.
- Rerank timeout fallback; embedding model/version provenance on each row.
- Latency + cost dashboards; prompt/response redaction in logs.

### AgentCore
- Gateway authorization policies; tool allowlist by role/session/persona.
- Identity-propagation checks; trace correlation across Runtime / Gateway /
  Memory / backend.
- Tool-result schema validation; human approval for risky tools; eval gate
  before deploy.

### App
- Rate limits; cost guardrails; PII redaction; feature flags.
- Search/memory/tool audit ledger (60-min has `tool_audit` — generalize it).
- Canary rollout + A/B + offline eval gate before strategy promotion.

---

## Suggested 2-hour module shape (one way to assemble the above)

| Block | Minutes | Modules | Floor (everyone) | Ceiling (experts) |
|---|---|---|---|---|
| Act I — Retrieve | 30 | A, B, F | wire one routing rule | add a strategy + read the ladder |
| Act II — Validate & Measure | 30 | C, D | add `quantity>0` validator | run an eval set, read NDCG delta |
| Act III — Tune Aurora | 30 | E | hit a p95 target | beat recall@10 baseline |
| Act IV — Govern | 20 | G, I | toggle personalization off | inspect a Cedar denial trace |
| Close | 10 | J + hardening read | replay one trace | — |

Net-new infra (H, J full, Eval Studio UI) are the long poles — stage them as
"show, don't build" if the 2-hour budget tightens.

---

## Data-model additions the expansion implies

`search_traces`, `search_eval_sets`, `search_eval_cases`,
`search_strategy_profiles`, `product_vectors` — schemas sketched in the
design-review docs. Add behind migrations `012+`, gated so the 60-min path
never touches them.

---

## Pre-event checklist (applies to BOTH sessions)

- [ ] **Smoke-test provision**: fresh account → `scripts/dry-run-builders.sh`
  green end-to-end (backend up, catalog 40, warehouse present,
  `AGENTCORE_MEMORY_ID` populated, Marco Turn 4 → BK-01, `tool_audit` row).
- [ ] **Confirm AgentCore Memory** is available in the event account/region —
  the health gate hard-requires `AGENTCORE_MEMORY_ID`.
- [ ] **Verify Bedrock model access** for Embed English v3 + Rerank v3.5 +
  Claude Opus 4.6 / Haiku 4.5 in the event region (`check_model_access.py`).
- [ ] **Pin the live Beeswax/warehouse numbers** for the run-of-show success
  check: `psql` the seeded DB for BK-01 Beeswax quantity pre- and
  post-shipment-UPDATE, and make the run-of-show metric match observed data
  (see content fix note).
