/**
 * SpotlightTour: a short tour of the Storefront, three stops.
 *
 * Each stop rings one control: the Ask Pellier button, the Builder view switch
 * and the Operator link. A stop whose control is not on the page (on a phone
 * the switches fold into the menu) shows its card in the middle of the page
 * rather than ringing nothing.
 *
 * FirstVisitTour, which the Storefront home mounts, opens it once per browser
 * and never with `?tour=off`, so it does not open by itself on the Operator or
 * in a guide capture. The header's replay button opens it again on any
 * Storefront page; TourHost, in the shared header, listens for both.
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

/** Announced on window to open the tour: on a first visit, or from the replay button. */
export const TOUR_START_EVENT = 'pellier:tour-start'
export const SPOTLIGHT_SEEN_KEY = 'pellier-storefront-spotlight-seen'
/** The first visit waits for the page to lay out, so the first ring lands on the button. */
export const FIRST_VISIT_DELAY_MS = 600

const TARGETS: Record<(typeof TOUR.STEPS)[number]['id'], string> = {
  'ask-pellier': '[data-tour="ask-pellier"]',
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

// Seen once in this browser means seen in every tab: Lab 4 opens the
// storefront in a second tab, where a tour reopening over the header blocked
// the Operator link. sessionStorage is still read so a tab that set it keeps
// working. `?tour=off` counts as seen for the tab.
function hasSeenTour(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('tour') === 'off') {
      window.sessionStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
      return true
    }
    return (
      window.localStorage.getItem(SPOTLIGHT_SEEN_KEY) === 'true'
      || window.sessionStorage.getItem(SPOTLIGHT_SEEN_KEY) === 'true'
    )
  } catch {
    return true
  }
}

function markTourSeen(): void {
  try {
    window.localStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
  } catch {
    // Storage is optional. Without it the tour may show again; it never traps the visitor.
  }
}

/** Opens the tour once per browser, a moment after the Storefront home first renders. */
export function FirstVisitTour() {
  useEffect(() => {
    if (hasSeenTour()) return
    const timer = window.setTimeout(() => {
      markTourSeen()
      window.dispatchEvent(new Event(TOUR_START_EVENT))
    }, FIRST_VISIT_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [])
  return null
}

/** The header's replay button. On a phone it is hidden with the other folded controls. */
export function TourReplayButton() {
  return (
    <button
      type="button"
      className="pellier-tour-button"
      aria-label={TOUR.REPLAY}
      title={TOUR.REPLAY}
      data-testid="tour-replay"
      onClick={() => window.dispatchEvent(new Event(TOUR_START_EVENT))}
    >
      <CircleHelp size={16} strokeWidth={1.8} aria-hidden="true" />
    </button>
  )
}

/** The open tour, when a first visit or the replay button asks for it. */
export function TourHost() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const start = () => setOpen(true)
    window.addEventListener(TOUR_START_EVENT, start)
    return () => window.removeEventListener(TOUR_START_EVENT, start)
  }, [])

  const close = useCallback(() => setOpen(false), [])
  return open ? <SpotlightTour onClose={close} /> : null
}
