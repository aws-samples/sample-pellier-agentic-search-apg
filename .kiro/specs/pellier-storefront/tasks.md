# Pellier Storefront — Implementation Tasks

## How to use this document

- Tasks are numbered in dependency order. Lower numbers unblock higher numbers.
- Layers are grouped so a developer can work within a layer without context-switching.
- Each leaf task has: title, acceptance criteria (links to `requirements.md` IDs), files to create/modify, test verification, and a "done when" signal.
- Priority tags: **[P0]** primary deliverable, **[P1]** storefront supporting, **[P2]** lower priority (Storyboard/Discover route stubs per Requirement 1.13).
- Sibling-spec blockers are flagged inline with **[blocked by: ...]**.

### Challenge block markers

- Python files use `# === CHALLENGE N: START ===` and `# === CHALLENGE N: END ===`.
- TypeScript/JavaScript files (`.ts`, `.tsx`, `.js`) use `// === CHALLENGE N: START ===` and `// === CHALLENGE N: END ===`.
- Both forms must include matching END markers.
- The corresponding `solutions/moduleM/<relative path>` file must match the code between the markers byte-for-byte (enforced by Task 7.4).

## Out of scope (owned elsewhere)

The following are **not** tracked here. They live in the `.claude/prompts/` playbooks and run after this spec completes:

- CloudFormation nested stacks — `.claude/prompts/infrastructure.md`
- IAM policies — `.claude/prompts/infrastructure.md`
- Cognito User Pool + App Client provisioning — `.claude/prompts/infrastructure.md`
- Bootstrap scripts (`scripts/seed-database.sh` and friends) — `.claude/prompts/infrastructure.md`
- Workshop lab guide prose — `.claude/prompts/workshop-content.md`
- Builders session lab guide prose — `.claude/prompts/builders-content.md`

## Sibling-spec dependencies

| Blocker spec             | What this spec needs from it                                                                                                                                    | Tasks that depend                      |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `catalog-enrichment`     | `pellier.product_catalog` table with `tags text[]` column populated per the 9-product showcase and ~444-product full catalog, 1024-dim embeddings present | 2.1, 2.2, 3.6, 3.7                     |
| `customer-support-agent` | `customer_support_agent` Strands Agent exportable from `backend/agents/experience_guide.py`                                                               | 2.4 (routing wiring), 7.3 verification |

Start tasks 1.x in parallel with sibling-spec work; gate catalog-dependent tasks on `catalog-enrichment` reaching the "seeded catalog with tags" milestone.

---

## Layer 1 — Shared foundations (unblocks everything)

- [x] 1.1 **[P0] Centralize user-facing copy (backend + frontend)**
  - Acceptance: satisfies Req 1.12 and 7.2.1, 7.2.2.
  - Create `pellier/backend/storefront_copy.py` and `pellier/frontend/src/copy.ts`.
  - Move every customer-facing string that will be authored in later tasks into these two modules (announcement bar, 8 intents, 9 reasoning-chip templates, sign-in strip copy, curated banner copy, status strip copy, category chip labels, refinement chip labels, Storyboard teasers, footer columns, auth modal copy, preferences modal copy, error envelopes).
  - Test verification: add `frontend/src/__tests__/copy.test.ts` that regex-scans `copy.ts` for forbidden words (Req 1.12.2), emojis, and em dashes. Same check on the Python side via `tests/backend/test_copy_compliance.py`.
  - Done when: both copy modules compile, the copy compliance tests pass, and no other task's PR contains a hardcoded user-facing string.

- [x] 1.2 **[P0] Extend shared TypeScript types**
  - Acceptance: matches Data Models section of `design.md`.
  - Modify `pellier/frontend/src/services/types.ts` to add `Product` (with `tags`, `reasoning`), `ReasoningStyle`, `ReasoningChip`, `Intent`, `ProductOverride`, `User`, `Preferences` (plus the four tag union types), `SearchResponse`, and keep `SearchResult` as a `type SearchResult = SearchResponse` alias.
  - Test verification: `tsc --noEmit` clean in `frontend/`.
  - Done when: existing imports resolve and no runtime TS errors appear in `npm run build`.

- [x] 1.3 **[P0] Extend shared Pydantic models**
  - Acceptance: matches Data Models section of `design.md`.
  - Modify `pellier/backend/models/__init__.py` (and `product.py`, `search.py` as fits) to add `Preferences`, `VerifiedUser`, `SearchResponse` (with `alias_generator=to_camel`, `populate_by_name=True`), plus the four tag literal types.
  - Test verification: `pytest tests/backend/test_models.py` — round-trip JSON with both snake_case and camelCase keys.
  - Done when: `SearchResponse(products=[], query_embedding_ms=1, search_ms=2, total_ms=3).model_dump(by_alias=True)` returns camelCase keys.

- [x] 1.4 **[P0] Personalization match scoring**
  - Acceptance: Req 3.3.2 and 3.3.2.1.
  - Create `pellier/backend/services/personalization.py` with `match_score(product_tags, prefs, *, weights=None)` and `sort_personalized(products, prefs)`. Default weights = all-ones (equal-weight overlap). Tie-break by default editorial order.
  - Test verification: `tests/backend/test_personalization.py` — with seeded 9-product showcase tags from `storefront.md`, confirm `Italian Linen Camp Shirt` scores higher than `Signature Straw Tote` for `{vibe: ['minimal'], categories: ['linen']}`. Assert the weighted hook accepts a `weights` kwarg and does not change default behavior when omitted.
  - Done when: tests pass; no call-site changes needed in later tasks to adopt weighted scoring.

