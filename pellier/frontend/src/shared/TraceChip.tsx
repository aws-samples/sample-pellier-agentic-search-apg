/**
 * TraceChip — a small mono pill naming the tool/signal that produced
 * a result.
 *
 * The same atom appears in Pellier (under product cards, in the
 * Live Floor Strip, on the Memory Handoff card) and on the Observatory
 * (Tools surface, Sessions, Observatory). Importing both surfaces
 * from this single file is the cohesion guarantee — when the visual
 * treatment evolves, every place that names a tool updates together.
 *
 * Visual: warm tint + 1px accent border, mono label at 11px with slight
 * tracking for readable dot-syntax. Optional `duration` renders a faint
 * right-aligned mono timestamp ("· 2.1s ago"). Optional `linkToObservatory`
 * wraps the chip in an anchor that deep-links to the Observatory route that
 * explains this concept (the "how this works" handoff).
 */
import React from 'react'
import { lookupVocab } from './agentVocabulary'
import { routePath } from '../utils/assetPath'

export interface TraceChipProps {
  /** Tool name, dot-separated. e.g. "memory.recall", "inventory.live". */
  tool: string
  /** Optional trailing duration string ("2.1s ago", "12s ago"). */
  duration?: string
  /**
   * When true, wraps the chip in an anchor tag pointing to the
   * Observatory route that explains this tool. Lets shoppers click
   * any trace and land on the developer-facing explainer for it.
   */
  linkToObservatory?: boolean
  /** Visual variant. `solid` is the default technical treatment;
   *  `ghost` is a softer fill suitable for dark surfaces, and
   *  `provenance` is the shopper-facing Pellier label treatment. */
  variant?: 'solid' | 'ghost' | 'provenance'
  /** Label display. `tool` preserves the raw trace, `label` uses the
   *  attendee-friendly vocabulary label while keeping the raw trace in
   *  the tooltip and test id. */
  labelMode?: 'tool' | 'label' | 'signal'
  /** Compact mode shrinks padding for dense tables. */
  compact?: boolean
}

function withPellierTraceContext(path: string, tool: string): string {
  const [pathAndSearch, hash] = path.split('#')
  const separator = pathAndSearch.includes('?') ? '&' : '?'
  const params = new URLSearchParams({
    from: 'pellier',
    trace: tool,
  })
  return `${pathAndSearch}${separator}${params.toString()}${hash ? `#${hash}` : ''}`
}

export const TraceChip: React.FC<TraceChipProps> = ({
  tool,
  duration,
  linkToObservatory = false,
  variant = 'solid',
  labelMode = 'tool',
  compact = false,
}) => {
  const vocab = lookupVocab(tool)
  const isProvenance = variant === 'provenance'
  const accent = 'var(--trace-accent, var(--accent))'
  // `signal` prints the part after the separator (the catalog tag itself),
  // keeping the canonical prefix for vocabulary lookup while sparing the
  // shopper the internal signal name.
  const label =
    labelMode === 'label'
      ? vocab.label
      : labelMode === 'signal'
        ? tool.split(' · ').slice(1).join(' · ') || tool
        : tool

  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: isProvenance ? 5 : 6,
    fontFamily: 'var(--mono)',
    fontSize: isProvenance ? 10.5 : 11,
    fontWeight: isProvenance ? 600 : 500,
    letterSpacing: isProvenance ? '0.08em' : '0.05em',
    fontFeatureSettings: "'calt' 1, 'liga' 1",
    color: isProvenance
      ? `color-mix(in srgb, ${accent} 88%, var(--ink))`
      : 'var(--accent)',
    background:
      isProvenance
        ? `color-mix(in srgb, ${accent} 7%, var(--cream-warm))`
        : variant === 'ghost'
        ? 'color-mix(in srgb, var(--accent) 5%, transparent)'
        : 'color-mix(in srgb, var(--accent) 9%, var(--cream-warm))',
    border: isProvenance
      ? `1px solid color-mix(in srgb, ${accent} 18%, transparent)`
      : '1px solid color-mix(in srgb, var(--accent) 22%, transparent)',
    borderRadius: 999,
    padding: isProvenance
      ? compact ? '4px 8px' : '5px 11px'
      : compact ? '4px 8px' : '5px 10px',
    whiteSpace: 'nowrap',
    textDecoration: 'none',
    cursor: linkToObservatory ? 'pointer' : 'default',
    transition: 'background 0.15s, border-color 0.15s',
  }

  const content = (
    <>
      {isProvenance ? (
        <span
          aria-hidden="true"
          style={{
            width: 5,
            height: 5,
            borderRadius: 999,
            background: accent,
            opacity: 0.78,
            flexShrink: 0,
          }}
        />
      ) : null}
      <span>{label}</span>
      {duration ? (
        <span style={{ color: 'color-mix(in srgb, var(--accent) 48%, var(--ink))' }}>
          · {duration}
        </span>
      ) : null}
    </>
  )

  if (linkToObservatory) {
    return (
      <a
        href={routePath(withPellierTraceContext(vocab.observatoryPath, tool))}
        title={`${vocab.label}: ${vocab.description}`}
        data-testid={`trace-chip-${tool}`}
        style={baseStyle}
        onMouseEnter={(e) => {
          e.currentTarget.style.background =
            isProvenance
              ? `color-mix(in srgb, ${accent} 12%, var(--cream-warm))`
              : 'color-mix(in srgb, var(--accent) 14%, var(--cream-warm))'
          e.currentTarget.style.borderColor =
            isProvenance
              ? `color-mix(in srgb, ${accent} 32%, transparent)`
              : 'color-mix(in srgb, var(--accent) 38%, transparent)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background =
            isProvenance
              ? `color-mix(in srgb, ${accent} 7%, var(--cream-warm))`
              : variant === 'ghost'
              ? 'color-mix(in srgb, var(--accent) 5%, transparent)'
              : 'color-mix(in srgb, var(--accent) 9%, var(--cream-warm))'
          e.currentTarget.style.borderColor =
            isProvenance
              ? `color-mix(in srgb, ${accent} 18%, transparent)`
              : 'color-mix(in srgb, var(--accent) 22%, transparent)'
        }}
      >
        {content}
      </a>
    )
  }

  return (
    <span
      title={`${vocab.label}: ${vocab.description}`}
      data-testid={`trace-chip-${tool}`}
      style={baseStyle}
    >
      {content}
    </span>
  )
}
