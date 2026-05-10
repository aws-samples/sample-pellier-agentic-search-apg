# Implementation Plan: Atelier Observatory

## Overview

Build the Atelier Observatory — a read-only editorial-luxury AI observability surface — in 6 incremental phases. Each phase produces a working, testable increment. The implementation reorganizes existing atelier-v2 and atelier-arch components into a new `/src/atelier/` directory tree, replaces useState-based navigation with React Router nested routes, introduces a fixture-first data layer, and adds backend API endpoints. All surfaces follow the cream/sand/espresso design system with Fraunces, Inter, and JetBrains Mono typography.

## Tasks

- [x] 1. Phase 0 — Foundation: design tokens, fonts, shell, routing, shared components, fixture infrastructure
  - [x] 1.1 Create the `/src/atelier/` directory tree and design token CSS files
    - Create `src/atelier/styles/tokens.css` with all color tokens (cream-1, cream-2, cream-elev, ink-1, red-1, green-1, espresso-1, espresso-2, and opacity variants)
    - Create `src/atelier/styles/fonts.css` importing Fraunces, Inter, and JetBrains Mono with CSS custom properties (--serif, --sans, --mono)
    - Create `src/atelier/styles/base.css` with global Atelier resets (flat aesthetic, no glassmorphism/blurs/gradients)
    - _Requirements: 15.1, 15.2, 15.6, 22.1_

  - [x] 1.2 Create shared UI components library
    - Create `src/atelier/components/Eyebrow.tsx` — monospace uppercase label with burgundy dot (JetBrains Mono, 9-10px, letter-spacing 0.22em)
    - Create `src/atelier/components/ExpCard.tsx` — cream-elev background, 1px rule-1 border, 14px border-radius, 24px burgundy accent line at top-left
    - Create `src/atelier/components/StatusPill.tsx` — shipped (sage green-soft bg, green-1 text) and exercise (red-soft bg, red-1 text)
    - Create `src/atelier/components/StatusDot.tsx` — live (burgundy pulsing), idle (ink-4 muted), empty (burgundy outline)
    - Create `src/atelier/components/WorkshopProgressStrip.tsx` — segment bar with solid (shipped) and dashed (exercise) segments, shipped/total fraction
    - Create `src/atelier/components/CategoryBadge.tsx` — Both/Managed/Owned/Teaching with distinct color schemes
    - Create `src/atelier/components/EditorialTitle.tsx` — page-level title block (eyebrow + Fraunces title + summary paragraph)
    - Create `src/atelier/components/TabNav.tsx` — Fraunces italic tab links with burgundy underline on active
    - Create `src/atelier/components/BreadcrumbTrail.tsx` — dot-separated JetBrains Mono uppercase breadcrumb from route path
    - Create `src/atelier/components/ModeStrip.tsx` — routing pattern pill toggles
    - Create `src/atelier/components/ContextRail.tsx` — 360px right column wrapper for session detail views
    - Create `src/atelier/components/index.ts` barrel export
    - _Requirements: 15.3, 15.4, 15.5, 15.7, 22.3_

  - [x] 1.3 Create AtelierFrame shell with React Router nested routes
    - Create `src/atelier/shell/AtelierFrame.tsx` — 240px sidebar + flexible canvas grid layout wrapping `<Outlet />`
    - Create `src/atelier/shell/Sidebar.tsx` — espresso-colored left nav with three sections (OBSERVE, UNDERSTAND, MEASURE), Settings divider, persona footer; use `<NavLink>` for active state (espresso-2 bg, 2px burgundy accent bar, full-opacity icon)
    - Create `src/atelier/shell/TopBar.tsx` — SurfaceToggle (reuse existing component), BreadcrumbTrail from route, live status metadata, persona avatar
    - Update `App.tsx` to replace the single `/atelier` route with nested routes under `<AtelierFrame>`: sessions, sessions/:id (with chat/telemetry/brief children), architecture, architecture/:concept, agents, tools, routing, memory, performance, evaluations, observatory, settings
    - Preserve existing `/atelier/architecture/:section` → WorkshopPage route for backward compatibility
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8_

  - [x] 1.4 Create TypeScript interfaces and fixture infrastructure
    - Create `src/atelier/types/persona.ts`, `session.ts`, `chat.ts`, `telemetry.ts`, `brief.ts`, `agent.ts`, `tool.ts`, `routing.ts`, `memory.ts`, `performance.ts`, `evaluations.ts`, `observatory.ts`, `architecture.ts` with all interfaces from the design document
    - Create `src/atelier/types/index.ts` barrel export
    - Create fixture JSON files in `src/atelier/fixtures/`: `sessions.json`, `session-7f5a.json`, `agents.json`, `tools.json`, `routing.json`, `memory-marco.json`, `performance.json`, `evaluations.json`, `observatory.json`, `architecture.json`
    - Create `src/atelier/hooks/useAtelierData.ts` — central data-fetching hook that switches between fixture imports and API fetch based on `source` option; returns `{ data, loading, error, refetch }`
    - _Requirements: 16.1, 16.4, 16.5_

  - [x] 1.5 Create AtelierErrorBoundary
    - Create `src/atelier/shell/AtelierErrorBoundary.tsx` wrapping the `<Outlet />` in AtelierFrame
    - Render editorial error page: "SOMETHING WENT WRONG" eyebrow, "The observatory hit a snag." title, error message in monospace, "Return to Sessions" link
    - Sidebar and TopBar remain functional outside the boundary
    - _Requirements: 19.2, 19.4_

  - [x] 1.6 Write property test for route resolution correctness
    - Install `fast-check` as a dev dependency
    - **Property 5: Route resolution correctness**
    - Generate valid Atelier route paths from defined segments (sessions, sessions/:id, architecture, architecture/:concept, agents, tools, routing, memory, performance, evaluations, observatory, settings) and verify React Router resolves each to a non-null component
    - **Validates: Requirements 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8**

