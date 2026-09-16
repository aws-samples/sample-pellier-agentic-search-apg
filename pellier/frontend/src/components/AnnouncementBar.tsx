/**
 * AnnouncementBar — storefront service strip above the sticky header.
 *
 * Cycles through editorial house notes every 5 seconds with a
 * smooth vertical crossfade. Each line reads like a concierge aside —
 * the agent quietly surfacing what it noticed while watching the floor.
 *
 * A pulse dot on the left, a small-caps-style verb (THE HOUSE EDIT /
 * GIFT SERVICE / SERVICE) in sans semibold + wide tracking, and body copy
 * in cream. Pellier keeps this retail-facing; Pellier Observatory carries the
 * proof and trace vocabulary.
 *
 * Copy lives in copy.ts. It intentionally avoids mutable inventory and
 * verification claims; those belong on a live evidence-bearing surface.
 */
import { useState, useEffect } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { EDITORIAL_FLOOR_NOTES } from '../copy'
import { cssVar as c } from '../design/cssVars'

const MONO_STACK = 'var(--mono)'

/* The strip is espresso, so it takes the burgundy raised for dark grounds.
   `--accent` here measured 1.61:1 against the bar and neither the label nor
   the presence dot could be read. */
const ON_DARK_ACCENT = 'var(--pellier-burgundy-on-dark)'

const CYCLE_MS = 5000

export default function AnnouncementBar() {
  const [index, setIndex] = useState(0)
  const reduceMotion = useReducedMotion()
  const finding = EDITORIAL_FLOOR_NOTES[index]

  useEffect(() => {
    if (reduceMotion) return
    const t = setInterval(() => {
      setIndex((i) => (i + 1) % EDITORIAL_FLOOR_NOTES.length)
    }, CYCLE_MS)
    return () => clearInterval(t)
  }, [reduceMotion])

  return (
    <div
      role="region"
      aria-label="Storefront announcements"
      data-testid="announcement-bar"
      className="w-full relative overflow-hidden"
      style={{
        background: c.ink,
        color: c.bg,
        fontFamily: 'var(--sans)',
        fontSize: '12.5px',
        letterSpacing: '0.04em',
        lineHeight: 1.2,
        padding: '0 24px',
        height: 44,
        fontWeight: 400,
      }}
    >
      <style>{`
        @keyframes pelliers-floor-pulse {
          0% { transform: scale(0.6); opacity: 0.9; }
          100% { transform: scale(1.8); opacity: 0; }
        }
      `}</style>

      <AnimatePresence mode="wait">
        <motion.span
          key={index}
          className="absolute inset-0 flex items-center justify-center"
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: -8 }}
          transition={{ duration: reduceMotion ? 0 : 0.35, ease: 'easeOut' }}
          style={{ padding: '0 60px' }}
        >
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 10,
              maxWidth: '100%',
            }}
          >
            {/* Pulse dot — agent presence cue, anchored to the copy so it
                never floats orphaned at the bar's edge on wide viewports. */}
            <span
              aria-hidden="true"
              data-testid="announcement-pulse"
              style={{
                position: 'relative',
                width: 8,
                height: 8,
                borderRadius: 999,
                background: ON_DARK_ACCENT,
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  inset: -6,
                  borderRadius: 999,
                  background:
                    'color-mix(in srgb, var(--pellier-burgundy-on-dark) 35%, transparent)',
                  animation: reduceMotion
                    ? 'none'
                    : 'pelliers-floor-pulse 1.8s ease-out infinite',
                }}
              />
            </span>
            {finding.verb ? (
              <span
                style={{
                  fontFamily: 'var(--sans)',
                  fontStyle: 'normal',
                  fontWeight: 600,
                  fontSize: '13px',
                  letterSpacing: '0.22em',
                  textTransform: 'uppercase',
                  color: ON_DARK_ACCENT,
                  whiteSpace: 'nowrap',
                }}
              >
                {finding.verb}
              </span>
            ) : null}
            <span
              style={{
                color: c.bg,
                opacity: 0.92,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {finding.text}
            </span>
            {finding.trace ? (
              <span
                aria-hidden="true"
                style={{
                  fontFamily: MONO_STACK,
                  fontSize: '10.5px',
                  letterSpacing: '0.04em',
                  color: 'rgba(251,244,232,0.55)',
                  borderLeft: '1px solid rgba(251,244,232,0.18)',
                  paddingLeft: 12,
                  marginLeft: 4,
                  whiteSpace: 'nowrap',
                }}
              >
                {finding.trace}
              </span>
            ) : null}
          </span>
        </motion.span>
      </AnimatePresence>
    </div>
  )
}
