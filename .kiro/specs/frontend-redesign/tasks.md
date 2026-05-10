# Implementation Plan: Frontend Redesign

## Overview

Five-phase frontend rebuild of Pellier, replacing every visible surface with a cinematic editorial luxury aesthetic. Each phase ships as its own PR with the application remaining fully functional at every checkpoint. The rebuild preserves the frozen backend, chat drawer behavior, three-pattern agent model, and persona system. Implementation uses React 18, TypeScript, Tailwind CSS 3, and Framer Motion 12.

## Tasks

- [x] 1. Phase 1 — Design System + Primitives
  - [x] 1.1 Create design token module at `src/design/tokens.ts`
    - Export named constants for all color tokens (Cream `#F7F3EE`, Sand `#E8DFD4`, Espresso `#3B2F2F`, Olive `#6B705C`, Terracotta `#C44536`, plus preserved ink/cream/dusk palette values, Atelier dark surfaces `espressoDark #1F1410`, `espressoMid #2A1E18`)
    - Export spacing scale (4px base: xs through 3xl)
    - Export typography tokens referencing Fraunces (display), Inter (body), JetBrains Mono (mono)
    - Export warm-tinted shadow tokens (sm, md, lg, xl)
    - Export border radii tokens (sm through full)
    - Export animation timing tokens: 240ms ease-out for slides, 180ms ease-out for fades, spring config
    - Export responsive breakpoint tokens: mobile (768px), expansionStack (1280px — Atelier expansion area stacks below this), wide (1440px). Desktop band is implicit between mobile and wide
    - Export fluid layout tokens: containerPadding (`clamp(16px, 4vw, 48px)`), displaySize (`clamp(28px, 4vw, 48px)`), headlineSize (`clamp(22px, 3vw, 36px)`), bodySize (`clamp(14px, 1.1vw, 16px)` — narrow 2px range is intentional: reading distance doesn't change meaningfully between laptop sizes), gridCardMin (280px), maxWidth (1440px)
    - Export TypeScript types: `ColorToken`, `SpacingToken`, `ShadowToken`, `RadiusToken`, `AnimationTiming`
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 16.1, 16.2, 16.8_

  - [x] 1.2 Create typography stylesheet at `src/design/typography.css`
    - Add `@font-face` imports for Fraunces, Inter, and JetBrains Mono (using existing `@fontsource-variable` packages)
    - Add text utility classes for display, body, and mono styles
    - _Requirements: 1.3_

  - [x] 1.3 Extend `tailwind.config.js` with new token values
    - Add `cream-50: '#F7F3EE'` (not `cream-new`), `sand`, `espresso`, `olive`, `espresso-dark`, `espresso-mid` to `theme.extend.colors`
    - Add `warm-sm`, `warm-md`, `warm-xl` to `theme.extend.boxShadow`
    - Add `wide: '1440px'` and `expansion-stack: '1280px'` to `theme.extend.screens`
    - Add `'container-x': 'clamp(16px, 4vw, 48px)'` to `theme.extend.spacing` for fluid container horizontal padding
    - Preserve all existing color tokens (`cream`, `ink`, `accent`, etc.) and shadow tokens (`warm`, `warm-lg`) for backward compatibility
    - _Requirements: 1.4, 1.5, 16.2, 16.4_

  - [x] 1.4 Build 11 primitives in `src/design/primitives/`
    - [x] 1.4.1 Build Button primitive (`Button.tsx`)
      - Support three variants: primary (filled), secondary (outlined), ghost (text-only)
      - Support sizes: sm, md, lg
      - Consume only token values or extended Tailwind classes, no hardcoded literals
      - Include visible focus indicator for keyboard navigation
      - _Requirements: 2.1, 2.2, 2.3, 14.2_

    - [x] 1.4.2 Build Chip primitive (`Chip.tsx`)
      - Support suggestion/tag variants with active/inactive states
      - Consume only token values, no hardcoded literals
      - _Requirements: 2.1, 2.2_

    - [x] 1.4.3 Build Card primitive (`Card.tsx`)
      - Support variants: product, recommendation, reasoning, default
      - Render with warm-tinted soft shadows, no harsh borders
      - _Requirements: 2.1, 2.2, 2.4_

    - [x] 1.4.4 Build Input primitive (`Input.tsx`)
      - Support search bar variant (mic icon, ⌘K hint) and text input variant
      - Include visible focus indicator
      - _Requirements: 2.1, 2.2, 14.2_

    - [x] 1.4.5 Build Modal primitive (`Modal.tsx`)
      - Render via `createPortal` to `document.body`
      - Implement focus trap: Tab/Shift+Tab cycle within modal
      - Close on Escape key press
      - Accept `ariaLabel` prop for accessibility
      - _Requirements: 2.1, 2.5, 14.4_

    - [x] 1.4.6 Build Drawer primitive (`Drawer.tsx`)
      - Animate open/closed using Framer Motion with 240ms ease-out slide timing token
      - Render via `createPortal` to `document.body`
      - Implement focus trap while open
      - Support `side` prop for left/right positioning
      - Respect `prefers-reduced-motion` by disabling or reducing to opacity-only transitions
      - _Requirements: 2.1, 2.6, 2.9, 14.4_

    - [x] 1.4.7 Build Avatar primitive (`Avatar.tsx`)
      - Display single character monogram inside circular container
      - Support configurable background color and sizes (sm, md, lg)
      - _Requirements: 2.1, 2.7_

    - [x] 1.4.8 Build Pill primitive (`Pill.tsx`)
      - Support status indicator variants (Live, High confidence)
      - _Requirements: 2.1, 2.2_

    - [x] 1.4.9 Build IconButton primitive (`IconButton.tsx`)
      - Circular ghost button for header use
      - Include visible focus indicator
      - _Requirements: 2.1, 2.2, 14.2_

    - [x] 1.4.10 Build Sidebar primitive (`Sidebar.tsx`)
      - Support dark variant (espresso `#1F1410` background, cream text) and light variant
      - Accept nav items with active state, icons, and optional badges
      - _Requirements: 2.1, 2.2_

    - [x] 1.4.11 Build Timeline primitive (`Timeline.tsx`)
      - Render vertical sequence of numbered steps with connecting lines
      - Support `TimelineStepState` with statuses: `"pending"`, `"in-progress"`, `"complete"`, `"skipped"`
      - Visual states: pending (muted), in-progress (pulsing), complete (filled), skipped (dimmed with skip indicator)
      - Respect `prefers-reduced-motion` for pulsing animation
      - _Requirements: 2.1, 2.8, 2.9_

  - [x] 1.5 Create barrel export at `src/design/primitives/index.ts`
    - Re-export all 11 primitives from a single entry point
    - _Requirements: 2.1_

  - [x] 1.6 Create `src/design/README.md` documenting the design system
    - Document each primitive, its props, variants, and usage examples
    - Document the color palette, typography, spacing, shadow, and animation tokens
    - _Requirements: 2.10_

  - [x] 1.7 Create `/dev/design-system` preview route
    - Create `DesignSystemPreview` page component
    - Guard with `import.meta.env.DEV` so production builds exclude it via Vite dead-code elimination
    - Render every primitive in all supported variants, sizes, and interactive states (default, hover, focus, disabled, active)
    - Display color palette with token names and hex values side by side
    - Display typography samples for each font family and weight
    - Register route in `App.tsx`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]\* 1.8 Write unit tests for all Phase 1 primitives
    - Test each primitive renders without crashing
    - Test Button renders all three variants (primary, secondary, ghost)
    - Test Card renders with warm shadow tokens
    - Test Modal renders via portal to `document.body`
    - Test Drawer animates with 240ms timing
    - Test Avatar renders monogram character
    - Test Timeline renders correct number of steps and supports `"skipped"` status
    - Test Preview route renders all primitives
    - Test color palette display shows token names and hex values
    - Test `prefers-reduced-motion` disables animations on animated primitives
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.3, 3.4_

  - [ ]\* 1.9 Install `fast-check` and write property-based tests for Phase 1
    - [ ]\* 1.9.1 Write property test: No hardcoded color or spacing literals in primitives
      - **Property 1: No hardcoded color or spacing literals in primitives**
      - For any primitive source file in `src/design/primitives/`, assert no hardcoded hex color values or pixel spacing values outside token imports
      - **Validates: Requirements 2.2**

    - [ ]\* 1.9.2 Write property test: Focus trap containment
      - **Property 2: Focus trap containment**
      - For any set of focusable elements (1-20) inside an open Modal or Drawer, Tab from last element wraps to first, Shift+Tab from first wraps to last
      - **Validates: Requirements 2.5, 14.4**

    - [ ]\* 1.9.3 Write property test: Avatar monogram rendering
      - **Property 3: Avatar monogram rendering**
      - For any single Unicode character and any valid CSS color string, Avatar renders that character centered with the specified background color
      - **Validates: Requirements 2.7**

    - [ ]\* 1.9.4 Write property test: Timeline step count invariant
      - **Property 4: Timeline step count invariant**
      - For any list of N steps (N >= 1), Timeline renders exactly N step indicators and exactly N-1 connecting lines
      - **Validates: Requirements 2.8**

  - [x] 1.10 Verify old app still renders correctly
    - Confirm existing CSS custom properties (`--cream`, `--ink`, `--accent`) still exist in `index.css`
    - Confirm existing Tailwind tokens (`cream`, `ink`, `accent`, `warm`, `warm-lg`) are preserved
    - Run `tsc && vite build` to verify no build errors
    - _Requirements: 1.5, 12.1_

  - [x] 1.11 Create `PHASE_1_NOTES.md`
    - Document design decisions, token naming rationale (`cream-50` not `cream-new`), and any deviations from reference images
    - _Requirements: 12.6_

