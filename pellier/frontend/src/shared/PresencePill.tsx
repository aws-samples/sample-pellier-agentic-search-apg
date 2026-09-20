/**
 * PresencePill — compact "agent is here" cue: breathing accent dot + a
 * short professional label.
 *
 * Both halves are claims about live systems, so both are measured:
 *
 *   the label   `Concierge online` only while `/api/health` has answered
 *               successfully within the last 30 seconds; `Concierge offline`
 *               otherwise, including before the first check returns, and
 *               including when a check is still in flight past its deadline.
 *   the tail    the persona, plus a memory age derived from the newest
 *               event the memory endpoint reports for them. No event, no
 *               age: a literal "14h memory" described no session and was
 *               indistinguishable from a measurement.
 *
 * Used on the Pellier capability strip (cream-tinted, glass background)
 * and on the Observatory TopBar. Both use Pellier's warm paper and ink.
 * Only a verified online Observatory dot uses the positive-status color.
 *
 * Pass `sessionLabel=""` explicitly to force-hide the fragment.
 */
import React, { useEffect, useState } from 'react'

import { API_BASE_URL } from '../services/apiBase'
import { checkBackendHealth } from '../services/chat'

export type PresenceSurface = 'pellier' | 'observatory'
export type PresenceMode = 'listening' | 'thinking' | 'idle'

export interface PresencePillProps {
  surface: PresenceSurface
  /** Persona id ("marco" / "anna" / "theo" / null/"fresh"). */
  personaId?: string | null
  /** Explicit override; otherwise derived from persona id. */
  sessionLabel?: string
  /** Animation state. `thinking` makes the dot pulse faster. */
  mode?: PresenceMode
  /**
   * Override the lead label. Left unset the pill reports measured health,
   * which is the only honest default.
   */
  label?: string
}

const ACCENT = 'var(--accent)'

/**
 * How long a successful check stands for. This is the claim the label makes,
 * so it is the number that has to be true.
 */
export const HEALTH_FRESH_MS = 30_000

/**
 * How often a check is attempted. Shorter than the freshness window so a
 * healthy backend always has a fresh answer in hand: at the same cadence,
 * every cycle would blink offline for the duration of the request.
 */
const HEALTH_POLL_MS = 15_000

/**
 * How long one check may take before it is abandoned. Without this a hung
 * health endpoint leaves the pill reading online for as long as the tab is
 * open, which is the exact opposite of what it is for.
 */
export const HEALTH_TIMEOUT_MS = 5_000

const PRESENCE_ONLINE = 'Concierge online'
const PRESENCE_OFFLINE = 'Concierge offline'
/* Before the first health check answers there is no evidence either way.
   Saying offline there is the same unfounded claim as saying online was,
   and it reads in a workshop room as a broken system rather than a pending
   request. */
const PRESENCE_CHECKING = 'Concierge checking'

