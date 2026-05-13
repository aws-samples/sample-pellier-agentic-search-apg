/**
 * AnnouncementBar — Live Floor Strip above the sticky header.
 *
 * Cycles through editorial "just in" findings every 5 seconds with a
 * smooth vertical crossfade. Each line reads like a concierge aside —
 * the agent quietly surfacing what it noticed while watching the floor.
 *
 * Restyled for re:Invent: a pulse dot on the left, an italic Fraunces
 * verb (Noticing / Just spotted / Trending) leading the copy, and a
 * mono "trace" stamp on the right naming the tool that produced the
 * finding. The whole strip reads as the agent's voice — not a shipping
 * banner.
 *
 * Falls back to the static ANNOUNCEMENT copy as the first item so the
 * shipping/returns line still appears in the rotation.
 */
import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ANNOUNCEMENT } from '../copy'

const DUSK = '#3d2518'
const CREAM = '#fbf4e8'
const ACCENT = '#c44536'
const FRAUNCES_STACK = "'Fraunces', Georgia, serif"
const MONO_STACK = "'JetBrains Mono', ui-monospace, monospace"

const CYCLE_MS = 5000

interface Finding {
  /** Italic verb that leads the copy ("Noticing", "Just spotted"). */
  verb?: string
  /** Body text. */
  text: string
  /** Mono trace stamp on the right ("trace · inventory.search · 2.1s ago"). */
  trace?: string
}

const FINDINGS: Finding[] = [
  { text: ANNOUNCEMENT },
  {
    verb: 'Noticing',
    text: 'linen searches up 60% since Thursday — three new pieces just landed in the Summer Edit.',
    trace: 'trace · inventory.search · 2.1s ago',
  },
  {
    verb: 'Just spotted',
    text: 'the Pellier Linen Shirt back in all sizes after a 9-day wait.',
    trace: 'trace · inventory.watch · 28s ago',
  },
  {
    verb: 'Trending',
    text: 'Cashmere-Blend Cardigan moving 4× faster this week — 2 left in your size.',
    trace: 'trace · trend.signal · 12s ago',
  },
  {
    verb: 'Holding',
    text: 'last 2 pairs of the Leather Slide Sandal in 42 — saved for shoppers who looked twice.',
    trace: 'trace · cart.holds · 47s ago',
  },
  {
    verb: 'Pairing',
    text: 'shoppers who liked the Oxford are reaching for the Camp Shirt 73% of the time.',
    trace: 'trace · pairing.score · 1.4s ago',
  },
  {
    verb: 'Restocked',
    text: 'Ceramic Tumbler Set is back after selling out twice this month.',
    trace: 'trace · inventory.watch · 6s ago',
  },
  {
    verb: 'Watching',
    text: 'Wide-Leg Linen Trousers in Terracotta — third week running as a bestseller.',
    trace: 'trace · trend.signal · 33s ago',
  },
]

export default function AnnouncementBar() {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const t = setInterval(() => {
      setIndex((i) => (i + 1) % FINDINGS.length)
    }, CYCLE_MS)
    return () => clearInterval(t)
  }, [])

  return (
    <div
      role="region"
      aria-label="Live floor — agent observations"
      aria-live="polite"
      data-testid="announcement-bar"
      className="w-full relative overflow-hidden"
      style={{
        background: DUSK,
        color: CREAM,
        fontFamily: 'var(--sans)',
        fontSize: '12.5px',
        letterSpacing: '0.04em',
        lineHeight: 1.2,
        padding: '0 24px',
        height: 44,
        fontWeight: 400,
      }}
    >
      {/* Pulse dot — agent presence cue, anchored left of the rotating copy */}
      <span
        aria-hidden="true"
        data-testid="announcement-pulse"
        style={{
          position: 'absolute',
          left: 24,
          top: '50%',
          transform: 'translateY(-50%)',
          width: 8,
          height: 8,
          borderRadius: 999,
          background: ACCENT,
          zIndex: 1,
        }}
      >
        <style>{`
          @keyframes pelliers-floor-pulse {
            0% { transform: scale(0.6); opacity: 0.9; }
            100% { transform: scale(1.8); opacity: 0; }
          }
        `}</style>
        <span
          style={{
            position: 'absolute',
            inset: -6,
            borderRadius: 999,
            background: 'rgba(196, 69, 54, 0.35)',
            animation: 'pelliers-floor-pulse 1.8s ease-out infinite',
          }}
        />
      </span>

      <AnimatePresence mode="wait">
        <motion.span
          key={index}
          className="absolute inset-0 flex items-center justify-center"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
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
            {FINDINGS[index].verb ? (
              <span
                style={{
                  fontFamily: FRAUNCES_STACK,
                  fontStyle: 'italic',
                  color: '#f6c8a8',
                  fontWeight: 500,
                  fontSize: '14.5px',
                  letterSpacing: '-0.005em',
                  whiteSpace: 'nowrap',
                }}
              >
                {FINDINGS[index].verb}
              </span>
            ) : null}
            <span
              style={{
                color: CREAM,
                opacity: 0.92,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {FINDINGS[index].text}
            </span>
            {FINDINGS[index].trace ? (
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
                {FINDINGS[index].trace}
              </span>
            ) : null}
          </span>
        </motion.span>
      </AnimatePresence>
    </div>
  )
}
