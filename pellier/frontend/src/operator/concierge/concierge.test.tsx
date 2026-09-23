/**
 * Operator Concierge: the behaviours a screenshot cannot show.
 *
 * What is worth pinning here is not that components render. It is that the surface
 * cannot lie: a suggestion appears only when real context supports it, a step is
 * never shown complete before the server said so, an empty memory read is not dressed
 * as a successful load, a draft is always labelled as unsent, and one client's
 * conversation can never appear under another client's record.
 */

import { describe, expect, it, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import ClientRecord from '../surfaces/ClientRecord'
import ConciergeConversation from './ConciergeConversation'
import {
  GUIDED_SERVICE_RECOVERY_PROMPTS,
  TEMPLATES,
  buildTemplateContext,
  rankTemplates,
} from './templates'
import type { OperatorClientRecord } from '../../services/operator'
import type { ConciergeMessage } from '../../services/operatorConcierge'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RECORD = {
  client: {
    customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura',
    membership: 'circle' as const, spend12mo: 3940, orderCount: 2,
    orderValue: 540, lastOrderAt: null, note: 'Open return dispute.',
    personaId: null, openTicketCount: 1, creditBalanceCents: 4000,
    creditBalance: '40.00',
    returnEvidence: {
      authoritativeReturnCount: 0,
      supportAssertsReturn: true,
      unconfirmedReturnAssertion: true,
    },
  },
  orders: [
    {
      orderId: 41, productId: '41', productName: 'Coral Lacquer Catchall',
      brand: 'Pellier Maison', price: 325.36, quantity: 1, placedAt: null,
      imageUrl: '/products/house-coral-lacquer-catchall.png',
    },
  ],
  tickets: [
    {
      ticketId: 'TKT-2026-3015', subject: 'Return received, refund disputed',
      status: 'pending' as const, channel: 'chat', lastNote: 'Awaiting decision.',
      openedAt: null, resolvedAt: null,
    },
  ],
  credits: [],
}

const CAPS = {
  capabilities: {
    client_read: { state: 'available', reason: 'local_read_path' },
    initiate_return: {
      state: 'temporarily_unavailable', reason: 'governed_action_unavailable',
    },
    issue_credit: { state: 'not_enabled', reason: 'capability_not_published' },
  },
  observedAt: '2026-08-26T23:48:44Z',
  source: 'agentcore',
  ttlSeconds: 60,
  governedActionsAvailable: false,
  cached: false,
}

const CONFIG = {
  composerEnabled: true,
  orchestrationAvailable: true,
  dataSource: 'Local PostgreSQL',
  // Matches `SUPPORTED_WORKFLOWS` from services/operator_concierge.py.
  supportedWorkflowKinds: ['client_summary', 'investigate_resolution',
                           'replacement_search', 'draft_client_note'],
  orchestration: 'available',
  note: 'Ask about this client.',
}

/** Every workflow the orchestrator implements, as the config route publishes them. */
const ALL_WORKFLOWS = CONFIG.supportedWorkflowKinds

/** One SSE frame, exactly as `routes/operator.py` writes it. */
function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

interface Wiring {
  /** Session replay returned by GET. Empty means a fresh thread. */
  messages?: unknown[]
  latestSessionId?: string | null
  /** Frames the stream emits, in order. */
  stream?: string[]
  /** Overrides the client id the session GET claims to be bound to. */
  boundCustomerId?: string
}

function wire(w: Wiring = {}): ReturnType<typeof vi.fn> {
  const messages = w.messages ?? []
  const fetchMock = vi.fn(
    (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const json = (body: unknown) =>
        Promise.resolve({
          ok: true, status: 200, json: () => Promise.resolve(body),
        } as Response)

      if (url.endsWith('/turns/stream')) {
        const chunks = (w.stream ?? []).map((s) => new TextEncoder().encode(s))
        let i = 0
        return Promise.resolve({
          ok: true,
          status: 200,
          body: {
            getReader: () => ({
              read: () =>
                Promise.resolve(
                  i < chunks.length
                    ? { value: chunks[i++], done: false }
                    : { value: undefined, done: true },
                ),
            }),
          },
        } as unknown as Response)
      }
      if (url.includes('/concierge/sessions/latest')) {
        return json({ sessionId: w.latestSessionId ?? null })
      }
      if (url.includes('/concierge/sessions') && method === 'POST') {
        return json({
          sessionId: 'sess-1', customerId: 'CUST-JESSICA',
          surface: 'operator_concierge', createdBy: 'op-1', messages: [],
          truncated: false,
        })
      }
      if (url.includes('/concierge/sessions/')) {
        return json({
          sessionId: 'sess-1',
          customerId: w.boundCustomerId ?? 'CUST-JESSICA',
          surface: 'operator_concierge', createdBy: 'op-1', messages,
          truncated: false,
        })
      }
      if (url.includes('/concierge/config')) return json(CONFIG)
      if (url.includes('/operator/capabilities')) return json(CAPS)
      if (url.includes('/operator/clients/')) return json(RECORD)
      return json({})
    },
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderRecord(entry = '/operator/clients/CUST-JESSICA') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/operator/clients/:customerId" element={<ClientRecord />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Templates: deterministic, from loaded state
// ---------------------------------------------------------------------------

describe('contextual suggestions', () => {
  it('offers nothing when no record has loaded', () => {
    // The alternative — showing four inviting rows before the data exists — is how a
    // suggestion becomes a dead end.
    expect(rankTemplates(buildTemplateContext(null), ALL_WORKFLOWS)).toEqual([])
  })

  it('ranks the unconfirmed service issue first', () => {
    const ctx = buildTemplateContext(RECORD as unknown as OperatorClientRecord)
    const ranked = rankTemplates(ctx, ALL_WORKFLOWS)
    expect(ranked[0].id).toBe('investigate_resolution')
    // And it says WHY, from the record rather than from a generic invitation.
    expect(ranked[0].description(ctx!)).toContain('TKT-2026-3015')
    expect(ranked[0].description(ctx!)).toContain('unconfirmed')
  })

  it('drops a suggestion whose context cannot be resolved', () => {
    const bare = {
      ...RECORD,
      client: { ...RECORD.client, returnEvidence: undefined },
      orders: [],
      tickets: [],
    }
    const ctx = buildTemplateContext(bare as unknown as OperatorClientRecord)
    const ids = rankTemplates(ctx, ALL_WORKFLOWS).map((t) => t.id)
    // No order and no ticket leaves nothing honest to offer.
    expect(ids).toEqual([])
  })

  it('offers no suggestion whose workflow the server does not publish', () => {
    // The structural fix for a real defect: a Replacement Search row shipped while its
    // request classified to `client_summary`, so the surface advertised one workflow and
    // ran another. Visibility is gated on the server's list, which makes an
    // unimplemented workflow unofferable rather than a thing to remember to hide.
    const ctx = buildTemplateContext(RECORD as unknown as OperatorClientRecord)
    const offered = rankTemplates(ctx, ['client_summary']).map((t) => t.workflow)
    expect(offered).toEqual(['client_summary'])
    // And an unread config offers nothing at all rather than everything.
    expect(rankTemplates(ctx, undefined)).toEqual([])
    expect(rankTemplates(ctx, [])).toEqual([])
  })

  it('advertises a workflow kind for every template', () => {
    for (const template of TEMPLATES) {
      expect(template.workflow).toBeTruthy()
      // The kind must be one the orchestrator publishes, or the row is a promise the
      // backend cannot keep.
      expect(ALL_WORKFLOWS).toContain(template.workflow)
    }
  })

  it('builds requests whose verb routes to the intended workflow', () => {
    // The cross-language half of the contract. `classify_workflow` in
    // services/operator_concierge.py routes on these verbs; if one is reworded here
    // without the router, every chip would quietly become a client summary.
    const ctx = buildTemplateContext(RECORD as unknown as OperatorClientRecord)!
    const verb: Record<string, string> = {
      investigate_resolution: 'Investigate',
      summarize_client: 'Summarize',
      draft_client_note: 'Draft',
      replacement_search: 'replacement',
    }
    for (const template of TEMPLATES) {
      expect(template.buildRequest(ctx)).toContain(verb[template.id])
    }
  })

  it('never infers a pronoun for a client', () => {
    // The record carries a name, not a gender. A template that guesses misgenders a
    // real person in a way the neutral form never does.
    const ctx = buildTemplateContext(RECORD as unknown as OperatorClientRecord)!
    for (const template of TEMPLATES) {
      const built = ` ${template.buildRequest(ctx).toLowerCase()} `
      for (const pronoun of [' her ', ' his ', ' she ', ' he ', " her's "]) {
        expect(built).not.toContain(pronoun)
      }
    }
  })

  it('renders one row per available template, with its reason', async () => {
    wire()
    renderRecord()
    const rail = await screen.findByTestId('operator-concierge-suggestions')

    expect(
      screen.getByTestId('operator-concierge-suggestion-investigate_resolution'),
    ).toBeInTheDocument()
    expect(rail.textContent).toContain('TKT-2026-3015')
    // Ranked, not alphabetical: the investigation leads.
    const buttons = rail.querySelectorAll('button[data-template]')
    expect(buttons[0].getAttribute('data-template')).toBe('investigate_resolution')
  })
})

// ---------------------------------------------------------------------------
// One turn, with real progress
// ---------------------------------------------------------------------------

describe('submitting a turn', () => {
  const STREAM = [
    frame('step', {
      kind: 'request', label: 'Request saved', source: 'Aurora',
      status: 'complete', durationMs: 12,
    }),
    frame('step', {
      kind: 'memory', label: 'Conversation context checked',
      source: 'AgentCore Memory', status: 'complete',
      result: 'No prior conversation context',
    }),
    frame('step', {
      kind: 'synthesis', label: 'Drafting client note',
      source: 'Amazon Bedrock', status: 'running',
    }),
    frame('complete', {
      turnId: 'turn-1', sessionId: 'sess-1', status: 'complete', replayed: false,
      summary: 'Thank you for your patience while we review your return.',
      workflow: 'draft_client_note',
      primaryLabel: 'Draft — not sent',
      primaryNote: 'Pellier does not send messages from this surface.',
      sections: [{
        id: 'operatorContext', label: 'Operator context', tone: 'context',
        body: 'One open ticket; no authoritative return record.',
      }],
      investigation: [], evidence: [], sources: [], proposedActions: [],
    }),
  ]

  const ANSWERED = [
    {
      messageId: 1, role: 'user' as const,
      content: 'Draft a short, sincere note to Jessica', turnId: 'turn-1',
      turnState: 'incomplete' as const, actorType: 'operator', artifact: null,
      artifactVersion: null, createdAt: null,
    },
    {
      messageId: 2, role: 'assistant' as const,
      content: 'Thank you for your patience while we review your return.',
      turnId: 'turn-1', turnState: 'complete' as const, actorType: 'assistant',
      artifact: {
        workflow: 'draft_client_note',
        primaryLabel: 'Draft — not sent',
        primaryNote: 'Pellier does not send messages from this surface.',
        sections: [{
          id: 'operatorContext', label: 'Operator context', tone: 'context',
          body: 'One open ticket; no authoritative return record.',
        }],
        investigation: [
          {
            kind: 'memory', label: 'Conversation context checked',
            source: 'AgentCore Memory', status: 'complete',
            result: 'No prior conversation context',
          },
        ],
        evidence: [], sources: [], proposedActions: [], products: [],
      },
      artifactVersion: 2, createdAt: null,
    },
  ]

  it('shows the request immediately and steps as the server reports them', async () => {
    wire({ stream: STREAM, messages: ANSWERED })
    renderRecord()
    const suggestion = await screen.findByTestId(
      'operator-concierge-suggestion-draft_client_note',
    )
    fireEvent.click(suggestion)

    // The request is a fact the moment it is sent, so it renders before any answer.
    const pending = await screen.findByTestId('operator-concierge-pending')
    expect(pending.textContent).toContain('Draft a short, sincere note')

    await waitFor(() => {
      expect(pending.textContent).toContain('Request saved')
    })
    // The in-flight row says in progress rather than naming a completed source.
    await waitFor(() => {
      expect(pending.querySelector('[data-step-status="running"]')).not.toBeNull()
    })
  })

  it('yields the orientation copy once there is a turn to read', async () => {
    // Steps only, no completion frame: the turn stays in flight, which is the
    // state this is about.
    wire({ stream: STREAM.slice(0, 2), messages: [] })
    renderRecord()

    // Before there is anything to read, the pane explains itself.
    const suggestion = await screen.findByTestId(
      'operator-concierge-suggestion-draft_client_note',
    )
    expect(screen.getByText(/Grounded in this client/)).toBeInTheDocument()

    fireEvent.click(suggestion)
    const pending = await screen.findByTestId('operator-concierge-pending')
    await waitFor(() => expect(pending.textContent).toContain('Request saved'))

    // While that turn is on screen the explanation stops holding reading space
    // in a pane the operator is already using.
    expect(screen.queryByText(/Grounded in this client/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Strands Graph path/)).not.toBeInTheDocument()
  })

  it('starts the guided Jessica case as a fresh streamed investigation', async () => {
    const fetchMock = wire({ stream: STREAM, messages: ANSWERED })
    renderRecord(
      '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title',
    )

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/turns/stream'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
    const streamCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith('/turns/stream'),
    )
    expect(JSON.parse(String(streamCall?.[1]?.body)).message).toBe(
      GUIDED_SERVICE_RECOVERY_PROMPTS[0],
    )
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes('/concierge/sessions/latest'),
      ),
    ).toBe(false)
  })

  it('opens the chat entry on saved history without starting another investigation', async () => {
    const fetchMock = wire({ latestSessionId: 'sess-1', messages: ANSWERED })
    renderRecord('/operator/clients/CUST-JESSICA#operator-concierge')
    await screen.findByText('Thank you for your patience while we review your return.')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    expect(screen.queryByTestId('operator-concierge-pending')).not.toBeInTheDocument()
  })

  it('offers the exact second guided turn after the investigation completes', async () => {
    const firstTurn = [
      {
        messageId: 1, role: 'user' as const,
        content: GUIDED_SERVICE_RECOVERY_PROMPTS[0], turnId: 'turn-1',
        turnState: 'incomplete' as const, actorType: 'operator', artifact: null,
        artifactVersion: null, createdAt: null,
      },
      {
        messageId: 2, role: 'assistant' as const,
        content: 'The records and the ticket disagree.', turnId: 'turn-1',
        turnState: 'complete' as const, actorType: 'assistant',
        artifact: {
          workflow: 'investigate_resolution',
          primaryLabel: 'Established by the records',
          primaryNote: '',
          sections: [], investigation: [], evidence: [], sources: [],
          proposedActions: [], products: [],
        },
        artifactVersion: 2, createdAt: null,
      },
    ]
    const fetchMock = wire({ stream: STREAM, messages: firstTurn })
    renderRecord(
      '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title',
    )

    fireEvent.click(
      await screen.findByRole('button', { name: 'Check the source records' }),
    )

    await waitFor(() => {
      const streamCalls = fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith('/turns/stream'),
      )
      expect(streamCalls).toHaveLength(2)
      expect(JSON.parse(String(streamCalls[1][1]?.body)).message).toBe(
        GUIDED_SERVICE_RECOVERY_PROMPTS[1],
      )
    })
  })

  it.each([false, true])('reveals the checkpoint after three completed guided turns, including retry=%s', async (retry) => {
    const messages: ConciergeMessage[] = GUIDED_SERVICE_RECOVERY_PROMPTS.flatMap((prompt, index) => [
      {
        messageId: index * 2 + 1, role: 'user' as const,
        content: prompt, turnId: `turn-${index + 1}`,
        turnState: 'incomplete' as const, actorType: 'operator', artifact: null,
        artifactVersion: null, createdAt: null,
      },
      {
        messageId: index * 2 + 2, role: 'assistant' as const,
        content: `Guided answer ${index + 1}`, turnId: `turn-${index + 1}`,
        turnState: 'complete' as const, actorType: 'assistant',
        artifact: {
          workflow: 'investigate_resolution',
          primaryLabel: 'Established by the records',
          primaryNote: '',
          sections: [], investigation: [], evidence: [], sources: [],
          proposedActions: [], products: [],
        },
        artifactVersion: 2, createdAt: null,
      },
    ])
    if (retry) {
      const successfulAnswer = { ...messages[5] }
      messages[5] = { ...messages[5], turnState: 'failed', content: 'Investigation could not be completed.' }
      messages.push(
        { ...messages[4], messageId: 7, turnId: 'turn-retry' },
        { ...successfulAnswer, messageId: 8, turnId: 'turn-retry' },
      )
    }
    wire({ stream: STREAM, messages })
    renderRecord(
      '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title',
    )

    expect(
      await screen.findByTestId('operator-concierge-human-checkpoint'),
    ).toBeInTheDocument()
    expect(
      screen.queryByTestId('operator-concierge-guided-next'),
    ).not.toBeInTheDocument()
  })

  it('labels a draft as unsent and keeps operator context separate', async () => {
    wire({ stream: STREAM, messages: ANSWERED })
    renderRecord()
    fireEvent.click(
      await screen.findByTestId('operator-concierge-suggestion-draft_client_note'),
    )

    const label = await screen.findByTestId('operator-concierge-primary-label')
    expect(label.textContent).toBe('Draft — not sent')
    const context = screen.getByTestId('operator-concierge-section-operatorContext')
    expect(context.textContent).toContain('Operator context')
    expect(context.textContent).toContain('no authoritative return record')
    // The pending block is gone once the durable turn is loaded.
    expect(screen.queryByTestId('operator-concierge-pending')).toBeNull()
  })

  it('offers no way to send the draft', async () => {
    wire({ stream: STREAM, messages: ANSWERED })
    renderRecord()
    fireEvent.click(
      await screen.findByTestId('operator-concierge-suggestion-draft_client_note'),
    )
    await screen.findByTestId('operator-concierge-primary-label')

    // There is no send capability on this surface, so there is no button implying one.
    for (const label of [/send/i, /email/i, /notify/i, /message client/i]) {
      expect(screen.queryByRole('button', { name: label })).toBeNull()
    }
  })

  it('does not present an empty memory read as a successful load', async () => {
    wire({ stream: STREAM, messages: ANSWERED })
    renderRecord()
    fireEvent.click(
      await screen.findByTestId('operator-concierge-suggestion-draft_client_note'),
    )
    const investigation = await screen.findByTestId(
      'operator-concierge-investigation',
    )
    expect(investigation.textContent).toContain('How this answer was built')
    expect(investigation.textContent).toContain('Conversation context checked')
    fireEvent.click(
      screen.getByRole('button', { name: /How this answer was built/i }),
    )
    expect(investigation.textContent).toContain('Conversation context checked')
    expect(investigation.textContent).toContain('AgentCore Memory')
    expect(investigation.textContent).not.toContain('0 prior turns')
  })

  it('renders no reasoning trace, only observable operations', async () => {
    wire({ stream: STREAM, messages: ANSWERED })
    renderRecord()
    fireEvent.click(
      await screen.findByTestId('operator-concierge-suggestion-draft_client_note'),
    )
    await screen.findByTestId('operator-concierge-primary-label')

    const text = document.body.textContent ?? ''
    for (const banned of ['Let me think', 'Thinking', 'chain of thought',
                          'reasoning', 'Analyzing the']) {
      expect(text.toLowerCase()).not.toContain(banned.toLowerCase())
    }
    // And no emoji anywhere on an operator surface.
    expect(text).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  it('makes the human checkpoint explicit before preparing a review', async () => {
    const fetchMock = wire({ latestSessionId: 'sess-1', messages: ANSWERED })
    renderRecord()

    const checkpoint = await screen.findByTestId(
      'operator-concierge-human-checkpoint',
    )
    expect(checkpoint).toHaveTextContent(
      'This prepares a review. It does not authorize or execute the return.',
    )
    expect(checkpoint).toHaveTextContent('You confirm or decline on the review in Action Queue')

    fireEvent.click(
      screen.getByRole('radio', { name: /Coral Lacquer Catchall/i }),
    )
    fireEvent.change(screen.getByLabelText('Return reason'), {
      target: { value: 'not_as_described' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'Prepare review' }),
    )

    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(([input]) =>
        String(input).endsWith('/turns/stream'),
      )
      expect(streamCall).toBeDefined()
      const body = JSON.parse(String(streamCall?.[1]?.body))
      expect(body.message).toContain('Prepare the return')
      expect(body.message).toContain('Coral Lacquer Catchall')
      expect(body.message).toContain("Customer's stated reason: not_as_described.")
      expect(body.message).toContain('for review')
    })
  })
})

