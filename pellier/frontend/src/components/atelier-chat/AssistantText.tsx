/**
 * AssistantText — direct ink text on cream with inline citations.
 *
 * No bubble. 14px text, line-height 1.7, 2px left padding so it reads
 * as a flowing paragraph rather than a packaged message.
 *
 * Citation infrastructure ships here: citations are rendered as
 * terracotta pills on cream-warm (font-mono, "trace 7" style) that
 * emit an ``onCitationClick(ref)`` when clicked. The content of the
 * pill is the ``ref`` (e.g. "trace 7"). The current synthesis system
 * prompt does not yet emit citations — see
 * ``docs/backlog.md`` for the follow-up task; the pills
 * appear only when the LLM starts emitting inline citation markers.
 *
 * ``citations`` is expected in the shape [{k, ref}] from the
 * WorkshopResponseEvent contract. ``k`` is the source tag the LLM
 * used (e.g. "beans.b_colombia_huila"); ``ref`` is what renders on
 * the pill.
 */

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'
const CREAM_WARM = '#f5e8d3'

export interface AssistantCitation {
  k: string
  ref: string
}

export interface AssistantTextProps {
  text: string
  citations?: AssistantCitation[]
  /** Called with the citation's ``ref`` (e.g. "trace 7") on click. */
  onCitationClick?: (ref: string) => void
}

export default function AssistantText({
  text,
  citations,
  onCitationClick,
}: AssistantTextProps) {
  const hasCitations = !!citations && citations.length > 0
  // Build a lookup so inline [trace N] markers can resolve to citation data.
  const citationByRef = new Map(
    (citations ?? []).map((c) => [c.ref, c]),
  )

  // Split text on [trace N] markers for inline rendering.
  // If no markers found, falls back to trailing pills.
  const TRACE_RE = /\[trace \d+\]/g
  const hasInlineMarkers = TRACE_RE.test(text)

  function renderLineWithCitations(line: string, lineIdx: number) {
    if (!hasInlineMarkers) {
      return <p key={lineIdx} className="m-0 mb-2 last:mb-0">{line}</p>
    }
    const parts = line.split(/(\[trace \d+\])/)
    return (
      <p key={lineIdx} className="m-0 mb-2 last:mb-0">
        {parts.map((part, i) => {
          const match = part.match(/^\[trace (\d+)\]$/)
          if (match) {
            const ref = `trace ${match[1]}`
            const c = citationByRef.get(ref)
            return (
              <button
                key={i}
                type="button"
                data-testid={`citation-pill-${ref}`}
                onClick={() => onCitationClick?.(ref)}
                className="font-mono text-[10px] px-[7px] py-[1px] rounded-full transition-opacity hover:opacity-80 mx-1 align-[2px]"
                style={{ background: CREAM_WARM, color: ACCENT }}
                title={c?.k ? `Source: ${c.k}` : undefined}
              >
                {ref}
              </button>
            )
          }
          return <span key={i}>{part}</span>
        })}
      </p>
    )
  }

  return (
    <div
      data-testid="assistant-text"
      className="mb-4 text-[15px] leading-[1.7]"
      style={{ color: INK, paddingLeft: 2, letterSpacing: '-0.003em' }}
    >
      {text.split('\n').map((line, i) => renderLineWithCitations(line, i))}
      {/* Trailing pills fallback — shown when citations exist but no
          inline [trace N] markers were found in the text. */}
      {hasCitations && !hasInlineMarkers && (
        <div
          className="flex flex-wrap gap-1.5 mt-2"
          data-testid="assistant-text-citations"
        >
          {citations!.map((c, i) => (
            <button
              key={`${c.ref}-${i}`}
              type="button"
              data-testid={`citation-pill-${c.ref}`}
              onClick={() => onCitationClick?.(c.ref)}
              className="font-mono text-[10px] px-[7px] py-[1px] rounded-full transition-opacity hover:opacity-80"
              style={{ background: CREAM_WARM, color: ACCENT, verticalAlign: 2 }}
              title={c.k ? `Source: ${c.k}` : undefined}
            >
              {c.ref}
            </button>
          ))}
          <span className="text-[10px] italic" style={{ color: INK_SOFT }}>
            click to scroll to the source panel
          </span>
        </div>
      )}
    </div>
  )
}
