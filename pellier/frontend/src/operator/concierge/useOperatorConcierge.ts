/**
 * One controller for the Concierge pane. Components render; this owns server truth.
 *
 * Scattering `fetchCapabilities()` / `createSession()` / `appendTurn()` across
 * components is how a surface ends up with four opinions about whether a governed
 * action is available. Every server fact enters here.
 *
 * Two deliberate behaviours:
 *
 *   Lazy sessions      Opening a client record must not create a database
 *                      conversation. Thousands of empty threads would be the
 *                      cost of a page view. A session is created when the
 *                      operator first submits.
 *
 *   Concurrent reads   Capability, config, and latest-session are independent, so
 *                      they run together. The client record itself is already a
 *                      ~1s parallel read; turning the right pane into a serial
 *                      waterfall on top of it would undo that.
 */

import { upsertInvestigationStep } from './traceSteps'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  createConciergeSession,
  fetchCapabilities,
  fetchConciergeConfig,
  fetchConciergeSession,
  fetchLatestConciergeSession,
  streamConciergeTurn,
} from '../../services/operator'
import type {
  CapabilitySnapshot,
  ConciergeConfig,
  ConciergeInvestigationStep,
  ConciergeMessage,
  ConciergeStreamAnswer,
} from '../../services/operator'

export type ConciergeStatus =
  | 'loading'
  | 'ready'
  | 'read_only'
  | 'submitting'
  | 'capability_unverified'
  | 'conversation_unavailable'
  | 'config_unavailable'

export interface ConciergeController {
  status: ConciergeStatus
  capabilities: CapabilitySnapshot | null
  config: ConciergeConfig | null
  sessionId: string | null
  messages: ConciergeMessage[]
  /** True when a governed write is currently reachable. */
  governedActionsAvailable: boolean
  composerEnabled: boolean
  error: string | null
  /** Real steps arriving during an in-flight turn. Empty when idle. */
  liveSteps: ConciergeInvestigationStep[]
  /** The request currently in flight, so it renders before the answer exists. */
  pendingRequest: string | null
  /** Durable server answer, visible while post-answer work and history reload finish. */
  liveAnswer: ConciergeStreamAnswer | null
  submit: (message: string) => Promise<boolean>
  retryHistory: () => Promise<void>
  startNew: () => void
  stopReceiving: () => void
}

interface ConciergeOptions {
  /** A guided workshop run starts clean instead of replaying the prior case file. */
  resumeLatest?: boolean
}

