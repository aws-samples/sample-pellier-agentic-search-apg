# Lab content audit — memory model + Aurora schema changes

Two changes need to land in the golden lab content, CFNs, contentspec, and IAM policies:

1. **Memory model**: STM/LTM (two tiers) → working / semantic / episodic / procedural (four substrates).
2. **Aurora schema**: every table is now under `pellier.*`. `customer_episodic_seed` and `returns` were moved out of `public` via `ALTER TABLE ... SET SCHEMA pellier`. The migrations (`003_persona_seed.sql`, `005_theo_returns.sql`) already contain idempotent relocation blocks; they just need to be re-run on any cluster that was seeded before the move.

---

## Status as of 2026-05-25 (Workshop Studio repo)

| § | Topic | Status |
|---|---|---|
| 1 | Memory model — STM/LTM → 4 substrates | ✅ **Landed.** 8 content files updated; `01-agentcore-memory-stm/` renamed to `01-memory-substrates/` via `git mv`; procedural-memory honesty callout added; Atelier README image caption updated for the 4-panel viewer. |
| 2 | Aurora schema — `public.*` → `pellier.*` | ✅ **Landed.** No `public.*` references in any markdown/CFN/IAM/contentspec — every snippet was already `pellier.`-qualified before this pass. **Open one-liner:** `search_path` on the Aurora cluster parameter group is unset (Aurora default is `'$user', public`); off-script unqualified `psql` queries against `tool_audit` etc. would fail. Cheap insurance: add `search_path = '"$user", pellier, public'` to the `ClusterParameterGroup` in `assets/pellier-database.yml`. Every shipped snippet qualifies its tables, so this only matters for ad-hoc terminal queries. |
| 3 | Verification checklist | ✅ Run on Workshop Studio repo — all green. |
| 4 | Frontend changes already shipped | ℹ️ Source-repo only; flagged for awareness, no carry-over needed. |
| 5 | Drop `_MUTATING_TOOLS` filter | ✅ **Landed.** 7 edits across `02-agentcore-runtime/index.en.md` (including reframing §4 as a smoke test, not a "zero rows" demo) + `when-things-misbehave` row + two takeaway questions. |
| 6 | Logging accuracy (Dispatcher `specialist=`) | ✅ **Done by default** — audit confirmed no markdown refs to update. |
| 7 | `style_match` three live bugs | ✅ **Source-repo backend only.** No lab snippet showed the broken SQL. |
| 8 | Inner-specialist tools don't audit | ✅ **Resolved in source repo (this commit).** See §9 below. Pattern I → Pattern III parity for procedural memory. The "Pattern III complete; Pattern I partial" honesty note was added to `content/20-act-2-the-ledger/01-memory-substrates/index.en.md` in the Workshop Studio repo as a hedge until propagation merged — that note can now come out (or stay as historical context, since the gap is real until the source-repo build is cut). |
| 9 | Turn 5 escalation (`escalate_to_stylist`) wiring | ⚠️ **One-line builder fix needed in Workshop Studio repo.** Source repo is fully aligned — `PERSONA_HERO_PILLS`, `PERSONA_TURN_TRACES`, three Turn 5 fixtures (`session-marco-capstone.json` / `session-anna-housewarming.json` / `session-theo-home-not-wardrobe.json`), `sessions.json` index, and `persona-turn-alignment.test.ts` (3 tests pass) all carry the new escalation strings. The Marco capstone section in `01-meet-marco/index.en.md` is also already on the new copy. **Stale line to fix upstream:** `content/10-act-1-the-boutique/02-wire-floor-check/index.en.md:221` says *"Turn 5 (`style_match`) already worked"* — wrong on two counts (Turn 5 is `escalate_to_stylist`, and `style_match` is Turn 2). Replace with: *"Turns 1–3 (`find_pieces`, `style_match`, `price_intelligence`) and Turn 5 (`escalate_to_stylist`) already worked; this change isolated and fixed the stock-specific path."* No source-repo edit needed (builder markdowns are owned upstream). |
| 10 | Tool count drift — "twelve tools" → 13 | ⚠️ **Three builder markdowns + one Atelier strip line need upstream fixes.** Source-repo backend has had 13 `@tool` functions for some time (`find_pieces`, `find_pieces_hybrid`, `explore_collection`, `side_by_side`, `style_match`, `whats_trending`, `price_intelligence`, `floor_check`, `running_low`, `returns_and_care`, `restock_shelf`, `process_return`, `escalate_to_stylist`); fixture `tools.json` already lists all 13. **Stale lines upstream:** (a) `content/10-act-1-the-boutique/index.en.md:109` says `12/12 tools shipped`; should read `13/13 tools shipped → floor_check has a sage "Shipped" pill` (or `12/13 → 13/13` if pre-exercise). (b) `content/10-act-1-the-boutique/02-wire-floor-check/index.en.md:23` says `(11/12 → 12/12 shipped)`; should read `(12/13 → 13/13 shipped)`. (c) Same file line 176 `progress strip read 11/12 shipped` → `12/13 shipped`. (d) Same file line 179 `12/12 shipped` → `13/13 shipped`. (e) Same file line 190 collapsed-block heading `If the strip still says 11/12` → `12/13`. (f) `content/90-appendix/01-the-cast/index.en.md:9` says `five specialists, twelve tools, three skills, and three personas` → `…thirteen tools…`. (g) Same file line 54 `## The twelve tools` heading → `## The thirteen tools`. (h) Same file lines 62–75 — table is missing `escalate_to_stylist` row. Add: `| \`escalate_to_stylist\` | Style Advisor, Curator, Experience Guide | session memory | Hand off to a real stylist when the shopper asks for human help |`. (i) Same file lines 77–79 `internal cart.holds capability used for cart bookkeeping` is correct framing (it really is a memory namespace, not a tool), so leave the prose. The sentence already says "not a customer-callable tool, so it doesn't appear in the discovery registry" — accurate. **Source-repo fixes shipped separately** (see §11–§13 below). |
| 11 | Atelier Tools surface count drift (source repo) | ✅ **Source-repo fix needed.** `pellier/frontend/src/atelier/surfaces/understand/Tools.tsx:1240` eyebrow says `twelve functions` → should be `thirteen functions`. Same file line 1242 summary says `Twelve tools in the registry. Eleven ship as reference` → should be `Thirteen tools in the registry. Twelve ship as reference`. The strip itself derives counts from the fixture, so it already renders 13 segments correctly; only the eyebrow + summary copy is stale. |
| 12 | Atelier Agents surface model drift (source repo) | ✅ **Source-repo fix needed.** `Agents.tsx:734` eyebrow `Understand · Agents · five peers · all Opus 4.6 · 0.2` is wrong on two counts: Value Analyst + Stock Keeper run on Haiku 4.5, and per-agent temperatures are 0.4/0.4/0.1/0.0/0.2 (not all 0.2). Same file line 509 RelatedCard prose `the other two patterns use a Haiku 4.5 router` conflates SkillRouter with the routing patterns. `agents.json` fixture has matching drift on 4 of 5 rows (model wrong on Value Analyst + Stock Keeper; temperature wrong on Style Advisor, Curator, Stock Keeper). |
| 13 | Architecture detail-page numeral / category drift (source repo) | ✅ **Source-repo fix needed.** Six of the eight detail pages hardcode numerals and categories that disagree with `architecture.json`. Affected: `SkillsDetail` (category `workshop` → `live`), `StateDetail` (numeral `V` → `IV`), `RuntimeDetail` (numeral `VI` → `V`, category `optional` → `workshop`), `EvaluationsDetail` (numeral `VIII` → `VI`), `ToolRegistryDetail` (numeral collides with StateDetail; orphaned from the 6-entry index grid), `McpDetail` (numeral `VII`, orphaned from grid). |
| 14 | Tool registry "9 tools" stale copy (source repo) | ✅ **Source-repo fix needed.** `agentcore_gateway.py:6/25/38`, `tool_registry.py:11`, `seed_tool_registry.py:4/23`, `test_tool_registry.py:254`, `test_gateway.py:158` all say "9 tools" — `GATEWAY_TOOL_NAMES` actually has 10 entries (added `style_match`). Note: gateway exposes 10 of the 13 backend `@tool` functions (skips `find_pieces_hybrid`, `process_return`, `escalate_to_stylist`); this is the gateway-vs-backend asymmetry, not a bug. |
| 15 | README "12 @tool functions" + lists `cart.holds` as a tool | ✅ **Source-repo fix needed.** `README.md:48` claims `5 specialists × 12 @tool functions`; line 204 says `12 @tool functions across the agent set:`; lines 206–209 list omits `find_pieces_hybrid` + `escalate_to_stylist` and includes `cart.holds`. `cart.holds` is a memory namespace, not a `@tool`. |

