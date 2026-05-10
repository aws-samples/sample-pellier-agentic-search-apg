# Phase 1 Notes - Design System + Primitives

## What shipped

- **Design token module** (`src/design/tokens.ts`): Single source of truth for colors, spacing, typography, shadows, radii, animation timing, breakpoints, and fluid layout values
- **Typography stylesheet** (`src/design/typography.css`): `@font-face` imports for Fraunces, Inter, and JetBrains Mono via `@fontsource-variable` packages, plus text utility classes
- **Tailwind config extensions**: New color tokens (`cream-50`, `sand`, `espresso`, `olive`, `espresso-dark`, `espresso-mid`), shadow tokens (`warm-sm`, `warm-md`, `warm-xl`), screen breakpoints (`wide`, `expansion-stack`), and fluid spacing (`container-x`)
- **11 component primitives** in `src/design/primitives/`: Button, Chip, Card, Input, Modal, Drawer, Avatar, Pill, IconButton, Sidebar, Timeline
- **Barrel export** (`src/design/primitives/index.ts`): Single entry point re-exporting all 11 primitives
- **Design system README** (`src/design/README.md`): Documents each primitive, its props, variants, and usage examples alongside token documentation
- **`/dev/design-system` preview route**: Development-only route rendering every primitive in all supported variants, sizes, and interactive states. Guarded with `import.meta.env.DEV` so production builds exclude it via Vite dead-code elimination

## Token naming decisions

- **`cream-50` chosen over `cream-new`**: Follows Tailwind's numeric shade convention (e.g., `gray-50`, `blue-100`). The `-50` suffix signals a lighter variant in the same family, which is immediately understood by anyone familiar with Tailwind's default palette
- **Existing `cream` (#fbf4e8) preserved**: The original cream token remains untouched for backward compatibility. Unrebuilt components continue to reference `cream` without changes. The new `cream-50` (#F7F3EE) is a distinct, slightly cooler tone used by the redesigned surfaces
- **`container-x` chosen over `fluid-px`**: Matches Tailwind's x-axis naming convention (e.g., `px-4` for horizontal padding). The `container-x` name communicates "container horizontal padding" at a glance
- **`expansionStack` (1280px) added as a named token**: The Atelier expansion area transitions from 3-column to 2+1 layout at this width. Rather than using a magic number scattered across components, it lives as a named breakpoint token in both `tokens.ts` and `tailwind.config.js` (`expansion-stack`)

## Coexistence strategy

New design system tokens live alongside old CSS custom properties and Tailwind tokens. The old tokens (`--cream`, `--ink`, `--accent`, `--cream-warm`, `--ink-soft`, `--ink-quiet`, `--dusk` in `index.css`; `cream`, `ink`, `accent`, `warm`, `warm-lg` etc. in `tailwind.config.js`) are not removed until all consumers are retired after Phase 5. This means:

- No existing component breaks during the rebuild
- Both old and new tokens are available simultaneously
- Phase 2-5 components import from `tokens.ts` and use the new Tailwind classes
- Old components continue using the original CSS custom properties and Tailwind classes unchanged

## Body text narrow range

The `bodySize` clamp (`clamp(14px, 1.1vw, 16px)`) has an intentionally narrow 2px range. Reading distance doesn't change meaningfully between laptop sizes (14" and 16" screens are viewed from roughly the same distance), so body text stays near-constant while display type does the scaling work. This avoids the common mistake of making body text too large on wide screens or too small on narrow ones - the 2px range is a deliberate editorial choice, not a limitation.

## Fluid responsive approach

Three layout bands with fluid content within each band:

- **Mobile** (< 768px): Single-column layouts, stacked content
- **Desktop** (768px - 1440px): Multi-column grids, fluid spacing
- **Wide** (> 1440px): Content stops growing at `maxWidth` and centers

Implementation techniques:

- CSS `clamp()` for typography scaling (display: 28px-48px, headline: 22px-36px, body: 14px-16px)
- `auto-fill` + `minmax()` for product grids (cards naturally reflow from 1 to 4 columns)
- `100dvh` for full-height layouts (accounts for mobile browser chrome)
- `clamp(16px, 4vw, 48px)` for container horizontal padding

## Wide-band centering

On displays wider than 1440px, content stops growing at `maxWidth` (1440px) and centers with `margin: 0 auto`. This is intentional editorial discipline - wide displays get more breathing room, not more content. The extra space on either side of the content area creates a gallery-like framing effect that reinforces the luxury aesthetic.

## No deviations from reference images

Phase 1 is foundation-only; no visual surfaces were rebuilt yet. The preview route at `/dev/design-system` is the visual QA surface for this phase. All primitives render with the correct tokens, and the existing storefront and Atelier surfaces are visually unchanged.

## Dependencies

No new runtime dependencies added. The existing `@fontsource-variable` packages (Fraunces, Inter, JetBrains Mono) and Framer Motion are already in the project. `fast-check` (dev-only, under 10KB gzipped) will be added for property-based tests in Task 1.9.

## Follow-ups for Phase 2

- Rebuild Boutique pages (Header, HeroStage, ProductGrid, Footer) using new primitives and tokens
- Restyle ChatDrawer and CommandPill visual layers (tokens, fonts, shadows only - no behavioral changes)
- Apply `cream-50` background, editorial whitespace, and fluid container to StorefrontPage
- Persona switcher relocation from modal to Avatar dropdown in header
