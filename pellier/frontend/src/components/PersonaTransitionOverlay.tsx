/**
 * PersonaTransitionOverlay — full-screen acknowledgement for scenario
 * selection and clearing.
 *
 * Reads PersonaContext.lastTransition. A ``sign-in`` transition means the
 * shopper scenario changed; it does not establish a security principal.
 * ``sign-out`` clears that scenario. The internal names remain for context
 * compatibility, while the visible copy keeps scenario and identity separate.
 *
 * Auto-dismisses after 1100ms (sign-in) / 800ms (sign-out). Click
 * anywhere on the overlay to dismiss early. Press Escape to dismiss
 * early too.
 *
 * Mounts via createPortal so the overlay sits above every route and
 * modal. Calls PersonaContext.clearTransition on dismissal so a
 * remount doesn't re-trigger on a stale marker.
 */
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, MotionConfig, useReducedMotion } from 'motion/react'
import { usePersona } from '../contexts/PersonaContext'
import { getPersonaPhoto } from '../data/personaPhotos'

const SIGN_IN_DURATION_MS = 1100
const SIGN_OUT_DURATION_MS = 800

// Persona-specific editorial line shown under the selected scenario.
// This overlay also appears during ordinary persona switching, so the copy
// describes each taste profile without implying that a prior thread exists.
const WELCOME_TAGLINES: Record<string, string> = {
  marco: 'Travel and utility, grounded in leather and linen.',
  anna: 'Gifting and ceremony, expressed in silk and glass.',
  theo: 'Slow living through craft, stoneware, and natural materials.',
  fresh: 'The floor is yours. Tell Pellier what catches your eye.',
}

function welcomeTagFor(personaId: string): string {
  return (
    WELCOME_TAGLINES[personaId] ??
    'Your Pellier edit is ready.'
  )
}

export default function PersonaTransitionOverlay() {
  const { lastTransition, clearTransition } = usePersona()
  const reducedMotion = useReducedMotion()
  const photoUrl = lastTransition ? getPersonaPhoto(lastTransition.persona.id) : undefined
  const firstName = lastTransition?.persona.display_name.split(' ')[0] ?? ''

  useEffect(() => {
    if (!lastTransition) return
    const ms =
      lastTransition.kind === 'sign-in'
        ? SIGN_IN_DURATION_MS
        : SIGN_OUT_DURATION_MS
    const t = setTimeout(clearTransition, ms)
    return () => clearTimeout(t)
  }, [lastTransition, clearTransition])

  // Escape key dismisses early.
  useEffect(() => {
    if (!lastTransition) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearTransition()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [lastTransition, clearTransition])

  return createPortal(
    <MotionConfig reducedMotion="user">
    <AnimatePresence>
      {lastTransition && (
        <motion.div
          key={lastTransition.id}
          className="fixed inset-0 z-[3000] flex items-center justify-center cursor-pointer"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28 }}
          onClick={clearTransition}
          role="status"
          aria-live="polite"
        >
          {/* Espresso scrim with a hair of blur — matches the tour
              overlay register so the storefront palette carries. */}
          <div
            className="absolute inset-0"
            style={{
              background: 'rgba(31, 20, 16, 0.55)',
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
            }}
          />

          <motion.div
            className="relative"
            initial={reducedMotion ? false : { opacity: 0, scale: 0.88, y: 24, filter: 'blur(10px)' }}
            animate={{ opacity: 1, scale: 1, y: 0, filter: 'blur(0px)' }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: -8, filter: 'blur(6px)' }}
            transition={{ type: 'spring', stiffness: 210, damping: 26, mass: 0.86 }}
            style={{
              maxWidth: lastTransition.kind === 'sign-in' ? 440 : 380,
              width: '92vw',
            }}
          >
            <div
              className="text-center"
              style={{
                background:
                  'linear-gradient(180deg, rgba(255,252,247,0.98) 0%, rgba(247,239,226,0.98) 100%)',
                border: '1px solid var(--rule-1)',
                borderRadius: 18,
                overflow: 'visible',
                boxShadow:
                  '0 28px 80px -20px rgba(31, 20, 16, 0.5), 0 8px 28px rgba(31,20,16,0.18)',
                padding:
                  lastTransition.kind === 'sign-in' ? '34px 34px 32px' : '28px 30px 26px',
              }}
            >
              <motion.div
                initial={{ scale: 0.72, y: 12, opacity: 0 }}
                animate={{ scale: 1, y: 0, opacity: 1 }}
                transition={{ delay: 0.12, type: 'spring', stiffness: 210, damping: 20 }}
                style={{
                  width: lastTransition.kind === 'sign-in' ? 112 : 82,
                  height: lastTransition.kind === 'sign-in' ? 112 : 82,
                  borderRadius: '50%',
                  margin: '0 auto 18px',
                  background: lastTransition.persona.avatar_color,
                  border: '4px solid rgba(255,250,240,0.94)',
                  boxShadow:
                    '0 18px 38px rgba(31,20,16,0.28), 0 0 0 1px rgba(31,20,16,0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                  color: 'var(--cream-1)',
                  fontFamily: 'var(--sans)',
                  fontSize: lastTransition.kind === 'sign-in' ? 42 : 30,
                  fontWeight: 650,
                  lineHeight: 1,
                }}
              >
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt={`${lastTransition.persona.display_name} profile`}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  lastTransition.persona.avatar_initial
                )}
              </motion.div>

              {/* Mono eyebrow — same register as the welcome card */}
              <div
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  letterSpacing: '0.24em',
                  textTransform: 'uppercase',
                  color: 'var(--red-1)',
                  fontWeight: 500,
                  marginBottom: 14,
                }}
              >
                <span aria-hidden>●</span>&nbsp;&nbsp;
                {lastTransition.kind === 'sign-in'
                  ? 'Scenario selected'
                  : 'Scenario cleared'}
                &nbsp;&nbsp;<span aria-hidden>●</span>
              </div>

              {/* Sans greeting — matches .sf-greeting on PellierWelcome
                  (readable; avoid heavy italic Fraunces on cream). */}
              <h2
                style={{
                  fontFamily: 'var(--sans)',
                  fontStyle: 'normal',
                  fontWeight: 400,
                  fontSize: lastTransition.kind === 'sign-in' ? 34 : 25,
                  lineHeight: 1.15,
                  letterSpacing: '-0.015em',
                  color: 'var(--ink-1)',
                  margin: 0,
                }}
              >
                {lastTransition.kind === 'sign-in' ? (
                  <>
                    Viewing{' '}
                    {firstName}.
                  </>
                ) : (
                  <>
                    Leaving{' '}
                    {firstName}.
                  </>
                )}
              </h2>

              {/* Persona-specific tag — sign-in only. */}
              {lastTransition.kind === 'sign-in' && (
                <p
                  style={{
                    fontFamily: 'var(--sans)',
                    fontStyle: 'normal',
                    fontWeight: 400,
                    fontSize: 15,
                    lineHeight: 1.6,
                    color: 'var(--ink-2)',
                    margin: '14px auto 0',
                    maxWidth: 360,
                  }}
                >
                  {welcomeTagFor(lastTransition.persona.id)}
                </p>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
    </MotionConfig>,
    document.body,
  )
}
