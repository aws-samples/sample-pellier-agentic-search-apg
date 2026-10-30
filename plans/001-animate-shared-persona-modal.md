# 001 - Animate the shared persona modal

- **Status**: DONE
- **Commit**: `633df9e`
- **Severity**: MEDIUM
- **Category**: Purpose and frequency, physicality and origin, accessibility
- **Estimated scope**: 2 files, approximately 80 lines changed or added

## Problem

`PersonaModal` is an occasional, shared overlay opened from the storefront and
Labs. It currently returns `null` as soon as `open` becomes false, so the card
and backdrop appear and disappear without communicating the relationship to the
trigger or the completed close action. It also has no
`prefers-reduced-motion` alternative.

```tsx
// pellier/frontend/src/components/PersonaModal.tsx:65-75 - current
if (!open) return null

return createPortal(
  <div
    className="pm-backdrop"
    data-testid="persona-modal-backdrop"
    onClick={(e) => {
      if (e.target === e.currentTarget) onClose()
    }}
  >
    <div className="pm-card" data-testid="persona-modal">
```

The two CSS surfaces only establish static layout and visual styling:

```css
/* pellier/frontend/src/styles/persona-modal.css:9-30 - current */
.pm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(31, 20, 16, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.pm-card {
  width: 100%;
  max-width: 540px;
  background: var(--cream-1);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 30px 80px -20px rgba(31, 20, 16, 0.40), 0 0 0 1px var(--rule-1);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
}
```

## Target

Keep the modal structural and data behavior unchanged, but place its portal
content inside `AnimatePresence` so it can enter and exit cleanly:

- Fade the backdrop from opacity `0` to `1` over `180ms`, and fade it out over
  `180ms`.
- Enter the centered card from `opacity: 0; transform:
  translateY(6px) scale(0.97)` to `opacity: 1; transform:
  translateY(0) scale(1)` over `240ms`.
- Exit the card to the same `opacity: 0; transform:
  translateY(6px) scale(0.97)` state over `180ms`.
- Use `cubic-bezier(0.23, 1, 0.32, 1)` for every phase. This is the existing
  modal ease-out convention, and is appropriate for a centered overlay.
- Use `transform-origin: center` on the card. A centered modal is exempt from
  trigger-origin scaling.
- With `prefers-reduced-motion: reduce`, retain the same opacity feedback but
  omit all `transform` values. Do not use a zero-duration transition.
- Give the card `role="dialog"`, `aria-modal="true"`, and
  `aria-labelledby="persona-modal-title"`. Add that id to the existing `h2`.

```tsx
// target motion values
const PERSONA_MODAL_EASE: [number, number, number, number] = [
  0.23, 1, 0.32, 1,
]

const reduceMotion = Boolean(useReducedMotion())
const cardInitial = reduceMotion
  ? { opacity: 0 }
  : { opacity: 0, transform: 'translateY(6px) scale(0.97)' }
const cardAnimate = reduceMotion
  ? { opacity: 1 }
  : { opacity: 1, transform: 'translateY(0) scale(1)' }
const cardExit = reduceMotion
  ? { opacity: 0 }
  : { opacity: 0, transform: 'translateY(6px) scale(0.97)' }
```

## Repo conventions to follow

- The project already uses Framer Motion `AnimatePresence`, `motion`, and
  `useReducedMotion`; do not add a dependency.
- [Header.tsx](../pellier/frontend/src/components/Header.tsx) uses
  `AnimatePresence initial={false}`, full `transform` strings, and
  `useReducedMotion()` for menu entry and exit.
- [Modal.tsx](../pellier/frontend/src/design/primitives/Modal.tsx) is the
  shared modal exemplar: it fades the backdrop for `0.18s`, uses a
  `0.24s` card entrance and a `0.18s` card exit, and uses
  `[0.23, 1, 0.32, 1]` as its modal easing.
- [CartPanel.tsx](../pellier/frontend/src/components/CartPanel.tsx) shows
  the preferred reduced-motion hook style:
  `const reduceMotion = Boolean(useReducedMotion())`.