/** A stable key per submission so a network retry cannot duplicate the turn. */
function transportKey(): string {
  const random = globalThis.crypto?.randomUUID?.()
  return random ?? `tk-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function useOperatorConcierge(
  clientId: string,
  options: ConciergeOptions = {},
): ConciergeController {
  const resumeLatest = options.resumeLatest ?? true
  const [capabilities, setCapabilities] = useState<CapabilitySnapshot | null>(null)
  const [config, setConfig] = useState<ConciergeConfig | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConciergeMessage[]>([])
  const [status, setStatus] = useState<ConciergeStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const [liveSteps, setLiveSteps] = useState<ConciergeInvestigationStep[]>([])
  const [pendingRequest, setPendingRequest] = useState<string | null>(null)
  const [liveAnswer, setLiveAnswer] = useState<ConciergeStreamAnswer | null>(null)
  const [loadedClientId, setLoadedClientId] = useState<string | null>(null)
  const active = useRef(true)
  const busy = useRef(false)
  const turnController = useRef<AbortController | null>(null)
  const clientGeneration = useRef(0)

  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      turnController.current?.abort()
    }
  }, [])

  useEffect(() => {
    turnController.current?.abort()
    busy.current = false
    const generation = ++clientGeneration.current
    const isCurrentClient = () =>
      active.current && clientGeneration.current === generation
    if (!clientId) return
    setStatus('loading')
    setError(null)
    setCapabilities(null)
    setConfig(null)
    setLoadedClientId(null)
    setMessages([])
    setSessionId(null)
    setLiveSteps([])
    setPendingRequest(null)
    setLiveAnswer(null)

    // Independent reads, so concurrently. `allSettled` because a capability
    // read failing must not hide the conversation, and vice versa.
    void Promise.allSettled([
      fetchCapabilities(),
      fetchConciergeConfig(),
      resumeLatest
        ? fetchLatestConciergeSession(clientId)
        : Promise.resolve(null),
    ]).then(async ([caps, cfg, latest]) => {
      if (!isCurrentClient()) return

      if (caps.status === 'fulfilled') {
        setCapabilities(caps.value)
      } else {
        // A control-plane read failure is NOT a governance state. Keep them
        // distinguishable: the backend already fails closed, and if even that
        // could not be reached we say so rather than implying a closed rail.
        setCapabilities(null)
      }
      if (cfg.status === 'fulfilled') setConfig(cfg.value)

      if (latest.status === 'rejected') {
        setStatus('conversation_unavailable')
        return
      }
      if (cfg.status === 'rejected') {
        setStatus('config_unavailable')
        return
      }

      let resumed: string | null = null
      if (latest.status === 'fulfilled') resumed = latest.value

      if (resumed) {
        try {
          const session = await fetchConciergeSession(clientId, resumed)
          if (!isCurrentClient()) return
          // Never render another client's conversation or silently replace it.
          if (session.customerId !== clientId) throw new Error('conversation_scope_mismatch')
          setSessionId(session.sessionId)
          setMessages(session.messages)
          if (session.messages.at(-1)?.turnState === 'incomplete') {
            setError('The saved turn is still incomplete. Refresh history before sending another request.')
            setStatus('conversation_unavailable')
            return
          }
        } catch {
          if (!isCurrentClient()) return
          setStatus('conversation_unavailable')
          return
        }
      }

      if (!isCurrentClient()) return
      if (caps.status !== 'fulfilled') {
        setStatus('capability_unverified')
      } else {
        setStatus(caps.value.governedActionsAvailable ? 'ready' : 'read_only')
      }
      setLoadedClientId(clientId)
    })
  }, [clientId, resumeLatest])

  const governedActionsAvailable = Boolean(capabilities?.governedActionsAvailable)
  const composerEnabled = Boolean(
    config?.composerEnabled && loadedClientId === clientId &&
    status !== 'conversation_unavailable' && status !== 'config_unavailable' && status !== 'loading',
  )

  const submit = useCallback(
    async (message: string) => {
      const text = message.trim()
      if (!text || !composerEnabled || busy.current) return false
      busy.current = true
      const controller = new AbortController()
      turnController.current = controller
      const generation = clientGeneration.current
      const isCurrentClient = () =>
        active.current && clientGeneration.current === generation
      setStatus('submitting')
      setError(null)
      setLiveSteps([])
      setLiveAnswer(null)
      // Show the request immediately. Seven seconds of stillness after pressing
      // Enter is the single worst part of the experience, and the request is a fact
      // as soon as it is sent.
      setPendingRequest(text)
      try {
        // Lazy creation: the first submission is what makes a thread exist.
        const id = sessionId ?? (await createConciergeSession(clientId)).sessionId
        if (!isCurrentClient()) return false
        setSessionId(id)
        if (controller.signal.aborted) throw new Error('Receiving stopped; the server may still be working.')

        await streamConciergeTurn(
          clientId,
          id,
          text,
          transportKey(),
          (step) => {
            if (!isCurrentClient()) return false
            setLiveSteps((prev) => upsertInvestigationStep(prev, step))
          },
          (answer) => {
            if (!isCurrentClient()) return false
            setLiveAnswer(answer)
          },
          controller.signal,
        )
        if (!isCurrentClient()) return false

        // Reload rather than optimistically appending: the server owns turn state,
        // and a replayed submission must not show twice.
        const session = await fetchConciergeSession(clientId, id)
        if (!isCurrentClient()) return false
        if (session.customerId !== clientId) throw new Error('conversation_scope_mismatch')
        if (session.messages.at(-1)?.turnState === 'incomplete') {
          throw new Error('The saved turn is still incomplete. Refresh history before sending another request.')
        }
        setMessages(session.messages)
        setPendingRequest(null)
        setLiveSteps([])
        setLiveAnswer(null)
        setStatus(governedActionsAvailable ? 'ready' : 'read_only')
        return true
      } catch (err) {
        if (!isCurrentClient()) return false
        setError(err instanceof Error ? err.message : 'operator_unavailable')
        // Preserve the request and any durable streamed answer until history reconciles.
        setStatus('conversation_unavailable')
        return false
      } finally {
        if (isCurrentClient()) {
          busy.current = false
          turnController.current = null
        }
      }
    },
    [clientId, composerEnabled, governedActionsAvailable, sessionId],
  )

  const retryHistory = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    const generation = clientGeneration.current
    const current = () => active.current && clientGeneration.current === generation
    setStatus('loading')
    try {
      const [caps, cfg, latest] = await Promise.all([
        fetchCapabilities(), fetchConciergeConfig(),
        sessionId ? Promise.resolve(sessionId) : fetchLatestConciergeSession(clientId),
      ])
      const session = latest ? await fetchConciergeSession(clientId, latest) : null
      if (!current()) return
      if (session && session.customerId !== clientId) throw new Error('conversation_scope_mismatch')
      setCapabilities(caps)
      setConfig(cfg)
      setSessionId(session?.sessionId ?? null)
      setMessages(session?.messages ?? [])
      const incomplete = session?.messages.at(-1)?.turnState === 'incomplete'
      if (incomplete) {
        setError('The saved turn is still incomplete. Refresh history again before sending another request.')
        setStatus('conversation_unavailable')
        return
      }
      setLiveSteps([])
      setLiveAnswer(null)
      setPendingRequest(null)
      setError(null)
      setLoadedClientId(clientId)
      setStatus(caps.governedActionsAvailable ? 'ready' : 'read_only')
    } catch {
      if (current()) setStatus('conversation_unavailable')
    } finally {
      if (current()) busy.current = false
    }
  }, [clientId, sessionId])

  const startNew = useCallback(() => {
    if (busy.current || !config?.composerEnabled) return
    setSessionId(null)
    setMessages([])
    setLiveSteps([])
    setLiveAnswer(null)
    setPendingRequest(null)
    setError(null)
    setLoadedClientId(clientId)
    setStatus(governedActionsAvailable ? 'ready' : 'read_only')
  }, [clientId, config?.composerEnabled, governedActionsAvailable])
  const stopReceiving = useCallback(() => { turnController.current?.abort() }, [])

  useEffect(() => {
    // Honour the server's capability TTL; never refresh the conversation on this timer.
    const ttl = Number.isFinite(capabilities?.ttlSeconds) ? Math.max(1, capabilities!.ttlSeconds) * 1000 : 60_000
    let current = true
    let refreshing = false
    const refresh = async () => {
      if (document.visibilityState !== 'visible' || refreshing) return
      refreshing = true
      try {
        const caps = await fetchCapabilities()
        if (current) setCapabilities(caps)
      } catch {
        if (current) setCapabilities(null)
      } finally { refreshing = false }
    }
    const timer = window.setInterval(() => void refresh(), ttl)
    window.addEventListener('focus', refresh)
    return () => { current = false; window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [clientId, capabilities?.ttlSeconds])

  return useMemo(
    () => ({
      status,
      capabilities,
      config,
      sessionId,
      messages,
      governedActionsAvailable,
      composerEnabled,
      error,
      liveSteps,
      pendingRequest,
      liveAnswer,
      submit,
      retryHistory,
      startNew,
      stopReceiving,
    }),
    [
      status,
      capabilities,
      config,
      sessionId,
      messages,
      governedActionsAvailable,
      composerEnabled,
      error,
      liveSteps,
      pendingRequest,
      liveAnswer,
      submit,
      retryHistory,
      startNew,
      stopReceiving,
    ],
  )
}
