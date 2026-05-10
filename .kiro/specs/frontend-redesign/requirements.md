# Requirements Document

## Introduction

Complete frontend rebuild of the Pellier application, replacing every visible surface with a cinematic editorial luxury aesthetic while preserving the frozen backend, chat drawer behavior, three-pattern agent model, and persona system. The rebuild ships as five sequential phases, each as its own PR, with the application remaining fully functional at every checkpoint.

## Glossary

- **Boutique**: The customer-facing e-commerce storefront surface served at the `/` route
- **Atelier**: The AI observatory and instrumentation surface served at the `/atelier` route, providing telemetry, architecture cards, and chat
- **Design_System**: The collection of design tokens (colors, typography, spacing, shadows, radius) and reusable component primitives that form the visual foundation for both Boutique and Atelier surfaces
- **Primitive**: A low-level, reusable UI component (Button, Chip, Card, Input, Modal, Drawer, Avatar, Pill, IconButton, Sidebar, Timeline) built from design tokens
- **Design_Token**: An exported constant or CSS custom property defining a single visual attribute (color, font size, spacing, shadow, radius) consumed by primitives and page components
- **Chat_Drawer**: The right-side slide-in chat panel on the Boutique surface, powered by the `useAgentChat` hook, that streams agent responses via SSE
- **Three_Pattern_Model**: The three agent orchestration patterns available in the Atelier: Pattern I (Agents-as-Tools), Pattern II (Graph), Pattern III (Dispatcher)
- **Persona_System**: The workshop persona mechanism (Marco, Anna, fresh visitor) that scopes chat context, long-term memory, and order history by customer_id
- **Reasoning_Timeline**: A vertical numbered timeline in the Atelier session detail view showing the six reasoning steps an agent traverses during a recommendation turn
- **Session_Detail**: The Atelier view displaying a single chat session with editorial title, recommendation rail, pattern mode strip, and reasoning timeline
- **Mode_Strip**: A horizontal selector at the top of the Atelier session detail view allowing the user to switch between the three agent orchestration patterns
- **Hero_Stage**: The cinematic hero section on the Boutique landing page that cycles through shopper intents with cross-fading product imagery
- **Preview_Route**: A development-only route at `/dev/design-system` that renders every primitive in all states for visual QA
- **SSE_Telemetry**: Server-Sent Events stream carrying agent steps, tool calls, reasoning steps, skill routing, and runtime timing data from the backend to the frontend
- **Memory_Orbit_SVG**: An animated SVG visualization in the Atelier reasoning expansion area depicting the user memory retrieval process as orbiting nodes

## Requirements

### Requirement 1: Design Token Foundation

**User Story:** As a developer, I want a centralized set of design tokens exported from a single TypeScript module, so that every component in the rebuild draws from one source of truth for colors, typography, spacing, shadows, and border radii.

#### Acceptance Criteria

1. THE Design_System SHALL export a `tokens.ts` module from `src/design/tokens.ts` containing named constants for all color, spacing, typography, shadow, and radius values
2. WHEN a color token is defined, THE Design_System SHALL include at minimum: Cream `#F7F3EE`, Sand `#E8DFD4`, Espresso `#3B2F2F`, Olive `#6B705C`, Terracotta accent, and the existing ink/cream/dusk palette values
3. WHEN a typography token is defined, THE Design_System SHALL reference Fraunces for display and editorial headlines, Inter for UI body text, and JetBrains Mono for code and monospace surfaces
4. THE Design_System SHALL extend the Tailwind configuration in `tailwind.config.js` with all new token values so that Tailwind utility classes reflect the redesigned palette
5. WHEN the old design system tokens are still referenced by unrebuilt components, THE Design_System SHALL preserve the existing CSS custom properties in `index.css` alongside the new tokens until all phases are complete
6. THE Design_System SHALL define default animation timing tokens: 240ms ease-out for slides and 180ms ease-out for fades

### Requirement 2: Component Primitives

**User Story:** As a developer, I want a library of 11 reusable component primitives built from the new design tokens, so that all rebuilt pages compose from a consistent visual vocabulary.

#### Acceptance Criteria