## Steps

1. In `pellier/frontend/src/components/PersonaModal.tsx`, import
   `AnimatePresence`, `motion`, and `useReducedMotion` from `framer-motion`.
   Define `PERSONA_MODAL_EASE` at module scope as
   `[0.23, 1, 0.32, 1]`.
2. Inside `PersonaModal`, call
   `const reduceMotion = Boolean(useReducedMotion())`. Define `cardInitial`,
   `cardAnimate`, and `cardExit` exactly as in the Target section. Do not use
   Framer Motion `x`, `y`, or `scale` props.
3. Remove the early `if (!open) return null`. Always call `createPortal`, with
   `<AnimatePresence initial={false}>` inside the portal and the existing
   overlay rendered only when `open` is true. This preserves a mounted exit
   long enough for Framer Motion to complete it.
4. Change `.pm-backdrop` from a plain `div` to `motion.div`. Set `initial`,
   `animate`, and `exit` to opacity-only values. Set its transition to
   `{ duration: 0.18, ease: PERSONA_MODAL_EASE }`.
5. Change `.pm-card` from a plain `div` to `motion.div`. Apply the three card
   values from Step 2, set
   `transition={{ duration: 0.24, ease: PERSONA_MODAL_EASE }}` for entry and
   `exit={{ ...cardExit, transition: { duration: 0.18, ease:
   PERSONA_MODAL_EASE } }}` for exit. Use `style={{ transformOrigin:
   'center' }}`. Keep the existing CSS classes unchanged.
6. Add `id="persona-modal-title"` to the existing `h2`, and add
   `role="dialog"`, `aria-modal="true"`, and
   `aria-labelledby="persona-modal-title"` to the motion card. Preserve the
   current backdrop, X-button, Escape, persona-selection, and sign-out close
   paths.
7. Extend `pellier/frontend/src/components/PersonaModal.test.tsx` with an
   accessibility assertion for the dialog role and accessible name. Where a
   close assertion is added, use `waitFor` rather than assuming synchronous
   unmounting; the overlay is expected to remain briefly during its exit.

## Boundaries

- Do not edit `Header.tsx`, `TopBar.tsx`, `ChatDrawer.tsx`, or the Labs
  workbench.
- Do not change persona fetching, copy, persona cards, selection behavior, or
  close semantics.
- Do not modify `persona-modal.css` for entrance keyframes. Framer Motion owns
  this interruptible mount/unmount animation.
- Do not add a stagger, hover lift, blur animation, particles, or sparkle
  effects.
- Do not add dependencies or animate layout-driving properties.
- If the current code differs materially from commit `633df9e`, stop and
  report the drift instead of applying this plan by analogy.

## Verification

- **Mechanical**:
  ```sh
  cd pellier/frontend
  npm test -- --run src/components/PersonaModal.test.tsx src/components/Header.test.tsx
  npm run type-check
  npm run lint
  npm run build
  git diff --check
  ```
  All commands must exit successfully.
- **Feel check**:
  - Open the modal from both the storefront header and the Labs top bar. The
    backdrop should establish focus first; the card should arrive from a
    restrained 6px lower position, not pop or bounce.
  - Close with Escape, the X button, the backdrop, selecting a persona, and
    signing out. Every path should fade out faster than it entered and leave no
    stuck overlay.
  - In browser DevTools Animations, slow playback to 10%. The card should use
    only opacity and the full transform string; no width, height, top, left,
    margin, or Framer `x`/`y`/`scale` shorthand should animate.
  - Toggle `prefers-reduced-motion: reduce` in DevTools Rendering. The
    backdrop and card should still fade, but the card must not translate or
    scale.
  - Reopen while closing. The active transition should remain smooth and finish
    in the final requested state without a second duplicate modal.
- **Done when**: the shared modal uses the same motion behavior from every
  entry point, closes cleanly from every existing close path, and preserves
  opacity-only feedback under reduced motion.