**Open items not in any section:**
- `atelier-memory.png` still needs re-screenshotting against the live 4-panel viewer once the source-repo frontend ships. (Image task, not content.)
- `search_path` parameter-group hardening — see §2 row above.

---

## 1. Memory model — STM/LTM → 4 substrates

The new model:

| Substrate | Storage | Lifetime | Write cadence |
|---|---|---|---|
| **Working** | AgentCore Memory session turns under `user:{id}:session:{sid}` (or `anon:{sid}`) | Last K turns | Every turn |
| **Semantic** | AgentCore Memory KV under `user:{id}:preferences` | Durable | When customer tells us something stable |
| **Episodic** | Aurora `pellier.customer_episodic_seed` today; `pellier.orders` + `pellier.returns` are the real per-customer ledger | Durable | When the turn earns the latency |
| **Procedural** | Aurora `pellier.tool_audit` aggregate | Append-only | After every mutating tool call |

Honest gap to call out in lab content: `tool_audit` schema today captures `latency_ms` on mutating tools only. Adding `intent`, `persona_id`, and `success` columns is the next ticket — procedural memory is currently a **sketch over a partial schema**, and the workshop should be honest about that.

### Files that still teach STM/LTM and need rewriting

| File | What's stale | What to teach instead |
|---|---|---|
| `lab-content/workshop/10-module1-observe.en.md:84` | "STM + LTM orbit" framing | Drop orbit. Teach 4 substrate panels with provenance pills (live / fixture / sketch). |
| `lab-content/workshop/99-wrap-up.en.md:20` | "Long-Term Memory (LTM) — preference learning" | "Semantic memory — durable preferences in AgentCore Memory KV. Episodic memory — per-customer events in Aurora." |
| `lab-content/workshop/99-wrap-up.en.md:31` | "Wire LTM next" | "Wire procedural memory — add `intent` / `persona_id` / `success` columns to `pellier.tool_audit` and aggregate them." |
| `lab-content/workshop/static/pellier-labs.yml:101` | "verify STM" | "verify working memory (session turns) reads back through `/api/agent/session/{id}`" |
| `lab-content/builders/index.en.md:45,57,72,90` | STM-only framing of Act II | Teach all four substrates; STM-only readback exercise becomes the "working memory" entry point but mention the other three are wired and visible in the Atelier. |
| `lab-content/builders/10-act-1-the-boutique/01-meet-marco/index.en.md:22,29,41` | "long-term taste memory" / "session-scoped STM" two-tier dichotomy | Replace with the 4-substrate model. Marco's "linen, warm neutrals" come from **semantic** memory; his recent Lisbon-trip browsing rows come from **episodic** memory; the live conversation is **working**; the orchestrator's tool choice is shaped by **procedural**. |
| `lab-content/builders/10-act-1-the-boutique/03-prove-rerank/index.en.md:279` | "Act II · AgentCore Memory (STM)" CTA | "Act II · Memory, four substrates" |
| `lab-content/builders/20-act-2-the-ledger/index.en.md:9,27,38,56,80,82,92,100,101,122` | Whole act framed as "STM only" | Reframe Act II as: **working memory** (the readback exercise) **plus a tour of the other three** (semantic via `get_user_preferences`, episodic via `pellier.customer_episodic_seed`, procedural via `pellier.tool_audit`). The hands-on exercise stays on working memory; the other three become "see this in the Atelier" callouts. |
| `lab-content/builders/20-act-2-the-ledger/01-agentcore-memory-stm/` (directory + file) | Path is `01-agentcore-memory-stm/`; everything inside teaches STM/LTM dichotomy | Rename directory to `01-agentcore-memory-working/` (or `01-memory-substrates/`). Rewrite the page around the 4-substrate model. The persistence-on-reload exercise still works for working memory — keep it as the hands-on, but reframe the final table from "STM vs. long-term taste" into the 4-row substrate table above. |
| `lab-content/builders/30-act-3-the-concierge/02-mcp-and-knowledge-bases/index.en.md:178` | "generate → STM → managed Runtime" diagram | "generate → working memory → managed Runtime" (or just say "memory") |
| `lab-content/builders/static/introduction/README.md:12` | Image caption: "Atelier · Memory orbit — persona at centre, STM inner ring, LTM outer ring" | "Atelier · Memory — four substrate panels (working / semantic / episodic / procedural) with live-vs-fixture provenance pills" — and re-shoot `atelier-memory.png` since the orbit is gone |
| `lab-content/builders/90-appendix/04-your-stack/index.en.md:26` | The "two-tier" model line refers to Opus/Haiku, not memory — this is **fine**, keep it. | (no change) |

