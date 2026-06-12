# Dual-repo review — adversarially triaged verdict (2026-06-11)

The 161-agent review (`dual-repo-review-report.md`, 91 findings) was tuned for **recall**, so it
contains false positives, already-fixed findings, and design decisions misread as bugs. Every
actionable finding below was **re-verified against the real code** — first by hand (high-severity
cluster), then by a 72-agent adversarial verification workflow whose `fresh_account_blocker`
boolean was itself re-judged (it over-flagged: it called the floor_check-stub a blocker, which is
false).

## Bottom line for the fresh-account run

**The only true fresh-account blocker was the stale auto-applied solution files — FIXED in this
session (part a).** Of the 15 findings the workflow flagged as "blockers," **zero actually break a
freshly-provisioned box.** You are clear to provision once the pellier-repo changes are committed.

---

## ❌ FALSE POSITIVES — do NOT act (acting would cause damage or churn)

| # | Finding | Why it's wrong |
|---|---|---|
| Top-1 | `agentcore_runtime.py` service/param "bug" (`bedrock-agentcore-runtime` / `agentRuntimeId` / `authToken`) | Identical to the proven-working `scripts/deploy/test_runtime.py` + asserted by `test_runtime_switch.py:360-366`. The "fix" would break the working invoke. |
| #0 | floor_check stub "never triggers fallback" | `_INVENTORY_AGENT_STUBBED=False` is **correct** post-bootstrap (the pre-apply wires real floor_check). The suggested swap to the source-inspection helper would re-introduce a fallback when the tool is genuinely wired. |
| i=14/17 | CORS wildcard + credentials "breaks fresh deployments" | Bootstrap serves frontend+API **same-origin** from one uvicorn (`app.py:2128`, via `/ports/8000/`); no CORS preflight fires. Chat path uses bearer, not cookies. Config smell, not a break. |
| i=56 | PassRole ARN mismatch "blocks provisioning" | `static/iam_policy.json` is the participant **console** policy; deploy runs via the InstanceRole whose PassRole (`pellier-code-editor.yml:249`) is correctly `pellier-*`-scoped. |
| i=33, i=34, i=51 | (stale-closure effect / `credentials:'include'` / solution max_tokens) | Refuted by the verifiers against real code — no runtime impact on the participant path. |

## 🟢 STALE — already fixed, no action

`i=26` Aurora `search_path` (set at `pellier-database.yml:65`) · `i=50` orchestrator model-id (uses
settings) · `i=52` `_SDK_AVAILABLE` cache (present in solution).

---

## ✅ FIXED in this session

- **Solution-file drift (the real blocker)** — re-synced 8 auto-applied solution files to their
  backend twins + added `test_auto_applied_solution_matches_backend` CI tripwire. (part a)
- **`chat.py:575` NameError** — added function-local `from config import settings` in
  `_strands_enhanced_chat` (crashed the non-streaming chat path for any session).
- **`index_performance.py` columns** — `product_description`→`description`, `stars`→`rating`
  (6 each); `/api/performance/*` + `/api/quantization` were crashing.

---

## 🟡 CONFIRMED-REAL, worth fixing — none block provisioning

### Content (builders repo — participant-visible, highest reader-impact)
- **i=58** Act II §2: "open `pellier/backend/services/agentcore_runtime.py`" → should be
  `pellier/backend/agentcore_runtime.py` (the `@app.entrypoint` lives there, not in services/).
- **i=61** Act II expected-output `product_id:7` → `37` (Theo's Wabi-Sabi Bowl).
- **i=62** Six `> Probe note (resolve on-box)` callouts still visible in Act II §02 + Act III §2a.
- **i=60** Act I "Three columns" for `warehouse_inventory` → four (`updated_at`).
- **i=70** `FACILITATOR_RUN_OF_SHOW.md` presents the Gateway/token path as the mandatory Exercise 2
  rail — contradicts the lab's in-process-mandatory framing.
- **i=68** `BOOT_PATH.md` references `000_pellier_schema.sql` → actual is `001_schema.sql`.
- **i=54/55/64** Facilitator cleanup commands: wrong cluster id (`pellier-workshop` →
  `pellier-cluster-${WorkshopId}`), stack name, and runtime name (`pellier-agent` →
  `pellier_orchestrator`). Teardown silently fails → instances keep billing.
- **i=59** `$PG_URL` undefined (optional "out of time" expand — use bare `psql`).
- **i=63, i=65, i=69** reference-diagram skills/ path · unexplained `backend`/`workshop` aliases ·
  `EXERCISE_INVENTORY.md` double-underscore filename.

### Backend (real bugs, off the mandatory path)
- **return_policies** — table genuinely uncreated; `returns_and_care` (Experience Guide may call it
  before `process_return`) hits a missing relation. Fix: migration `009_return_policies.sql`
  (cols `category_name, return_window_days, conditions, refund_method` + a `default` row).
- **i=1** `graph_orchestrator.py:18` import `strands.agent.graph` → `strands.multiagent`
  (UI-only; `GRAPH_AVAILABLE` silently False).
- **i=6** `managed_policy.py:63` `settings.get_aws_region()` → `aws_region_resolved`
  (AttributeError caught; env fallback works).
- **i=11** `ChatMessage.role` unvalidated → prompt-injection vector (add `Literal["user","assistant"]`).
- **i=44** `ToolChip.tsx:140` `dangerouslySetInnerHTML` unsanitized → XSS.
- **i=45** `workshop.ts:286` `res.body!` non-null assertion → crash on null body.
- **i=8** `vector_search.py:208` dead `bind` line.
- Hygiene: email logged at INFO (i=12), `delete_cookie` missing secure/samesite (i=18),
  `str(e)` leaked in ~11 handlers (i=19), JWT parse error leaked (i=16), restock endpoint
  unauthenticated (i=15), per-request SkillRouter (i=21), timeout leak (i=35).

### Deploy/scripts (deploy-time only, not participant-facing)
- **i=24** `deploy_all.sh:74` STACKNAME missing from prereq validation.
- **deploy SECRET_HASH** (`deploy_all.sh:381`) — smoke-test auth omits SECRET_HASH → false-green
  deploy verification when the app client has a secret.
- **i=29** `bootstrap-environment.sh:690` single-quoted heredoc writes literal `$AWS_REGION`
  (the `.env` source below provides the real value → nil impact).
- **i=30** "Python 3.13 configured" logged regardless of actual `$PY_VER`.
- **i=66/67/71** `gen_placeholders.py` dead session-mount path / Linux-only fonts / in-loop imports
  (dev-only utility).
- **i=27** `check_model_access.py` hardcoded `us-east-1` (intentional; add a warn-on-mismatch).
- **i=28** `dry-run-builders.sh` missing `set -e`.
- **i=57** `static/iam_policy.json` redundant `AgentCoreControl` Sid.
