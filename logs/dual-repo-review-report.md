# Code Review Report: pellier + builders

## Executive Summary

**pellier** (application repo): 78 findings spanning critical through info. The most acute risk is in `A:svc-agentcore` — the managed-runtime invocation path is entirely non-functional due to a wrong boto3 service name and wrong API parameters, affecting both the starter and solution files. Solutions parity is a systemic problem: six solution files diverge from the live backend in ways that break the backend when copied in. Frontend has several high-severity bugs including a cart that never survives page reload and a persona-cache collision that serves one user's personalized results to another.

**builders** (workshop content repo): 22 findings. Primary issues are broken facilitator cleanup commands, author-TODO probe notes left visible to participants, a content page pointing to the wrong source file, and stale schema migration references in operational runbooks.

**Severity breakdown — pellier:** Critical 0 (service-name bug downgraded to high by verifier), High 21, Medium 8, Low 36, Info 5.
**Severity breakdown — builders:** High 2, Medium 7, Low 8, Info 2.

---

## Pellier — Application Repo

### HIGH

**`floor_check`/`running_low` stubs never trigger graceful fallback**
`pellier/backend/agents/stock_keeper.py:82` | `pellier/backend/services/chat.py:2139`
`_INVENTORY_AGENT_STUBBED = False` is hardcoded (and acknowledged as a legacy flag), so the dispatcher never enters the graceful-fallback branch. Any inventory-intent query routes to the Stock Keeper, calls the stub, and the LLM relays raw error JSON to the learner.
*Fix:* In `chat.py` around line 2137, replace the `getattr(inventory_agent_module, "_INVENTORY_AGENT_STUBBED", False)` check with a call to `_floor_check_is_workshop_stub()` (already implemented in `routes/atelier_observatory.py:151`), which correctly inspects source for the stub sentinel.

---

**Wrong boto3 service name for `invoke_agent_runtime` — always raises `UnknownServiceError`**
`pellier/backend/services/agentcore_runtime.py:165` (same bug in `solutions/the-ledger/services/agentcore_runtime.py:165`)
`boto3.client("bedrock-agentcore-runtime")` does not exist; the valid service is `"bedrock-agentcore"`. The `UnknownServiceError` is silently swallowed by the broad `except Exception` handler, returning `{"error": "runtime_unavailable"}` on every call when `USE_AGENTCORE_RUNTIME=true`.
*Fix:* Change the service name to `"bedrock-agentcore"` in both files.

---

**Wrong parameter names for `invoke_agent_runtime` — `agentRuntimeId` and `authToken` do not exist**
`pellier/backend/services/agentcore_runtime.py:172-175` (same in solutions)
Even after fixing the service name, `agentRuntimeId=runtime_id` and `authToken=auth_token` are not valid members of `InvokeAgentRuntime`. The correct parameters are `agentRuntimeArn` and `runtimeUserId`.
*Fix:* Replace `agentRuntimeId=runtime_id` with `agentRuntimeArn=endpoint` (pass ARN directly), remove `authToken=auth_token`, add `runtimeUserId=user_id or "anonymous"`. Apply to both starter and solutions files, and also `solutions/the-ledger/services/agentcore_runtime_with_invoke_log.py:173-184`.

---

**`get_session_history` returns `List[List[EventMessage]]` — `JSONResponse` 500**
`pellier/backend/services/agentcore_memory.py:252` (same in `solutions/the-ledger/services/agentcore_memory.py:209`)
`session.get_last_k_turns(k=100)` returns `List[List[EventMessage]]`; `EventMessage` is a `DictWrapper` subclass that is not JSON-serializable. The result is passed directly to `JSONResponse`, producing a 500 on every call when `AGENTCORE_MEMORY_ID` is set. Tests always monkeypatch `AGENTCORE_MEMORY_ID=None` so this is never exercised.
*Fix:* Replace `return list(session.get_last_k_turns(k=100))` with `return [{"role": msg.get("role"), "content": msg.get("content")} for turn in session.get_last_k_turns(k=100) for msg in turn]` in both files.

---

**`NameError: settings` used without import in `_strands_enhanced_chat`**
`pellier/backend/services/chat.py:575`
Line 575 references `settings.AGENTCORE_MEMORY_ID` but `settings` is never imported in `_strands_enhanced_chat`. The only `from config import settings` relevant to this class is at line 461 inside `__init__` (function-local scope). Every authenticated request with a `session_id` raises `NameError` at this line.
*Fix:* Add `from config import settings` inside `_strands_enhanced_chat`, immediately before the `if session_id:` block at line 573, mirroring the pattern at `chat_stream` line 1561.

---

**`index_performance.py` selects non-existent columns — every benchmark crashes**
`pellier/backend/services/index_performance.py:142-144` (8 query blocks)
All five query blocks SELECT `product_description` and `stars`. The schema (`001_schema.sql`) defines these columns as `description` and `rating`. Every call to these methods fails with a PostgreSQL "column does not exist" error. The routes `/api/performance/*` and `/api/quantization` are all affected.
*Fix:* Replace every occurrence of `product_description` with `description` and `stars` with `rating` at lines 142, 144, 240, 242, 567, 661, 686, and 716.

---

**`router_test.py` TEST\_CASES reference non-existent skill names — 7/10 cases always fail**
`pellier/backend/skills/router_test.py:43-105`
TEST\_CASES expect skills named `style-advisor` and `gift-concierge`. The actual loaded skills are `the-gift-table`, `the-makers-shelf`, and `the-packing-list`. `SkillRouter._parse()` drops unknown names, so all 7 positive test cases always fail. The workshop README points participants to this harness as a validation step.
*Fix:* Replace `"style-advisor"` with `"the-packing-list"` in the three single-skill cases (lines 43, 48, 53) and `{"style-advisor", "gift-concierge"}` with `{"the-gift-table"}` in the three gift cases (lines 63, 69, 75).

