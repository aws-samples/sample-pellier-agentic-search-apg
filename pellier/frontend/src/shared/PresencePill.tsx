/**
 * PresencePill — "Pellier · listening" chip with a breathing burgundy
 * dot. The single signature element that tells an attendee the agent
 * is alive, on either surface.
 *
 * Used on the Boutique hero (cream-tinted, glass background) and on
 * the Atelier TopBar (transparent, dark-surface variant). One atom,
 * two faces, controlled by `surface`.
 *
 * The session fragment ("session · marco · 14h memory") follows the
 * pill in a mono right-rule. Pass an explicit `sessionLabel` to
 * override the default fragment derivation.
 */
import React from 'react'

export type PresenceSurface = 'boutique' | 'atelier'
export type PresenceMode = 'listening' | 'thinking' | 'idle'

export interface PresencePillProps {
  surface: PresenceSurface
  /** Persona id ("marco" / "anna" / "theo" / null/"fresh"). */
  personaId?: string | null
  /** Explicit override; otherwise derived from persona id. */
  sessionLabel?: string
  /** Animation state. `thinking` makes the dot pulse faster. */
  mode?: PresenceMode
  /** Lead label. Defaults to "Pellier · listening". */
  label?: string
}

const ACCENT = '#a8423a'
const MONO_STACK =
  "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

const MEMORY_AGE: Record<string, string> = {
  marco: '14h memory',
  anna: '2d memory',
  theo: '5d memory',
}

function deriveSessionLabel(personaId: string | null | undefined): string {
  if (!personaId || personaId === 'fresh') return 'session · new · learning'
  return `session · ${personaId} · ${MEMORY_AGE[personaId] ?? 'recall on'}`
}

const KEYFRAMES_INJECTED_FLAG = '__pelliersPresenceKeyframesInjected'

function ensureKeyframes() {
  if (typeof document === 'undefined') return
  const w = window as unknown as Record<string, boolean | undefined>
  if (w[KEYFRAMES_INJECTED_FLAG]) return
  const style = document.createElement('style')
  style.dataset.pelliersPresence = 'true'
  style.textContent = `
    @keyframes pelliers-presence-breathe {
      0%, 100% { opacity: 0.45; transform: scale(0.9); }
      50% { opacity: 1; transform: scale(1.15); }
    }
    @keyframes pelliers-presence-think {
      0%, 100% { opacity: 0.55; transform: scale(0.85); }
      50% { opacity: 1; transform: scale(1.25); }
    }
  `
  document.head.appendChild(style)
  w[KEYFRAMES_INJECTED_FLAG] = true
}

export const PresencePill: React.FC<PresencePillProps> = ({
  surface,
  personaId,
  sessionLabel,
  mode = 'listening',
  label = 'Pellier · listening',
}) => {
  // Inject the breathing keyframes once per page. Component-scoped
  // <style> tags would re-render on every mount; this hoists them.
  ensureKeyframes()

  const isAtelier = surface === 'atelier'
  const session = sessionLabel ?? deriveSessionLabel(personaId)

  const animation =
    mode === 'idle'
      ? 'none'
      : mode === 'thinking'
        ? 'pelliers-presence-think 1.2s ease-in-out infinite'
        : 'pelliers-presence-breathe 2.4s ease-in-out infinite'

  return (
    <div
      data-testid={`presence-pill-${surface}`}
      data-mode={mode}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: '6px 12px',
        borderRadius: 999,
        border: isAtelier
          ? '1px solid rgba(250,243,232,0.18)'
          : '1px solid rgba(31,20,16,0.16)',
        background: isAtelier
          ? 'rgba(250,243,232,0.06)'
          : 'rgba(255,250,240,0.72)',
        backdropFilter: 'blur(6px)',
        fontFamily: 'var(--sans), Inter, system-ui, sans-serif',
        fontSize: '11.5px',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color: isAtelier ? 'rgba(250,243,232,0.92)' : '#1f1410',
        fontWeight: 500,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: ACCENT,
          animation,
          flexShrink: 0,
        }}
      />
      <span>{label}</span>
      {session ? (
        <span
          style={{
            fontFamily: MONO_STACK,
            fontSize: 10,
            letterSpacing: '0.06em',
            color: isAtelier ? 'rgba(250,243,232,0.55)' : '#6b4a35',
            textTransform: 'none',
            marginLeft: 4,
            paddingLeft: 10,
            borderLeft: isAtelier
              ? '1px solid rgba(250,243,232,0.18)'
              : '1px solid rgba(31,20,16,0.18)',
          }}
        >
          {session}
        </span>
      ) : null}
    </div>
  )
}
