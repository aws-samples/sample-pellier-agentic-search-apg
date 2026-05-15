/**
 * TraceChip — a small mono pill naming the tool/signal that produced
 * a result.
 *
 * The same atom appears on the Boutique (under product cards, in the
 * Live Floor Strip, on the Memory Handoff card) and on the Atelier
 * (Tools surface, Sessions, Observatory). Importing both surfaces
 * from this single file is the cohesion guarantee — when the visual
 * treatment evolves, every place that names a tool updates together.
 *
 * Visual: warm tint + 1px accent border, mono label at 11px with slight
 * tracking for readable dot-syntax. Optional `duration` renders a faint
 * right-aligned mono timestamp ("· 2.1s ago"). Optional `linkToAtelier`
 * wraps the chip in an anchor that deep-links to the Atelier route that
 * explains this concept (the "how this works" handoff).
 */
import React from 'react'
import { lookupVocab } from './agentVocabulary'

export interface TraceChipProps {
  /** Tool name, dot-separated. e.g. "memory.recall", "inventory.live". */
  tool: string
  /** Optional trailing duration string ("2.1s ago", "12s ago"). */
  duration?: string
  /**
   * When true, wraps the chip in an anchor tag pointing to the
   * Atelier route that explains this tool. Lets shoppers click
   * any trace and land on the developer-facing explainer for it.
   */
  linkToAtelier?: boolean
  /** Visual variant. `solid` is the default Boutique treatment;
   *  `ghost` is a softer fill suitable for dark surfaces. */
  variant?: 'solid' | 'ghost'
  /** Compact mode shrinks padding for dense tables. */
  compact?: boolean
}

export const TraceChip: React.FC<TraceChipProps> = ({
  tool,
  duration,
  linkToAtelier = false,
  variant = 'solid',
  compact = false,
}) => {
  const vocab = lookupVocab(tool)

  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    fontFamily: 'var(--mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '0.05em',
    fontFeatureSettings: "'calt' 1, 'liga' 1",
    color: 'var(--accent)',
    background:
      variant === 'ghost'
        ? 'color-mix(in srgb, var(--accent) 5%, transparent)'
        : 'color-mix(in srgb, var(--accent) 9%, var(--cream-warm))',
    border: '1px solid color-mix(in srgb, var(--accent) 22%, transparent)',
    borderRadius: 6,
    padding: compact ? '4px 8px' : '5px 10px',
    whiteSpace: 'nowrap',
    textDecoration: 'none',
    cursor: linkToAtelier ? 'pointer' : 'default',
    transition: 'background 0.15s, border-color 0.15s',
  }

  const content = (
    <>
      <span>{tool}</span>
      {duration ? (
        <span style={{ color: 'color-mix(in srgb, var(--accent) 48%, var(--ink))' }}>
          · {duration}
        </span>
      ) : null}
    </>
  )

  if (linkToAtelier) {
    return (
      <a
        href={vocab.atelierPath}
        title={`${vocab.label} — ${vocab.description}`}
        data-testid={`trace-chip-${tool}`}
        style={baseStyle}
        onMouseEnter={(e) => {
          e.currentTarget.style.background =
            'color-mix(in srgb, var(--accent) 14%, var(--cream-warm))'
          e.currentTarget.style.borderColor =
            'color-mix(in srgb, var(--accent) 38%, transparent)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background =
            variant === 'ghost'
              ? 'color-mix(in srgb, var(--accent) 5%, transparent)'
              : 'color-mix(in srgb, var(--accent) 9%, var(--cream-warm))'
          e.currentTarget.style.borderColor =
            'color-mix(in srgb, var(--accent) 22%, transparent)'
        }}
      >
        {content}
      </a>
    )
  }

  return (
    <span
      title={`${vocab.label} — ${vocab.description}`}
      data-testid={`trace-chip-${tool}`}
      style={baseStyle}
    >
      {content}
    </span>
  )
}
