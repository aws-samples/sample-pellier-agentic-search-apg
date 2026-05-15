/**
 * CSS custom properties for inline `style={{ ... }}` in React.
 * Every name resolves through `src/styles/daylight-bridge.css` at :root
 * (and `--dl-*` in `daylight-tokens.css`). Prefer these over hex literals
 * so Boutique + Atelier stay locked to the vendored Daylight palette.
 */
export const cssVar = {
  bg: 'var(--cream)',
  paper: 'var(--cream-warm)',
  paper2: 'var(--cream-2)',
  ink: 'var(--ink)',
  ink2: 'var(--ink-soft)',
  muted: 'var(--ink-quiet)',
  faint: 'var(--ink-5)',
  accent: 'var(--accent)',
  dusk: 'var(--dusk)',
  line: 'var(--rule-1)',
  /** Primary-ink filled control (selected chips, dark buttons) */
  surfaceInk: 'var(--dl-ink)',
  /** High-contrast text on `surfaceInk` */
  onInkSurface: 'var(--cream-warm)',
} as const
