# Pellier Storefront — Requirements

## Introduction

This spec defines the full customer-facing Pellier storefront and the workshop scaffolding that AWS re:Invent 2026 participants extend through nine progressive challenges. It covers the storefront UI, the FastAPI backend that powers it, the Cognito + AgentCore Identity authentication flow, the preference-based personalization engine, and the nine challenge scaffolds across three modules.

Repo-wide conventions live in `.kiro/steering/` and are authoritative:

- `project.md` — modules, directories, database overview
- `tech.md` — stack, model IDs, dependencies
- `coding-standards.md` — Python and TypeScript patterns, agent/tool naming, temperatures
- `database.md` — schema, pgvector patterns
- `workshop-content.md` — lab content guidelines, exact agent/tool names
- `storefront.md` — copy rules, design tokens, nav, intents, auth UX, product tags

This spec builds on them without restating them. Where conflicts exist between the source prompt and steering, steering wins and the conflict is flagged below.

### Conflicts with source prompt (resolved)

1. **Backend path prefix.** The source prompt references paths under `pellier/backend/app/services/…` and `pellier/backend/app/agents/…`. Steering (`coding-standards.md`, `project.md`) and the repo use `pellier/backend/services/…` and `pellier/backend/agents/…` with no `app/` layer. **Resolved:** this spec uses the steering/repo paths throughout.
2. **Aurora version.** Earlier, `tech.md` pinned 17.5 while `project.md` said "currently 17.7". **Resolved:** `tech.md` has been updated to track "latest available at workshop time (currently 17.7)" and this spec does not pin a point release.

No other steering conflicts surfaced.

### Scope boundaries

- **In scope:** storefront UI, backend API, auth flow, preferences engine, C1–C9 challenge scaffolds, visible acceptance criteria.
- **Out of scope (own specs):**
  - Product table DDL, tagging pipeline, embedding generation → `catalog-enrichment`
  - Customer support specialist agent → `customer-support-agent`
- **Out of scope (own docs):** CloudFormation, IAM, bootstrap scripts, lab guide prose → `.claude/prompts/infrastructure.md`, `workshop-content.md`, `builders-content.md`.

### Audiences

Two distinct audiences consume this product:

- **Shoppers** — visitors to the storefront during demos and self-exploration.
- **Workshop participants** — developers completing the 2-hour Workshop or 1-hour Builders Session by editing code between `# === CHALLENGE N: START/END ===` blocks.

Requirements below are grouped by audience where the distinction matters.

---

## 1. Shopper Experience

### Requirement 1.1 — Page structure and announcement bar

**User story:** As a shopper, I want a consistent top-to-bottom boutique layout so the experience feels curated and coherent.

**Acceptance criteria (EARS):**

- 1.1.1 WHEN the page loads THEN the browser SHALL display, in order: announcement bar, sticky header, hero stage, sign-in-strip-or-curated-banner, live status strip, category filter chips, product grid, refinement panel, Storyboard 3-card grid, 5-column footer, floating ⌘K pill.
- 1.1.2 WHEN the announcement bar renders THEN it SHALL display the exact copy `Free shipping on orders over $150 · Returns within 30 days · Summer Edit No. 06 is now live` in 11px with `tracking-[0.12em]` on a dusk background.
- 1.1.3 WHEN the viewport scrolls THEN the sticky header SHALL remain visible with the nav structure defined in `storefront.md` (Home · Shop · Storyboard · Discover · Account + centered wordmark + right actions).
- 1.1.4 WHEN the page title is requested THEN the `<title>` SHALL be `Pellier — Summer Edit No. 06`.

### Requirement 1.2 — Top navigation and Account state

**User story:** As a shopper, I want to see navigation that matches my signed-in state so I know whether personalization is active.

**Acceptance criteria (EARS):**

- 1.2.1 WHEN the sticky header renders THEN it SHALL contain exactly five nav items: Home (current-page ink highlight), Shop, Storyboard, Discover, and the Account button.
- 1.2.2 WHEN the user is signed out THEN the Account button SHALL show the generic account icon plus the label `Account`.
- 1.2.3 WHEN the user is signed in AND `/api/auth/me` returns a verified `given_name` claim THEN the Account button SHALL show the icon plus `Hi, {given_name}` using the Cognito `given_name` claim.
- 1.2.4 WHEN any previously valid About/Journal/Shop-variant nav item appears in the header THEN the build SHALL fail code review; About content lives in the footer (per `storefront.md`).
- 1.2.5 WHEN the viewport is narrower than the mobile breakpoint THEN the `Ask Pellier` text link SHALL be hidden and the centered wordmark SHALL remain visible.

### Requirement 1.3 — Hero stage with rotating intents

**User story:** As a shopper, I want a cinematic hero that shows real customer questions pairing with real products so I understand what Pellier can do in 7 seconds.

**Acceptance criteria (EARS):**