### Image asset to re-capture

- `lab-content/builders/static/imgs/atelier-memory.png` (caption noted above) — the surface is now a 4-panel substrate viewer, not an orbit. Re-screenshot from `/atelier/architecture/memory` after the frontend ships.

---

## 2. Aurora schema — `public.*` → `pellier.*`

Two tables moved schemas:

- `public.customer_episodic_seed` → `pellier.customer_episodic_seed` (FKs preserved)
- `public.returns` → `pellier.returns` (FKs preserved)

The migrations already do this idempotently. The relocation blocks live at the top of:

- `scripts/migrations/003_persona_seed.sql:32-44`
- `scripts/migrations/005_theo_returns.sql:39-51`

If a cluster was seeded before these blocks landed, re-running the migrations performs a one-time `ALTER TABLE ... SET SCHEMA pellier` and then the rest is a no-op (`CREATE TABLE IF NOT EXISTS` / upserts). **Confirmed working: ran against the live Aurora cluster in the working repo; 11 episodic rows + 8 returns rows preserved.**

### CFN / IAM / contentspec changes

| Surface | What to check | Why |
|---|---|---|
| **CFN — Aurora bootstrap** | If any migration ordering or `CREATE TABLE` references `public.customer_episodic_seed` or `public.returns`, switch to `pellier.*`. The migration's `IF NOT EXISTS` guards in `pellier.*` will keep fresh deploys idempotent. | Fresh CFN deploys will land tables in `pellier.*` directly via the migrations; the `ALTER TABLE` blocks become no-ops on first run. |
| **CFN — IAM policy for the app role** | If the policy lists tables explicitly, add `pellier.customer_episodic_seed` / `pellier.returns` and remove any `public.*` grants for these. If it grants `pellier.*` already, no change needed. | Otherwise the app gets `permission denied` on `customer_episodic_seed` / `returns` after the move. |
| **CFN — RDS/Aurora parameter group** | `search_path` setting — if it's `'$user', public`, attendees who don't qualify table names will hit "table not found" once everything moves to `pellier`. Either keep `public` in the search path (cheap), or set `search_path = '$user', pellier, public` so unqualified queries resolve to `pellier.*` first. | The lab contentspec teaches schema-qualified names everywhere now; recommend `pellier, public` order so legacy unqualified queries still resolve to the canonical schema. |
| **Contentspec — psql snippets** | Anywhere a snippet runs an unqualified `INSERT INTO returns` / `FROM customer_episodic_seed`, qualify it with `pellier.`. | Already fixed in the working repo at: |
| | | - `lab-content/workshop/20-module2-understand.en.md:247` — three writes line |
| | | - `pellier/frontend/src/atelier/fixtures/session-theo-ceramics-return.json` — two SQL strings |
| | | - `pellier/frontend/src/atelier/surfaces/understand/WritePath.tsx:175-179` — three-write transaction display |
| **Contentspec — `psql` examples in builder content** | `lab-content/builders/20-act-2-the-ledger/01-agentcore-memory-stm/index.en.md:113` already uses `pellier.customer_episodic_seed`. **Verify this matches in the master repo.** | If the master repo is older, this snippet may still say `customer_episodic_seed` unqualified — would fail after the move. |