1. THE Design_System SHALL provide the following 11 primitives in `src/design/primitives/`: Button, Chip, Card, Input, Modal, Drawer, Avatar, Pill, IconButton, Sidebar, Timeline
2. WHEN a Primitive is rendered, THE Primitive SHALL consume only values from the Design_Token module or the extended Tailwind configuration, not hardcoded color or spacing literals
3. THE Button Primitive SHALL support at minimum three variants: primary (filled), secondary (outlined), and ghost (text-only)
4. THE Card Primitive SHALL render with warm-tinted soft shadows matching the editorial luxury aesthetic and no harsh borders
5. THE Modal Primitive SHALL trap keyboard focus, close on Escape, and render via `createPortal` to `document.body`
6. THE Drawer Primitive SHALL animate open and closed using Framer Motion with the 240ms ease-out slide timing token
7. THE Avatar Primitive SHALL display a single character monogram inside a circular container with configurable background color
8. THE Timeline Primitive SHALL render a vertical sequence of numbered steps with connecting lines between them
9. WHEN `prefers-reduced-motion` is active, THE Primitive animations SHALL be disabled or reduced to opacity-only transitions
10. THE Design_System SHALL include a `README.md` in `src/design/` documenting each primitive, its props, and usage examples

### Requirement 3: Design System Preview Route

**User Story:** As a developer, I want a development-only route at `/dev/design-system` that renders every primitive in all its variants and states, so that I can visually QA the design system without navigating the full application.

#### Acceptance Criteria

1. WHEN the application is running in development mode, THE Preview_Route SHALL be accessible at `/dev/design-system`
2. WHEN the application is running in production mode, THE Preview_Route SHALL not be included in the production bundle
3. THE Preview_Route SHALL render every Primitive in all supported variants, sizes, and interactive states (default, hover, focus, disabled, active)
4. THE Preview_Route SHALL display the color palette with token names and hex values side by side
5. THE Preview_Route SHALL display typography samples for each font family and weight defined in the Design_Token module

### Requirement 4: Boutique Landing Page Rebuild

**User Story:** As a customer, I want the Boutique landing page to present a cinematic editorial luxury experience with a hero stage, product grid, and editorial teasers, so that browsing feels like reading a high-end magazine.

#### Acceptance Criteria

1. THE Boutique SHALL render a rebuilt Hero_Stage section using new primitives and design tokens while preserving the existing 8-intent rotation cycle, 7.5-second cadence, hover-pause behavior, and ticker chip click-to-jump behavior
2. THE Boutique SHALL render a rebuilt product grid using the Card Primitive with warm-tinted shadows and gentle scroll-reveal fade-in. Animation timing SHALL respect prefers-reduced-motion
3. THE Boutique SHALL render a rebuilt header with the centered "Pellier" wordmark, five navigation items, surface toggle, persona pill, and bag icon with live count badge
4. WHEN the hero search bar receives a query submission, THE Boutique SHALL open the existing Chat_Drawer with the query already streaming, preserving the current `openDrawerWithQuery` behavior
5. THE Boutique SHALL render a rebuilt footer with brand column, explore links, editorial columns, and bottom copyright strip using new primitives and tokens
6. THE Boutique SHALL achieve a Lighthouse performance score of 90 or higher
7. WHEN a customer navigates to the Boutique, THE Boutique SHALL use generous editorial whitespace and the Cream `#F7F3EE` background color

### Requirement 5: Persona Switcher Relocation

**User Story:** As a customer, I want to access the persona switcher from a top-right avatar dropdown in the header, so that switching personas is always one click away without a separate modal flow.

#### Acceptance Criteria

1. THE Boutique header SHALL render the persona switcher as a top-right Avatar dropdown that opens on click
2. WHEN a persona is active, THE Avatar dropdown trigger SHALL display the persona's monogram initial and display name
3. WHEN no persona is active, THE Avatar dropdown trigger SHALL display a generic user icon with a "Sign in" label
4. WHEN a persona is selected from the dropdown, THE Persona_System SHALL execute the same `switchPersona` hook flow including session regeneration and chat history clearing
5. THE Avatar dropdown SHALL close when the user clicks outside of it or presses Escape

### Requirement 6: Chat Drawer Visual Refresh

**User Story:** As a customer, I want the floating "Ask Pellier" pill and the chat drawer to match the new editorial luxury aesthetic, so that the conversational experience feels cohesive with the rebuilt storefront.