- 1.3.1 WHEN the hero stage mounts THEN it SHALL cross-fade through the 8 intents listed in `storefront.md` in order, advancing every 7.5 seconds.
- 1.3.2 WHEN each intent becomes active THEN the stage SHALL show the hero image (rounded rectangle, 520px on mobile, 640px on desktop, single premium drop shadow, no double border), with `slow-zoom` Ken Burns (14s alternate, scale 1.02 → 1.08).
- 1.3.3 WHEN the intent `a thoughtful gift for someone who runs` is active THEN the hero SHALL render the `productOverride` from `storefront.md`: Featherweight Trail Runner, $168, 4.9 rating, athletic running shoe image.
- 1.3.4 WHEN the active intent changes THEN the floating info card (top-left, max-width ~400px, glass cream, 24px corners, soft shadow) SHALL render: `Someone just asked` breadcrumb with small B mark + pulse dot, intent query in italic Fraunces 22–26px wrapped in curly quotes, product details row (brand · color · name in Fraunces 17–19px · price · star rating · review count), `Add to bag` primary button, circular heart button, thin divider, 10px mono `Matched on:` footnote, and `340 ms` latency stamp.
- 1.3.5 WHEN the hero stage renders THEN a bottom-center floating search pill (glass cream, fully rounded, 560px max width) SHALL contain the B mark avatar, `Tell Pellier what you're looking for...` placeholder, blinking terracotta caret, and right-side `Ask Pellier` primary button.
- 1.3.6 WHEN the user hovers anywhere on the stage THEN intent rotation SHALL pause, the 2px terracotta progress bar SHALL freeze at its current fill, and ticker chips SHALL remain clickable.
- 1.3.7 WHEN the user's cursor leaves the stage THEN rotation SHALL resume and the progress bar SHALL continue from the paused position (not restart).
- 1.3.8 WHEN the user clicks a ticker chip below the image THEN the stage SHALL jump to that intent immediately, reset the progress bar to 0%, and restart the 7.5-second timer.
- 1.3.9 WHEN the search pill input matches any keyword in the 8 intents THEN pressing Enter SHALL jump the stage to the matched intent.
- 1.3.10 WHEN the stage is on mobile THEN the dark glass `Someone just asked` breadcrumb SHALL be visible top-left; WHEN on desktop THEN only the cream `Curated for you` chip SHALL show top-right.

### Requirement 1.4 — Sign-in strip vs curated banner (mutually exclusive)

**User story:** As a shopper, I want a single clear band below the hero that reflects my current personalization state.

**Acceptance criteria (EARS):**

- 1.4.1 WHEN the user is signed out AND has not dismissed the strip this session THEN the sign-in strip SHALL render per `storefront.md` (cream-warm gradient, B mark + pulse dot, `PERSONALIZED VISIONS` eyebrow, italic Fraunces `Sign in and watch Pellier tailor the storefront to you.`, `Sign in for personalized visions` CTA, `Not now` dismiss).
- 1.4.2 WHEN the user dismisses the strip THEN `sessionStorage.setItem('pellier.signinStrip.dismissed', 'true')` SHALL be called and the strip SHALL not reappear until a new session.
- 1.4.3 WHEN the user is signed in AND `/api/user/preferences` returns a non-null value THEN the curated banner SHALL render per `storefront.md` (terracotta gradient, pulse dot, `CURATED FOR YOU` label, `Tailored to your preferences, {given_name}. {pref1} · {pref2} · {pref3}`, `Adjust preferences` link).
- 1.4.4 WHEN the user is signed in AND `/api/user/preferences` returns `null` THEN neither band SHALL render; the preferences onboarding modal SHALL auto-open exactly once per fresh sign-in (not on subsequent page reloads while already signed in). The specific signal used to distinguish "fresh sign-in" from "reload while signed in" (e.g., short-lived callback cookie, URL flag, or referrer check) SHALL be resolved in `design.md`.
- 1.4.5 WHEN preferences are saved THEN the curated banner SHALL appear with the `fade-slide-up` 0.6s animation.

### Requirement 1.5 — Live status strip and category chips

**User story:** As a shopper, I want a reassuring status line and a quick way to filter by category.

**Acceptance criteria (EARS):**

- 1.5.1 WHEN the status strip renders THEN it SHALL display `Live inventory · refreshed daily · curated by hand` alongside links for shipping, returns, and secure checkout.
- 1.5.2 WHEN `/api/inventory` returns a recent timestamp THEN the strip SHALL not display stale-data warnings.
- 1.5.3 WHEN the category chip row renders THEN it SHALL display in horizontal scroll order: All (dusk fill, selected), Linen, Dresses, Accessories, Outerwear, Footwear, Home.
- 1.5.4 WHEN a category chip is clicked THEN the product grid SHALL filter to that category and the chip SHALL take the dusk-fill selected state.

### Requirement 1.6 — Product grid with parallax reveal

**User story:** As a shopper, I want products to cascade into view with a luxurious feel so browsing feels like an editorial, not a catalog dump.

**Acceptance criteria (EARS):**

