/**
 * AnnouncementBar: the storefront's store notes above the sticky header.
 *
 * The notes take turns every five seconds with a short fade. A pause button
 * stops them (WCAG 2.2.2), and so does a pointer resting on the bar. With
 * reduced motion the first note stays and there is no button, because
 * nothing moves. Every note sits in the same grid cell, so the bar keeps the
 * tallest note's height and the page never shifts when a note changes. The
 * colors are the `--dl-announce-*` tokens.
 *
 * Copy lives in copy.ts. It intentionally avoids mutable inventory and
 * verification claims; those belong on a live evidence-bearing surface.
 */
import { useEffect, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { useReducedMotion } from 'motion/react'
import { ANNOUNCEMENTS, ANNOUNCEMENT_CONTROLS } from '../copy'
import '../styles/announcement-bar.css'

const CYCLE_MS = 5000

export default function AnnouncementBar() {
  const reduceMotion = Boolean(useReducedMotion())
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [hovered, setHovered] = useState(false)
  const rotates = !reduceMotion
  const turning = rotates && !paused && !hovered

  useEffect(() => {
    if (!turning) return
    const timer = window.setInterval(() => setIndex(i => (i + 1) % ANNOUNCEMENTS.length), CYCLE_MS)
    return () => window.clearInterval(timer)
  }, [turning])

  const shown = rotates ? index : 0

  return (
    <div
      role="region"
      aria-label="Storefront announcements"
      data-testid="announcement-bar"
      data-rotates={rotates ? 'true' : 'false'}
      className="pellier-announcement"
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      <div className="pellier-announcement-notes">
        {ANNOUNCEMENTS.map((note, i) => (
          <p
            key={note.VERB}
            className="pellier-announcement-note"
            data-active={i === shown ? 'true' : 'false'}
            aria-hidden={i === shown ? undefined : true}
          >
            <span className="pellier-announcement-verb">{note.VERB}</span>
            <span className="pellier-announcement-text">{note.TEXT}</span>
          </p>
        ))}
      </div>
      {rotates ? (
        <button
          type="button"
          className="pellier-announcement-pause"
          data-testid="announcement-pause"
          aria-label={paused ? ANNOUNCEMENT_CONTROLS.PLAY : ANNOUNCEMENT_CONTROLS.PAUSE}
          title={paused ? ANNOUNCEMENT_CONTROLS.PLAY : ANNOUNCEMENT_CONTROLS.PAUSE}
          onClick={() => setPaused(p => !p)}
        >
          {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
        </button>
      ) : null}
    </div>
  )
}
