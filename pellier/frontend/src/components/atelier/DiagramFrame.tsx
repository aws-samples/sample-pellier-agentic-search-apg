/**
 * DiagramFrame — cream-elev container for inline SVG diagrams.
 *
 * Used by MCP, Tool Registry (bipartite graph), Evaluations (triangle
 * with multi-color corners), and anywhere else a page wants an SVG
 * held in a proper frame with label/meta header and optional legend.
 *
 * Prop ``legend`` renders in a bottom band — standardized across pages
 * that describe edge styles ("solid = everyday", "dashed = read-only").
 */
import type { ReactNode } from 'react'

export interface DiagramLegendItem {
  /** Small visual marker (a line, dot, or swatch). */
  marker?: ReactNode
  /** Label text — may include ``<em>`` for inline emphasis. */
  label: ReactNode
}

export interface DiagramFrameProps {
  /** Left-side mono small-caps label, e.g. "Network · this turn". */
  label?: string
  /** Right-side mono metadata, e.g. "3 nodes · 2 edges". */
  meta?: ReactNode
  /** The SVG diagram. */
  children: ReactNode
  /** Optional legend items — renders as a cream-2 strip at the bottom. */
  legend?: DiagramLegendItem[]
}

export default function DiagramFrame({
  label,
  meta,
  children,
  legend,
}: DiagramFrameProps) {
  const hasHead = Boolean(label || meta)
  return (
    <div className="at-diagram">
      {hasHead && (
        <div className="at-diagram-head">
          {label && <span className="at-diagram-label">{label}</span>}
          {meta && <span className="at-diagram-meta">{meta}</span>}
        </div>
      )}
      <div className="at-diagram-body">{children}</div>
      {legend && legend.length > 0 && (
        <div className="at-diagram-legend">
          {legend.map((item, i) => (
            <span className="at-diagram-legend-item" key={i}>
              {item.marker}
              {item.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
