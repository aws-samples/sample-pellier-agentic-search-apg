# Daylight design system — integration

Pellier consumes the Daylight design system (originally built for the
DAT409 Wayfare workshop) as the source of truth for color, type,
spacing, radius, shadow, and component CSS. Every Boutique and
Atelier surface inherits from these tokens.

## Layout

```
pellier/frontend/
├── public/design-system/daylight/   ← VENDORED from dat409
│   ├── tokens.css                     (78 lines — all CSS variables)
│   ├── daylight.css                   (259 lines — all .dl-* components)
│   ├── components.html                (gallery, dev reference)
│   └── STYLEGUIDE.md                  (token usage rules)
└── src/
    ├── index.css                    @imports Daylight + bridge before Tailwind
    ├── styles/
    │   └── daylight-bridge.css      Aliases Pellier names → --dl-* tokens
    └── atelier/styles/
        └── tokens.css               --at-* semantic aliases (cards, pills, sidebar)
```

## Cascade order (load priority)

```
1. public/design-system/daylight/tokens.css     ← --dl-* values
2. public/design-system/daylight/daylight.css   ← .dl-* component styles
3. src/styles/daylight-bridge.css               ← --cream / --ink / --accent / --at-* → --dl-*
4. tailwind base / components / utilities        (inside @layer base)
5. src/atelier/styles/tokens.css                 ← --at-* semantic aliases
6. component-level CSS / inline styles
```

`tailwind.config.js` references CSS variables (`'cream': 'var(--cream)'`,
etc.) so every `bg-cream` / `text-ink` / `border-accent` utility
flows through the bridge to the Daylight value at runtime.

## Token contract

**Daylight tokens (`--dl-*`)** — the source of truth. Defined once in
`public/design-system/daylight/tokens.css`. Don't override here; if you
need a different value for a surface, override at scope.

**Pellier aliases (`--cream`, `--ink`, `--accent`, ...)** — declared in
`src/styles/daylight-bridge.css`. Existing component code references
these names; the bridge renames Daylight tokens onto them so no
component file needs editing.

| Pellier name | Daylight target | Role |
| --- | --- | --- |
| `--cream` | `--dl-bg` | Page background (off-white) |
| `--cream-warm` | `--dl-paper` | Cards, panels |
| `--cream-2` | `--dl-paper-2` | Recessed surfaces |
| `--ink` | `--dl-ink` | Primary text |
| `--ink-soft` | `--dl-ink-2` | Body prose |
| `--ink-quiet` | `--dl-muted` | Captions, eyebrows |
| `--accent` | `--dl-accent` | Terracotta accent |
| `--rule-1` | `--dl-line` | Hairline borders |
| `--at-cream-1` | `--dl-bg` | Atelier background |
| `--at-ink-1` | `--dl-ink` | Atelier primary text |
| `--at-red-1` | `--dl-accent` | Atelier accent |
| `--at-green-1` | `--dl-ok` | Atelier "shipped" status |
| `--serif` / `--at-serif` | `--dl-font-serif` | Instrument Serif → Fraunces → Georgia |
| `--sans` / `--at-sans` | `--dl-font-sans` | Instrument Sans → system UI |
| `--mono` / `--at-mono` | `--dl-font-mono` | JetBrains Mono |

Full list in `src/styles/daylight-bridge.css`.

**Atelier semantic aliases (`--at-card-bg`, `--at-status-shipped-bg`,
`--at-sidebar-bg`, ...)** — declared in `src/atelier/styles/tokens.css`.
These reference `--at-*` aliases and the bridge resolves the chain
back to `--dl-*`.

## How to override a single surface

```css
.pellier-special-section {
  --accent:      #2f6f4f;            /* override at scope */
  --accent-soft: #e3efe6;
}
```

Every component inside `.pellier-special-section` now renders with
that accent. The rest of the app stays terracotta.

## How to use Daylight components directly

Mount Daylight component classes on JSX elements:

```tsx
<div className="dl-card">
  <p className="dl-eyebrow">Trace</p>
  <h3 className="dl-h2">Marco's Turn 4</h3>
  <pre className="dl-code-block">
    <code>SELECT ...</code>
  </pre>
  <div className="dl-score">
    <span className="big">0.92</span>
    <small>Palette match</small>
  </div>
</div>
```

Available classes are listed in `STYLEGUIDE.md` and rendered live in
`components.html`. Both files ship in `public/design-system/daylight/`
so participants can browse them in Code Editor too.

## Re-importing from dat409

When dat409 evolves Daylight and you want to pick up upstream changes:

```bash
DAT=path/to/sample-dat409-hybrid-search-aurora-mcp
PEL=pellier/frontend/public/design-system/daylight
cp $DAT/design-system/daylight/{tokens.css,daylight.css,STYLEGUIDE.md,components.html} $PEL/
```

The bridge file at `src/styles/daylight-bridge.css` only renames
tokens — it never copies values. So upstream Daylight changes propagate
automatically. If a token is *renamed* in upstream Daylight, update
the bridge to point at the new name; that's the only file you'll
need to touch.

## What was removed when Daylight landed

- The hardcoded `:root` block in `index.css` (60+ lines of color hex
  values — replaced by the bridge)
- The hardcoded `--at-*` color values in `atelier/styles/tokens.css`
  (the file now holds only Atelier-specific semantic aliases)
- Hardcoded hex values in `tailwind.config.js` (`'cream': '#fbf4e8'`,
  etc. — repointed at `var(--cream)`)

## Persona avatar shades

`--persona-marco` / `--persona-anna` are intentionally *not* in
Daylight — they're scoped to persona surfaces and stay declared
inline in `index.css`. Add new persona shades there if needed.
