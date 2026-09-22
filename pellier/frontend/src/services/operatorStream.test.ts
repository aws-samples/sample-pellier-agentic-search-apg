import { afterEach, describe, expect, it, vi } from 'vitest'

import { streamConciergeTurn } from './operator'

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('operator concierge stream', () => {
  it('keeps durable answers distinct from observable work steps', async () => {
    const payload = [
      frame('step', {
        kind: 'client',
        label: 'Client record loaded',
        source: 'Local PostgreSQL',
        status: 'complete',
      }),
      frame('answer', {
        turnId: 'turn-1',
        sessionId: 'sess-1',
        status: 'complete',
        replayed: false,
        summary: 'The client has one open service issue.',
        workflow: 'client_summary',
      }),
      frame('complete', {
        turnId: 'turn-1',
        sessionId: 'sess-1',
        status: 'complete',
        replayed: false,
        summary: 'The client has one open service issue.',
      }),
    ].join('')
    const chunks = [new TextEncoder().encode(payload)]
    let index = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          body: {
            getReader: () => ({
              read: () =>
                Promise.resolve(
                  index < chunks.length
                    ? { value: chunks[index++], done: false }
                    : { value: undefined, done: true },
                ),
            }),
          },
        } as unknown as Response),
      ),
    )

    const steps: string[] = []
    const answers: string[] = []
    const complete = await streamConciergeTurn(
      'CUST-JESSICA',
      'sess-1',
      'Summarize this client',
      'transport-1',
      (step) => steps.push(step.source),
      (answer) => answers.push(answer.summary),
    )

    expect(fetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      credentials: 'include', headers: expect.objectContaining({ Accept: 'text/event-stream' }),
    }))
    expect(steps).toEqual(['Local PostgreSQL'])
    expect(answers).toEqual(['The client has one open service issue.'])
    expect(complete.summary).toBe('The client has one open service issue.')
  })
})
