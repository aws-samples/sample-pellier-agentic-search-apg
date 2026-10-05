# Daylight design system integration

Pellier consumes the Daylight design system (originally built for the
DAT409 Wayfare workshop) as the source of truth for color, type,
spacing, radius, shadow, and component CSS. The Storefront and the
Operator inherit from these tokens.

## Layout

```
pellier/frontend/
├── public/design-system/daylight/   ← VENDORED from dat409
│   ├── tokens.css                     (78 lines, all CSS variables)
│   ├── daylight.css                   (259 lines, all .dl-* components)
│   ├── components.html                (gallery, dev reference)
│   └── STYLEGUIDE.md                  (token usage rules)
└── src/
    ├── index.css                    @imports Daylight + bridge before Tailwind
    └── styles/
        └── daylight-bridge.css      Aliases Pellier names → --dl-* tokens
```

## Cascade order (load priority)

```
1. public/design-system/daylight/tokens.css     ← --dl-* values
2. public/design-system/daylight/daylight.css   ← .dl-* component styles
3. src/styles/daylight-bridge.css               ← --cream / --ink / --accent / --obs-* → --dl-*
4. tailwind base / components / utilities        (inside @layer base)
5. component-level CSS / inline styles
```

`tailwind.config.js` references CSS variables (`'cream': 'var(--cream)'`,
etc.) so every `bg-cream` / `text-ink` / `border-accent` utility
flows through the bridge to the Daylight value at runtime.

## Token contract

**Daylight tokens (`--dl-*`)** are the source of truth. Defined once in
`public/design-system/daylight/tokens.css`. Don't override here; if you
need a different value for a surface, override at scope.

**Pellier aliases (`--cream`, `--ink`, `--accent`, ...)** are declared in
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
| `--obs-cream-1` | `--dl-bg` | Second alias family, still read by `src/shared/` and `components/ui/` |
| `--obs-ink-1` | `--dl-ink` | Primary text, same family |
| `--obs-red-1` | `--pellier-accent` | Accent, same family |
| `--obs-green-1` | `--dl-ok` | "Shipped" status, same family |
| `--serif` / `--obs-serif` | `--dl-font-serif` | Instrument Serif → Fraunces → Georgia |
| `--sans` / `--obs-sans` | `--dl-font-sans` | Instrument Sans → system UI |
| `--mono` / `--obs-mono` | `--dl-font-mono` | JetBrains Mono |

Full list in `src/styles/daylight-bridge.css`.

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
tokens; it never copies values. So upstream Daylight changes propagate
automatically. If a token is *renamed* in upstream Daylight, update
the bridge to point at the new name; that's the only file you'll
need to touch.

## What was removed when Daylight landed

- The hardcoded `:root` block in `index.css` (60+ lines of color hex
  values, replaced by the bridge)
- Hardcoded hex values in `tailwind.config.js` (`'cream': '#fbf4e8'`,
  etc., repointed at `var(--cream)`)

## Persona avatar shades

`--persona-marco` / `--persona-anna` are intentionally *not* in
Daylight: they're scoped to persona surfaces and stay declared
inline in `index.css`. Add new persona shades there if needed.
