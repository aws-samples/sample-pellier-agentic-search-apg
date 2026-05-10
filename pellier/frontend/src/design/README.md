# Pellier Design System

The visual foundation for the Pellier frontend redesign. Every component in the rebuilt storefront (Boutique) and observatory (Atelier) surfaces draws from this module. Colors, typography, spacing, shadows, radii, animation timing, breakpoints, and fluid layout values are defined once in `tokens.ts` and consumed by the 11 reusable primitives in `primitives/`.

---

## Color Palette

All color tokens are exported from `tokens.ts` and extended into the Tailwind config.

| Token          | Hex       | Usage                                         |
| -------------- | --------- | --------------------------------------------- |
| `cream`        | `#F7F3EE` | Primary background (Boutique), light surfaces |
| `sand`         | `#E8DFD4` | Secondary background, muted fills             |
| `espresso`     | `#3B2F2F` | Dark text, primary actions                    |
| `olive`        | `#6B705C` | Accent green, tags, secondary indicators      |
| `terracotta`   | `#C44536` | Accent red, CTAs, active states, links        |
| `ink`          | `#2D1810` | Primary text, dark actions (preserved)        |
| `inkSoft`      | `#6B4A35` | Secondary text (preserved)                    |
| `inkQuiet`     | `#A68668` | Tertiary text, metadata (preserved)           |
| `dusk`         | `#3D2518` | Dark surfaces, hover states (preserved)       |
| `creamWarm`    | `#F5E8D3` | Secondary background, hover fills (preserved) |
| `espressoDark` | `#1F1410` | Atelier sidebar background                    |
| `espressoMid`  | `#2A1E18` | Atelier dark surface mid-tone                 |

> **Naming note:** The Tailwind class is `cream-50` (not `cream-new`). This avoids collision with the existing `cream` token (`#fbf4e8`) which remains for backward compatibility until all phases are complete.

---

## Typography

Three font families cover all surfaces. Fluid sizing via `clamp()` keeps text proportional across viewport widths without per-breakpoint overrides.

### Font Families

| Role                | Family                    | Fallback Stack          | Weight |
| ------------------- | ------------------------- | ----------------------- | ------ |
| Display / Headlines | Fraunces (variable)       | Georgia, serif          | 400    |
| Body / UI           | Inter (variable)          | system-ui, sans-serif   | 400    |
| Mono / Code         | JetBrains Mono (variable) | ui-monospace, monospace | 400    |

### Text Utility Classes (`typography.css`)

| Class             | Family         | Size                             | Notes                         |
| ----------------- | -------------- | -------------------------------- | ----------------------------- |
| `.text-display`   | Fraunces       | `clamp(28px, 4vw, 48px)`         | Hero headlines, product names |
| `.text-headline`  | Fraunces       | `clamp(22px, 3vw, 36px)`         | Section headlines             |
| `.text-body`      | Inter          | `clamp(14px, 1.1vw, 16px)`       | Default body text             |
| `.text-body-sm`   | Inter          | 13px                             | Small body text, captions     |
| `.text-mono`      | JetBrains Mono | 12px                             | Code, tech footnotes          |
| `.text-eyebrow`   | Inter          | 10px, uppercase, 0.16em tracking | Category labels               |
| `.text-microcopy` | Inter          | 11px                             | Fine print, disclaimers       |

---

## Spacing Scale

4px base unit. All values exported from `tokens.ts`.

| Token | Value | Typical Use                |
| ----- | ----- | -------------------------- |
| `xs`  | 4px   | Tight gaps, icon padding   |
| `sm`  | 8px   | Chip padding, small gaps   |
| `md`  | 16px  | Card padding, section gaps |
| `lg`  | 24px  | Section spacing            |
| `xl`  | 32px  | Large section spacing      |
| `2xl` | 48px  | Page section dividers      |
| `3xl` | 64px  | Hero section padding       |

---

## Shadow Tokens

Warm-tinted shadows using `rgba(107, 74, 53, ...)` (ink-soft base) for the editorial luxury feel. No cold grey drops.

| Token | Value                                                               | Usage                  |
| ----- | ------------------------------------------------------------------- | ---------------------- |
| `sm`  | `0 2px 8px rgba(107,74,53,0.06), 0 1px 3px rgba(107,74,53,0.04)`    | Subtle card elevation  |
| `md`  | `0 4px 16px rgba(107,74,53,0.08), 0 2px 6px rgba(107,74,53,0.05)`   | Default card shadow    |
| `lg`  | `0 8px 24px rgba(107,74,53,0.10), 0 4px 8px rgba(107,74,53,0.06)`   | Elevated cards, modals |
| `xl`  | `0 24px 48px rgba(107,74,53,0.14), 0 8px 16px rgba(107,74,53,0.08)` | Hero elements, drawers |

---

## Border Radii

| Token  | Value  | Usage                        |
| ------ | ------ | ---------------------------- |
| `sm`   | 8px    | Chips, pills, small elements |
| `md`   | 12px   | Cards, inputs                |
| `lg`   | 16px   | Modals, large cards          |
| `xl`   | 24px   | Hero elements                |
| `full` | 9999px | Avatars, circular buttons    |

---

## Animation Timing

| Token    | Duration                    | Easing   | Usage                             |
| -------- | --------------------------- | -------- | --------------------------------- |
| `slide`  | 240ms                       | ease-out | Drawer open/close, panel slides   |
| `fade`   | 180ms                       | ease-out | Opacity transitions, hover states |
| `spring` | stiffness: 320, damping: 28 | —        | Framer Motion spring animations   |

All animated primitives respect `prefers-reduced-motion` by disabling or reducing to opacity-only transitions.

---

## Responsive Breakpoints