---

**Smoke-test Cognito auth silently broken — `SECRET_HASH` never computed**
`scripts/deploy/deploy_all.sh:381-397`
`CLIENT_SECRET` is fetched (with the comment "Workshop Studio rotates it per account") but is never used. The `initiate-auth` call passes only `USERNAME` and `PASSWORD`, omitting `SECRET_HASH`. When the app client has a client secret (the standard Workshop Studio configuration), Cognito rejects with "Unable to verify secret hash", `TOKEN` is set to `"null"`, all three smoke-test invocations silently fail, and the success banner still prints.
*Fix:* Compute `SECRET_HASH=$(echo -n "${USER}${COGNITO_CLIENT}" | openssl dgst -sha256 -hmac "$CLIENT_SECRET" -binary | base64)`, include it in `--auth-parameters` conditionally, and add a guard `[ -z "$TOKEN" ] || [ "$TOKEN" = "null" ] && { echo "ERROR: Failed to obtain Cognito token"; exit 1; }` before the smoke tests.

---

**`check_traces.py` queries wrong CloudWatch log group — always returns empty**
`scripts/deploy/check_traces.py:21`
Log group is constructed as `/aws/bedrock/agentcore/runtime/{runtime_id}`. The actual group is `/aws/bedrock-agentcore/runtimes/<runtime-id>` (two differences: slash vs hyphen, `runtime` vs `runtimes`). The script always prints "No recent traces found".
*Fix:* Change line 21 to `log_group = f"/aws/bedrock-agentcore/runtimes/{runtime_id}"`.

---

**`pellier.return_policies` table never created — `returns_and_care` tool silently fails**
`pellier/backend/services/agent_tools.py:758`
The `returns_and_care` @tool queries `pellier.return_policies` (line 776), but this table is absent from all 8 migrations and no seed script populates it. Any return/refund/care query routes to the Experience Guide, calls this tool, and gets a PostgreSQL "relation does not exist" error. The `.kiro/specs` confirm the table was supposed to be seeded by bootstrap but the migration was never written.
*Fix:* Add migration `009_return_policies.sql` creating and seeding `pellier.return_policies` with a `default` row and per-category rows. Alternatively, replace the DB query with a hard-coded dict.

---

**`CartContext` always clears persisted cart on page load — `sessionStorage` vs `localStorage` mismatch**
`pellier/frontend/src/contexts/CartContext.tsx:83`
`hydrateItems()` reads the session guard from `sessionStorage.getItem('pellier-session-id')`, but every writer of that key uses `localStorage` (PersonaContext.tsx:142, chat.ts:16). Nothing ever writes to `sessionStorage`. So `currentSession` is always `""`, the condition always fires, `localStorage['pellier-cart']` is always removed, and cart items can never survive a page reload.
*Fix:* Change both `sessionStorage` reads in CartContext.tsx (lines 83 and 163) to `localStorage`.

---

**`clearChat()` removes the persona's backend session ID immediately after `switchPersona` sets it**
`pellier/frontend/src/hooks/useAgentChat.ts:803`
`PersonaContext.switchPersona()` stores the backend session ID in `localStorage['pellier-session-id']`. ChatDrawer's `useEffect` on `persona?.id` then calls `clearChat()`, which unconditionally removes `localStorage['pellier-session-id']`. Subsequent calls mint a new random session ID unknown to the backend, orphaning the AgentCore STM session.
*Fix:* Remove `localStorage.removeItem('pellier-session-id')` from `clearChat()`. Session-ID lifecycle belongs solely to PersonaContext.

---

**Safari < 16.4 crashes on lookbehind regex in `telemetryTrace.ts`**
`pellier/frontend/src/atelier/surfaces/observe/telemetryTrace.ts:110`
`turn.content.split(/(?<=[.!?])\s+/)` uses a lookbehind assertion unsupported in Safari before 16.4 (March 2023). On older iPads/iPhones this throws `SyntaxError: Invalid regular expression` at module load time, crashing the entire TelemetryTab surface.
*Fix:* Replace with `turn.content.match(/[^.!?]+[.!?]*/g) ?? [turn.content]` or a lookahead-based split.

---

**`AtelierErrorBoundary` never resets on intra-Atelier navigation**
`pellier/frontend/src/atelier/shell/AtelierFrame.tsx:26-29`
`AtelierFrame` stays mounted across `/atelier/*` navigation, so `hasError: true` persists after any surface crash. An attendee who hits a crash on one surface is stuck in the error screen for all Atelier surfaces until they click the single escape link.
*Fix:* Key the boundary on the current pathname: read `useLocation().pathname` in `AtelierFrame` and pass it as `key={pathname}` to `<AtelierErrorBoundary>`.

---

**`PERSONA_TURN_TRACES[marco][0]` incorrectly labels `the-packing-list` skill for Turn 1**
`pellier/frontend/src/data/personaCurations.ts:397`
Turn 1 data has `{ skill: 'the-packing-list', tools: ['find_pieces'] }`, but `session-marco-opening-demo.json` Turn 1 has no `skill` field; the skill only appears in Turn 2. The file's own inline comment at line 312 correctly says "Turn 1 → Style Advisor · find\_pieces" with no skill. The unit test validates the same wrong value, masking the error.
*Fix:* Change line 397 to `{ tools: ['find_pieces'] }` and update `EXPECTED_TRACES.marco[0]` in the test file to match.

---

**`solutions/closing-marcos-gap/agents/curator.py` uses `find_pieces` instead of `find_pieces_hybrid` and is missing factory + escalation plumbing**

These are two separately verified findings that share a root cause and are merged here.

