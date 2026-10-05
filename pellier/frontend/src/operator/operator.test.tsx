/**
 * The desk: the clients, Jessica's record, the investigation and the proposed
 * credit, against the API client mocked at the service boundary.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TurnStep } from '../components/turn/turnTypes'
import type { InvestigationAnswer } from '../services/operator'
import {
  ANSWER, ANSWERED_REQUEST, APPROVED_REVIEW, BOOK, DENIED_ON_RELOAD, EXECUTED_REVIEW, NOTHING_WRITTEN,
  OPEN_REQUEST, PENDING_REVIEW, QUEUE, RECORD, RECORDED_ONCE, UNWRITTEN_REVIEW, STEPS, WRITE_KEY, detail,
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

import ClientBook, { ClientList } from './surfaces/ClientBook'
import ClientRecord from './surfaces/ClientRecord'
import ReviewRecord from './surfaces/ReviewRecord'
import { ReviewList, reviewOutcome } from './surfaces/ReviewQueue'
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

  it('streams the Investigator and Planner steps, then shows the proposed credit waiting for approval', async () => {
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
    // The card for the review the Planner opened.
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
    expect(screen.getByTestId('operator-review-retry')).toHaveTextContent('Retry execution')
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
    expect(checks).toHaveTextContent('Zero store_credits rows and zero tool_audit rows for this key: the tool was never entered.')
    expect(screen.getByTestId('operator-credit-denied')).toBeInTheDocument()
    expect(screen.getByTestId('operator-review-execute')).toHaveTextContent('Execute again')
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

  it('after a reload, shows the stored denial as what the Gateway answered the desk', async () => {
    api.fetchReview.mockResolvedValue(detail(DENIED_ON_RELOAD, NOTHING_WRITTEN))
    renderAt('/operator/reviews/41', <ReviewRecord />)
    const checks = await screen.findByTestId('operator-credit-checks')
    expect(within(checks).getByText('DENY')).toBeInTheDocument()
    expect(checks).toHaveTextContent('What the Gateway answered the desk')
    expect(checks).toHaveTextContent('credit_limit_forbid')
    expect(within(checks).getByText('Not written')).toBeInTheDocument()
    expect(screen.getByTestId('operator-review-last-attempt')).toHaveTextContent('denied')
    expect(screen.getByTestId('operator-review-last-attempt')).toHaveTextContent('(stored)')
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

describe('the reviews list', () => {
  it('names where each credit stands', async () => {
    api.fetchReviewQueue.mockResolvedValue({ ...QUEUE, reviews: [PENDING_REVIEW, EXECUTED_REVIEW, UNWRITTEN_REVIEW], total: 3, pendingCount: 1 })
    renderAt('/operator/reviews', <ReviewList />)
    expect(await screen.findByTestId('operator-reviews')).toBeInTheDocument()
    const rows = screen.getAllByTestId('operator-review-41')
    expect(rows.map(r => r.getAttribute('data-outcome'))).toEqual(['Waiting for Nadia', 'Credited', 'Not written'])
    expect(screen.getByTestId('operator-reviews-count')).toHaveTextContent('1 waiting')
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
