# Pellier Storefront — Kiro Spec Prompt

**For:** AWS re:Invent 2026 workshop **Build Agentic AI-Powered Search with Amazon Aurora PostgreSQL** (2-hour Workshop + 1-hour Builders Session).

**What this produces:** `requirements.md`, `design.md`, and `tasks.md` specifying the full Pellier storefront — UI, backend, authentication, personalization, and the nine workshop challenges.

**Prerequisites:**
Repo-wide conventions are captured in `.kiro/steering/`:

- `project.md` — module structure, directories, database high-level
- `tech.md` — tech stack, model IDs, dependencies
- `coding-standards.md` — Python and TypeScript patterns, agent/tool naming
- `database.md` — schema, pgvector patterns, query conventions
- `workshop-content.md` — lab content guidelines
- `storefront.md` — customer-facing copy rules, design tokens, nav, intents, auth UX

Kiro picks these up automatically. This spec builds on them and does not restate them.

**Related specs already exist:**

- `catalog-enrichment` — product table DDL, tagging pipeline, embedding generation
- `customer-support-agent` — one of the five specialist agents

This spec references but does not duplicate their scope.

---

## How to use

1. Paste the `# Kiro Spec Request` section below into Kiro's spec chat
2. Review and iterate on the generated `requirements.md`
3. Approve → Kiro generates `design.md`
4. Approve → Kiro generates `tasks.md`
5. Execute tasks

---

# Kiro Spec Request

You are building the **Pellier Storefront** feature — the full customer-facing application that participants extend through nine progressive challenges during a 2-hour Workshop or 1-hour Builders Session.

This spec covers the storefront UI, the FastAPI backend that powers it, the Cognito + AgentCore Identity authentication flow, the personalization engine, and the nine challenge scaffolds. It does NOT cover the data catalog pipeline (see `catalog-enrichment` spec) or the customer support specialist agent (see `customer-support-agent` spec). Reference them where relevant.

All repo-wide conventions (tech stack, tool/agent naming, coding standards, database patterns, design tokens, copy rules, nav structure, intents, product tags, auth UX) live in `.kiro/steering/`. Do not restate them — use them.

Assume everything in steering is authoritative. If any section of this spec appears to conflict with steering, steering wins. Flag the conflict in your output rather than silently resolving.

---

## The product experience (shopper view)

Build a single-page boutique storefront titled **Pellier — Summer Edit No. 06**. Golden hour editorial aesthetic. Customer-facing copy follows the rules in `storefront.md` steering.

### Layout

Top-to-bottom page structure:

1. **Announcement bar** — dusk background, 11px tracking-[0.12em]: _"Free shipping on orders over $150 · Returns within 30 days · Summer Edit No. 06 is now live"_
2. **Sticky header** — nav structure from `storefront.md` steering
3. **Hero stage** (described below)
4. **Sign-in strip** OR **Curated banner** (mutually exclusive, based on auth state — see `storefront.md` steering)
5. **Live status strip** — _"Live inventory · refreshed daily · curated by hand"_ + shipping/returns/secure checkout links
6. **Category filter chips** — horizontal scroll: All (dusk fill, selected), Linen, Dresses, Accessories, Outerwear, Footwear, Home
7. **Product grid** (described below)
8. **Multi-turn refinement panel** — white card, B mark, _"Pellier here, want me to narrow this down?"_ + 4 filter chips (Under $100, Ships by Friday, Gift-wrappable, From smaller makers)
9. **From the Storyboard** — 3-card teaser grid per `storefront.md` steering
10. **Footer** — 5 columns per `storefront.md` steering
11. **Floating ⌘K pill** — global concierge shortcut per `storefront.md` steering

### Hero stage (cinematic product showcase)