- [x] 2. Checkpoint — Phase 1 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 2 — Boutique Rebuild
  - [x] 3.1 Rebuild Header component
    - Centered "Pellier" wordmark with circular B logo
    - Five nav items: Home, Shop, Storyboard, Discover, Account
    - Surface toggle (Storefront ↔ Atelier)
    - Replace PersonaPill + PersonaModal with persona Avatar dropdown using Avatar primitive
    - Avatar dropdown: shows persona monogram when signed in, generic user icon when signed out
    - Dropdown calls `switchPersona` hook flow directly (not PersonaModal)
    - Dropdown closes on outside click or Escape
    - Bag icon with live count badge
    - Sticky with `backdrop-filter: blur(12px)` and `-webkit-backdrop-filter` prefix
    - _Requirements: 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 15.3_

  - [x] 3.2 Rebuild HeroStage component
    - Restyle with new primitives and design tokens
    - Preserve existing 8-intent rotation cycle, 7.5-second cadence, hover-pause behavior, and ticker chip click-to-jump behavior
    - Hero search bar submission opens ChatDrawer via existing `openDrawerWithQuery`
    - _Requirements: 4.1, 4.4_

  - [x] 3.3 Rebuild ProductGrid component
    - Use Card primitive with warm-tinted shadows
    - Use CSS Grid with `auto-fill` and `minmax(280px, 1fr)` so columns adjust dynamically (1 col mobile → 2-3 cols on 14" laptops → 3-4 cols on 16" displays)
    - Implement scroll-reveal fade-in using IntersectionObserver
    - Respect `prefers-reduced-motion` by disabling animation
    - _Requirements: 4.2, 14.5, 16.3_

  - [x] 3.4 Rebuild Footer component
    - Brand column, explore links, editorial columns, bottom copyright strip
    - Use new primitives and tokens
    - _Requirements: 4.5_

  - [x] 3.5 Restyle ChatDrawer visual layer
    - Same `useAgentChat` hook, SSE streaming, message persistence, three entry points
    - Apply new tokens: warm shadows, Fraunces display type for header, Inter for message body
    - 240ms ease-out slide animation matching Drawer primitive timing
    - Success gate: side-by-side visual diff showing only token/font/shadow changes, zero behavioral changes
    - _Requirements: 6.1, 6.2, 6.4_

  - [x] 3.6 Restyle CommandPill visual layer
    - Same fixed bottom-right positioning, keyboard shortcut display, surface-aware toggle behavior
    - Apply new design tokens
    - Success gate: side-by-side visual diff showing only visual layer changes, zero behavioral changes
    - _Requirements: 6.3_

  - [x] 3.7 Apply Cream `#F7F3EE` background, editorial whitespace, and fluid container
    - Update StorefrontPage to use `cream-50` background token
    - Apply fluid `max-width: 1440px` container with `container-x` padding token (`clamp(16px, 4vw, 48px)`)
    - On wide displays (> 1440px), content centers with `margin: 0 auto` — wide displays get more breathing room, not more content
    - Use fluid typography tokens (`clamp()`) for display and headline text so type scales proportionally between 14" laptops and 16" displays
    - Ensure generous editorial whitespace throughout
    - Verify no horizontal scrollbar at any viewport width between 320px and 2560px
    - _Requirements: 4.7, 16.4, 16.8, 16.10_

  - [ ]\* 3.8 Write unit tests for Phase 2 components
    - Test Header renders wordmark, 5 nav items, surface toggle, persona dropdown, bag icon
    - Test Hero stage preserves 8-intent rotation and hover-pause behavior
    - Test Product grid renders with Card primitive
    - Test Footer renders all columns
    - Test ChatDrawer restyled with new tokens (visual snapshot)
    - Test CommandPill preserves positioning and keyboard shortcut display
    - Test Persona dropdown opens on click, closes on outside click and Escape
    - Test Hero search bar submission opens ChatDrawer with query
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 5.1, 5.5, 6.2, 6.3_

  - [ ]\* 3.9 Write property-based tests for Phase 2
    - [ ]\* 3.9.1 Write property test: Persona avatar dropdown data binding
      - **Property 5: Persona avatar dropdown data binding**
      - For any persona with non-empty `display_name` and `avatar_initial`, the Avatar dropdown trigger displays the persona's monogram and includes the display name
      - **Validates: Requirements 5.2**

    - [ ]\* 3.9.2 Write property test: WCAG AA contrast compliance
      - **Property 10: WCAG AA contrast compliance**
      - For any foreground/background color pair from the token palette used together, computed contrast ratio meets WCAG AA thresholds (4.5:1 normal text, 3:1 large text)
      - **Validates: Requirements 10.5, 14.1**

    - [ ]\* 3.9.3 Write property test: Visible focus indicators on interactive primitives
      - **Property 11: Visible focus indicators on interactive primitives**
      - For any interactive primitive (Button, Chip, Input, IconButton, Sidebar item), when receiving keyboard focus via Tab, a visible focus indicator is present
      - **Validates: Requirements 14.2**

    - [ ]\* 3.9.4 Write property test: Backdrop-filter vendor prefix pairing
      - **Property 12: Backdrop-filter vendor prefix pairing**
      - For any source file containing `backdrop-filter`, that file also contains `-webkit-backdrop-filter` with the same value
      - **Validates: Requirements 15.3**

    - [ ]\* 3.9.5 Write property test: No horizontal overflow at any viewport width
      - **Property 13: No horizontal overflow at any viewport width**
      - For any viewport width between 320px and 2560px (sampled at 50px increments), assert `document.documentElement.scrollWidth <= document.documentElement.clientWidth` on both Boutique and Atelier routes
      - **Validates: Requirements 16.10**

  - [x] 3.10 Verify Atelier still renders with old components
    - Confirm `/atelier` route renders without errors using existing WorkshopPage
    - Run `tsc && vite build` to verify no build errors
    - _Requirements: 12.2_

  - [x] 3.11 Lighthouse audit: Boutique >= 90
    - Run Lighthouse performance audit on the Boutique landing page
    - _Requirements: 4.6_

  - [x] 3.12 Create `PHASE_2_NOTES.md`
    - Document design decisions, ChatDrawer/CommandPill visual diff results, and any deviations
    - _Requirements: 12.6_

