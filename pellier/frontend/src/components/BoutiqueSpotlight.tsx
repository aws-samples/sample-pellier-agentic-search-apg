/**
 * BoutiqueSpotlight — guided first-visit walkthrough for the boutique.
 *
 * A three-step spotlight that introduces visitors to Pellier: the
 * editorial storefront, the Ask Pellier concierge, and the Atelier toggle
 * for those curious about what's under the hood. Shows once per browser
 * session (sessionStorage gate).
 *
 * Mirrors AtelierSpotlight in structure, animation, keyboard handling,
 * and visual language. Only the content, the final-step CTA copy, and
 * the sessionStorage key differ.
 *
 * Keyboard: Escape dismisses. ArrowRight / Enter advance. ArrowLeft
 * goes back.
 */
import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight } from 'lucide-react'

const CREAM = '#fbf4e8'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'
const CREAM_WARM = '#f5e8d3'

interface SpotlightStep {
  numeral: string
  kicker: string
  headline: string
  body: string
}

const STEPS: SpotlightStep[] = [
  {
    numeral: 'I',
    kicker: 'Welcome to',
    headline: 'Pellier',
    body: "An editorial boutique with one trick up its sleeve — search that actually understands what you're after. Browse the floor, or just tell us what you have in mind.",
  },
  {
    numeral: 'II',
    kicker: 'Sign in first',
    headline: 'Let Pellier remember you',
    body: "Pick a persona from the top-right pill and watch the boutique tune itself — the cover, the recommendations, the voice of the chat. Try Marco for linen, Anna for gifts, Theo for home, or stay a Fresh visitor to see the editorial default.",
  },
  {
    numeral: 'III',
    kicker: 'Your concierge',
    headline: 'Ask Pellier',
    body: "Tap the floating button anytime and ask in your own words — \"a linen piece for slow Sundays,\" \"something that travels well.\" Pellier reads the boutique and pulls what fits.",
  },
  {
    numeral: 'IV',
    kicker: 'Behind the curtain',
    headline: 'The Atelier',
    body: "Curious how Pellier thinks? Toggle to the Atelier in the header and watch every reasoning step, tool call, and decision unfold in real time. The wires, made visible.",
  },
]

const FINAL_CTA = 'Start browsing'

// One-shot gate: once the visitor dismisses the spotlight in a
// session, don't re-show it on route changes or refreshes within
// the same tab. sessionStorage is the right shelf for this — it
// clears when the tab closes so a fresh session still gets the
// walkthrough.
const SPOTLIGHT_SEEN_KEY = 'pellier-storefront-spotlight-seen'

function hasSeenSpotlight(): boolean {
  if (typeof window === 'undefined') return true
  try {
    return window.sessionStorage.getItem(SPOTLIGHT_SEEN_KEY) === 'true'
  } catch {
    // private mode / storage disabled — skip rather than re-show
    // forever. Losing the gate is safer than spamming the overlay.
    return true
  }
}

function markSpotlightSeen(): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
  } catch {
    /* noop */
  }
}

export default function BoutiqueSpotlight() {
  // Initialize from sessionStorage so the overlay stays dismissed
  // across the lifetime of a tab.
  const [visible, setVisible] = useState(() => !hasSeenSpotlight())
  const [step, setStep] = useState(0)

  const dismiss = useCallback(() => {
    markSpotlightSeen()
    setVisible(false)
  }, [])

  const next = useCallback(() => {
    if (step < STEPS.length - 1) setStep((s) => s + 1)
    else dismiss()
  }, [step, dismiss])

  const prev = useCallback(() => {
    if (step > 0) setStep((s) => s - 1)
  }, [step])

  useEffect(() => {
    if (!visible) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss()
      if (e.key === 'ArrowRight' || e.key === 'Enter') next()
      if (e.key === 'ArrowLeft') prev()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [visible, dismiss, next, prev])

  if (!visible) return null

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[999] flex items-center justify-center p-4"
        style={{
          background: 'rgba(45, 24, 16, 0.35)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={dismiss}
      >
        <motion.div
          key={step}
          className="relative w-full max-w-[460px] rounded-3xl overflow-hidden"
          style={{
            background: CREAM,
            border: '1px solid rgba(45, 24, 16, 0.08)',
            boxShadow: '0 25px 60px rgba(45, 24, 16, 0.18)',
          }}
          initial={{ opacity: 0, y: 20, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 340, damping: 30 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Editorial numeral mark — replaces the icon badge */}
          <div className="flex items-center justify-center pt-12 pb-2">
            <div
              className="leading-none select-none"
              style={{
                fontFamily: 'Fraunces, Georgia, serif',
                fontWeight: 300,
                fontStyle: 'italic',
                color: ACCENT,
                fontSize: 64,
                letterSpacing: '-0.02em',
              }}
            >
              {current.numeral}
            </div>
          </div>

          {/* Content */}
          <div className="px-8 pb-3 text-center">
            <p
              className="text-[10px] font-medium uppercase mb-3"
              style={{ color: ACCENT, letterSpacing: '0.2em' }}
            >
              {current.kicker}
            </p>
            <h2
              className="text-[32px] leading-[1.1] mb-4"
              style={{
                fontFamily: 'Fraunces, Georgia, serif',
                fontWeight: 400,
                fontStyle: 'italic',
                color: INK,
                letterSpacing: '-0.02em',
              }}
            >
              {current.headline}
            </h2>
            <p
              className="text-[15px] leading-[1.7] mx-auto"
              style={{ color: INK_SOFT, maxWidth: 360 }}
            >
              {current.body}
            </p>
          </div>

          {/* Footer — dots + navigation */}
          <div className="px-8 pt-4 pb-8 flex items-center justify-between">
            {/* Step dots */}
            <div className="flex items-center gap-2">
              {STEPS.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setStep(i)}
                  aria-label={`Step ${i + 1}`}
                  className="rounded-full transition-all duration-200"
                  style={{
                    width: i === step ? 20 : 7,
                    height: 7,
                    background: i === step ? ACCENT : `${INK_QUIET}50`,
                  }}
                />
              ))}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3">
              {step > 0 && (
                <button
                  type="button"
                  onClick={prev}
                  className="text-[13px] font-medium px-3 py-1.5 rounded-lg transition-colors"
                  style={{ color: INK_SOFT }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = CREAM_WARM)
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = 'transparent')
                  }
                >
                  Back
                </button>
              )}
              {!isLast && (
                <button
                  type="button"
                  onClick={dismiss}
                  className="text-[13px] px-3 py-1.5 rounded-lg"
                  style={{ color: INK_QUIET }}
                >
                  Skip
                </button>
              )}
              <button
                type="button"
                onClick={next}
                className="inline-flex items-center gap-1.5 text-[13px] font-medium px-5 py-2 rounded-full transition-colors"
                style={{ background: INK, color: CREAM }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = '#3d2518')
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = INK)
                }
              >
                {isLast ? FINAL_CTA : 'Next'}
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
