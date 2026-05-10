# Phase 3 Notes — Atelier Shell Rebuild

## What shipped

- **New `AtelierPage.tsx`** — replaces `WorkshopPage.tsx` at the `/atelier` route
- **Dark espresso sidebar** (260px fixed) with Observatory, Sessions, Memory, Inventory, Agents, Tools, Evaluations, Settings nav items
- **Top bar** (64px cream-50, sticky) with breadcrumb, live session indicator, agents-online metric, persona dropdown
- **Session detail layout** with Mode Strip at top, Fraunces editorial title, metadata row, reasoning timeline placeholder, recommendation rail
- **Mode Strip** — Pattern I and II selectable pills, Pattern III non-selectable with explainer popover and visual separator
- **Session list view** — card-based list of past sessions with status pills
- **Placeholder views** for Memory, Inventory, Agents, Tools, Evaluations, Settings with editorial descriptions
- **Cold-start view** on Observatory with 6 suggestion chips

## Architecture decisions

**Layout grid**: CSS Grid `260px 1fr × 100dvh` for the two-column shell. The main canvas uses `flex-1 min-h-0 overflow-y-auto` so the top bar stays sticky while the main content scrolls independently. Works on any laptop size (14" through 16") and external displays.

**Sidebar primitive usage**: Uses `Sidebar` from `design/primitives` with `variant="dark"`. The header slot carries the "B" wordmark + Observatory · Live status; the footer slot carries the PersonaDropdown.

**Persona dropdown reuse**: Extracted `PersonaDropdown` sub-component within AtelierPage.tsx with `variant: 'dark' | 'light'` and `align: 'top' | 'bottom'` props. Used in both the sidebar footer (dark, aligns upward) and top bar (light, aligns downward). Same `switchPersona` / `signOut` flow as Header.tsx — fetches `/api/atelier/personas` on first open, closes on outside click or Escape.

**Mode Strip composition**: Pattern I and II use solid cream-50 fill when active (with `shadow-warm-sm`), border-sand when inactive (hover → border-espresso). Pattern III uses dashed border + opacity-60 + "Storefront · Production" small caps label. A vertical `ink-quiet/40` separator sits between Pattern II and Pattern III to reinforce the spatial grammar (interactive options vs reference representation). Clicking Pattern III opens a 320px popover with a "Open Storefront →" link — never mutates active pattern state.

**Pattern state**: Lives in `useState<PatternId>('agents_as_tools')` on AtelierPage. Phase 4 will thread this into `useAgentChat({ pattern: activePattern })`. The hook already accepts the pattern parameter.

**WorkshopPage preservation**: The old `WorkshopPage.tsx` is untouched and still accessible at `/atelier/architecture/:section` so architecture detail pages (MemoryArchPage, McpArchPage, etc.) continue to work. We'll retire WorkshopPage fully when those detail pages are migrated or deferred.

## Provider behavior

`useEffect` on mount calls `setChatSurface('concierge')` so ⌘K and the floating CommandPill open the centered ConciergeModal instead of the storefront ChatDrawer. This matches the existing chat surface routing in UIContext.

All existing hooks are preserved unchanged: `usePersona`, `useUI`, `useAgentChat` (not yet wired to mode strip — Phase 4).

## Styling discipline

Everything uses design tokens from `design/tokens.ts`:

- Colors: `bg-espresso-dark`, `bg-cream-50`, `text-ink-soft`, `border-sand`, `text-accent`
- Shadows: `shadow-warm-sm`, `shadow-warm-md`
- Transitions: `duration-fade`, `duration-slide`
- Fonts: `font-display` (Fraunces), `font-sans` (Inter), `font-mono` (JetBrains Mono)
- Fluid scaling: `clamp()` on display type, `px-container-x` for horizontal padding
- Max-width: `1440px` centered on session detail and session list

## No deviations from reference

The dark sidebar matches reference image 1 exactly: espresso-dark (#1F1410) background, cream text, "B Pellier" wordmark, Observatory · Live indicator, nav items in the specified order, persona avatar + chevron at the bottom. The mode strip sits above the editorial title as specified.

## Boutique unchanged

The `/` route (StorefrontPage) was not modified. `npx tsc --noEmit` and `npx vite build` both pass cleanly. The Boutique continues to render with Phase 2 components unchanged.

## Follow-ups for Phase 4

- Wire reasoning timeline to SSE telemetry events (six steps: understanding intent, retrieving memory, scanning inventory, ranking, agent collaboration, final recommendation)
- Replace the timeline placeholder card with the real ReasoningTimeline component
- Build three-column expansion area: "How we arrived at this", "What we know about you" (Memory Orbit SVG), "A team of specialists"
- Build Memory Orbit SVG with animated + static variants
- Footer strip with pull-quote "The Atelier doesn't just automate. It reasons, remembers and refines."
- Wire the Mode Strip's `activePattern` state into `useAgentChat` so pattern selection propagates to the backend