---

## Layer 2 — Backend services (C1–C8 challenge scaffolds + auth middleware prerequisites)

- [x] 2.1 **[P0] C1: Vector search — `_vector_search` on HybridSearchService** [blocked by: `catalog-enrichment`]
  - Acceptance: Req 2.3.1–2.3.6; wraps query patterns from `database.md`.
  - Modify `pellier/backend/services/hybrid_search.py` to add `async def _vector_search(self, embedding, limit, ef_search, iterative_scan=True)` inside a `# === CHALLENGE 1: START ===` / `# === CHALLENGE 1: END ===` block with the complete solution: CTE embedding, `SET LOCAL hnsw.ef_search`, conditional `SET LOCAL hnsw.iterative_scan = 'relaxed_order'`, parameterized placeholders, `quantity > 0` filter, cosine `<=>` ordering, `1 - distance` as similarity. Call `sql_query_logger` with parameterized args only (Req 5.4.2, 5.3.3).
  - Files: `hybrid_search.py` (modify), `solutions/the-quiet-search/services/hybrid_search.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_vector_search.py` — mocks psycopg; asserts the CTE shape, the two `SET LOCAL` calls with the passed values, the `iterative_scan` branch, the parameterized-only call pattern, and the `limit` bound.
  - Done when: `POST /api/search` with `query="linen shirt"` returns ≥5 results in <500ms p95 against the seeded catalog (Req 5.1.1) and the challenge block text matches verbatim between `services/hybrid_search.py` and `solutions/the-quiet-search/services/hybrid_search.py`.

- [x] 2.2 **[P0] C2: `get_trending_products` tool** [blocked by: `catalog-enrichment`]
  - Acceptance: Req 2.4.1–2.4.2 and coding-standards tool pattern.
  - **Pre-existing context:** the 9 tools listed in `workshop-content.md` steering already exist in `pellier/backend/services/agent_tools.py`. C2 wraps ONLY `get_trending_products` in a challenge block — participants delete and reimplement that one function; the other 8 tools remain as-is.
  - Modify `pellier/backend/services/agent_tools.py` by carving the existing `get_trending_products()` body into a `# === CHALLENGE 2: START/END ===` block: `@tool` decorated, `_db_service` availability check, `_run_async()` bridging, returns `json.dumps(...)`, returns `json.dumps({"error": str(e)})` on exception.
  - Files: `agent_tools.py` (modify), `solutions/closing-marcos-gap/services/agent_tools_floor_check_solution.py` (drop-in mirror).
  - Test verification: `tests/backend/test_agent_tools.py::test_get_trending_products` — happy path returns ≥3 products as valid JSON; `_db_service=None` returns an error envelope; raised exception returns `{"error": ...}`.
  - Done when: tool callable from a REPL returns a parseable JSON string with ≥3 products.

- [x] 2.3 **[P0] C3: `product_recommendation_agent` specialist** [blocked by: 2.2]
  - Acceptance: Req 2.4.3–2.4.5. **All 4 tools this agent uses (`search_products`, `get_trending_products`, `compare_products`, `get_product_by_category`) already exist in `agent_tools.py` today; no scaffolding work here for those tools — only wire them into the Strands Agent.**
  - Modify `pellier/backend/agents/curator.py` to define `product_recommendation_agent` inside a `# === CHALLENGE 3: START/END ===` block: `Agent(model=BedrockModel(model_id=settings.BEDROCK_CHAT_MODEL), temperature=0.2, tools=[search_products, get_trending_products, compare_products, get_product_by_category], system_prompt=copy.RECOMMENDATION_SYSTEM_PROMPT)`.
  - Files: `curator.py` (modify), `solutions/closing-marcos-gap/agents/curator.py` (new drop-in mirror), `copy.py` (add `RECOMMENDATION_SYSTEM_PROMPT`).
  - Test verification: `tests/backend/test_c3_recommendation_relevance.py` — stubbed Bedrock returns a canned answer mentioning `Sundress in Washed Linen`; test parses the response, looks up the product's `tags`, asserts overlap with `{evening, warm, dresses, outerwear}`. Assert the Straw Tote would fail this check.
  - Done when: `"something for warm evenings out"` produces a recommendation whose tags intersect the evening/warm set (Req 2.4.5).

- [x] 2.4 **[P0] C4: Multi-agent orchestrator** [blocked by: 2.3, `customer-support-agent` spec]
  - Acceptance: Req 2.4.6–2.4.8 and 4.3.1.
  - Modify `pellier/backend/agents/orchestrator.py` to define the orchestrator inside a `# === CHALLENGE 4: START/END ===` block: Haiku 4.5 model id exactly as steering specifies, `temperature=0.0`, tools list `[search_agent, product_recommendation_agent, price_optimization_agent, inventory_restock_agent, customer_support_agent]` (symbol import for the last), `system_prompt=copy.ORCHESTRATOR_SYSTEM_PROMPT` enforcing priority `pricing > inventory > support > search > recommendation`.
  - Files: `orchestrator.py` (modify), `solutions/closing-marcos-gap/agents/orchestrator.py` (new drop-in mirror), `copy.py` (add `ORCHESTRATOR_SYSTEM_PROMPT`).
  - Test verification: `tests/backend/test_orchestrator_routing.py` — five representative queries (one per specialist intent) each route to the expected specialist via stubbed Bedrock; routing is observable via span tags from `otel_trace_extractor`. Add `test_priority_order_on_ambiguous_queries` that injects a query matching both pricing and inventory and asserts pricing (higher priority) fires.
  - Done when: routing tests green, including `test_priority_order_on_ambiguous_queries`.