#### Acceptance Criteria

1. THE Chat_Drawer SHALL retain the same `useAgentChat` hook, SSE streaming behavior, message persistence, and three entry points (CommandPill click, keyboard shortcut, suggestion pill click)
2. THE Chat_Drawer SHALL be restyled using new primitives and design tokens with warm-tinted shadows, Fraunces display type for the header, and Inter for message body text
3. THE CommandPill SHALL be restyled using new design tokens while preserving its fixed bottom-right positioning, keyboard shortcut display, and surface-aware toggle behavior
4. WHEN the Chat_Drawer is open, THE Chat_Drawer SHALL animate in from the right at 240ms ease-out matching the Drawer Primitive timing
5. IF the Chat_Drawer fails to connect to the backend, THEN THE Chat_Drawer SHALL display the same offline fallback message as the current implementation

### Requirement 7: Atelier Shell Rebuild

**User Story:** As a workshop participant, I want the Atelier shell to feature a dark espresso sidebar, a top bar with breadcrumb and live session indicator, and a clean session layout, so that the instrumentation surface feels like a professional observatory.

#### Acceptance Criteria

1. THE Atelier SHALL render a dark Sidebar using the Sidebar Primitive with an espresso `#1f1410` background and cream text
2. THE Atelier SHALL render a top bar containing a breadcrumb trail and a live session indicator showing the active session status
3. THE Atelier session detail layout SHALL display the Mode_Strip above the editorial title, a recommendation rail to the right, with the Mode_Strip positioned at the top of the main content area before any other session content
4. THE Atelier SHALL render a session list view showing all available sessions with timestamps and summary information
5. THE Atelier SHALL render placeholder views for Memory, Inventory, Agents, Tools, Evaluations, and Settings sections accessible from the Sidebar
6. WHEN the user navigates between Atelier sections via the Sidebar, THE Atelier SHALL update the breadcrumb trail to reflect the current location
7. THE Atelier SHALL achieve a Lighthouse performance score of 85 or higher

### Requirement 8: Three-Pattern Mode Strip

**User Story:** As a workshop participant, I want a mode strip at the top of the Atelier session detail view that lets me switch between the three agent orchestration patterns, so that I can observe how each pattern processes the same query differently.

#### Acceptance Criteria

1. THE Mode_Strip SHALL render three pattern representations: Pattern I (Agents-as-Tools) and Pattern II (Graph) as selectable pills with active states; Pattern III (Dispatcher) as a visually distinct non-selectable pill with dashed border, reduced opacity, and a "Storefront · Production" label. Clicking Pattern III SHALL open a small explainer describing the pattern's role and pointing to the Storefront, but SHALL NOT switch the Atelier into dispatcher mode (which is not implemented)
2. WHEN a pattern is selected, THE Mode_Strip SHALL visually highlight the active pattern and pass the selection to the existing chat hook's pattern parameter
3. THE Mode_Strip SHALL preserve the current three-pattern switching behavior without modifying any backend API calls or payload shapes
4. THE Mode_Strip SHALL include a subtle visual separator between the selectable patterns (I and II) and the informational pattern (III), reinforcing the spatial grammar of "interactive options" vs "reference representation"

### Requirement 9: Reasoning Timeline

**User Story:** As a workshop participant, I want a vertical numbered reasoning timeline in the Atelier session detail view that shows the six steps an agent traverses during a recommendation, so that I can understand the agent's decision-making process in real time.

#### Acceptance Criteria

1. THE Reasoning_Timeline SHALL render six numbered steps using the Timeline Primitive: understanding intent, retrieving memory, scanning inventory, ranking, agent collaboration, and final recommendation
2. WHEN SSE_Telemetry events arrive, THE Reasoning_Timeline SHALL update each step's status in real time (pending, in-progress, complete)
3. THE Reasoning_Timeline SHALL render a three-column expansion area below the timeline with columns titled "How we arrived at this", "What we know about you" (containing the Memory_Orbit_SVG), and "A team of specialists"
4. THE Reasoning_Timeline footer strip SHALL render the editorial pull-quote "The Atelier doesn't just automate. It reasons, remembers and refines." alongside an at-a-glance metrics row matching image 1's bottom strip (total duration, success rate)
5. WHEN `prefers-reduced-motion` is active, THE Memory_Orbit_SVG animation SHALL be replaced with a static layout

