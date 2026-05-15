/**
 * AtelierSpotlight — guided first-visit walkthrough for the Atelier.
 *
 * A three-step spotlight that introduces the instrumentation surface:
 * the Atelier concept, the conversation pane, and the reasoning tabs.
 * Shows once per browser session (sessionStorage gate).
 *
 * Mirrors BoutiqueSpotlight in structure, animation, keyboard
 * handling, and visual language — editorial roman numerals, Fraunces
 * italic headlines, warm cream card. Only the content, the final-step
 * CTA copy, and the sessionStorage key differ.
 *
 * Keyboard: Escape dismisses. ArrowRight / Enter advance. ArrowLeft
 * goes back.
 */
import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { cssVar as c } from '../design/cssVars'


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
    headline: 'The Atelier',
    body: "This is where Pellier thinks out loud. Every agent decision, every tool call, every database read — visible in real time. The workshop behind the boutique.",
  },
  {
    numeral: 'II',
    kicker: 'On the left',
    headline: 'The conversation',
    body: "Ask Pellier anything you'd ask in the boutique. The difference here: you see exactly how the answer was built — which specialist handled it, what tools fired, how long each step took.",
  },
  {
    numeral: 'III',
    kicker: 'On the right',
    headline: 'The reasoning',
    body: "Three tabs. Telemetry replays every panel the agent emitted. Architecture maps the seven building blocks. Performance shows where the system spends its time. Tap any card to go deeper.",
  },
]

const FINAL_CTA = 'Get started'

export default function AtelierSpotlight() {
  const [visible, setVisible] = useState(true)
  const [step, setStep] = useState(0)

  const dismiss = useCallback(() => {
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
            background: c.bg,
            border: '1px solid rgba(45, 24, 16, 0.08)',
            boxShadow: '0 25px 60px rgba(45, 24, 16, 0.18)',
          }}
          initial={{ opacity: 0, y: 20, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 340, damping: 30 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Editorial numeral mark */}
          <div className="flex items-center justify-center pt-12 pb-2">
            <div
              className="leading-none select-none"
              style={{
                fontFamily: 'Fraunces, Georgia, serif',
                fontWeight: 300,
                fontStyle: 'italic',
                color: c.accent,
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
              style={{ color: c.accent, letterSpacing: '0.2em' }}
            >
              {current.kicker}
            </p>
            <h2
              className="text-[32px] leading-[1.1] mb-4"
              style={{
                fontFamily: 'Fraunces, Georgia, serif',
                fontWeight: 400,
                fontStyle: 'italic',
                color: c.ink,
                letterSpacing: '-0.02em',
              }}
            >
              {current.headline}
            </h2>
            <p
              className="text-[15px] leading-[1.7] mx-auto"
              style={{ color: c.ink2, maxWidth: 360 }}
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
                    background:
                      i === step
                        ? c.accent
                        : 'color-mix(in srgb, var(--ink-quiet) 50%, transparent)',
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
                  style={{ color: c.ink2 }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = c.paper)
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
                  style={{ color: c.muted }}
                >
                  Skip
                </button>
              )}
              <button
                type="button"
                onClick={next}
                className="inline-flex items-center gap-1.5 text-[13px] font-medium px-5 py-2 rounded-full transition-colors"
                style={{ background: c.ink, color: c.bg }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = 'var(--ink)')
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = c.ink)
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
