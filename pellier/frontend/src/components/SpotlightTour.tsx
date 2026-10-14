/**
 * SpotlightTour: the first-visit tour of the Storefront.
 *
 * Five stops. The first, Code Editor, is outside this app, so its card sits
 * in the middle of the page with no ring. The others ring a control: the Ask
 * Pellier button, the shopper chips (the docked panel's "Signed in as" row,
 * or the header's shopper pill when the panel is closed), the Builder view
 * switch and the Operator link. A stop whose control is not on the page falls
 * back to the centred card rather than ringing nothing.
 *
 * It follows the first-visit welcome (PellierSpotlight): however the welcome
 * closes, it announces TOUR_START_EVENT and the tour opens at its first stop.
 * The welcome shows only on the Storefront home, once per browser, and not
 * with `?tour=off`, so the tour never opens by itself on the Operator or in a
 * guide capture. The header's replay button opens it again on any Storefront
 * page.
 *
 * Motion is a fade for the card and a copper pulse on the ring, both off when
 * the visitor asks for reduced motion. Every color is a token.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useReducedMotion } from 'motion/react'
import { CircleHelp } from 'lucide-react'
import { TOUR } from '../copy'
import '../styles/spotlight-tour.css'

/** Announced on window when the first-visit welcome closes. */
export const TOUR_START_EVENT = 'pellier:tour-start'

const TARGETS: Record<(typeof TOUR.STEPS)[number]['id'], string | null> = {
  'code-editor': null,
  'ask-pellier': '[data-tour="ask-pellier"]',
  shoppers: '[data-tour="shoppers"]',
  'builder-view': '.pellier-builder-toggle',
  operator: '[data-tour="operator"]',
}

const GUTTER = 16
const RING_PAD = 6
const CARD_GAP = 14
const FOCUSABLE = 'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'

interface Box { top: number; left: number; width: number; height: number }
type Placement = 'below' | 'above' | 'center'

function targetBox(selector: string | null): Box | null {
  if (!selector) return null
  // The first match the page lays out: the shopper stop has two candidates,
  // and only one shows at a time.
  const rect = Array.from(document.querySelectorAll(selector))
    .map(element => element.getBoundingClientRect())
    .find(box => box.width > 0 && box.height > 0)
  if (!rect) return null
  return {
    top: rect.top - RING_PAD,
    left: rect.left - RING_PAD,
    width: rect.width + RING_PAD * 2,
    height: rect.height + RING_PAD * 2,
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

function placeCard(ring: Box | null, card: { width: number; height: number }) {
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  if (!ring) {
    return {
      placement: 'center' as Placement,
      top: Math.max(GUTTER, (viewportHeight - card.height) / 2),
      left: Math.max(GUTTER, (viewportWidth - card.width) / 2),
    }
  }
  const left = clamp(
    ring.left + ring.width / 2 - card.width / 2,
    GUTTER,
    viewportWidth - GUTTER - card.width,
  )
  const below = ring.top + ring.height + CARD_GAP
  if (below + card.height <= viewportHeight - GUTTER) {
    return { placement: 'below' as Placement, top: below, left }
  }
  const above = ring.top - CARD_GAP - card.height
  return { placement: 'above' as Placement, top: Math.max(GUTTER, above), left }
}

function trapTab(event: KeyboardEvent, dialog: HTMLElement): void {
  const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE))
  if (focusable.length === 0) {
    event.preventDefault()
    dialog.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  const outside = !dialog.contains(active)
  if (event.shiftKey && (active === first || active === dialog || outside)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || outside)) {
    event.preventDefault()
    first.focus()
  }
}

/**
 * The open tour. Mounting it opens it at the first stop; `onClose` runs on
 * Skip, Done or Escape.
 */
