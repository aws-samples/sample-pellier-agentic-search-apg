/**
 * One investigation of one client: the graph's steps as they stream, then the
 * brief and the proposal.
 *
 * Every state is driven by a real stream event; nothing is faked with timers.
 * The step list is the same shape Ask Pellier renders, merged by id with
 * `upsertStep`, so a tool's `running` event becomes its `done` event in place.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { upsertStep, type TurnStep, type TurnStatus } from '../../components/turn/turnTypes'
import {
  OperatorApiError,
  streamInvestigation,
  type InvestigationAnswer,
} from '../../services/operator'

export type InvestigationPhase = 'idle' | 'running' | 'done' | 'failed' | 'stopped'

export interface InvestigationState {
  phase: InvestigationPhase
  steps: TurnStep[]
  answer: InvestigationAnswer | null
  error: string | null
}

const IDLE: InvestigationState = { phase: 'idle', steps: [], answer: null, error: null }

/** The status line's words, from the newest running step or the outcome. */
export function investigationStatus(state: InvestigationState): TurnStatus | null {
  if (state.phase === 'idle') return null
  if (state.phase === 'stopped') return { label: 'Investigation stopped', state: 'done' }
  if (state.phase === 'failed') return { label: 'The investigation did not complete', state: 'failed' }
  if (state.phase === 'done') {
    const proposal = state.answer?.proposal
    // A case a person already approved resolves to that review, not a new one.
    const label = !proposal
      ? 'Investigation complete'
      : proposal.status === 'approved' ? 'Already approved' : 'Waiting for approval'
    return { label, state: 'done' }
  }
  const running = [...state.steps].reverse().find(step => step.status === 'running')
  return { label: running?.label ?? 'Investigator reads the case', state: 'working' }
}

export function useInvestigation(customerId: string) {
  const [state, setState] = useState<InvestigationState>(IDLE)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => {
    setState(IDLE)
    return () => {
      controller.current?.abort()
      controller.current = null
    }
  }, [customerId])

  const start = useCallback(async (): Promise<InvestigationAnswer | null> => {
    if (controller.current) return null
    const abort = new AbortController()
    controller.current = abort
    // An aborted run belongs to a client or a Stop that has already moved on.
    const live = () => !abort.signal.aborted && controller.current === abort
    setState({ phase: 'running', steps: [], answer: null, error: null })
    try {
      const answer = await streamInvestigation(
        customerId,
        step => { if (live()) setState(current => ({ ...current, steps: upsertStep(current.steps, step) })) },
        answer => { if (live()) setState(current => ({ ...current, answer })) },
        abort.signal,
      )
      if (!live()) return null
      setState(current => ({
        ...current,
        phase: answer.status === 'failed' ? 'failed' : 'done',
        answer,
        error: answer.error,
      }))
      return answer
    } catch (reason) {
      if (!live()) return null
      const code = reason instanceof OperatorApiError ? reason.code : 'operator_unavailable'
      setState(current => ({ ...current, phase: 'failed', error: code }))
      return null
    } finally {
      if (controller.current === abort) controller.current = null
    }
  }, [customerId])

  const stop = useCallback(() => {
    const running = controller.current
    if (!running) return
    running.abort()
    controller.current = null
    setState(current => ({ ...current, phase: 'stopped', error: null }))
  }, [])

  return { ...state, status: investigationStatus(state), start, stop }
}