`solutions/closing-marcos-gap/agents/curator.py:10-15, 40-94`
The solution imports `find_pieces` (plain vector) instead of `find_pieces_hybrid`. It also lacks `build_recommendation_agent()`, `inject_skills`, `inject_persona_preamble`, `escalate_to_stylist`, and `specialist_hooks` plumbing. `bootstrap-labs.sh` pre-applies this file at provision time. The missing factory causes `ImportError` in both `chat.py:2100` and `graph_pattern.py:130` on startup.
*Fix:* Replace `find_pieces` with `find_pieces_hybrid`, add the factory and all missing imports/tools. Diff against `pellier/backend/agents/curator.py` for exact parity.

---

**`solutions/closing-marcos-gap/agents/experience_guide.py` missing `escalate_to_stylist` and `specialist_hooks`**
`solutions/closing-marcos-gap/agents/experience_guide.py:24-25`
Missing `escalate_to_stylist` tool grant and `specialist_hooks` escalation forwarding. Bootstrap pre-applies this file, so every provisioned environment silently drops the escalation path for Theo's persona.
*Fix:* Add `escalate_to_stylist` to the import and `tools=[...]` list, add `specialist_hooks` import and escalation forwarding block in `support()`, matching the live backend exactly.

---

**`solutions/the-ledger/services/agentcore_gateway.py` has 9 tools vs backend's 13 and is missing `access_token` parameter**

These are two separately verified findings for the same file.

`solutions/the-ledger/services/agentcore_gateway.py:40-50, 105-158`
`GATEWAY_TOOL_NAMES` has 9 entries; the backend has 13. Tests assert exactly 13. The solution is the "SHORT ON TIME" `cp` target. After `cp`, two tests fail and four tools are missing from the MCP server. Additionally, all three gateway functions lack `access_token: Optional[str] = None` and the `_gateway_headers` helper, meaning `chat.py:1610`'s call `create_gateway_orchestrator(access_token=_user_token)` raises `TypeError` after the copy.
*Fix:* Add `find_pieces_hybrid`, `style_match`, `process_return`, `escalate_to_stylist` to `GATEWAY_TOOL_NAMES`; add the `_gateway_headers` helper; add `access_token` parameter to all three functions.

---

**`solutions/the-quiet-search/services/hybrid_search.py` exports `HybridSearchService` — import breaks backend on `cp`**
`solutions/the-quiet-search/services/hybrid_search.py:26`
`agent_tools.py:528` does `from services.hybrid_search import HybridSearch`. The solution exports `class HybridSearchService` with no `search()` method. The README lists this as a recovery `cp` target. Running the `cp` causes an `ImportError` on startup and breaks `find_pieces_hybrid`.
*Fix:* Rename `class HybridSearchService` to `class HybridSearch` and implement a compatible `async def search(self, query, query_embedding, k_vector, k_bm25, rrf_k, top_n)` method, or remove the `cp` command from the README.

---

**`solutions/the-quiet-search/services/business_logic.py` uses stale schema columns**
`solutions/the-quiet-search/services/business_logic.py:28-60`
Uses `product_description`, `stars`, `category_name`, `"productURL"` — all columns that do not exist in the current schema (`description`, `rating`, `category`, `"imgUrl"`). The README lists this as a manual recovery `cp` target. Running it would fail every BusinessLogic SQL call.
*Fix:* Update all SQL column references and method names to match the current live schema and `pellier/backend/services/business_logic.py`. Or remove the recovery `cp` command from the README.

---

### MEDIUM

**Module-level response cache in `useAgentChat` ignores `persona`/`customer_id`**
`pellier/frontend/src/hooks/useAgentChat.ts:168`
`responseCache` is module-scoped. `cacheKey()` keys only on query text with no persona component. If persona A asks a query and persona B asks the same within 5 minutes, persona B receives A's personalized response from cache. The cache is also never cleared on persona switch or sign-out.
*Fix:* Change `cacheKey` to include `customerId`: `` `${customerId ?? 'anon'}:${query.trim().toLowerCase()}` ``. Wire `responseCache.clear()` into `switchPersona` and `signOut`.

---

**`solutions/closing-marcos-gap/agents/orchestrator.py` hardcodes model IDs and `max_tokens`**
`solutions/closing-marcos-gap/agents/orchestrator.py:32-33`
Hardcodes `model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0"` and `max_tokens=4096`. The backend uses `settings.BEDROCK_HAIKU_MODEL` and `settings.ROUTER_MAX_TOKENS_HAIKU` (320). The `cp` shortcut produces a 12× larger token budget than intended.
*Fix:* Add `from config import settings` and replace hardcoded values with `settings.BEDROCK_HAIKU_MODEL` and `settings.ROUTER_MAX_TOKENS_HAIKU` in both factory functions.

---

**POST `/api/tools/restock` is an unauthenticated DB write endpoint**
`pellier/backend/app.py:650-665`
No `user=Depends(get_current_user)` guard. `request: dict` with bare `request["product_id"]` access — missing keys propagate as HTTP 500 with `detail=str(e)`, leaking the exception.
*Fix:* Add `user=Depends(get_current_user)`. Replace `request: dict` with a Pydantic model `class RestockRequest(BaseModel): product_id: int; quantity: int = Field(ge=0)`.

---

**CORS wildcard + `allow_credentials=True` is invalid and `cors_origins_list` is dead code**

These two findings are merged (same root cause, same file).

`pellier/backend/app.py:300-306` / `pellier/backend/config.py:105-110`
`allow_origins=["*"]` with `allow_credentials=True` is rejected by browsers per the Fetch spec. `settings.cors_origins_list` (correctly defined in config.py) is never read — app.py hardcodes the wildcard.
*Fix:* Replace `allow_origins=["*"]` with `allow_origins=settings.cors_origins_list`. The Vite proxy shields the workshop's same-origin flow, but the config infrastructure exists and should be used.

---

**`blurbForProduct` lookbehind regex crashes Safari < 16.4** — already listed under HIGH above.

---

**`solutions/the-ledger/services/agentcore_gateway.py`** — already listed under HIGH above.

