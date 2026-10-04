/**
 * The Operator API client: the investigation stream and the error mapping.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { OperatorApiError, executeReview, fetchClientRecord, streamInvestigation } from './operator'

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function streaming(payload: string, status = 200): void {
  const chunks = [new TextEncoder().encode(payload)]
  let index = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({
      ok: status < 400,
      status,
      body: {
        getReader: () => ({
          read: () => Promise.resolve(
            index < chunks.length ? { value: chunks[index++], done: false } : { value: undefined, done: true },
          ),
          cancel: () => Promise.resolve(),
          releaseLock: () => undefined,
        }),
      },
    } as unknown as Response)),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('streamInvestigation', () => {
  it('relays each step and the answer, and settles on complete', async () => {
    const answer = {
      turnId: 'turn-1', customerId: 'CUST-JESSICA', status: 'complete',
      investigation: { facts: ['Both went back.'], missing: ['No credit recorded.'] },
      planner: 'A $100.00 credit is proposed.', proposal: { reviewId: 41, amount: '100.00' },
      graph: { graphId: 'g', pattern: 'strands-graph', execution: 'in-process', modelId: 'm', nodes: [], durationMs: 1 },
      error: null,
    }
    streaming([
      frame('status', { type: 'status', label: 'Investigator reads the case' }),
      frame('step', { type: 'step', id: 'investigator', label: 'Investigator reads the case', status: 'running', tags: ['Investigator'] }),
      frame('step', { type: 'step', id: 'get_orders', label: "Reading Jessica's orders", status: 'done', finding: '3 orders on file', tags: ['Aurora'] }),
      frame('answer', answer),
      frame('complete', { ...answer, type: 'complete' }),
    ].join(''))
    const steps: string[] = []
    const answers: unknown[] = []

    const final = await streamInvestigation('CUST-JESSICA', step => steps.push(`${step.id}:${step.status}`), a => answers.push(a))

    expect(steps).toEqual(['investigator:running', 'get_orders:done'])
    expect(answers).toHaveLength(1)
    expect(final.proposal).toEqual({ reviewId: 41, amount: '100.00' })
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(String(url)).toMatch(/\/api\/operator\/clients\/CUST-JESSICA\/investigate$/)
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).credentials).toBe('include')
  })

  it('throws the backend error code when the stream ends in an error event', async () => {
    streaming(frame('error', { detail: 'investigation_failed' }))
    await expect(streamInvestigation('CUST-JESSICA', () => undefined, () => undefined))
      .rejects.toMatchObject({ code: 'investigation_failed' })
  })

  it('names the sign-in boundary when the desk refuses the stream', async () => {
    streaming('', 401)
    await expect(streamInvestigation('CUST-JESSICA', () => undefined, () => undefined))
      .rejects.toMatchObject({ code: 'operator_sign_in_required', status: 401 })
  })
})

describe('request errors', () => {
  it('maps a 403 to the staff sign-in state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false, status: 403, json: () => Promise.resolve({ detail: 'operator_group_required' }),
    } as unknown as Response)))
    const error = await fetchClientRecord('CUST-JESSICA').catch(e => e)
    expect(error).toBeInstanceOf(OperatorApiError)
    expect(error.code).toBe('operator_group_required')
    expect(error.needsOperatorSignIn).toBe(true)
  })

  it('carries what a governed refusal says is missing', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false, status: 409,
      json: () => Promise.resolve({ detail: { error: 'governed_rail_unavailable', missing: ['AGENTCORE_GATEWAY_URL'] } }),
    } as unknown as Response)))
    const error = await executeReview(41, 'h'.repeat(64)).catch(e => e)
    expect(error.code).toBe('governed_rail_unavailable')
    expect(error.missing).toEqual(['AGENTCORE_GATEWAY_URL'])
  })
})