- [x] 2.5 **[P1] C5: AgentCore Runtime migration**
  - Acceptance: Req 2.5.1 and Design "Runtime selection switch".
  - Modify `pellier/backend/services/agentcore_runtime.py` to add `async def run_agent_on_runtime(message, session_id, user_id)` inside a `# === CHALLENGE 5: START/END ===` block. Add `USE_AGENTCORE_RUNTIME: bool = False` to `backend/config.py` via `pydantic-settings`. Update `app.py` (or the `/api/agent/chat` route — created in 3.5) to branch on the env var.
  - Files: `agentcore_runtime.py` (modify), `config.py` (modify), `solutions/the-ledger/services/agentcore_runtime.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_runtime_switch.py` — with `USE_AGENTCORE_RUNTIME=false` the in-process Strands orchestrator handles the request; with `=true` the runtime path is called (mocked).
  - Done when: flipping `USE_AGENTCORE_RUNTIME=true` in `backend/.env` and restarting routes `/api/agent/chat` through runtime without further code changes.

- [x] 2.6 **[P0] C6: AgentCore STM Memory (session history + user preferences)**
  - Acceptance: Req 2.5.2, 4.3.2, 4.4.1, 6.2.1.
  - Modify `pellier/backend/services/agentcore_memory.py` to implement `AgentCoreMemory` with `append_session_turn`, `get_session_history`, `get_user_preferences`, `set_user_preferences` inside a `# === CHALLENGE 6: START/END ===` block. Key schemes: `user:{user_id}:session:{session_id}` for authenticated sessions, `anon:{session_id}` for anonymous. No cross-namespace merge; anon namespace left orphaned on sign-in (Req 4.3.3).
  - Files: `agentcore_memory.py` (modify), `solutions/the-ledger/services/agentcore_memory.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_agentcore_memory.py` — round-trip preference save/load; session history append-and-read; assert anon namespace is not accessible via user key and vice versa.
  - Done when: `POST /api/user/preferences` and `/api/agent/chat` (from 3.4, 3.5) exercise this service end-to-end.

- [x] 2.7 **[P1] C7: AgentCore MCP Gateway**
  - Acceptance: Req 2.5.3.
  - Modify `pellier/backend/services/agentcore_gateway.py` to expose the 9 tools via MCP streamable HTTP inside a `# === CHALLENGE 7: START/END ===` block. Tool signatures and JSON envelopes identical to `agent_tools.py`.
  - Files: `agentcore_gateway.py` (modify), `solutions/the-ledger/services/agentcore_gateway.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_gateway.py` — MCP client can discover all 9 tools and invoke `get_trending_products` returning the same JSON shape as the in-process call.
  - Done when: discovery returns the full 9-tool list with names matching `workshop-content.md` exactly (Req 2.2.3).

- [x] 2.8 **[P1] C8: OpenTelemetry trace extraction**
  - Acceptance: Req 2.5.4, 5.4.1.
  - Modify `pellier/backend/services/otel_trace_extractor.py` to produce `{ spans: Span[], totalMs: number, specialistRoute: string }` for a given run inside a `# === CHALLENGE 8: START/END ===` block. Wire it into the orchestrator's streaming path so each request produces an extractable trace.
  - Files: `otel_trace_extractor.py` (modify), `solutions/the-ledger/services/otel_trace_extractor.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_otel_extractor.py` — run the orchestrator with a stubbed Bedrock, assert the extractor returns at least one orchestrator span, one specialist span, and one tool span.
  - Done when: the `/inspector` view (existing frontend component) renders the extractor output.

---

## Layer 3 — Backend Challenge 9 scaffolds (auth + identity)

- [x] 3.1 **[P0] C9.1: Cognito JWT validation middleware**
  - Acceptance: Req 4.2.1–4.2.4, 5.3.1–5.3.3.
  - Create `pellier/backend/services/cognito_auth.py` inside a `# === CHALLENGE 9.1: START/END ===` block: `CognitoAuthService` with JWKS client (1h TTL cache), `validate_jwt(token) -> VerifiedUser`, `extract_user(request)` reading `Authorization: Bearer` then `access_token` cookie, and a FastAPI `require_user` dependency setting `request.state.user`.
  - Files: `cognito_auth.py` (new), `config.py` (add `COGNITO_POOL_ID`, `COGNITO_REGION`, `COGNITO_CLIENT_ID`, `COGNITO_CLIENT_SECRET`, `COGNITO_DOMAIN`, `APP_BASE_URL`, `OAUTH_REDIRECT_URI`), `solutions/the-ledger/services/cognito_auth.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_cognito_auth.py` — valid token passes; expired / wrong `iss` / wrong `aud` / wrong `token_use` / unsigned-by-JWKS all fail; JWKS fetch is called once for N concurrent validations (cache hit).
  - Done when: a protected endpoint returns 401 without a token and returns `request.state.user` populated with a valid one.