---

### LOW

**`graph_orchestrator.py` stale import path (`strands.agent.graph`) — `GRAPH_AVAILABLE` always `False`**
`pellier/backend/agents/graph_orchestrator.py:18`
Import raises `ModuleNotFoundError`; correct path is `strands.multiagent` (as used in `graph_pattern.py:214`). The Atelier graph panel always shows "(static structure)" instead of "(GraphBuilder active)".
*Fix:* Change line 18 to `from strands.multiagent import GraphBuilder`.

---

**`GraphAgentAdapter`: router node failure silently returns `_EmptyResult` with no log**
`pellier/backend/agents/graph_pattern.py:227`
When the router node raises an exception, all five condition closures return `False` without logging. The comment at line 278 incorrectly claims "the warning above already logged the routing failure" — no such warning exists.
*Fix:* Inside the condition closure, check `isinstance(router_result.result, Exception)` and emit `logger.warning(...)` before returning `False`. Fix the misleading comment.

---

**Pattern I specialist wrappers swallow exceptions and expose error text via Haiku**
`pellier/backend/agents/curator.py:158` (same in all 5 specialists)
All five `@tool` wrappers catch broad `Exception` and return `{"error": f"... error: {str(e)}"}`. Haiku may paraphrase internal exception text to the user. Pattern is identical in solutions/ — accepted workshop simplification.
*Fix* (if promoted to production): Return a generic `{"error": "I ran into a problem — try again.", "internal_detail": str(e)}` and add one sentence to `ORCHESTRATOR_SYSTEM_PROMPT` on error handling.

---

**`graph_orchestrator.py` hardcodes model labels that diverge when env-override is active**
`pellier/backend/agents/graph_orchestrator.py:45`
Model labels are hardcoded strings; if `BEDROCK_OPUS_MODEL` is overridden to Sonnet the panel still shows "Claude Opus 4.6".
*Fix:* Import `settings` from `config` and use `settings.BEDROCK_OPUS_MODEL` / `settings.BEDROCK_HAIKU_MODEL` in the metadata dict.

---

**`agentcore_evals.py` uses wrong boto3 service — `bedrock-agentcore` has no `create_evaluation_job`**
`pellier/backend/services/agentcore_evals.py:109-122`
`create_evaluation_job` lives on the `"bedrock"` service, not `"bedrock-agentcore"`. Payload keys are also wrong. Off by default; no learner path affected. Tests stub boto3 entirely.
*Fix:* Change client to `boto3.client("bedrock")` and rewrite the payload to match `CreateEvaluationJob`'s required shape when the graduation path is activated.

---

**`managed_policy._region()` calls non-existent `settings.get_aws_region()`**
`pellier/backend/services/managed_policy.py:63`
Raises `AttributeError` on every call; silently falls back to `os.environ.get("AWS_REGION")`. The fallback produces the correct value in workshop environments, so functional impact is nil.
*Fix:* Replace `settings.get_aws_region()` with `settings.aws_region_resolved`.

---

**`IndexPerformanceService` uses blocking `psycopg.connect` inside async route handlers**
`pellier/backend/services/index_performance.py:58`
Six `async def` methods call synchronous `psycopg.connect()` without `asyncio.to_thread`. Blocks the event loop during benchmarks. No impact at single-user workshop concurrency.
*Fix:* Switch to `psycopg.AsyncConnection` throughout, or inject the existing `DatabaseService` which has a properly configured `AsyncConnectionPool`.

---

**`vector_search.py`: first `bind` construction is dead code**
`pellier/backend/services/vector_search.py:208`
Lines 208-212 build `bind` which is immediately overwritten on line 213. The comment claiming "embedding twice" is also wrong — the CTE alias requires only one binding.
*Fix:* Delete lines 208-212.

---

**`ContextManager` singleton mixes messages from all concurrent sessions**
`pellier/backend/services/context_manager.py:577-585`
Single process-level `ContextManager` with no session key. `clear_context` accepts `session_id` but ignores it. Stats are inflated across sessions. Buffer is not fed to the LLM, so response quality is unaffected.
*Fix* (option b): Document explicitly that this is a process-level aggregate counter; remove the misleading `session_id` parameter from `clear_context` or rename it.

---

**Client-controlled `conversation_history[].role` flows unsanitized into LLM prompt**
`pellier/backend/services/chat.py:625-630`
`ChatMessage.role` is `str` with no `Literal` constraint. Role value is concatenated into the orchestrator's user message without validation.
*Fix:* Change `role: str` to `role: Literal["user", "assistant"]` in `pellier/backend/models/search.py:89`. The `Literal` import is already present.

---

**User email logged at INFO level on every chat turn**
`pellier/backend/services/chat.py:534`
`user.get('email')` logged at INFO at lines 534 and 582 and set as an OTEL trace attribute at lines 608 and 1648.
*Fix:* Replace all four `user.get('email')` usages with `user.get('sub', 'anonymous')`. The `sub` claim is already used at line 579.

---

**`services/auth.py` leaks JWT parse error details to callers**
`pellier/backend/services/auth.py:96-97`
`detail=f"Invalid token: {e}"` exposes internal PyJWT error text (e.g. "Signature verification failed") to unauthenticated callers.
*Fix:* Change to `detail="auth_failed"` and log the raw exception at DEBUG level.

---

**`delete_cookie()` omits `secure`/`samesite` — cookies may not be cleared**
`pellier/backend/routes/auth.py:296-303`
`response.delete_cookie(cookie, path="/")` does not pass `secure=True, samesite="lax"`, which were set at `set_cookie` time. Non-matching deletion attributes may cause browsers to retain stale session cookies.
*Fix:* Add `secure=True, samesite="lax"` to each `delete_cookie` call in `_clear_session_cookies`.

---

