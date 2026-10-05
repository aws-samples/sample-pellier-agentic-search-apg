# Pellier design tokens and primitives

Every color, shadow and scrim is a CSS custom property in
`src/styles/daylight-tokens.css`, written once for the light theme at `:root`
and once for the dark theme under `[data-theme="dark"]`. Components read them
as `var(--dl-*)`, through the role names in `tailwind.config.js` (`page`,
`paper`, `ink`, `copper`, ...), or through `cssVars.ts` for inline styles.
`src/__tests__/token_guard.test.ts` fails on a hard-coded color anywhere else
in `src/`, and `token_contrast.test.ts` checks the pairs in both themes.

This directory holds `cssVars.ts` and the two primitives that are mounted.

---

## Primitives

Two primitives live in `src/design/primitives/` and are re-exported from
`primitives/index.ts`. Both are mounted by `components/Header.tsx`.

Nine others once sat beside them — Button, Card, Chip, Input, Modal, Drawer,
Pill, Sidebar, Timeline — fully written, fully exported, and imported by
nothing. They have been removed. If you need a control the two below do not
cover, take the pattern from the surface stylesheet that already draws it
rather than reviving a parallel one here.

### Avatar

Circular monogram display.

- **Sizes:** `sm`, `md`, `lg`
- **Key props:** `initial` (single character), `bgColor`, `size`

### IconButton

Circular ghost button for icon-only actions (header, toolbars).

- **Sizes:** `sm` (32px), `md` (44px, the touch floor)
- **Key props:** `icon`, `size`, `ariaLabel`, `onClick`
- Includes a visible focus indicator, and does not shrink as a flex item
