import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('chat service auth transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    fetchMock = vi.fn()
    global.fetch = fetchMock as unknown as typeof fetch
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('includes cookies on streaming chat requests', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        'data: {"type":"complete","response":{"response":"done","products":[],"suggestions":[]}}\n\n',
        { status: 200 },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    const updates: unknown[] = []

    const result = await sendChatMessageStreaming(
      'hello',
      [],
      (event) => updates.push(event),
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    expect(init).toMatchObject({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ Accept: 'text/event-stream' }),
    })
    expect(JSON.parse(init.body as string)).toMatchObject({
      response_mode: 'balanced',
    })
    expect(updates).toHaveLength(1)
    expect(result.response).toBe('done')
  })

  it('returns the durable Evidence Ledger from the terminal event', async () => {
    const ledger = {
      version: '1.0',
      authority: 'canonical-receipt-projection',
      principalScoped: true,
      turnId: 'turn-1',
      events: [],
      evidenceSufficiency: [],
    }
    fetchMock.mockResolvedValueOnce(
      new Response(
        `data: ${JSON.stringify({
          type: 'complete',
          response: {
            response: 'done',
            products: [],
            evidence_ledger: ledger,
          },
        })}\n\n`,
        { status: 200 },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    const result = await sendChatMessageStreaming('hello', [], vi.fn())

    expect(result.evidence_ledger).toEqual(ledger)
  })

  it('sends the selected live agent configuration', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        'data: {"type":"complete","response":{"response":"done","products":[]}}\n\n',
        { status: 200 },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    await sendChatMessageStreaming(
      'find a gift',
      [],
      vi.fn(),
      undefined,
      true,
      'CUST-ANNA',
      'dispatcher',
      'fast',
    )

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body as string)).toMatchObject({
      guardrails_enabled: true,
      customer_id: 'CUST-ANNA',
      pattern: 'dispatcher',
      response_mode: 'fast',
    })
  })

  it('keeps prior rendered product identity in multi-turn requests', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        'data: {"type":"complete","response":{"response":"done","products":[]}}\n\n',
        { status: 200 },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    await sendChatMessageStreaming(
      'Keep that pair and confirm the total.',
      [
        {
          role: 'assistant',
          content: 'The Beeswax Pillar Candle and Brass Incense Holder make a quiet ritual.',
          timestamp: new Date(),
          products: [
            {
              id: 41,
              name: 'Beeswax Pillar Candle',
              price: 38,
              image: '',
              category: 'Home Decor',
              availability: { status: 'in_stock' },
            },
            {
              id: 42,
              name: 'Brass Incense Holder',
              price: 45,
              image: '',
              category: 'Home Decor',
              availability: { status: 'in_stock' },
            },
            {
              id: 43,
              name: 'Ceramic Ring Dish',
              price: 35,
              image: '',
              category: 'Home Decor',
              availability: { status: 'in_stock' },
            },
          ],
        },
      ],
      vi.fn(),
    )

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body as string).conversation_history).toEqual([
      {
        role: 'assistant',
        content: 'The Beeswax Pillar Candle and Brass Incense Holder make a quiet ritual.',
        products: [
          {
            id: 41,
            name: 'Beeswax Pillar Candle',
            price: 38,
            category: 'Home Decor',
            availability: 'in_stock',
          },
          {
            id: 42,
            name: 'Brass Incense Holder',
            price: 45,
            category: 'Home Decor',
            availability: 'in_stock',
          },
        ],
      },
    ])
  })

  it('sends zero, two, then four prior messages across a three-turn thread', async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(
          'data: {"type":"complete","response":{"response":"done","products":[]}}\n\n',
          { status: 200 },
        ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    const turn1User = {
      role: 'user' as const,
      content: 'Hand-thrown ceramics for a slower morning routine',
      timestamp: new Date(),
    }
    const turn1Assistant = {
      role: 'assistant' as const,
      content: 'The Stoneware Pour-Over Set establishes the ritual.',
      timestamp: new Date(),
    }
    const turn2User = {
      role: 'user' as const,
      content: 'What goes well with the pour-over set, keeping to the same materials and morning routine?',
      timestamp: new Date(),
    }
    const turn2Assistant = {
      role: 'assistant' as const,
      content: 'The Ceramic Tumblers and Woven Mat Set are the strongest companions.',
      timestamp: new Date(),
    }

    await sendChatMessageStreaming(turn1User.content, [], vi.fn())
    await sendChatMessageStreaming(
      turn2User.content,
      [turn1User, turn1Assistant],
      vi.fn(),
    )
    await sendChatMessageStreaming(
      'Without asking me to repeat the ritual or material, which pairing should I choose and why?',
      [turn1User, turn1Assistant, turn2User, turn2Assistant],
      vi.fn(),
    )

    expect(
      fetchMock.mock.calls.map(([, init]) =>
        JSON.parse(init.body as string).conversation_history,
      ),
    ).toEqual([
      [],
      [
        { role: 'user', content: turn1User.content, products: [] },
        { role: 'assistant', content: turn1Assistant.content, products: [] },
      ],
      [
        { role: 'user', content: turn1User.content, products: [] },
        { role: 'assistant', content: turn1Assistant.content, products: [] },
        { role: 'user', content: turn2User.content, products: [] },
        { role: 'assistant', content: turn2Assistant.content, products: [] },
      ],
    ])
  })

  it('classifies non-2xx responses using status and response detail', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Chat service not initialized' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      name: 'ChatServiceError',
      code: 'service_unavailable',
      status: 503,
      retryable: true,
    })
  })

  it('does not blame the shopper for a missing route', async () => {
    // A 404 means the endpoint is not there — a wrong backend target or a dev
    // proxy pointed at the other branch's port. Classing it as a request
    // validation failure told the shopper to reword a perfectly good question,
    // so it must degrade as service availability and stay retryable.
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Not Found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('Is the Hadley shirt at the Brooklyn warehouse?', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'service_unavailable',
      status: 404,
      retryable: true,
    })
  })

  it('still classifies real request validation as invalid_request', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'customer_id failed pattern check' }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'invalid_request',
      status: 422,
    })
  })

  it('does not misclassify a bare 401 as a policy denial', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'HTTP 401 Unauthorized: invalid bearer token' }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'authentication_required',
      retryable: false,
    })
  })

  it('does not turn an infrastructure AccessDeniedException into a policy verdict', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: 'AccessDeniedException while invoking the configured model',
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'service_unavailable',
      status: 503,
    })
  })

  it('treats an unstructured HTTP 403 as an authentication boundary', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'not authorized' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'authentication_required',
      status: 403,
      retryable: false,
    })
  })

  it('rejects structured error events instead of returning fallback content', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        [
          'data: {"type":"content_delta","delta":"Starting..."}',
          'data: {"type":"error","code":"policy_denied","message":"Request blocked by the active policy.","retryable":false}',
          '',
        ].join('\n\n'),
        { status: 200 },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    const updates: unknown[] = []

    await expect(
      sendChatMessageStreaming('process this return', [], event => updates.push(event)),
    ).rejects.toMatchObject({
      code: 'policy_denied',
      retryable: false,
    })
    expect(updates).toHaveLength(2)
  })

  it('surfaces an expected workshop build state as a distinct failure', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        [
          'data: {"type":"build_required","code":"workshop_build_required","message":"Inventory Agent is intentionally unbuilt."}',
          'data: {"type":"complete","response":{"response":"Inventory Agent is intentionally unbuilt.","products":[],"suggestions":[],"success":false}}',
          '',
        ].join('\n\n'),
        { status: 200 },
      ),
    )

    const { sendChatMessageStreaming } = await import('./chat')
    const updates: Array<{ type?: string }> = []

    // The storefront never shows the participant wording to a shopper. The
    // build state surfaces as its own quiet failure card, keyed by the
    // backend's code so the Observatory and lab guide can name it.
    await expect(
      sendChatMessageStreaming(
        'Is the Hadley shirt in stock?',
        [],
        event => updates.push(event),
      ),
    ).rejects.toMatchObject({
      code: 'workshop_build_required',
      retryable: false,
      referenceId: 'workshop_build_required',
    })
    expect(updates.map(event => event.type)).toContain('build_required')
  })

  it('rejects a stream that closes before a complete event', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('data: {"type":"content_delta","delta":"Partial answer"}\n\n', {
        status: 200,
      }),
    )

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'stream_interrupted',
      retryable: true,
    })
  })

  it('normalizes fetch failures as retryable network errors', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    const { sendChatMessageStreaming } = await import('./chat')

    await expect(
      sendChatMessageStreaming('hello', [], vi.fn()),
    ).rejects.toMatchObject({
      code: 'network_error',
      retryable: true,
    })
  })
})
