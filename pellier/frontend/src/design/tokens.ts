/**
 * Design System Tokens — Single Source of Truth
 *
 * Every component in the Pellier redesign draws from this module.
 * Colors, typography, spacing, shadows, radii, animation timing,
 * breakpoints, and fluid layout values are all defined here.
 *
 * Do not hardcode visual values in components — import from this file.
 */

// ---------------------------------------------------------------------------
// Color tokens
// ---------------------------------------------------------------------------

/** Hex literals mirror `public/design-system/daylight/tokens.css` / bridge. */
export const colors = {
  cream: "#f7f3ec",
  sand: "#f1ece1",
  espresso: "#1f1410",
  olive: "#6B705C",
  terracotta: "#9a3412",
  ink: "#1f1410",
  inkSoft: "#3a3833",
  inkQuiet: "#6b665d",
  dusk: "#1f1410",
  creamWarm: "#fbf8f2",
  espressoDark: "#1f1410",
  espressoMid: "#2a2724",
} as const;

// ---------------------------------------------------------------------------
// Spacing scale (4px base)
// ---------------------------------------------------------------------------

export const spacing = {
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "32px",
  "2xl": "48px",
  "3xl": "64px",
} as const;

// ---------------------------------------------------------------------------
// Typography tokens
// ---------------------------------------------------------------------------

export const typography = {
  display: { family: "'Fraunces', Georgia, serif", weight: 400 },
  body: {
    family: "'Instrument Sans', system-ui, -apple-system, sans-serif",
    weight: 400,
  },
  mono: { family: "'JetBrains Mono', ui-monospace, monospace", weight: 400 },
} as const;

// ---------------------------------------------------------------------------
// Shadow tokens (warm-tinted)
// ---------------------------------------------------------------------------

export const shadows = {
  sm: "0 2px 8px rgba(107, 74, 53, 0.06), 0 1px 3px rgba(107, 74, 53, 0.04)",
  md: "0 4px 16px rgba(107, 74, 53, 0.08), 0 2px 6px rgba(107, 74, 53, 0.05)",
  lg: "0 8px 24px rgba(107, 74, 53, 0.10), 0 4px 8px rgba(107, 74, 53, 0.06)",
  xl: "0 24px 48px rgba(107, 74, 53, 0.14), 0 8px 16px rgba(107, 74, 53, 0.08)",
} as const;

// ---------------------------------------------------------------------------
// Border radii
// ---------------------------------------------------------------------------

export const radii = {
  sm: "8px",
  md: "12px",
  lg: "16px",
  xl: "24px",
  full: "9999px",
} as const;

// ---------------------------------------------------------------------------
// Animation timing
// ---------------------------------------------------------------------------

export const animation = {
  slide: { duration: "240ms", easing: "ease-out" },
  fade: { duration: "180ms", easing: "ease-out" },
  spring: { stiffness: 320, damping: 28 },
} as const;

// ---------------------------------------------------------------------------
// Responsive breakpoints
//
// Two breakpoints define three bands:
// mobile (< 768px), desktop (768px-1440px implicit), wide (> 1440px)
// ---------------------------------------------------------------------------

export const breakpoints = {
  mobile: "768px",
  /** Atelier expansion area stacks from 3-col to 2+1 below this width */
  expansionStack: "1280px",
  wide: "1440px",
} as const;

// ---------------------------------------------------------------------------
// Fluid layout tokens — used via CSS clamp() for continuous scaling
// ---------------------------------------------------------------------------

export const fluid = {
  /** Container horizontal padding: 16px on mobile → 48px on wide */
  containerPadding: "clamp(16px, 4vw, 48px)",
  /** Display text: 28px on mobile → 48px on wide */
  displaySize: "clamp(28px, 4vw, 48px)",
  /** Section headline: 22px on mobile → 36px on wide */
  headlineSize: "clamp(22px, 3vw, 36px)",
  /**
   * Body text: narrow 2px range is intentional — reading distance
   * doesn't change meaningfully between 14" and 16" laptops, so
   * body text stays near-constant while display type does the
   * scaling work.
   */
  bodySize: "clamp(14px, 1.1vw, 16px)",
  /** Product grid min card width for auto-fill */
  gridCardMin: "280px",
  /** Max content width */
  maxWidth: "1440px",
} as const;

// ---------------------------------------------------------------------------
// TypeScript types
// ---------------------------------------------------------------------------

export type ColorToken = keyof typeof colors;
export type SpacingToken = keyof typeof spacing;
export type ShadowToken = keyof typeof shadows;
export type RadiusToken = keyof typeof radii;

export interface AnimationTiming {
  duration: string;
  easing: string;
}
