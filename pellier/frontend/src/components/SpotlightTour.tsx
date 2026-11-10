/**
 * SpotlightTour: a short tour of Pellier, told in chapters.
 *
 * Each stop rings one control and says what it is. The Storefront chapter
 * opens on a first visit and rings the header: the Ask Pellier button, the
 * Builder view switch, the Operator link, then the shoppers in the dock. The
 * other chapters open when the part of the page they describe first appears:
 * a settled answer, a client record on the Operator, a proposed credit. The
 * component that owns that part says when, with `useTourChapter`
 * (tourChapters.ts).
 *
 * A chapter opens once per browser and never with `?tour=off`, so it stays
 * out of a guide capture. It never clicks anything for the visitor. The
 * header's replay button plays the chapters that are on the page; TourHost,
 * in the shared header, opens them one at a time.
 *
 * Motion is a fade for the card and a copper pulse on the ring, both off when
 * the visitor asks for reduced motion. Every color is a token.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation } from 'react-router-dom'
import { useReducedMotion } from 'motion/react'
import { CircleHelp } from 'lucide-react'
import { TOUR } from '../copy'
import {
  TOUR_START_EVENT,
  chapterRank,
  hasSeen,
  markSeen,
  replayStops,
  targetElement,
  toursOff,
  useTourChapter,
  type ChapterId,
  type TourStop,
  type TourSurface,
  wholeChapter,
} from './tourChapters'
import '../styles/spotlight-tour.css'

const GUTTER = 16
const RING_PAD = 6
const CARD_GAP = 14
/** How often an open tour looks again for its control: a record or a photo can load and move it with no scroll. */
const FOLLOW_MS = 250
/** The kinds of field a visitor writes in. */
const WRITTEN_INPUTS = ['text', 'search', 'email', 'url', 'tel', 'password', 'number']
const FOCUSABLE = 'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'

interface Box { top: number; left: number; width: number; height: number }
type Placement = 'below' | 'above' | 'over' | 'center'
interface CardPlace { placement: Placement; top: number; left: number }
type TourRequest = ChapterId | 'replay'

function sameBox(a: Box | null, b: Box | null): boolean {
  if (!a || !b) return a === b
  return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height
}

function samePlace(a: CardPlace | null, b: CardPlace): boolean {
  return a !== null && a.placement === b.placement && a.top === b.top && a.left === b.left
}

function ringAround(element: Element | null): Box | null {
  if (!element) return null
  const rect = element.getBoundingClientRect()
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
  // The card stays in the window even when the visitor scrolls its control out of it.
  const lowest = viewportHeight - GUTTER - card.height
  const below = ring.top + ring.height + CARD_GAP
  if (below <= lowest) {
    return { placement: 'below' as Placement, top: Math.max(GUTTER, below), left }
  }
  const above = ring.top - CARD_GAP - card.height
  if (above >= GUTTER) {
    return { placement: 'above' as Placement, top: Math.min(above, lowest), left }
  }
  // No room beside a tall panel: the card covers its lower edge and leaves its heading in view.
  return { placement: 'over' as Placement, top: Math.max(GUTTER, lowest), left }
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
 * The open tour. Mounting it opens it at the first of `stops`; `onClose` runs
 * on Skip, Done or Escape. A stop whose control has left the page shows its
 * card in the middle rather than ringing nothing.
 */
export default function SpotlightTour({ stops, onClose }: { stops: TourStop[]; onClose: () => void }) {
  const [step, setStep] = useState(0)
  const [ring, setRing] = useState<Box | null>(null)
  const [card, setCard] = useState<CardPlace | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const reduceMotion = Boolean(useReducedMotion())
  const current = stops[step]
  const total = stops.length
  const isLast = step === total - 1

  const next = useCallback(() => {
    if (step < total - 1) setStep(step + 1)
    else onClose()
  }, [onClose, step, total])
  const back = useCallback(() => {
    if (step > 0) setStep(step - 1)
  }, [step])

  useLayoutEffect(() => {
    const { target } = current
    // jsdom has no scrollIntoView; a browser always does.
    if (target.inPage) {
      targetElement(target)?.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'instant' })
    }
    const measure = () => {
      const box = ringAround(targetElement(target))
      const dialog = dialogRef.current
      setRing(previous => (sameBox(previous, box) ? previous : box))
      if (!dialog) return
      const place = placeCard(box, { width: dialog.offsetWidth, height: dialog.offsetHeight })
      setCard(previous => (samePlace(previous, place) ? previous : place))
    }
    measure()
    // Caught on the way down, so the dock and the Operator's columns count: scroll does not bubble.
    const scrolling = { passive: true, capture: true }
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, scrolling)
    const following = window.setInterval(measure, FOLLOW_MS)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, scrolling)
      window.clearInterval(following)
    }
  }, [current])

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
          data-shape={current.target.panel ? 'panel' : 'control'}
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

