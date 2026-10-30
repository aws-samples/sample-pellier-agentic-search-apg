/**
 * The desk: the clients, Jessica's record, the investigation and the proposed
 * credit, against the API client mocked at the service boundary.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TurnStep } from '../components/turn/turnTypes'
import type { InvestigationAnswer, OperatorReview } from '../services/operator'
import {
  ANSWER, ANSWERED_REQUEST, APPROVED_REVIEW, BOOK, DENIED_ON_RELOAD, EXECUTED_REVIEW, NOTHING_WRITTEN,
  RECEIPT_MISSING_RECORD, RECORDED_AFTER_A_FAILED_ATTEMPT,
  OPEN_REQUEST, PENDING_REVIEW, PROBE_REVIEW, QUEUE, RECORD, RECORDED_ONCE, UNWRITTEN_REVIEW, STEPS, WRITE_KEY,
  detail,
} from './fixtures'

const api = vi.hoisted(() => ({
  fetchClientBook: vi.fn(),
  fetchClientRecord: vi.fn(),
  fetchReview: vi.fn(),
  fetchReviewQueue: vi.fn(),
  confirmReview: vi.fn(),
  declineReview: vi.fn(),
  executeReview: vi.fn(),
  streamInvestigation: vi.fn(),
}))

vi.mock('../services/operator', async () => {
  const actual = await vi.importActual<typeof import('../services/operator')>('../services/operator')
  return { ...actual, ...api }
})

const auth = vi.hoisted(() => ({
  user: { sub: 'sub-nadia', email: 'nadia@pellier.example.com', username: 'nadia', givenName: 'nadia' } as { sub: string; email: string; username?: string; givenName?: string } | null,
  isAuthenticated: true,
  loading: false,
  authUnavailable: false,
  logout: vi.fn(),
}))

const providers = vi.hoisted(() => ({ surfaces: [] as string[] }))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => auth,
  useOptionalAuth: () => auth,
  AuthProvider: ({ children, surface }: { children: React.ReactNode; surface?: string }) => {
    providers.surfaces.push(surface ?? 'shopper')
    return children
  },
}))

import ClientBook, { ClientList, shortDate } from './surfaces/ClientBook'
import ClientRecord from './surfaces/ClientRecord'
import ReviewRecord from './surfaces/ReviewRecord'
import { ReviewList, reviewOutcome } from './surfaces/ReviewQueue'
import ProposedCreditCard, { gatewayDetail, splitDetail } from './components/ProposedCreditCard'
import { ReviewQueueContext } from './hooks/useReviewQueue'
import OperatorFrame, { operatorTitleForPath } from './shell/OperatorFrame'

function renderAt(path: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/operator/clients/:customerId" element={element} />
        <Route path="/operator/reviews/:reviewId" element={element} />
        <Route path="*" element={element} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchClientBook.mockResolvedValue(BOOK)
  api.fetchClientRecord.mockResolvedValue(RECORD)
  api.fetchReviewQueue.mockResolvedValue(QUEUE)
  api.fetchReview.mockResolvedValue(detail(PENDING_REVIEW))
  api.confirmReview.mockResolvedValue({ reviewId: 41, status: 'approved', humanState: 'confirmed', decidedBy: 'sub-nadia', decidedByName: 'nadia', decidedAt: null, assurance: APPROVED_REVIEW.assurance })
  api.declineReview.mockResolvedValue({ reviewId: 41, status: 'rejected', humanState: 'declined', decidedBy: 'sub-nadia', decidedByName: 'nadia', decidedAt: null, assurance: { human: 'DECLINED', policy: 'NOT_EVALUATED', aurora: 'NOT_REACHED', evidence: 'NO_EXECUTION' } })
  api.executeReview.mockResolvedValue({
    reviewId: 41, rail: 'gateway-mcp', executionTurnId: 'turn-execution-1', idempotencyKey: WRITE_KEY,
    actorPrincipal: 'sub-nadia', assurance: EXECUTED_REVIEW.assurance,
    notes: {}, tool: 'give_store_credit', result: { status: 'success', credit_id: 12, idempotent_replay: false }, record: RECORDED_ONCE,
  })
  api.streamInvestigation.mockImplementation(async (_id: string, onStep: (s: TurnStep) => void, onAnswer: (a: InvestigationAnswer) => void) => {
    for (const step of STEPS) onStep(step)
    onAnswer(ANSWER)
    return ANSWER
  })
})

describe('the clients', () => {
  it('lists open requests and the last order, with no tiers', async () => {
    renderAt('/operator', <ClientList />)
    expect(await screen.findByTestId('operator-book')).toBeInTheDocument()
    const jessica = screen.getByTestId('operator-client-jessica')
    expect(jessica).toHaveTextContent('Jessica Nakamura')
    expect(jessica).toHaveTextContent('1 open request')
    expect(jessica).toHaveTextContent('Two items went back, no credit yet')
    expect(jessica).toHaveTextContent('Waffle Bath Robe, Sage')
    expect(screen.getByTestId('operator-client-anna')).toHaveTextContent('Stoneware Pour-Over Set')
    expect(screen.queryByText(/silver|gold|member/i)).not.toBeInTheDocument()
    expect(screen.getByText('2 open requests')).toBeInTheDocument()
  })

  it('tells a signed-out reader to sign in as Nadia with her password', async () => {
    const { OperatorApiError } = await vi.importActual<typeof import('../services/operator')>('../services/operator')
    api.fetchClientBook.mockRejectedValueOnce(new OperatorApiError('authentication_required', 401))
    renderAt('/operator', <ClientList />)
    expect(await screen.findByTestId('operator-book-error')).toHaveTextContent('Staff sign-in required')
    expect(screen.getByTestId('operator-book-error')).toHaveTextContent(/Nadia with her password/)
    expect(screen.getByTestId('operator-state-sign-in')).toBeInTheDocument()
  })

  it('refuses a signed-in shopper without offering sign-in again', async () => {
    const { OperatorApiError } = await vi.importActual<typeof import('../services/operator')>('../services/operator')
    api.fetchClientBook.mockRejectedValueOnce(new OperatorApiError('operator_group_required', 403))
    renderAt('/operator', <ClientList />)
    expect(await screen.findByTestId('operator-book-error')).toHaveTextContent('Staff access required')
    expect(screen.queryByTestId('operator-state-sign-in')).not.toBeInTheDocument()
  })
})

describe("Jessica's record", () => {
  it('says there is no such client for an unknown id, not that the database failed', async () => {
    const { OperatorApiError } = await vi.importActual<typeof import('../services/operator')>('../services/operator')
    api.fetchClientRecord.mockRejectedValueOnce(new OperatorApiError('Unknown client: jessica', 404))
    renderAt('/operator/clients/jessica', <ClientRecord />)
    const state = await screen.findByTestId('operator-record-error')
    expect(state).toHaveTextContent('No such client')
    expect(state).toHaveTextContent('The client list is the current one.')
    expect(state).not.toHaveTextContent(/database/i)
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('shows the ticket, the orders with their return state, and no credit', async () => {
    renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    expect(await screen.findByTestId('operator-record')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Jessica Nakamura')
    const ticket = screen.getByTestId('operator-ticket')
    expect(ticket).toHaveTextContent('TKT-2026-3015')
    expect(ticket).toHaveTextContent('Two items went back, no credit yet')
    expect(within(ticket).getByTestId('status-tag')).toHaveTextContent('Open')
    expect(within(screen.getByTestId('operator-order-301')).getByTestId('status-tag')).toHaveTextContent('Returned')
    expect(within(screen.getByTestId('operator-order-302')).getByTestId('status-tag')).toHaveTextContent('Returned')
    expect(within(screen.getByTestId('operator-order-303')).getByTestId('status-tag')).toHaveTextContent('Delivered')
    expect(screen.getByTestId('operator-credits-none')).toHaveTextContent('No credit recorded.')
    expect(screen.getByTestId('operator-investigate')).toHaveTextContent('Investigate')
    // A plain link to the storefront in a new tab. It signs nobody in from a
    // URL: Jessica's card on the home page is the one click, into the shopper
    // session, so Nadia stays signed in here.
    const storefront = screen.getByTestId('operator-storefront-handoff')
    expect(storefront).toHaveTextContent('Open the storefront')
    expect(storefront).toHaveAttribute('href', '/')
    expect(storefront).toHaveAttribute('target', '_blank')
    expect(storefront).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('shows her open chat request with no amount, then the review that answered it', async () => {
    api.fetchClientRecord.mockResolvedValueOnce({ ...RECORD, requests: [OPEN_REQUEST] })
    const { unmount } = renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    const open = await screen.findByTestId('operator-credit-request')
    expect(within(open).getByTestId('status-tag')).toHaveTextContent('Open request')
    expect(open).toHaveTextContent('Store credit request, no amount')
    expect(open).not.toHaveTextContent('$')
    unmount()

    api.fetchClientRecord.mockResolvedValueOnce({ ...RECORD, requests: [ANSWERED_REQUEST] })
    renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    const answered = await screen.findByTestId('operator-credit-request')
    expect(within(answered).getByTestId('status-tag')).toHaveTextContent('Investigated')
    expect(within(answered).getByRole('link')).toHaveAttribute('href', '/operator/reviews/41')
  })

  it('streams the Investigator and Advisor steps, then shows the proposed credit waiting for approval', async () => {
    renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    fireEvent.click(await screen.findByTestId('operator-investigate'))
    expect(api.streamInvestigation).toHaveBeenCalledWith('CUST-JESSICA', expect.any(Function), expect.any(Function), expect.any(AbortSignal))
    expect(await screen.findByTestId('operator-brief')).toHaveTextContent('No store credit is recorded')
    // The step list merged by id: one row per step, the last status wins.
    fireEvent.click(screen.getByTestId('turn-fold'))
    const steps = screen.getAllByTestId('turn-step')
    expect(steps).toHaveLength(6)
    expect(steps.map(s => s.getAttribute('data-status'))).toEqual(['done', 'done', 'done', 'done', 'done', 'done'])
    expect(steps[1]).toHaveTextContent("Reading Jessica's tickets")
    expect(steps[1]).toHaveTextContent('1 open ticket: Two items went back, no credit yet')
    expect(steps[5]).toHaveTextContent('$100.00 credit proposed for 2 returned items, waiting for approval')
    expect(screen.getByTestId('turn-status')).toHaveTextContent('Waiting for approval')
    // The card for the review the Advisor opened.
    await waitFor(() => expect(api.fetchReview).toHaveBeenCalledWith(41))
    const card = await screen.findByTestId('operator-proposed-credit')
    expect(within(card).getByTestId('operator-credit-amount')).toHaveTextContent('$100.00')
    expect(within(card).getByText('Waiting for Nadia')).toBeInTheDocument()
    expect(within(card).getByTestId('operator-review-confirm')).toBeInTheDocument()
    expect(within(card).getByTestId('operator-review-decline')).toBeInTheDocument()
    expect(within(card).queryByTestId('operator-review-execute')).not.toBeInTheDocument()
  })

  it('says a case a person already approved resolves to that review', async () => {
    const approvedAnswer: InvestigationAnswer = { ...ANSWER, proposal: { ...ANSWER.proposal!, status: 'approved' } }
    api.streamInvestigation.mockImplementationOnce(async (_id: string, onStep: (s: TurnStep) => void, onAnswer: (a: InvestigationAnswer) => void) => {
      for (const step of STEPS) onStep(step)
      onAnswer(approvedAnswer)
      return approvedAnswer
    })
    api.fetchReview.mockResolvedValue(detail(EXECUTED_REVIEW, RECORDED_ONCE))
    renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    fireEvent.click(await screen.findByTestId('operator-investigate'))
    expect(await screen.findByTestId('turn-status')).toHaveTextContent('Already approved')
    const card = await screen.findByTestId('operator-proposed-credit')
    expect(within(card).queryByTestId('operator-review-confirm')).not.toBeInTheDocument()
    expect(await within(card).findByText('Recorded once')).toBeInTheDocument()
  })

  it('reports a failed investigation and proposes nothing', async () => {
    api.streamInvestigation.mockImplementationOnce(async (_id: string, onStep: (s: TurnStep) => void) => {
      onStep(STEPS[0])
      const { OperatorApiError } = await vi.importActual<typeof import('../services/operator')>('../services/operator')
      throw new OperatorApiError('investigation_failed', 500)
    })
    renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    fireEvent.click(await screen.findByTestId('operator-investigate'))
    expect(await screen.findByTestId('operator-investigation-error')).toHaveTextContent('did not complete')
    expect(screen.queryByTestId('operator-proposed-credit')).not.toBeInTheDocument()
    expect(api.fetchReview).not.toHaveBeenCalled()
  })

  it('follows an existing review after a refresh', async () => {
    api.fetchClientRecord.mockResolvedValue({ ...RECORD, reviews: [PENDING_REVIEW] })
    renderAt('/operator/clients/CUST-JESSICA', <ClientRecord />)
    const line = await screen.findByTestId('operator-record-review')
    expect(line).toHaveTextContent('Waiting for approval')
    expect(line).toHaveTextContent('$100.00 store credit')
    expect(within(line).getByRole('link', { name: 'Open the review' })).toHaveAttribute('href', '/operator/reviews/41')
    expect(await screen.findByTestId('operator-proposed-credit')).toBeInTheDocument()
  })
})

describe('the review record', () => {
  it('binds Approve to the exact fingerprint and re-reads the record', async () => {
    api.fetchReview.mockResolvedValueOnce(detail(PENDING_REVIEW)).mockResolvedValue(detail(APPROVED_REVIEW))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-confirm'))
    await waitFor(() => expect(api.confirmReview).toHaveBeenCalledWith(41, PENDING_REVIEW.actionHash))
    expect(await screen.findByText('Approved by Nadia')).toBeInTheDocument()
    expect(screen.getByTestId('operator-review-execute')).toHaveTextContent('Execute')
    expect(api.executeReview).not.toHaveBeenCalled()
    // Approval is not a policy verdict and not a row.
    const checks = screen.getByTestId('operator-credit-checks')
    expect(within(checks).getByText('Not evaluated yet')).toBeInTheDocument()
    expect(within(checks).getByText('Nothing written')).toBeInTheDocument()
  })

  it('names the recorded approver for every staff reader, with her portrait', async () => {
    const reader = auth.user
    auth.user = { sub: 'sub-other-staff', email: 'other@pellier.example.com', username: 'other' }
    try {
      api.fetchReview.mockResolvedValue(detail(APPROVED_REVIEW))
      renderAt('/operator/reviews/41', <ReviewRecord />)
      expect(await screen.findByText('Approved by Nadia')).toBeInTheDocument()
      const approval = screen.getByTestId('operator-credit-checks').querySelector('[data-check="approval"]')
      expect(approval?.querySelector('img')).not.toBeNull()
    } finally {
      auth.user = reader
    }
  })

  it('names the Lab 4 policy check as the probe review\'s origin, not the Advisor or Nadia', async () => {
    api.fetchReview.mockResolvedValue({ ...detail(PROBE_REVIEW, NOTHING_WRITTEN), orders: [] })
    renderAt('/operator/reviews/57', <ReviewRecord />)
    const line = 'Opened and confirmed by the Lab 4 policy check (probe data, covers no order)'
    expect(await screen.findByTestId('operator-review-requester')).toHaveTextContent(line)
    expect(screen.queryByText('the Advisor, on the desk')).toBeNull()
    const approval = screen.getByTestId('operator-credit-checks').querySelector('[data-check="approval"]')
    expect(approval).toHaveTextContent('No person approved it')
    expect(approval).toHaveTextContent(line)
    expect(approval?.querySelector('img')).toBeNull()
    expect(screen.queryByText(/Approved by/)).toBeNull()
    // The stored answer still reads as the Gateway gave it; the desk never executes probe data.
    expect(screen.getByTestId('operator-review-last-attempt')).toHaveTextContent('The Gateway answered: denied')
    expect(screen.queryByTestId('operator-review-execute')).toBeNull()
    expect(screen.queryByTestId('operator-review-retry')).toBeNull()
  })

  it('names a missing receipt beside a committed credit', async () => {
    const missing = { ...EXECUTED_REVIEW, assurance: { ...EXECUTED_REVIEW.assurance, evidence: 'RECEIPT_MISSING' as const } }
    api.fetchReview.mockResolvedValue(detail(missing, RECEIPT_MISSING_RECORD))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const checks = await screen.findByTestId('operator-credit-checks')
    expect(within(checks).getByText('Receipt missing')).toBeInTheDocument()
    expect(checks).toHaveTextContent('Credit #12 is in store_credits; no tool_audit row records the call that wrote it.')
    expect(within(checks).queryByText('Not written')).toBeNull()
  })

  it('keeps a failed attempt beside the row that applied the credit', async () => {
    api.fetchReview.mockResolvedValue(detail(EXECUTED_REVIEW, RECORDED_AFTER_A_FAILED_ATTEMPT))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const checks = await screen.findByTestId('operator-credit-checks')
    expect(within(checks).getByText('Recorded once')).toBeInTheDocument()
    expect(checks).toHaveTextContent('Credit #12 and tool_audit row #4051, once each.')
    expect(checks).toHaveTextContent('1 other attempt for this key did not apply; tool_audit keeps it.')
  })

  it('declines without a fingerprint and submits nothing', async () => {
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-decline'))
    await waitFor(() => expect(api.declineReview).toHaveBeenCalledWith(41))
    expect(api.confirmReview).not.toHaveBeenCalled()
    expect(api.executeReview).not.toHaveBeenCalled()
  })

  it('executes the approved credit and shows one credit and one audit row', async () => {
    api.fetchReview.mockResolvedValueOnce(detail(APPROVED_REVIEW)).mockResolvedValue(detail(EXECUTED_REVIEW, RECORDED_ONCE))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-execute'))
    await waitFor(() => expect(api.executeReview).toHaveBeenCalledWith(41, APPROVED_REVIEW.actionHash))
    const checks = await screen.findByTestId('operator-credit-checks')
    await waitFor(() => expect(within(checks).getByText('ALLOW')).toBeInTheDocument())
    expect(within(checks).getByText('Recorded once')).toBeInTheDocument()
    expect(checks).toHaveTextContent('Credit #12 and tool_audit row #4051')
    expect(screen.getByTestId('operator-credit-recorded')).toHaveTextContent('Credit #12 recorded for Jessica Nakamura')
    expect(screen.getByTestId('operator-review-retry')).toHaveTextContent('Replay with the same key')
    expect(screen.getByTestId('operator-review-receipt')).toHaveTextContent('gateway-mcp')
    expect(screen.getByTestId('operator-review-receipt')).toHaveTextContent(WRITE_KEY)
  })

  it('shows a Cedar denial from the execute response as DENY with nothing written for the key', async () => {
    api.fetchReview.mockResolvedValueOnce(detail(APPROVED_REVIEW)).mockResolvedValue(detail(UNWRITTEN_REVIEW, NOTHING_WRITTEN))
    api.executeReview.mockResolvedValueOnce({
      reviewId: 41, rail: 'gateway-mcp', executionTurnId: 'turn-execution-1', idempotencyKey: WRITE_KEY,
      actorPrincipal: 'sub-nadia', assurance: { human: 'CONFIRMED', policy: 'DENY', aurora: 'NOT_REACHED', evidence: 'POLICY_PROOF' },
      notes: { policy: 'Cedar denied the action; the tool was never entered.' }, tool: 'give_store_credit',
      result: { status: 'policy_denied' }, record: NOTHING_WRITTEN,
    })
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-execute'))
    const checks = await screen.findByTestId('operator-credit-checks')
    await waitFor(() => expect(within(checks).getByText('DENY')).toBeInTheDocument())
    expect(within(checks).getByText('Not written')).toBeInTheDocument()
    expect(checks).toHaveTextContent('No store_credits row and no tool_audit row for this key.')
    expect(checks).toHaveTextContent('The tool was never entered.')
    expect(screen.getByTestId('operator-credit-denied')).toBeInTheDocument()
    expect(screen.getByTestId('operator-credit-denied')).toHaveTextContent('No credit or audit row was found for this key.')
    expect(screen.getByTestId('operator-review-execute')).toHaveTextContent('Execute again')
  })

  it.each([null, { ...NOTHING_WRITTEN, readable: false }, RECORDED_ONCE])('does not infer database absence from a policy denial alone (%j)', async record => {
    api.fetchReview.mockResolvedValue(detail(DENIED_ON_RELOAD, record))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const denial = await screen.findByTestId('operator-credit-denied')
    expect(denial).toHaveTextContent('AgentCore Policy denied this attempt before the tool ran.')
    expect(denial).not.toHaveTextContent('Nothing was written')
    expect(denial).not.toHaveTextContent('No credit or audit row was found')
    expect(denial).toHaveTextContent(record?.readable
      ? 'The recorded rows for this key are shown above.'
      : 'The database record could not be verified.')
  })

  it('after a reload with no stored answer, says so and what the tables hold', async () => {
    api.fetchReview.mockResolvedValue(detail(UNWRITTEN_REVIEW, NOTHING_WRITTEN))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const checks = await screen.findByTestId('operator-credit-checks')
    expect(within(checks).getByText('Not stored')).toBeInTheDocument()
    expect(checks).toHaveTextContent('No answer from the Gateway is stored for this attempt.')
    expect(within(checks).getByText('Not written')).toBeInTheDocument()
    expect(screen.queryByTestId('operator-credit-denied')).not.toBeInTheDocument()
    expect(screen.getByTestId('operator-review-receipt')).toHaveTextContent('no row written')
    expect(screen.queryByTestId('operator-review-last-attempt')).not.toBeInTheDocument()
  })

  it('after a reload, shows the stored denial as the Gateway answer', async () => {
    api.fetchReview.mockResolvedValue(detail(DENIED_ON_RELOAD, NOTHING_WRITTEN))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const checks = await screen.findByTestId('operator-credit-checks')
    expect(within(checks).getByText('DENY')).toBeInTheDocument()
    expect(checks).toHaveTextContent('The Gateway answered: denied')
    expect(checks).toHaveTextContent('credit_limit_forbid')
    expect(within(checks).getByText('Not written')).toBeInTheDocument()
    const attempt = screen.getByTestId('operator-review-last-attempt')
    expect(attempt).toHaveTextContent('Last attempt')
    expect(attempt).toHaveTextContent('The Gateway answered: denied')
    expect(attempt).toHaveTextContent('(stored)')
  })

  it('after a reload, names a refusal as the desk, never as the Gateway', async () => {
    const refused: OperatorReview = {
      ...DENIED_ON_RELOAD,
      assurance: { human: 'CONFIRMED', policy: 'NOT_EVALUATED', aurora: 'NOT_REACHED', evidence: 'NO_EXECUTION' },
      execution: {
        ...DENIED_ON_RELOAD.execution!,
        notes: { policy: 'Refused by the desk: missing AGENTCORE_GATEWAY_URL, 2026-10-04 15:04 UTC. The desk sent nothing to the Gateway. tool_audit and store_credits show what ran and what was paid.' },
        lastAttempt: {
          ...DENIED_ON_RELOAD.execution!.lastAttempt!,
          outcome: 'refused', rail: 'refused', policy: 'NOT_EVALUATED', engineMode: null, matchingForbids: [],
          policyEngineId: null, policyDigest: null, detail: 'missing AGENTCORE_GATEWAY_URL',
          label: 'Refused by the desk: missing AGENTCORE_GATEWAY_URL',
        },
      },
    }
    api.fetchReview.mockResolvedValue(detail(refused, NOTHING_WRITTEN))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const attempt = await screen.findByTestId('operator-review-last-attempt')
    expect(attempt).toHaveTextContent('Refused by the desk: missing AGENTCORE_GATEWAY_URL')
    expect(attempt).not.toHaveTextContent('Gateway answered')
    expect(screen.getByTestId('operator-credit-checks')).not.toHaveTextContent('Gateway answered')
  })

  it('surfaces a governed refusal with what is missing', async () => {
    const { OperatorApiError } = await vi.importActual<typeof import('../services/operator')>('../services/operator')
    api.fetchReview.mockResolvedValue(detail(APPROVED_REVIEW))
    api.executeReview.mockRejectedValueOnce(new OperatorApiError('governed_rail_unavailable', 409, ['AGENTCORE_GATEWAY_URL']))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-execute'))
    expect(await screen.findByTestId('operator-review-decision-error')).toHaveTextContent('Missing: AGENTCORE_GATEWAY_URL')
  })
})

describe('after a decision', () => {
  it('moves keyboard focus to the next action when Approve goes away', async () => {
    api.fetchReview.mockResolvedValueOnce(detail(PENDING_REVIEW)).mockResolvedValue(detail(APPROVED_REVIEW))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const approve = await screen.findByTestId('operator-review-confirm')
    approve.focus()
    fireEvent.click(approve)
    const execute = await screen.findByTestId('operator-review-execute')
    await waitFor(() => expect(execute).toHaveFocus())
  })

  it('pulls focus to the card once after a decision, not on every later refresh', () => {
    const controller = (busy: 'approving' | null, review = APPROVED_REVIEW) => ({
      detail: detail(review), error: null, busy, execution: null, decisionError: null,
      decisionErrorMissing: [], approve: vi.fn(), decline: vi.fn(), execute: vi.fn(), reload: vi.fn(),
    })
    const { rerender } = render(<MemoryRouter><ProposedCreditCard controller={controller('approving')} /></MemoryRouter>)
    rerender(<MemoryRouter><ProposedCreditCard controller={controller(null)} /></MemoryRouter>)
    const execute = screen.getByTestId('operator-review-execute')
    expect(execute).toHaveFocus()

    execute.blur()
    rerender(<MemoryRouter><ProposedCreditCard controller={controller(null)} /></MemoryRouter>)
    expect(document.body).toHaveFocus()
  })

  it('announces a refused decision', async () => {
    const { OperatorApiError } = await import('../services/operator')
    api.confirmReview.mockRejectedValueOnce(new OperatorApiError('operator_group_required', 403))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-confirm'))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveAttribute('data-testid', 'operator-review-decision-error')
  })

  it('keeps the record on screen and offers Try again when the re-read fails', async () => {
    const { OperatorApiError } = await import('../services/operator')
    api.fetchReview
      .mockResolvedValueOnce(detail(PENDING_REVIEW))
      .mockRejectedValueOnce(new OperatorApiError('operator_unavailable', 503))
      .mockResolvedValue(detail(APPROVED_REVIEW))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-confirm'))
    const retry = await screen.findByRole('button', { name: 'Try again' })
    expect(screen.getByTestId('operator-review-record')).toBeInTheDocument()
    fireEvent.click(retry)
    expect(await screen.findByText('Approved by Nadia')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })
})

describe('the dates on the desk', () => {
  it('reads a timestamp as its UTC date, the zone the policy time is written in', () => {
    // Event 12: a review decided at 23:56 UTC read Oct 23 beside "2026-10-22 23:56 UTC".
    const zone = process.env.TZ
    process.env.TZ = 'Pacific/Auckland'
    try {
      expect(shortDate('2026-10-22T23:56:00Z')).toBe('Oct 22, 2026')
    } finally {
      if (zone === undefined) delete process.env.TZ
      else process.env.TZ = zone
    }
  })
})

describe('the reviews list', () => {
  it('names where each credit stands', async () => {
    api.fetchReviewQueue.mockResolvedValue({ ...QUEUE, reviews: [PENDING_REVIEW, EXECUTED_REVIEW, UNWRITTEN_REVIEW], total: 3, pendingCount: 1 })
    renderAt('/operator/reviews', <ReviewList />)
    expect(await screen.findByTestId('operator-reviews')).toBeInTheDocument()
    const rows = screen.getAllByTestId('operator-review-41')
    expect(rows.map(r => r.getAttribute('data-outcome'))).toEqual(['Waiting for approval', 'Credited', 'Not written'])
    expect(screen.getByTestId('operator-reviews-count')).toHaveTextContent('1 waiting for approval')
  })

  it("lists Jessica's chat request above the reviews: no amount, nothing to approve", async () => {
    api.fetchReviewQueue.mockResolvedValue({ ...QUEUE, requests: [OPEN_REQUEST], openRequestCount: 1 })
    renderAt('/operator/reviews', <ReviewList />)
    const row = await screen.findByTestId('operator-request-40')
    expect(row).toHaveAttribute('data-outcome', 'Open request')
    expect(row).toHaveTextContent('Store credit request, no amount')
    expect(row).not.toHaveTextContent('$')
    expect(row).toHaveAttribute('href', '/operator/clients/CUST-JESSICA')
    expect(within(row).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByTestId('operator-requests-count')).toHaveTextContent('1 open')
    expect(screen.getAllByTestId('operator-review-41')).toHaveLength(1)
  })

  it("lists one row per case: no Lab 4 probe, no request an investigation has answered", async () => {
    const { PROBE_REVIEW } = await import('./fixtures')
    const answered = { ...OPEN_REQUEST, requestId: 39, status: 'investigated' }
    api.fetchReviewQueue.mockResolvedValue({
      ...QUEUE, reviews: [PROBE_REVIEW, EXECUTED_REVIEW], total: 2, requests: [answered], openRequestCount: 0,
    })
    renderAt('/operator/reviews', <ReviewList />)
    expect(await screen.findByTestId('operator-reviews')).toBeInTheDocument()
    expect(screen.getAllByRole('link').map(link => link.getAttribute('href')))
      .toEqual([`/operator/reviews/${EXECUTED_REVIEW.reviewId}`])
    expect(screen.queryByTestId('operator-requests')).not.toBeInTheDocument()
  })

  it('says there is nothing to approve when only the probe exists', async () => {
    const { PROBE_REVIEW } = await import('./fixtures')
    api.fetchReviewQueue.mockResolvedValue({ ...QUEUE, reviews: [PROBE_REVIEW], total: 1 })
    renderAt('/operator/reviews', <ReviewList />)
    expect(await screen.findByTestId('operator-reviews-empty')).toBeInTheDocument()
  })

  it('never derives an outcome from the human decision alone', () => {
    expect(reviewOutcome(APPROVED_REVIEW).word).toBe('Approved')
    expect(reviewOutcome({ ...APPROVED_REVIEW, executionTurnId: 'turn-x' }).word).toBe('Outcome unverified')
    expect(reviewOutcome(EXECUTED_REVIEW).word).toBe('Credited')
    expect(reviewOutcome(UNWRITTEN_REVIEW).word).toBe('Not written')
    expect(reviewOutcome(DENIED_ON_RELOAD).word).toBe('DENY')
    const refused = { ...UNWRITTEN_REVIEW.assurance, policy: 'NOT_EVALUATED' as const }
    expect(reviewOutcome({ ...UNWRITTEN_REVIEW, assurance: refused }).word).toBe('Not written')
    expect(reviewOutcome({ ...EXECUTED_REVIEW, assurance: { ...EXECUTED_REVIEW.assurance, policy: 'DENY', aurora: 'NOT_REACHED', evidence: 'POLICY_PROOF' } }).word).toBe('DENY')
  })

  it('calls a committed credit with no receipt credited, never not written (review, 2026-10-22)', () => {
    const missing = { ...EXECUTED_REVIEW.assurance, evidence: 'RECEIPT_MISSING' as const }
    expect(reviewOutcome({ ...EXECUTED_REVIEW, assurance: missing }).word).toBe('Credited, receipt missing')
  })

  it('never calls the Lab 4 probe approved, even before its answer is stored', () => {
    const unanswered = { ...PROBE_REVIEW, assurance: APPROVED_REVIEW.assurance, execution: null, executionTurnId: null }
    expect(reviewOutcome(unanswered).word).toBe('Lab 4 probe')
    expect(reviewOutcome(PROBE_REVIEW).word).toBe('DENY')
  })
})

describe('the desk shell', () => {
  it('titles each route and shows Nadia with her portrait when she is signed in', async () => {
    expect(operatorTitleForPath('/operator')).toBe('Clients, Pellier Operator')
    expect(operatorTitleForPath('/operator/clients/CUST-JESSICA')).toBe('Client, Pellier Operator')
    expect(operatorTitleForPath('/operator/reviews')).toBe('Reviews, Pellier Operator')
    expect(operatorTitleForPath('/operator/reviews/41')).toBe('Review, Pellier Operator')
    render(
      <MemoryRouter initialEntries={['/operator']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />}>
            <Route index element={<ClientBook />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    const staff = await screen.findByTestId('operator-staff')
    expect(staff).toHaveTextContent('Nadia')
    // The desk reads the staff session, never the storefront's shopper session.
    expect(providers.surfaces).toContain('staff')
    expect(providers.surfaces).not.toContain('shopper')
    expect(staff.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/assets/personas/nadia-720.webp'))
    expect(await screen.findByTestId('operator-book')).toBeInTheDocument()
    expect(screen.getByTestId('operator-book-choose')).toHaveTextContent('Choose a client')
    expect(screen.getByTestId('operator-reviews-link-count')).toHaveTextContent('1')
  })

  it('refreshes the reviews rail when a decision lands, not on the next poll', async () => {
    api.fetchReview.mockResolvedValueOnce(detail(APPROVED_REVIEW)).mockResolvedValue(detail(EXECUTED_REVIEW, RECORDED_ONCE))
    render(
      <MemoryRouter initialEntries={['/operator/reviews/41']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />}>
            <Route path="reviews/:reviewId" element={<ReviewRecord />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('operator-review-41')).toHaveAttribute('data-outcome', 'Waiting for approval')
    expect(screen.getByTestId('operator-reviews-link-count')).toHaveTextContent('1')
    api.fetchReviewQueue.mockResolvedValue({ ...QUEUE, reviews: [EXECUTED_REVIEW], pendingCount: 0 })

    fireEvent.click(await screen.findByTestId('operator-review-execute'))

    await waitFor(() => expect(screen.getByTestId('operator-review-41')).toHaveAttribute('data-outcome', 'Credited'))
    expect(screen.getByTestId('operator-reviews-link-count')).toHaveTextContent('0')
    expect(api.fetchClientBook.mock.calls.length).toBeGreaterThan(1)
  })

  it('offers the password sign-in, never a staff chip, when nobody is signed in', async () => {
    auth.isAuthenticated = false
    auth.user = null
    try {
      render(
        <MemoryRouter initialEntries={['/operator']}>
          <Routes>
            <Route path="/operator" element={<OperatorFrame />}>
              <Route index element={<ClientBook />} />
            </Route>
          </Routes>
        </MemoryRouter>,
      )
      expect(await screen.findByTestId('operator-sign-in')).toHaveTextContent('Staff sign-in')
      expect(screen.queryByTestId('workshop-sign-in')).not.toBeInTheDocument()
    } finally {
      auth.isAuthenticated = true
      auth.user = { sub: 'sub-nadia', email: 'nadia@pellier.example.com', username: 'nadia', givenName: 'nadia' }
    }
  })
})

describe('the investigation status after a decision', () => {
  it('names the decision instead of the stale waiting status', async () => {
    const { decidedStatus } = await import('./investigation/InvestigationSteps')
    const waiting = { label: 'Waiting for approval', state: 'done' as const }
    const review = (humanState: string) =>
      ({ detail: { review: { humanState } } }) as unknown as Parameters<typeof decidedStatus>[1]
    expect(decidedStatus(waiting, review('confirmation_required'), true)).toEqual(waiting)
    expect(decidedStatus(waiting, review('confirmed'), true)).toEqual({ label: 'Approved', state: 'done' })
    expect(decidedStatus(waiting, review('declined'), true)).toEqual({ label: 'Declined', state: 'done' })
    expect(decidedStatus(waiting, null, true)).toEqual(waiting)
    const working = { label: 'Investigator reads the case', state: 'working' as const }
    expect(decidedStatus(working, review('confirmed'), true)).toEqual(working)
    // A case that resolved to a review someone had already approved keeps saying so.
    const already = { label: 'Already approved', state: 'done' as const }
    expect(decidedStatus(already, review('confirmed'), false)).toEqual(already)
  })
})

describe('the review a client record follows', () => {
  it('skips the Lab 4 probe while a real review exists', async () => {
    const { activeReview } = await import('./surfaces/ClientRecord')
    const { PROBE_REVIEW, EXECUTED_REVIEW, PENDING_REVIEW } = await import('./fixtures')
    // The check's probe is the newest review once it runs; Jessica's credit stays followed.
    expect(activeReview([PROBE_REVIEW, EXECUTED_REVIEW])).toBe(EXECUTED_REVIEW)
    // An open review still wins over a decided one.
    expect(activeReview([PROBE_REVIEW, EXECUTED_REVIEW, PENDING_REVIEW])).toBe(PENDING_REVIEW)
    // A record whose only review is the probe still shows it.
    expect(activeReview([PROBE_REVIEW])).toBe(PROBE_REVIEW)
    expect(activeReview([])).toBeNull()
  })
})

describe('the investigation refreshes the desk', () => {
  it('re-reads the review queue when an investigation opens a review', async () => {
    const refresh = vi.fn()
    render(
      <MemoryRouter initialEntries={['/operator/clients/CUST-JESSICA']}>
        <ReviewQueueContext.Provider value={{ queue: QUEUE, error: null, refreshing: false, updatedAt: null, refresh }}>
          <Routes>
            <Route path="/operator/clients/:customerId" element={<ClientRecord />} />
          </Routes>
        </ReviewQueueContext.Provider>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByTestId('operator-investigate'))
    await screen.findByTestId('operator-brief')
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))
  })
})

describe('the execution actions and their outcomes', () => {
  it('keeps one label for the first run and for the run after a DENY', async () => {
    api.fetchReview.mockResolvedValue(detail(APPROVED_REVIEW))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    expect(await screen.findByTestId('operator-review-execute')).toHaveTextContent(/^Execute$/)
    api.fetchReview.mockResolvedValue(detail(DENIED_ON_RELOAD, NOTHING_WRITTEN))
    api.executeReview.mockResolvedValueOnce({
      reviewId: 41, rail: 'gateway-mcp', executionTurnId: 'turn-execution-1', idempotencyKey: WRITE_KEY,
      actorPrincipal: 'sub-nadia', assurance: DENIED_ON_RELOAD.assurance,
      notes: {}, tool: 'give_store_credit', result: { status: 'policy_denied' }, record: NOTHING_WRITTEN,
    })
    fireEvent.click(screen.getByTestId('operator-review-execute'))
    await waitFor(() => expect(screen.getByTestId('operator-review-execute')).toHaveTextContent(/^Execute again$/))
  })

  it('shows a replay as its own neutral outcome that names the original credit', async () => {
    api.fetchReview.mockResolvedValue(detail(EXECUTED_REVIEW, RECORDED_ONCE))
    api.executeReview.mockResolvedValueOnce({
      reviewId: 41, rail: 'gateway-mcp', executionTurnId: 'turn-execution-2', idempotencyKey: WRITE_KEY,
      actorPrincipal: 'sub-nadia', assurance: EXECUTED_REVIEW.assurance,
      notes: {}, tool: 'give_store_credit', result: { status: 'success', credit_id: 12, idempotent_replay: true }, record: RECORDED_ONCE,
    })
    renderAt('/operator/reviews/41', <ReviewRecord />)
    fireEvent.click(await screen.findByTestId('operator-review-retry'))
    const replayed = await screen.findByTestId('operator-credit-replayed')
    expect(within(replayed).getByTestId('status-tag')).toHaveTextContent('Replayed, no new row')
    expect(within(replayed).getByTestId('status-tag')).toHaveAttribute('data-tone', 'pending')
    expect(replayed).toHaveTextContent('credit #12 already recorded')
    expect(screen.queryByTestId('operator-credit-recorded')).not.toBeInTheDocument()
  })

  it('says waiting for approval when no staff member is signed in', async () => {
    const signedIn = auth.user
    auth.user = null
    auth.isAuthenticated = false
    try {
      renderAt('/operator/reviews/41', <ReviewRecord />)
      const checks = await screen.findByTestId('operator-credit-checks')
      expect(within(checks).getByText('Waiting for approval')).toBeInTheDocument()
    } finally {
      auth.user = signedIn
      auth.isAuthenticated = true
    }
  })

  it('offers a copy control beside the write key', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    api.fetchReview.mockResolvedValue(detail(EXECUTED_REVIEW, RECORDED_ONCE))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const card = await screen.findByTestId('operator-proposed-credit')
    fireEvent.click(within(card).getByRole('button', { name: 'Copy write key' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(WRITE_KEY))
    expect(await within(card).findByRole('status')).toHaveTextContent('write key copied')
    expect(within(card).getByRole('button', { name: 'Copy write key' })).toBeInTheDocument()
  })
})

describe('check details', () => {
  it('splits the Gateway note into a verdict and a facts line', () => {
    const note = EXECUTED_REVIEW.execution!.notes.policy!
    expect(gatewayDetail(note)).toEqual({
      verdict: 'The Gateway answered: allowed.',
      note: 'Engine in ENFORCE, 2026-10-04 15:04 UTC. Evidence: tool_audit and store_credits.',
    })
    const denied = gatewayDetail(DENIED_ON_RELOAD.execution!.notes.policy!)
    expect(denied.verdict).toBe('The Gateway answered: denied. The tool never ran.')
    expect(denied.note).toContain('Forbid: credit_limit_forbid')
  })

  it('shows the LOG_ONLY caveat instead of a bare allowed', () => {
    const logOnly = 'The Gateway answered: allowed, 2026-10-04 15:04 UTC. The call went through and the tool ran, '
      + 'but the attachment read just before the call was LOG_ONLY, so that is not a decision. '
      + 'tool_audit and store_credits show what ran and what was paid.'
    expect(gatewayDetail(logOnly)).toEqual({
      verdict: 'The Gateway answered: allowed.',
      caveat: 'The call went through and the tool ran, but the attachment read just before the call was LOG_ONLY, '
        + 'so that is not a decision.',
      note: '2026-10-04 15:04 UTC. Evidence: tool_audit and store_credits.',
    })
    const unreadable = logOnly.replace('LOG_ONLY', 'unreadable').replace('2026-10-04 15:04 UTC', 'an earlier attempt')
    expect(gatewayDetail(unreadable).caveat).toContain('unreadable, so that is not a decision')
  })

  it('keeps every other backend Policy and Recorded sentence', () => {
    const notes = [
      'AgentCore Policy evaluated the action and permitted it.',
      'The gateway is LOG_ONLY, so the call returning is not a decision.',
      'The policy engine state could not be read, so no verdict is claimed.',
      'Cedar denied the action; the tool was never entered.',
      'This execution ran in process, so AgentCore Policy was not consulted. Only the managed Gateway rail produces a Cedar verdict.',
      'Refused by the desk: the governed rail was not ready, an earlier attempt. The desk sends nothing to the Gateway. '
        + 'tool_audit and store_credits show what ran and what was paid.',
      'Ran in process, 2026-10-04 15:04 UTC. No policy engine was asked. tool_audit and store_credits show what ran and what was paid.',
    ]
    for (const text of notes) {
      const detail = gatewayDetail(text)
      const shown = [detail.verdict, detail.caveat, detail.note].filter(Boolean).join(' ')
      for (const word of text.split(/\s+/).map(w => w.replace(/^\(|[.,;:)]+$/g, ''))) expect(shown).toContain(word)
    }
  })

  it('renders the caveat on the card beside an allowed verdict', async () => {
    const logOnly = 'The Gateway answered: allowed, 2026-10-04 15:04 UTC. The call went through and the tool ran, '
      + 'but the attachment read just before the call was LOG_ONLY, so that is not a decision. '
      + 'tool_audit and store_credits show what ran and what was paid.'
    api.fetchReview.mockResolvedValue(detail({
      ...EXECUTED_REVIEW,
      execution: { ...EXECUTED_REVIEW.execution!, notes: { policy: logOnly } },
    }, RECORDED_ONCE))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const card = await screen.findByTestId('operator-proposed-credit')
    expect(await within(card).findByTestId('operator-check-caveat')).toHaveTextContent('so that is not a decision')
  })

  it('splits text of any other shape on its first sentence', () => {
    expect(gatewayDetail('Something unexpected. It has two sentences.')).toEqual({
      verdict: 'Something unexpected.', note: 'It has two sentences.',
    })
    expect(splitDetail('One sentence only')).toEqual({ verdict: 'One sentence only' })
  })
})

describe('the keyboard route and the narrow order', () => {
  function renderDesk(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />}>
            <Route index element={<ClientBook />} />
            <Route path="clients/:customerId" element={<ClientRecord />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
  }

  it('offers skip links to the list, the record and the investigation', async () => {
    renderDesk('/operator/clients/CUST-JESSICA')
    await screen.findByTestId('operator-record')
    const nav = screen.getByRole('navigation', { name: 'Move around the desk' })
    expect(within(nav).getAllByRole('link').map(link => link.textContent)).toEqual([
      'Skip to the clients', 'Skip to the record', 'Skip to the investigation',
    ])
    fireEvent.click(within(nav).getByRole('link', { name: 'Skip to the investigation' }))
    expect(document.getElementById('op-aside')).toHaveFocus()
  })

  it('marks index routes so the list leads on a narrow window, and record routes so the record does', async () => {
    const { container, unmount } = renderDesk('/operator')
    await screen.findByTestId('operator-book')
    expect(container.querySelector('.op-desk')).toHaveAttribute('data-view', 'index')
    expect(screen.queryByRole('link', { name: 'Skip to the investigation' })).not.toBeInTheDocument()
    unmount()
    const record = renderDesk('/operator/clients/CUST-JESSICA')
    await screen.findByTestId('operator-record')
    expect(record.container.querySelector('.op-desk')).toHaveAttribute('data-view', 'record')
  })
})