- [x] 3.2 **[P0] C9.2: AgentCore Identity wrapper**
  - Acceptance: Req 4.3.1–4.3.3.
  - Create `pellier/backend/services/agentcore_identity.py` inside a `# === CHALLENGE 9.2: START/END ===` block: `AgentCoreIdentityService` with `get_verified_user_context(request)` returning `UserContext(user_id | None, session_id, namespace)`. Namespace uses `user:{user_id}:session:{session_id}` when authenticated, `anon:{session_id}` otherwise.
  - Files: `agentcore_identity.py` (new), `solutions/the-ledger/services/agentcore_identity.py` (new drop-in mirror).
  - Test verification: `tests/backend/test_agentcore_identity.py` — authenticated request yields user namespace; unauthenticated yields anon namespace; `user_id` in `UserContext` equals `request.state.user.user_id`.
  - Done when: the orchestrator consumes `UserContext` to scope `agentcore_memory` calls (wired in 3.5).

- [x] 3.3 **[P0] `/api/auth/*` routes**
  - Acceptance: Req 3.1.1–3.1.5, 4.1.3.
  - Create `pellier/backend/routes/auth.py` (or extend `app.py`) implementing:
    - `GET /api/auth/signin?provider=<google|apple|email>` → 302 to Cognito `/oauth2/authorize` with `identity_provider` mapped (`Google`, `SignInWithApple`, omitted for email), `client_id`, `response_type=code`, `scope=openid email profile`, generated `state`, `redirect_uri` from config.
    - `GET /api/auth/callback?code&state` → validate state, POST `/oauth2/token`, validate via JWKS (3.1), set three httpOnly Secure SameSite=Lax cookies (`access_token`, `id_token`, `refresh_token`), set `just_signed_in=1` cookie (`Max-Age=60`, httpOnly false, Secure, SameSite=Lax) per Design decision #2, 302 to `/`.
    - **Rationale for `just_signed_in`:** this cookie carries NO authentication value — it is a single-use "callback occurred" flag that the SPA reads and deletes on first mount. `httpOnly: false` is required so the SPA can read and delete it; `Secure` + `SameSite=Lax` prevents cross-origin leakage. No session data or token fragment is stored in it.
    - `GET /api/auth/me` → returns `{ user_id, email, given_name }` on success.
    - `POST /api/auth/logout` → clear cookies, call Cognito `/oauth2/revoke`.
    - `POST /api/auth/refresh` → rotate tokens using the `refresh_token` cookie; used by the frontend interceptor (3.7 on the frontend).
  - Files: `routes/auth.py` (new) or `app.py` (modify), `services/auth.py` (may already exist — confirm and extend).
  - Test verification: `tests/backend/test_auth_routes.py` — state-mismatch returns 400 `invalid_state`; callback happy path sets the four cookies; `/api/auth/me` 401s without valid token; logout clears cookies.
  - Done when: full Cognito sign-in loop works end-to-end against the E2E dev pool (3.8).

- [x] 3.4 **[P0] `/api/user/preferences` routes with JWT**
  - Acceptance: Req 3.2.1–3.2.4, 4.4.1–4.4.3.
  - Create `pellier/backend/routes/user.py` (or extend `app.py`) with `GET` and `POST /api/user/preferences` protected by `require_user`. `POST` validates the payload against the four tag literal types (returns 422 on unknown values) and calls `AgentCoreMemory.set_user_preferences`.
  - Test verification: `tests/backend/test_preferences_api.py` — GET null when unseen; POST round-trip; POST with unknown tag returns 422 with offending field names.
  - Done when: preferences persist across sign-out/sign-in with the same IdP subject.

- [x] 3.5 **[P0] `/api/agent/chat` SSE + `/api/agent/session/{id}`**
  - Acceptance: Req 3.4.1–3.4.4; stream-start-only JWT validation per Error Handling row and Sequence Diagram #2 note.
  - Create (or extend) `pellier/backend/routes/agent.py` to stream SSE from `orchestrator` (C4) or `run_agent_on_runtime` (C5) based on `USE_AGENTCORE_RUNTIME`. Validate the JWT exactly once at stream start; do not re-check per chunk. Resolve `UserContext` via `AgentCoreIdentityService` (3.2). First SSE event includes `session_id` when one is auto-generated.
  - Test verification: `tests/backend/test_agent_chat_stream.py` — mid-stream token expiry does not abort the stream; session continuity works with `session_id` passed in subsequent calls; anonymous requests fall to `anon:{session_id}` namespace.
  - Done when: frontend can chat for a full multi-turn conversation with memory and tokens that remain in cookies only (Req 5.3.1).

- [x] 3.6 **[P0] `/api/products` personalized + `/api/products/{id}` + `/api/inventory`** [blocked by: `catalog-enrichment`]
  - Acceptance: Req 3.3.1–3.3.5, 3.5.1–3.5.2.
  - Create `pellier/backend/routes/products.py` (or extend) with `GET /api/products?personalized=<bool>&category=<name>`, `GET /api/products/{id}`, `GET /api/inventory`. Personalized branch reads preferences from `AgentCoreMemory`, calls `sort_personalized` (1.4), returns ranked list. Unauthenticated and no-prefs branches return default editorial order.
  - Test verification: `tests/backend/test_products_personalized.py` — with seeded catalog and known tags, Sundress/Cardigan top the list for `{vibe: ['creative'], occasions: ['evening']}`; anon request returns editorial order.
  - Done when: flipping `personalized=true` observably changes the returned ordering.

