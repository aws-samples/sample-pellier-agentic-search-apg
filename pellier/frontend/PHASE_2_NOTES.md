# Phase 2 Notes — Boutique Rebuild

## What shipped

- **Header rebuild**: Persona avatar dropdown replacing PersonaPill + PersonaModal. Centered "Pellier" wordmark with circular B logo. Five nav items with sticky `backdrop-filter: blur(12px)` and `-webkit-backdrop-filter` prefix for Safari.
- **HeroStage restyle**: New design tokens applied. Existing 8-intent rotation cycle, 7.5s cadence, hover-pause behavior, and ticker chip click-to-jump behavior preserved unchanged.
- **ProductGrid rebuild**: CSS Grid `auto-fill` with `minmax(280px, 1fr)` for dynamic column count (1 col mobile, 2-3 cols on 14" laptops, 3-4 cols on 16" displays). Card primitive with warm-tinted shadows. Scroll-reveal fade-in via IntersectionObserver respecting `prefers-reduced-motion`.
- **Footer restyle**: Brand column, explore links, editorial columns, bottom copyright strip rebuilt with new primitives and tokens.
- **ChatDrawer visual refresh**: New tokens, fonts, and shadows applied. Zero behavioral changes.
- **CommandPill visual refresh**: Replaced hardcoded constants with Tailwind token classes. Zero behavioral changes.
- **StorefrontPage fluid container**: `min-h-dvh bg-cream-50` background. Fluid `max-width: 1440px` container with `container-x` padding token.

## Persona switcher relocation

PersonaPill + PersonaModal replaced with an inline Avatar dropdown in the Header. The dropdown:

- Displays persona monogram (Avatar primitive) when a persona is active, generic user icon when signed out
- Calls `switchPersona` hook directly on selection (same session regeneration and chat history clearing)
- Fetches persona list from `/api/atelier/personas` on first open
- Closes on outside click or Escape key

## Nav item changes

Left nav updated from Home/Shop/Storyboard/Discover to Shop/Stories/Ask Pellier/About per reference image 3. The `NavItem` type was expanded to include the new items (`stories`, `ask-pellier`, `about`) alongside the old ones (`home`, `shop`, `storyboard`, `discover`, `account`) for backward compatibility. WorkshopPage continues to use `current="home"` without issue.

## ChatDrawer visual diff

Visual-only changes — tokens, fonts, shadows updated. Zero behavioral changes:

- Same `useAgentChat` hook
- Same SSE streaming
- Same three entry points (CommandPill click, keyboard shortcut, suggestion pill click)
- Same mobile bottom-sheet variant (drag handle, 80dvh height) explicitly preserved per Requirement 10.4
- Same offline fallback message

## CommandPill visual diff

Visual-only changes — replaced hardcoded constants with Tailwind token classes:

- Same fixed bottom-right positioning
- Same keyboard shortcut display (`⌘K` / `Ctrl+K`)
- Same surface-aware toggle behavior (drawer on storefront, concierge on atelier)

## Fluid responsive

- **ProductGrid**: CSS Grid `auto-fill` + `minmax(280px, 1fr)` for dynamic column count
- **StorefrontPage**: `min-h-dvh bg-cream-50` for full-height layout with dynamic viewport height
- **HeroStage**: `px-container-x` for fluid padding via `clamp(16px, 4vw, 48px)`
- **Header/Footer**: Fluid `max-width: 1440px` container with `margin: 0 auto` centering on wide displays
- **Typography**: Fluid `clamp()` sizing for display and headline text

## Atelier unchanged

The `/atelier` route (WorkshopPage) was not modified. It continues to render with old components and old design tokens. Verified by:

1. `npx tsc --noEmit` — zero TypeScript errors
2. `npx vite build` — production build succeeds
3. WorkshopPage imports Header and Footer (both rebuilt in Phase 2) with full backward compatibility. The Header's `current` prop interface is unchanged; WorkshopPage's `<Header current="home" />` call works as before.

## No deviations from reference images

All Boutique components match the editorial luxury direction from reference image 3. The warm cream/espresso/terracotta palette, Fraunces display type, Inter body text, and warm-tinted shadows are applied consistently across all rebuilt surfaces.

## Follow-ups for Phase 3

- Rebuild Atelier shell with dark espresso sidebar, top bar with breadcrumb and live session indicator, session detail layout, and Mode Strip
- Wire Mode Strip to `useAgentChat` hook's pattern parameter
- Build session list view and placeholder views for sidebar sections
