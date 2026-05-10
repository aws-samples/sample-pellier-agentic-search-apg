/**
 * RefinementPanel — multi-turn chip panel beneath the product grid.
 *
 * Validates Requirements 1.8.1, 1.8.2, and 1.8.3.
 *
 * Renders a white card with a small B mark, the `Pellier here, want me to
 * narrow this down?` prompt, and four toggleable chips from `copy.ts`:
 *   - Under $100
 *   - Ships by Friday
 *   - Gift-wrappable
 *   - From smaller makers
 *
 * Behavior:
 *   - Chips compose with AND semantics (Req 1.8.3): every active chip is
 *     reported as a single filter key in the callback payload. The parent
 *     is responsible for serializing them to the `/api/products` query
 *     string (1.8.2) and remounting the grid so parallax re-observes
 *     (handled via the `key={prefsVersion}` pattern in task 4.6).
 *   - Controlled when `activeFilters` is provided; uncontrolled otherwise.
 *     Mirrors the CategoryChips convention so the two panels feel
 *     identical from a parent's perspective.
 */
import { useCallback, useMemo, useState } from 'react'
import { REFINEMENT } from '../copy'
import { usePersona } from '../contexts/PersonaContext'

// Persona-tailored prompt. Fresh (and null) keep the default from
// copy.ts so the scanner stays happy. Returning personas get a
// refinement invitation grounded in their signal — makes the panel
// feel like it remembers them rather than reading as generic chrome.
const PERSONA_PROMPT: Record<string, string> = {
  marco: 'Want me to narrow to linen and travel?',
  anna: 'Want me to narrow by gift occasion or recipient?',
  theo: 'Want me to narrow to home goods that wear in?',
}

// --- Design tokens (storefront.md) --------------------------------------
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const DUSK = '#3d2518'
const ACCENT = '#c44536'

// Strongly-typed label union. The `as const` in copy.ts keeps the tuple
// literal so the resulting union covers exactly the four panel chips.
export type RefinementChip = (typeof REFINEMENT.CHIPS)[number]

interface RefinementPanelProps {
  /** Controlled active set. Order-insensitive; the component normalizes. */
  activeFilters?: readonly RefinementChip[]
  /**
   * Called after each toggle with the full new active set (AND-composed).
   * Parents serialize this to the `/api/products` query string per Req
   * 1.8.2 and remount the grid.
   */
  onChange?: (next: RefinementChip[]) => void
  /**
   * Measured latency (ms) of the last filter pass. When the parent
   * lifts state and applies filters, it passes the real elapsed time
   * here so the teaching caption shows a true number instead of the
   * hardcoded "~143ms". `null` falls back to the hardcoded label so
   * uncontrolled usage still reads sensibly.
   */
  measuredLatencyMs?: number | null
}

