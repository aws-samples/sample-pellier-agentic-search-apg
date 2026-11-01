import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { OperatorReviewDetail } from '../../services/operator'
import { PENDING_REVIEW, detail } from '../fixtures'

const api = vi.hoisted(() => ({
  fetchReview: vi.fn(),
  confirmReview: vi.fn(),
  declineReview: vi.fn(),
  executeReview: vi.fn(),
}))

vi.mock('../../services/operator', async () => {
  const actual = await vi.importActual<typeof import('../../services/operator')>('../../services/operator')
  return { ...actual, ...api }
})

import { useReview } from './useReview'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

const reviewDetail = (reviewId: number) => detail({ ...PENDING_REVIEW, reviewId })

describe('useReview', () => {
  it('drops a late response for the review the reader already left', async () => {
    const first = deferred<OperatorReviewDetail>()
    api.fetchReview.mockImplementation((id: number) =>
      id === 41 ? first.promise : Promise.resolve(reviewDetail(id)))

    const { result, rerender } = renderHook(({ id }) => useReview(id), { initialProps: { id: 41 } })
    rerender({ id: 42 })
    await waitFor(() => expect(result.current.detail?.review.reviewId).toBe(42))

    await act(async () => { first.resolve(reviewDetail(41)) })

    expect(result.current.detail?.review.reviewId).toBe(42)
    expect(result.current.error).toBeNull()
  })

  it('drops a late failure for the review the reader already left', async () => {
    const first = deferred<OperatorReviewDetail>()
    api.fetchReview.mockImplementation((id: number) =>
      id === 41 ? first.promise.then(() => { throw new Error('late') }) : Promise.resolve(reviewDetail(id)))

    const { result, rerender } = renderHook(({ id }) => useReview(id), { initialProps: { id: 41 } })
    rerender({ id: 42 })
    await waitFor(() => expect(result.current.detail?.review.reviewId).toBe(42))
    await act(async () => { first.resolve(reviewDetail(41)) })

    expect(result.current.error).toBeNull()
    expect(result.current.detail?.review.reviewId).toBe(42)
  })
})