// ---------------------------------------------------------------------------
// Resume, and the client binding
// ---------------------------------------------------------------------------

describe('resuming a conversation', () => {
  const HISTORY = [
    {
      messageId: 1, role: 'user' as const, content: 'Summarize Jessica',
      turnId: 'turn-0', turnState: 'incomplete' as const, actorType: 'operator',
      artifact: null, artifactVersion: null, createdAt: null,
    },
    {
      messageId: 2, role: 'assistant' as const,
      content: 'Two orders. One open ticket.', turnId: 'turn-0',
      turnState: 'complete' as const, actorType: 'assistant',
      artifact: { investigation: [], evidence: [], sources: [] },
      artifactVersion: 2, createdAt: null,
    },
  ]

  it('labels a failed investigation and retries its original request without asserting a result', () => {
    const retry = vi.fn()
    render(<ConciergeConversation
      messages={[
        HISTORY[0],
        { ...HISTORY[1], turnState: 'failed', content: 'Investigation could not be completed.',
          artifact: { primaryLabel: 'Established by the records' } },
      ]}
      onRetry={retry}
    />)
    expect(screen.getByTestId('operator-concierge-primary-label')).toHaveTextContent(
      'Investigation incomplete',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Retry this request' }))
    expect(retry).toHaveBeenCalledExactlyOnceWith(HISTORY[0].content)
    expect(screen.queryByText('Established by the records')).not.toBeInTheDocument()
  })

  it('replays the stored thread instead of the empty state', async () => {
    wire({ latestSessionId: 'sess-1', messages: HISTORY })
    renderRecord()
    await screen.findByTestId('operator-concierge-thread')

    expect(screen.getByText('Two orders. One open ticket.')).toBeInTheDocument()
    expect(screen.queryByTestId('operator-concierge-empty')).toBeNull()
  })

  it('does not mark an answered turn as not started', async () => {
    // The operator message's own `turnState` stays `incomplete` forever, because the
    // transcript is append-only. Completion is derived from the paired answer.
    wire({ latestSessionId: 'sess-1', messages: HISTORY })
    renderRecord()
    await screen.findByTestId('operator-concierge-thread')

    expect(screen.queryByTestId('operator-concierge-turnstate')).toBeNull()
  })

  it('never renders a session bound to another client', async () => {
    // A session id is not authority. The server binds it, and a mismatch resets.
    wire({
      latestSessionId: 'sess-1', messages: HISTORY, boundCustomerId: 'CUST-THEO',
    })
    renderRecord()
    await screen.findByTestId('operator-concierge-empty')

    expect(screen.queryByText('Two orders. One open ticket.')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Loading is not a governance state
// ---------------------------------------------------------------------------

describe('before server truth arrives', () => {
  it('never claims a capability is unavailable while it is still being read', async () => {
    // The distinction this whole surface argues for, applied to its own loading
    // state: "not yet read" is not "closed". Both the band and the composer used to
    // assert unavailability for about a second and then flip to enabled.
    let release = (): void => {}
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL): Promise<Response> => {
        const url = String(input)
        const json = (body: unknown) =>
          Promise.resolve({
            ok: true, status: 200, json: () => Promise.resolve(body),
          } as Response)
        if (url.includes('/concierge/config')) {
          return held.then(() => json(CONFIG))
        }
        if (url.includes('/concierge/sessions/latest')) return json({ sessionId: null })
        if (url.includes('/operator/capabilities')) return json(CAPS)
        if (url.includes('/operator/clients/')) return json(RECORD)
        return json({})
      }),
    )
    renderRecord()

    const input = await screen.findByTestId('operator-concierge-input')
    expect(input.getAttribute('placeholder')).toBe('Reading client context…')
    const band = screen.getByTestId('operator-concierge-state')
    expect(band.textContent).not.toMatch(/unavailable|not enabled|read only/i)

    release()
    await waitFor(() => {
      expect(input.getAttribute('placeholder')).toContain('Ask about this client')
    })
  })
})

// ---------------------------------------------------------------------------
// Replacement recommendations
// ---------------------------------------------------------------------------

describe('replacement recommendations', () => {
  const RECONCILED = {
    productId: '37', name: 'Wabi-Sabi Bowl', brand: 'Pellier Home',
    category: 'Home Decor', price: 65, imgUrl: '/products/theo-wabi-sabi-bowl.png',
    role: 'best_match',
    fitReasons: ['Same category as the original (Home Decor)',
                 '$100.00 below the $165.00 paid'],
    priceDeltaUsd: -100,
    inventoryEvidence: {
      status: 'reconciled_in_stock', availableQuantity: 50,
      authority: 'source_of_truth', reconciledToLedger: true,
      aggregateCacheStale: false, disagreements: [],
    },
    availabilitySentence: '50 units currently available across 3 locations.',
    retrievalEvidence: { rerankScore: 0.11, rrfScore: 0.03 },
  }

  const STALE = {
    ...RECONCILED,
    productId: '21', name: 'Beeswax Taper Candles', price: 48, role: 'alternative',
    imgUrl: '/products/anna-beeswax-taper-candles.png',
    inventoryEvidence: {
      status: 'reconciled_in_stock', availableQuantity: 41,
      authority: 'source_of_truth', reconciledToLedger: true,
      aggregateCacheStale: true, catalogCacheQuantity: 50,
      catalogLedgerQuantity: 41, disagreements: [],
    },
    availabilitySentence: '41 units currently available across 3 locations.',
  }

  const UNVERIFIED = {
    ...RECONCILED,
    productId: '60', name: 'Blown Glass Decanter', price: 210, role: 'alternative',
    imgUrl: '/products/maison-blown-glass-decanter.png',
    inventoryEvidence: {
      status: 'availability_not_verified', availableQuantity: null,
      reconciledToLedger: false, aggregateCacheStale: false, disagreements: [],
    },
    availabilitySentence: 'Availability not verified.',
  }

  function replacementTurn(replacement: unknown) {
    return [
      {
        messageId: 1, role: 'user' as const,
        content: 'For order #306, find a replacement for "Stoneware Pour-Over Set".',
        turnId: 'turn-r', turnState: 'incomplete' as const, actorType: 'operator',
        artifact: null, artifactVersion: null, createdAt: null,
      },
      {
        messageId: 2, role: 'assistant' as const,
        content: 'Three Home Decor options with reconciled availability.',
        turnId: 'turn-r', turnState: 'complete' as const, actorType: 'assistant',
        artifact: {
          workflow: 'replacement_search',
          sections: [{ id: 'comparison', label: 'How these compare', tone: 'neutral',
                       body: 'They differ in price.' }],
          recommendation: { body: 'Confirm which she prefers.' },
          investigation: [], evidence: [], sources: [], proposedActions: [],
          replacement,
        },
        artifactVersion: 2, createdAt: null,
      },
    ]
  }

  it('renders the product with backend price and availability', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({
        available: [RECONCILED], closeMatches: [],
        plan: { describeHardControls: ['price ≤ $189.75 (similar-price heuristic)'] },
        retrieval: { poolSize: 13, afterHardConstraints: 13, reranked: 12,
                     reconciledCount: 3, rerankApplied: true,
                     strategy: 'hybrid+rerank' },
        grounding: { resolved: true, matchedOn: 'named in the request' },
      }),
    })
    renderRecord()
    const card = await screen.findByTestId('operator-concierge-product-37')

    expect(card.textContent).toContain('Wabi-Sabi Bowl')
    expect(card.textContent).toContain('$65.00')
    // The availability sentence is the backend's, verbatim.
    expect(
      screen.getByTestId('operator-concierge-availability-37').textContent,
    ).toBe('50 units currently available across 3 locations.')
    // The SKU is present but subdued, so an operator can quote it.
    expect(card.textContent).toContain('37')
  })

  it('serves the 4:5 derivatives rather than the master', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({ available: [RECONCILED], closeMatches: [] }),
    })
    renderRecord()
    const card = await screen.findByTestId('operator-concierge-product-37')

    const avif = card.querySelector('source[type="image/avif"]')
    expect(avif?.getAttribute('srcSet') ?? '').toContain('-480.avif')
    expect(avif?.getAttribute('srcSet') ?? '').toContain('-960.avif')
    const img = card.querySelector('img')
    // 4:5, matching the catalog masters at 1122x1402.
    expect(Number(img?.getAttribute('width')) / Number(img?.getAttribute('height')))
      .toBeCloseTo(0.8, 3)
  })

  it('keeps unverified availability out of the available set', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({
        available: [RECONCILED], closeMatches: [UNVERIFIED],
        coverageNote: '',
      }),
    })
    renderRecord()
    const rail = await screen.findByTestId('operator-concierge-recommendations')

    expect(rail.textContent).toContain('Available replacements')
    expect(rail.textContent).toContain('availability not verified')
    // The unverified option never claims stock, and never claims to be out of stock.
    const unverified = screen.getByTestId('operator-concierge-product-60')
    expect(unverified.getAttribute('data-availability')).toBe('unverified')
    expect(unverified.textContent).toContain('Availability not verified.')
    expect(unverified.textContent).not.toMatch(/out of stock/i)
  })

  it('surfaces a stale aggregate cache without resolving it', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({ available: [STALE], closeMatches: [] }),
    })
    renderRecord()
    const card = await screen.findByTestId('operator-concierge-product-21')

    // Both numbers, so the discrepancy is visible rather than silently picked.
    expect(card.textContent).toContain('41 units currently available')
    expect(card.textContent).toContain('aggregate catalog cache reads 50')
    expect(card.textContent).toContain('ledger\u2019s 41')
  })

  it('shows at most three cards and no marketplace furniture', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({
        available: [RECONCILED, STALE, { ...UNVERIFIED, productId: '36',
          name: 'Ceramic Tumblers', price: 78,
          inventoryEvidence: RECONCILED.inventoryEvidence,
          availabilitySentence: '50 units currently available across 3 locations.' }],
        closeMatches: [],
      }),
    })
    renderRecord()
    const rail = await screen.findByTestId('operator-concierge-recommendations')

    expect(rail.querySelectorAll('.operator-concierge-product')).toHaveLength(3)
    for (const banned of [/\d+% off/i, /sale/i, /was \$/i, /save \$/i, /loyalty/i,
                          /points/i, /★/, /reviews?\b/i, /free shipping/i]) {
      expect(rail.textContent ?? '').not.toMatch(banned)
    }
    // No control that implies a write this surface cannot perform.
    for (const label of [/swap/i, /replace order/i, /reserve/i, /add to cart/i,
                         /apply credit/i]) {
      expect(screen.queryByRole('button', { name: label })).toBeNull()
    }
  })

  it('states inventory coverage rather than implying retrieval failed', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({
        available: [], closeMatches: [UNVERIFIED],
        coverageNote:
          'No candidate has current availability reconciled to the inventory ' +
          'ledger. Ledger coverage exists for 40 of 1,000 catalog products, so ' +
          'close matches are shown with availability unverified.',
      }),
    })
    renderRecord()
    const rail = await screen.findByTestId('operator-concierge-recommendations')

    expect(rail.textContent).toContain('40 of 1,000 catalog products')
    expect(rail.textContent).not.toMatch(/error|failed|unavailable service/i)
  })

  it('lists the order lines when the item could not be resolved', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({
        grounding: {
          resolved: false, reason: 'ambiguous_item_reference',
          candidates: [
            { orderId: 336, productId: '51', name: 'Camel Wool Overcoat', price: 895 },
            { orderId: 322, productId: '45', name: 'Tailored Wool Blazer', price: 346.38 },
          ],
        },
      }),
    })
    renderRecord()
    const clarify = await screen.findByTestId('operator-concierge-clarify')

    // The operator picks. No card is shown, because nothing was searched for.
    expect(clarify.textContent).toContain('#336')
    expect(clarify.textContent).toContain('Camel Wool Overcoat')
    expect(clarify.textContent).toContain('#322')
    expect(screen.queryByTestId('operator-concierge-recommendations')).toBeNull()
  })

  it('reports the retrieval receipt without becoming a search console', async () => {
    wire({
      latestSessionId: 'sess-1',
      messages: replacementTurn({
        available: [RECONCILED], closeMatches: [],
        plan: { describeHardControls: ['price ≤ $189.75 (similar-price heuristic)',
                                       'current availability reconciled to the ledger'] },
        retrieval: { poolSize: 13, afterHardConstraints: 13, reranked: 12,
                     reconciledCount: 3, rerankApplied: true,
                     strategy: 'hybrid+rerank' },
      }),
    })
    renderRecord()
    const receipt = await screen.findByTestId('operator-concierge-retrieval')

    expect(receipt.textContent).toContain('13 candidates')
    expect(receipt.textContent).toContain('12 reranked')
    expect(receipt.textContent).toContain('similar-price heuristic')
    expect(receipt.textContent).toContain('3 of 12')
    // Score contributions, FTS/pgvector internals and RRF math belong in the
    // Observatory, not in an operator's recommendation.
    for (const banned of [/ts_rank/i, /rrf_k/i, /cosine/i, /hnsw/i, /tsquery/i]) {
      expect(receipt.textContent ?? '').not.toMatch(banned)
    }
  })
})