- [x] 3.7 **[P0] `POST /api/search` endpoint (wire C1)** [blocked by: 2.1]
  - Acceptance: Req 3.3.6, 5.1.1, and `SearchResponse` shape from 1.3.
  - Create or extend `pellier/backend/routes/search.py` with `POST /api/search`. Embed the query via `EmbeddingService`, call `HybridSearchService._vector_search`, return `SearchResponse` (camelCase fields).
  - Test verification: `tests/backend/test_search_endpoint.py` — timing fields are populated; p95 < 500ms smoke test against seeded catalog.
  - Done when: frontend search pill in 4.2 shows results within the 500ms budget.

- [x] 3.8 **[P0] E2E Cognito dev pool bootstrap (CI)**
  - Acceptance: Design "Testing Strategy — E2E (Playwright against a dedicated Cognito dev pool)".
  - Add `tests/e2e/bootstrap_cognito_dev_pool.py` (or `.ts`) that creates a test user via `AdminCreateUser` + `AdminSetUserPassword` using a CI-scoped admin role and a pool ID/client ID from CI secrets. Separate pool from workshop infrastructure; email/password-only. Google and Apple IdP flows validated via manual workshop dry-runs, **not** automated E2E.
  - Files: `tests/e2e/bootstrap_cognito_dev_pool.py` (new), `tests/e2e/teardown_cognito_dev_pool.py` (new), `.github/workflows/e2e.yml` (or the equivalent CI config — create only if not already tracked elsewhere).
  - Test verification: `tests/e2e/auth-happy-path.spec.ts` can sign in with the bootstrapped credentials.
  - Done when: CI runs E2E green against the dev pool.

---

## Layer 4 — Frontend components (home page primary deliverable)

- [x] 4.1 **[P0] UIContext with modal singleton + global ⌘K/Escape**
  - Acceptance: Req 1.11.2–1.11.5.
  - Modify `pellier/frontend/src/contexts/UIContext.tsx` to hold `activeModal: 'concierge' | 'auth' | 'preferences' | 'cart' | 'checkout' | null`. Opening any modal closes the previous. Global `keydown` handler toggles concierge on `⌘K`/`Ctrl+K`, closes any open modal on `Escape`.
  - Test verification: `UIContext.test.tsx` — opening auth while concierge is open closes concierge; `Escape` closes whichever is active; `⌘K` toggles concierge.
  - Done when: every modal created downstream uses `UIContext` rather than local `isOpen` state.

- [x] 4.2 **[P0] Announcement bar + sticky header + nav (5 items + wordmark + Account)**
  - Acceptance: Req 1.1.1–1.1.4, 1.2.1–1.2.5.
  - Modify `pellier/frontend/src/components/Header.tsx` to render exactly 5 nav items (Home, Shop, Storyboard, Discover, Account). Update `AccountButton` to read `useAuth().user` and render `Account` signed out, `Hi, {givenName}` signed in. Remove any legacy About/Journal items. Add `<AnnouncementBar>` component above the header with exact copy from `copy.ts`.
  - Test verification: `Header.test.tsx` — renders 5 nav items; hides `Ask Pellier` text at <768px; swaps Account label on auth state.
  - Done when: the page renders the nav spec with no legacy items, on all three breakpoints.

- [x] 4.3 **[P0] Hero stage with intent rotation, hover-pause, progress bar, ticker**
  - Acceptance: Req 1.3.1–1.3.10.
  - Create `pellier/frontend/src/components/HeroStage.tsx` plus child components `IntentInfoCard`, `SearchPill`, `IntentTicker`, `ProgressBar`. Consume the 8 intents from `copy.ts`. Implement `productOverride` for intent 2 (Featherweight Trail Runner). Hover anywhere on the stage pauses rotation and freezes the progress bar. Ticker chip click jumps the stage and resets the 7.5s timer. Search input keyword-match jumps to the matching intent on Enter. Apply `slow-zoom` Ken Burns (14s alternate, 1.02 → 1.08).
  - Test verification: `HeroStage.test.tsx` with fake timers — cycles at 7.5s; hover pauses; unhover resumes from paused position; ticker click resets; keyword-match navigation works; mobile shows the dark glass breadcrumb, desktop hides it.
  - Done when: tests green and visual review matches `storefront.md` descriptions.

- [x] 4.4 **[P0] Sign-in strip / curated banner (auth-state driven)** [depends on: 5.1 for `useAuth().preferences`; stub to `null` until 5.1 lands]
  - Acceptance: Req 1.4.1–1.4.5 and Design decision #2 (`just_signed_in` cookie).
  - Create `pellier/frontend/src/components/AuthStateBand.tsx` which reads `useAuth()` and renders `<SignInStrip>` (signed out, not dismissed), `<CuratedBanner>` (signed in + prefs), or nothing (signed in + no prefs). Sign-in strip dismissal writes `sessionStorage.setItem('pellier.signinStrip.dismissed', 'true')`. Curated banner entrance animation is `fade-slide-up` 0.6s. On mount, read and immediately delete the `just_signed_in` cookie; if it was set AND `preferences === null`, open `PreferencesModal` via `UIContext`.
  - Test verification: `AuthStateBand.test.tsx` — covers all four state combinations plus the `just_signed_in` cookie path; confirms the cookie is deleted after read.
  - Done when: the three auth states render correctly and the modal auto-opens only on fresh sign-in.