**Many `app.py` exception handlers expose `str(e)` as HTTP detail**
`pellier/backend/app.py:563,618,632,647,665,694,831,843,892,924,1011`
~15 handlers raise `HTTPException(500, detail=str(e))`, potentially exposing psycopg connection strings and boto3 ARNs.
*Fix:* Replace `detail=str(e)` with generic operation-specific strings (e.g., `"search_failed"`, `"restock_failed"`). Existing `logger.error` calls already preserve the real error server-side.

---

**`SkillRouter` instantiated fresh per-request — Bedrock client never reused**
`pellier/backend/services/chat.py:1799-1800`
New `SkillRouter` per request defeats the `self._agent` cache. Design comment says "Construct once; call route() per turn."
*Fix:* Add `get_skill_router()` singleton function in `skills/loader.py` mirroring `get_registry()`. Replace both call sites (chat.py:1800, atelier_observatory.py:780).

---

**STM hydration guard reads stale `messages` via closure**
`pellier/frontend/src/hooks/useAgentChat.ts:297`
`if (messages.length > 1) return` inside an async `.then()` reads a stale closure value; `messages` is not in the `[sessionId]` dependency array.
*Fix:* Replace with `if (messagesRef.current.length > 1) return`. `messagesRef` is already maintained at lines 326-328.

---

**`LayoutContext` auto-start-tour effect has empty dependency array — never re-runs after onboarding**
`pellier/frontend/src/contexts/LayoutContext.tsx:72`
`useEffect(() => { if (showOnboarding) return; ... }, [])` captures `showOnboarding` at mount and never re-runs when it transitions to `false`.
*Fix:* Add `showOnboarding` to the dependency array.

---

**`chat.ts` SSE fetch calls omit `credentials: 'include'` — cookie-auth users treated as anonymous**
`pellier/frontend/src/services/chat.ts:93`
Neither streaming fetch call sets `credentials: 'include'`. In the httpOnly-cookie auth path, no auth credentials reach the chat endpoint and the user is treated as anonymous.
*Fix:* Add `credentials: 'include'` to the fetch options at lines 93 and 176.

---

**`useScrollAndFlash` pending flash timeouts accumulate without cleanup**
`pellier/frontend/src/hooks/useScrollAndFlash.ts:48`
`pendingTimeouts.current` is pushed to but never cleared on unmount.
*Fix:* Add `useEffect(() => () => { pendingTimeouts.current.forEach(clearTimeout); pendingTimeouts.current = [] }, [])`.

---

**`ChatTab.tsx` AGENTS\_LIST hardcodes Experience Guide as `idle`**
`pellier/frontend/src/atelier/surfaces/observe/ChatTab.tsx:1582`
`agents.json` marks Experience Guide as `"shipped"`. The Chat session rail shows it grayed-out.
*Fix:* Change `status: 'idle'` to `status: 'live'` for Experience Guide in `AGENTS_LIST`.

---

**`evaluations.json` uses generic agent aliases that don't match canonical names**
`pellier/frontend/src/atelier/fixtures/evaluations.json:3-49`
Uses "Search", "Recommendation", "Pricing", "Inventory" while `agents.json` uses "Style Advisor", "Curator", "Value Analyst", "Stock Keeper". No cross-surface mapping exists.
*Fix:* Update `evaluations.json` agentName values to canonical names.

---

**`elapsedMs` mismatch between `sessions.json` index and detail fixtures**
`pellier/frontend/src/atelier/fixtures/session-theo-ceramics-return.json:5`
theo-ceramics-return: sessions.json=2140ms vs detail fixture=5840ms. anna-birthday-gift: 5640ms vs 6231ms. Visible in the Brief tab.
*Fix:* Update `sessions.json` to match the authoritative detail fixture values (5840 and 6231).

---

**`sortSessionsByRecency` function name contradicts ascending sort implementation**
`pellier/frontend/src/atelier/surfaces/observe/SessionsList.tsx:30`
Named "recency" (newest-first) but sorts oldest-first. File docstring repeats the wrong claim. Inner comment is correct.
*Fix:* Rename to `sortSessionsChronologically` and update the file docstring.

---

**`ToolChip` uses `dangerouslySetInnerHTML` with unsanitized `panel.meta`**
`pellier/frontend/src/components/atelier-chat/ToolChip.tsx:140`
`panel.meta` HTML from the backend is injected without sanitization. The same file already strips tags in `defaultSummary()`. `ConfidenceSummary.tsx` has a `stripTags()` helper.
*Fix:* Replace `dangerouslySetInnerHTML={{ __html: panel.meta }}` with `panel.meta.replace(/<[^>]+>/g, '')` rendered as plain text.

---

**`workshop.ts`: non-null assertion on `res.body` throws on null bodies**
`pellier/frontend/src/services/workshop.ts:286`
`res.body!.getReader()` will throw `TypeError` if `res.body` is null.
*Fix:* Add `if (!res.body) throw new Error('Response body is null — streaming not supported');` before `getReader()`.

---

**`clearCart` uses browser `confirm()` — blocks render thread**
`pellier/frontend/src/contexts/CartContext.tsx:259`
Synchronous blocking dialog incompatible with ongoing animations and streaming updates.
*Fix:* Replace with inline `pendingClear` boolean state and a confirmation pill in CartPanel.

---

**`ConciergeModal`: `role="dialog"` without `aria-modal="true"`**
`pellier/frontend/src/components/ConciergeModal.tsx:423-424`
Missing `aria-modal` prevents virtual cursor trapping in NVDA/VoiceOver. `ChatDrawer.tsx:273` has the same issue. `AuthModal.tsx` and all design primitives correctly include it.
*Fix:* Add `aria-modal="true"` to both `ConciergeModal.tsx` and `ChatDrawer.tsx` dialog containers.

---