- 1.6.1 WHEN the viewport is desktop, tablet, or mobile THEN the grid SHALL render 3-col, 2-col, or 1-col respectively, with `aspect-[4/5]` image cards.
- 1.6.2 WHEN a card enters the viewport (IntersectionObserver threshold `0.05`, rootMargin `'0px 0px -5% 0px'`) THEN it SHALL animate from `opacity: 0; transform: translateY(56px) scale(0.975)` to `opacity: 1; transform: translateY(0) scale(1)` over 1100–1200ms with `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-expo) per `storefront.md`.
- 1.6.3 WHEN multiple cards in the same row enter the viewport THEN each subsequent card SHALL start 220ms after its left neighbor.
- 1.6.4 WHEN a card has already animated THEN subsequent scroll-backs SHALL NOT retrigger the animation (once-per-card-per-page-view).
- 1.6.5 WHEN a card renders THEN it SHALL include, in order: warm wash overlay, optional top-left badge (EDITOR'S PICK / BESTSELLER / JUST IN), top-right heart (fades in on hover), brand + color row, product name, price + rating, thin divider, agent reasoning chip, full-width `Add to bag` secondary button.
- 1.6.6 WHEN preferences are saved or changed THEN the grid SHALL re-fetch from `/api/products?personalized=true`, re-render in match-score order, and re-observe cards so parallax fires again (this is the single exception to 1.6.4, treated as a new page view).

### Requirement 1.7 — Agent reasoning chips (four rotating styles)

**User story:** As a shopper, I want to see why each product was picked so the storefront feels considered rather than automated.

**Acceptance criteria (EARS):**

- 1.7.1 WHEN the grid renders 9 showcase cards THEN reasoning chips SHALL cycle across four styles: `picked`, `matched`, `pricing`, `context`, distributed so no two adjacent cards share a style where possible.
- 1.7.2 WHEN the `picked` style renders THEN it SHALL read `Picked because {reason}` in italic Fraunces with a small B mark prefix.
- 1.7.3 WHEN the `matched` style renders THEN it SHALL read `Matched on: {attr1} · {attr2} · {attr3}` using attributes drawn from the product's tags.
- 1.7.4 WHEN the `pricing` style renders THEN it SHALL read `Price watch: ${N} below category average. Only {M} left.` with the `Only M left` clause in terracotta (`--accent`).
- 1.7.5 WHEN the `context` style renders THEN it SHALL read `Gift-ready: signature packaging, arrives tomorrow` or equivalent context copy.

### Requirement 1.8 — Multi-turn refinement panel

**User story:** As a shopper, I want a quick way to refine results without typing.

**Acceptance criteria (EARS):**

- 1.8.1 WHEN the refinement panel renders THEN it SHALL be a white card with B mark and the copy `Pellier here, want me to narrow this down?` plus four chips: `Under $100`, `Ships by Friday`, `Gift-wrappable`, `From smaller makers`.
- 1.8.2 WHEN any chip is toggled THEN the active filter set SHALL be sent to `/api/products` as a query parameter and the grid SHALL re-render with parallax re-observation.
- 1.8.3 WHEN multiple chips are active THEN filters SHALL compose with AND semantics.

### Requirement 1.9 — Storyboard teaser grid

**User story:** As a shopper, I want editorial content that reinforces the "slower kind of shopping" voice.

**Acceptance criteria (EARS):**

- 1.9.1 WHEN the Storyboard section renders THEN it SHALL be a 3-card grid (not a single editorial block).
- 1.9.2 WHEN each card renders THEN it SHALL contain an editorial image with golden wash, a category badge, a volume number, an italic Fraunces title, a 2–3 sentence excerpt, and a `Read the full vision ›` link in terracotta.
- 1.9.3 WHEN a card is hovered THEN its image SHALL scale to 1.05.
- 1.9.4 WHEN the three cards render THEN they SHALL be, in order: `MOOD FILM · Vol. 12 · Summer · A summer worth slowing for.`, `VISION BOARD · Vol. 11 · The Makers · The last clay studio in Ojai.`, `BEHIND THE SCENES · Vol. 10 · The Edit · How we chose this season.`

### Requirement 1.10 — Footer

**User story:** As a shopper, I want a complete footer with the About content I expect to find.

**Acceptance criteria (EARS):**

- 1.10.1 WHEN the footer renders THEN it SHALL have exactly 5 columns per `storefront.md`: Brand, Shop, About, Service, Storyboard newsletter.
- 1.10.2 WHEN the About column renders THEN it SHALL contain links: `Our story`, `Makers we love`, `Sustainability`, `Press`.
- 1.10.3 WHEN the bottom strip renders THEN it SHALL show `© ... · Privacy · Terms · Accessibility`.

### Requirement 1.11 — Global ⌘K concierge pill

**User story:** As a shopper, I want a global shortcut to summon Pellier from anywhere on the page.

**Acceptance criteria (EARS):**

- 1.11.1 WHEN the page renders THEN a compact dusk pill SHALL be fixed in the bottom-right corner with a small B mark, `Ask Pellier` label, and styled `⌘K` keycap.
- 1.11.2 WHEN the user presses `⌘K` on macOS or `Ctrl+K` elsewhere THEN the concierge modal SHALL toggle open/closed.
- 1.11.3 WHEN the user presses `Escape` with any modal open THEN that modal SHALL close.
- 1.11.4 WHEN the concierge modal is open and another modal (Auth, Preferences) is requested THEN the concierge SHALL close first so only one modal is visible at a time.
- 1.11.5 WHEN the ⌘K pill is clicked THEN the same toggle behavior as 1.11.2 SHALL apply.

### Requirement 1.12 — Customer-facing copy compliance

**User story:** As the brand voice, I want every user-facing string to follow the editorial rules.

**Acceptance criteria (EARS):**

- 1.12.1 WHEN any customer-facing string is authored THEN it SHALL contain zero emojis and zero em dashes per `storefront.md`.
- 1.12.2 WHEN any customer-facing string is authored THEN it SHALL NOT contain the forbidden words: `AI`, `search` (as feature noun), `intelligent`, `smart`, `agent`, `LLM`, `vector`, `embedding`.
- 1.12.3 WHEN technical references are needed THEN they SHALL appear only in 10px monospace footnotes.
- 1.12.4 WHEN centralized copy is authored THEN it SHALL live in `pellier/frontend/src/copy.ts` and `pellier/backend/storefront_copy.py` so one file review catches any regressions.

### Requirement 1.13 — Storyboard and Discover routes (minimal index pages)

**User story:** As a shopper who clicks `Storyboard` or `Discover` in the nav, I want to land on something coherent rather than a 404.

**Acceptance criteria (EARS):**

- 1.13.1 WHEN the user navigates to `/storyboard` THEN the route SHALL render a minimal index page with the header, footer, and ⌘K pill intact, the same 3-card Storyboard grid from the home page (Requirement 1.9), and a `Coming soon - the full editorial hub arrives with the next Edit.` editorial line in italic Fraunces.
- 1.13.2 WHEN the user navigates to `/discover` THEN the route SHALL render a minimal index page with the header, footer, and ⌘K pill intact. WHEN the user is signed out THEN the page SHALL prompt with the sign-in CTA and copy `Discover is tailored to you. Sign in and watch the storefront tune itself.`. WHEN the user is signed in THEN the page SHALL render the personalized product grid (`?personalized=true`) and the same `Coming soon` editorial line indicating fuller curation lands later.
- 1.13.3 WHEN either route renders THEN copy rules from Requirement 1.12 SHALL apply (no emojis, no em dashes, no forbidden words).
- 1.13.4 WHEN either route is linked from the header THEN the active nav item SHALL take the ink-highlighted current-page state described in Requirement 1.2.1.

---

## 2. Workshop Participant Experience

### Requirement 2.1 — Two delivery formats, one codebase

**User story:** As a workshop participant, I want a single codebase that supports both the 2-hour Workshop and 1-hour Builders Session.

**Acceptance criteria (EARS):**

- 2.1.1 WHEN a participant opens a challenge file THEN they SHALL find a single `# === CHALLENGE N: START ===` and matching `# === CHALLENGE N: END ===` block per challenge.
- 2.1.2 WHEN the Workshop format is delivered THEN participants SHALL delete the code between the blocks and reimplement from hints across all 9 challenges within 110 minutes of content time (M1 30 min + M2 40 min + M3 40 min).
- 2.1.3 WHEN the Builders Session format is delivered THEN participants SHALL build C1 only and read-and-test C2 through C9 within 50 minutes of content time (M1 15 min + M2 20 min + M3 15 min).
- 2.1.4 WHEN a participant pastes the drop-in solution `cp solutions/moduleN/path/file.py pellier/backend/path/file.py` and restarts the backend THEN the challenge SHALL pass its verification without further edits.

