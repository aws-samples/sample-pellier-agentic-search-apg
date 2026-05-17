/**
 * PresencePill — compact “agent is here” cue: breathing accent dot + a
 * short professional label. The optional trailing fragment (mono) only
 * appears for signed-in personas so first-time visitors are not hit with
 * session jargon.
 *
 * Used on the Boutique capability strip (cream-tinted, glass background)
 * and on the Atelier TopBar (same boutique styling on the light cream bar).
 *
 * Pass `sessionLabel=""` explicitly to force-hide the fragment, or rely
 * on defaults: fresh / anonymous → no fragment; returning shoppers →
 * `marco · 14h memory` style tail.
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
  /** Lead label. Defaults to a discreet concierge cue (no “listening”). */
  label?: string
}

const ACCENT = 'var(--accent)'

const MEMORY_AGE: Record<string, string> = {
  marco: '14h memory',
  anna: '2d memory',
  theo: '5d memory',
}

function deriveSessionLabel(personaId: string | null | undefined): string {
  if (!personaId || personaId === 'fresh') return ''
  return `${personaId} · ${MEMORY_AGE[personaId] ?? 'recall on'}`
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
  label = 'Concierge online',
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
      role="status"
      aria-label="AI-assisted personal shopping. A concierge agent is ready to help."
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: '6px 12px',
        borderRadius: 999,
        border: isAtelier
          ? '1px solid color-mix(in srgb, var(--cream-warm) 18%, transparent)'
          : '1px solid color-mix(in srgb, var(--dl-ink) 16%, transparent)',
        background: isAtelier
          ? 'color-mix(in srgb, var(--cream-warm) 6%, transparent)'
          : 'color-mix(in srgb, var(--cream-warm) 72%, transparent)',
        backdropFilter: 'blur(6px)',
        fontFamily: 'var(--sans), system-ui, sans-serif',
        fontSize: '11px',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: isAtelier
          ? 'color-mix(in srgb, var(--cream-warm) 92%, transparent)'
          : 'var(--ink)',
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
            fontFamily: 'var(--mono)',
            fontSize: 10,
            letterSpacing: '0.06em',
            color: isAtelier
              ? 'color-mix(in srgb, var(--cream-warm) 55%, transparent)'
              : 'var(--ink-soft)',
            textTransform: 'none',
            marginLeft: 4,
            paddingLeft: 10,
            borderLeft: isAtelier
              ? '1px solid color-mix(in srgb, var(--cream-warm) 18%, transparent)'
              : '1px solid color-mix(in srgb, var(--dl-ink) 18%, transparent)',
          }}
        >
          {session}
        </span>
      ) : null}
    </div>
  )
}
