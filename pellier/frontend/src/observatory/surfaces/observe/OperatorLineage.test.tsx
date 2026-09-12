import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import OperatorLineage from './OperatorLineage'

const HANDOFF = {
  schemaVersion: '1',
  trust: 'UNTRUSTED_SHOPPER_CONTEXT',
  checkpoint: 'WAITING_FOR_HUMAN',
  customerId: 'CUST-THEO',
  source: { sessionId: 'shopper-session', turnId: 'turn-shopper' },
  shopperRequest: 'My Wabi-Sabi Bowl arrived chipped.',
  routing: {
    specialist: 'customer_service',
    tools: ['get_return_policy', 'initiate_return'],
  },
  proposal: {
    reviewId: 8,
    action: 'initiate_return',
    actionHash: 'a'.repeat(64),
  },
}

const PENDING = {
  customerId: 'CUST-THEO',
  customerName: 'Theo',
  dataSource: 'Local PostgreSQL',
  handoff: HANDOFF,
  review: {
    reviewId: 8,
    customerId: 'CUST-THEO',
    customerName: 'Theo',
    action: 'initiate_return',
    status: 'pending',
    sourceTurnId: 'turn-shopper',
    executionTurnId: null,
    actionHash: 'a'.repeat(64),
  },
  orchestration: {
    graphId: 'operator-concierge-v1',
    pattern: 'strands-graph',
    execution: 'application-orchestrated',
    deploymentTarget: 'AgentCore Runtime',
    agents: ['case-investigator', 'resolution-planner'],
    executedNodes: [
      {
        nodeId: 'case-investigator',
        status: 'completed',
        durationMs: 8,
      },
      {
        nodeId: 'resolution-planner',
        status: 'completed',
        durationMs: 13,
      },
    ],
    checkpoint: {
      state: 'WAITING_FOR_HUMAN',
      reviewId: 8,
      actionHash: 'a'.repeat(64),
    },
  },
  execution: null,
}

function mockResponse(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      } as Response),
    ),
  )
}