### Requirement 2.2 — Challenge file structure

**User story:** As a workshop participant, I want challenge blocks and hints placed consistently so I can find where to edit.

**Acceptance criteria (EARS):**

- 2.2.1 WHEN a challenge file ships THEN the `# === CHALLENGE N: START ===` marker SHALL appear on a line by itself, followed by complete solution code, followed by `# === CHALLENGE N: END ===` on a line by itself.
- 2.2.2 WHEN a challenge block is present THEN the solution code between the markers SHALL be functional on its own; removing the block and replacing with hints SHALL produce the participant-facing state.
- 2.2.3 WHEN agent/tool names appear in challenge code THEN they SHALL match the exact names in `workshop-content.md` steering (tools: `search_products`, `get_trending_products`, `get_price_analysis`, `get_product_by_category`, `get_inventory_health`, `get_low_stock_products`, `restock_product`, `compare_products`, `get_return_policy`; agents: `search_agent`, `product_recommendation_agent`, `price_optimization_agent`, `inventory_restock_agent`, `customer_support_agent`).
- 2.2.4 WHEN a tool is authored THEN it SHALL use the `@tool` decorator from `strands`, return a JSON-serialized string, check `_db_service` availability, use `_run_async()` for async DB calls, and return `json.dumps({"error": str(e)})` on exception — per `coding-standards.md`.

### Requirement 2.3 — Module 1: Smart Search (C1)

**User story:** As a workshop participant, I want to implement pgvector similarity search so I understand retrieval end-to-end.

**Acceptance criteria (EARS):**

- 2.3.1 WHEN C1 is opened at `pellier/backend/services/hybrid_search.py` THEN the challenge block SHALL contain the method signature `async def _vector_search(self, embedding, limit, ef_search, iterative_scan=True)` on `HybridSearchService`.
- 2.3.2 WHEN C1 is implemented THEN the query SHALL use the CTE pattern `WITH query_embedding AS (SELECT %s::vector as emb)` per `database.md` and `<=>` cosine distance for similarity.
- 2.3.3 WHEN C1 runs THEN it SHALL call `SET LOCAL hnsw.ef_search = %s` using the passed `ef_search` value.
- 2.3.4 WHEN `iterative_scan=True` THEN C1 SHALL call `SET LOCAL hnsw.iterative_scan = 'relaxed_order'`.
- 2.3.5 WHEN C1 runs THEN the method SHALL accept a pre-computed embedding from the caller and SHALL NOT call Bedrock Embed itself.
- 2.3.6 WHEN C1 is done THEN the verification step SHALL be: query `linen shirt` returns ≥5 results in <500ms with non-zero similarity scores.

### Requirement 2.4 — Module 2: Agentic AI (C2–C4)

**User story:** As a workshop participant, I want to add a tool, build a specialist agent, and wire an orchestrator so I see the Agents-as-Tools pattern concretely.

**Acceptance criteria (EARS):**