export default function SpotlightTour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0)
  const [ring, setRing] = useState<Box | null>(null)
  const [card, setCard] = useState<{ placement: Placement; top: number; left: number } | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const reduceMotion = Boolean(useReducedMotion())
  const current = TOUR.STEPS[step]
  const total = TOUR.STEPS.length
  const isLast = step === total - 1

  const next = useCallback(() => {
    if (step < total - 1) setStep(step + 1)
    else onClose()
  }, [onClose, step, total])
  const back = useCallback(() => {
    if (step > 0) setStep(step - 1)
  }, [step])

  useLayoutEffect(() => {
    const measure = () => {
      const box = targetBox(TARGETS[current.id])
      const dialog = dialogRef.current
      setRing(box)
      if (dialog) setCard(placeCard(box, { width: dialog.offsetWidth, height: dialog.offsetHeight }))
    }
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, { passive: true })
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure)
    }
  }, [current.id])

  // Declared before the focus effect, so it records the control that opened
  // the tour rather than the dialog.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    return () => {
      if (opener?.isConnected && opener !== document.body) opener.focus()
    }
  }, [])

  useEffect(() => {
    dialogRef.current?.focus()
  }, [step])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Tab' && dialogRef.current) {
        trapTab(event, dialogRef.current)
        return
      }
      const keys: Record<string, () => void> = { Escape: onClose, ArrowRight: next, ArrowLeft: back }
      const action = keys[event.key]
      if (!action) return
      // Caught on the way down and stopped here, Escape never reaches the
      // store's own handler, which would also close the docked Ask Pellier.
      event.preventDefault()
      event.stopPropagation()
      action()
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [back, next, onClose])

  return createPortal(
    <div
      className="spotlight-tour"
      data-testid="spotlight-tour"
      data-motion={reduceMotion ? 'reduce' : 'full'}
      data-target={ring ? 'ring' : 'none'}
    >
      {ring ? (
        <div
          className="spotlight-tour-ring"
          data-testid="spotlight-tour-ring"
          aria-hidden="true"
          style={{ top: ring.top, left: ring.left, width: ring.width, height: ring.height }}
        />
      ) : null}
      <div
        ref={dialogRef}
        key={current.id}
        role="dialog"
        aria-modal="true"
        aria-label={`${TOUR.DIALOG_LABEL}: ${current.title}`}
        aria-describedby="spotlight-tour-body"
        tabIndex={-1}
        className="spotlight-tour-card"
        data-placement={card?.placement ?? 'center'}
        // Unplaced, the card waits transparent, not hidden: the focus effect
        // runs before the first placement paints, and a browser will not focus
        // a visibility: hidden element.
        style={card ? { top: card.top, left: card.left } : { top: 0, left: 0, opacity: 0 }}
      >
        <div className="spotlight-tour-top">
          <span className="spotlight-tour-progress">{TOUR.progress(step + 1, total)}</span>
          <button type="button" className="spotlight-tour-skip" onClick={onClose}>
            {TOUR.SKIP}
          </button>
        </div>
        <h2 className="spotlight-tour-title">{current.title}</h2>
        <p id="spotlight-tour-body" className="spotlight-tour-body">{current.body}</p>
        <div className="spotlight-tour-actions">
          {step > 0 ? (
            <button type="button" className="spotlight-tour-back" onClick={back}>
              {TOUR.BACK}
            </button>
          ) : null}
          <button type="button" className="spotlight-tour-next" onClick={next}>
            {isLast ? TOUR.DONE : TOUR.NEXT}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/**
 * The header's replay button and the tour it opens: by itself when the
 * welcome closes, or from the button.
 */
export function TourControl() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const start = () => setOpen(true)
    window.addEventListener(TOUR_START_EVENT, start)
    return () => window.removeEventListener(TOUR_START_EVENT, start)
  }, [])

  const close = useCallback(() => setOpen(false), [])

  return (
    <>
      <button
        type="button"
        className="pellier-tour-button"
        aria-label={TOUR.REPLAY}
        title={TOUR.REPLAY}
        data-testid="tour-replay"
        onClick={() => setOpen(true)}
      >
        <CircleHelp size={16} strokeWidth={1.8} aria-hidden="true" />
      </button>
      {open ? <SpotlightTour onClose={close} /> : null}
    </>
  )
}