- [x] 4. Checkpoint — Phase 2 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 3 — Atelier Shell Rebuild
  - [x] 5.1 Build AtelierPage shell replacing WorkshopPage layout
    - `/atelier` renders session list with cold-start fallback (editorial empty state with suggestion pills and chat drawer entry points) when no session is active
    - Dark espresso sidebar (fixed 240-260px), top bar with breadcrumb and live session indicator, main content area fills remaining viewport width fluidly
    - Main canvas uses `calc(100vw - sidebar-width)` or CSS Grid `1fr` to adapt to any laptop screen size (14" through 16")
    - _Requirements: 7.1, 7.2, 16.5_

  - [x] 5.2 Build dark Sidebar
    - Espresso `#1F1410` background, cream text
    - Nav items: Observatory, Sessions, Memory, Inventory, Agents, Tools, Evaluations, Settings
    - Active state highlighting
    - _Requirements: 7.1_

  - [x] 5.3 Build top bar with breadcrumb trail and live session indicator
    - Breadcrumb updates to reflect current sidebar section
    - Live session indicator shows active session status
    - _Requirements: 7.2, 7.6_

  - [x] 5.4 Build session detail layout
    - Mode Strip positioned above editorial title
    - Recommendation rail to the right
    - _Requirements: 7.3_

  - [x] 5.5 Build Mode Strip component
    - Pattern I (Agents-as-Tools) and Pattern II (Graph) as selectable pills with active states
    - Pattern III (Dispatcher) as non-selectable pill with dashed border, reduced opacity, "Storefront · Production" label
    - Clicking Pattern III opens explainer popover but does NOT switch modes
    - Visual separator between selectable patterns (I, II) and informational pattern (III)
    - Pass selected pattern to `useAgentChat` hook's pattern parameter
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 5.6 Build session list view
    - Card-based list of available sessions with timestamps and summary info
    - _Requirements: 7.4_

  - [x] 5.7 Build placeholder views for sidebar sections
    - Memory, Inventory, Agents, Tools, Evaluations, Settings
    - Each renders as placeholder card with "Coming soon" messaging
    - Accessible from sidebar navigation
    - _Requirements: 7.5_

  - [ ]\* 5.8 Write unit tests for Phase 3 components
    - Test Atelier renders dark sidebar with espresso background
    - Test top bar renders breadcrumb and session indicator
    - Test Mode Strip renders 3 patterns with correct selectability
    - Test Pattern III click does not change active pattern
    - Test session list renders with timestamps
    - Test placeholder views render for all 6 sidebar sections
    - Test cold-start fallback renders when no session is active
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1_

  - [ ]\* 5.9 Write property-based tests for Phase 3
    - [ ]\* 5.9.1 Write property test: Breadcrumb reflects sidebar navigation
      - **Property 6: Breadcrumb reflects sidebar navigation**
      - For any sidebar item click, the breadcrumb terminal segment matches the clicked item's label
      - **Validates: Requirements 7.6**

    - [ ]\* 5.9.2 Write property test: Pattern III non-selectability
      - **Property 7: Pattern III non-selectability**
      - For any current active pattern (I or II), clicking Pattern III does not change the active pattern
      - **Validates: Requirements 8.1**

    - [ ]\* 5.9.3 Write property test: Pattern selection propagation
      - **Property 8: Pattern selection propagation**
      - For any selectable pattern (agents_as_tools or graph), selecting it visually highlights it and passes the corresponding parameter to the chat hook
      - **Validates: Requirements 8.2**

  - [x] 5.10 Verify Boutique still renders correctly
    - Confirm `/` route renders the rebuilt Boutique without errors
    - Run `tsc && vite build` to verify no build errors
    - _Requirements: 12.3_

  - [x] 5.11 Lighthouse audit: Atelier >= 85
    - Run Lighthouse performance audit on the Atelier shell
    - _Requirements: 7.7_

  - [x] 5.12 Create `PHASE_3_NOTES.md`
    - Document design decisions, sidebar nav structure, Mode Strip behavior, and any deviations
    - _Requirements: 12.6_

