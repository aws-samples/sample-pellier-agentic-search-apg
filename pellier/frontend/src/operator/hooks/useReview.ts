/**
 * One review, and the three things a person can do to it.
 *
 * Approve records a decision and performs no mutation. Execute asks whether
 * the system may carry the approved credit out, which is a separate question
 * with its own answer. After each, the record is re-read from the server: the
 * decision's authoritative shape, the stored receipt and the counted rows all
 * come from there, never from local state.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  confirmReview,
  declineReview,
  executeReview,
  fetchReview,
  OperatorApiError,
  type OperatorExecutionResult,
  type OperatorReviewDetail,
} from '../../services/operator'

export type ReviewBusy = 'approving' | 'declining' | 'executing' | null

export interface ReviewController {
  detail: OperatorReviewDetail | null
  error: string | null
  busy: ReviewBusy
  /** The last execution response of THIS session; the durable record is in `detail`. */
  execution: OperatorExecutionResult | null
  decisionError: string | null
  decisionErrorMissing: readonly string[]
  approve: () => Promise<void>
  decline: () => Promise<void>
  execute: () => Promise<void>
  reload: () => Promise<void>
}

export function useReview(reviewId: number | null): ReviewController {
  const [detail, setDetail] = useState<OperatorReviewDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<ReviewBusy>(null)
  const [execution, setExecution] = useState<OperatorExecutionResult | null>(null)
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [decisionErrorMissing, setDecisionErrorMissing] = useState<readonly string[]>([])
  const active = useRef(true)

  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])

  const reload = useCallback(async () => {
    if (reviewId === null || !Number.isFinite(reviewId)) {
      setDetail(null)
      setError(reviewId === null ? null : 'review_not_found')
      return
    }
    try {
      const fresh = await fetchReview(reviewId)
      if (!active.current) return
      if (fresh.review.reviewId !== reviewId) throw new OperatorApiError('review_mismatch', 500)
      setDetail(fresh)
      setError(null)
    } catch (reason) {
      if (!active.current) return
      setError(reason instanceof OperatorApiError ? reason.code : 'operator_unavailable')
    }
  }, [reviewId])

  useEffect(() => {
    setDetail(null)
    setExecution(null)
    setDecisionError(null)
    setDecisionErrorMissing([])
    void reload()
  }, [reload])

  const run = useCallback(async (kind: Exclude<ReviewBusy, null>, work: () => Promise<unknown>) => {
    if (!detail || busy) return
    setBusy(kind)
    setDecisionError(null)
    setDecisionErrorMissing([])
    try {
      await work()
    } catch (reason) {
      if (!active.current) return
      setDecisionError(reason instanceof OperatorApiError ? reason.code : 'operator_unavailable')
      setDecisionErrorMissing(reason instanceof OperatorApiError ? reason.missing : [])
    } finally {
      if (active.current) setBusy(null)
      // The server owns the outcome. Re-read it whether the call succeeded or not.
      await reload()
    }
  }, [busy, detail, reload])

  const approve = useCallback(
    () => run('approving', () => confirmReview(detail!.review.reviewId, detail!.review.actionHash)),
    [detail, run],
  )
  const decline = useCallback(
    () => run('declining', () => declineReview(detail!.review.reviewId)),
    [detail, run],
  )
  const execute = useCallback(
    () => run('executing', async () => {
      const outcome = await executeReview(detail!.review.reviewId, detail!.review.actionHash)
      if (active.current) setExecution(outcome)
    }),
    [detail, run],
  )

  return { detail, error, busy, execution, decisionError, decisionErrorMissing, approve, decline, execute, reload }
}
