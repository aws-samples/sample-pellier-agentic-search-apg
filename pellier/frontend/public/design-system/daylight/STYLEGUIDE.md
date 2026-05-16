# Daylight Design System

A warm, off-white, editorial design language. Originally drawn for Wayfare; reusable for Pellier and other internal projects.

## How to use

```html
<link rel="stylesheet" href="../design-system/daylight/tokens.css" />
<link rel="stylesheet" href="../design-system/daylight/daylight.css" />
```

Load `tokens.css` first — it defines the CSS variables that `daylight.css` consumes. Both files together are roughly 8 KB unminified. No build step, no JS dependency.

All component classes are prefixed `dl-` so they coexist with whatever else is on the page.

## Theming

Override tokens at any scope. To re-skin a page (or a single section) into a different accent without touching the component CSS:

```css
.pellier-section {
  --dl-accent:      #2f6f4f;
  --dl-accent-soft: #e3efe6;
  --dl-accent-ink:  #1a3a2a;
}
```

That's the recommended way to give Pellier its own subtle color identity while keeping every component, type ramp, and spacing rule consistent with Wayfare.

## Tokens

### Color

Surfaces — `--dl-bg`, `--dl-paper`, `--dl-paper-2`, `--dl-line`, `--dl-line-strong`. The page sits on `--dl-bg`; cards and panels use `--dl-paper`.

Ink — `--dl-ink`, `--dl-ink-2`, `--dl-muted`, `--dl-faint`. Use `--dl-ink` for headings, `--dl-ink-2` for body prose, `--dl-muted` for captions and eyebrows.

Accent — `--dl-accent` (terracotta), `--dl-accent-soft` (tint), `--dl-accent-ink` (dark accent for text-on-tint). Italic display type uses the accent.

Semantic — `--dl-ok`, `--dl-warn`, `--dl-err`, `--dl-info`.

### Type

Two faces: a serif for display and prose, a sans for UI metadata and code labels.

- `--dl-font-serif` — Instrument Serif → Fraunces (variable) → Georgia. Display, headings, body.
- `--dl-font-sans`  — Instrument Sans → system UI stack. Eyebrows, buttons, table headers, captions.
- `--dl-font-mono`  — JetBrains Mono → SF Mono → Menlo. Code, numerical readouts.

Scale (in px): `display 54 / h1 40 / h2 28 / h3 20 / lead 18 / body 15 / small 13 / eyebrow 11`.

Italic terracotta is the signature flourish — use it sparingly inside `.dl-display em`.

### Space and rhythm

Spacing tokens follow a 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 px ramp (`--dl-s-1` through `--dl-s-9`). Use the `.dl-stack`, `.dl-stack-lg`, `.dl-stack-xl` utilities for vertical rhythm.

### Radius

Six radius tokens: `--dl-r-sm` 6, `--dl-r-md` 10, `--dl-r-lg` 14, `--dl-r-xl` 20, `--dl-r-pill` 999. Cards use `lg`, panels and heroes use `xl`, buttons use `md`, pills and badges use `pill`.

### Shadow

Three: `--dl-sh-paper` (subtle paper depth on cards), `--dl-sh-lift` (hover state), `--dl-sh-deep` (modals, popovers).

## Components

`.dl-header` — page header with brand on the left, nav tabs on the right.

`.dl-nav-tabs > .dl-tab` — pill-style tab navigation. Add `.is-active` for the selected state.

`.dl-display`, `.dl-h1` ... `.dl-h3`, `.dl-lead`, `.dl-eyebrow`, `.dl-small`, `.dl-prose` — typography.

`.dl-btn` plus a variant: `.dl-btn-primary` (ink), `.dl-btn-accent` (terracotta), `.dl-btn-ghost`. Add `.dl-btn-block` for full-width and `.dl-btn-lg` for the larger size.

`.dl-input`, `.dl-textarea`, `.dl-select`, `.dl-label` — form controls.

`.dl-searchbar` — the editorial-style search input used on Wayfare. Houses an optional `.dl-chip` label, an `<input>`, and a primary button.

`.dl-card`, `.dl-card-lg`, `.dl-card-flush` — surfaces. Use `card-flush` for cards that wrap an image.

`.dl-panel` — large surface with a sans-serif uppercase title via `.dl-panel h3`.

`.dl-tag`, `.dl-pill` — inline tagging. Pills are interactive (filterable); tags are descriptive.

`.dl-badge` — small uppercase badge in accent.

`.dl-meta` — uppercase sans caption used above headings ("Liguria · Italy · 14 day window").

`.dl-table` — semantic table with monospace numeric columns via `.num`.

`.dl-code-block` — dark code block. Spans inside: `.kw` keywords, `.nm` names, `.st` strings, `.c` comments.

`.dl-score`, `.dl-bar` — score readouts and progress bars used on the debug screens.

`.dl-hero` with optional `.dl-stamp` — hero image area with overlay metadata.

`.dl-footer` — page footer.

## Layout primitives

`.dl-container` — centered wrapper, max 1200px, 48px gutter.

`.dl-grid`, `.dl-grid-2`, `.dl-grid-3`, `.dl-grid-4` — equal grids with the standard gap.

`.dl-grid-sidebar` — 240px sidebar + flex column. Collapses to a single column under 760px.

## Voice

Daylight is editorial, not technical. Section titles read like magazine spreads ("Where the next *chapter* begins"). Eyebrows are short and uppercase ("LIGURIA · ITALY"). Body copy is in serif and not afraid of full sentences.

When in doubt: less chrome, more prose; less color, more contrast in type weight; less iconography, more typographic hierarchy.

## File map

```
design-system/daylight/
├── tokens.css        — variables only
├── daylight.css      — components (depends on tokens.css)
├── components.html   — visual reference of every component
└── STYLEGUIDE.md     — this file
```