/** Whole hours or days since `iso`, or null when it is not a usable date. */
function memoryAgeLabel(iso: string | null | undefined): string | null {
  if (!iso) return null
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return null
  const minutes = Math.floor((Date.now() - then) / 60_000)
  if (minutes < 0) return null
  if (minutes < 60) return `${Math.max(minutes, 1)}m memory`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h memory`
  return `${Math.floor(hours / 24)}d memory`
}

interface MemoryPanelItem {
  timestamp?: string | null
}

/** The newest timestamp across every substrate panel the endpoint returned. */
function newestMemoryTimestamp(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  let newest: number | null = null
  let newestIso: string | null = null
  for (const panel of Object.values(payload as Record<string, unknown>)) {
    if (!panel || typeof panel !== 'object') continue
    const items = (panel as { items?: MemoryPanelItem[] }).items
    if (!Array.isArray(items)) continue
    for (const item of items) {
      if (!item?.timestamp) continue
      const parsed = Date.parse(item.timestamp)
      if (Number.isNaN(parsed)) continue
      if (newest === null || parsed > newest) {
        newest = parsed
        newestIso = item.timestamp
      }
    }
  }
  return newestIso
}

/**
 * The most recent completed check, shared across every `PresencePill`
 * mount in this tab. `useBackendReachable` starts a fresh poll cycle on
 * every mount regardless (below), but client-side navigation between
 * Observatory routes unmounts and remounts the pill on each transition,
 * which reset `reachable` to `null` every time -- flashing "Concierge
 * checking" for the gap before the new mount's own check resolved, even
 * seconds after a real, still-fresh measurement. A measurement this cache
 * holds is exactly as real after a remount as it was before it; only its
 * age matters, which `freshUntil` already encodes.
 */
let healthCache: { reachable: boolean; freshUntil: number } | null = null

/**
 * Test-only: clear the cross-mount cache. Without this, one test's real or
 * fake-timer measurement could still read as fresh at the start of the next
 * test in the same file, since the cache otherwise only self-expires with
 * real wall-clock or advanced fake time.
 */
export function __resetPresenceHealthCacheForTests(): void {
  healthCache = null
}

function cachedReachable(): boolean | null {
  if (!healthCache || healthCache.freshUntil <= Date.now()) return null
  return healthCache.reachable
}

function cachedFreshUntil(): number | null {
  if (!healthCache || healthCache.freshUntil <= Date.now()) return null
  return healthCache.freshUntil
}

/**
 * True while a health check has *succeeded* inside the freshness window.
 *
 * Three things make this a measurement rather than a cadence. Each check
 * carries a deadline, so a hung endpoint resolves as a failure instead of
 * never resolving. A check that is still in flight blocks the next one, so a
 * slow backend does not accumulate requests. And a success is stamped with
 * the time it arrived and expires on its own, so the label can never outlive
 * the evidence for it even if the polling loop stops running.
 */
function useBackendReachable(): boolean | null {
  const [reachable, setReachable] = useState<boolean | null>(cachedReachable)
  const [freshUntil, setFreshUntil] = useState<number | null>(cachedFreshUntil)
  useEffect(() => {
    let active = true
    // Each effect owns its request. StrictMode's replacement effect must not
    // inherit an in-flight flag from the effect that was just cleaned up.
    let inFlight = false
    let activeController: AbortController | null = null
    let deadline: number | undefined

    const check = async () => {
      if (inFlight) return
      inFlight = true
      const controller = new AbortController()
      activeController = controller
      deadline = window.setTimeout(
        () => controller.abort(),
        HEALTH_TIMEOUT_MS,
      )
      try {
        const ok = await checkBackendHealth(controller.signal)
        if (!active) return
        const until = Date.now() + HEALTH_FRESH_MS
        healthCache = { reachable: ok, freshUntil: until }
        if (ok) {
          setFreshUntil(until)
          setReachable(true)
        } else {
          // The endpoint answered, and answered badly. No need to wait out
          // the window for a fact already in hand.
          setReachable(false)
        }
      } finally {
        window.clearTimeout(deadline)
        activeController = null
        inFlight = false
      }
    }

    void check()
    const poll = window.setInterval(() => void check(), HEALTH_POLL_MS)
    return () => {
      active = false
      window.clearInterval(poll)
      window.clearTimeout(deadline)
      activeController?.abort()
    }
  }, [])

  // One timer per success, armed for the exact moment the claim lapses.
  useEffect(() => {
    if (freshUntil === null) return
    const remaining = freshUntil - Date.now()
    if (remaining <= 0) {
      setReachable(false)
      return
    }
    const expiry = window.setTimeout(() => setReachable(false), remaining)
    return () => window.clearTimeout(expiry)
  }, [freshUntil])

  return reachable
}

/** The persona's memory age, or null when no event carries a timestamp. */
function useMemoryAge(personaId: string | null | undefined): string | null {
  const [age, setAge] = useState<string | null>(null)

  useEffect(() => {
    setAge(null)
    if (!personaId || personaId === 'fresh') return
    const controller = new AbortController()
    fetch(
      `${API_BASE_URL}/api/observatory/memory/${encodeURIComponent(personaId)}`,
      {
        signal: controller.signal,
      },
    )
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (controller.signal.aborted) return
        setAge(memoryAgeLabel(newestMemoryTimestamp(payload)))
      })
      .catch(() => {
        if (!controller.signal.aborted) setAge(null)
      })
    return () => controller.abort()
  }, [personaId])

  return age
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
    @media (prefers-reduced-motion: reduce) {
      [data-pellier-presence-dot] {
        animation: none !important;
        opacity: 1 !important;
        transform: none !important;
      }
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
  label,
}) => {
  // Inject the breathing keyframes once per page. Component-scoped
  // <style> tags would re-render on every mount; this hoists them.
  ensureKeyframes()

  const reachable = useBackendReachable()
  const memoryAge = useMemoryAge(personaId)
  const isObservatory = surface === 'observatory'
  const resolvedLabel =
    label ??
    (reachable === null
      ? PRESENCE_CHECKING
      : reachable
        ? PRESENCE_ONLINE
        : PRESENCE_OFFLINE)
  const derivedSession =
    !personaId || personaId === 'fresh'
      ? ''
      : [personaId, memoryAge].filter(Boolean).join(' · ')
  const session = sessionLabel ?? derivedSession

  const animation =
    mode === 'idle' || reachable !== true
      ? 'none'
      : mode === 'thinking'
        ? 'pelliers-presence-think 1.2s ease-in-out infinite'
        : 'pelliers-presence-breathe 2.4s ease-in-out infinite'

  return (
    <div
      data-testid={`presence-pill-${surface}`}
      data-mode={mode}
      data-reachable={reachable === null ? 'unknown' : reachable ? 'true' : 'false'}
      role="status"
      aria-label={
        reachable === null
          ? 'AI-assisted personal shopping. Checking whether a concierge agent is reachable.'
          : reachable
            ? 'AI-assisted personal shopping. A concierge agent is ready to help.'
            : 'AI-assisted personal shopping. The concierge is not reachable right now.'
      }
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: isObservatory ? '8px 14px' : '6px 12px',
        borderRadius: 999,
        border: isObservatory
          ? '1px solid color-mix(in srgb, var(--pellier-burgundy) 18%, var(--rule-1))'
          : '1px solid color-mix(in srgb, var(--dl-ink) 16%, transparent)',
        background: isObservatory
          ? 'var(--cream-elev)'
          : 'color-mix(in srgb, var(--cream-warm) 72%, transparent)',
        backdropFilter: isObservatory ? 'none' : 'blur(6px)',
        boxShadow: isObservatory ? 'inset 0 1px 0 rgb(255 255 255 / 65%), 0 3px 10px rgb(60 40 10 / 4%)' : undefined,
        fontFamily: 'var(--sans), system-ui, sans-serif',
        fontSize: isObservatory ? '13px' : '11px',
        letterSpacing: isObservatory ? '0.01em' : '0.12em',
        textTransform: isObservatory ? 'none' : 'uppercase',
        lineHeight: 1.3,
        color: isObservatory ? 'var(--pellier-burgundy)' : 'var(--ink)',
        fontWeight: 500,
      }}
    >
      <span
        aria-hidden="true"
        data-pellier-presence-dot
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: isObservatory
            ? reachable === true ? 'var(--gov-allow-fg)' : 'var(--pellier-burgundy)'
            : ACCENT,
          animation,
          flexShrink: 0,
        }}
      />
      <span>{resolvedLabel}</span>
      {session ? (
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 11,
            letterSpacing: '0.06em',
            color: 'var(--ink-soft)',
            textTransform: 'none',
            marginLeft: 4,
            paddingLeft: 10,
            borderLeft: isObservatory
              ? '1px solid var(--rule-2)'
              : '1px solid color-mix(in srgb, var(--dl-ink) 18%, transparent)',
          }}
        >
          {session}
        </span>
      ) : null}
    </div>
  )
}
