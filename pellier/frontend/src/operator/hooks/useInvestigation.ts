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

export type InvestigationPhase = 'idle' | 'running' | 'done' | 'failed'

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
  if (state.phase === 'failed') return { label: 'The investigation did not complete', state: 'failed' }
  if (state.phase === 'done') {
    return {
      label: state.answer?.proposal ? 'Waiting for approval' : 'Investigation complete',
      state: 'done',
    }
  }
  const running = [...state.steps].reverse().find(step => step.status === 'running')
  return { label: running?.label ?? 'Investigator reads the case', state: 'working' }
}

export function useInvestigation(customerId: string) {
  const [state, setState] = useState<InvestigationState>(IDLE)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => {
    setState(IDLE)
    return () => controller.current?.abort()
  }, [customerId])

  const start = useCallback(async (): Promise<InvestigationAnswer | null> => {
    if (controller.current) return null
    const abort = new AbortController()
    controller.current = abort
    setState({ phase: 'running', steps: [], answer: null, error: null })
    try {
      const answer = await streamInvestigation(
        customerId,
        step => setState(current => ({ ...current, steps: upsertStep(current.steps, step) })),
        answer => setState(current => ({ ...current, answer })),
        abort.signal,
      )
      setState(current => ({
        ...current,
        phase: answer.status === 'failed' ? 'failed' : 'done',
        answer,
        error: answer.error,
      }))
      return answer
    } catch (reason) {
      const code = reason instanceof OperatorApiError ? reason.code : 'operator_unavailable'
      setState(current => ({ ...current, phase: 'failed', error: code }))
      return null
    } finally {
      controller.current = null
    }
  }, [customerId])

  const stop = useCallback(() => controller.current?.abort(), [])

  return { ...state, status: investigationStatus(state), start, stop }
}