- 2.4.1 WHEN C2 is opened at `pellier/backend/services/agent_tools.py` THEN the challenge block SHALL implement `get_trending_products()` as `@tool`-decorated, returning a JSON string of the top-trending products; it SHALL check `_db_service` availability, use `_run_async()`, and return `json.dumps({"error": str(e)})` on exception.
- 2.4.2 WHEN C2 is done THEN the verification SHALL be: calling the tool directly in a REPL returns a parseable JSON string with ≥3 products.
- 2.4.3 WHEN C3 is opened at `pellier/backend/agents/curator.py` THEN the challenge block SHALL instantiate `product_recommendation_agent` as a Strands `Agent` wrapping `BedrockModel(model_id=settings.BEDROCK_CHAT_MODEL)` with `temperature=0.2` and tools `[search_products, get_trending_products, compare_products, get_product_by_category]`.
- 2.4.4 WHEN C3's system prompt is authored THEN it SHALL emphasize warm, editorial, catalog-style reasoning grounded in specific product attributes.
- 2.4.5 WHEN C3 is done THEN the verification SHALL be: calling the agent with `something for warm evenings out` returns a response that names at least one specific product (brand + color + price) AND that product's `tags` column SHALL include at least one of `evening`, `warm`, `dresses`, or `outerwear` (so relevance, not just mention, is checked). Expected matches include Sundress in Washed Linen or Cashmere-Blend Cardigan; an irrelevant recommendation such as Signature Straw Tote SHALL fail verification.
- 2.4.6 WHEN C4 is opened at `pellier/backend/agents/orchestrator.py` THEN the challenge block SHALL instantiate the orchestrator with `BedrockModel(model_id='global.anthropic.claude-haiku-4-5-20251001-v1:0')`, `temperature=0.0`, and five specialist tools following the Strands "Agents as Tools" pattern.
- 2.4.7 WHEN C4 routes a query THEN intent classification priority SHALL be `pricing > inventory > support > search > recommendation (default)` per `coding-standards.md`.
- 2.4.8 WHEN C4 is done THEN the verification SHALL be: five representative queries (one per specialist intent) each route to the expected specialist, observable via trace logs.

### Requirement 2.5 — Module 3: Production Patterns (C5–C8)

**User story:** As a workshop participant, I want to layer production patterns on top of the working agent so I see the path from prototype to deployable.

**Acceptance criteria (EARS):**

- 2.5.1 WHEN C5 is opened at `pellier/backend/services/agentcore_runtime.py` THEN the challenge block SHALL migrate the orchestrator from local Strands execution to AgentCore Runtime and expose a `run_agent_on_runtime(message, session_id)` entry point.
- 2.5.2 WHEN C6 is opened at `pellier/backend/services/agentcore_memory.py` THEN the challenge block SHALL implement two concerns: (a) short-term memory for multi-turn session history keyed by `session_id`, (b) persistent user preferences keyed by `user:{user_id}:preferences` where `user_id` comes from verified Cognito JWT (delivered by C9).
- 2.5.3 WHEN C7 is opened at `pellier/backend/services/agentcore_gateway.py` THEN the challenge block SHALL expose the agent tools via the MCP streamable HTTP transport so an external agent client can discover and invoke them.
- 2.5.4 WHEN C8 is opened at `pellier/backend/services/otel_trace_extractor.py` THEN the challenge block SHALL extract OpenTelemetry spans produced by the agent run and format them for the `/inspector` view.

### Requirement 2.6 — Module 3 Capstone: Agent Identity (C9)

**User story:** As a workshop participant, I want to wire real Cognito + AgentCore Identity into the storefront so personalization is bound to my verified user, closing the loop from retrieval through reasoning to identity.

**Acceptance criteria (EARS):**

- 2.6.1 WHEN C9 ships THEN it SHALL span exactly four files, each with its own `# === CHALLENGE 9.N: START/END ===` block:
  1. `pellier/backend/services/cognito_auth.py`
  2. `pellier/backend/services/agentcore_identity.py`
  3. `pellier/frontend/src/utils/auth.ts`
  4. `pellier/frontend/src/components/AuthModal.tsx` + `pellier/frontend/src/components/PreferencesModal.tsx` (both gated by block 9.4)
- 2.6.2 WHEN C9.1 is done THEN `cognito_auth.py` SHALL provide a JWKS client with 1-hour TTL cache, a JWT validator, and a FastAPI middleware/dependency that extracts the verified `user_id`, `email`, and `given_name` into `request.state.user`.
- 2.6.3 WHEN C9.1 validates a token THEN it SHALL reject expired tokens, tokens with invalid `iss`, `aud`, or `token_use`, and tokens signed with keys not in the Cognito JWKS.
- 2.6.4 WHEN C9.2 is done THEN `agentcore_identity.py` SHALL expose `get_verified_user_context(request)` returning `user_id` + a session namespace usable by `agentcore_memory.py`.
- 2.6.5 WHEN C9.3 is done THEN `auth.ts` SHALL provide Cognito Hosted UI redirect helpers for `google`, `apple`, and `email`, a `useAuth()` React context, and silent token refresh via the `refresh_token` cookie.
- 2.6.6 WHEN C9.4 is done THEN `AuthModal.tsx` SHALL render exactly the structure in `storefront.md` (three provider buttons, disclaimer, `Secured by AgentCore Identity` 10px mono footer) and `PreferencesModal.tsx` SHALL render the four preference groups (Vibe 6 cards, Colors 5 pill chips, Where 6 pill chips, Categories 6 pill chips) with the selected-chip visual state from `storefront.md`.
- 2.6.7 WHEN C9 is done THEN the capstone verification SHALL be: sign in with Google, save preferences, observe the product grid re-sort by match score, sign out, confirm Account button returns to `Account` and the sign-in strip reappears.

### Requirement 2.7 — Drop-in solutions path

**User story:** As a workshop participant who is short on time, I want to paste a working solution and keep moving.

**Acceptance criteria (EARS):**

