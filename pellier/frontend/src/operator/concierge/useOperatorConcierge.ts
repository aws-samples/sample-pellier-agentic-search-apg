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
 *
 * A turn runs on the server whether or not this page is still reading it. When the
 * stream ends early, or the page loads while a turn is unanswered, the conversation
 * is reread: a running turn is waited for, and one whose worker stopped arrives
 * already settled by the server as `interrupted`. Starting a new conversation is
 * never the automatic way out.
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
  ConciergeSession,
  ConciergeStreamAnswer,
} from '../../services/operator'
import type { ConciergeOpenTurn } from '../../services/operatorConcierge'

export type ConciergeStatus =
  | 'loading'
  | 'ready'
  | 'read_only'
  | 'submitting'
  /** A saved request is still being answered on the server; this page is waiting. */
  | 'working'
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
  /** The saved request still waiting for its answer, when there is one. */
  openTurn: ConciergeOpenTurn | null
  submit: (message: string) => Promise<boolean>
  retryHistory: () => Promise<void>
  startNew: () => void
  stopReceiving: () => void
}

interface ConciergeOptions {
  /** A guided workshop run starts clean instead of replaying the prior case file. */
  resumeLatest?: boolean
  /** A review returns to its originating conversation, even if a newer one exists. */
  initialSessionId?: string | null
}

