/**
 * PersonaModal — the shared persona switcher.
 *
 * One component, two entry points: the storefront header pill and the
 * Observatory breadcrumb indicator both open this same modal. Styling lives
 * in src/styles/persona-modal.css.
 *
 * Three visual persona cards as buttons. The active persona is explicit and
 * every close and account state is shared by Storefront and Observatory.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, Check, X } from 'lucide-react'
import { usePersona, type PersonaListItem } from '../contexts/PersonaContext'
import { SCENARIO } from '../copy'
import { getPersonaModalPortrait } from '../data/personaPhotos'
import { useFocusTrap } from '../shared/useFocusTrap'
import '../styles/persona-modal.css'

interface PersonaModalProps {
  open: boolean
  onClose: () => void
  /** A conversation handoff stays open as the chosen scenario becomes active. */
  closeOnSelect?: boolean
}

const PERSONA_MODAL_EASE: [number, number, number, number] = [
  0.23, 1, 0.32, 1,
]

export default function PersonaModal({ open, onClose, closeOnSelect = true }: PersonaModalProps) {
  const { persona, switchPersona, signOut, switching, switchError } = usePersona()
  const [personas, setPersonas] = useState<PersonaListItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [retryVersion, setRetryVersion] = useState(0)
  const [loading, setLoading] = useState(false)
  const reduceMotion = Boolean(useReducedMotion())
  const dialogRef = useRef<HTMLDivElement | null>(null)

  // Escape closes, Tab stays inside, and focus returns to the pill that
  // opened the chooser.
  useFocusTrap({ containerRef: dialogRef, active: open, onClose })

  // Fetch persona list on first open
  useEffect(() => {
    if (!open || personas.length > 0) return
    setLoading(true)
    setError(null)
    fetch('/api/observatory/personas')
      .then((r) => {
        if (!r.ok) throw new Error('We couldn’t load the profiles. Please try again.')
        return r.json()
      })
      .then((data) => {
        const list = Array.isArray(data) ? data : []
        const withoutFresh = list.filter((p: { id: string }) => p.id !== 'fresh')
        setPersonas(withoutFresh)
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : 'Live personas unavailable.'),
      )
      .finally(() => setLoading(false))
  }, [open, personas.length, retryVersion])

  const handleSelect = useCallback(
    async (id: string) => {
      if (await switchPersona(id) && closeOnSelect) onClose()
    },
    [switchPersona, onClose, closeOnSelect],
  )

  const handleSignOut = useCallback(() => {
    signOut()
    onClose()
  }, [signOut, onClose])

  return createPortal(
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          className="pm-backdrop"
          data-testid="persona-modal-backdrop"
          initial={false}
          animate={{ opacity: 1 }}
          exit={{ opacity: 1 }}
          transition={{ duration: 0 }}
          onClick={(e) => {
            if (e.target === e.currentTarget) onClose()
          }}
        >
          <motion.div
            ref={dialogRef}
            className="pm-card"
            data-testid="persona-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="persona-modal-title"
            initial={
              reduceMotion
                ? false
                : { transform: 'translateY(6px) scale(0.97)' }
            }
            animate={{ transform: 'translateY(0) scale(1)' }}
            exit={
              reduceMotion
                ? undefined
                : {
                    transform: 'translateY(6px) scale(0.97)',
                    transition: { duration: 0.18, ease: PERSONA_MODAL_EASE },
                  }
            }
            transition={{ duration: 0.24, ease: PERSONA_MODAL_EASE }}
            style={{ transformOrigin: 'center' }}
          >
            <div className="pm-head">
              <div>
                <div className="pm-eyebrow">Client perspective</div>
                <h2 id="persona-modal-title" className="pm-title">
                  {SCENARIO.CHOOSE_TITLE}
                </h2>
                <p className="pm-sub">
                  Explore each profile’s history and preferences. Account
                  access uses a separate sign-in.
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                data-testid="persona-modal-close"
                className="pm-close"
                aria-label="Close"
              >
                <X size={17} aria-hidden="true" />
              </button>
            </div>

            <div className="pm-list">
              {loading ? (
                <div className="pm-loading" role="status">
                  <span />
                  <span />
                  <span />
                  <p>Loading live client profiles</p>
                </div>
              ) : null}
              {error || switchError ? (
                <div className="pellier-recovery" role="alert">
                  <p>{error ?? switchError}</p>
                  {error ? <button type="button" className="pellier-retry" onClick={() => setRetryVersion(v => v + 1)}>Try again</button> : null}
                </div>
              ) : null}
              {personas.map((p) => {
                const isActive = persona?.id === p.id
                const photoUrl = getPersonaModalPortrait(p.id)
                return (
                  <button
                    key={p.id}
                    type="button"
                    disabled={switching}
                    data-testid={`persona-card-${p.id}`}
                    data-persona={p.id}
                    onClick={() => handleSelect(p.id)}
                    className={`pm-card-btn${isActive ? ' active' : ''}`}
                    aria-pressed={isActive}
                  >
                    <span className="pm-avatar" aria-hidden="true">
                      {photoUrl ? (
                        <img
                          className="pm-avatar-photo"
                          src={photoUrl}
                          width={1200}
                          height={1800}
                          alt=""
                          decoding="async"
                        />
                      ) : (
                        <span className="pm-avatar-fallback">
                          {p.avatar_initial}
                        </span>
                      )}
                    </span>

                    <span className="pm-content">
                      <span className="pm-name-row">
                        <span className="pm-name">{p.display_name}</span>
                        <span className="pm-tag">{p.role_tag}</span>
                      </span>
                      <span className="pm-blurb">{p.blurb}</span>
                      <span className="pm-meta-row">
                        <span className="pm-meta-item">
                          <span className="num">{p.stats.visits}</span> visits
                        </span>
                        <span className="pm-meta-item">
                          <span className="num">{p.stats.orders}</span> orders
                        </span>
                        <span className="pm-meta-item">
                          {p.stats.last_seen_days === null
                            ? 'New profile'
                            : `Seen ${p.stats.last_seen_days}d ago`}
                        </span>
                      </span>
                    </span>

                    <span className="pm-select" aria-hidden="true">
                      {isActive ? <Check size={16} /> : <ArrowRight size={16} />}
                    </span>
                  </button>
                )
              })}
            </div>

            {persona ? (
              <div className="pm-foot">
                <span>
                  Active profile: <strong>{persona.display_name}</strong>
                </span>
                <button
                  type="button"
                  onClick={handleSignOut}
                  data-testid="persona-sign-out"
                  className="pm-signout"
                >
                  Clear scenario
                </button>
              </div>
            ) : null}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}