- 2.7.1 WHEN a participant runs `cp solutions/moduleN/<relative path> pellier/backend/<relative path>` THEN the copied file SHALL contain the complete solution code identical to what lives inside the `# === CHALLENGE N: START/END ===` block.
- 2.7.2 WHEN the backend is restarted after a drop-in paste THEN the challenge verification step SHALL pass without further edits.
- 2.7.3 WHEN solutions are organized on disk THEN they SHALL live under the named module folders: `solutions/the-quiet-search/`, `solutions/closing-marcos-gap/`, and `solutions/the-paper-trail/` (per `project.md`).

---

## 3. Backend API

### Requirement 3.1 — Auth endpoints

**User story:** As the frontend, I want standardized auth endpoints so the sign-in flow works across IdPs without special cases.

**Acceptance criteria (EARS):**

- 3.1.1 WHEN `GET /api/auth/signin?provider=<google|apple|email>` is called THEN the backend SHALL 302-redirect to the Cognito Hosted UI `/oauth2/authorize` with the matching `identity_provider` param (`Google`, `SignInWithApple`, omitted for email), the configured `client_id`, `response_type=code`, `scope=openid email profile`, a generated `state` (CSRF) value, and `redirect_uri=/api/auth/callback`.
- 3.1.2 WHEN `GET /api/auth/callback?code=<code>&state=<state>` is called THEN the backend SHALL validate `state` against the stored value, POST to Cognito `/oauth2/token` with `grant_type=authorization_code`, verify the returned tokens via Cognito JWKS, set three httpOnly Secure SameSite=Lax cookies (`access_token`, `id_token`, `refresh_token`), and 302-redirect to `/`.
- 3.1.3 WHEN `GET /api/auth/me` is called THEN the backend SHALL validate the JWT from the `Authorization: Bearer` header or `access_token` cookie and return `{ user_id, email, given_name }` on success or `401` on failure.
- 3.1.4 WHEN `POST /api/auth/logout` is called THEN the backend SHALL clear the three cookies, call Cognito `/oauth2/revoke` on the refresh token, and return `{ "ok": true }`.
- 3.1.5 WHEN any auth endpoint encounters a Cognito error THEN it SHALL log the error with redaction of tokens and return a non-leaking error envelope `{ "error": "auth_failed" }` with the appropriate HTTP status.

### Requirement 3.2 — User preference endpoints

**User story:** As the frontend, I want to read and write the signed-in user's preferences so personalization survives page reloads.

**Acceptance criteria (EARS):**

- 3.2.1 WHEN `GET /api/user/preferences` is called with a valid JWT THEN the backend SHALL call `agentcore_memory.get_user_preferences(user_id)` and return `{ preferences }` or `{ preferences: null }` if none exist.
- 3.2.2 WHEN `POST /api/user/preferences` is called with body `{ vibe: string[], colors: string[], occasions: string[], categories: string[] }` AND a valid JWT THEN the backend SHALL validate the payload, call `agentcore_memory.set_user_preferences(user_id, prefs)`, and return the saved object.
- 3.2.3 WHEN either preference endpoint receives an invalid or missing JWT THEN it SHALL return `401`.
- 3.2.4 WHEN the preference payload contains values outside the steering-defined sets (Vibe, Colors, Occasions, Categories) THEN the backend SHALL return `422` with the offending field names.

### Requirement 3.3 — Product and search endpoints

**User story:** As the frontend, I want one product endpoint that handles both anonymous and personalized listings.

**Acceptance criteria (EARS):**