### IAM policy specifics

The app role needs (replace `<schema>` with `pellier`):

```
SELECT, INSERT, UPDATE on pellier.customer_episodic_seed
SELECT, INSERT on pellier.returns
SELECT on pellier.orders, pellier.customers, pellier.product_catalog, pellier.return_policies, pellier.tools
INSERT on pellier.tool_audit
USAGE on schema pellier
USAGE on all sequences in schema pellier   -- for BIGSERIAL on returns + customer_episodic_seed
```

Drop any explicit grants on `public.customer_episodic_seed` or `public.returns` (the relocation moved the underlying objects; the names no longer resolve).

---

## 3. Quick verification checklist for the master repo

After applying the changes:

- [ ] `grep -rn "STM\|LTM" lab-content/` returns only intentional historical references (Opus/Haiku two-tier in `90-appendix/04-your-stack/`).
- [ ] `grep -rn "public\.customer_episodic_seed\|public\.returns" .` returns only the relocation blocks in `scripts/migrations/003_persona_seed.sql` and `scripts/migrations/005_theo_returns.sql`.
- [ ] `grep -rn "INSERT INTO returns\|INSERT INTO customer_episodic" .` returns no unqualified writes outside the migration files.
- [ ] CFN deploys to a fresh cluster land tables in `pellier.*` and the app role can read/write them.
- [ ] `atelier-memory.png` is re-captured against the 4-panel viewer.