// ---------------------------------------------------------------------------
// Proposed actions
// ---------------------------------------------------------------------------

describe('proposed actions', () => {
  const PROPOSAL = {
    tool: 'initiate_return',
    state: 'review_required',
    reviewId: 36,
    customer: { customerId: 'CUST-RACHEL' },
    order: { orderId: 325, placedAt: '2026-08-08T16:53:54Z' },
    product: {
      productId: '47', name: 'Vetiver Quietude', category: 'Beauty', price: 186,
      imgUrl: '/products/maison-vetiver-quietude.png',
    },
    material: {
      customer_id: 'CUST-RACHEL', product_id: 47, reason: 'not_as_described',
    },
    actionHash: '3a2a47ec4b7fbed09a0a1169390e19456fe0f7d1560326f6ebcd921d796171e8',
    executionCapability: {
      state: 'temporarily_unavailable', reason: 'governed_action_unavailable',
      executable: false,
    },
    reviewSourceTurnId: '',
    note: '',
  }

  function reviewDetail(humanState: string, assurance: Record<string, string>) {
    return {
      review: {
        reviewId: 36, customerId: 'CUST-RACHEL', customerName: 'Rachel Green',
        slug: 'rachel', personaId: null, action: 'initiate_return',
        parameters: PROPOSAL.material, status:
          humanState === 'confirmed' ? 'approved' : 'pending',
        humanState, assurance,
        sourceTurnId: 'turn-b134db08cf234b0aa07c19d4de741e3d', orderId: 325,
        issue: '', recommendation: {}, actionHash: PROPOSAL.actionHash,
        decidedBy: humanState === 'confirmed' ? 'operator-1' : null,
        requestedAt: null, decidedAt: null,
      },
      client: null, order: null, product: null, fulfilment: null,
    }
  }

  function proposalTurn(proposal: unknown) {
    return [
      {
        messageId: 1, role: 'user' as const,
        content: 'Prepare a return for review for the under-filled bottle.',
        turnId: 'turn-p', turnState: 'incomplete' as const, actorType: 'operator',
        artifact: null, artifactVersion: null, createdAt: null,
      },
      {
        messageId: 2, role: 'assistant' as const,
        content: 'A return action has been prepared for review against order #325.',
        turnId: 'turn-p', turnState: 'complete' as const, actorType: 'assistant',
        artifact: {
          workflow: 'investigate_resolution',
          sections: [], recommendation: { body: 'A person should review it.' },
          investigation: [], evidence: [], sources: [],
          proposedActions: proposal ? [proposal] : [],
        },
        artifactVersion: 2, createdAt: null,
      },
    ]
  }

  function wireWithReview(
    proposal: unknown,
    detail: unknown,
  ): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn((input: RequestInfo | URL): Promise<Response> => {
      const url = String(input)
      const json = (body: unknown) =>
        Promise.resolve({
          ok: true, status: 200, json: () => Promise.resolve(body),
        } as Response)
      if (url.includes('/operator/reviews/')) {
        return detail instanceof Error ? Promise.reject(detail) : json(detail)
      }
      if (url.includes('/concierge/sessions/latest')) return json({ sessionId: 'sess-1' })
      if (url.includes('/concierge/sessions/')) {
        return json({
          sessionId: 'sess-1', customerId: 'CUST-JESSICA',
          surface: 'operator_concierge', createdBy: 'op-1',
          messages: proposalTurn(proposal), truncated: false,
        })
      }
      if (url.includes('/concierge/config')) return json(CONFIG)
      if (url.includes('/operator/capabilities')) return json(CAPS)
      if (url.includes('/operator/clients/')) return json(RECORD)
      return json({})
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  it('states the prepared action, the human axis and execution separately', async () => {
    wireWithReview(PROPOSAL, reviewDetail('confirmation_required', {
      human: 'CONFIRMATION_REQUIRED', policy: 'PENDING',
      aurora: 'NOT_EVALUATED', evidence: 'PENDING',
    }))
    renderRecord()
    const card = await screen.findByTestId('operator-concierge-proposal')

    expect(card.textContent).toContain('Return review prepared')
    expect(card.textContent).toContain('Vetiver Quietude')
    expect(card.textContent).toContain('#325')
    expect(card.textContent).toContain('Not as described')
    // Two independent facts, two rows.
    expect(
      screen.getByTestId('operator-concierge-proposal-human').textContent,
    ).toBe('Required')
    expect(
      screen.getByTestId('operator-concierge-proposal-execution').textContent,
    ).toBe('Temporarily unavailable')
  })

  it('names the live human-review gate without claiming execution is authorized', async () => {
    wireWithReview({
      ...PROPOSAL,
      executionCapability: { state: 'review_required', executable: false },
    }, reviewDetail('confirmation_required', {
      human: 'CONFIRMATION_REQUIRED', policy: 'PENDING',
      aurora: 'NOT_EVALUATED', evidence: 'PENDING',
    }))
    renderRecord()
    expect(await screen.findByTestId('operator-concierge-proposal-execution')).toHaveTextContent(
      'Requires human confirmation',
    )
  })

  it('offers no control that would execute or approve in place', async () => {
    wireWithReview(PROPOSAL, reviewDetail('confirmation_required', {
      human: 'CONFIRMATION_REQUIRED', policy: 'PENDING',
      aurora: 'NOT_EVALUATED', evidence: 'PENDING',
    }))
    renderRecord()
    await screen.findByTestId('operator-concierge-proposal')

    for (const label of [/execute/i, /do it/i, /approve all/i, /confirm/i,
                         /run now/i, /apply/i]) {
      expect(screen.queryByRole('button', { name: label })).toBeNull()
    }
    // The one affordance: navigation to the canonical review surface.
    const link = screen.getByTestId('operator-concierge-proposal-review-link')
    expect(link.getAttribute('href')).toBe('/operator/reviews/36?client=CUST-JESSICA&session=sess-1&turn=turn-p')
    await waitFor(() => expect(link).toHaveTextContent('Review this return'))
    expect(screen.getByTestId('operator-concierge-proposal')).toHaveTextContent(
      'Review #36 is saved in Action Queue',
    )
    const handoff = screen.getByRole('navigation', { name: 'Prepared reviews' })
    expect(screen.getByTestId('operator-concierge-body')).not.toContainElement(handoff)
    expect(handoff.querySelector('a')).toHaveAttribute('href', link.getAttribute('href'))
    expect(handoff).not.toHaveTextContent(/pending|confirmed|completed/i)
  })

  it('does not invent a pending human decision when the current review cannot be read', async () => {
    wireWithReview(PROPOSAL, new Error('review_unavailable'))
    renderRecord()
    await waitFor(() =>
      expect(screen.getByTestId('operator-concierge-proposal-human')).toHaveTextContent(
        'Could not read current decision',
      ),
    )
    expect(screen.getByTestId('operator-concierge-proposal-review-link')).toHaveAttribute(
      'href', '/operator/reviews/36?client=CUST-JESSICA&session=sess-1&turn=turn-p',
    )
  })

  it('keeps review preparation available after a preparation failure', async () => {
    wireWithReview({ ...PROPOSAL, reviewId: null, state: 'could_not_prepare_review' }, null)
    renderRecord()
    const prepare = await screen.findByRole('button', { name: 'Prepare review' })
    // Still offered, and still waiting for the customer's stated reason.
    expect(prepare).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Return reason'), {
      target: { value: 'damaged' },
    })
    expect(prepare).toBeEnabled()
    expect(screen.getByTestId('operator-concierge-proposal-human')).toHaveTextContent(
      'No review prepared',
    )
  })

  it('renders the four axes from the review API, not from the artifact', async () => {
    // Confirmed by a human while the rail is closed: the state that proves the axes
    // move independently.
    wireWithReview(PROPOSAL, reviewDetail('confirmed', {
      human: 'CONFIRMED', policy: 'PENDING',
      aurora: 'NOT_EVALUATED', evidence: 'PENDING',
    }))
    renderRecord()
    await screen.findByTestId('operator-concierge-proposal')

    await waitFor(() => {
      expect(
        screen.getByTestId('operator-concierge-proposal-human').textContent,
      ).toBe('Confirmed')
    })
    // The existing component, reused verbatim — same test id the ReviewRecord
    // surface asserts against, which is the point of not rebuilding it.
    const assurance = screen.getByTestId('operator-assurance')
    expect(screen.getByTestId('operator-assurance-human').textContent)
      .toContain('Confirmed')
    // A confirmation did not become an authorization or a database effect.
    expect(screen.getByTestId('operator-assurance-policy').textContent)
      .toContain('Pending')
    expect(screen.getByTestId('operator-assurance-aurora').textContent)
      .toContain('Not evaluated')
    expect(screen.getByTestId('operator-assurance-evidence').textContent)
      .toContain('Pending')
    expect(assurance).toBeInTheDocument()
    // And execution is still closed.
    expect(
      screen.getByTestId('operator-concierge-proposal-execution').textContent,
    ).toBe('Temporarily unavailable')
  })

  it('says a review was already open rather than claiming authorship', async () => {
    wireWithReview(
      { ...PROPOSAL, state: 'review_already_open',
        reviewSourceTurnId: 'turn-an-earlier-one' },
      reviewDetail('confirmation_required', {
        human: 'CONFIRMATION_REQUIRED', policy: 'PENDING',
        aurora: 'NOT_EVALUATED', evidence: 'PENDING',
      }),
    )
    renderRecord()
    const card = await screen.findByTestId('operator-concierge-proposal')
    expect(card.textContent).toContain('already awaiting a decision')
  })

  it('offers no review link when no review was prepared', async () => {
    wireWithReview(
      { ...PROPOSAL, state: 'not_enabled', reviewId: null, actionHash: '',
        executionCapability: { state: 'not_enabled', executable: false } },
      reviewDetail('confirmation_required', {}),
    )
    renderRecord()
    const card = await screen.findByTestId('operator-concierge-proposal')

    expect(card.textContent).toContain('not published')
    expect(
      screen.queryByTestId('operator-concierge-proposal-review-link'),
    ).toBeNull()
    expect(
      screen.getByTestId('operator-concierge-proposal-execution').textContent,
    ).toBe('Not enabled')
  })

  it('renders no proposal for a read workflow', async () => {
    wireWithReview(null, reviewDetail('confirmation_required', {}))
    renderRecord()
    await screen.findByTestId('operator-concierge-thread')
    expect(screen.queryByTestId('operator-concierge-proposal')).toBeNull()
  })

  it('carries no decorative emoji', async () => {
    wireWithReview(PROPOSAL, reviewDetail('confirmation_required', {
      human: 'CONFIRMATION_REQUIRED', policy: 'PENDING',
      aurora: 'NOT_EVALUATED', evidence: 'PENDING',
    }))
    renderRecord()
    await screen.findByTestId('operator-concierge-proposal')
    expect(document.body.textContent ?? '').not.toMatch(/\p{Extended_Pictographic}/u)
  })
})


it('uses the active ticket when a resolved ticket precedes it', () => {
  const record = { ...RECORD, tickets: [
    { ...RECORD.tickets[0], ticketId: 'RESOLVED', subject: 'Old issue', status: 'resolved' },
    RECORD.tickets[0],
  ] }
  const context = buildTemplateContext(record as unknown as OperatorClientRecord)!
  expect(context.ticketId).toBe('TKT-2026-3015')
  expect(context.ticketSubject).toBe('Return received, refund disputed')
  expect(context.openTicketCount).toBe(1)
})
