/**
 * AtmosphereStrip — thin operator ticker below the AtelierHero.
 *
 * Mirrors the storefront's "Live inventory · refreshed daily · curated
 * by hand" footer ticker — same grammar, same typographic register,
 * operator content. Terracotta LIVE dot + label signals "this is
 * happening right now"; the rest reads as editorial meta.
 *
 * Live values wire through the WorkshopPage's session state:
 *   - active sessions count (currently always 1 — see below)
 *   - skill count loaded into context this turn
 *   - median panel duration in current turn
 *
 * "Active sessions" is reserved for when we wire multi-session
 * tracking; for now the single-session case renders naturally (`1
 * ACTIVE SESSION` singular). That's honest shop operator language.
 */

const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'

interface AtmosphereStripProps {
  activeSessions?: number
  skillCount: number
  medianMs: number | null
}

export default function AtmosphereStrip({
  activeSessions = 1,
  skillCount,
  medianMs,
}: AtmosphereStripProps) {
  const sessionWord = activeSessions === 1 ? 'ACTIVE SESSION' : 'ACTIVE SESSIONS'
  const skillWord = skillCount === 1 ? 'SKILL LOADED' : 'SKILLS LOADED'
  const medianDisplay = medianMs === null ? '—' : `${medianMs}MS MEDIAN`
  return (
    <div
      data-testid="atmosphere-strip"
      className="py-3 flex justify-center items-center gap-3.5 flex-wrap text-[11px] font-medium uppercase"
      style={{
        borderTop: '1px solid rgba(45, 24, 16, 0.18)',
        borderBottom: '1px solid rgba(45, 24, 16, 0.18)',
        color: INK_SOFT,
        letterSpacing: '0.14em',
      }}
    >
      <span className="inline-flex items-center gap-[7px]">
        <span
          aria-hidden
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: ACCENT }}
        />
        <span style={{ color: ACCENT }}>LIVE</span>
      </span>
      <span style={{ color: INK_QUIET }} aria-hidden>
        ·
      </span>
      <span>
        {activeSessions} {sessionWord}
      </span>
      <span style={{ color: INK_QUIET }} aria-hidden>
        ·
      </span>
      <span>
        {skillCount} {skillWord}
      </span>
      <span style={{ color: INK_QUIET }} aria-hidden>
        ·
      </span>
      <span>{medianDisplay}</span>
    </div>
  )
}