- [ ] 6. Checkpoint — Phase 3 complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Phase 4 — Atelier Reasoning Timeline
  - [ ] 7.1 Build ReasoningTimeline component
    - Six numbered steps using Timeline primitive: Understanding intent, Retrieving memory, Scanning inventory, Ranking, Agent collaboration, Final recommendation
    - Steps support pending → in-progress → complete AND pending → skipped transitions
    - _Requirements: 9.1, 9.2_

  - [ ] 7.2 Wire ReasoningTimeline to SSE telemetry events
    - Map SSE events to timeline steps per the design doc mapping table:
      - `skill_routing` → Step 1 (Understanding intent): mark complete
      - `agent_step` (memory agent) → Step 2 (Retrieving memory): in-progress/complete
      - `tool_call` (search/inventory) → Step 3 (Scanning inventory): in-progress
      - `agent_step` (recommendation) → Step 4 (Ranking): in-progress
      - `agent_step` (orchestrator) → Step 5 (Agent collaboration): in-progress
      - `content_delta` (final) → Step 6 (Final recommendation): complete
    - Build a state reducer enforcing forward-only transitions (pending → in-progress → complete, or pending → skipped)
    - _Requirements: 9.2_

  - [ ] 7.3 Build three-column expansion area
    - Column 1: "How we arrived at this" — reasoning narrative
    - Column 2: "What we know about you" — Memory Orbit SVG
    - Column 3: "A team of specialists" — agent team cards
    - Use CSS Grid that transitions: 3 equal columns (wide > 1440px) → 2+1 stacked (below `expansionStack` token at 1280px) → 1 column (< 768px)
    - _Requirements: 9.3, 16.6_

  - [ ] 7.4 Build Memory Orbit SVG
    - Animated variant with orbiting nodes depicting memory retrieval
    - Static variant for `prefers-reduced-motion`
    - _Requirements: 9.3, 9.5_

  - [ ] 7.5 Build footer strip
    - Exact pull-quote: "The Atelier doesn't just automate. It reasons, remembers and refines."
    - At-a-glance metrics row: total duration, success rate
    - _Requirements: 9.4_

  - [ ]\* 7.6 Write unit tests for Phase 4 components
    - Test ReasoningTimeline renders 6 numbered steps
    - Test three-column expansion area renders with correct titles
    - Test footer strip renders pull-quote and metrics
    - Test Memory Orbit SVG renders static layout with `prefers-reduced-motion`
    - Test step transitions: pending → in-progress → complete, pending → skipped
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]\* 7.7 Write property-based tests for Phase 4
    - [ ]\* 7.7.1 Write property test: Timeline step forward-only transitions
      - **Property 9a: Timeline step forward-only transitions**
      - For any valid sequence of SSE telemetry events (including skipped steps for Pattern II graph mode), each step only transitions forward: pending → in-progress → complete, or pending → skipped. No step regresses
      - **Validates: Requirements 9.2**

    - [ ]\* 7.7.2 Write property test: Timeline step completion ordering
      - **Property 9b: Timeline step completion ordering**
      - For any pair of completed steps N and N-1, step N's `completedAt` >= step N-1's `completedAt`. Steps with "skipped" or "pending" status are exempt
      - **Validates: Requirements 9.2**

  - [ ] 7.8 Verify Boutique still renders correctly
    - Confirm `/` route renders without errors
    - Run `tsc && vite build` to verify no build errors
    - _Requirements: 12.4_

  - [ ] 7.9 Create `PHASE_4_NOTES.md`
    - Document SSE mapping decisions, timeline state machine design, and any deviations
    - _Requirements: 12.6_

