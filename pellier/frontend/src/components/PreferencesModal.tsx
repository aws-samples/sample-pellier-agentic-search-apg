/**
 * PreferencesModal - Challenge 9.4b surface.
 *
 * Validates Requirement 2.6.6 (preferences modal half) and the
 * `storefront.md` "Preferences onboarding modal" spec.
 *
 * Contract (per storefront.md):
 *   - Centered cream rounded-3xl card over a glass backdrop-blur overlay.
 *   - Header: B mark + "A quick tune-up" + short explainer.
 *   - Body headline: italic "What moves you?" + subheadline.
 *   - Four preference groups, all multi-select:
 *       Group 1 Vibe       -> 6 cards with 2-word descriptors.
 *       Group 2 Colors     -> 5 pill chips with gradient swatches.
 *       Group 3 Occasions  -> 6 pill chips.
 *       Group 4 Categories -> 6 pill chips.
 *   - Selected chip visual state: Daylight ink surface + paper foreground
 *     (`var(--dl-ink)` / `var(--cream-warm)`).
 *   - Submit row: `Skip for now` secondary + `Save and see my storefront`
 *     primary.
 *   - Footer: `Preferences stored with AgentCore Memory` 10px mono with
 *     shield icon.
 *
 * Behavior on save:
 *   1. Collect the selected chip labels into a Preferences payload, mapped
 *      onto the four tag literal types (VibeTag / ColorTag / OccasionTag /
 *      CategoryTag).
 *   2. Call `useAuth().savePreferences(prefs)` which POSTs to
 *      /api/user/preferences and advances prefsVersion on success. This
 *      causes ProductGrid (mounted with key={prefsVersion}) to remount and
 *      re-fetch /api/products?personalized=true - the grid re-sort and
 *      parallax re-fire that closes the full sign-in -> prefs -> grid loop.
 *   3. Close the modal (UIContext singleton).
 *   4. The curated banner flash (AuthStateBand) is triggered automatically
 *      because `preferences` is now non-null.
 *
 * "Skip for now" closes the modal without posting anything. The user can
 * re-open the modal from the Account menu or the curated banner's
 * "Adjust preferences" link later.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { PREFERENCES_MODAL, type PreferenceGroup } from '../copy'
import { useUI } from '../contexts/UIContext'
import type {
  CategoryTag,
  ColorTag,
  OccasionTag,
  Preferences,
  VibeTag,
} from '../services/types'
import { useAuth } from '../utils/auth'
import { cssVar as c } from '../design/cssVars'

// === CHALLENGE 9.4: START ===
// --- Design tokens → Daylight via `cssVars` / bridge --------------------

const FRAUNCES_STACK = 'Fraunces, Georgia, serif'
const MONO_STACK =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'

// --- Label -> tag mappings -----------------------------------------------
// copy.ts ships human-readable labels ("Evenings out", "Warm tones") while
// the wire contract uses the lowercase tag literals (`evening`, `warm`).
// These maps are the single point of truth for the translation; any new
// label added to copy.ts must land here too or the payload type-check
// below will fail at runtime (unknown keys drop out of the final payload).
const VIBE_LABEL_TO_TAG: Record<string, VibeTag> = {
  Minimal: 'minimal',
  Bold: 'bold',
  Serene: 'serene',
  Adventurous: 'adventurous',
  Creative: 'creative',
  Classic: 'classic',
}

const COLOR_LABEL_TO_TAG: Record<string, ColorTag> = {
  'Warm tones': 'warm',
  Neutrals: 'neutral',
  Earth: 'earth',
  'Soft pastels': 'soft',
  'Deep and moody': 'moody',
}

const OCCASION_LABEL_TO_TAG: Record<string, OccasionTag> = {
  Everyday: 'everyday',
  Travel: 'travel',
  'Evenings out': 'evening',
  Outdoor: 'outdoor',
  'Slow mornings': 'slow',
  Work: 'work',
}

const CATEGORY_LABEL_TO_TAG: Record<string, CategoryTag> = {
  Linen: 'linen',
  Footwear: 'footwear',
  Outerwear: 'outerwear',
  Accessories: 'accessories',
  Home: 'home',
  Dresses: 'dresses',
}

// Gradient swatch tokens for Group 2 (Colors). Each key matches the
// `swatch` field in copy.ts PREFERENCES_MODAL.GROUPS[1].chips.
const SWATCH_GRADIENTS: Record<string, string> = {
  'terracotta-to-amber':
    'linear-gradient(135deg, var(--dl-accent) 0%, var(--dl-warn) 100%)',
  'sand-to-ink-soft':
    'linear-gradient(135deg, var(--dl-paper-2) 0%, var(--dl-muted) 100%)',
  'ink-soft-to-dusk':
    'linear-gradient(135deg, var(--dl-muted) 0%, var(--dl-ink) 100%)',
  'cream-warm-to-cream':
    'linear-gradient(135deg, var(--cream-warm) 0%, var(--cream) 100%)',
  'ink-to-near-black':
    'linear-gradient(135deg, var(--dl-ink) 0%, color-mix(in srgb, var(--dl-ink) 65%, #000) 100%)',
}

// Index helpers — the GROUPS array in copy.ts is a four-entry tuple in a
// fixed order (vibe, colors, occasions, categories). Referring by index
// keeps the rendering loop honest.
const GROUP_VIBE = 0
const GROUP_COLORS = 1
const GROUP_OCCASIONS = 2
const GROUP_CATEGORIES = 3

// --- Chip component ------------------------------------------------------
interface ChipProps {
  label: string
  descriptor?: string
  swatch?: string
  selected: boolean
  onToggle: () => void
  testId: string
  variant: 'card' | 'pill'
}

function Chip({
  label,
  descriptor,
  swatch,
  selected,
  onToggle,
  testId,
  variant,
}: ChipProps) {
  const base = {
    cursor: 'pointer',
    transition:
      'background 160ms ease-out, color 160ms ease-out, border-color 160ms ease-out, transform 120ms ease-out',
    fontFamily: 'var(--sans)',
  }

  // Selected state: Daylight ink + paper (resolved via cssVars).
  const selectedStyle = selected
    ? {
        background: c.surfaceInk,
        color: c.onInkSurface,
        borderColor: c.surfaceInk,
      }
    : {
        background: c.bg,
        color: c.ink,
        borderColor: c.muted,
      }

  if (variant === 'card') {
    return (
      <button
        type="button"
        data-testid={testId}
        data-selected={selected ? 'true' : 'false'}
        aria-pressed={selected}
        onClick={onToggle}
        style={{
          ...base,
          ...selectedStyle,
          padding: '16px 14px',
          borderRadius: 16,
          border: `1px solid ${selectedStyle.borderColor}`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          gap: 4,
          textAlign: 'left',
        }}
      >
        <span style={{ fontSize: 15, fontWeight: 500 }}>{label}</span>
        {descriptor && (
          <span
            style={{
              fontSize: 11,
              color: selected ? c.paper : c.ink2,
              letterSpacing: '0.02em',
            }}
          >
            {descriptor}
          </span>
        )}
      </button>
    )
  }

  return (
    <button
      type="button"
      data-testid={testId}
      data-selected={selected ? 'true' : 'false'}
      aria-pressed={selected}
      onClick={onToggle}
      style={{
        ...base,
        ...selectedStyle,
        padding: '10px 16px',
        borderRadius: 9999,
        border: `1px solid ${selectedStyle.borderColor}`,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 13,
      }}
    >
      {swatch && SWATCH_GRADIENTS[swatch] && (
        <span
          data-testid={`${testId}-swatch`}
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: SWATCH_GRADIENTS[swatch],
            border: `1px solid ${selected ? c.surfaceInk : c.muted}`,
          }}
        />
      )}
      <span>{label}</span>
    </button>
  )
}

// --- PreferencesModal ----------------------------------------------------
export default function PreferencesModal() {
  const { activeModal, closeModal } = useUI()
  const { savePreferences } = useAuth()
  const isOpen = activeModal === 'preferences'

  // One Set per group, indexed 0..3 to match the copy.ts tuple order.
  const [selected, setSelected] = useState<Array<Set<string>>>([
    new Set(),
    new Set(),
    new Set(),
    new Set(),
  ])

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset local state whenever the modal is opened so the modal doesn't
  // ghost prior selections between sessions.
  useEffect(() => {
    if (isOpen) {
      setSelected([new Set(), new Set(), new Set(), new Set()])
      setError(null)
      setSaving(false)
    }
  }, [isOpen])

  // Lock body scroll while open. UIContext's global keydown handler covers
  // Escape, so we don't need a local listener.
  useEffect(() => {
    if (!isOpen || typeof document === 'undefined') return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [isOpen])

  const toggle = useCallback((groupIndex: number, label: string) => {
    setSelected((prev) => {
      const next = prev.map((s) => new Set(s))
      if (next[groupIndex].has(label)) {
        next[groupIndex].delete(label)
      } else {
        next[groupIndex].add(label)
      }
      return next
    })
  }, [])

  // Map the Set<label> selections onto the typed Preferences payload.
  const buildPayload = useMemo(
    () => (): Preferences => {
      const vibe: VibeTag[] = []
      for (const label of selected[GROUP_VIBE]) {
        const tag = VIBE_LABEL_TO_TAG[label]
        if (tag) vibe.push(tag)
      }
      const colors: ColorTag[] = []
      for (const label of selected[GROUP_COLORS]) {
        const tag = COLOR_LABEL_TO_TAG[label]
        if (tag) colors.push(tag)
      }
      const occasions: OccasionTag[] = []
      for (const label of selected[GROUP_OCCASIONS]) {
        const tag = OCCASION_LABEL_TO_TAG[label]
        if (tag) occasions.push(tag)
      }
      const categories: CategoryTag[] = []
      for (const label of selected[GROUP_CATEGORIES]) {
        const tag = CATEGORY_LABEL_TO_TAG[label]
        if (tag) categories.push(tag)
      }
      return { vibe, colors, occasions, categories }
    },
    [selected],
  )

  const handleSave = async () => {
    setError(null)
    setSaving(true)
    try {
      await savePreferences(buildPayload())
      // Close the modal on success. The curated banner flash and grid
      // re-sort are triggered by AuthContext advancing prefsVersion.
      closeModal()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save_failed')
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = () => {
    // No POST, just dismiss. Preferences stay null; AuthStateBand renders
    // nothing and the sign-in -> prefs loop can be restarted from the
    // Account menu.
    closeModal()
  }

  if (!isOpen) return null

  const groups = PREFERENCES_MODAL.GROUPS as PreferenceGroup[]

  return (
    <div
      data-testid="prefs-modal-backdrop"
      role="presentation"
      onClick={closeModal}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        background: 'rgba(45, 24, 16, 0.45)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
      }}
    >
      <div
        data-testid="prefs-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prefs-modal-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 640,
          maxHeight: '90vh',
          overflowY: 'auto',
          background: c.bg,
          borderRadius: 24,
          padding: '32px 32px 20px 32px',
          boxShadow:
            '0 24px 60px rgba(45, 24, 16, 0.32), 0 4px 12px rgba(45, 24, 16, 0.2)',
          fontFamily: 'var(--sans)',
          color: c.ink,
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 10,
            textAlign: 'center',
          }}
        >
          <span
            data-testid="prefs-modal-b-mark"
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 44,
              height: 44,
              borderRadius: '50%',
              background: c.ink,
              color: c.bg,
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontSize: 20,
              lineHeight: 1,
            }}
          >
            B
          </span>
          <h2
            id="prefs-modal-title"
            data-testid="prefs-modal-header"
            style={{
              margin: 0,
              fontFamily: FRAUNCES_STACK,
              fontSize: 24,
              fontWeight: 500,
              color: c.ink,
              letterSpacing: '-0.01em',
            }}
          >
            {PREFERENCES_MODAL.HEADER}
          </h2>
          <p
            data-testid="prefs-modal-subheader"
            style={{ margin: 0, fontSize: 13, color: c.ink2, lineHeight: 1.5 }}
          >
            {PREFERENCES_MODAL.SUBHEADER}
          </p>
        </div>

        {/* Body headline */}
        <div
          style={{
            marginTop: 18,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
            textAlign: 'center',
          }}
        >
          <span
            data-testid="prefs-modal-italic-headline"
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontSize: 22,
              color: c.ink,
              lineHeight: 1.3,
            }}
          >
            {PREFERENCES_MODAL.ITALIC_HEADLINE}
          </span>
          <span
            data-testid="prefs-modal-subheadline"
            style={{ fontSize: 13, color: c.ink2 }}
          >
            {PREFERENCES_MODAL.SUBHEADLINE}
          </span>
        </div>

        {/* Four preference groups */}
        <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
          {groups.map((group, groupIndex) => (
            <section
              key={groupIndex}
              data-testid={`prefs-group-${groupIndex}`}
              data-group-kind={group.kind}
            >
              <h3
                data-testid={`prefs-group-${groupIndex}-heading`}
                style={{
                  margin: 0,
                  marginBottom: 10,
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  color: c.ink2,
                }}
              >
                {group.heading}
              </h3>
              <div
                style={{
                  display: group.kind === 'card' ? 'grid' : 'flex',
                  gridTemplateColumns:
                    group.kind === 'card'
                      ? 'repeat(3, minmax(0, 1fr))'
                      : undefined,
                  flexWrap: group.kind === 'pill' ? 'wrap' : undefined,
                  gap: 10,
                }}
              >
                {group.chips.map((chip, chipIndex) => (
                  <Chip
                    key={chip.label}
                    label={chip.label}
                    descriptor={chip.descriptor}
                    swatch={chip.swatch}
                    selected={selected[groupIndex].has(chip.label)}
                    onToggle={() => toggle(groupIndex, chip.label)}
                    testId={`prefs-chip-${groupIndex}-${chipIndex}`}
                    variant={group.kind}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>

        {/* Error message */}
        {error && (
          <p
            data-testid="prefs-modal-error"
            style={{
              marginTop: 14,
              fontSize: 12,
              color: c.accent,
              textAlign: 'center',
            }}
          >
            {error}
          </p>
        )}

        {/* Submit row */}
        <div
          style={{
            marginTop: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <button
            type="button"
            data-testid="prefs-modal-skip"
            onClick={handleSkip}
            disabled={saving}
            style={{
              background: 'transparent',
              border: 'none',
              color: c.ink2,
              fontSize: 13,
              textDecoration: 'underline',
              textUnderlineOffset: 3,
              cursor: saving ? 'not-allowed' : 'pointer',
              padding: '8px 4px',
              opacity: saving ? 0.6 : 1,
            }}
          >
            {PREFERENCES_MODAL.SKIP}
          </button>
          <button
            type="button"
            data-testid="prefs-modal-submit"
            onClick={handleSave}
            disabled={saving}
            style={{
              background: c.ink,
              color: c.bg,
              border: 'none',
              padding: '12px 20px',
              borderRadius: 9999,
              fontSize: 14,
              fontWeight: 500,
              letterSpacing: '0.02em',
              cursor: saving ? 'not-allowed' : 'pointer',
              transition: 'background 160ms ease-out, transform 120ms ease-out',
              opacity: saving ? 0.7 : 1,
            }}
            onMouseEnter={(e) => {
              if (!saving) e.currentTarget.style.background = c.accent
            }}
            onMouseLeave={(e) => {
              if (!saving) e.currentTarget.style.background = c.ink
            }}
          >
            {PREFERENCES_MODAL.SUBMIT}
          </button>
        </div>

        {/* Footer strip: 10px mono with shield icon */}
        <div
          data-testid="prefs-modal-footer"
          style={{
            marginTop: 20,
            paddingTop: 14,
            borderTop: `1px solid ${c.line}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            color: c.muted,
            fontFamily: MONO_STACK,
            fontSize: 10,
            letterSpacing: '0.04em',
          }}
        >
          <svg
            data-testid="prefs-modal-shield"
            aria-hidden="true"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>{PREFERENCES_MODAL.FOOTER}</span>
        </div>
      </div>
    </div>
  )
}
// === CHALLENGE 9.4: END ===
