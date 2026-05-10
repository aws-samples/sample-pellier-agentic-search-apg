/**
 * AnnouncementBar — agentic ticker strip above the sticky header.
 *
 * Cycles through editorial "just in" findings every 5 seconds with a
 * smooth vertical crossfade. Each line reads like a concierge aside —
 * the agent quietly surfacing what it noticed while watching the floor.
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

const CYCLE_MS = 5000

const FINDINGS: string[] = [
  ANNOUNCEMENT,
  'Just in \u00b7 The Pellier Linen Shirt is back in all sizes',
  'Just in \u00b7 3 new arrivals added to the Summer Edit this morning',
  'Bestseller \u00b7 Cashmere-Blend Cardigan trending 4x this week',
  'Just in \u00b7 Leather Slide Sandal down to last 2 pairs in 42',
  'Our pick \u00b7 Linen searches up 60% since last Thursday',
  'Just in \u00b7 Ceramic Tumbler Set restocked after selling out twice',
  'Our pick \u00b7 Customers who liked the Oxford also loved the Camp Shirt',
  'Bestseller \u00b7 Wide-Leg Linen Trousers in Terracotta — 3rd week running',
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
      aria-label="Site announcements"
      aria-live="polite"
      data-testid="announcement-bar"
      className="w-full text-center relative overflow-hidden"
      style={{
        background: DUSK,
        color: CREAM,
        fontFamily: 'var(--sans)',
        fontSize: '11.5px',
        letterSpacing: '0.14em',
        lineHeight: 1,
        wordSpacing: '0.08em',
        textTransform: 'uppercase',
        padding: '0 16px',
        height: 42,
        fontWeight: 500,
      }}
    >
      <AnimatePresence mode="wait">
        <motion.span
          key={index}
          className="absolute inset-0 flex items-center justify-center tracking-[0.12em]"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
        >
          {FINDINGS[index].startsWith('Just in') || FINDINGS[index].startsWith('Our pick') || FINDINGS[index].startsWith('Bestseller') ? (
            <>
              <span style={{ color: ACCENT }}>
                {FINDINGS[index].split('\u00b7')[0]}
              </span>
              <span style={{ color: CREAM, opacity: 0.5 }}>{'\u00b7'}</span>
              <span>&nbsp;{FINDINGS[index].split('\u00b7').slice(1).join('\u00b7').trim()}</span>
            </>
          ) : (
            FINDINGS[index]
          )}
        </motion.span>
      </AnimatePresence>
    </div>
  )
}