- [ ] 8. Checkpoint — Phase 4 complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Phase 5 — Mobile
  - [ ] 9.1 Gate: verify mobile Atelier mockups exist
    - Check `docs/redesign-references/mobile-atelier/` for mockup artifacts
    - If mockups don't exist, defer mobile Atelier work and document in phase notes
    - _Requirements: 11.0_

  - [ ] 9.2 Mobile Boutique layout
    - Bottom navigation bar replacing desktop header nav at viewport < 768px
    - Hero stage stacks info card below image instead of overlaying
    - Product grid renders single-column with full-width cards (CSS Grid `auto-fill` naturally collapses to 1 column)
    - Use `100dvh` not `100vh` for iOS Safari and Android navigation bar compatibility
    - Verify no horizontal scrollbar at named demo widths: 320px (iPhone SE), 375px (iPhone), 412px (Samsung Galaxy), 768px (iPad Mini), 1024px, 1280px (14" laptop), 1440px, 1728px (16" MacBook Pro), 1920px, 2560px
    - _Requirements: 10.1, 10.2, 10.3, 16.9, 16.10_

  - [ ] 9.3 Mobile ChatDrawer
    - Preserve existing mobile bottom-sheet variant unchanged (drag handle, 80dvh height)
    - Apply Phase 1 visual layer updates only (tokens, fonts, shadows)
    - Do not modify bottom-sheet structural behavior
    - _Requirements: 10.4_

  - [ ] 9.4 Mobile Atelier layout
    - Sidebar as slide-in drawer triggered by hamburger menu button at viewport < 768px
    - Single-column session list
    - Reasoning timeline three-column expansion stacks vertically into single column
    - Mode strip renders as horizontally scrollable strip
    - Use `100dvh` not `100vh` for iOS Safari
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ]\* 9.5 Write unit tests for Phase 5 responsive behavior
    - Test Mobile Boutique renders bottom nav at 767px viewport
    - Test Hero stage stacks info card below image at 767px
    - Test Product grid renders single-column at 767px
    - Test Mobile Atelier sidebar renders as drawer at 767px
    - Test Mode strip renders as horizontally scrollable at 767px
    - Test WCAG AA contrast ratios on mobile layout
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 11.1, 11.4_

  - [ ] 9.6 Verify desktop still works at desktop viewports
    - Confirm Boutique and Atelier render correctly at >= 768px
    - Run `tsc && vite build` to verify no build errors
    - _Requirements: 12.5_

  - [ ] 9.7 Create `PHASE_5_NOTES.md`
    - Document mobile breakpoint decisions, `100dvh` usage, mockup gate result, and any deviations
    - _Requirements: 12.6_

- [ ] 10. Final checkpoint — All phases complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify no backend files were modified across all phases
  - Verify no new heavyweight dependencies added beyond React 18, Tailwind CSS 3, Framer Motion 12, and lucide-react (fast-check is dev-only and under 10KB gzipped)
  - _Requirements: 13.1, 13.2_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between phases
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `cream-50` Tailwind color name (not `cream-new`) was decided during design review
- The `"skipped"` status on `TimelineStepState` is critical for Pattern II graph mode where unmatched specialist nodes are skipped
- Restyled components (ChatDrawer, CommandPill) require explicit side-by-side visual diff success gates — snapshot tests alone are insufficient
- `fast-check` is under 10KB gzipped and qualifies under the lightweight utility exception (Requirement 13.4)
- All existing hooks and contexts (`useAgentChat`, `usePersona`, `useUI`, `useCart`, `useAuth`, `useLayout`) are preserved unchanged