/** Opens the Storefront chapter once per browser, a moment after the home page first renders. */
export function FirstVisitTour() {
  useTourChapter('storefront', true)
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

function requestOf(event: Event): TourRequest {
  return event instanceof CustomEvent && typeof event.detail === 'string' ? (event.detail as ChapterId) : 'replay'
}

/** True while the visitor is partway through writing something, such as their next question. */
function isWriting(): boolean {
  const field = document.activeElement
  const written = field instanceof HTMLTextAreaElement
    || (field instanceof HTMLInputElement && WRITTEN_INPUTS.includes(field.type))
  return written && field.value.trim() !== ''
}

/** Orientation before detail, and a replay after whatever was already waiting. */
function inTellingOrder(a: TourRequest, b: TourRequest): number {
  const rank = (request: TourRequest) => (request === 'replay' ? Number.MAX_SAFE_INTEGER : chapterRank(request))
  return rank(a) - rank(b)
}

/**
 * The open tour, for a chapter that is ready or for the replay button.
 *
 * One chapter shows at a time; another that becomes ready meanwhile waits its
 * turn. `hold` keeps a chapter from opening over a running turn. A chapter
 * opens by itself only on a page that shows all of it, and never over a
 * question the visitor is writing: it is let go, and its part of the page asks
 * again the next time it is ready. A chapter counts as seen when it opens,
 * never when it is only asked for, and a new page closes the tour and forgets
 * what was waiting.
 */
export function TourHost({ surface, hold = false }: { surface: TourSurface; hold?: boolean }) {
  const { pathname } = useLocation()
  const [waiting, setWaiting] = useState<TourRequest[]>([])
  const [stops, setStops] = useState<TourStop[] | null>(null)
  // Storage may refuse the seen flag; while this header stays mounted a chapter still opens only once.
  const opened = useRef(new Set<ChapterId>())

  useEffect(() => {
    const start = (event: Event) => {
      const request = requestOf(event)
      setWaiting(current => (current.includes(request) ? current : [...current, request].sort(inTellingOrder)))
    }
    window.addEventListener(TOUR_START_EVENT, start)
    return () => window.removeEventListener(TOUR_START_EVENT, start)
  }, [])

  // `?tour=off` is read here, on the first page of the tab, whether or not that page has a chapter.
  useEffect(() => {
    toursOff()
  }, [])

  useEffect(() => {
    setStops(null)
    setWaiting(current => (current.length === 0 ? current : []))
  }, [pathname])

  useEffect(() => {
    if (stops || hold || waiting.length === 0) return
    const [request, ...rest] = waiting
    setWaiting(rest)
    if (request !== 'replay' && (opened.current.has(request) || hasSeen(request) || isWriting())) return
    const found = request === 'replay' ? replayStops(surface) : wholeChapter(request)
    if (found.length === 0) return
    if (request !== 'replay') {
      opened.current.add(request)
      markSeen(request)
    }
    setStops(found)
  }, [stops, hold, waiting, surface])

  const close = useCallback(() => setStops(null), [])
  return stops ? <SpotlightTour stops={stops} onClose={close} /> : null
}