---

## 4. Frontend changes already shipped (working repo)

These are done in `sample-pellier-agentic-search-apg` and don't need carrying over manually if you're cherry-picking, but flagging for awareness:

- `pellier/frontend/src/atelier/types/memory.ts` — full type rewrite to 4-substrate model
- `pellier/frontend/src/atelier/types/index.ts` — exports `MemorySubstrate`, `MemorySubstratePanel`, `MemorySource`
- `pellier/frontend/src/atelier/surfaces/understand/architecture/MemoryDetail.tsx` — dropped orbit, 4-panel viewer with provenance pills
- `pellier/frontend/src/atelier/surfaces/understand/MemoryDashboard.tsx` — same shape, persona switcher
- `pellier/frontend/src/atelier/fixtures/architecture.json` — Memory card (II) rewritten for 4 substrates
- `pellier/frontend/src/atelier/fixtures/memory-{marco,anna,theo}.json` — all three on the 4-substrate shape
- `pellier/backend/routes/atelier_observatory.py` — `/memory/{persona}` populates all 4 substrates with live overlay where possible

---

## 5. tool_audit — drop the `_MUTATING_TOOLS` filter

Procedural memory's aggregate over `pellier.tool_audit` was returning a single row (`process_return - fired 7x`) on a typical browse session because the policy hook only audited mutating tools. That kept Theo's "agents that write state with a paper trail" demo clean but starved every other persona's procedural panel. Procedural memory needs **which tool wins for which intent at which latency** — and that requires reads in the table too.