- [x] 2. Checkpoint — Verify Phase 0 foundation
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: shell renders with sidebar + top bar + outlet, all shared components render correctly, fixture data loads via useAtelierData, all nested routes resolve

- [x] 3. Phase 1 — Sessions: list + session detail with Chat, Telemetry, and Brief tabs
  - [x] 3.1 Implement SessionsList surface
    - Create `src/atelier/surfaces/observe/SessionsList.tsx` — page Eyebrow, EditorialTitle (Fraunces 52px), summary paragraph, list of session ExpCards
    - Each session card: hex ID, opening query (Fraunces italic), elapsed time, agent count, routing pattern badge, timestamp
    - Sort sessions by most recent first (descending timestamp)
    - Empty state with editorial message when no sessions exist for the active persona
    - Click navigates to `/atelier/sessions/:id`
    - Load data via `useAtelierData({ key: 'sessions' })`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Write property test for session sort order
    - **Property 1: Sessions are sorted by recency**
    - Generate random Session[] with distinct timestamps, pass to sort function, verify descending order
    - **Validates: Requirements 2.1**

  - [x] 3.3 Write property test for session card field completeness
    - **Property 2: Session card field completeness**
    - Generate random Session objects, render card, verify all 6 required fields (hex ID, opening query, elapsed time, agent count, routing pattern, timestamp) are present and non-empty
    - **Validates: Requirements 2.2**

  - [x] 3.4 Implement SessionView container and ChatTab
    - Create `src/atelier/surfaces/observe/SessionView.tsx` — reads `:id` from useParams, renders TabNav (Chat / Telemetry / Brief) with `<Outlet />` for tab content
    - Create `src/atelier/surfaces/observe/ChatTab.tsx` — two-column layout: chat thread (left) + ContextRail (360px, right)
    - Chat thread: persona strip at top (avatar, name, context summary, customer ID), user messages as right-aligned dark bubbles (ink-1 bg, cream text, 14px radius), assistant messages as left-aligned prose
    - Tool call chips: collapsible, showing tool name, description, timing; expanded shows SQL in cream-2 code block with burgundy keyword highlighting and result summary
    - Product recommendation grid: three-column grid of product cards with image placeholder, brand, name, price
    - Plan row at start of each assistant turn: routing pattern badge, step count, flow summary, "view trace" link
    - Confidence rows: sage green background, percentage, reasoning
    - Memory pills: burgundy dashed border, tier badge (STM/LTM), content
    - Context rail: Memory card (STM/LTM tiers with item counts and chips), Agents card (5 specialists with status dots), Skills card (style-advisor, gift-concierge with activation status)
    - Composer bar at bottom: sparkle icon, placeholder text, keyboard shortcut badge, send button
    - Empty state: suggested query pills ("Try asking")
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15_

  - [x] 3.5 Implement TelemetryTab
    - Create `src/atelier/surfaces/observe/TelemetryTab.tsx` — two-column layout: numbered timeline (left) + ContextRail (right)
    - Timeline: numbered panels in vertical timeline with connecting line on left, each panel has category badge (Both/Managed/Owned/Teaching), title, description, status (complete green/running burgundy pulsing/queued muted), timing
    - Mode strip above timeline: routing pattern pill toggles (Dispatcher/Agents-as-Tools/Graph), Dispatcher active for storefront sessions
    - Eyebrow with total panel count (e.g., "Thirteen panels · 13")
    - Active/expanded panel: elevated background and border shadow
    - Context rail: product recommendation card with image placeholder, brand, name, price, editorial blurb, "Why this pick" reasons, "Trace this pick" button, confidence score, token count
    - Three-column expansion area below timeline: "How we arrived" (SQL panels), "Memory orbit" (STM/LTM visualization), "Team of specialists" (agent status cards)
    - Footer strip: pull quote, active agents count, data sources count, decisions today, success rate
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [x] 3.6 Implement BriefTab (Curator's Brief)
    - Create `src/atelier/surfaces/observe/BriefTab.tsx` — single-column magazine layout (max-width 620px, centered)
    - Title block: Eyebrow ("Curator's Brief · Folio NN"), Fraunces italic headline, metadata (filed time, session ID)
    - Metadata grid: Customer, Request, Plan, Elapsed fields with monospace labels and serif values
    - Numbered editorial sections (i., ii., iii., iv., v.) with drop-cap first paragraphs, Fraunces italic section titles, 16.5px serif prose
    - Tool selection section: evidence panel with pgvector discovery SQL and ranked tool list with cosine distances
    - Memory section: STM and LTM tier rows showing what was remembered/recalled
    - Products section: three-column grid of product cards with image placeholders, brand, name, trace links
    - Confidence section: large confidence percentage (76px serif) with numbered supporting statistics
    - Editorial footer: "fin." mark and closing italic statement
    - Inline trace pills: burgundy monospace badges referencing telemetry steps
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

  - [x] 3.7 Add loading, error, and empty states for all Session surfaces
    - Add skeleton/loading placeholders for SessionsList, ChatTab, TelemetryTab, BriefTab
    - Add error states with editorial message and retry button
    - Add empty states with contextual editorial messages
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [x] 4. Checkpoint — Verify Phase 1 sessions
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: sessions list renders from fixtures, session detail tabs switch correctly, chat/telemetry/brief render all required elements, loading/error/empty states work

- [x] 5. Phase 2 — Understand: Architecture index, Agents, Tools, Routing, Memory dashboard
  - [x] 5.1 Implement Architecture index surface
    - Create `src/atelier/surfaces/understand/ArchitectureIndex.tsx` — 2-column grid of 8 architecture concept ExpCards
    - Each card: Roman numeral (Fraunces italic, burgundy), CategoryBadge, title (Fraunces 26px), role subtitle (Fraunces italic, burgundy), prose description, code snippet (cream-2 bg, monospace), "Open [concept]" link navigating to `/atelier/architecture/:slug`
    - 8 concepts: Memory, MCP, State Management, Tool Registry/Gateway, Skills, Runtime, Evaluations, Grounding
    - Legend card below grid explaining four category badges
    - Load data from `architecture.json` fixture
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.2 Implement Agents surface
    - Create `src/atelier/surfaces/understand/Agents.tsx` — WorkshopProgressStrip (5 segments: 3 shipped, 2 exercise) + 5 agent row cards
    - Each agent card: Roman numeral, name (Fraunces 24px), role description, StatusDot + StatusPill, tool chips, model tag ("Opus 4.6 · 0.2"), "Open [Agent]" link
    - Shipped agents (Search, Recommendation, Pricing): solid borders, cream-elev bg, sage "Shipped" pills, cream-2 tool chips with solid borders
    - Exercise agents (Inventory, Customer Support): dashed borders, transparent bg, burgundy "Exercise" pills, transparent tool chips with dashed burgundy borders, exercise files list
    - "Related" callout card linking to Skills and Routing surfaces
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 5.3 Write property test for workshop progress strip accuracy
    - **Property 3: Workshop progress strip accuracy**
    - Generate random arrays of items with status "shipped" or "exercise", render WorkshopProgressStrip, verify solid segment count equals shipped count, dashed segment count equals exercise count, total equals item count
    - **Validates: Requirements 8.1, 9.1, 17.3**

  - [x] 5.4 Implement Tools surface with live pgvector discovery
    - Create `src/atelier/surfaces/understand/Tools.tsx` — WorkshopProgressStrip (9 segments: 6 shipped, 3 exercise) + discovery demo card + 9 tool row cards
    - Discovery demo card: query input with sample natural-language query, ranked results list with cosine distances; hits real `POST /api/atelier/tools/discover` endpoint
    - Create `src/atelier/hooks/useToolDiscovery.ts` — dedicated hook that always calls the real API, returns `{ results, loading, error, durationMs, sql }`
    - Each tool card: numeral, function name (JetBrains Mono 17px), description, StatusDot, StatusPill, function signature code block, "Used by" agent chips, metadata (invocation count, version)
    - Shipped tools (search_products, browse_category, compare_products, trending_products, price_analysis, return_policy): solid borders, sage status
    - Exercise tools (inventory_health, restock_product, low_stock): dashed borders, burgundy status
    - "Related" callout card linking to Agents and Architecture · Tool Registry
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 16.3_

  - [x] 5.5 Implement Routing surface
    - Create `src/atelier/surfaces/understand/Routing.tsx` — 3 routing pattern ExpCards
    - Each card: pattern name, description, code snippet/diagram, agent list, active indicator (StatusDot + "Active" StatusPill for Dispatcher)
    - Dispatcher shown as active for storefront sessions (not Agents-as-Tools)
    - Fallback to fixture data when unavailable
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 5.6 Implement Memory dashboard surface
    - Create `src/atelier/surfaces/understand/MemoryDashboard.tsx` — STM + LTM tiers for active persona
    - STM state: turn count, recent intents, fresh items from current session
    - LTM state: stored preferences, prior order history, behavioral patterns via pgvector semantic recall
    - Orbit visualization: persona at center, STM items on inner ring, LTM items on outer ring, labeled connector dots
    - Empty state when no memory data exists for persona
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 5.7 Add loading, error, and empty states for all Understand surfaces
    - Add skeleton/loading, error with retry, and empty states for ArchitectureIndex, Agents, Tools, Routing, MemoryDashboard
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [x] 6. Checkpoint — Verify Phase 2 understand surfaces
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: architecture index renders 8 cards, agents show shipped/exercise distinction, tools discovery card hits real API, routing shows Dispatcher as active, memory dashboard renders orbit visualization

- [x] 7. Phase 3 — Architecture detail pages (8 total, following Memory template)
  - [x] 7.1 Create DetailPageShell template component
    - Create `src/atelier/surfaces/understand/architecture/DetailPageShell.tsx` (or migrate from existing `src/components/atelier/DetailPageShell.tsx`) — reusable template with: detail Eyebrow (numeral + concept name + CategoryBadge), hero title (Fraunces 56px italic), hero prose, slot for concept-specific content, cheat-sheet strip (3-column grid of takeaways with Roman numeral Eyebrows and italic text), live state callout (pulsing indicator, context description, current metric values)
    - _Requirements: 7.1, 7.4, 7.5_

  - [x] 7.2 Implement Memory detail page
    - Create `src/atelier/surfaces/understand/architecture/MemoryDetail.tsx` — two tier cards (STM and LTM) side by side with tier name, CategoryBadge, title, role, prose, code snippet
    - Orbit centerpiece visualization: persona at center, STM items on inner ring, LTM items on outer ring, labeled connector dots
    - Live state callout: STM turn count, LTM fact count for active persona
    - Fallback to fixture data when live data unavailable
    - _Requirements: 7.2, 7.3, 7.6, 7.7_

  - [x] 7.3 Implement remaining 7 architecture detail pages
    - Create `McpDetail.tsx`, `StateDetail.tsx`, `ToolRegistryDetail.tsx`, `SkillsDetail.tsx`, `RuntimeDetail.tsx`, `EvaluationsDetail.tsx`, `GroundingDetail.tsx` — all using DetailPageShell template
    - Migrate content from existing `src/components/atelier-arch/` pages (MemoryArchPage, McpArchPage, StateManagementArchPage, ToolRegistryArchPage, RuntimeArchPage, EvaluationsArchPage, GroundingArchPage) into the new template structure
    - Create `src/atelier/surfaces/understand/architecture/ArchitectureDetail.tsx` — reads `:concept` from useParams and renders the matching detail page
    - Each page: concept-specific content cards, cheat-sheet strip, live state callout
    - _Requirements: 7.1, 7.6, 7.7_

  - [x] 7.4 Add loading, error, and empty states for architecture detail pages
    - Add skeleton/loading, error with retry, and fixture fallback states for all 8 detail pages
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [x] 8. Checkpoint — Verify Phase 3 architecture detail pages
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: all 8 detail pages render with correct template structure, existing architecture deep links still work via backward-compatible route, orbit visualization renders on Memory detail

- [x] 9. Phase 4 — Measure: Performance and Evaluations surfaces
  - [x] 9.1 Implement Performance surface
    - Create `src/atelier/surfaces/measure/Performance.tsx`
    - Stat cards: P50 cold start time and P50 warm reuse time with sample counts and distribution labels
    - Cold start histogram: SVG visualization showing bimodal distribution of cold vs warm starts
    - Per-panel latency budget table: rows for each panel type (LLM, tool, memory), horizontal bar fills proportional to time, millisecond values
    - pgvector comparison table: IVFFlat, HNSW, brute-force with recall, QPS, build time, storage columns; HNSW row highlighted as shipped strategy
    - Storage usage bars: catalog embeddings, tool registry, memory vectors with sizes and percentages
    - Measure controls: time window selector (1h/6h/24h/7d pills), sample size slider, "Run benchmark" button
    - Fallback to fixture data when unavailable
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 9.2 Implement Evaluations surface
    - Create `src/atelier/surfaces/measure/Evaluations.tsx`
    - Agent evaluation scorecards: accuracy, latency percentiles, citation rates per agent
    - Version-over-version quality trends for each evaluation recipe
    - Follow ExpCard pattern with Eyebrows, editorial titles, monospace metadata
    - Fallback to fixture data when unavailable
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 9.3 Add loading, error, and empty states for Measure surfaces
    - Add skeleton/loading, error with retry, and empty states for Performance and Evaluations
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [x] 10. Checkpoint — Verify Phase 4 measure surfaces
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: performance surface renders all 6 visualization types, evaluations surface renders scorecards with trends, fixture fallback works

- [x] 11. Phase 5 — Observatory wide-angle dashboard
  - [x] 11.1 Implement Observatory surface
    - Create `src/atelier/surfaces/observe/Observatory.tsx` — wide-angle dashboard
    - Summary ExpCards: active sessions, agent status (5 agents with live/idle dots), tool invocations, memory state (STM/LTM counts), performance headlines
    - Large serif numerals for key metrics, monospace labels
    - Live pulsing indicator on dashboard and in Sidebar Observatory nav item
    - Fallback to fixture data with note indicating mock data when no live data available
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 11.2 Add loading, error, and empty states for Observatory
    - Add skeleton/loading, error with retry, and empty states
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [x] 12. Checkpoint — Verify Phase 5 observatory
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: observatory renders all summary cards, live pulsing indicator works, fixture fallback displays note

- [x] 13. Backend API endpoints and data wiring
  - [x] 13.1 Create backend atelier observatory router
    - Create `pellier/backend/routes/atelier_observatory.py` with FastAPI router mounted at `/api/atelier/`
    - Implement `GET /api/atelier/sessions` — returns session list for persona (fixture data initially, DB query when available)
    - Implement `GET /api/atelier/sessions/{id}` — returns full session detail or 404
    - Implement `GET /api/atelier/agents` — returns 5 agents with status, tools, model config
    - Implement `GET /api/atelier/tools` — returns 9 tools with signatures, status, metadata
    - Implement `POST /api/atelier/tools/discover` — pgvector semantic search (wire to existing tool_registry endpoint logic)
    - Implement `GET /api/atelier/routing` — returns 3 routing patterns with active indicator
    - Implement `GET /api/atelier/memory/{persona}` — returns STM + LTM state for persona
    - Implement `GET /api/atelier/performance` — returns metrics and benchmarks
    - Implement `GET /api/atelier/evaluations` — returns agent scorecards
    - Implement `GET /api/atelier/observatory` — returns dashboard summary
    - Add Pydantic models: AtelierSessionSummary, AtelierToolDiscoverRequest, AtelierToolDiscoverResult, AtelierToolDiscoverResponse
    - All endpoints read-only, return 503 when DB not connected, graceful degradation on errors
    - Register router in `app.py`
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.11_

  - [x] 13.2 Wire frontend useAtelierData to API endpoints
    - Update `useAtelierData` hook to support `source: 'api'` mode that fetches from `/api/atelier/*` endpoints
    - Implement transparent fallback: if API call fails, fall back to fixture data without showing error
    - Wire Tools discovery card to use `useToolDiscovery` hook (already hitting real API)
    - _Requirements: 16.2, 16.3_

  - [x] 13.3 Write property test for fixture data round-trip integrity
    - **Property 4: Fixture data round-trip integrity**
    - For each fixture key, load via useAtelierData with source "fixture" and compare to raw JSON import — verify no fields dropped, no values mutated
    - **Validates: Requirements 16.1**

- [x] 14. Cross-cutting: build state detection, persona/settings, final polish
  - [x] 14.1 Implement build state detection
    - Add logic to determine shipped vs exercise status for tools and agents based on file existence checks or backend status responses
    - When a tool/agent transitions from exercise to shipped, update card styling from dashed/exercise to solid/shipped
    - Update WorkshopProgressStrip segments to reflect current shipped/exercise state
    - _Requirements: 17.1, 17.2, 17.3_

  - [x] 14.2 Implement Settings surface with persona selection
    - Create `src/atelier/surfaces/Settings.tsx` — persona selection interface
    - Default to Marco as active persona
    - When persona changes, update all surfaces to show data scoped to new persona
    - Update Sidebar footer to reflect active persona's name, avatar initial (colored circle), and role label (JetBrains Mono uppercase)
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

  - [x] 14.3 Write unit tests for shared components
    - Test ExpCard renders with correct cream-elev background, rule-1 border, 14px radius, burgundy accent
    - Test StatusPill renders "Shipped" in sage green, "Exercise" in burgundy
    - Test StatusDot renders live (pulsing), idle (muted), empty (outline) variants
    - Test Eyebrow renders monospace uppercase with burgundy dot
    - Test CategoryBadge renders correct colors for both/managed/owned/teaching
    - _Requirements: 15.3, 15.4, 15.5_

  - [x] 14.4 Write unit tests for data layer
    - Test useAtelierData returns fixture data when source is 'fixture'
    - Test useAtelierData sets loading state during fetch
    - Test useAtelierData sets error state on failure
    - Test useToolDiscovery calls correct endpoint and parses results
    - _Requirements: 16.1, 16.2_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Verify end-to-end: all 13+ surfaces render, all routes deep-linkable, sidebar navigation works, fixture data loads, API endpoints respond, build state detection updates UI, persona switching scopes data, error boundaries catch render errors

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each build phase
- Property tests validate universal correctness properties using `fast-check`
- Unit tests validate specific rendering scenarios and edge cases
- The design uses TypeScript throughout — all code examples use React 18 + TypeScript + Tailwind CSS
- Existing atelier-v2 and atelier-arch components are migrated into the new `/src/atelier/` directory tree, not deleted (backward-compatible routes preserved)
- The pgvector tool discovery card hits the real API from day one; all other surfaces start with fixtures
