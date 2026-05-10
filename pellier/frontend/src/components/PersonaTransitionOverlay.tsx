/**
 * PersonaTransitionOverlay — full-screen celebration for sign-in /
 * sign-out moments.
 *
 * Reads PersonaContext.lastTransition. On sign-in: cream card with
 * italic Fraunces "Welcome back, {name}." + a persona-specific tag
 * line + animated red-1 check. On sign-out: smaller farewell card
 * with "See you soon, {name}." — mirrored but quieter.
 *
 * Auto-dismisses after 2400ms (sign-in) / 1600ms (sign-out). Click
 * anywhere on the overlay to dismiss early. Press Escape to dismiss
 * early too.
 *
 * Mounts via createPortal so the overlay sits above every route and
 * modal. Calls PersonaContext.clearTransition on dismissal so a
 * remount doesn't re-trigger on a stale marker.
 */
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Check } from 'lucide-react'
import { usePersona } from '../contexts/PersonaContext'

const SIGN_IN_DURATION_MS = 2400
const SIGN_OUT_DURATION_MS = 1600

// Persona-specific "your thread" line shown under the greeting on
// sign-in. Short and grounded in the persona's signal — echoes the
// context paragraph they'll see on the storefront welcome card.
// Falls through to a generic line for unknown personas.
const WELCOME_TAGLINES: Record<string, string> = {
  marco: 'Your thread is still warm — linen and oat tones await.',
  anna: 'Gifts, wrapped and waiting where you left them.',
  theo: 'Quiet pieces, kept ready — ceramics and stoneware wait.',
  fresh: 'The floor is yours — tell Pellier what catches your eye.',
}

function welcomeTagFor(personaId: string): string {
  return (
    WELCOME_TAGLINES[personaId] ??
    'The boutique remembers. Pick up where you left off.'
  )
}

export default function PersonaTransitionOverlay() {
  const { lastTransition, clearTransition } = usePersona()

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
            initial={{ opacity: 0, scale: 0.96, y: 14 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -6 }}
            transition={{ type: 'spring', stiffness: 240, damping: 26 }}
            style={{
              maxWidth: lastTransition.kind === 'sign-in' ? 460 : 380,
              width: '92vw',
            }}
          >
            <div
              className="text-center"
              style={{
                background: 'var(--cream-1)',
                border: '1px solid var(--rule-1)',
                borderRadius: 18,
                boxShadow: '0 24px 80px -16px rgba(31, 20, 16, 0.35)',
                padding:
                  lastTransition.kind === 'sign-in' ? '36px 40px 32px' : '28px 36px 24px',
              }}
            >
              {/* Mono eyebrow — same register as the welcome card */}
              <div
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  letterSpacing: '0.24em',
                  textTransform: 'uppercase',
                  color: 'var(--red-1)',
                  fontWeight: 500,
                  marginBottom: 18,
                }}
              >
                <span aria-hidden>●</span>&nbsp;&nbsp;
                {lastTransition.kind === 'sign-in'
                  ? 'Signed in'
                  : 'Signed out'}
                &nbsp;&nbsp;<span aria-hidden>●</span>
              </div>

              {/* Animated check / dash. Sign-in is a red-1 outlined
                  circle with a check; sign-out is a thinner ink ring
                  with a long-dash — less celebratory. */}
              <motion.div
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.15, type: 'spring', stiffness: 220 }}
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: '50%',
                  margin: '0 auto 14px',
                  background:
                    lastTransition.kind === 'sign-in'
                      ? 'var(--red-1)'
                      : 'transparent',
                  border:
                    lastTransition.kind === 'sign-in'
                      ? 'none'
                      : '1px solid var(--ink-3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {lastTransition.kind === 'sign-in' ? (
                  <Check
                    className="h-5 w-5"
                    style={{ color: 'var(--cream-1)', strokeWidth: 2.5 }}
                  />
                ) : (
                  <span
                    aria-hidden
                    style={{
                      width: 16,
                      height: 1,
                      background: 'var(--ink-3)',
                      display: 'block',
                    }}
                  />
                )}
              </motion.div>

              {/* Italic Fraunces greeting — matches the storefront's
                  editorial voice. */}
              <h2
                style={{
                  fontFamily: 'var(--serif)',
                  fontStyle: 'italic',
                  fontWeight: 400,
                  fontSize: lastTransition.kind === 'sign-in' ? 30 : 24,
                  lineHeight: 1.1,
                  letterSpacing: '-0.01em',
                  color: 'var(--ink-1)',
                  margin: 0,
                }}
              >
                {lastTransition.kind === 'sign-in' ? (
                  <>
                    Welcome back,{' '}
                    {lastTransition.persona.display_name.split(' ')[0]}.
                  </>
                ) : (
                  <>
                    See you soon,{' '}
                    {lastTransition.persona.display_name.split(' ')[0]}.
                  </>
                )}
              </h2>

              {/* Persona-specific tag — sign-in only. */}
              {lastTransition.kind === 'sign-in' && (
                <p
                  style={{
                    fontFamily: 'var(--serif)',
                    fontStyle: 'italic',
                    fontWeight: 600,
                    fontSize: 15,
                    lineHeight: 1.55,
                    letterSpacing: '-0.005em',
                    color: 'var(--ink-3)',
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
    </AnimatePresence>,
    document.body,
  )
}