- Full-bleed product image in rounded rectangle (520px mobile, 640px desktop), single premium drop shadow, no double border
- Cross-fades to a new product every 7.5 seconds across the 8 rotating intents from `storefront.md` steering
- Each image has a `slow-zoom` Ken Burns effect (14s alternate, scale 1.02 → 1.08)
- **Floating info card top-left** (max-width ~400px, glass-morphic cream, 24px rounded corners, soft shadow):
  - "Someone just asked" breadcrumb row at top with small B mark + pulse dot
  - Intent query in large italic Fraunces (22–26px), in quotes
  - Product details row: brand, color, name (17–19px Fraunces), price, star rating, review count
  - "Add to bag" primary + circular heart button
  - Thin divider, then 10px mono "Matched on: [attributes]" footnote + "340 ms" latency stamp
- **Floating search pill bottom-center** — glass cream, fully rounded, 560px max width:
  - Small B mark avatar (left)
  - "Tell Pellier what you're looking for..." placeholder
  - Blinking terracotta caret
  - "Ask Pellier" primary button (right)
- **Corner chips:**
  - Top-left: dark glass "Someone just asked" breadcrumb with white B mark (mobile only)
  - Top-right: cream glass "Curated for you" chip with accent pulse dot
- **Below image, same rounded container:**
  - "Others are asking right now" ticker: horizontal row of italic quoted chips (all 8 intents). Active chip is ink-filled. Clicking any chip jumps the stage to that intent and resets auto-rotation.
  - 2px terracotta progress bar fills over 7.5 seconds (resets on intent change)
  - Rotation pauses on hover anywhere on the stage; progress bar freezes and resumes from paused position

### Product grid (9 cards, soft parallax reveal)

3-col desktop, 2-col tablet, 1-col mobile, `aspect-[4/5]` image cards.

Parallax timing follows the `parallax-card` animation spec in `storefront.md` steering (1100–1200ms ease-out-expo, 220ms stagger, IntersectionObserver threshold 0.05).

Each card contains:

