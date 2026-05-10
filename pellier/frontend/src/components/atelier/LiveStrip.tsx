/**
 * LiveStrip — the universal bottom band every Atelier architecture
 * page ends with.
 *
 * Structure is fixed: black header bar with pulse dot + eyebrow (left),
 * mono session metadata (right), italic Fraunces title below the
 * eyebrow. Body content renders as children — this is where each page
 * diverges (routing decision rows, STM/LTM cells, tool-call lines,
 * waterfall bar, etc.).
 *
 * When a page renders stub data, pass a ``stubCaption`` string; it
 * appears above the body in mono ink-4 so participants understand
 * what's wired vs what's mocked. Never lie about measurement.
 */
import type { ReactNode } from 'react'

export interface LiveStripProps {
  /** Header eyebrow. Defaults to "Live · this turn". */
  eyebrow?: string
  /** Italic serif title below the eyebrow, e.g. "Queries, row by row." */
  title: ReactNode
  /** Mono session metadata on the right, e.g. "turn 04 · 11:47:32 · txn t_8a4f". */
  meta?: ReactNode
  /** Optional caption for stubbed pages — shown before body in mono ink-4. */
  stubCaption?: string
  /** Body content (page-specific — rows, cells, waterfall, etc.). */
  children: ReactNode
}

export default function LiveStrip({
  eyebrow = 'Live · this turn',
  title,
  meta,
  stubCaption,
  children,
}: LiveStripProps) {
  return (
    <section className="at-live">
      <div className="at-live-head">
        <div className="at-live-head-left">
          <div className="at-live-eyebrow">
            <span className="at-live-pulse" aria-hidden /> {eyebrow}
          </div>
          <div className="at-live-title">{title}</div>
        </div>
        {meta && <div className="at-live-meta">{meta}</div>}
      </div>
      {stubCaption && (
        <p className="at-live-stub-caption">{stubCaption}</p>
      )}
      <div className="at-live-body">{children}</div>
    </section>
  )
}