**`ConciergeModal`: deprecated `onKeyPress` — double-fires on CJK keyboards**
`pellier/frontend/src/components/ConciergeModal.tsx:697`
`onKeyPress` is deprecated since React 17 and fires during IME composition. `ChatDrawer` correctly uses `onKeyDown`.
*Fix:* Change to `onKeyDown={handleKeyPress}` and add `if (e.nativeEvent.isComposing) return` at the top of the handler.

---

**`solutions/closing-marcos-gap/agents/stock_keeper.py` hardcodes `max_tokens=2048`**
`solutions/closing-marcos-gap/agents/stock_keeper.py:110`
Backend uses `settings.AGENT_MAX_TOKENS_HAIKU` (800). The `cp` shortcut produces a 2.5× larger token budget.
*Fix:* Replace `max_tokens=2048` with `max_tokens=settings.AGENT_MAX_TOKENS_HAIKU`.

---

**`solutions/the-ledger/services/agentcore_memory.py` missing `_SDK_AVAILABLE` sentinel — warning spam**
`solutions/the-ledger/services/agentcore_memory.py:111-140`
Backend added a module-level `_SDK_AVAILABLE` cache to suppress repeated import-failure warnings. Solution retries the import unconditionally, regressing to warning-per-request after `cp`.
*Fix:* Add the `_SDK_AVAILABLE: Optional[bool] = None` sentinel and guard logic matching the backend.

---