Two breakpoints define three layout bands. Content is fluid within each band.

| Token            | Value  | Band Below                                                   | Band Above                                                          |
| ---------------- | ------ | ------------------------------------------------------------ | ------------------------------------------------------------------- |
| `mobile`         | 768px  | Mobile (< 768px): single column, bottom nav, stacked layouts | Desktop (768px+): multi-column, persistent sidebar                  |
| `wide`           | 1440px | Desktop (768px - 1440px): 2-3 grid columns, fluid scaling    | Wide (> 1440px): content centers at max-width, extra breathing room |
| `expansionStack` | 1280px | Atelier expansion area stacks from 3-col to 2+1 layout       | Full 3-column expansion area                                        |

### Three-Band Layout

- **Mobile** (< 768px): Single-column layouts, bottom navigation, stacked hero, drawer sidebar
- **Desktop** (768px - 1440px): Multi-column grids, persistent sidebar, fluid typography scaling between mobile and wide sizes
- **Wide** (> 1440px): Content stops growing at `maxWidth` (1440px) and centers with `margin: 0 auto`. Wide displays get more breathing room, not more content

---

## Fluid Layout Tokens

Continuous scaling values used via CSS `clamp()` so layouts adapt smoothly across viewport widths rather than snapping at breakpoints.

| Token              | Value                      | Purpose                                           |
| ------------------ | -------------------------- | ------------------------------------------------- |
| `containerPadding` | `clamp(16px, 4vw, 48px)`   | Horizontal padding that breathes on wide displays |
| `displaySize`      | `clamp(28px, 4vw, 48px)`   | Display text scales from mobile to wide           |
| `headlineSize`     | `clamp(22px, 3vw, 36px)`   | Section headlines scale proportionally            |
| `bodySize`         | `clamp(14px, 1.1vw, 16px)` | Body text with intentionally narrow range         |
| `gridCardMin`      | 280px                      | Minimum card width for CSS Grid `auto-fill`       |
| `maxWidth`         | 1440px                     | Content max-width, centers on ultra-wide          |

> **Body text narrow range:** The 2px range (`14px` to `16px`) is intentional. Reading distance doesn't change meaningfully between 14-inch and 16-inch laptops, so body text stays near-constant while display type does the scaling work.

---

## Primitives

All 11 primitives live in `src/design/primitives/` and are re-exported from `primitives/index.ts`.

### Button

Versatile action button with three visual variants and three sizes.

- **Variants:** `primary` (filled), `secondary` (outlined), `ghost` (text-only)
- **Sizes:** `sm`, `md`, `lg`
- **Key props:** `variant`, `size`, `disabled`, `onClick`, `children`
- Includes visible focus indicator for keyboard navigation

### Chip

Suggestion and tag chip with toggle state.

- **States:** `active` (filled), `inactive` (outlined)
- **Key props:** `active`, `onClick`, `children`

### Card

Borderless container with warm-tinted soft shadows.

- **Variants:** `default`, `product`, `recommendation`, `reasoning`
- **Key props:** `variant`, `className`, `children`

### Input

Text input with search bar variant.

- **Variants:** `search` (with mic icon and command-K hint), `text` (standard)
- **Key props:** `variant`, `placeholder`, `value`, `onChange`
- Includes visible focus indicator

### Modal

Overlay dialog rendered via `createPortal` to `document.body`.

- Traps keyboard focus (Tab/Shift+Tab cycle within modal)
- Closes on Escape key press
- **Key props:** `open`, `onClose`, `ariaLabel`, `children`

### Drawer

Slide-in panel with Framer Motion animation.

- Animates at 240ms ease-out matching the slide timing token
- Rendered via `createPortal` to `document.body`
- Focus trap while open
- **Sides:** `left`, `right`
- **Key props:** `open`, `onClose`, `side`, `ariaLabel`, `children`
- Respects `prefers-reduced-motion`

### Avatar

Circular monogram display.

- **Sizes:** `sm`, `md`, `lg`
- **Key props:** `initial` (single character), `bgColor`, `size`

### Pill

Status indicator badge.

- **Variants:** `live` (pulsing dot), `confidence`, `default`
- **Key props:** `variant`, `children`

### IconButton

Circular ghost button for icon-only actions (header, toolbars).

- **Sizes:** `sm`, `md`
- **Key props:** `icon`, `size`, `ariaLabel`, `onClick`
- Includes visible focus indicator

### Sidebar

Navigation sidebar with dark and light variants.

- **Dark variant:** Espresso `#1F1410` background, cream text (Atelier)
- **Light variant:** Cream background, ink text (Boutique)
- **Key props:** `variant`, `items` (array of `SidebarItem`), `activeItem`, `onItemClick`
- `SidebarItem`: `{ id, label, icon?, badge? }`

### Timeline

Vertical numbered step sequence with connecting lines.

- **Step statuses:** `pending` (muted), `in-progress` (pulsing), `complete` (filled), `skipped` (dimmed with skip indicator)
- **Key props:** `steps` (array of `TimelineStep`)
- `TimelineStep`: `{ number, label, status, content? }`
- Respects `prefers-reduced-motion` for pulsing animation

---

## Notes

- The `expansionStack` token (1280px) defines where the Atelier three-column expansion area transitions from 3 equal columns to a 2+1 stacked layout. This is separate from the `mobile` breakpoint.
- `cream-50` (`#F7F3EE`) was chosen over `cream-new` to follow Tailwind's numeric shade convention and avoid confusion with the existing `cream` token (`#fbf4e8`).
- The body text narrow `clamp()` range (14px to 16px) is intentional — reading distance doesn't change meaningfully between laptop sizes, so body text stays near-constant while display type does the scaling work.
