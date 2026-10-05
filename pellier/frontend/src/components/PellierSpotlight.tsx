/**
 * PellierSpotlight - the first-visit orientation for the governed storefront.
 *
 * It frames Pellier the way the architecture actually works: a Storefront
 * Dispatcher routing shopper turns to specialists, a separate two-agent
 * Operator Concierge graph, shared Aurora customer truth, and every
 * state-changing action behind a human confirmation.
 *
 * Claims here are deliberately limited to what ships. Comparable retail-agent
 * architectures spread this across four engines (a vector index, a key-value
 * store, an external cache); Pellier does it in Aurora PostgreSQL alone, so
 * the copy says Aurora and names no service this app does not use. It also
 * does not mention promotions or notifications, which are not implemented.
 *
 * Every color is a token (the Tailwind roles in tailwind.config.js), so the
 * overlay follows the theme; headings are Instrument Sans 500 through the
 * base heading rule, and buttons are pills.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { X } from 'lucide-react'
import { imageSrc } from '../utils/assetPath'


/** The four people the labs follow, in lab order. */
const LAB_PEOPLE = [
  { id: 'anna', name: 'Anna', lab: 1, topic: 'search', image: '/assets/personas/anna-720.webp' },
  { id: 'marco', name: 'Marco', lab: 2, topic: 'an agent with tools', image: '/assets/personas/marco-720.webp' },
  { id: 'theo', name: 'Theo', lab: 3, topic: 'a managed agent', image: '/assets/personas/theo-720.webp' },
  { id: 'jessica', name: 'Jessica', lab: 4, topic: 'an approved action', image: '/assets/personas/jessica-720.webp' },
] as const

/**
 * A slide's media.
 *
 * `photo` is one catalog photograph. `personas` is the four lab anchors as a
 * portrait strip of the four people the labs follow.
 */
type SpotlightMedia =
  | { kind: 'photo'; src: string; alt: string }
  | { kind: 'personas' }

interface SpotlightStep {
  label: string
  eyebrow: string
  headline: string
  body: string
  media: SpotlightMedia
}

const STEPS: SpotlightStep[] = [
  {
    label: 'Choose',
    eyebrow: 'Welcome to Pellier',
    headline: 'Begin with the edit.',
    body: 'Choose a point of view, then browse a collection shaped by the details that matter to that shopper.',
    // A 16:9 hero, not the 4:5 product shot. This band is ~2.85:1, so
    // `object-cover` on a portrait frame cropped away most of the bag and left
    // a hard zoom on its middle.
    media: {
      kind: 'photo',
      src: '/products/landing-hero-weekender-1600.webp',
      alt: 'A leather weekender on an oak bench beside a linen throw, a wooden bowl and a stoneware vase of olive branches',
    },
  },
  {
    label: 'Ask',
    eyebrow: 'Ask Pellier',
    headline: 'Use your own words.',
    body: 'Ask for a piece or occasion. Pellier reads the current catalog and your chosen point of view before it recommends a place to start.',
    // The webp of the same frame: the PNG beside it is 1.8 MB for a 552px band.
    media: {
      kind: 'photo',
      src: '/products/hero-anna-1600.webp',
      alt: 'A white gift box tied with a blush-pink ribbon, a blank kraft tag and a vase with one eucalyptus stem on a small oak side table',
    },
  },
  {
    label: 'Trace',
    eyebrow: 'Builder view and Operator',
    headline: 'Follow the evidence.',
    body: 'Turn on the Builder view to see the steps behind each answer. When a request needs a person, such as a store credit, it waits on the Operator desk until someone on the team approves or declines it.',
    // The four people the evidence is followed for, rather than a screenshot of
    // the surface that follows it. A cropped UI capture read as washed-out
    // chrome at this size and dated the moment the panel changed.
    media: { kind: 'personas' },
  },
]