- [x] 4.5 **[P0] Live status strip + category chips + refinement panel**
  - Acceptance: Req 1.5.1–1.5.4 and 1.8.1–1.8.3.
  - Create `LiveStatusStrip.tsx`, `CategoryChips.tsx`, `RefinementPanel.tsx`. Status strip fetches `/api/inventory` and shows stale-data warning if `stale=true`. Category chip click filters the grid via query param. Refinement chips compose with AND semantics and re-fetch the grid.
  - Test verification: component tests on each; integration test exercising chip toggles → grid re-fetch (mocked API).
  - Done when: toggling chips changes the product list and parallax re-observes on grid remount.

- [x] 4.6 **[P0] Product grid with parallax IntersectionObserver**
  - Acceptance: Req 1.6.1–1.6.6.
  - Create `ProductGrid.tsx` and `ProductCard.tsx`. Extend `hooks/useScrollReveal.ts` to accept `{ threshold: 0.05, rootMargin: '0px 0px -5% 0px', staggerMs: 220, index }` with the exact ease-out-expo timing from `storefront.md`. The grid is mounted with `key={prefsVersion}` from `useAuth()` so a preference save remounts the grid and re-fires parallax (Req 1.6.6). Cards include warm wash overlay, optional top-left badge, top-right heart (fades in on hover), brand + color, name, price + rating, thin divider, `<ReasoningChip>`, full-width `Add to bag`.
  - Test verification: `ProductGrid.test.tsx` — parallax triggers once per card under normal scroll; remount on `prefsVersion` change re-fires. Frame-rate smoke (Req 5.1.4) covered by a manual Chromium check documented in the test's JSDoc.
  - Done when: the 9 showcase cards animate on scroll with the 220ms stagger and 1100–1200ms ease-out-expo.

- [x] 4.7 **[P0] Reasoning chips (four rotating styles)**
  - Acceptance: Req 1.7.1–1.7.5.
  - Create `ReasoningChip.tsx`. Takes a `ReasoningChip` model from 1.2 and renders the `picked` / `matched` / `pricing` / `context` style. `pricing` urgent clause wraps in a `<span style={{color:'var(--accent)'}}>`. Assignment logic ensures no two adjacent cards share a style where possible.
  - Test verification: `ReasoningChip.test.tsx` — renders each style correctly; grid-level test asserts distribution across the 9 cards.
  - Done when: the grid shows all four styles and the `pricing` urgent clause is terracotta.

- [x] 4.8 **[P0] Storyboard teaser grid (3-card, home-page section)**
  - Acceptance: Req 1.9.1–1.9.4.
  - Create `StoryboardTeaser.tsx` with the three exact cards from `copy.ts`: MOOD FILM Vol. 12, VISION BOARD Vol. 11, BEHIND THE SCENES Vol. 10. Hover scales image 1.05. `Read the full vision ›` link in terracotta.
  - Test verification: `StoryboardTeaser.test.tsx` — renders 3 cards, correct copy, hover scale applied.
  - Done when: home-page section renders 3 cards, never 1.

- [x] 4.9 **[P0] Footer (5 columns)**
  - Acceptance: Req 1.10.1–1.10.3.
  - Create `Footer.tsx` with Brand, Shop, About (`Our story`, `Makers we love`, `Sustainability`, `Press`), Service, Storyboard newsletter columns. Bottom strip with © plus Privacy/Terms/Accessibility.
  - Test verification: `Footer.test.tsx` — 5 columns, About contents verified, bottom strip present.
  - Done when: About is confirmed to live only in the footer (no top-nav item).

- [x] 4.10 **[P0] Floating ⌘K command pill**
  - Acceptance: Req 1.11.1, 1.11.5.
  - Create `CommandPill.tsx` fixed at bottom-right with dusk pill, small B mark, `Ask Pellier` label, styled `⌘K` keycap. Click toggles concierge via `UIContext` (from 4.1).
  - Test verification: `CommandPill.test.tsx` — click toggles `activeModal === 'concierge'`.
  - Done when: the pill appears on every page (home + storyboard + discover) and toggles the concierge.

- [x] 4.11 **[P2] Storyboard route — minimal index page**
  - Acceptance: Req 1.13.1, 1.13.3, 1.13.4.
  - Create `pages/StoryboardPage.tsx` that composes `StickyHeader`, the existing `StoryboardTeaser` (reused from 4.8), a `ComingSoonLine` (italic Fraunces copy from `copy.ts` — `Coming soon - the full editorial hub arrives with the next Edit.`), `Footer`, and `CommandPill`. Wire into `App.tsx` with `react-router-dom` v6 `<Routes>`.
  - Test verification: `StoryboardPage.test.tsx` — renders header with `Storyboard` in the ink-highlighted current-page state and the 3-card grid.
  - Done when: `/storyboard` renders without a 404.