The gate is now gone. Every ALLOWed tool call (read + write) writes a row; DENY decisions still skip audit (the tool didn't run) and live in the in-memory decision deque instead.

### Files that still teach "mutations only" and need updating

| File | What's stale | What to teach instead |
|---|---|---|
| `lab-content/workshop/20-module2-understand.en.md:280` (working repo: already updated) | "Open `services/policy_hook.py`. Find `_MUTATING_TOOLS` (around line 60)" | The set is gone. Teach: "every `ALLOW` (mapped or unmapped, read or write) calls `tool_audit_writer.record_allow` in `BeforeToolCallEvent` and `record_after` in `AfterToolCallEvent`. DENY skips audit because the tool never ran." |
| `solutions/the-ledger/sql/tool_audit_recap.sql:1-13` (working repo: already updated) | Header says "Why mutations only: services/policy_hook.py:75 audits `_MUTATING_TOOLS`..." | "Every ALLOWed tool call writes a row — reads and writes alike — so a typical browse session shows `find_pieces`, `floor_check`, etc. alongside any `process_return`/`restock_shelf` mutations." |
| `scripts/migrations/002_workshop_telemetry.sql:121-125` (working repo: already updated) | "One row per mutating tool invocation (`_MUTATING_TOOLS = {restock_shelf, process_return}`)" | "One row per ALLOWed tool call — reads and writes alike. DENY decisions skip audit and live in policy_hook's per-session decision deque." |
| Any contentspec / lab snippet that says "tool_audit captures mutations" or "process_return writes a row" without mentioning reads | Implies a partial table | Teach: every ALLOWed call writes. The `tool` column distinguishes reads from writes if you want a mutations-only view (`WHERE tool IN ('process_return','restock_shelf')`). |
| Image asset: any screenshot of the procedural panel with one row | Stale post-change | Re-screenshot from `/atelier/architecture/memory` after a Marco browse turn — you'll see `find_pieces` + `style_match` rows alongside any prior `process_return` aggregates. |

### Backend code change (already shipped in working repo)

- `pellier/backend/services/policy_hook.py` — dropped `_MUTATING_TOOLS`; refactored `_on_before_tool` so the audit INSERT fires on every ALLOW (mapped or unmapped). Added `_begin_audit` helper. Fail-open path now also audits.
- `pellier/backend/services/tool_audit_writer.py` — header docstring no longer says "every mutation"; says "every tool call".
- `pellier/backend/routes/atelier_observatory.py` — procedural caveat updated; `/memory/{persona}` docstring updated.
- `pellier/frontend/src/atelier/fixtures/memory-{marco,anna,theo}.json` — caveats updated.
- `pellier/frontend/src/atelier/surfaces/understand/architecture/MemoryDetail.tsx` — cheat-sheet entry + procedural tier prose updated.
- `pellier/backend/tests/test_policy_hook.py` — two tests inverted (`test_read_only_allow_audits` was previously `_does_not_audit`); one new test for unmapped tools (`test_unmapped_tool_audits_without_policy_evaluate`). 12 tests pass.

### Verification

After the change, on a fresh browse turn for Marco:

```sql
SELECT tool, count(*), round(avg(latency_ms))::int AS avg_ms
  FROM pellier.tool_audit
 GROUP BY tool
 ORDER BY count(*) DESC;
```

Should show `find_pieces`, `style_match`, etc. alongside `process_return`. The procedural panel in `/atelier/architecture/memory` will show all of them with `Live` provenance.

---

## 6. Logging accuracy — Dispatcher log used intent slug instead of agent name

The Dispatcher log line was emitting `🎯 Dispatcher | specialist=search` — but `search` is the **intent slug**, not the specialist agent's display name. The actual specialist for that intent is **Style Advisor**. The mapping (already present in `chat.py:_tool_to_agent_name`) is:

| Intent | Specialist agent (display name) |
|---|---|
| `search` | Style Advisor |
| `recommendation` | Curator |
| `pricing` | Value Analyst |
| `inventory` | Stock Keeper |
| `support` | Experience Guide |

The log now reads:

```
🎯 Dispatcher | specialist=Style Advisor (intent=search)
```

The same fix landed on the STUBBED-specialist branch a few lines above. No lab-content references to grep — the log line wasn't quoted in any markdown today — but worth flagging for the master repo so any screenshots taken with the old log get retaken. If the master repo has identical log surfaces in screenshots, re-capture.

### Backend code change (already shipped in working repo)

- `pellier/backend/services/chat.py:2058-2062, 2124-2127` — both Dispatcher log lines now resolve `intent_hint → specialist display name` via the existing `_tool_to_agent_name` helper, and emit both fields so the intent is still grep-able.

---

## 7. `style_match` — three live bugs against `pellier.product_catalog`

The Style Advisor's `style_match` tool errored on every call against the real Aurora schema. Three bugs in `pellier/backend/services/agent_tools.py` (the `style_match` body around line 813):

1. **Wrong column name.** SELECTed `category_name` from `pellier.product_catalog`. The actual column is `category` (`category_name` is a different column on `pellier.return_policies`). This was the visible error in the user's log: `ERROR: column "category_name" does not exist`.
2. **Numpy truthiness.** `if not source.get("embedding")` raised `The truth value of an array with more than one element is ambiguous` because pgvector returns embeddings as numpy arrays. Replaced with `emb is None or len(emb) == 0`.
3. **Wrong vector literal format.** `str(numpy_array)` produces `[v1 v2 v3]` (space-separated); pgvector's text I/O wants `[v1,v2,...]` (comma-separated). Without the fix, `embedding <=> %s::vector` fails with `invalid input syntax for type vector`. Replaced with `"[" + ",".join(repr(float(v)) for v in emb) + "]"`.

### Backend code change (already shipped in working repo)

- `pellier/backend/services/agent_tools.py:815-836` — three fixes above. Verified end-to-end: `style_match(22, 3)` now returns 3 cosine-similarity matches with correct `category` field on every row.

### Lab content

No lab snippet shows the broken SQL — the bug was in tool code, not in any teaching doc. But: any screenshot or transcript that shows a "no matches" or "couldn't find pairings" agent response on a `style_match`-style query is now stale. Re-run the demo turn ("What goes with the Hadley shirt?") and re-capture if a screenshot is in lab content.

---

## 8. ~~Open / partial — inner specialist tools don't audit yet~~ → **Resolved (see §9)**

When the orchestrator (Pattern I, agents-as-tools) called a wrapper tool like `recommendation` or `search`, the wrapper instantiated a fresh inner specialist Agent that did **not** carry the `PolicyEnforcementHook`. So the wrapper call showed up in `pellier.tool_audit`, but the specialist's own tool calls (`find_pieces`, `style_match`, etc.) didn't. Visible symptom: the procedural aggregate had rows for `recommendation`, `process_return`, etc., but never for inner tools.

**Fix shipped in §9.** Pattern I procedural memory is now complete; the Workshop Studio "Pattern III complete; Pattern I partial" honesty note can be retired once the source-repo build is cut.

---

## 9. Inner-specialist hook propagation — Pattern I now audits inner tools

Closes §8. Pattern I (agents-as-tools) now writes audit rows for the inner specialist's tool calls (`find_pieces`, `style_match`, …) alongside the wrapper-level call. Procedural memory's per-tool aggregate is complete for both patterns.

### Design

The Pattern I `@tool` wrappers (`search`, `recommendation`, `pricing`, `inventory`, `support`) build a fresh inner specialist Agent each time they're invoked. Their LLM-facing `@tool` signature can't take a `session_id` parameter, so a `ContextVar` threads it through:

- **`pellier/backend/services/session_context.py`** — `session_id_var: ContextVar[Optional[str]]`. Mirrors the pattern used by `services/persona_context.py` and `skills/context.py`. Empty default lets unit tests build inner agents without scaffolding.
- **`pellier/backend/agents/specialist_hooks.py`** — `attach_policy_hook(agent)` reads the var and registers `PolicyEnforcementHook` on the inner agent. Same registration shape as the outer attachment at `services/chat.py:1869-1882`: prefer `agent.hooks.add_hook(provider)` so `register_hooks` runs once; fall back to `agent.add_hook(provider._on_before_tool)` for shims without a registry surface.
- **`pellier/backend/services/chat.py`** — outer chat handler sets/resets `session_id_var` next to the existing persona/skill ContextVars (set after persona, reset in the same `finally` that resets the others). `asyncio.to_thread` propagates the context into the worker thread via `copy_context()`.
- **5 wrappers** — each one calls `attach_policy_hook(agent)` right after the existing `agent.add_hook(capture_result)` line:
  - `agents/style_advisor.py` (`search`)
  - `agents/curator.py` (`recommendation`)
  - `agents/value_analyst.py` (`pricing`)
  - `agents/stock_keeper.py` (`inventory`)
  - `agents/experience_guide.py` (`support`)

### Tests (already shipped)

`pellier/backend/tests/test_policy_hook.py` adds three:
- `test_attach_policy_hook_uses_session_id_from_contextvar` — wraps a fake agent with a `hooks.add_hook` registry, sets the var, asserts `PolicyEnforcementHook` is registered with the right `session_id`.
- `test_attach_policy_hook_falls_back_to_callback_registration` — fake agent with `hooks=None` and a callback-style `add_hook`; asserts the bound `_on_before_tool` callback is registered.
- `test_attach_policy_hook_with_no_session_id_uses_anonymous` — ContextVar unset; provider attaches with `session_id=None`. `record_allow` already tolerates this by writing `"_anonymous"`.

15 hook tests pass. **460 passed, 1 skipped** in the full backend suite.

### Live verification

```sql
SELECT tool, count(*) FROM pellier.tool_audit
 WHERE session_id = 'hook-prop-verify-1'
 GROUP BY tool ORDER BY count(*) DESC;
```

Returns:

```
('find_pieces_hybrid', 3)
('recommendation', 1)
```

Before this fix, the same session would have shown `('recommendation', 1)` only. `find_pieces_hybrid` is the inner Style Advisor tool — now visible to procedural memory.

### Lab content

No lab snippet teaches the broken state, so nothing to rewrite. The Workshop Studio "partial for Pattern I" hedge in `01-memory-substrates/index.en.md` is now historical; either remove it on the next pass or keep it as the dev-history footnote it always was.