export const SPOTLIGHT_SEEN_KEY = 'pellier-storefront-spotlight-seen'
const MOTION_EASE: [number, number, number, number] = [0.16, 1, 0.3, 1]
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function hasSeenSpotlight(): boolean {
  if (typeof window === 'undefined') return true
  try {
    return window.sessionStorage.getItem(SPOTLIGHT_SEEN_KEY) === 'true'
  } catch {
    return true
  }
}

function markSpotlightSeen(): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
  } catch {
    // Storage is optional. Do not trap the visitor in the tour.
  }
}

export default function PellierSpotlight() {
  const [visible, setVisible] = useState(() => !hasSeenSpotlight())
  const [step, setStep] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const reduceMotion = Boolean(useReducedMotion())

  const dismiss = useCallback(() => {
    markSpotlightSeen()
    setVisible(false)
  }, [])

  const next = useCallback(() => {
    if (step < STEPS.length - 1) {
      setStep((current) => current + 1)
      return
    }
    dismiss()
  }, [dismiss, step])

  const previous = useCallback(() => {
    if (step > 0) setStep((current) => current - 1)
  }, [step])

  useEffect(() => {
    if (!visible) return
    const previousOverflow = document.body.style.overflow
    openerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    document.body.style.overflow = 'hidden'
    dialogRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      if (openerRef.current?.isConnected) {
        openerRef.current.focus()
      }
    }
  }, [visible])

  useEffect(() => {
    if (!visible) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Tab') {
        const dialog = dialogRef.current
        if (!dialog) return
        const focusable = Array.from(
          dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
        )
        if (focusable.length === 0) {
          event.preventDefault()
          dialog.focus()
          return
        }

        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        const active = document.activeElement
        if (
          event.shiftKey &&
          (active === first || active === dialog || !dialog.contains(active))
        ) {
          event.preventDefault()
          last.focus()
        } else if (
          !event.shiftKey &&
          (active === last || !dialog.contains(active))
        ) {
          event.preventDefault()
          first.focus()
        }
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        dismiss()
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault()
        next()
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        previous()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [dismiss, next, previous, visible])

  if (!visible) return null

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[999] flex items-center justify-center bg-scrim p-4 sm:p-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: reduceMotion ? 0.1 : 0.18, ease: MOTION_EASE }}
        onClick={dismiss}
      >
        <motion.div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="pellier-spotlight-title"
          aria-describedby="pellier-spotlight-description"
          tabIndex={-1}
          className="relative w-full max-w-[552px] overflow-hidden rounded-[var(--dl-r-card)] border border-line bg-paper text-ink shadow-deep outline-none"
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.985 }}
          animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.99 }}
          transition={{
            duration: reduceMotion ? 0.1 : 0.24,
            ease: MOTION_EASE,
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            aria-label="Skip welcome tour"
            onClick={dismiss}
            className="absolute right-3 top-3 z-10 inline-flex h-12 w-12 items-center justify-center rounded-full border border-on-photo/30 bg-scrim text-on-photo transition-colors hover:border-on-photo focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-on-photo focus-visible:ring-offset-2 focus-visible:ring-offset-scrim"
          >
            <X size={17} strokeWidth={1.8} aria-hidden="true" />
          </button>

          <div className="h-[194px] overflow-hidden bg-recessed sm:h-[208px]">
            <AnimatePresence initial={false} mode="wait">
              {current.media.kind === 'photo' ? (
                <motion.img
                  key={current.media.src}
                  src={imageSrc(current.media.src)}
                  alt={current.media.alt}
                  className="h-full w-full object-cover"
                  initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 1.035 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 1.02 }}
                  transition={{
                    duration: reduceMotion ? 0.1 : 0.28,
                    ease: MOTION_EASE,
                  }}
                />
              ) : (
                /* One label for the whole strip: four portraits announced
                   separately would read as four unrelated images between the
                   headline and the controls. */
                <motion.div
                  key="personas"
                  role="img"
                  aria-label={`The four people each lab follows: ${LAB_PEOPLE.map(
                    (person) => `${person.name}, lab ${person.lab}, ${person.topic}`,
                  ).join('; ')}`}
                  className="grid h-full w-full grid-cols-4 gap-2 p-2"
                  initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 1.035 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 1.02 }}
                  transition={{
                    duration: reduceMotion ? 0.1 : 0.28,
                    ease: MOTION_EASE,
                  }}
                >
                  {LAB_PEOPLE.map((person) => (
                    <div
                      key={person.id}
                      className="relative overflow-hidden rounded-[var(--pellier-image-radius-sm)]"
                    >
                      <img
                        src={imageSrc(person.image)}
                        alt=""
                        width={720}
                        height={1080}
                        className="h-full w-full object-cover"
                      />
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-scrim to-transparent px-1.5 pb-1.5 pt-6 text-center">
                        <span className="block font-mono text-[9px] uppercase leading-tight tracking-[0.12em] text-on-photo">
                          {person.name}
                        </span>
                        <span className="block font-mono text-[9px] uppercase leading-tight tracking-[0.1em] text-on-photo/70">
                          {`Lab ${person.lab}`}
                        </span>
                      </div>
                    </div>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="relative px-6 pb-2 pt-0 sm:px-8">
            <AnimatePresence initial={false} mode="wait">
              <motion.div
                key={current.label}
                className="pt-6"
                initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 7 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -5 }}
                transition={{
                  duration: reduceMotion ? 0.1 : 0.2,
                  ease: MOTION_EASE,
                }}
              >
                <div className="mb-3 flex items-baseline gap-3">
                  <span
                    aria-hidden="true"
                    className="font-sans text-[18px] font-medium leading-none text-copper"
                  >
                    {String(step + 1).padStart(2, '0')}
                  </span>
                  <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-copper">
                    {current.eyebrow}
                  </p>
                </div>
                <h2
                  id="pellier-spotlight-title"
                  className="max-w-[18ch] font-sans text-[34px] font-medium leading-[1.03] text-ink sm:text-[38px]"
                >
                  {current.headline}
                </h2>
                <p
                  id="pellier-spotlight-description"
                  className="mt-3 max-w-[39ch] font-sans text-[15px] leading-6 text-ink-2"
                >
                  {current.body}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-t border-line px-6 py-4 sm:px-8">
            <nav className="flex items-center gap-2.5" aria-label="Welcome tour progress">
              <span
                aria-hidden="true"
                className="font-sans text-[10px] font-semibold tracking-[0.14em] text-muted"
              >
                01
              </span>
              {STEPS.map((tourStep, index) => (
                <button
                  key={tourStep.label}
                  type="button"
                  onClick={() => setStep(index)}
                  aria-label={`Show ${tourStep.label}, step ${index + 1} of ${STEPS.length}`}
                  aria-current={index === step ? 'step' : undefined}
                  className="group inline-flex h-12 w-12 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
                >
                  <span
                    aria-hidden="true"
                    className={[
                      'block h-px transition-[width,background-color] duration-200',
                      index === step
                        ? 'w-7 bg-ink'
                        : 'w-4 bg-line-strong group-hover:bg-muted',
                    ].join(' ')}
                  />
                </button>
              ))}
              <span
                aria-hidden="true"
                className="font-sans text-[10px] font-semibold tracking-[0.14em] text-muted"
              >
                03
              </span>
            </nav>

            <div className="flex items-center gap-2">
              {step > 0 ? (
                <button
                  type="button"
                  onClick={previous}
                  className="min-h-12 rounded-full px-4 font-sans text-[13px] font-medium text-ink-2 transition-colors hover:bg-recessed hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
                >
                  Back
                </button>
              ) : (
                <button
                  type="button"
                  onClick={dismiss}
                  className="min-h-12 rounded-full px-4 font-sans text-[13px] font-medium text-ink-2 transition-colors hover:bg-recessed hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
                >
                  Skip
                </button>
              )}
              <button
                type="button"
                onClick={next}
                className="inline-flex min-h-12 items-center gap-2 rounded-full bg-ink px-5 font-sans text-[13px] font-medium text-on-ink transition-colors hover:bg-ink-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
              >
                {isLast ? 'Explore Pellier' : 'Continue'}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