- [x] 4.12 **[P2] Discover route — minimal index page**
  - Acceptance: Req 1.13.2, 1.13.3, 1.13.4.
  - Create `pages/DiscoverPage.tsx`. Signed out: render a sign-in CTA with copy `Discover is tailored to you. Sign in and watch the storefront tune itself.`. Signed in: render the personalized `ProductGrid` (4.6) plus the same `ComingSoonLine`.
  - Test verification: `DiscoverPage.test.tsx` — both auth states render the correct variant.
  - Done when: `/discover` works in both states.

---

## Layer 5 — Frontend Challenge 9 scaffolds (auth + preferences UIs)

- [x] 5.1 **[P0] C9.3: `auth.ts` helpers + `useAuth()` extension**
  - Acceptance: Req 2.6.5, Design `frontend/src/utils/auth.ts` signatures.
  - Create `pellier/frontend/src/utils/auth.ts` inside a `# === CHALLENGE 9.3: START/END ===` block (use JS-style `// === CHALLENGE 9.3: START ===` markers to match the file type).
    - Exports: `redirectToSignIn(provider, opts?)`, `openSignInChooser(opts?)`, `redirectToLogout()`, `useAuth()`.
    - Extend `contexts/AuthContext.tsx` (existing) rather than replace it; expose `user`, `preferences`, `refresh()`, `savePreferences(p)`, `isLoading`.
    - `services/api.ts` 401 interceptor: call `/api/auth/refresh`; on success retry once; on failure call `openSignInChooser({ returnTo: window.location.pathname + window.location.search })`.
  - Files: `utils/auth.ts` (new), `contexts/AuthContext.tsx` (modify), `services/api.ts` (modify), `solutions/the-ledger/frontend/utils/auth.ts` (new drop-in mirror).
  - Test verification: `auth.test.ts` — `openSignInChooser` routes to `/signin?returnTo=...`; the 401 interceptor retries once after a successful refresh; a second 401 falls through to the chooser.
  - Done when: E2E refresh test (`e2e/auth-refresh.spec.ts`) passes and the fail test (`e2e/auth-refresh-fail.spec.ts`) lands on `/signin` with all three providers visible.

- [x] 5.2 **[P0] C9.4a: `AuthModal.tsx`** [blocked by: 5.1]
  - Acceptance: Req 2.6.6 for the auth modal, `storefront.md` auth modal spec.
  - Create `pellier/frontend/src/components/AuthModal.tsx` inside a `// === CHALLENGE 9.4: START ===` block: centered cream rounded-3xl card, glass backdrop. Header: B mark + `Welcome to Pellier` + `Sign in for a storefront built for you`. Body: `PERSONALIZED VISIONS` eyebrow + italic `Let the storefront find you.`. Three buttons: `Continue with Google`, `Continue with Apple`, `Continue with email` — each calling `redirectToSignIn(<provider>)` with `returnTo` from the current URL. Disclaimer line + `Secured by AgentCore Identity` 10px mono footer.
  - When opened from the chooser (`/signin?returnTo=...`), all three providers visible, no provider preselected.
  - Test verification: `AuthModal.test.tsx` — three buttons invoke `redirectToSignIn` with the correct provider; modal uses `UIContext.activeModal === 'auth'`.
  - Done when: click-through to Cognito Hosted UI works end-to-end.

- [x] 5.3 **[P0] C9.4b: `PreferencesModal.tsx`** [blocked by: 5.1]
  - Acceptance: Req 2.6.6 for the preferences modal, `storefront.md` preferences onboarding spec.
  - Create `pellier/frontend/src/components/PreferencesModal.tsx` inside a `// === CHALLENGE 9.4: START ===` block: four groups with chip UI per steering.
    - Group 1 Vibe: 6 cards (Minimal, Bold, Serene, Adventurous, Creative, Classic) with 2-word descriptors.
    - Group 2 Colors: 5 pill chips with gradient swatches.
    - Group 3 Occasions: 6 pill chips.
    - Group 4 Categories: 6 pill chips.
    - Selected chip visual state: `background: #2d1810`, `color: #fbf4e8`, `border-color: #2d1810`.
    - Submit row: `Skip for now` secondary + `Save and see my storefront` primary.
    - Footer: `Preferences stored with AgentCore Memory` 10px mono with shield icon.
  - On save: call `useAuth().savePreferences(prefs)`, which POSTs to `/api/user/preferences`, then closes the modal, triggers the curated banner flash, and advances `prefsVersion` in `AuthContext` (causing `ProductGrid` to remount and re-fetch `/api/products?personalized=true`).
  - Test verification: `PreferencesModal.test.tsx` — chip selection toggles match Req; save triggers POST and closes modal; selected-chip colors match exactly.
  - Done when: the full loop from Cognito sign-in → preferences save → grid re-sort works, verified by `e2e/auth-happy-path.spec.ts`.

---

## Layer 6 — Configuration and wiring

- [x] 6.1 **[P0] Config keys for auth + runtime + URLs**
  - Acceptance: Req 4.1.2, 4.1.4, 7.2.3; Design runtime switch.
  - Modify `pellier/backend/config.py` (pydantic-settings) to add: `COGNITO_POOL_ID`, `COGNITO_REGION`, `COGNITO_CLIENT_ID`, `COGNITO_CLIENT_SECRET`, `COGNITO_DOMAIN`, `APP_BASE_URL`, `OAUTH_REDIRECT_URI`, `USE_AGENTCORE_RUNTIME` (default false), plus the existing Bedrock model IDs.
  - Modify `pellier/backend/.env.example` with placeholder entries for every new key. Do **not** put real values in the repo.
  - Modify `pellier/frontend/.env.example` with `VITE_API_BASE_URL`.
  - Test verification: `tests/backend/test_config.py` — missing required auth env vars cause a clear startup error; `USE_AGENTCORE_RUNTIME` defaults to `False`.
  - Done when: a fresh clone can `cp .env.example .env`, fill in Cognito values, and start the backend.