### Requirement 10: Mobile Boutique

**User Story:** As a mobile customer, I want the Boutique to be fully usable on screens narrower than 768px with a splash screen, responsive home layout, responsive product page, and bottom navigation, so that the editorial luxury experience translates to handheld devices.

#### Acceptance Criteria

1. WHEN the viewport width is below 768px, THE Boutique SHALL render a mobile-optimized layout with a bottom navigation bar replacing the desktop header navigation
2. WHEN the viewport width is below 768px, THE Boutique hero stage SHALL stack the info card below the image instead of overlaying it
3. WHEN the viewport width is below 768px, THE product grid SHALL render in a single-column layout with full-width cards
4. WHEN the viewport width is below 768px, THE Chat_Drawer SHALL preserve its existing mobile bottom-sheet variant unchanged. Visual layer updates from Phase 1 SHALL apply, but the bottom-sheet structural behavior, drag handle, and 80dvh height are not modified
5. THE Boutique mobile layout SHALL maintain WCAG AA color contrast ratios across all text and interactive elements

### Requirement 11: Mobile Atelier

**User Story:** As a mobile workshop participant, I want the Atelier to be usable on screens narrower than 768px with the sidebar as a drawer, responsive session list, session detail, and reasoning timeline, so that I can observe agent behavior from a tablet or phone.

#### Acceptance Criteria

0. WHEN Phase 5 begins, mobile Atelier mockups SHALL exist as HTML artifacts in `docs/redesign-references/mobile-atelier/`. Phase 5 implementation SHALL not begin without these mockups in place. The mockups serve as the visual contract for mobile Atelier the same way the existing reference images serve for desktop
1. WHEN the viewport width is below 768px, THE Atelier Sidebar SHALL render as a slide-in drawer triggered by a hamburger menu button instead of a persistent sidebar
2. WHEN the viewport width is below 768px, THE Atelier session list SHALL render in a single-column card layout
3. WHEN the viewport width is below 768px, THE Reasoning_Timeline three-column expansion area SHALL stack vertically into a single column
4. WHEN the viewport width is below 768px, THE Mode_Strip SHALL render as a horizontally scrollable strip

### Requirement 12: Phase Isolation and Application Stability

**User Story:** As a developer, I want each phase to ship as a separate PR with the application remaining fully functional at every checkpoint, so that no phase introduces a broken state.

#### Acceptance Criteria

1. WHEN Phase 1 is complete, THE application SHALL render the existing Boutique and Atelier surfaces without visual regression, with the new design system available alongside the old one
2. WHEN Phase 2 is complete, THE Boutique SHALL render entirely with new primitives and tokens while the Atelier continues to render with the old design
3. WHEN Phase 3 is complete, THE Atelier shell SHALL render with the new sidebar, top bar, and session layout while the reasoning timeline uses placeholder content
4. WHEN Phase 4 is complete, THE Atelier reasoning timeline SHALL be fully wired to live SSE_Telemetry data
5. WHEN Phase 5 is complete, THE Boutique and Atelier SHALL be fully responsive at the 768px mobile breakpoint
6. EACH phase SHALL include a `PHASE_N_NOTES.md` file documenting design decisions and any deviations from the reference images

### Requirement 13: Dependency and Backend Constraints

**User Story:** As a developer, I want the rebuild to use only React, Tailwind, and Framer Motion without introducing new heavyweight dependencies, and to make zero changes to the backend, so that the project stays lean and the API contract is preserved.

#### Acceptance Criteria

1. THE frontend rebuild SHALL not add any new heavyweight UI framework dependencies beyond the existing React 18, Tailwind CSS 3, and Framer Motion 12
2. THE frontend rebuild SHALL not modify any backend API endpoints, request payloads, response shapes, or agent code
3. THE frontend rebuild SHALL not introduce client-side state management for data that the backend already manages (personas, sessions, chat history persistence beyond localStorage)
4. IF a lightweight utility package is needed (under 10KB gzipped), THEN THE developer SHALL document the justification in the phase notes before adding it

### Requirement 14: Accessibility Compliance