- 3.3.1 WHEN `GET /api/products` is called with no auth THEN the backend SHALL return the full showcase product list in default editorial order.
- 3.3.2 WHEN `GET /api/products?personalized=true` is called with a valid JWT AND the user has saved preferences THEN the backend SHALL compute a match score per product (count of overlapping values between the product's `tags` column and the union of user preferences — each matching tag contributes `1`, all preference groups weighted equally) and return the product list sorted by match score descending, ties broken by default editorial order.
- 3.3.2.1 **Take It Further (advanced participants):** the equal-weight scoring in 3.3.2 is intentionally simple for the workshop. A production system would weight groups differently (e.g., category and occasion matches heavier than vibe or colors). This is called out as an extension in the lab guide, not as a built-in feature.
- 3.3.3 WHEN `GET /api/products?personalized=true` is called with a valid JWT AND the user has no saved preferences THEN the backend SHALL return the default editorial order.
- 3.3.4 WHEN `GET /api/products?category=<name>` is called THEN the backend SHALL filter to the named category with `ILIKE` per `database.md`.
- 3.3.5 WHEN `GET /api/products/{id}` is called THEN the backend SHALL return the product row or `404`.
- 3.3.6 WHEN `POST /api/search` is called with `{ query: string }` THEN the backend SHALL embed the query, call `HybridSearchService._vector_search()` (C1 implementation), and return ranked results.

### Requirement 3.4 — Agent endpoints

**User story:** As the frontend, I want streaming agent responses so the chat feels live.

**Acceptance criteria (EARS):**

- 3.4.1 WHEN `POST /api/agent/chat` is called with `{ message: string, session_id?: string }` THEN the backend SHALL run the orchestrator (C4, and C5 on AgentCore Runtime once C5 is in place) and stream the response as Server-Sent Events.
- 3.4.2 WHEN the request includes a valid JWT THEN the agent SHALL receive the verified user context via `agentcore_identity.get_verified_user_context(request)` and scope memory reads/writes to `user:{user_id}`.
- 3.4.3 WHEN `session_id` is omitted THEN the backend SHALL generate one and return it in the first SSE event.
- 3.4.4 WHEN `GET /api/agent/session/{id}` is called with a valid JWT THEN the backend SHALL return the multi-turn history from AgentCore Memory for that session, scoped to the verified user.

### Requirement 3.5 — Inventory endpoint

**User story:** As the frontend, I want a lightweight inventory signal for the live status strip.

**Acceptance criteria (EARS):**

- 3.5.1 WHEN `GET /api/inventory` is called THEN the backend SHALL return `{ last_refreshed: ISO-8601, counts: { [category]: integer } }`.
- 3.5.2 WHEN inventory data is stale beyond 24h THEN the endpoint SHALL return `stale: true` alongside the counts.

---

## 4. Authentication

### Requirement 4.1 — Cognito User Pool configuration

**User story:** As the platform, I want one Cognito User Pool that federates Google, Apple, and native email.

**Acceptance criteria (EARS):**

- 4.1.1 WHEN the Cognito User Pool is provisioned THEN it SHALL expose a Hosted UI with federated identity providers `Google` and `SignInWithApple` plus native email/password.
- 4.1.2 WHEN the User Pool client is provisioned THEN allowed OAuth flows SHALL be `code`, scopes SHALL be `openid email profile`, and callback URLs SHALL include the storefront `/api/auth/callback` for local, workshop, and production origins.
- 4.1.3 WHEN tokens are issued THEN the ID token SHALL include the `given_name` claim (required for the Account button and curated banner copy).
- 4.1.4 WHEN provisioning details exceed this spec THEN they SHALL live in the `.claude/prompts/infrastructure.md` playbook, not here.

### Requirement 4.2 — JWT verification middleware

**User story:** As the backend, I want one place that verifies JWTs so every protected endpoint inherits the same guarantees.

**Acceptance criteria (EARS):**

- 4.2.1 WHEN the middleware starts THEN it SHALL fetch Cognito JWKS and cache keys for 1 hour TTL.
- 4.2.2 WHEN a protected request arrives THEN the middleware SHALL read the JWT from `Authorization: Bearer` or the `access_token` cookie (in that priority) and validate signature, `iss`, `aud`, `exp`, and `token_use=access`.
- 4.2.3 WHEN validation succeeds THEN the middleware SHALL set `request.state.user = { user_id, email, given_name }` and call the next handler.
- 4.2.4 WHEN validation fails on expired token AND a `refresh_token` cookie is present THEN the backend SHALL attempt a silent refresh against Cognito; on success it SHALL rotate the cookies and retry the request once, otherwise return `401`.
- 4.2.5 WHEN a refresh attempt fails THEN the frontend `useAuth()` SHALL deep-link to `/signin` preserving the current path.

### Requirement 4.3 — AgentCore Identity integration

**User story:** As an agent, I want the verified user context delivered with the request so memory and personalization are always scoped correctly.

**Acceptance criteria (EARS):**

- 4.3.1 WHEN the orchestrator runs for an authenticated request THEN `agentcore_identity.get_verified_user_context(request)` SHALL return a context object whose `user_id` matches `request.state.user.user_id`.
- 4.3.2 WHEN an agent calls `agentcore_memory` THEN the user context SHALL scope keys by `user:{user_id}:...` so no cross-user bleed is possible.
- 4.3.3 WHEN an unauthenticated request triggers the agent THEN the context SHALL fall back to an anonymous `session_id`-scoped namespace; WHEN the user later signs in THEN the session history SHALL NOT automatically merge into the user's namespace (safer default — no silent data crossover).
- 4.3.3.1 **Take It Further (advanced participants):** anonymous → authenticated session handoff (opt-in merge after sign-in) is called out as an extension in the lab guide. The workshop default is no auto-merge; participants who want to implement merge must add their own explicit consent step.

### Requirement 4.4 — Preference persistence contract

**User story:** As the personalization engine, I want one source of truth for user preferences.

**Acceptance criteria (EARS):**

- 4.4.1 WHEN preferences are written THEN they SHALL persist via `agentcore_memory.py` at key `user:{user_id}:preferences` — never in browser localStorage, never in the product DB.
- 4.4.2 WHEN a user signs out and back in with the same IdP subject THEN preferences SHALL still be readable.
- 4.4.3 WHEN preferences are read THEN the shape SHALL be `{ vibe: string[], colors: string[], occasions: string[], categories: string[] }` matching the four groups in `storefront.md`.

---

## 5. Non-Functional Requirements

### Requirement 5.1 — Performance

**Acceptance criteria (EARS):**

- 5.1.1 WHEN `POST /api/search` executes against the seeded catalog THEN the p95 end-to-end latency SHALL be under 500ms (measured on the workshop instance).
- 5.1.2 WHEN `POST /api/agent/chat` streams a typical query THEN the first token SHALL arrive under 2s and the full response SHALL complete under 6s for single-specialist routes.
- 5.1.3 WHEN a protected endpoint runs JWT verification with a warm JWKS cache THEN the added latency SHALL be under 200ms.
- 5.1.4 WHEN the product grid parallax animates THEN the frame rate SHALL hold at 60fps on the reference workshop browser (Chromium-based).

### Requirement 5.2 — Responsiveness

**Acceptance criteria (EARS):**

- 5.2.1 WHEN the viewport is mobile (<768px) THEN the grid SHALL be 1 column, hero image height 520px, and the `Ask Pellier` nav text link SHALL be hidden.
- 5.2.2 WHEN the viewport is tablet (≥768px and <1024px) THEN the grid SHALL be 2 columns.
- 5.2.3 WHEN the viewport is desktop (≥1024px) THEN the grid SHALL be 3 columns and hero image height 640px.

### Requirement 5.3 — Security

**Acceptance criteria (EARS):**

- 5.3.1 WHEN tokens are stored on the client THEN they SHALL be httpOnly Secure SameSite=Lax cookies ONLY, never `localStorage` or `sessionStorage`.
- 5.3.2 WHEN a request originates cross-origin THEN cookies SHALL not be sent (SameSite=Lax) unless following a top-level navigation.
- 5.3.3 WHEN PII appears in logs THEN it SHALL be redacted; token payloads SHALL never be logged.
- 5.3.4 WHEN `state` does not match between `signin` and `callback` THEN `callback` SHALL return `400 invalid_state`.

### Requirement 5.4 — Observability

**Acceptance criteria (EARS):**

- 5.4.1 WHEN C8 is complete THEN every agent run SHALL emit OpenTelemetry spans extractable by `otel_trace_extractor.py` for the `/inspector` view.
- 5.4.2 WHEN SQL is executed by the search service THEN it SHALL log via `sql_query_logger.py` with parameterized placeholders (not interpolated values) per `database.md`.

---

## 6. Data Dependencies

### Requirement 6.1 — Catalog spec defers to `catalog-enrichment`

**Acceptance criteria (EARS):**

- 6.1.1 WHEN this spec references the product table THEN it SHALL use the schema, tags column, embedding column, and seeded rows defined in `.kiro/specs/catalog-enrichment/` without re-declaring them.
- 6.1.2 WHEN personalization computes a match score THEN it SHALL read the `tags text[]` column defined by `catalog-enrichment` and use the values listed in the 9-product showcase table in `storefront.md`.

### Requirement 6.2 — Session and preference storage

**Acceptance criteria (EARS):**

- 6.2.1 WHEN session history or user preferences are stored THEN they SHALL use `pellier/backend/services/agentcore_memory.py` (implemented by C6) — not the product DB, not Redis, not in-process dicts in production paths.

---

## 7. Integration Requirements

### Requirement 7.1 — Customer support specialist defers to its own spec

**Acceptance criteria (EARS):**

- 7.1.1 WHEN the orchestrator (C4) references `customer_support_agent` THEN the specialist's implementation SHALL be sourced from `.kiro/specs/customer-support-agent/` without duplication in this spec.
- 7.1.2 WHEN this spec's tasks create the orchestrator routing THEN the five-specialist tool list SHALL include a symbol import for `customer_support_agent`, even if the specialist code itself is owned by the other spec.

### Requirement 7.2 — Configuration and copy centralization

**Acceptance criteria (EARS):**

- 7.2.1 WHEN the frontend renders user-facing strings THEN they SHALL be imported from `pellier/frontend/src/copy.ts`.
- 7.2.2 WHEN the backend emits user-facing strings THEN they SHALL be imported from `pellier/backend/storefront_copy.py`.
- 7.2.3 WHEN OAuth redirect URIs are configured THEN they SHALL be environment-variable-driven via `pydantic-settings`.

---

## 8. Out of Scope (Owned Elsewhere)

- Product catalog DDL, embedding pipeline, tag assignment — `catalog-enrichment` spec.
- Customer support specialist agent — `customer-support-agent` spec.
- CloudFormation, IAM, bootstrap scripts, Workshop Studio provisioning — `.claude/prompts/infrastructure.md`.
- Workshop lab guide prose — `.claude/prompts/workshop-content.md`, `.claude/prompts/builders-content.md`.

---

## Validation Checklist

- [x] Nav has exactly 5 items (Requirement 1.2.1).
- [x] About content in footer, not top nav (1.2.4, 1.10.2).
- [x] Sign-in strip vs curated banner mutually exclusive (1.4.1–1.4.5).
- [x] ⌘K global concierge with Escape + second ⌘K close (1.11.2, 1.11.3).
- [x] Intent rotation pauses on hover; progress bar freezes and resumes (1.3.6, 1.3.7).
- [x] Grid re-sorts on preference change (1.6.6, 3.3.2).
- [x] Parallax matches `storefront.md` timing (1.6.2, 1.6.3).
- [x] 9 challenges total, 1/3/5 split (2.3, 2.4, 2.5, 2.6).
- [x] C9 is four files (2.6.1).
- [x] Storyboard is 3-card grid (1.9.1).
- [x] Storyboard and Discover routes render minimal index pages (1.13).
- [x] Real Cognito + AgentCore Identity (4.1–4.3).
- [x] Preferences persist to AgentCore Memory (4.4.1, 6.2.1).
- [x] httpOnly cookies only (5.3.1).
- [x] Orchestrator Haiku 4.5 @ 0.0, specialists Opus 4.6 @ 0.2 (2.4.3, 2.4.6).
- [x] Tool pattern enforced (2.2.4).
- [x] Defers to `catalog-enrichment` and `customer-support-agent` (6.1, 7.1).
- [x] Agent/tool names match steering (2.2.3).

---

## Approval Gate

Requirements complete. Revision incorporates:

- Resolved path-prefix and Aurora-version conflicts (Introduction).
- Personalization scoring clarified as equal-weight tag overlap with weighted scoring flagged as Take It Further (3.3.2, 3.3.2.1).
- C3 verification tightened to require tag-level relevance (2.4.5).
- Anonymous → authenticated session handoff flagged as Take It Further (4.3.3.1).
- Preferences-modal "once per fresh sign-in" signal deferred to `design.md` (1.4.4).
- Storyboard and Discover minimal index routes added (1.13).

Reply **approve** to proceed with `design.md`, or point out further edits.