/** A stable key per submission so a network retry cannot duplicate the turn. */
function transportKey(): string {
  const random = globalThis.crypto?.randomUUID?.()
  return random ?? `tk-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

/** How often a page waiting on a running turn rereads the conversation. */
export const WORKING_POLL_MS = 2500

export const UNSETTLED_TURN =
  'The last request stopped before its answer was saved. Retry history to record what it left behind.'

const INCOMPLETE_TURN =
  'The saved turn is still incomplete. Refresh history before sending another request.'

/** What a loaded conversation leaves the composer free to do. */
function resumedState(session: ConciergeSession): 'idle' | 'working' | 'unsettled' {
  if (session.openTurn?.state === 'running') return 'working'
  if (session.openTurn) return 'unsettled'
  // A server that does not report open turns cannot say whether this one is running.
  if (session.messages.at(-1)?.turnState === 'incomplete') return 'unsettled'
  return 'idle'
}

function unsettledCopy(session: ConciergeSession): string {
  return session.openTurn ? UNSETTLED_TURN : INCOMPLETE_TURN
}

/** The conversation after a stream ended early, when it says what the turn did. */
async function rereadAfterStream(clientId: string, sessionId: string) {
  const session = await fetchConciergeSession(clientId, sessionId)
  if (session.customerId !== clientId || session.sessionId !== sessionId) return null
  const state = resumedState(session)
  return state === 'unsettled' ? null : { session, state }
}

export function useOperatorConcierge(
  clientId: string,
  options: ConciergeOptions = {},
): ConciergeController {
  const resumeLatest = options.resumeLatest ?? true
  const initialSessionId = options.initialSessionId ?? null
  const [capabilities, setCapabilities] = useState<CapabilitySnapshot | null>(null)
  const [config, setConfig] = useState<ConciergeConfig | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConciergeMessage[]>([])
  const [status, setStatus] = useState<ConciergeStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const [liveSteps, setLiveSteps] = useState<ConciergeInvestigationStep[]>([])
  const [pendingRequest, setPendingRequest] = useState<string | null>(null)
  const [liveAnswer, setLiveAnswer] = useState<ConciergeStreamAnswer | null>(null)
  const [openTurn, setOpenTurn] = useState<ConciergeOpenTurn | null>(null)
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
    setOpenTurn(null)

    // Independent reads, so concurrently. `allSettled` because a capability
    // read failing must not hide the conversation, and vice versa.
    void Promise.allSettled([
      fetchCapabilities(),
      fetchConciergeConfig(),
      initialSessionId
        ? Promise.resolve(initialSessionId)
        : resumeLatest
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

      let working = false
      if (resumed) {
        try {
          const session = await fetchConciergeSession(clientId, resumed)
          if (!isCurrentClient()) return
          // Never render another client's conversation or silently replace it.
          if (session.customerId !== clientId || session.sessionId !== resumed) throw new Error('conversation_scope_mismatch')
          setSessionId(session.sessionId)
          setMessages(session.messages)
          setOpenTurn(session.openTurn ?? null)
          const state = resumedState(session)
          if (state === 'unsettled') {
            setError(unsettledCopy(session))
            setStatus('conversation_unavailable')
            return
          }
          working = state === 'working'
        } catch {
          if (!isCurrentClient()) return
          setStatus('conversation_unavailable')
          return
        }
      }

      if (!isCurrentClient()) return
      if (working) {
        setStatus('working')
      } else if (caps.status !== 'fulfilled') {
        setStatus('capability_unverified')
      } else {
        setStatus(caps.value.governedActionsAvailable ? 'ready' : 'read_only')
      }
      setLoadedClientId(clientId)
    })
  }, [clientId, resumeLatest, initialSessionId])

  const governedActionsAvailable = Boolean(capabilities?.governedActionsAvailable)
  const composerEnabled = Boolean(
    config?.composerEnabled && loadedClientId === clientId && status !== 'working' &&
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
      let id = sessionId
      let saved = false
      try {
        // Lazy creation: the first submission is what makes a thread exist.
        id = sessionId ?? (await createConciergeSession(clientId)).sessionId
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
            // The server saves the request before reporting it, so from here the
            // request outlives this page whatever happens to the stream.
            if (step.kind === 'request') saved = true
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
        if (resumedState(session) !== 'idle') throw new Error(unsettledCopy(session))
        setMessages(session.messages)
        setOpenTurn(null)
        setPendingRequest(null)
        setLiveSteps([])
        setLiveAnswer(null)
        setStatus(governedActionsAvailable ? 'ready' : 'read_only')
        return true
      } catch (err) {
        if (!isCurrentClient()) return false
        // The stream is not the turn. Stopped here, dropped, or refused because a
        // turn is already running: the server may still be answering, or may have
        // answered. Reread before reporting anything as failed.
        const resumed = id ? await rereadAfterStream(clientId, id).catch(() => null) : null
        if (!isCurrentClient()) return false
        // A saved request is either still open or answered, so with nothing open it
        // has its answer. An unsaved one never reached the server and is kept here.
        if (resumed && (resumed.state === 'working' || saved)) {
          setMessages(resumed.session.messages)
          setOpenTurn(resumed.session.openTurn ?? null)
          setPendingRequest(null)
          setLiveSteps([])
          setLiveAnswer(null)
          setError(null)
          setStatus(resumed.state === 'working' ? 'working' : governedActionsAvailable ? 'ready' : 'read_only')
          // Clear the draft only when the server holds it.
          return saved
        }
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
        sessionId || initialSessionId ? Promise.resolve(sessionId || initialSessionId) : fetchLatestConciergeSession(clientId),
      ])
      const session = latest ? await fetchConciergeSession(clientId, latest) : null
      if (!current()) return
      if (session && (session.customerId !== clientId || session.sessionId !== latest)) throw new Error('conversation_scope_mismatch')
      setCapabilities(caps)
      setConfig(cfg)
      setSessionId(session?.sessionId ?? null)
      setMessages(session?.messages ?? [])
      setOpenTurn(session?.openTurn ?? null)
      const state = session ? resumedState(session) : 'idle'
      if (session && state === 'unsettled') {
        setError(unsettledCopy(session))
        setStatus('conversation_unavailable')
        return
      }
      setLiveSteps([])
      setLiveAnswer(null)
      setPendingRequest(null)
      setError(null)
      setLoadedClientId(clientId)
      setStatus(state === 'working' ? 'working' : caps.governedActionsAvailable ? 'ready' : 'read_only')
    } catch {
      if (current()) setStatus('conversation_unavailable')
    } finally {
      if (current()) busy.current = false
    }
  }, [clientId, sessionId, initialSessionId])

  const startNew = useCallback(() => {
    if (busy.current || !config?.composerEnabled) return
    setSessionId(null)
    setMessages([])
    setOpenTurn(null)
    setLiveSteps([])
    setLiveAnswer(null)
    setPendingRequest(null)
    setError(null)
    setLoadedClientId(clientId)
    setStatus(governedActionsAvailable ? 'ready' : 'read_only')
  }, [clientId, config?.composerEnabled, governedActionsAvailable])
  const stopReceiving = useCallback(() => { turnController.current?.abort() }, [])

  useEffect(() => {
    // Wait for a running turn by rereading its conversation. The server settles one
    // whose worker stopped, so this ends in an answer or an interruption, never a
    // turn left open.
    if (status !== 'working' || !sessionId) return
    const generation = clientGeneration.current
    let current = true
    let reading = false
    const reread = async () => {
      if (reading) return
      reading = true
      try {
        const session = await fetchConciergeSession(clientId, sessionId)
        if (!current || !active.current || clientGeneration.current !== generation) return
        if (session.customerId !== clientId || session.sessionId !== sessionId) throw new Error('conversation_scope_mismatch')
        setMessages(session.messages)
        setOpenTurn(session.openTurn ?? null)
        const state = resumedState(session)
        if (state === 'working') return
        if (state === 'unsettled') {
          setError(unsettledCopy(session))
          setStatus('conversation_unavailable')
          return
        }
        setError(null)
        setStatus(governedActionsAvailable ? 'ready' : 'read_only')
      } catch {
        if (current && active.current && clientGeneration.current === generation) {
          setStatus('conversation_unavailable')
        }
      } finally {
        reading = false
      }
    }
    const timer = window.setInterval(() => void reread(), WORKING_POLL_MS)
    return () => { current = false; window.clearInterval(timer) }
  }, [status, sessionId, clientId, governedActionsAvailable])

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
      openTurn,
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
      openTurn,
      submit,
      retryHistory,
      startNew,
      stopReceiving,
    ],
  )
}
