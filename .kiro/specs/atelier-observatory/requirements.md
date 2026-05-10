# Requirements Document

## Introduction

The Atelier is an editorial-luxury AI observatory surface layered into the existing Pellier e-commerce application. It provides a read-only observability interface for workshop participants (DAT406, AWS re:Invent) and engineers building agentic systems on Aurora PostgreSQL. A surface-toggle in the top bar switches between Boutique (existing storefront) and Atelier (new observability surface). The Atelier visualizes the inner workings of 5 peer specialist agents, 2 skills, 3 routing patterns, 9 tools, and the memory/evaluation subsystems — all rendered in a flat editorial aesthetic with a cream/sand/espresso design system using Fraunces, Inter, and JetBrains Mono typography.

## Glossary

- **Atelier**: The AI observatory surface — a read-only instrumentation UI that lets engineers observe how the agentic system reasons, routes, remembers, and performs.
- **Boutique**: The existing customer-facing storefront surface at `/`.
- **Surface_Toggle**: A segmented control in the top bar that switches between Boutique and Atelier views.
- **Sidebar**: The espresso-colored (dark) left navigation panel (240px) with three nav sections: Observe, Understand, Measure.
- **Top_Bar**: The horizontal bar above the canvas containing the Surface_Toggle, breadcrumb trail, live status metadata, and persona avatar.
- **Canvas**: The main content area to the right of the Sidebar where surface content renders.
- **Session**: A single conversation between a persona and the agentic system, identified by a short hex ID (e.g., #7F5A).
- **Persona**: A mock customer profile (e.g., Marco) used as the demo identity in the Atelier; selected via Settings.
- **Agent**: One of 5 peer specialist agents (Search, Recommendation, Pricing, Inventory, Customer Support), all Claude Opus 4.6 at temperature 0.2.
- **Skill**: A runtime-injected persona-routed capability (style-advisor or gift-concierge), routed by the SkillRouter (Claude Haiku 4.5).
- **Routing_Pattern**: One of 3 orchestration strategies: Dispatcher (storefront default), Agents-as-Tools, or Graph.
- **Tool**: One of 9 named functions registered in tool_registry with pgvector embeddings for semantic discovery.
- **STM**: Short-term memory managed by AgentCore — ephemeral, session-scoped conversation state.
- **LTM**: Long-term memory stored in Aurora pgvector — semantic recall across sessions, customer preferences, behavioral patterns.
- **Workshop_Progress_Strip**: A visual bar showing shipped (solid) vs exercise (dashed) segments for challenges.
- **Eyebrow**: A small monospace uppercase label (JetBrains Mono, 9-10px, letter-spacing 0.22em) used as a section identifier throughout the Atelier design system.
- **Exp_Card**: An elevated cream card with a 1px border, 14px border-radius, and a short burgundy accent line at the top-left.
- **Status_Pill**: A small rounded pill label indicating shipped (sage green) or exercise (burgundy) state.
- **Status_Dot**: A small circular indicator — live (burgundy, pulsing), idle (muted), or empty (burgundy outline).
- **Fixture**: A static JSON mock data file in `/src/atelier/fixtures/` used before real API endpoints are wired.
- **Build_State_Detection**: The mechanism that determines whether a tool or agent is shipped or an exercise, based on file existence checks.
- **Curator_Brief**: A magazine-style editorial deconstruction of a single session — the destination of every "Open Full Trace" action.

## Requirements

### Requirement 1: Atelier Shell and Navigation Foundation

**User Story:** As a workshop participant, I want a consistent shell with sidebar navigation, top bar, and surface toggle, so that I can navigate between all Atelier surfaces within a unified editorial layout.

#### Acceptance Criteria

1. THE Atelier SHALL render a two-column grid layout with a 240px espresso-colored Sidebar on the left and a flexible Canvas on the right.
2. THE Sidebar SHALL display three navigation sections labeled OBSERVE, UNDERSTAND, and MEASURE, each preceded by an Eyebrow with a burgundy dot.
3. THE Sidebar OBSERVE section SHALL contain navigation items for Sessions (with session count badge) and Observatory (with a live pulsing dot).
4. THE Sidebar UNDERSTAND section SHALL contain navigation items for Architecture (with count badge "8"), Agents (with shipped/total fraction badge), Routing (with count badge "3"), Memory, and Tools (with shipped/total fraction badge).
5. THE Sidebar MEASURE section SHALL contain navigation items for Evaluations and Performance.
6. THE Sidebar SHALL contain a Settings navigation item below a divider line, separated from the three main sections.
7. THE Sidebar SHALL display a persona footer at the bottom showing the active persona avatar (initial letter in a colored circle), name (Fraunces italic), and role label (JetBrains Mono uppercase).
8. WHEN a navigation item is selected, THE Sidebar SHALL highlight the active item with an espresso-2 background, full-opacity icon, and a 2px burgundy accent bar on the left edge.
9. THE Top_Bar SHALL display the Surface_Toggle on the left, a breadcrumb trail (JetBrains Mono, uppercase, dot-separated) showing the current navigation path, and contextual metadata with persona avatar on the right.
10. THE Surface_Toggle SHALL render as a pill-shaped segmented control with "Boutique" and "Atelier" options, where the active option has an ink-1 background with cream text.
11. WHEN the user clicks "Boutique" in the Surface_Toggle, THE Atelier SHALL navigate to the storefront route (`/`).
12. WHEN the user clicks "Atelier" in the Surface_Toggle while on the storefront, THE Atelier SHALL navigate to the Atelier route (`/atelier`).
13. THE Sidebar brand row SHALL display a circular cream "B" mark and "Pellier" in Fraunces at the top.

### Requirement 2: Sessions List Surface

**User Story:** As a workshop participant, I want to see a list of all sessions for the active persona, so that I can select a session to inspect its telemetry, chat, and brief.

#### Acceptance Criteria

1. WHEN the user navigates to Sessions in the Sidebar, THE Atelier SHALL display a list of sessions for the active persona, sorted by most recent first.
2. THE Sessions list SHALL display each session as an Exp_Card showing the session hex ID, the opening query (Fraunces italic), elapsed time, agent count, routing pattern used, and a timestamp.
3. THE Sessions list SHALL display a page Eyebrow, editorial title (Fraunces, 52px), and summary paragraph above the list.
4. WHEN the user clicks a session card, THE Atelier SHALL navigate to the session detail view with Chat as the default active tab.
5. IF no sessions exist for the active persona, THEN THE Atelier SHALL display an empty state with an editorial message explaining that no sessions have been recorded yet.

### Requirement 3: Session Detail — Chat Tab

**User Story:** As a workshop participant, I want to view the multi-turn chat conversation for a session with inline tool calls, agent routing, and memory updates, so that I can understand how the agentic system responded to each user turn.

#### Acceptance Criteria

1. THE Session detail view SHALL display three tabs: Chat (i.), Telemetry (ii.), and Brief (iii.), rendered as Fraunces italic links with a burgundy underline on the active tab.
2. WHEN the Chat tab is active, THE Atelier SHALL render a two-column layout with the chat thread on the left and a context rail (360px) on the right.
3. THE Chat thread SHALL display user messages as right-aligned dark bubbles (ink-1 background, cream text, 14px border-radius) and assistant messages as left-aligned prose blocks.
4. WHEN an assistant turn includes tool calls, THE Chat thread SHALL display each tool call as a collapsible chip showing the tool name, a brief description, and execution timing.
5. WHEN a tool chip is expanded, THE Chat thread SHALL display the SQL query (in a cream-2 code block with burgundy keyword highlighting) and result summary.
6. WHEN an assistant turn includes product recommendations, THE Chat thread SHALL display a three-column grid of product cards with image placeholder, brand, name, and price.
7. THE Chat thread SHALL display a plan row at the start of each assistant turn showing the routing pattern badge, step count, flow summary, and a "view trace" link.
8. THE Chat thread SHALL display confidence rows (sage green background) showing the confidence percentage and reasoning.
9. THE Chat thread SHALL display memory pills (burgundy dashed border) when the system writes to STM or LTM, showing the tier badge and what was stored.
10. THE context rail SHALL display a Memory card showing STM and LTM tiers with item counts and individual memory items as chips.
11. THE context rail SHALL display an Agents card listing all 5 specialists with their current status (live dot or idle dot).
12. THE context rail SHALL display a Skills card showing style-advisor and gift-concierge with their activation status.
13. THE Chat thread SHALL include a persona strip at the top showing the persona avatar, name, context summary (returning customer, prior orders, preferences), and customer ID.
14. THE Chat thread SHALL include a composer bar at the bottom with a sparkle icon, placeholder text, keyboard shortcut badge, and send button.
15. WHEN the Chat thread has no messages, THE Atelier SHALL display suggested query pills ("Try asking") to guide the user.

### Requirement 4: Session Detail — Telemetry Tab

**User Story:** As a workshop participant, I want to view the step-by-step telemetry timeline for a session, so that I can trace every agent step, tool call, and decision the system made.

#### Acceptance Criteria

1. WHEN the Telemetry tab is active, THE Atelier SHALL render a two-column layout with the timeline on the left and a context rail (360px) on the right.
2. THE Telemetry timeline SHALL display each step as a numbered panel in a vertical timeline with a connecting line on the left.
3. THE Telemetry panel SHALL display a category badge (Both/Managed/Owned/Teaching with distinct color schemes), a title, a description, status (complete/running/queued), and timing.
4. THE Telemetry panel status dots SHALL use green fill for complete, burgundy pulsing for running, and muted for queued.
5. THE Telemetry timeline SHALL display a mode strip above the timeline showing the active routing pattern (Dispatcher, Agents-as-Tools, Graph) as pill-shaped toggles, with Dispatcher active for storefront sessions.
6. THE Telemetry timeline SHALL display an Eyebrow with the total panel count (e.g., "Thirteen panels · 13").
7. WHEN a timeline panel is in the active/expanded state, THE Atelier SHALL highlight it with an elevated background and border shadow.
8. THE context rail SHALL display a product recommendation card with image placeholder, brand, name, price, editorial blurb, "Why this pick" reasons list, a "Trace this pick" button, confidence score, and token count.
9. THE Atelier SHALL display a three-column expansion area below the timeline showing: (a) "How we arrived" with expanded SQL panels, (b) "Memory orbit" with STM/LTM visualization, and (c) "Team of specialists" with agent status cards.
10. THE Atelier SHALL display a footer strip below the expansion area with a pull quote, active agents count, data sources count, decisions today count, and success rate.

### Requirement 5: Session Detail — Curator's Brief Tab

**User Story:** As a workshop participant, I want to read an editorial deconstruction of how the system arrived at its recommendations for a session, so that I can understand the full reasoning chain in a shareable magazine-style format.

#### Acceptance Criteria

1. WHEN the Brief tab is active, THE Atelier SHALL render a single-column magazine-style layout (max-width 620px, centered) with editorial typography.
2. THE Curator_Brief SHALL display a centered title block with an Eyebrow ("Curator's Brief · Folio NN"), a Fraunces italic headline, and metadata (filed time, session ID).
3. THE Curator_Brief SHALL display a metadata grid showing Customer, Request, Plan, and Elapsed fields with monospace labels and serif values.
4. THE Curator_Brief SHALL contain numbered editorial sections (i., ii., iii., iv., v.) with drop-cap first paragraphs, section titles in Fraunces italic, and prose in 16.5px serif.
5. THE Curator_Brief section on tool selection SHALL include an evidence panel with the pgvector discovery SQL query and a ranked tool list with cosine distances.
6. THE Curator_Brief section on memory SHALL display STM and LTM tier rows showing what the system remembered and recalled.
7. THE Curator_Brief section on products SHALL display a three-column grid of product cards with image placeholders, brand, name, and trace links.
8. THE Curator_Brief section on confidence SHALL display a large confidence percentage (76px serif) with numbered supporting statistics.
9. THE Curator_Brief SHALL end with an editorial footer containing a "fin." mark and a closing italic statement.
10. THE Curator_Brief SHALL include inline trace pills (burgundy monospace badges) referencing specific telemetry steps.

### Requirement 6: Architecture Index Surface

**User Story:** As a workshop participant, I want to see an index of all 8 architectural concepts with summary cards, so that I can navigate to any concept's detail page.

#### Acceptance Criteria

1. WHEN the user navigates to Architecture in the Sidebar, THE Atelier SHALL display a 2-column grid of 8 architecture cards.
2. THE Architecture card SHALL display a Roman numeral (Fraunces italic, burgundy), a category badge (Both/Managed/Owned), a title (Fraunces 26px), a role subtitle (Fraunces italic, burgundy), prose description, a code snippet (cream-2 background, monospace), and an "Open [concept]" link.
3. THE 8 architecture concepts SHALL be: Memory, MCP, State Management, Tool Registry/Gateway, Skills, Runtime, Evaluations, and Grounding.
4. THE Architecture index SHALL display a legend card below the grid explaining the four category badges: Both, Managed, Owned, and Teaching.
5. WHEN the user clicks an "Open [concept]" link, THE Atelier SHALL navigate to the corresponding architecture detail page.

### Requirement 7: Architecture Detail Pages

**User Story:** As a workshop participant, I want to view a deep-dive detail page for each architectural concept following a consistent template, so that I can learn how each concept works with prose, visualizations, code snippets, and live state.

#### Acceptance Criteria

1. THE Architecture detail page SHALL follow the template established by the Memory mockup: detail Eyebrow (numeral + concept name + category badge), hero title (Fraunces 56px italic), hero prose, concept-specific content cards, a cheat-sheet strip, and a live state callout.
2. THE Memory detail page SHALL display two tier cards (STM and LTM) side by side, each with tier name, category badge, title, role, prose, and a code snippet.
3. THE Memory detail page SHALL display an orbit centerpiece visualization showing the persona at center with STM items on an inner ring and LTM items on an outer ring, with labeled connector dots.
4. THE Architecture detail page cheat-sheet strip SHALL display a 3-column grid of key takeaways, each with a Roman numeral Eyebrow and italic text.
5. THE Architecture detail page live state callout SHALL display a live pulsing indicator, context description, and current metric values (e.g., STM turn count, LTM fact count) for the active persona.
6. THE Atelier SHALL render 8 architecture detail pages total: Memory (from mockup), MCP, State Management, Tool Registry/Gateway, Skills, Runtime, Evaluations, and Grounding, all following the same template structure.
7. WHEN the Architecture detail page has no live data available, THE Atelier SHALL display the detail page content from fixture data with a note indicating the data source.

### Requirement 8: Agents Surface

**User Story:** As a workshop participant, I want to view all 5 specialist agents with their status, tools, model configuration, and shipped/exercise state, so that I can understand the agent architecture and track my workshop progress.

#### Acceptance Criteria

1. WHEN the user navigates to Agents in the Sidebar, THE Atelier SHALL display a Workshop_Progress_Strip showing 5 segments (3 shipped solid, 2 exercise dashed) with a shipped/total fraction.
2. THE Agents surface SHALL display each agent as a vertical row card with: a Roman numeral, agent name (Fraunces 24px), role description, status indicators (Status_Dot + Status_Pill), tool chips, model tag ("Opus 4.6 · 0.2"), and an "Open [Agent]" link.
3. THE Agents surface SHALL display shipped agents (Search, Recommendation, Pricing) with solid borders, cream-elev background, and sage "Shipped" pills.
4. THE Agents surface SHALL display exercise agents (Inventory, Customer Support) with dashed borders, transparent background, burgundy "Exercise" pills, and an exercise files list showing the files to implement.
5. THE Agents surface SHALL display a "Related" callout card linking to the Skills surface and the Routing surface.
6. THE Agents surface tool chips for shipped agents SHALL use cream-2 background with solid borders, and tool chips for exercise agents SHALL use transparent background with dashed burgundy borders.

### Requirement 9: Tools Surface

**User Story:** As a workshop participant, I want to view all 9 tools with their signatures, status, and a live pgvector discovery demo, so that I can understand how agents find and invoke tools.

#### Acceptance Criteria

1. WHEN the user navigates to Tools in the Sidebar, THE Atelier SHALL display a Workshop_Progress_Strip showing 9 segments (6 shipped, 3 exercise) with a 6/9 fraction.
2. THE Tools surface SHALL display a discovery demo card at the top with a query input showing a sample natural-language query, and a ranked list of matching tools with cosine distances.
3. THE Tools discovery demo card SHALL execute a real pgvector similarity query against the tool_registry table and display results with rank numbers, tool names, shipped/exercise status, and distance scores.
4. THE Tools surface SHALL display each tool as a row card with: a numeral, function name (JetBrains Mono 17px), description, Status_Dot, Status_Pill, function signature (in a code block), "Used by" agent chips, and metadata (invocation count, version).
5. THE Tools surface SHALL display shipped tools (search_products, browse_category, compare_products, trending_products, price_analysis, return_policy) with solid borders and sage status.
6. THE Tools surface SHALL display exercise tools (inventory_health, restock_product, low_stock) with dashed borders and burgundy status.
7. THE Tools surface SHALL display a "Related" callout card linking to the Agents surface and the Architecture · Tool Registry detail page.

### Requirement 10: Routing Surface

**User Story:** As a workshop participant, I want to view the 3 routing patterns (Dispatcher, Agents-as-Tools, Graph) with their configurations and active status, so that I can understand how the orchestrator routes requests to specialists.

#### Acceptance Criteria

1. WHEN the user navigates to Routing in the Sidebar, THE Atelier SHALL display cards for the 3 routing patterns: Dispatcher, Agents-as-Tools, and Graph.
2. THE Routing surface SHALL indicate which pattern is currently active for the storefront (Dispatcher by default) with a live Status_Dot and "Active" Status_Pill.
3. THE Routing pattern card SHALL display the pattern name, a description of how it works, a code snippet or diagram showing the routing logic, and the list of agents it routes to.
4. THE Routing surface SHALL display Dispatcher as the active pattern for storefront sessions, correcting any prior display that showed Agents-as-Tools as the default.
5. IF the routing pattern data is unavailable, THEN THE Atelier SHALL display the routing cards from fixture data.

### Requirement 11: Memory Dashboard Surface

**User Story:** As a workshop participant, I want to view a live dashboard of the active persona's STM and LTM state, so that I can observe how memory accumulates and is recalled across sessions.

#### Acceptance Criteria

1. WHEN the user navigates to Memory in the Sidebar, THE Atelier SHALL display a memory dashboard for the active persona showing both STM and LTM tiers.
2. THE Memory dashboard SHALL display STM state including turn count, recent intents, and fresh items from the current session.
3. THE Memory dashboard SHALL display LTM state including stored preferences, prior order history, and behavioral patterns retrieved via pgvector semantic recall.
4. THE Memory dashboard SHALL include an orbit visualization showing the persona at center with memory items positioned on concentric rings.
5. IF no memory data exists for the active persona, THEN THE Atelier SHALL display an empty state explaining that no memory has been recorded.

### Requirement 12: Performance Surface

**User Story:** As a workshop participant, I want to view performance metrics including cold start times, latency budgets, and pgvector benchmarks, so that I can understand the system's operational characteristics.

#### Acceptance Criteria

1. WHEN the user navigates to Performance in the Sidebar, THE Atelier SHALL display stat cards for P50 cold start time and P50 warm reuse time with sample counts and distribution labels.
2. THE Performance surface SHALL display a cold start histogram as an SVG visualization showing the bimodal distribution of cold vs warm starts.
3. THE Performance surface SHALL display a per-panel latency budget table with rows for each panel type (LLM, tool, memory), horizontal bar fills proportional to time, and millisecond values.
4. THE Performance surface SHALL display a pgvector comparison table showing the three index strategies (IVFFlat, HNSW, brute-force) with columns for recall, QPS, build time, and storage, with the shipped strategy (HNSW) highlighted.
5. THE Performance surface SHALL display storage usage bars for catalog embeddings, tool registry, and memory vectors with sizes and percentages.
6. THE Performance surface SHALL display measure controls with time window selector (1h/6h/24h/7d pills), sample size slider, and a "Run benchmark" button.
7. IF performance data is unavailable, THEN THE Atelier SHALL display the performance surface from fixture data.

### Requirement 13: Evaluations Surface

**User Story:** As a workshop participant, I want to view agent evaluation scorecards with accuracy, latency, and citation metrics, so that I can understand how agent quality is measured and tracked.

#### Acceptance Criteria

1. WHEN the user navigates to Evaluations in the Sidebar, THE Atelier SHALL display evaluation scorecards for each agent showing accuracy, latency percentiles, and citation rates.
2. THE Evaluations surface SHALL display version-over-version quality trends for each evaluation recipe.
3. THE Evaluations surface SHALL follow the Exp_Card pattern with Eyebrows, editorial titles, and monospace metadata.
4. IF evaluation data is unavailable, THEN THE Atelier SHALL display the evaluations surface from fixture data.

### Requirement 14: Observatory Wide-Angle Dashboard

**User Story:** As a workshop participant, I want a wide-angle dashboard that shows a real-time overview of the entire agentic system, so that I can monitor all agents, tools, sessions, and performance at a glance.

#### Acceptance Criteria

1. WHEN the user navigates to Observatory in the Sidebar, THE Atelier SHALL display a wide-angle dashboard with summary cards for active sessions, agent status, tool invocations, memory state, and performance headlines.
2. THE Observatory SHALL display a live pulsing indicator in the Sidebar and on the dashboard to indicate real-time data.
3. THE Observatory summary cards SHALL follow the Exp_Card pattern and display key metrics with large serif numerals and monospace labels.
4. IF no live data is available, THEN THE Atelier SHALL display the observatory from fixture data with a note indicating mock data.

### Requirement 15: Design System Compliance

**User Story:** As a workshop participant, I want the Atelier to use a consistent editorial design system across all surfaces, so that the experience feels cohesive and polished.

#### Acceptance Criteria

1. THE Atelier SHALL use the following color tokens: cream-1 (#faf3e8), cream-2 (#f4ead6), cream-elev (#fffaf0), ink-1 (#1f1410), red-1 (#a8423a), green-1 (#6b8c5e), espresso-1 (#1f1410), espresso-2 (#2a1e18), and all ink/rule opacity variants defined in the mockups.
2. THE Atelier SHALL use Fraunces (serif, italic-capable) for editorial headlines, titles, and display type; Inter for UI body text, buttons, and navigation; and JetBrains Mono for code snippets, labels, eyebrows, and metadata.
3. THE Atelier SHALL use the Exp_Card pattern (cream-elev background, 1px rule-1 border, 14px border-radius, 24px burgundy accent line at top-left) for all content cards.
4. THE Atelier SHALL use the Eyebrow pattern (JetBrains Mono, 9-10px, letter-spacing 0.22em, uppercase, burgundy or ink-4 color, preceded by a small dot) for section labels.
5. THE Atelier SHALL use Status_Pills (shipped: green-soft background with green-1 text; exercise: red-soft background with red-1 text) and Status_Dots (live: burgundy pulsing; idle: ink-4; empty: burgundy outline) consistently.
6. THE Atelier SHALL render a flat editorial aesthetic with no glassmorphism, blurs, or gradients (except product image placeholders).
7. THE Atelier SHALL use tab navigation (Fraunces italic, 16px, with burgundy underline on active tab) for session detail views.

### Requirement 16: Data Wiring and Fixture Strategy

**User Story:** As a developer, I want a clear data strategy where early phases use mock fixtures and later phases wire to real API endpoints, so that the frontend can be built incrementally without backend dependencies.

#### Acceptance Criteria

1. THE Atelier SHALL load data from static fixture files in `/src/atelier/fixtures/` during Phase 0 and Phase 1.
2. WHEN real API endpoints are available (Phase 2+), THE Atelier SHALL fetch data from `/api/atelier/*` endpoints instead of fixtures.
3. THE Tools discovery card SHALL use the real pgvector backend (`/api/atelier/tools/discover`) for semantic tool search, even during early phases.
4. THE Atelier fixtures SHALL include mock data for: sessions list, session detail (chat turns, telemetry panels, brief content), agents, tools, routing patterns, memory state, performance metrics, evaluations, and observatory summary.
5. THE Atelier SHALL provide TypeScript interfaces for all fixture and API data shapes in a shared types file.

### Requirement 17: Build State Detection

**User Story:** As a workshop participant, I want the Atelier to automatically detect which tools and agents I have implemented, so that the UI reflects my workshop progress without manual configuration.

#### Acceptance Criteria

1. THE Atelier SHALL determine whether a tool or agent is "shipped" or "exercise" based on file existence checks or backend status responses.
2. WHEN a tool or agent transitions from exercise to shipped (file is implemented), THE Atelier SHALL update the corresponding card from dashed/exercise styling to solid/shipped styling.
3. THE Workshop_Progress_Strip SHALL update its segment fills to reflect the current shipped/exercise state of all items in the relevant category.

### Requirement 18: Persona and Settings

**User Story:** As a workshop participant, I want to select a demo persona from the Settings page, so that all Atelier surfaces show data scoped to that persona.

#### Acceptance Criteria

1. WHEN the user navigates to Settings in the Sidebar, THE Atelier SHALL display a persona selection interface.
2. THE Settings page SHALL default to Marco as the active persona.
3. WHEN the user selects a different persona, THE Atelier SHALL update all surfaces to show data scoped to the newly selected persona.
4. THE Sidebar footer SHALL update to reflect the currently active persona's name, avatar initial, and role.

### Requirement 19: Empty, Error, and Loading States

**User Story:** As a workshop participant, I want clear feedback when data is loading, unavailable, or errored, so that I understand the system state at all times.

#### Acceptance Criteria

1. WHILE data is loading for any surface, THE Atelier SHALL display a loading state consistent with the editorial design system (e.g., subtle skeleton placeholders or a centered loading indicator).
2. IF an API request fails, THEN THE Atelier SHALL display an error state with an editorial message explaining the failure and suggesting a retry.
3. IF a surface has no data to display, THEN THE Atelier SHALL display an empty state with an editorial message appropriate to the surface context.
4. THE Atelier SHALL provide loading, error, and empty states for every surface: Sessions list, Session detail (all 3 tabs), Architecture index, Architecture detail pages, Agents, Tools, Routing, Memory dashboard, Performance, Evaluations, and Observatory.

### Requirement 20: Routing and URL Structure

**User Story:** As a workshop participant, I want deep-linkable URLs for all Atelier surfaces, so that I can bookmark and share specific views.

#### Acceptance Criteria

1. THE Atelier SHALL be accessible at the `/atelier` route as the entry point.
2. THE Atelier SHALL support nested routes for session detail views (e.g., `/atelier/sessions/:id`).
3. THE Atelier SHALL support routes for each Understand surface (e.g., `/atelier/architecture`, `/atelier/agents`, `/atelier/tools`, `/atelier/routing`, `/atelier/memory`).
4. THE Atelier SHALL support routes for architecture detail pages (e.g., `/atelier/architecture/memory`, `/atelier/architecture/mcp`).
5. THE Atelier SHALL support routes for Measure surfaces (e.g., `/atelier/performance`, `/atelier/evaluations`).
6. THE Atelier SHALL support a route for the Observatory (e.g., `/atelier/observatory`).
7. THE Atelier SHALL support a route for Settings (e.g., `/atelier/settings`).
8. THE Atelier SHALL preserve the existing Boutique storefront at `/` without modification.

### Requirement 21: Backend API Endpoints

**User Story:** As a frontend developer, I want read-only API endpoints for all Atelier data, so that the frontend can fetch live data from the backend.

#### Acceptance Criteria

1. THE Backend SHALL expose a `GET /api/atelier/sessions` endpoint returning a list of sessions for the active persona.
2. THE Backend SHALL expose a `GET /api/atelier/sessions/:id` endpoint returning full session detail including chat turns, telemetry panels, and brief content.
3. THE Backend SHALL expose a `GET /api/atelier/agents` endpoint returning the list of 5 agents with their status, tools, and model configuration.
4. THE Backend SHALL expose a `GET /api/atelier/tools` endpoint returning the list of 9 tools with their signatures, status, and metadata.
5. THE Backend SHALL expose a `POST /api/atelier/tools/discover` endpoint accepting a natural-language query and returning ranked tool matches with cosine distances from pgvector.
6. THE Backend SHALL expose a `GET /api/atelier/memory/:persona` endpoint returning STM and LTM state for the specified persona.
7. THE Backend SHALL expose a `GET /api/atelier/routing` endpoint returning the 3 routing pattern configurations and which is currently active.
8. THE Backend SHALL expose a `GET /api/atelier/performance` endpoint returning cold start, latency budget, pgvector benchmark, and storage metrics.
9. THE Backend SHALL expose a `GET /api/atelier/evaluations` endpoint returning agent evaluation scorecards and version trends.
10. THE Backend SHALL expose a `GET /api/atelier/observatory` endpoint returning the wide-angle dashboard summary data.
11. THE Backend API endpoints SHALL be read-only (GET or safe POST for search) and SHALL NOT mutate any application state.

### Requirement 22: Frontend Code Organization

**User Story:** As a developer, I want all Atelier code organized under `/src/atelier/` with clear subdirectories, so that the codebase is maintainable and the Boutique storefront remains untouched.

#### Acceptance Criteria

1. THE Atelier frontend code SHALL reside under `pellier/frontend/src/atelier/` with subdirectories: `shell/` (sidebar, top bar, layout), `surfaces/` (one file per surface), `components/` (shared UI primitives), `fixtures/` (mock data), and `types/` (TypeScript interfaces).
2. THE Atelier SHALL NOT modify any existing Boutique storefront components or pages.
3. THE Atelier shared components SHALL include reusable primitives for: Eyebrow, ExpCard, StatusPill, StatusDot, WorkshopProgressStrip, CheatSheetStrip, DetailPageShell, TabNav, and BreadcrumbTrail.