**User Story:** As a customer using assistive technology, I want the rebuilt surfaces to meet WCAG AA standards with visible focus states, keyboard navigation, and proper screen reader markup, so that the editorial luxury experience is inclusive.

#### Acceptance Criteria

1. THE rebuilt surfaces SHALL maintain WCAG AA color contrast ratios (4.5:1 for normal text, 3:1 for large text) across all text and interactive elements
2. THE rebuilt surfaces SHALL provide visible focus indicators on all interactive elements when navigated via keyboard
3. THE rebuilt surfaces SHALL use semantic HTML landmarks (`nav`, `main`, `aside`, `footer`, `header`) and ARIA attributes where native semantics are insufficient
4. THE Modal and Drawer Primitives SHALL implement focus trapping so keyboard navigation does not escape the overlay while it is open
5. WHEN animations are active, THE rebuilt surfaces SHALL respect the `prefers-reduced-motion` media query by disabling or reducing all motion

### Requirement 15: Cross-Browser Compatibility

**User Story:** As a customer, I want the rebuilt storefront to render correctly across modern browsers, so that the experience is consistent regardless of which browser I use.

#### Acceptance Criteria

1. THE rebuilt surfaces SHALL render correctly on Chrome, Safari, and Firefox (last 2 versions of each)
2. THE rebuilt surfaces SHALL render correctly on iOS Safari 16+ and Chrome Android 100+
3. WHEN `backdrop-filter` is used, THE rebuilt surfaces SHALL include the `-webkit-backdrop-filter` vendor prefix for Safari compatibility

### Requirement 16: Fluid Responsive Layout

**User Story:** As a customer using any device from a 14-inch laptop to a 16-inch MacBook Pro to an iPhone or Samsung phone, I want the layout to dynamically adapt to my screen size and resolution, so that the editorial luxury experience feels native to my device rather than scaled or cropped.

#### Acceptance Criteria

1. THE rebuilt surfaces SHALL use fluid layout techniques (CSS `clamp()`, viewport-relative units, percentage-based widths, CSS Grid `auto-fit`/`auto-fill`) so that content adapts continuously across viewport widths rather than snapping only at fixed breakpoints
2. THE Design_System SHALL define responsive breakpoint tokens: mobile (768px) and wide (1440px), with the desktop band implicit between them. An additional `expansionStack` token (1280px) SHALL define the Atelier expansion area's 3-column to 2+1 transition point. Content SHALL be fluid within each band, not fixed-width
3. THE Boutique product grid SHALL use CSS Grid with `auto-fill` and `minmax()` so that card columns adjust dynamically from 1 column on mobile to 2-3 columns on smaller laptops (1280px) to 3-4 columns on larger displays (1440px+)
4. THE Boutique hero stage, header, and footer SHALL use a fluid `max-width` container with horizontal padding that scales with viewport width (e.g., `clamp(16px, 4vw, 48px)`) so that content breathes on wide displays without feeling cramped on 14-inch screens
5. THE Atelier sidebar SHALL use a fixed width on desktop (240-260px) while the main content area fills the remaining viewport width fluidly, ensuring the session detail and reasoning timeline use available space on both 14-inch and 16-inch displays
6. THE Atelier three-column expansion area SHALL use CSS Grid that transitions from 3 equal columns on wide displays to a 2+1 stacked layout on narrower desktops (below the `expansionStack` breakpoint token at 1280px) to a single column on mobile (below 768px)
7. WHEN display pixel density varies (1x, 2x Retina, 3x), THE rebuilt surfaces SHALL render text and vector elements (SVGs, icons) crisply without scaling artifacts. Raster images SHALL provide appropriate resolution variants or use responsive `srcset` attributes
8. THE typography scale SHALL use fluid sizing via `clamp()` for display and headline text so that type scales proportionally between mobile and wide desktop without requiring per-breakpoint overrides (e.g., display text: `clamp(28px, 4vw, 48px)`)
9. THE rebuilt surfaces SHALL use `100dvh` (dynamic viewport height) instead of `100vh` for full-height layouts to account for mobile browser chrome (iOS Safari address bar, Android navigation bar)
10. THE Boutique and Atelier layouts SHALL render without horizontal scrollbars, content overflow, or layout shifts at any viewport width between 320px and 2560px
