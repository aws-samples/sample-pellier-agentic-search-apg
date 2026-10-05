import { apiFetch } from '../services/apiBase'
/**
 * PersonaModal: the header's shopper switcher.
 *
 * The same choice as the home page's chooser, in a dialog: one card per demo
 * shopper, and choosing one signs in with that shopper's demo account and
 * opens their edit (`useShopperSignIn`). Choosing another shopper signs the
 * current one out first; Sign out returns to the neutral, signed-out store.
 * The shopper marked as current is the one the shopper session names, so a
 * sign-in whose edit failed to open can be chosen again to finish opening it.
 * Styling lives in src/styles/persona-modal.css.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, Check, X } from 'lucide-react'
import { usePersona, type PersonaListItem } from '../contexts/PersonaContext'
import { HERO_CONCIERGE, SHOPPER } from '../copy'
import { getPersonaModalPortrait } from '../data/personaPhotos'
import { chooserShoppers, isWorkshopShopper, useShopperSignIn } from '../hooks/useShopperSignIn'
import { useFocusTrap } from '../shared/useFocusTrap'
import '../styles/persona-modal.css'

interface PersonaModalProps {
  open: boolean
  onClose: () => void
}

const PERSONA_MODAL_EASE: [number, number, number, number] = [
  0.23, 1, 0.32, 1,
]

export default function PersonaModal({ open, onClose }: PersonaModalProps) {
  // The chooser mounts only while open, so a closed switcher holds no sign-in
  // state and reads nothing.
  return createPortal(
    <AnimatePresence initial={false}>
      {open && <ShopperChooser onClose={onClose} />}
    </AnimatePresence>,
    document.body,
  )
}

function ShopperChooser({ onClose }: { onClose: () => void }) {
  const { persona, switching, switchError } = usePersona()
  const { choose, signOut, busy, error: signInError, signedInAs } = useShopperSignIn()
  const [personas, setPersonas] = useState<PersonaListItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [retryVersion, setRetryVersion] = useState(0)
  const [loading, setLoading] = useState(false)
  const reduceMotion = Boolean(useReducedMotion())
  const dialogRef = useRef<HTMLDivElement | null>(null)

  // Escape closes, Tab stays inside, and focus returns to the pill that
  // opened the chooser.
  useFocusTrap({ containerRef: dialogRef, active: true, onClose })

  // Fetch the shoppers each time the chooser opens.
  useEffect(() => {
    if (personas.length > 0) return
    setLoading(true)
    setError(null)
    apiFetch('/api/personas')
      .then((r) => {
        if (!r.ok) throw new Error('We couldn’t load the profiles. Please try again.')
        return r.json()
      })
      .then((data) => {
        setPersonas(chooserShoppers(Array.isArray(data) ? data as PersonaListItem[] : []))
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : 'Live personas unavailable.'),
      )
      .finally(() => setLoading(false))
  }, [personas.length, retryVersion])

  const handleSelect = useCallback(
    async (id: string) => {
      if (!isWorkshopShopper(id) || (id === signedInAs && id === persona?.id)) return
      if (await choose(id)) onClose()
    },
    [choose, onClose, persona?.id, signedInAs],
  )

  const handleSignOut = useCallback(() => {
    signOut()
    onClose()
  }, [signOut, onClose])

  return (
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
            <div className="pm-eyebrow">Demo shoppers</div>
            <h2 id="persona-modal-title" className="pm-title">
              {SHOPPER.CHOOSE}
            </h2>
            <p className="pm-sub">{HERO_CONCIERGE.IDENTITY_BOUNDARY}</p>
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
          {signInError ? (
            <div className="pellier-recovery" role="alert" data-testid="persona-modal-sign-in-error">
              <p>{HERO_CONCIERGE.FAILED}</p>
            </div>
          ) : null}
          {personas.map((p) => {
            const isActive = signedInAs === p.id
            const photoUrl = getPersonaModalPortrait(p.id)
            return (
              <button
                key={p.id}
                type="button"
                disabled={switching || Boolean(busy)}
                aria-busy={busy === p.id || undefined}
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
                    <span className="pm-tag">{busy === p.id ? HERO_CONCIERGE.SIGNING_IN : p.role_tag}</span>
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

        {signedInAs ? (
          <div className="pm-foot">
            <span>
              Signed in as{' '}
              <strong>{personas.find(p => p.id === signedInAs)?.display_name ?? signedInAs}</strong>
            </span>
            <button
              type="button"
              onClick={handleSignOut}
              data-testid="persona-sign-out"
              className="pm-signout"
            >
              {SHOPPER.SIGN_OUT}
            </button>
          </div>
        ) : null}
      </motion.div>
    </motion.div>
  )
}
