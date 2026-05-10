/**
 * PersonaModal — the shared persona switcher.
 *
 * One component, two entry points: the storefront header pill and the
 * Atelier breadcrumb indicator both open this same modal. Structure
 * matches docs/persona-switcher.html byte-for-byte; styling lives in
 * src/styles/persona-modal.css.
 *
 * Three persona cards as buttons. Active persona gets a burgundy ring
 * + inner box-shadow. Closes via: X button, backdrop click, Escape.
 */
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { usePersona, type PersonaListItem } from '../contexts/PersonaContext'
import '../styles/persona-modal.css'

interface PersonaModalProps {
  open: boolean
  onClose: () => void
}

export default function PersonaModal({ open, onClose }: PersonaModalProps) {
  const { persona, switchPersona, signOut, switching } = usePersona()
  const [personas, setPersonas] = useState<PersonaListItem[]>([])

  // Fetch persona list on first open
  useEffect(() => {
    if (!open || personas.length > 0) return
    fetch('/api/atelier/personas')
      .then((r) => r.json())
      .then((data) => {
        const list = Array.isArray(data) ? data : []
        setPersonas(list.filter((p: { id: string }) => p.id !== 'fresh'))
      })
      .catch(() => {})
  }, [open, personas.length])

  // Escape key closes the modal
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleSelect = useCallback(
    async (id: string) => {
      await switchPersona(id)
      onClose()
    },
    [switchPersona, onClose],
  )

  const handleSignOut = useCallback(() => {
    signOut()
    onClose()
  }, [signOut, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="pm-backdrop"
      data-testid="persona-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="pm-card" data-testid="persona-modal">
        {/* Head */}
        <div className="pm-head">
          <div>
            <div className="pm-eyebrow">Sign in</div>
            <h2 className="pm-title">
              Choose a <em>persona to inhabit.</em>
            </h2>
            <p className="pm-sub">
              Three histories. The boutique shifts depending on who you are.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="persona-modal-close"
            className="pm-close"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>

        {/* List */}
        <div className="pm-list">
          {personas.map((p) => {
            const isActive = persona?.id === p.id
            const isFresh = p.id === 'fresh'
            return (
              <button
                key={p.id}
                type="button"
                disabled={switching}
                data-testid={`persona-card-${p.id}`}
                onClick={() => handleSelect(p.id)}
                className={`pm-card-btn${isActive ? ' active' : ''}`}
              >
                <span
                  className={`pm-avatar ${isFresh ? 'fresh' : p.id}`}
                  aria-hidden
                >
                  {p.avatar_initial}
                </span>

                <span className="pm-content">
                  <span className="pm-name-row">
                    <span className="pm-name">
                      <em>{p.display_name}</em>
                    </span>
                    <span className={`pm-tag${isFresh ? ' fresh' : ''}`}>
                      {p.role_tag}
                    </span>
                  </span>
                  <span className="pm-blurb">{p.blurb}</span>
                  <span className="pm-meta-row">
                    <span className="pm-meta-item">
                      visits ·{' '}
                      <span className="num">{p.stats.visits}</span>
                    </span>
                    <span className="pm-meta-item">
                      orders ·{' '}
                      <span className="num">{p.stats.orders}</span>
                    </span>
                    <span className="pm-meta-item">
                      last seen ·{' '}
                      <span className="num">
                        {p.stats.last_seen_days === null
                          ? 'never'
                          : `${p.stats.last_seen_days}d ago`}
                      </span>
                    </span>
                  </span>
                </span>

                <span className="pm-arrow" aria-hidden>
                  →
                </span>
              </button>
            )
          })}

          {persona && (
            <button
              type="button"
              onClick={handleSignOut}
              data-testid="persona-sign-out"
              className="pm-signout"
            >
              Sign out
            </button>
          )}
        </div>

        {/* Foot */}
        <div className="pm-foot">
          <div className="pm-foot-text">
            <em>Three curated identities</em> — switch any time from the header.
          </div>
          <div className="pm-foot-meta">v1.0</div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