- Warm wash overlay on image
- Optional badge (EDITOR'S PICK / BESTSELLER / JUST IN) top-left of image
- Heart button top-right of image (fades in on hover)
- Brand + color row
- Product name
- Price + rating
- **Agent reasoning chip** below thin divider: small B mark + italic one-liner. Four rotating styles across the 9 cards:
  - "Picked because..." (picked style)
  - "Matched on: attr1 · attr2 · attr3" (matched style)
  - "Price watch: $X below category average. Only N left." (pricing style, urgent clause in terracotta)
  - "Gift-ready: signature packaging, arrives tomorrow" (context style)
- "Add to bag" secondary button (full-width at bottom)

### Personalization engine

When the user is authenticated with saved preferences, the backend sorts products by **match score** (count of overlapping tags with user preferences). Products are tagged per the table in `storefront.md` steering. Frontend re-renders the grid on preference save, triggering parallax re-observation.

Preferences are stored in AgentCore Memory keyed by the verified Cognito user_id (from Challenge 9).

---

## Authentication flow

The full auth modal, preferences onboarding modal, preference groups, and on-save behavior are specified in `storefront.md` steering. This spec adds only the API-level details:

### Full auth sequence

```
Browser → Cognito Hosted UI /authorize
       → Cognito federates to IdP (Google/Apple/email)
       → Cognito exchanges code for tokens
       → Redirect to /api/auth/callback?code=<code>
FastAPI → Exchange code at Cognito /oauth2/token
       → Verify tokens via Cognito JWKS (cached 1h TTL)
       → Extract sub, email, given_name
       → Set httpOnly Secure SameSite=Lax cookies (access, id, refresh)
       → Redirect to /
Every authenticated API call:
       → Authorization: Bearer <access_token> OR cookie
       → FastAPI JWT middleware validates via JWKS (Challenge 9.1)
       → AgentCore Identity wraps context with verified user_id (Challenge 9.2)
       → AgentCore Memory scoped by user_id via agentcore_memory.py
       → Agents receive verified user context
       → Personalization reads prefs from AgentCore Memory
```

### On preference save

1. `POST /api/user/preferences` with JWT
2. Backend validates JWT, extracts user_id
3. AgentCore Memory writes at `user:{user_id}:preferences` via agentcore_memory.py
4. Frontend closes modal, flashes curated banner with fade-slide-up animation
5. Re-fetches `/api/products?personalized=true` — backend reads prefs from AgentCore Memory, sorts by tag match score, returns ranked list
6. Grid re-renders with parallax stagger
7. Account button updates to "Hi, [given_name]"

---

## Backend API surface

```
# Auth
GET    /api/auth/signin?provider=<google|apple|email>   Redirect to Cognito Hosted UI
GET    /api/auth/callback?code=<code>&state=<state>     Cognito OAuth callback
GET    /api/auth/me                                      Current user from verified JWT
POST   /api/auth/logout                                  Clear cookies, revoke tokens

# User preferences (AgentCore Memory, via agentcore_memory.py)
GET    /api/user/preferences
POST   /api/user/preferences

# Products + search
GET    /api/products?personalized=<bool>&sort=<...>      Sorts by prefs if authenticated
GET    /api/products/{id}
POST   /api/search                                       { query } → ranked results via hybrid_search.py

# Agent
POST   /api/agent/chat                                   { message, session_id? }, SSE stream
GET    /api/agent/session/{id}

# Inventory
GET    /api/inventory                                    Live status for status strip
```

All authenticated endpoints require valid Cognito JWT via `Authorization: Bearer <token>` OR httpOnly `access_token` cookie. JWT verification uses Cognito JWKS (1h cache). Unauthenticated endpoints still work — just without personalization.

---

## The nine workshop challenges

Challenge files ship with complete solution code in `# === CHALLENGE N: START/END ===` blocks per `workshop-content.md` steering.

Tool and agent naming follows `coding-standards.md` and `workshop-content.md` steering. Temperature follows `coding-standards.md` (0.0 for orchestrator with Claude Haiku 4.5, 0.2 for specialists with Claude Opus 4.6).

### Module 1 — Smart Search (Workshop 30 min / Builders 15 min)

- **C1:** `_vector_search(self, embedding, limit, ef_search, iterative_scan=True)` on `HybridSearchService` in `pellier/backend/services/hybrid_search.py`
  - pgvector cosine distance (`<=>`) with CTE pattern per `database.md` steering
  - HNSW `ef_search` per-query tuning via `SET LOCAL`
  - Iterative scan `'relaxed_order'` when `iterative_scan=True`
  - Caller passes pre-computed embedding (the service does not call Bedrock itself)

### Module 2 — Agentic AI (Workshop 40 min / Builders 20 min)

- **C2:** `get_trending_products()` in `pellier/backend/services/agent_tools.py`, `@tool`-decorated per `coding-standards.md`
  - Returns JSON-serialized string via `json.dumps()`
  - Handles `_db_service` unavailability and error cases per coding-standards error pattern
  - Uses `_run_async()` helper for async-to-sync bridging

- **C3:** `product_recommendation_agent` in `pellier/backend/agents/curator.py`
  - Strands Agent wrapping `BedrockModel(model_id=settings.BEDROCK_CHAT_MODEL)` with `temperature=0.2`
  - Tools: `search_products`, `get_trending_products`, `compare_products`, `get_product_by_category`
  - System prompt emphasizes warm, editorial, catalog-style reasoning — grounded in specific product attributes

- **C4:** Multi-agent orchestrator in `pellier/backend/agents/orchestrator.py`
  - Uses Claude Haiku 4.5 via `BedrockModel(model_id='global.anthropic.claude-haiku-4-5-20251001-v1:0')` with `temperature=0.0`
  - Routes via Strands "Agents as Tools" pattern
  - Intent classification priority per `coding-standards.md`: pricing > inventory > support > search > recommendation (default)
  - Routes to five specialists: `search_agent`, `product_recommendation_agent`, `price_optimization_agent`, `inventory_restock_agent`, `customer_support_agent` (last one defined in `customer-support-agent` spec)

### Module 3 — Production Patterns (Workshop 40 min / Builders 15 min)

Infrastructure-out ordering.

- **C5:** AgentCore Runtime deployment in `pellier/backend/services/agentcore_runtime.py` — migrate orchestrator from local Strands to AgentCore Runtime
- **C6:** AgentCore STM Memory in `pellier/backend/services/agentcore_memory.py` — multi-turn session memory + user preferences keyed by Cognito user_id (from C9)
- **C7:** AgentCore MCP Gateway in `pellier/backend/services/agentcore_gateway.py` — expose tools via MCP for external agent consumers
- **C8:** OpenTelemetry in `pellier/backend/services/otel_trace_extractor.py` — agent trace extraction for `/inspector` view
- **C9 (THE CAPSTONE):** Agent Identity — Cognito + AgentCore Identity. Four files:
  1. `pellier/backend/services/cognito_auth.py` — JWKS client, JWT validator, FastAPI middleware extracting verified `user_id` into `request.state.user`
  2. `pellier/backend/services/agentcore_identity.py` — AgentCore Identity wrapper; `get_verified_user_context(request)` returns user_id + session_id namespace
  3. `pellier/frontend/src/utils/auth.ts` — Cognito hosted UI redirect helpers, `useAuth()` context, silent token refresh
  4. `pellier/frontend/src/components/AuthModal.tsx` + `pellier/frontend/src/components/PreferencesModal.tsx` — auth and preferences UIs per `storefront.md` steering

**Why C9 is the capstone:** participants spent M1 retrieving data, M2 reasoning over it, early M3 deploying it. C9 closes the loop by wiring real identity to the personalization they've seen working the entire workshop.

---

## What you should generate

### `requirements.md`

User stories for both audiences (shopper + workshop participant) with EARS-format acceptance criteria (Event, Actor, Response, State).

Sections:

1. **Shopper experience** — every storefront feature (hero stage, sign-in strip/curated banner, product grid with parallax, intent rotation, reasoning chips, refinement panel, Storyboard, footer, ⌘K pill)
2. **Workshop participant experience** — read-and-test vs build expectations per format, time budgets, "done when" signals, challenge file structure
3. **Backend API** — every endpoint with request/response schemas
4. **Authentication** — Cognito User Pool config, IdP federation (Google + Apple + email/password), JWT middleware, AgentCore Identity integration, preferences persistence
5. **Non-functional** — sub-500ms search latency, sub-2s agent response, sub-200ms auth check, parallax at 60fps, responsive breakpoints (mobile/tablet/desktop)
6. **Data dependencies** — relies on `catalog-enrichment` spec for the `tags text[]` column and seeded products
7. **Integration requirements** — references `customer-support-agent` spec for the customer support specialist; uses `agentcore_memory.py` for session + preference storage

### `design.md`

- **Architecture diagram** (Mermaid): browser → Cognito Hosted UI → FastAPI → (AgentCore Identity → AgentCore Memory → AgentCore Runtime → AgentCore Gateway → Aurora pgvector → Bedrock: Opus 4.6 + Haiku 4.5 + Cohere Embed v4 + Cohere Rerank v3.5)
- **Sequence diagrams:**
  1. Vector search (query → embedding → pgvector similarity → ranked results)
  2. Agent reasoning with tool use (user message → orchestrator (Haiku) → specialist (Opus) → tool call → response with trace)
  3. Multi-turn conversation with STM
  4. **Full auth + preferences flow** — diagram every step from sign-in click through Cognito redirect, Google OAuth, callback, JWT cookies, preferences fetch, save, product grid re-sort
- **Component tree** for React frontend
- **Data models** — TypeScript interfaces (Product, Intent, AgentResponse, SearchResult, User, Preferences, AuthTokens). Product table DDL lives in `catalog-enrichment` spec — reference it, do not duplicate
- **Service layer** — `HybridSearchService`, `EmbeddingService`, `AgentOrchestrator`, specialists, tools, `CognitoAuthService`, `AgentCoreIdentityService`
- **Error handling** — embedding API failure, agent timeout, empty results, auth failure recovery with silent refresh → deep-link signin
- **Testing strategy** — pytest for services, Playwright for auth e2e with Cognito dev pool, Percy or Chromatic for visual regression

### `tasks.md`

Numbered, dependency-ordered tasks. Each with: title, acceptance criteria, files to create/modify, test verification, "done when" signal.

Group by layer:

**[Frontend components]**

- Updated nav (Home · Shop · Storyboard · Discover + Account with state) per `storefront.md`
- Cinematic stage with intent rotation + progress bar + hover pause + ⌘K handler
- Floating info card + bottom-center search pill
- Product grid with parallax IntersectionObserver wrapper (ease-out-expo timing per `storefront.md`)
- Sign-in strip + curated banner with auth-state-driven show/hide
- Storyboard 3-card grid
- Footer expansion to 5 columns with About content
- AuthModal + PreferencesModal components (C9 deliverables)

**[Backend services]**

- Challenge scaffolds C1–C8 with `# === CHALLENGE N: START/END ===` blocks and complete solution code
- `/api/auth/*` routes
- `/api/user/preferences` routes with JWT middleware
- `/api/products?personalized=true` reading from AgentCore Memory via `agentcore_memory.py`

**[Backend challenge 9 scaffolds]**

- `cognito_auth.py` (C9.1)
- `agentcore_identity.py` (C9.2)

**[Frontend challenge 9 scaffolds]**

- `auth.ts` with `useAuth()` context (C9.3)
- `AuthModal.tsx`, `PreferencesModal.tsx` (C9.4)

**[Configuration]**

- `copy.ts` (frontend) and `copy.py` (backend) — all user-facing strings centralized
- OAuth redirect URI env variables
- React auth context provider wired at App root

Tasks for CloudFormation, IAM, bootstrap scripts, and lab guides are **out of scope for this spec** — they live in the companion Claude Code prompts at `.claude/prompts/infrastructure.md`, `workshop-content.md`, `builders-content.md`.

---

## Validation checklist (spec-specific)

Before delivering the spec, verify:

- [ ] Nav has exactly 5 items: Home, Shop, Storyboard, Discover, Account (per `storefront.md`)
- [ ] About content moved to footer, not top nav
- [ ] Sign-in strip hides when authenticated; curated banner shows when authenticated with prefs
- [ ] ⌘K globally opens concierge; Escape and second ⌘K close it
- [ ] Intent rotation pauses on hover; progress bar freezes and resumes
- [ ] Product grid re-sorts by preference match when prefs change
- [ ] Parallax specifications match `storefront.md` (1100–1200ms ease-out-expo, 220ms stagger, threshold 0.05)
- [ ] Challenge count: 9 total (1 in M1, 3 in M2, 5 in M3)
- [ ] C9 is four files (two backend + two frontend), all with challenge blocks
- [ ] Storyboard is a 3-card grid (not a single editorial block)
- [ ] Auth uses real Cognito + AgentCore Identity (not simulation)
- [ ] Preferences persist to AgentCore Memory (via `agentcore_memory.py`) keyed by verified Cognito user_id
- [ ] httpOnly Secure cookies for tokens (no localStorage)
- [ ] Orchestrator uses Claude Haiku 4.5 at temperature 0.0 per `coding-standards.md`
- [ ] Specialists use Claude Opus 4.6 at temperature 0.2 per `coding-standards.md`
- [ ] Tools use `@tool` decorator, return JSON strings, handle errors per `coding-standards.md`
- [ ] Spec defers to `catalog-enrichment` for product table DDL + tagging
- [ ] Spec defers to `customer-support-agent` for the customer support specialist
- [ ] All tool and agent names match `workshop-content.md` and `coding-standards.md` exactly

Generate the complete spec now.