**`solutions/the-quiet-search/services/hybrid_search_with_rerank.py` inherits from stale base class**
`solutions/the-quiet-search/services/hybrid_search_with_rerank.py:27`
Inherits from `HybridSearchService` (doesn't exist in current backend) and calls `super().search()` with a 6-positional-arg signature incompatible with the current `HybridSearch.search()`. Not a `cp` target, but confusing.
*Fix:* Delete the file (no references, no cp target), or update it to extend `class HybridSearch` with the current signature.

---

**Backend copy `pellier/backend/skills/*/SKILL.md` files diverge from runtime-loaded `/skills/*/SKILL.md`**
`pellier/backend/skills/the-gift-table/SKILL.md`
Backend copies lack `display_name` and have older body content. Loader reads from repo-root `/skills/` (not `pellier/backend/skills/`). Presence of both sets misleads learners editing the wrong file.
*Fix:* Remove the SKILL.md-only subdirectories from `pellier/backend/skills/` (three directories: the-gift-table/, the-makers-shelf/, the-packing-list/).

---

**Aurora cluster parameter group does not set `search_path`**
`assets/pellier-database.yml:55` (all three copies)
No `search_path` parameter; default `'$user', public` means unqualified table names fail in ad-hoc psql sessions.
*Fix:* Add `search_path: '"$user", pellier, public'` to the `ClusterParameterGroup.Parameters` block in all three copies.

---

**`deploy_lambda.py` leaves `package.zip` artifact in caller's working directory**
`scripts/deploy/deploy_lambda.py:90-91`
`package.zip` is written to cwd on every invocation and never cleaned up. Not gitignored.
*Fix:* Remove lines 90-91 (the in-memory `zip_content` is already passed directly to the Lambda API). Add `*.zip` to `.gitignore`.

---

**`STACKNAME` omitted from prereq validation loop**
`scripts/deploy/deploy_all.sh:74`
Seven variables are validated but `STACKNAME` is not. An empty `STACKNAME` produces an opaque AWS CLI error at step 8 instead of the clear prereq-missing message.
*Fix:* Add `STACKNAME` to the for-loop on line 74.

---

**`dry-run-builders.sh` missing `set -e`**
`scripts/dry-run-builders.sh:24`
Without `-e`, a failed `cp "$TOOLS" "${TOOLS}.dryrun.bak"` continues silently, potentially leaving `agent_tools.py` in the patched state permanently with no backup to restore.
*Fix:* Change line 24 to `set -euo pipefail`.

---

**`bootstrap-environment.sh` heredoc writes literal `$AWS_REGION` (single-quoted EOF)**
`scripts/bootstrap-environment.sh:690`
`<< 'EOF'` suppresses variable expansion; the `.bashrc` lines become self-referencing `export AWS_REGION="$AWS_REGION"`. The `.env` source block below provides the correct value, so functional impact is nil.
*Fix:* Change `<< 'EOF'` to `<< EOF` or remove the redundant region export lines.

---

**`bootstrap-environment.sh` logs "Python 3.13 configured" regardless of installed version**
`scripts/bootstrap-environment.sh:713, 836`
Hardcoded to "3.13" while the install logic tries 3.14 first and captures the result in `$PY_VER`.
*Fix:* Replace both occurrences with `"Python ${PY_VER} configured"`.

---

**`check_model_access.py` hardcodes `REGION='us-east-1'` with no env-var override**
`scripts/check_model_access.py:17`
Intent is correct (us.*/global.* profiles require us-east-1) but the constraint is opaque and would give a false pass if the workshop ever expands to other regions.
*Fix:* Add a warning when `AWS_REGION != 'us-east-1'` rather than silently ignoring the env var.

---

**`AtelierFrame` comment claims `/atelier` route is gated by `AuthGate` — it is not**
`pellier/frontend/src/App.tsx:182`
The route renders `<AtelierFrame />` directly with no `<AuthGate>` wrapper despite the comment and file-level JSDoc claiming it is gated.
*Fix:* Wrap the route: `<Route path="/atelier" element={<AuthGate><AtelierFrame /></AuthGate>}>`.

---

**`PersonaStrip` declares `openingQuery` prop but never uses it**
`pellier/frontend/src/atelier/surfaces/observe/ChatTab.tsx:83-145`
Prop is in the type signature and passed at the call site but never destructured or rendered.
*Fix:* Remove `openingQuery` from the prop type and call site, or render it as a subtitle.

---

### INFO

**`business_logic.py` module docstring lists non-existent column `image_verified`**
`pellier/backend/services/business_logic.py:8`
Also annotates `reviews (TEXT)` when the schema defines `reviews integer`.
*Fix:* Remove `image_verified,` and change `reviews (TEXT)` to `reviews integer` in the docstring.

**`tool_audit_writer.record_allow` docstring says "AfterToolCall" — caller is `on_before_tool`**
`pellier/backend/services/tool_audit_writer.py:106-107`
*Fix:* Update docstring to say "Called from the BeforeToolCallEvent handler (on_before_tool) in chat.py."

**`hybrid_search.py` comment cites wrong migration number for the GIN index**
`pellier/backend/services/hybrid_search.py:280`
Says "(migration 005)"; index is created in migration 004.
*Fix:* Change `(migration 005)` to `(migration 004)`.

**`SKILL.md` example in `models.py` docstring uses stale skill name `style-advisor`**
`pellier/backend/skills/models.py:31`
*Fix:* Change example to `'the-gift-table'`.

---

## Builders — Workshop Content Repo

### HIGH

**Act II §2 directs learner to open wrong file for `@app.entrypoint`**
`content/20-act-2-the-ledger/02-agentcore-runtime/index.en.md:99`
Content says "Open `pellier/backend/services/agentcore_runtime.py`" and then shows the `@app.entrypoint` decorated `invoke()` function. That decorator is only in the top-level `pellier/backend/agentcore_runtime.py`. Opening the services/ file shows boto3 client helpers, not the entrypoint.
*Fix:* Change to `Open \`pellier/backend/agentcore_runtime.py\`.` (drop `services/`). The later references to `services/agentcore_runtime.py` for the `logger.info` exercise are correct and should remain.

---

**`$PG_URL` undefined in bootstrap — psql shortcut command fails**
`content/20-act-2-the-ledger/02-agentcore-runtime/index.en.md:204`
`psql "$PG_URL" -f solutions/the-ledger/sql/tool_audit_recap.sql` — `PG_URL` is never exported by bootstrap. Bootstrap exports `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`. The shortcut escape hatch fails with a connection error.
*Fix:* Replace `psql "$PG_URL"` with bare `psql` (picks up the PG* env vars set by bootstrap). Update the matching comment in the solutions SQL file.

---

### MEDIUM

**Unresolved author/probe-note TODOs visible to workshop participants**
`content/20-act-2-the-ledger/02-agentcore-runtime/index.en.md:329,364,410,432` and `content/30-act-3-the-concierge/02-mcp-and-knowledge-bases/index.en.md:180,216`
Six blockquote "Probe note (resolve on-box before publishing)" and "SANITIZE the ARN/account id" callouts appear in the main participant content flow, exposing unfinished authoring TODOs and unverified CLI output.
*Fix:* Verify each CLI surface on a live environment, capture real output with ARN/account values replaced by placeholders, and remove all "(resolve on-box)" notes before publishing.

---

**Facilitator cleanup guide uses wrong Aurora cluster identifier**
`content/90-appendix/04-facilitator-notes/index.en.md:218`
`--db-cluster-identifier pellier-workshop` does not match the actual identifier `pellier-cluster-${WorkshopId}`. The delete command fails, leaving the cluster running.
*Fix:* Replace with a dynamic lookup: `CLUSTER_ID=$(aws rds describe-db-clusters --query "DBClusters[?starts_with(DBClusterIdentifier,'pellier-cluster-')].DBClusterIdentifier" --output text)` then use `$CLUSTER_ID`.

---

**Facilitator run-of-show presents optional Gateway path as mandatory Exercise 2 path**
`FACILITATOR_RUN_OF_SHOW.md:133-155`
The run-of-show instructs table leads that Exercise 2 "runs on the authenticated Gateway rail" with `source ~/pellier-token.sh`. The lab guide explicitly states the mandatory path uses the in-process dispatcher (`pattern: dispatcher`, no token) and the Gateway/Policy beat is optional.
*Fix:* Rewrite section 00:46-00:53 to lead with the mandatory in-process path. Present the Gateway/Policy ALLOW/DENY beat as an optional fast-table extension. Update the failure escalation row to match.

---

**`BOOT_PATH.md` references stale migration filename `000_pellier_schema.sql`**
`BOOT_PATH.md:108,195,201`
The actual migration is `001_schema.sql`. The troubleshooting appendix and CFN template in this same repo both use `001_schema.sql`, confirming the mismatch.
*Fix:* Replace all three occurrences of `000_pellier_schema.sql` with `001_schema.sql`.

---

**Reference appendix project layout shows `backend/skills/` as SKILL.md location**
`content/90-appendix/01-reference/index.en.md:213`
Layout diagram shows `pellier/backend/skills/ # SKILL.md prompt overlays`. Loader reads from repo-root `/skills/`. A learner editing `pellier/backend/skills/the-gift-table/SKILL.md` would edit a stale copy with no effect.
*Fix:* Add `/skills/` at the repo root level annotated as `# editable SKILL.md prompt overlays`. Change `pellier/backend/skills/` annotation to `# Python skill system (loader, router, registry, models)`.

---

**Expected-output sample shows `product_id:7` for Wabi-Sabi Bowl — actual ID is 37**
`content/20-act-2-the-ledger/02-agentcore-runtime/index.en.md:178`
The "Expected shape" example shows `{"customer_id":"theo","product_id":7}`. `product_id` 7 is a Jute Placemat Set; the Wabi-Sabi Bowl is `productId` 37. Learners will see `product_id:37` in their actual audit row.
*Fix:* Change `product_id:7` to `product_id:37`.

---

**`gen_placeholders.py` `OUT` path hard-coded to a dead session mount**
`scripts/gen_placeholders.py:35`
`OUT = Path("/sessions/laughing-relaxed-ramanujan/mnt/...")` — this path exists only on the original authoring session. Any re-run fails immediately with `FileNotFoundError`.
*Fix:* Replace with `OUT = Path(__file__).parent.parent / "static"`.

---

### LOW

**Facilitator cleanup guide uses placeholder CloudFormation stack name**
`content/90-appendix/04-facilitator-notes/index.en.md:203`
`aws cloudformation delete-stack --stack-name pellier-workshop-instances` — Workshop Studio uses its own stack naming. The command silently exits with success (exit 0) while instances continue billing.
*Fix:* Add a note that teardown should be performed via the Workshop Studio event console, or instruct the facilitator to look up the actual stack name first.

---

**Participant IAM policy PassRole resource does not match actual runtime role name**
`static/iam_policy.json:54-63`
PassRole allows `arn:aws:iam::*:role/pellier-agentcore-runtime-execution`. The actual role is `pellier-agentcore-runtime-${WorkshopId}`. The workshop's EC2 instance role uses `pellier-*` wildcard correctly; the console policy does not.
*Fix:* Change resource ARN to `arn:aws:iam::*:role/pellier-agentcore-runtime-*`.

---

**Facilitator cleanup command uses wrong runtime name `pellier-agent`**
`content/90-appendix/04-facilitator-notes/index.en.md:207`
Deployed runtime is named `pellier_orchestrator` (underscore). Wrong name fails to delete the runtime.
*Fix:* Change to `cd /workshop/sample-pellier-agentic-search-apg/pellier/backend && agentcore delete -y`. Also fix line 87.

---

**`warehouse_inventory` schema described as "three columns" — it has four**
`content/10-act-1-the-boutique/02-wire-floor-check/index.en.md:55`
Schema has a fourth column `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
*Fix:* Change "Three columns" to "Four columns: warehouse\_id, product\_id, quantity, updated\_at".

---

**Shell alias commands used in multi-line bash blocks without documentation**
`content/20-act-2-the-ledger/02-agentcore-runtime/index.en.md:315`
`backend` and `workshop` aliases work only in the Code Editor interactive shell. Inconsistent with full-path commands used elsewhere on the same page.
*Fix:* Expand to `cd /workshop/sample-pellier-agentic-search-apg/pellier/backend && grep AGENTCORE_RUNTIME_ENDPOINT .env` or add an inline comment explaining the alias.

---

**`EXERCISE_INVENTORY.md` has spurious double underscore in pre-apply filename**
`EXERCISE_INVENTORY.md:70`
`agent_tools__builders_preapply.py` (double underscore) vs actual `agent_tools_builders_preapply.py`.
*Fix:* Remove the extra underscore.

---

**`gen_placeholders.py` Linux-only font paths crash on macOS/Windows**
`scripts/gen_placeholders.py:30-33`
All four font paths are hard-coded to `/usr/share/fonts/truetype/dejavu/` (Debian/Ubuntu only).
*Fix:* Add a platform-aware font resolver or bundle fonts in `scripts/fonts/`.

---

**`gen_placeholders.py`: `import math` repeated inside for-loops**
`scripts/gen_placeholders.py:269,277,289`
`import math` appears three times inside `make_atelier_memory()` (twice inside loops, once at function scope) and never at module level.
*Fix:* Add `import math` at the module level and remove the three in-function occurrences.

---

### INFO

**`AgentCoreControl` Sid is entirely redundant with `AgentCoreRuntime` wildcard**
`static/iam_policy.json:32-49`
`AgentCoreRuntime` already grants `bedrock-agentcore:*`. `AgentCoreControl` explicitly lists 13 of those same actions.
*Fix:* Remove the `AgentCoreControl` Sid entirely.

---

---

## Top Priorities

In order of severity + workshop delivery impact:

1. **Fix all three `agentcore_runtime.py` bugs** (wrong service name, wrong parameter names) in both `pellier/backend/services/agentcore_runtime.py` and `solutions/the-ledger/services/agentcore_runtime.py`. Challenge 5 is completely non-functional without this.

2. **Fix the solutions parity crisis**: Update `solutions/closing-marcos-gap/agents/curator.py` (add `build_recommendation_agent` factory, `find_pieces_hybrid`, `escalate_to_stylist`, skill injection) and `solutions/the-ledger/services/agentcore_gateway.py` (13 tools + `access_token` parameter). Bootstrap pre-applies these files; as deployed they cause `ImportError` on startup or silently degrade core features.

3. **Fix `agentcore_memory.py`** — `get_session_history` returns non-serializable `EventMessage` objects, causing HTTP 500 when `AGENTCORE_MEMORY_ID` is set. Apply to both starter and solutions files.

4. **Fix the `NameError` in `_strands_enhanced_chat`** (`chat.py:575`) — add `from config import settings`. This crashes the primary non-streaming chat path for any request with a `session_id`.

5. **Fix `index_performance.py` column names** (`product_description` → `description`, `stars` → `rating`) — all five `/api/performance/*` and `/api/quantization` routes fail on every invocation.

6. **Fix `pellier.return_policies` missing migration** — add migration 009 so the Experience Guide's `returns_and_care` tool can execute. Any return/care question fails silently for every participant.

7. **Fix the CartContext `sessionStorage`/`localStorage` mismatch** (`CartContext.tsx:83,163`) — cart is wiped on every page reload, breaking a core storefront feature.

8. **Fix the deploy smoke test** (`deploy_all.sh:381-397`) — compute `SECRET_HASH` and guard against a null token. Without this the deployment verification step silently passes regardless of whether the stack actually works.

9. **Fix `check_traces.py` log group path** (`/aws/bedrock/agentcore/runtime/` → `/aws/bedrock-agentcore/runtimes/`) and **`router_test.py` skill names** (`style-advisor`/`gift-concierge` → `the-packing-list`/`the-gift-table`) — both validation/observability tools permanently report failure or empty results.

10. **Resolve the six author-TODO probe notes** in builders content (Act II §2, Act III §2a) before next workshop delivery. These are currently visible to participants and include "SANITIZE the ARN/account id" instructions.