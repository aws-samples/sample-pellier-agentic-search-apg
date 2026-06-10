# Lab content audit — memory model + Aurora schema changes

Two changes need to land in the golden lab content, CFNs, contentspec, and IAM policies:

1. **Memory model**: STM/LTM (two tiers) → working / semantic / episodic / procedural (four substrates).
2. **Aurora schema**: every table is now under `pellier.*`. `customer_episodic_seed` and `returns` were moved out of `public` via `ALTER TABLE ... SET SCHEMA pellier`. The migrations (`003_persona_seed.sql`, `005_theo_returns.sql`) already contain idempotent relocation blocks; they just need to be re-run on any cluster that was seeded before the move.

---

## Status as of 2026-05-26 (Workshop Studio repo)

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
| 16 | Per-turn memory substrate visibility — fixtures + Sessions surfaces | ✅ **Source-repo fix shipped (this commit).** All 13 session fixtures across the 3 personas now carry `memoryPills` in chat (working / semantic / episodic / procedural / skill, persona-appropriate) and matching telemetry panels (`Memory Recall — Semantic`, `Memory Recall — Episodic`, `Memory Write — Working`); ChatTab `MemoryCard` and TelemetryTab "Memory substrate" column gained per-substrate gloss lines + a `→ What are the four substrates?` cross-link to `/atelier/architecture/memory`; "Memory orbit" terminology renamed to "Memory substrate" across `TelemetryTab.tsx` (3 spots) + `MemoryHandoffCard.tsx` (1 comment). Sequential indexes verified across all 13 fixtures; `sessions.property.test.ts` passes. **Closes the Batch 4 "memory substrate rollup" item.** |
| 17 | AgentCore CLI migration — `bedrock-agentcore-starter-toolkit` (Python) → `@aws/agentcore` (Node) | ⚠️ **Source-repo deploy refactor shipped (this commit); 6 builder markdown lines need upstream fixes.** The Python `bedrock-agentcore-starter-toolkit` (with `agentcore configure` + `agentcore launch`) is being retired; the new canonical CLI is the Node-based `@aws/agentcore` (https://github.com/aws/agentcore-cli) installed via `npm install -g @aws/agentcore`. The runtime SDK (`bedrock-agentcore>=1.4.3`) is unchanged — only the deploy CLI moved. **Source-repo done:** new `pellier/backend/agentcore.json.template` + `pellier/backend/aws-targets.json.template` carry all the config previously passed as CLI flags; `scripts/deploy/deploy_all.sh` step 5–6 now `envsubst`-renders both templates from CFN outputs and runs `agentcore deploy -y --json` (no more `agentcore configure`/`launch`); docstrings updated in `pellier/backend/.bedrock_agentcore.yaml`, `pellier/backend/agentcore_runtime.py`, `scripts/provision_agentcore_runtime.py` (marked deprecated), `scripts/deploy/agentcore_runtime_adapter.py`, and `scripts/deploy/README.md`. **Stale builder markdown lines upstream (Workshop Studio repo):** (a) `lab-content/builders/20-act-2-the-ledger/index.en.md:17, 84` — references to `agentcore configure`/`launch`; (b) `lab-content/builders/20-act-2-the-ledger/02-agentcore-runtime/index.en.md:9, 39, 189, 193, 224` — same. Replace with the `envsubst < agentcore.json.template > agentcore.json && agentcore deploy -y --json` flow. Also bootstrap install line should change from `pip install bedrock-agentcore-starter-toolkit` to `npm install -g @aws/agentcore`. **SDK signature drift fixed in same pass:** `services/agentcore_memory.py:244` now calls `list_long_term_memory_records(namespace=key, max_results=1)` (was `namespace_prefix=key`, deprecated; `memoryId` and `maxResults` were never the right names). `test_agentcore_memory.py::test_get_user_preferences_sdk_path_uses_correct_signature` pin-locks the new spelling. **Italics removal pass:** 42 `fontStyle: 'italic'` removals + 6 `<em>` tag removals across 18 Atelier surface files (Fraunces serif already provides editorial weight; italic on top was redundant). |
| 18 | AgentCore Identity sub-batch — namespace dash-form drift + Production Patterns lifecycle strip | ✅ **Source-repo only — no Workshop Studio carry-over needed.** Two pieces landed in one pass (2026-05-26). **(a) Namespace format drift (real bug):** the canonical AgentCore Memory namespace is `anon-{session_id}` / `user-{cognito_sub}-session-{session_id}` (dashes), because AgentCore session IDs must match `[a-zA-Z0-9][a-zA-Z0-9-_]*` — colons would 400 at the API boundary. The fixture, `chat.py`, `routes/atelier_observatory.py:480` (substrate-scan prefix would have returned zero matches against dash-form keys), 4 docstrings, and the `solutions/the-ledger/services/` mirror all carried colon-form strings (`user:{sub}:session:{id}`). Fixed across 13+ files in one sweep; `services/chat.py` now delegates to `AgentCoreIdentityService.build_namespace(sub, session_id)` so the format lives in one place. **(b) Production Patterns lifecycle strip:** new `wiring` field on `IdentityPattern` (5-step Cognito → namespace lifecycle, each step file-anchored) renders as a numbered strip on the Identity card. Strip pins the request flow: Cognito hosted UI → frontend `AuthContext`/`chat.ts` → outgoing `/api/agent/chat` with Bearer token + session_id → backend `get_verified_user_context` → `build_namespace` handoff to AgentCore Memory. New `surfaces/measure/ProductionPatterns.test.tsx` (6 tests) pins both contracts. 312/312 frontend tests green; 478 backend pass + 1 benign skip. |
| 19 | LangGraph comparison sub-batch — Routing surface comparison card | ✅ **Source-repo only — no Workshop Studio carry-over needed.** New `LangGraphComparisonCard` in `surfaces/understand/Routing.tsx`, rendered after `DispatcherIntentCard`. Three-row mapping table (Dispatcher → conditional edges from a router node; Agents-as-Tools → supervisor pattern with `create_react_agent`; Graph → `StateGraph` with `add_node`/`add_edge`) plus a "when to reach for LangGraph instead" footer pinning the three workflow shapes that justify a graph runtime: durable checkpointing, human-in-the-loop pause/resume, cycle-heavy planner ↔ critic ↔ executor topology. Editorial framing: *"Three patterns, not one graph"* — Strands lets you start with Dispatcher (a Python function) and graduate; LangGraph commits to a `StateGraph` from turn one. New `Routing.test.tsx` (4 tests) pins the rows, the keyword mapping per row, the editorial header, and the footer shapes. 316/316 frontend tests green. **Closes Batch 4.** |
| 20 | AgentCore — Workshop Studio testing guide (Runtime + Gateway + Memory) | 📝 **Reference, not a code change.** Step-by-step verification script for the new `@aws/agentcore` Node CLI flow on a Workshop Studio account: provision Memory (control-plane `create_memory`), run `deploy_all.sh` (4 Lambdas + Gateway + Runtime), wire local backend to live Gateway, observe in-process → MCP tool-discovery flip, cleanup. Documents the failure modes participants hit most often (token expiry, region drift, `iam:PassRole`, `.env` reload) and now reflects the full 13/13 gateway parity from §21. See §20 below. |
| 21 | Gateway parity sub-batch — every backend `@tool` reaches the Gateway | ✅ **Source-repo only — closes the §20 "optional extension".** New `pellier_experience_server.py` Lambda (process_return + escalate_to_stylist), `find_pieces_hybrid` added to the search target's schema, `deploy_gateway.py` gains the `experience` target, `deploy_all.sh` restructured 7 → 8 steps with the new Experience Lambda step, runtime adapter prompt lists the new tools, §20 step list / counts / cleanup loop updated. `GATEWAY_TOOL_NAMES` follow-up still needed in `services/agentcore_gateway.py` + `seed_tool_registry.py` to collapse §14's drift to a single canonical 13. See §21 below. |
| 22 | `@aws/agentcore` 0.18 CLI rework — flat-config deploy → stateful CDK project (SUPERSEDES §17) | ✅ **Source-repo + WS-repo CFN (2026-06-09).** End-to-end provisioning was validated on a real account through 8 sequential fixes (model-invoke IAM for global inference profiles, Lambda function-name lookup, `bedrock-agentcore:*` for `SynchronizeGatewayTargets`, `lambda:GetFunctionConfiguration` re-run idempotency, gateway target-schema sanitizer stripping `default`/`enum`, `bedrock:InvokeModel` on the MCP Lambda exec role, `get-gateway-target --target-id` flag, Node 20). Lambdas + Gateway + all 12 prefixed tools now verify. **Final link — the Runtime deploy — required a CLI rework:** `@aws/agentcore@latest` resolved to **0.18**, which dropped the flat `agentcore.json` + `aws-targets.json` + `envsubst` + `agentcore deploy` contract (the §17 path) in favor of a **stateful, CDK-based** project model (`create --no-agent` → `add agent --type byo` → JSON-patch → `deploy` from the project root). **Changes:** (a) `provision_agentcore_end_to_end.py` — new `_deploy_runtime_via_cli()` (create/add/patch/deploy, pinned `@aws/agentcore@0.18.0`, ARN from `agentcore/.cli/deployed-state.json`), replacing `_render_runtime_templates`; (b) `deploy_all.sh` steps 6-7 mirror it; (c) `bootstrap-environment.sh` installs **Node 20** (NodeSource) + runs **`cdk bootstrap`** (0.18 deploy is CDK-based); (d) `pellier-code-editor.yml` InstanceRole widened for CDK (cloudformation/`cdk-hnb659fds-*` S3+roles+SSM, PassRole to cloudformation); (e) new `pellier/backend/pyproject.toml` (0.18 uses uv, not requirements.txt) carrying the orchestrator's transitive imports; (f) deleted obsolete `agentcore.json.template` + `aws-targets.json.template`; (g) `provision_agentcore_runtime.py` hard-disabled (deprecated, superseded); (h) `test_agentcore_deploy_templates.py` rewritten to pin the NEW contract (8 static tests, green). **Deployed entrypoint = `pellier/backend/agentcore_runtime.py`** (in-process orchestrator, self-contained, no Gateway-egress JWT problem) — NOT the Gateway adapter (which lacks Authorization-header auth to its own CUSTOM_JWT Gateway). **Known external blocker (not infra):** the JWT smoke test's `InvokeAgentRuntime` runs the editorial model, which on fresh accounts may still be in Bedrock Marketplace "subscription processing" — owned by the WS event admin. See §22. |

**Open items not in any section:**
- `atelier-memory.png` still needs re-screenshotting against the live 4-panel viewer once the source-repo frontend ships. (Image task, not content.)
- `search_path` parameter-group hardening — see §2 row above.

---

## 1. Memory model — STM/LTM → 4 substrates

The new model:

| Substrate | Storage | Lifetime | Write cadence |
|---|---|---|---|
| **Working** | AgentCore Memory session turns under `user-{cognito_sub}-session-{sid}` (or `anon-{sid}`) — dashes, not colons; session IDs must match the AgentCore regex `[a-zA-Z0-9][a-zA-Z0-9-_]*` | Last K turns | Every turn |
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

---

## 16. Per-turn memory substrate visibility — fixtures + Sessions surfaces

The Architecture Memory page already taught the 4-substrate model in depth (tier cards, code snippets, provenance pills). But the **per-turn Sessions surfaces** were under-teaching: `marco-opening-demo/telemetry` showed *"No memory operations in this session"* even though the chat referenced semantic preferences and the system was demonstrably writing working memory each turn. Memory was visible in Architecture but invisible in Observe.

### What changed (source-repo only — no Workshop Studio carry-over needed)

**Fixtures — all 13 sessions × 3 personas now have memory operations recorded:**

| Fixture archetype | Fixtures | Memory pattern applied |
|---|---|---|
| Multi-turn opener (Marco linen-Goa) | `session-marco-opening-demo` | Semantic recall before retrieval each turn + Working write after each turn |
| Deterministic lookup (Marco midpoint) | `session-marco-midpoint-checkpoint` | Working write after the lookup |
| Single-turn hybrid+rerank (Anna gifting) | `session-anna-morning-ritual`, `session-anna-under-100` | Semantic recall + Working write |
| Mid-conversation gifting (Anna with episodic context) | `session-anna-candle-pairing`, `session-anna-birthday-gift` | Semantic recall + Episodic recall + Working write |
| Escalation (no catalog tool can answer) | `session-marco-capstone`, `session-anna-housewarming`, `session-theo-home-not-wardrobe` | Working write after `escalate_to_stylist`; episodic + procedural pills where context applies |
| Theo browse (slow-craft retrieval) | `session-theo-pour-over`, `session-theo-pour-over-pairing`, `session-theo-linen-seasons` | Semantic recall (+ Episodic where purchase history loads) + Working write |
| Theo write path (returns) | `session-theo-ceramics-return` | Episodic recall (verifies ownership before write opens) + Working write at end |

**Surfaces:**
- `pellier/frontend/src/atelier/surfaces/observe/TelemetryTab.tsx` — renamed "Memory orbit" → "Memory substrate" (3 spots); added `→ What are the four substrates?` link to `/atelier/architecture/memory` in the column header.
- `pellier/frontend/src/atelier/surfaces/observe/ChatTab.tsx` — `MemoryCard` now carries a one-sentence gloss under each substrate label *("This session's last K turns — read first, written every turn"* etc.) plus the same cross-link in its header.
- `pellier/frontend/src/components/MemoryHandoffCard.tsx` — comment renamed to "Memory substrate explainer".

**Verification:**
- All 13 fixtures parse as valid JSON; telemetry indexes are sequential 1..N.
- `traceLink` / `panel-N` refs all resolve to live indexes.
- `sessions.property.test.ts` passes (2/2).

### Lab content

No Workshop Studio carry-over needed — the Sessions surfaces are source-repo-only. **Closes the Batch 4 "memory substrate rollup" item** in the pending-batches memo.

---

## 17. AgentCore CLI migration + Memory SDK signature fix (Batch 3)

Two pieces of pre-existing drift, both surfacing as warnings before this commit:

1. **`MemorySessionManager.list_long_term_memory_records()` warning** — `unexpected keyword argument 'memoryId'`. The historic `namespace_prefix=` kwarg has been deprecated in favor of `namespace=` (exact match) / `namespace_path=` (hierarchical prefix); `memoryId` and `maxResults` were never the right names. Source-repo fix at `pellier/backend/services/agentcore_memory.py:244` calls the new shape; `test_agentcore_memory.py` pin-locks the spelling so a future SDK bump trips loudly.

2. **`bedrock-agentcore-starter-toolkit` (Python, `agentcore configure`/`launch`) is being retired** in favor of the new Node-based `@aws/agentcore` CLI (https://github.com/aws/agentcore-cli, `npm install -g @aws/agentcore`). The new CLI has NO flag overrides for region / role ARN / JWT config / env vars / entrypoint — everything must be in `agentcore.json` + `aws-targets.json` before `agentcore deploy`. The runtime Python SDK (`bedrock-agentcore>=1.4.3`) is unaffected.

### Source-repo changes (this commit)

| File | Change |
|---|---|
| `pellier/backend/agentcore.json.template` | **New.** Carries `${AGENTCORE_ROLE_ARN}` / `${OAUTH_ISSUER_URL}` / `${COGNITO_CLIENT}` / `${MCP_GATEWAY_URL}` / `${AGENT_MODEL_ID}` placeholders — every value previously passed as a `agentcore configure`/`launch` flag. |
| `pellier/backend/aws-targets.json.template` | **New.** Carries `${AWS_ACCOUNT}` + `${AWS_REGION}` for `agentcore deploy`. |
| `scripts/deploy/deploy_all.sh` step 5/7 + 6/7 | Replaced 9-flag `agentcore configure` + `agentcore launch --env` block with `envsubst < …template` rendering + single `agentcore deploy -y --json` call. New step 5/7 also derives `$AWS_ACCOUNT` via `aws sts get-caller-identity`. |
| `pellier/backend/.bedrock_agentcore.yaml` | Header comment marks file as legacy; notes new flow path. |
| `pellier/backend/agentcore_runtime.py` | Docstring updated to show new deploy invocation. |
| `scripts/provision_agentcore_runtime.py` | Docstring marks the script DEPRECATED; points at `deploy_all.sh`. |
| `scripts/deploy/agentcore_runtime_adapter.py` | Docstring updated to show new deploy invocation. |
| `scripts/deploy/README.md` | Step-by-step deploy refreshed; template files added to the file table. |
| `pellier/backend/services/agentcore_memory.py:244` | `namespace_prefix=key` → `namespace=key`. |
| `pellier/backend/tests/test_agentcore_memory.py:229–268` | Pin-test rewritten to reject the deprecated `namespace_prefix` (and the historic `memoryId`/`maxResults`). |

### Workshop Studio carry-over (builder markdowns — upstream-only)

These six lines reference the deprecated CLI surface; they need replacement with the new flow on the Workshop Studio side. Builder markdowns are not edited from this repo.

| File | Line | Stale ref |
|---|---|---|
| `lab-content/builders/20-act-2-the-ledger/index.en.md` | 17 | "`agentcore configure`" / "`agentcore launch`" |
| `lab-content/builders/20-act-2-the-ledger/index.en.md` | 84 | same |
| `lab-content/builders/20-act-2-the-ledger/02-agentcore-runtime/index.en.md` | 9 | introductory "we'll use the starter toolkit" framing |
| `lab-content/builders/20-act-2-the-ledger/02-agentcore-runtime/index.en.md` | 39 | `agentcore configure` invocation |
| `lab-content/builders/20-act-2-the-ledger/02-agentcore-runtime/index.en.md` | 189 | `agentcore launch` invocation |
| `lab-content/builders/20-act-2-the-ledger/02-agentcore-runtime/index.en.md` | 193 | `pip install bedrock-agentcore-starter-toolkit` install line |
| `lab-content/builders/20-act-2-the-ledger/02-agentcore-runtime/index.en.md` | 224 | wrap-up reference to "configure → launch" two-step |

#### Why the migration matters (teaching note)

The new `@aws/agentcore` CLI has **no flag overrides** for region / role ARN / JWT config / env vars / entrypoint. Every value previously passed as a `agentcore configure` or `agentcore launch --env` flag must now live in `agentcore.json` + `aws-targets.json` *before* `agentcore deploy` runs. This is why the source-repo flow uses `envsubst` to render the templates from CFN outputs at deploy time — there's no other way to inject dynamic values.

The runtime SDK (`bedrock-agentcore>=1.4.3`, used inside `agentcore_runtime_adapter.py`) is unchanged — only the deploy CLI moved.

#### Concrete before/after blocks

**Install line** (Workshop Studio repo, `02-agentcore-runtime/index.en.md:193`):

```bash
# BEFORE (deprecated)
pip install bedrock-agentcore-starter-toolkit

# AFTER
# Prerequisite: Node 18+ on the participant machine. Bootstrap script
# already provisions Node on Workshop Studio EC2; verify with `node -v`.
npm install -g @aws/agentcore
```

**Configure + launch two-step** (`02-agentcore-runtime/index.en.md:39, 189` and `index.en.md:17, 84`):

```bash
# BEFORE — configure (line 39) + launch (line 189)
agentcore configure \
  --entrypoint scripts/deploy/agentcore_runtime_adapter.py \
  --execution-role $AGENTCORE_ROLE_ARN \
  --authorizer-type CUSTOM_JWT \
  --jwt-discovery-url $OAUTH_ISSUER_URL/.well-known/openid-configuration \
  --jwt-allowed-clients $COGNITO_CLIENT \
  --env MCP_GATEWAY_URL=$MCP_GATEWAY_URL \
  --env AGENT_MODEL_ID=$AGENT_MODEL_ID
agentcore launch --env MCP_GATEWAY_URL=$MCP_GATEWAY_URL --env AGENT_MODEL_ID=$AGENT_MODEL_ID

# AFTER — render templates from CFN outputs, then one-shot deploy
envsubst < pellier/backend/agentcore.json.template > pellier/backend/agentcore.json
envsubst < pellier/backend/aws-targets.json.template > pellier/backend/aws-targets.json
agentcore deploy -y --json
```

**Template shape** (the new `agentcore.json` carries the same values that were CLI flags before):

```json
{
  "version": 1,
  "name": "pellier",
  "runtimes": [
    {
      "name": "pellier_orchestrator",
      "entrypoint": "scripts/deploy/agentcore_runtime_adapter.py",
      "requirementsFile": "scripts/deploy/requirements.txt",
      "executionRoleArn": "${AGENTCORE_ROLE_ARN}",
      "protocol": "HTTP",
      "authorizerType": "CUSTOM_JWT",
      "authorizerConfiguration": {
        "customJwtAuthorizer": {
          "discoveryUrl": "${OAUTH_ISSUER_URL}/.well-known/openid-configuration",
          "allowedClients": ["${COGNITO_CLIENT}"]
        }
      },
      "envVars": [
        { "name": "MCP_GATEWAY_URL", "value": "${MCP_GATEWAY_URL}" },
        { "name": "AGENT_MODEL_ID", "value": "${AGENT_MODEL_ID}" }
      ]
    }
  ]
}
```

`aws-targets.json.template` is just `{ "account": "${AWS_ACCOUNT}", "region": "${AWS_REGION}" }` — `$AWS_ACCOUNT` is derived in the source-repo deploy script via `aws sts get-caller-identity`.

**Framing prose** (`02-agentcore-runtime/index.en.md:9, 224` and the wrap-up):

| Stale | Replacement |
|---|---|
| "we'll use the AgentCore starter toolkit" | "we'll use the AgentCore CLI (`@aws/agentcore`) — Node-based, replaces the deprecated Python `bedrock-agentcore-starter-toolkit`." |
| "configure → launch two-step" | "render-templates → deploy one-shot — `envsubst` injects CFN outputs into `agentcore.json` + `aws-targets.json`, then `agentcore deploy -y --json` does the rest." |
| any "edit `.bedrock_agentcore.yaml`" callout | drop entirely; the new CLI doesn't read that file. The source repo keeps it as a legacy stub but the deploy path no longer touches it. |

#### Verification on a Workshop Studio EC2

After the upstream rewrite, a participant should be able to run:

```bash
node -v                                      # 18+
npm install -g @aws/agentcore
agentcore --version                          # confirms install
cd pellier/backend
envsubst < agentcore.json.template > agentcore.json
envsubst < aws-targets.json.template > aws-targets.json
agentcore deploy -y --json
```

…and see the runtime ARN in stdout (`agentcore deploy --json` emits one JSON object with `runtimeArn`, `endpointArn`, `iamRoleArn`). If `envsubst` leaves any `${...}` placeholders unfilled (i.e., the env var wasn't set by the bootstrap script), the deploy will fail validation before any AWS call — that's the intended fail-fast behavior, and the bootstrap script's `set -e` will surface it cleanly.

### Italics pass on Atelier surfaces (paired with Batch 3)

Copy hygiene done in the same commit as the CLI migration: 42 `fontStyle: 'italic'` removals + 6 `<em>` tag removals across 18 Atelier surface files. Rationale: the Atelier already uses Fraunces serif for editorial weight, so italic on top was redundant + cluttering on metric labels and prose. SVG diagram annotations (`<text fontStyle="italic">` in `StateDetail.tsx` / `McpDetail.tsx`) and the orientation arrow `<span>` at `Agents.tsx:294` are intentional and were preserved.

**Closes Batch 3 (both items): SDK warning fix + italics removal.**

---

## 18. AgentCore Identity sub-batch — namespace drift + lifecycle strip (Batch 4)

Two pieces landed together (2026-05-26). The first is a real accuracy bug — colon-form namespace strings would have failed at the AgentCore API boundary if they ever hit live SDK calls; the in-memory fallback path papered over it in dev. The second is a teaching surface that makes the Cognito → namespace handoff legible to operators.

### (a) Namespace format drift (colon → dash)

AgentCore session IDs must match `[a-zA-Z0-9][a-zA-Z0-9-_]*`. The canonical namespace builder (`AgentCoreIdentityService.build_namespace`) returns:

- Authenticated: `user-{cognito_sub}-session-{session_id}`
- Anonymous: `anon-{session_id}`

The fixture, the chat handler, the substrate-scan filter, four docstrings, and the `solutions/the-ledger/` mirror all carried colon-form strings (`user:{sub}:session:{id}` / `anon:{sid}`). Two of those would have caused real, visible bugs:

1. `services/chat.py` was constructing the namespace inline by string concatenation — would have produced colon-form keys against a real AgentCore Memory backend, which 400s.
2. `routes/atelier_observatory.py:480` filters `_SESSION_STORE` by prefix `f"user:{customer_id}:session:"`. Once writers use dashes, this filter returns zero matches — the live working-substrate panel would have rendered empty.

### Source-repo files touched (this commit)

| File | Change |
|---|---|
| `pellier/backend/services/chat.py` | Replaced inline namespace construction with `AgentCoreIdentityService.build_namespace(sub, session_id)` so the format lives in one place. |
| `pellier/backend/routes/atelier_observatory.py:480` | `f"user:{customer_id}:session:"` → `f"user-{customer_id}-session-"`. Substrate-scan filter now matches canonical writers. |
| `pellier/backend/services/agentcore_identity.py` | Module docstring + CHALLENGE 9.2 block updated to dash form with regex note. |
| `pellier/backend/services/agentcore_memory.py` | Module docstring + CHALLENGE 6 block + 2 method docstrings updated. (Preferences key keeps colons — `user:{user_id}:preferences` has no session-id component, so the regex doesn't apply.) |
| `pellier/backend/routes/agent.py` | Three docstrings updated. |
| `solutions/the-ledger/services/agentcore_identity.py` | Function body + docstring updated. The "byte-for-byte mirror with the challenge block" claim was untrue before this fix. |
| `solutions/the-ledger/services/agentcore_memory.py` | Multiple docstring + comment sites updated. |
| `pellier/backend/tests/test_agentcore_memory.py` | Tests now call `AgentCoreIdentityService.build_namespace` directly (pins the contract through the canonical builder); previous hardcoded `"user:alice:session:s1"` strings replaced. Two new namespace-isolation tests assert `user-alice-session-s1` form. |
| `pellier/backend/tests/test_agent_chat_stream.py` | Five docstring sites updated. |
| `pellier/backend/tests/test_agentcore_identity.py` | Three docstring sites updated. |
| `pellier/frontend/src/atelier/surfaces/understand/architecture/MemoryDetail.tsx` | Cheat-sheet entry + TierCard prose + code snippet updated to dash form; inline `f"user:..."` replaced with `AgentCoreIdentityService.build_namespace(user_id, session_id)`. |
| `pellier/frontend/src/atelier/fixtures/production-patterns.json` | Identity card summary, `namespacePattern.anon`/`signedIn`, code snippet, and Multitenancy answer + code snippet all updated. |

### (b) Production Patterns lifecycle strip

New `wiring` field on `IdentityPattern` carries five lifecycle steps, each anchored to the file/function that owns the hop. Renders as a numbered strip on the Identity card so operators can read the diff alongside the surface:

1. **Cognito hosted UI** — `frontend/src/contexts/AuthContext.tsx · parseTokenFromHash`
2. **Frontend stores token + session id** — `frontend/src/services/chat.ts · getSessionId / getAuthHeaders`
3. **Outgoing request** — `frontend/src/services/chat.ts · /api/chat/stream POST`
4. **Backend identity resolution** — `backend/services/agentcore_identity.py · get_verified_user_context`
5. **Namespace handed to AgentCore Memory** — `backend/services/agentcore_identity.py · build_namespace`

### Tests

`pellier/frontend/src/atelier/surfaces/measure/ProductionPatterns.test.tsx` (new, 6 tests) pins:
- Namespace pattern uses dashes, not colons (assertion against the regex constraint).
- Wiring strip lists exactly 5 lifecycle hops, each with a file anchor.
- Wiring covers the full Cognito → namespace chain (keyword spot-check).
- Identity card renders the strip with all 5 steps + their anchors.
- Both anon and signed-in namespace cards render in dash form.

312/312 frontend tests green; 478 backend pass + 1 benign skip.

### Lab content

No Workshop Studio carry-over needed — the namespace canonical form was already accurate in builder markdowns (or absent). Source-repo only.

---

## 19. LangGraph comparison sub-batch — Routing surface (Batch 4 close)

Operators arriving from a LangChain/LangGraph background ask the same question every workshop: *"where's the graph?"* The Routing surface ships three patterns (Dispatcher, Agents-as-Tools, Graph) — three progressive choices, not one StateGraph. The new card pins the editorial difference.

### Source-repo change (this commit)

| File | Change |
|---|---|
| `pellier/frontend/src/atelier/surfaces/understand/Routing.tsx` | New `LangGraphComparisonCard` rendered after `DispatcherIntentCard`. Header *"Three patterns, not one graph."* Three-row mapping table + "when to reach for LangGraph instead" footer. |
| `pellier/frontend/src/atelier/surfaces/understand/Routing.test.tsx` | **New.** 4 tests: editorial header present; three mapping rows with non-empty cells; recognizable LangGraph-concept keywords per row (`conditional edge` / `supervisor` / `StateGraph`); footer's three workflow shapes (`checkpoint`, `human-in-the-loop`, `cycle/planner-critic/topology`). |

### Mapping table (rendered)

| Pellier pattern | Closest LangGraph concept | Key difference |
|---|---|---|
| Dispatcher (rules → specialist) | Conditional edges from a router node | No graph object. The router is a Python function in `services/chat.py` — keyword rules, no LLM, ~60–120 ms. |
| Agents-as-Tools (orchestrator + `@tool`) | Supervisor pattern with `create_react_agent` | Strands keeps specialists as `@tool` callables; the orchestrator is just an Agent. No `StateGraph`, no `compile()` step, no checkpointer wiring. |
| Graph (Strands GraphBuilder) | `StateGraph` with `add_node` / `add_edge` | Closest analogue. Strands GraphBuilder is opt-in for multi-step ops; in LangGraph the graph is the default authoring surface from turn one. |

### Editorial framing (footer copy)

*"When to reach for LangGraph instead: long-running stateful workflows that need durable checkpointing, human-in-the-loop pause/resume, or cycle-heavy graphs (planner ↔ critic ↔ executor) where the topology itself is the design. Pellier's e-commerce concierge hot path is none of those — a keyword classifier plus one specialist call wins on latency every time."*

### Why co-located, not a separate sidebar

The "where's the graph?" question arrives *mid-Routing surface*, while the operator is already comparing the three patterns. Splitting it to a top-level sidebar would force a context switch. Co-located, the comparison reads as a fourth column on the same mental model.

### Lab content

No Workshop Studio carry-over needed — `lab-content/builders/90-appendix/04-your-stack/index.en.md:26` already lists LangGraph alongside LlamaIndex + Bedrock Agents as Strands alternatives, framed correctly (different runtime, portable `@tool` contract). The new Routing card supplements that one-line appendix mention with the operator-facing comparison; no upstream rewrite needed.

316/316 frontend tests green. **Closes Batch 4.**

---

## 20. AgentCore — Workshop Studio testing guide (Runtime + Gateway + Memory)

The new `@aws/agentcore` Node CLI changed the deploy ergonomics enough that the full Runtime + Gateway + Memory loop should be walked end-to-end on a Workshop Studio account before the next session. This section is the verification script — copy/paste-able blocks ordered by dependency.

> **Why this matters.** The Python `bedrock-agentcore-starter-toolkit` shipped two CLI verbs (`agentcore configure` + `agentcore launch`) that took region / role ARN / JWT config / env vars as flags. The new Node CLI has *no flags* for any of those — everything must live in `agentcore.json` and `aws-targets.json` before `agentcore deploy` runs. The migration is mostly mechanical, but the new "config-as-file" shape is what trips operators on first contact.

### Prerequisites

| Resource | Where it comes from |
|---|---|
| Workshop Studio EC2 (Code Editor) | Provisioned by the lab CFN; "Open Code Editor" link from the event console |
| Cognito user pool + client | CFN outputs `COGNITO_POOL`, `COGNITO_CLIENT` |
| Aurora cluster ARN + secret | CFN outputs `PGHOSTARN`, `PGSECRET`, `PGDATABASE` |
| AgentCore execution role | CFN output `AGENTCORE_ROLE_ARN` (trust policy: `bedrock-agentcore.amazonaws.com`) |
| Stack name | CFN output `STACKNAME` (used for the smoke-test user lookup) |
| Region | `us-east-1` (AgentCore GA region) |

The Workshop Studio AMI ships with `agentcore` (Node CLI) preinstalled. Verify before starting:

```bash
which agentcore && agentcore --version   # /usr/local/bin/agentcore, v1.x
node --version                           # >= 20.x
python3.13 --version                     # 3.13.x
aws sts get-caller-identity --query Account --output text
```

If the CLI is missing (or you're testing a fresh AMI build):

```bash
npm install -g @aws/agentcore
```

**Reference docs:**
- AgentCore CLI repo: https://github.com/aws/agentcore-cli
- Bedrock AgentCore developer guide: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/
- Runtime API reference: https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/

### Step 1 — Provision AgentCore Memory (one-time per account)

`AGENTCORE_MEMORY_ID` is read at backend boot time (`config.py:178`); when unset, `AgentCoreMemoryService` falls back to in-process dicts and the four-substrate panels show `fixture` provenance. To test the live path:

```bash
# us-east-1; one memory per workshop account is enough.
python3.13 - <<'PY'
import boto3, sys
client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")

# Idempotent: reuse if a PellierSTM memory already exists.
for mem in client.list_memories(maxResults=20).get("memories", []):
    if mem.get("name") == "PellierSTM":
        print(mem["id"]); sys.exit(0)

resp = client.create_memory(
    name="PellierSTM",
    description="Pellier workshop — short-term conversation memory",
    eventExpiryDuration=30,  # days
)
print(resp["memory"]["id"])
PY
```

API ref: [`bedrock-agentcore-control:CreateMemory`](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CreateMemory.html). Capture the printed memory id, then:

```bash
echo "AGENTCORE_MEMORY_ID=<paste-memory-id>" >> pellier/backend/.env
# Restart uvicorn (Builder's Session AMI: --reload picks it up automatically;
# otherwise: pkill -HUP -f 'uvicorn app:app').
```

**Verify:** hit `GET /api/agentcore/memory/status` — it should report `{"configured": true, "memory_id": "<id>", ...}`. Run any persona session in the Boutique chat, then `GET /api/agent/session/<session_id>` — the response now includes the AgentCore-side event log (working memory) instead of just the in-process buffer.

### Step 2 — Deploy the four Lambda MCP servers + AgentCore Gateway + Runtime

`scripts/deploy/deploy_all.sh` is the canonical end-to-end script. It now uses the Node CLI for the Runtime step (no more `agentcore configure`/`launch`) and provisions four Lambda MCP servers (search adds `find_pieces_hybrid`; the new `experience` server carries `process_return` + `escalate_to_stylist` so every backend `@tool` reaches the Gateway):

```bash
cd $REPO_PATH/scripts/deploy

# All values are CFN outputs of the workshop stack.
export PGHOSTARN=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`AuroraClusterArn`].OutputValue' --output text)
export PGSECRET=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`AuroraSecretArn`].OutputValue' --output text)
export PGDATABASE=postgres
export COGNITO_POOL=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text)
export COGNITO_CLIENT=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' --output text)
export AGENTCORE_ROLE_ARN=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`AgentCoreExecutionRoleArn`].OutputValue' --output text)
export AWS_REGION=us-east-1

source ./deploy_all.sh
```

`deploy_all.sh` runs eight steps:

1. **Search Lambda** (`pellier-search-server-function`) — Lambda MCP server for `semantic_search`, `find_pieces_hybrid`, and the inventory tools.
2. **Pricing Lambda** (`pellier-pricing-server-function`) — Lambda MCP server for price analysis + deal finding.
3. **Recommendation Lambda** (`pellier-recommend-server-function`) — Lambda MCP server for personalized recommendations.
4. **Experience Lambda** (`pellier-experience-server-function`) — Lambda MCP server for `process_return` (atomic ownership + INSERT + conditional quantity decrement against `pellier.returns`) and `escalate_to_stylist` (UI-only handoff payload).
5. **AgentCore Gateway** — created with Cognito JWT auth + the 4 Lambda targets; captures `MCP_GATEWAY_URL`. ([`CreateGateway`](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CreateGateway.html))
6. **Render `agentcore.json` + `aws-targets.json`** — `envsubst` substitutes `${AGENTCORE_ROLE_ARN}`, `${OAUTH_ISSUER_URL}`, `${COGNITO_CLIENT}`, `${MCP_GATEWAY_URL}`, `${AGENT_MODEL_ID}`, `${AWS_ACCOUNT}`, `${AWS_REGION}` from env into the two `.template` files. The Node CLI has *no* flags for these — they must be in JSON before deploy.
7. **`agentcore deploy -y --json`** — reads both JSON files from `pellier/backend/`, creates the Runtime, prints a JSON envelope on stdout for downstream tooling. ([`CreateAgentRuntime`](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CreateAgentRuntime.html))
8. **Three smoke-test invocations** against the deployed Runtime (search / trending / pricing).

Fail-fast guards: step 6 errors out via `: "${VAR:?...}"` if any of `AGENTCORE_ROLE_ARN`, `COGNITO_POOL`, `COGNITO_CLIENT`, `AWS_REGION` is unset — without those, the rendered JSON would have empty strings and `agentcore deploy` would only fail at the AWS-call stage with a much harder-to-triage error.

### Step 3 — Verify Gateway tool discovery

The Gateway now exposes all 13 backend `@tool` functions over MCP streamable HTTP, split across four Lambda targets. List them:

```bash
cd $REPO_PATH/scripts/deploy
uv run test_gateway_tools.py --gateway-url "$MCP_GATEWAY_URL" --token "$TOKEN"
```

Expected 13 tools (search target carries `find_pieces_hybrid` alongside the basic vector path; the new `experience` target carries `process_return` + `escalate_to_stylist` — closing the prior gateway-vs-backend asymmetry):

```
find_pieces, find_pieces_hybrid, whats_trending, price_intelligence,
explore_collection, floor_check, running_low, restock_shelf,
side_by_side, returns_and_care, style_match, process_return,
escalate_to_stylist
```

If the count is wrong: re-check `services/agentcore_gateway.py:GATEWAY_TOOL_NAMES` — `seed_tool_registry.py` uses the same list, so a drift surfaces in both spots.

### Step 4 — Test the Runtime (deployed agent path)

```bash
export AGENT_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
  --region "$AWS_REGION" \
  --query "agentRuntimes[?agentRuntimeName=='pellier_orchestrator'].agentRuntimeId | [0]" \
  --output text)

# Cognito access token (workshop user) — 1-hour lifetime.
export USER=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationUserEmail`].OutputValue' --output text)
export PASSWORD=$(aws cloudformation describe-stacks --stack-name "$STACKNAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationUserPassword`].OutputValue' --output text)
export TOKEN=$(aws cognito-idp initiate-auth --client-id "$COGNITO_CLIENT" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters "USERNAME=$USER,PASSWORD=$PASSWORD" \
  --region "$AWS_REGION" --query 'AuthenticationResult.AccessToken' --output text)

uv run test_runtime.py \
  --runtime-id "$AGENT_RUNTIME_ID" \
  --prompt "Find me linen for a 10-day trip to Goa" \
  --token "$TOKEN" --stream
```

Expected: streaming response with product cards. Trace links: CloudWatch log group `/aws/bedrock-agentcore/runtimes/<runtime-id>` (search for the `session.id` you passed in `payload`).

### Step 5 — Wire the local backend to the deployed Gateway

The hot path most operators want to test is *"local backend → AgentCore Gateway → Lambda MCP servers."* The runtime-as-Lambda hop is the production target; the local-orchestrator-against-live-Gateway path is what you exercise in the workshop because it lets participants edit Python and watch the Gateway path light up immediately.

```bash
# pellier/backend/.env
AGENTCORE_GATEWAY_URL=<paste $MCP_GATEWAY_URL>
AGENTCORE_GATEWAY_API_KEY=<paste from Gateway create — typically Cognito client secret or workshop literal>
AGENTCORE_MEMORY_ID=<from Step 1>
USE_AGENTCORE_RUNTIME=false   # leave false; we're testing the Gateway path, not the Runtime path
```

Restart uvicorn (Builder's AMI: `--reload` watch picks it up automatically).

**Verify:** in the Boutique, run *"What linen do you have for 10 days in Goa?"*

- The orchestrator picks the Gateway path because `AGENTCORE_GATEWAY_URL` is set (`services/chat.py:1603`).
- Atelier surface `/atelier/architecture/mcp` (McpDetail) status pill flips from `fixture` to `live`.
- `GET /api/workshop/card7` (Workshop card 7 panel) shows `gateway.configured = true` and lists all 13 tools.

If the orchestrator still uses in-process tools, `services/agentcore_gateway.py:create_gateway_orchestrator` returned `None` — check the uvicorn log for `MCP dependencies not installed` or `Gateway orchestrator setup failed`. The `mcp` Python package is in `pellier/backend/requirements.txt`; on a fresh AMI you may need `uv sync`.

### Step 6 — Production-ready: route Boutique tool calls through MCP Gateway

This is the teaching moment for *"taking it to production."* Today's Boutique calls the 13 `@tool` functions in-process via Strands. The Gateway path moves those tool definitions out of the orchestrator's process and into four Lambda functions discovered over MCP. The wiring already exists; the workshop just needs to flip the switch and have participants observe what changes.

**No code change needed for the demo path** (Step 5 covers it). The teaching points:

1. **Tool catalog moves out of the agent prompt.** With `AGENTCORE_GATEWAY_URL` set, the orchestrator pulls tools dynamically via `MCPClient.list_tools_sync()` instead of importing them from `services.agent_tools`. Show this in the Atelier Tools surface — provenance pill flips per tool.
2. **Auth boundary moves to the Gateway.** Lambda functions are no longer publicly callable; the Gateway enforces Cognito JWT before invoking them. Demo the failure case by hitting a Lambda's function URL directly (`InvalidSignatureException`).
3. **Semantic tool discovery scales.** `services/agentcore_gateway.py:create_gateway_orchestrator_with_semantic_search` already wires the `x_amz_bedrock_agentcore_search` tool. With 13 tools it's overkill, but show the prompt difference: instead of *"here are 13 tools, pick one"* the orchestrator gets *"call `x_amz_bedrock_agentcore_search` with the user's intent, then invoke the returned tool."* This is how the pattern scales to hundreds of tools without bloating the agent's prompt.
4. **Every backend tool now has a Gateway path.** The previous gateway-vs-backend asymmetry (10 of 13) is closed: `find_pieces_hybrid` rides the search target, `process_return` + `escalate_to_stylist` ride the new `experience` target. This is what lets the runtime-adapter prompt list every tool the in-process orchestrator can — no more "this only works locally" caveats during the workshop.

### Step 7 — Cleanup (Workshop Studio account hygiene)

```bash
# Delete the runtime (reads agentcore.json from cwd)
cd $REPO_PATH/pellier/backend && agentcore delete -y
# Delete the gateway
aws bedrock-agentcore-control delete-gateway --gateway-identifier <gw-id> --region us-east-1
# Delete the memory
aws bedrock-agentcore-control delete-memory --memory-id <mem-id> --region us-east-1
# Delete the 4 Lambdas
for fn in pellier-search-server pellier-pricing-server pellier-recommend-server pellier-experience-server; do
  aws lambda delete-function --function-name ${fn}-function --region us-east-1
done
```

Workshop Studio accounts are time-boxed, so cleanup is mostly to verify the deletion paths work — the account itself reaps everything when the event ends.

### Failure modes to expect (and how to diagnose)

| Symptom | Likely cause | Fix |
|---|---|---|
| `agentcore deploy` errors with `AccessDenied` on `iam:PassRole` | Workshop role lacks `iam:PassRole` for the AgentCore execution role | CFN should grant it; if testing outside the lab, attach `IAMFullAccess` to your test principal |
| `agentcore deploy` succeeds but `list-agent-runtimes` returns nothing | Different region between deploy and list | Both must use `us-east-1`; check `aws-targets.json` and the `--region` flag |
| Gateway returns `401` on tool list | Cognito token expired (1-hour default) or wrong client id | Re-run the `cognito-idp initiate-auth` block; verify `COGNITO_CLIENT` matches the Gateway's allowed-clients |
| Runtime returns `MCP_GATEWAY_URL not configured` | `agentcore.json.template` rendered before `MCP_GATEWAY_URL` was exported (step 4 of `deploy_all.sh` exports it; manual reorder breaks this) | Re-export `MCP_GATEWAY_URL`, re-run step 5 (`envsubst`) and step 6 (`agentcore deploy`) |
| `mem_id` from Step 1 was created but `/api/agentcore/memory/status` still says `configured: false` | Backend wasn't restarted after the `.env` edit | `pkill -HUP -f 'uvicorn app:app'` (or wait for `--reload`) |
| Frontend McpDetail still shows `fixture` after Step 5 | Frontend caches the first `/api/workshop/card7` response | Hard reload (Cmd-Shift-R) — fixture/live flip is reflected only on next request |

### What this guide does *not* cover

- **AgentCore Identity** — Cognito hosted UI is separate from the Runtime/Gateway/Memory loop. Builder's Session uses Cognito for the Boutique frontend's auth; the Identity-as-resource-credential flow (3rd-party API tokens vaulted in Identity) is mentioned in the Atelier Identity card but not exercised in this workshop.
- **AgentCore Code Interpreter / Browser** — out of scope for Pellier; the agent-tools surface mentions them as available primitives but doesn't deploy them.
- **Multi-region / DR** — workshop deploys to `us-east-1` only.

---

## 21. Gateway parity sub-batch — every backend `@tool` is now a Gateway target (Batch 4 follow-on)

The §20 *"optional extension"* (move `find_pieces_hybrid` / `process_return` / `escalate_to_stylist` behind the Gateway) is now wired in the source repo. Closes the gateway-vs-backend asymmetry that §14 flagged — `GATEWAY_TOOL_NAMES` (and any "10 of 13" prose downstream) need a follow-up touch in a separate pass; this section pins what landed here.

**Source-repo edits (this commit):**
- ✅ `scripts/deploy/pellier_search_server.py` — `find_pieces_hybrid` was already implemented and registered in `TOOLS`; the Gateway schema now lists it (previously only the in-process orchestrator could call it).
- ✅ `scripts/deploy/pellier_experience_server.py` — new Lambda handler. Mirrors `BusinessLogic.process_return` (atomic ownership-check → INSERT into `pellier.returns` → conditional `product_catalog.quantity` decrement, all inside one RDS Data API transaction) and `agent_tools.escalate_to_stylist` (UI-only handoff payload, no DB write). Cedar's allowed-reason set is duplicated as a defense-in-depth guard inside the Lambda.
- ✅ `scripts/deploy/deploy_gateway.py` — `TOOL_SCHEMAS` gains `find_pieces_hybrid` under the search target plus a new `experience` target with `process_return` + `escalate_to_stylist`. CLI args + `main()` accept `--experience-lambda-arn`.
- ✅ `scripts/deploy/deploy_all.sh` — restructured from 7 → 8 steps. Step 4 deploys the new Experience Lambda; step 5 (Gateway) now passes `--experience-lambda-arn`; cleanup loop deletes 4 Lambdas. Banner numbers, comment block, and the docstring at the top of the file are all renumbered.
- ✅ `scripts/deploy/agentcore_runtime_adapter.py` — orchestrator system prompt lists the new tools (`find_pieces_hybrid`, `process_return`, `escalate_to_stylist`) and adds a rule for *when* to escalate (only when no other tool can honestly answer).
- ✅ `lab-content-audit.md` §20 — step list is now 1–8, expected Gateway tool count is 13 (the prior list of 10), cleanup loop deletes 4 functions, and the "optional extension" callout is replaced with a "every backend tool now has a Gateway path" teaching point.

**What still needs a follow-up:**
- `services/agentcore_gateway.py:GATEWAY_TOOL_NAMES` and `seed_tool_registry.py` still describe a 10-tool gateway view. Once those are widened to all 13, §14's "9 tools / 10 entries" drift list collapses to a single canonical count.
- `agentcore.json.template` doesn't change — the Runtime adapter discovers tools dynamically from the Gateway URL, so adding targets is invisible to the agentcore.json envelope.

**Why:** The §20 testing guide called this out as a follow-on; landing it removes the *"this only works locally"* caveat from `find_pieces_hybrid` (the production retrieval pipeline) and from the two anchor write/handoff tools. Workshop participants now see *every* backend tool light up over Gateway when they flip `AGENTCORE_GATEWAY_URL`.

**How to apply:** When updating the Gateway tool count in any other surface (Atelier Tools card, Workshop card 7, README), the source-of-truth count is now 13 of 13. The previous "10 of 13" framing is obsolete.