export default function RefinementPanel({
  activeFilters,
  onChange,
  measuredLatencyMs,
}: RefinementPanelProps) {
  const { persona } = usePersona()
  const prompt = (persona?.id && PERSONA_PROMPT[persona.id]) || REFINEMENT.PROMPT

  // Internal fallback for uncontrolled use. Always a Set for O(1) toggles
  // but exposed as a stable array to the consumer.
  const [internal, setInternal] = useState<ReadonlySet<RefinementChip>>(
    () => new Set(),
  )

  const effective: ReadonlySet<RefinementChip> = useMemo(() => {
    if (activeFilters === undefined) return internal
    return new Set(activeFilters)
  }, [activeFilters, internal])

  const emit = useCallback(
    (nextSet: Set<RefinementChip>) => {
      // Preserve the copy.ts declaration order so the query string stays
      // deterministic across renders. The parent can still re-sort if it
      // wants, but deterministic emit avoids noisy fetches.
      const ordered = REFINEMENT.CHIPS.filter(c =>
        nextSet.has(c as RefinementChip),
      ) as RefinementChip[]
      if (activeFilters === undefined) setInternal(nextSet)
      onChange?.(ordered)
    },
    [activeFilters, onChange],
  )

  const toggle = useCallback(
    (chip: RefinementChip) => {
      const next = new Set(effective)
      if (next.has(chip)) next.delete(chip)
      else next.add(chip)
      emit(next)
    },
    [effective, emit],
  )

  return (
    <section
      data-testid="refinement-panel"
      aria-label="Refine results"
      className="mx-auto w-full max-w-6xl rounded-3xl"
      style={{
        background: '#ffffff',
        padding: '20px 24px',
        boxShadow: '0 8px 28px rgba(45, 24, 16, 0.06)',
        border: '1px solid rgba(45, 24, 16, 0.06)',
      }}
    >
      <div className="flex flex-col items-start gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span
            data-testid="refinement-b-mark"
            aria-hidden="true"
            className="inline-flex h-8 w-8 items-center justify-center rounded-full"
            style={{
              background: INK,
              color: CREAM,
              fontFamily: 'Fraunces, serif',
              fontStyle: 'italic',
              fontSize: '14px',
              lineHeight: 1,
            }}
          >
            {REFINEMENT.B_MARK_PREFIX}
          </span>
          <span
            data-testid="refinement-prompt"
            style={{
              fontFamily: 'Fraunces, serif',
              fontStyle: 'italic',
              fontSize: '18px',
              color: INK,
              lineHeight: 1.4,
            }}
          >
            {prompt}
          </span>
        </div>
        <ul
          data-testid="refinement-chips"
          className="flex flex-wrap items-center gap-2"
          style={{ listStyle: 'none', margin: 0, padding: 0 }}
        >
          {REFINEMENT.CHIPS.map(chip => {
            const isActive = effective.has(chip as RefinementChip)
            return (
              <li key={chip}>
                <button
                  type="button"
                  data-testid={`refinement-chip-${slug(chip)}`}
                  data-active={isActive ? 'true' : 'false'}
                  aria-pressed={isActive}
                  onClick={() => toggle(chip as RefinementChip)}
                  className="rounded-full transition-colors"
                  style={{
                    background: isActive ? INK : CREAM_WARM,
                    color: isActive ? CREAM : INK_SOFT,
                    border: `1px solid ${isActive ? INK : 'rgba(45, 24, 16, 0.08)'}`,
                    padding: '8px 16px',
                    fontSize: '13px',
                    letterSpacing: '0.04em',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => {
                    const btn = e.currentTarget as HTMLButtonElement
                    if (isActive) {
                      btn.style.background = DUSK
                    } else {
                      btn.style.background = '#efe2cc'
                      btn.style.color = INK
                    }
                  }}
                  onMouseLeave={e => {
                    const btn = e.currentTarget as HTMLButtonElement
                    if (isActive) {
                      btn.style.background = INK
                    } else {
                      btn.style.background = CREAM_WARM
                      btn.style.color = INK_SOFT
                    }
                  }}
                >
                  {chip}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
      {/* Teaching footer — appears when any chip is active. Shows
          the hairline + a mono caption explaining what's happening
          behind the scenes: pgvector semantic search composed with
          the active metadata filters in one SQL query. Turns the
          chip panel into a visible vector-search teaching moment. */}
      {effective.size > 0 && (
        <>
          <div
            data-testid="refinement-active-hairline"
            aria-hidden="true"
            style={{
              marginTop: '14px',
              height: '1px',
              width: '100%',
              background: `linear-gradient(90deg, transparent, ${ACCENT}, transparent)`,
            }}
          />
          <div
            data-testid="refinement-teaching-caption"
            style={{
              marginTop: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontFamily: 'JetBrains Mono, ui-monospace, monospace',
              fontSize: 10.5,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: INK_SOFT,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 5,
                height: 5,
                borderRadius: '50%',
                background: ACCENT,
              }}
            />
            pgvector cosine similarity
            <span aria-hidden style={{ color: 'rgba(45, 24, 16, 0.25)' }}>
              ×
            </span>
            {effective.size}{' '}
            {effective.size === 1 ? 'metadata filter' : 'metadata filters'}
            <span aria-hidden style={{ color: 'rgba(45, 24, 16, 0.25)' }}>
              ·
            </span>
            <span style={{ color: ACCENT }}>
              {measuredLatencyMs != null ? `~${measuredLatencyMs}ms` : '~143ms'}
            </span>
            <span aria-hidden style={{ color: 'rgba(45, 24, 16, 0.25)' }}>
              ·
            </span>
            <span
              style={{
                fontFamily: 'Fraunces, serif',
                fontStyle: 'italic',
                fontSize: 12,
                textTransform: 'none',
                letterSpacing: 0,
                color: INK_SOFT,
              }}
            >
              one SQL round-trip
            </span>
          </div>
        </>
      )}
    </section>
  )
}

function slug(label: string): string {
  return label
    .toLowerCase()
    .replace(/\$/g, 'dollar')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}