function renderPage(initialEntry = '/observatory/operator-lineage') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <OperatorLineage />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('OperatorLineage', () => {
  it('shows managed build evidence without implying a human approved the remedy', async () => {
    mockResponse({
      ...PENDING,
      orchestration: {
        ...PENDING.orchestration,
        execution: 'agentcore-runtime',
        deploymentTarget: 'Amazon Bedrock AgentCore Runtime (Operator)',
        buildFingerprint: 'b'.repeat(64),
        fingerprintMatches: true,
        runtimeSessionId: 'operator-runtime-session-fixture',
      },
    })
    renderPage()
    expect(await screen.findByLabelText('Operator Runtime evidence'))
      .toHaveTextContent('Verified')
    expect(screen.getByText('b'.repeat(64))).toBeInTheDocument()
    expect(screen.getByText('operator-runtime-session-fixture')).toBeInTheDocument()
    expect(screen.getByTestId('operator-lineage-human-decision'))
      .toHaveAttribute('data-stage-state', 'waiting')
    expect(screen.getByTestId('operator-lineage-execution'))
      .toHaveAttribute('data-stage-state', 'waiting')
  })

  it('renders the handoff, two graph agents, and later human checkpoint', async () => {
    mockResponse(PENDING)
    renderPage()

    expect(await screen.findByText('My Wabi-Sabi Bowl arrived chipped.'))
      .toBeInTheDocument()
    expect(screen.getByText('Local PostgreSQL')).toBeInTheDocument()
    expect(screen.getByTestId('operator-lineage-checkpoint'))
      .toHaveAttribute('data-stage-state', 'complete')
    expect(screen.getByTestId('operator-lineage-case-investigator'))
      .toHaveTextContent('completed in 8ms')
    expect(screen.getByTestId('operator-lineage-resolution-planner'))
      .toHaveTextContent('completed in 13ms')
    expect(screen.getByTestId('operator-lineage-human-decision'))
      .toHaveAttribute('data-stage-state', 'waiting')
    expect(screen.getByTestId('operator-lineage-execution'))
      .toHaveAttribute('data-stage-state', 'waiting')
    expect(screen.getByText(/strands-graph · AgentCore Runtime target/i))
      .toBeInTheDocument()

    expect(fetch).toHaveBeenCalledWith(
      '/api/observatory/operator-lineage/CUST-THEO',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('loads the exact review handed off from Operator', async () => {
    mockResponse(PENDING)
    renderPage(
      '/observatory/operator-lineage?customer=CUST-THEO&review=8',
    )

    await screen.findByText('My Wabi-Sabi Bowl arrived chipped.')
    expect(fetch).toHaveBeenCalledWith(
      '/api/observatory/operator-lineage/CUST-THEO?review_id=8',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('shows a live-data empty state rather than fixture lineage', async () => {
    mockResponse({
      customerId: 'CUST-THEO',
      dataSource: 'Local PostgreSQL',
      handoff: null,
      review: null,
      orchestration: null,
      execution: null,
    })
    renderPage()

    expect(
      await screen.findByText(/No durable handoff is present for CUST-THEO yet/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/does not substitute fixture data/i))
      .toBeInTheDocument()
    expect(screen.queryByTestId('operator-lineage-case-investigator'))
      .not.toBeInTheDocument()
  })

  it('does not mistake an authentication failure for a missing handoff', async () => {
    mockResponse({ detail: 'authentication_required' }, 401)
    renderPage()

    expect(await screen.findByText('Operator sign-in required'))
      .toBeInTheDocument()
    expect(screen.getByText(/principal-scoped lineage/i)).toBeInTheDocument()
    expect(screen.queryByText(/No durable handoff is present/i))
      .not.toBeInTheDocument()
  })

  it('keeps human, policy, database, and evidence outcomes distinct', async () => {
    mockResponse({
      ...PENDING,
      review: { ...PENDING.review, status: 'approved' },
      execution: {
        latestReceipt: {
          policy_outcome: 'ALLOW',
          aurora_outcome: 'APPLIED',
          evidence_outcome: 'COMPLETE',
          rail: 'gateway-mcp',
        },
      },
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId('operator-lineage-human-decision'))
        .toHaveAttribute('data-stage-state', 'complete')
    })
    const execution = screen.getByTestId('operator-lineage-execution')
    expect(execution).toHaveAttribute('data-stage-state', 'complete')
    expect(execution).toHaveTextContent('Policy ALLOW')
    expect(execution).toHaveTextContent('PostgreSQL APPLIED')
    expect(execution).toHaveTextContent('evidence COMPLETE')
  })

  it('does not present a failed graph node as complete', async () => {
    mockResponse({
      ...PENDING,
      orchestration: {
        ...PENDING.orchestration,
        executedNodes: [
          {
            nodeId: 'case-investigator',
            status: 'failed',
            durationMs: 8,
          },
        ],
      },
    })
    renderPage()

    const investigator = await screen.findByTestId(
      'operator-lineage-case-investigator',
    )
    expect(investigator).toHaveAttribute('data-stage-state', 'stopped')
    expect(investigator).toHaveTextContent('failed in 8ms')
  })

  it('marks every unexecuted node stopped when the graph itself failed', async () => {
    mockResponse({
      ...PENDING,
      orchestration: {
        ...PENDING.orchestration,
        status: 'failed',
        executedNodes: [],
      },
    })
    renderPage()

    expect(await screen.findByTestId('operator-lineage-case-investigator'))
      .toHaveAttribute('data-stage-state', 'stopped')
    expect(screen.getByTestId('operator-lineage-resolution-planner'))
      .toHaveAttribute('data-stage-state', 'stopped')
  })

  it('renders a denied execution receipt as a stopped attempt', async () => {
    mockResponse({
      ...PENDING,
      review: { ...PENDING.review, status: 'approved' },
      execution: {
        latestReceipt: {
          policy_outcome: 'DENY',
          aurora_outcome: 'NOT_ATTEMPTED',
          evidence_outcome: 'COMPLETE',
          rail: 'gateway-mcp',
        },
      },
    })
    renderPage()

    const execution = await screen.findByTestId('operator-lineage-execution')
    expect(execution).toHaveAttribute('data-stage-state', 'stopped')
    expect(execution).toHaveTextContent('Governed execution attempt')
    expect(execution).toHaveTextContent('Policy DENY')
  })

  it('renders a completed log-only receipt as terminal rather than waiting', async () => {
    mockResponse({
      ...PENDING,
      review: { ...PENDING.review, status: 'approved' },
      execution: {
        latestReceipt: {
          policy_outcome: 'WOULD_DENY',
          aurora_outcome: 'PERMITTED',
          evidence_outcome: 'RECEIPTED',
          rail: 'log-only',
        },
      },
    })
    renderPage()

    expect(await screen.findByTestId('operator-lineage-execution'))
      .toHaveAttribute('data-stage-state', 'complete')
  })
})