- [x] 6.2 **[P0] Wire React auth context provider at App root**
  - Acceptance: Req 7.2.1.
  - Modify `pellier/frontend/src/App.tsx` to wrap the tree with `<AuthProvider>` → `<CartProvider>` → `<UIProvider>` → `<Routes>`. Add `<AuthModal>` and `<PreferencesModal>` into the modal singleton slot managed by `UIContext`.
  - Test verification: `App.test.tsx` — providers resolve; default route renders `HomePage`.
  - Done when: the app boots with providers in the correct order and no runtime context errors.

- [x] 6.3 **[P0] Copy-compliance lint for PRs**
  - Acceptance: Req 1.12.1–1.12.4.
  - Add `frontend/src/__tests__/copy_hardcoded_strings.test.ts` — scans JSX text nodes and `return "..."` in component files for any string not imported from `copy.ts`. Fails if a user-facing hardcoded string is found outside `copy.ts`.
  - Add equivalent Python scan: `tests/backend/test_backend_copy_hardcoded.py` over any route/response that surfaces to the UI.
  - Test verification: the tests fail when someone introduces a hardcoded `Sign in and ...` string in a component and pass when moved to `copy.ts`.
  - Done when: CI enforces this on every PR.

---

## Layer 7 — Verification matrix

- [x] 7.1 **[P0] Performance smoke**
  - Acceptance: Req 5.1.1–5.1.3.
  - Add `tests/perf/test_perf_smoke.py` — measures `POST /api/search` p95 < 500ms; `POST /api/agent/chat` first token < 2s; JWT-verified endpoint warm path added latency < 200ms. Runs against a seeded dev catalog via a docker-compose or the workshop Code Editor box.
  - Done when: CI surfaces these numbers on every run.

- [x] 7.2 **[P0] Visual regression**
  - Acceptance: Req 5.2.1–5.2.3, 1.6.2.
  - Pick one of Percy or Chromatic (capture decision in the PR description). Snapshot the home page at mobile / tablet / desktop, hero at each of the 8 intents, Storyboard and Discover routes in both auth states.
  - Done when: CI fails on unapproved pixel diffs.

- [x] 7.3 **[P0] E2E suite green**
  - Acceptance: Design "Testing Strategy — E2E" + 3.8.
  - Prerequisite: Task 3.8 `bootstrap_cognito_dev_pool.py` must have run successfully; test credentials are provisioned by 3.8 per CI run and consumed here.
  - `e2e/auth-happy-path.spec.ts`, `e2e/auth-refresh.spec.ts`, `e2e/auth-refresh-fail.spec.ts`, `e2e/anon-to-auth.spec.ts` all pass against the dedicated dev pool.
  - Done when: nightly CI runs these on green.

- [x] 7.4 **[P0] Drop-in solutions parity**
  - Acceptance: Req 2.7.1–2.7.3.
  - Add `tests/backend/test_solutions_parity.py` — for each challenge file, confirm the code inside its `# === CHALLENGE N: START/END ===` block matches the contents of the corresponding `solutions/moduleM/<relative path>` file byte-for-byte (ignoring trailing newline).
  - Done when: drift between challenge blocks and solutions is detected by CI.

---

## Validation Checklist (tracks requirements.md)

- [x] Nav exactly 5 items, About in footer only — tasks 4.2, 4.9
- [x] Sign-in strip vs curated banner mutually exclusive — 4.4
- [x] ⌘K global concierge + Escape close — 4.1, 4.10
- [x] Hero rotation pauses on hover, progress bar resumes from pause — 4.3
- [x] Product grid re-sorts on preference change — 4.6, 3.6, 5.3
- [x] Parallax timing matches `storefront.md` — 4.6
- [x] 9 challenges total (1/3/5 split) — 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, (3.1 + 3.2 + 5.1 + 5.2 + 5.3 for C9)
- [x] C9 is four files with challenge blocks — 3.1, 3.2, 5.1, 5.2, 5.3
- [x] Storyboard is 3-card grid — 4.8
- [x] Storyboard and Discover routes render — 4.11, 4.12
- [x] Cognito + AgentCore Identity is real — 3.1, 3.2, 3.3, 3.8
- [x] Preferences persist via `agentcore_memory.py` — 2.6, 3.4
- [x] httpOnly cookies only (no localStorage) — 3.3, 5.1
- [x] Orchestrator Haiku 4.5 @ 0.0, specialists Opus 4.6 @ 0.2 — 2.3, 2.4
- [x] Tool pattern enforced — 2.2, 7.4
- [x] Defers to `catalog-enrichment` and `customer-support-agent` — tasks 2.1, 2.2, 3.6, 2.4

---

## Definition of Done for the spec

All tasks in Layers 1–6 marked complete; all Layer 7 verification tasks green in CI; every checklist row above ticked; no tasks from the out-of-scope list (CloudFormation, IAM, bootstrap scripts, lab guides) landed in this PR series.
