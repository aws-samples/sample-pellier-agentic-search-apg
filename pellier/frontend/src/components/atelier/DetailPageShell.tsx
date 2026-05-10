/**
 * DetailPageShell — the outer frame every Atelier architecture page shares.
 *
 * Renders breadcrumb → title → subtitle → meta strip, then the page
 * body as children. The Skills page is the visual contract: same
 * crumb tracking, same Fraunces 44px italic-capable title, same
 * small-caps meta labels in burgundy.
 *
 * Usage:
 *
 *   <DetailPageShell
 *     crumb={['Atelier', 'Architecture', 'Memory']}
 *     title={<>Memory, <em>two-tiered.</em></>}
 *     subtitle="Short-term holds the conversation. Long-term holds everything else worth remembering."
 *     meta={[
 *       { label: 'STM size', value: '12 turns' },
 *       { label: 'LTM facts', value: '1,247' },
 *     ]}
 *   >
 *     ...page body...
 *   </DetailPageShell>
 */
import type { ReactNode } from 'react'
import { useState } from 'react'
import { usePersona } from '../../contexts/PersonaContext'
import PersonaModal from '../PersonaModal'
import '../../styles/atelier-shared.css'

export interface MetaEntry {
  label: string
  value: ReactNode
}

export interface DetailPageShellProps {
  /** Breadcrumb segments. The last one is styled burgundy (the current page). */
  crumb: string[]
  /** Page title — may include ``<em>`` markup via ReactNode. */
  title: ReactNode
  /** Italic serif subtitle below the title. */
  subtitle?: ReactNode
  /** 3–5 key/value pairs for the meta strip; labels render in burgundy small-caps. */
  meta?: MetaEntry[]
  /** The page body — sections, frames, live strip at the end. */
  children: ReactNode
}

export default function DetailPageShell({
  crumb,
  title,
  subtitle,
  meta,
  children,
}: DetailPageShellProps) {
  const { persona } = usePersona()
  const [modalOpen, setModalOpen] = useState(false)

  return (
    <div className="at-page">
      <div className="at-crumb" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
          {crumb.map((segment, i) => {
            const isLast = i === crumb.length - 1
            return (
              <span key={`${segment}-${i}`}>
                {i > 0 && <span className="at-sep" aria-hidden>·</span>}{' '}
                <span className={isLast ? 'at-here' : ''}>{segment}</span>
              </span>
            )
          })}
        </div>
        <PersonaIndicator persona={persona} onClick={() => setModalOpen(true)} />
      </div>

      <div>
        <h1 className="at-title">{title}</h1>
        {subtitle && <p className="at-sub">{subtitle}</p>}
        {meta && meta.length > 0 && (
          <div className="at-meta">
            {meta.map((entry, i) => (
              <div key={`${entry.label}-${i}`}>
                <span className="at-meta-label">{entry.label}</span>
                {entry.value}
              </div>
            ))}
          </div>
        )}
      </div>

      {children}

      <PersonaModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}

/**
 * PersonaIndicator — the small "· AS Marco" pill in the breadcrumb row.
 * Three states: active persona (espresso avatar + name), fresh visitor
 * (dashed avatar + lighter name), no persona (dashed + "no persona").
 */
function PersonaIndicator({
  persona,
  onClick,
}: {
  persona: import('../../contexts/PersonaContext').PersonaSnapshot | null
  onClick: () => void
}) {
  const isFresh = persona?.id === 'fresh'
  const hasPersona = persona !== null
  const name = persona?.display_name ?? 'no persona'
  const initial = persona?.avatar_initial ?? '·'
  const avatarBg = hasPersona && !isFresh ? persona.avatar_color : 'transparent'
  const avatarColor = hasPersona && !isFresh ? 'var(--cream-1)' : 'var(--ink-3)'
  const avatarBorder =
    !hasPersona || isFresh
      ? '1px dashed var(--rule-3, rgba(31,20,16,0.28))'
      : 'none'
  const nameColor = hasPersona && !isFresh ? 'var(--ink-1)' : 'var(--ink-4)'

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="persona-indicator"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        padding: '4px 10px 4px 4px',
        background: 'var(--cream-2)',
        border: '1px solid var(--rule-1)',
        borderRadius: 100,
        cursor: 'pointer',
        fontFamily: 'var(--mono)',
        fontSize: 10,
        color: 'var(--ink-3)',
        letterSpacing: '0.1em',
      }}
    >
      <span style={{ color: 'var(--ink-4)', fontWeight: 500 }}>· AS</span>
      <span
        className="flex items-center justify-center rounded-full"
        style={{
          width: 20,
          height: 20,
          background: avatarBg,
          color: avatarColor,
          border: avatarBorder,
          fontFamily: 'var(--serif)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: 11,
        }}
      >
        {initial}
      </span>
      <span
        style={{
          color: nameColor,
          fontFamily: 'var(--serif)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: 12.5,
        }}
      >
        {name}
      </span>
    </button>
  )
}
