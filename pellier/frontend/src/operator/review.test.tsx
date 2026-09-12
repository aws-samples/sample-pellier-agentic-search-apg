/**
 * Tests for the prepared-review surfaces.
 *
 * These assert semantic behaviour, not layout. The ones that matter most are
 * negative: that confirming never paints a policy ALLOW or an Aurora effect,
 * that a changed parameter puts the decision back in a person's hands, and that
 * no client value is hardcoded in the components. A screenshot cannot show any
 * of that, and each one is a way the surface could quietly start lying.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  act,
  render as renderBase,
  screen,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react'
import type { ReactElement } from 'react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { UIProvider } from '../contexts/UIContext'
import ReviewQueue, { relativeTime, outcomeLine, outcomeKind } from './surfaces/ReviewQueue'
import ReviewRecord, { issueLine } from './surfaces/ReviewRecord'
import ActionAssurance from './components/ActionAssurance'
import OperatorFrame from './shell/OperatorFrame'

function render(ui: ReactElement) {
  return renderBase(<UIProvider>{ui}</UIProvider>)
}

const authMock = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  user: null as null | { sub: string; email: string; givenName?: string },
  isAuthenticated: false,
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: authMock.user,
    isAuthenticated: authMock.isAuthenticated,
    loading: false,
    login: authMock.login,
    logout: authMock.logout,
  }),
}))

beforeEach(() => {
  authMock.user = null
  authMock.isAuthenticated = false
})

const THEO_HASH = 'a'.repeat(64)
const THEO_HANDOFF = {
  schemaVersion: '1',
  trust: 'UNTRUSTED_SHOPPER_CONTEXT',
  checkpoint: 'WAITING_FOR_HUMAN',
  customerId: 'CUST-THEO',
  source: {
    sessionId: 'persona-theo-session',
    turnId: 'turn-theo-abc',
  },
  shopperRequest: 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
  transcriptExcerpt: [
    {
      role: 'user' as const,
      content: 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
    },
  ],
  routing: {
    specialist: 'customer_service',
    tools: ['get_return_policy', 'initiate_return'],
  },
  proposal: {
    reviewId: 12,
    action: 'initiate_return',
    actionHash: THEO_HASH,
  },
}

const PENDING_REVIEW = {
  reviewId: 12,
  customerId: 'CUST-THEO',
  customerName: 'Theo',
  slug: 'theo',
  action: 'initiate_return',
  parameters: {
    customer_id: 'CUST-THEO',
    product_id: 37,
    reason: 'damaged',
  },
  status: 'pending' as const,
  humanState: 'confirmation_required' as const,
  assurance: {
    human: 'CONFIRMATION_REQUIRED' as const,
    policy: 'PENDING' as const,
    aurora: 'NOT_EVALUATED' as const,
    evidence: 'PENDING' as const,
  },
  sourceTurnId: 'turn-theo-abc',
  orderId: 305,
  issue: 'arrived damaged',
  recommendation: {
    primaryAction: 'initiate_return',
    rationale: 'The client owns this piece and reported it damaged on arrival.',
    secondarySuggestion: {
      action: 'issue_credit',
      amountCents: 2500,
      rationale: 'A judgment call, not an entitlement.',
    },
  },
  actionHash: THEO_HASH,
  decidedBy: null,
  requestedBySub: null,
  requesterKind: 'unverified' as const,
  requestedAt: null,
  decidedAt: null,
}

const REVIEW_DETAIL = {
  review: PENDING_REVIEW,
  shopperHandoff: THEO_HANDOFF,
  client: {
    customerId: 'CUST-THEO',
    name: 'Theo',
    membership: 'registered' as const,
    spend12mo: 940,
    note: 'Slow craft.',
    personaId: 'theo',
  },
  order: {
    orderId: 305,
    productId: '37',
    productName: 'Wabi-Sabi Bowl',
    brand: 'Pellier Maison',
    price: 65,
    quantity: 1,
    placedAt: '2026-08-18T00:00:00Z',
    imageUrl: '/p/37.png',
  },
  product: {
    productId: '37',
    name: 'Wabi-Sabi Bowl',
    brand: 'Pellier Maison',
    price: 65,
    catalogQuantity: 50,
    imageUrl: '/p/37.png',
  },
  fulfilment: {
    totalUnits: 35,
    replacementAvailable: true,
    warehouses: [
      {
        warehouseId: 'BK-01', displayName: 'Brooklyn', city: 'Brooklyn, NY',
        quantity: 20, shipWindowMin: 1, shipWindowMax: 2,
      },
      {
        warehouseId: 'ATX-02', displayName: 'Austin', city: 'Austin, TX',
        quantity: 15, shipWindowMin: 2, shipWindowMax: 4,
      },
    ],
  },
  returns: [
    {
      returnId: 28, productId: '31', reason: 'damaged', status: 'approved',
      requestedAt: '2026-08-19T00:00:00Z', resolvedAt: null,
    },
  ],
}

type MockFetchResult = { status?: number; body?: unknown } | undefined

function mockFetch(
  handler: (
    url: string,
    init?: RequestInit,
  ) => MockFetchResult | Promise<MockFetchResult>,
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const result = await handler(url, init)
      const status = result?.status ?? 200
      return {
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(result?.body ?? {}),
      } as Response
    }),
  )
}

function renderQueue() {
  return render(
    <MemoryRouter initialEntries={['/operator/reviews']}>
      <Routes>
        <Route path="/operator/reviews" element={<ReviewQueue />} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderRecord() {
  return render(
    <MemoryRouter initialEntries={['/operator/reviews/12']}>
      <Routes>
        <Route path="/operator/reviews/:reviewId" element={<ReviewRecord />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// The queue
// ---------------------------------------------------------------------------

describe('ReviewQueue', () => {
  it('distinguishes repeated reviews of the same item and keeps both saved outcomes', async () => {
    const reviews = [1, 3].map((reviewId) => ({
      ...PENDING_REVIEW, reviewId, productName: 'Wabi-Sabi Bowl',
      humanState: 'confirmed', status: 'approved',
    }))
    mockFetch(() => ({ body: { reviews, total: 2, pendingCount: 0 } }))
    renderQueue()
    for (const id of [1, 3]) {
      const row = await screen.findByTestId(`operator-review-${id}`)
      expect(row).toHaveTextContent(`Review #${id}, order #305`)
      expect(row).toHaveTextContent('Wabi-Sabi Bowl')
      expect(row).toHaveAttribute('href', `/operator/reviews/${id}`)
      expect(within(row).getByTestId('operator-review-outcome')).toBeVisible()
    }
  })

  it.each([
    ['shopper', 'shopper-sub', 'Requested by the verified shopper'],
    ['operator', 'operator-sub', 'Prepared by an operator'],
    ['unverified', 'other-shopper-sub', 'Requester signed in; customer ownership unverified'],
    ['unverified', null, 'Original requester identity not recorded'],
  ])('describes the original %s requester independently of Operator sign-in', async (kind, sub, label) => {
    authMock.isAuthenticated = true
    authMock.user = { sub: 'current-operator', email: 'operator@example.test' }
    mockFetch(() => ({ body: {
      reviews: [{ ...PENDING_REVIEW, requesterKind: kind, requestedBySub: sub }],
      total: 1, pendingCount: 1,
    } }))
    renderQueue()
    expect(await screen.findByTestId('operator-review-requester-flag')).toHaveTextContent(label!)
    expect(screen.queryByText('Requester not signed in')).not.toBeInTheDocument()
  })

  it('filters the queue by outcome and counts each outcome', async () => {
    mockFetch(() => ({
      body: { reviews: [PENDING_REVIEW], total: 1, pendingCount: 1 },
    }))
    renderQueue()
    await screen.findByTestId(`operator-review-${PENDING_REVIEW.reviewId}`)

    expect(screen.getByTestId('operator-outcome-filter-pending')).toHaveTextContent('1')
    expect(screen.getByTestId('operator-outcome-filter-declined')).toHaveTextContent('0')

    fireEvent.click(screen.getByTestId('operator-outcome-filter-declined'))
    expect(
      screen.queryByTestId(`operator-review-${PENDING_REVIEW.reviewId}`),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('operator-outcome-filter-declined'))
    expect(
      screen.getByTestId(`operator-review-${PENDING_REVIEW.reviewId}`),
    ).toBeInTheDocument()
  })

  it('shows a pending review so the operator finds Theo without searching', async () => {
    mockFetch(() => ({
      body: { reviews: [PENDING_REVIEW], total: 1, pendingCount: 1 },
    }))
    renderQueue()
    await screen.findByTestId('operator-reviews')

    expect(screen.getByTestId('operator-review-12')).toBeInTheDocument()
    expect(screen.getByText(/Theo/)).toBeInTheDocument()
    expect(screen.getByText('Confirmation required')).toBeInTheDocument()
  })

  it('identifies the saved review and order without relying on the client name', async () => {
    mockFetch(() => ({
      body: { reviews: [PENDING_REVIEW], total: 1, pendingCount: 1 },
    }))
    renderQueue()
    await screen.findByTestId('operator-reviews')

    expect(screen.getByText('Review #12, order #305')).toBeInTheDocument()
  })

  it('never shows a raw session or turn identifier in the queue', async () => {
    mockFetch(() => ({
      body: { reviews: [PENDING_REVIEW], total: 1, pendingCount: 1 },
    }))
    const { container } = renderQueue()
    await screen.findByTestId('operator-reviews')

    expect(container.textContent).not.toContain('turn-theo-abc')
    expect(container.textContent).not.toContain(THEO_HASH)
  })

  it('renders an explicit empty state instead of a blank page', async () => {
    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    renderQueue()
    expect(await screen.findByTestId('operator-reviews-empty')).toBeInTheDocument()
  })

  it('renders a loading state', () => {
    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    renderQueue()
    expect(screen.getByTestId('operator-reviews-loading')).toBeInTheDocument()
  })

  it('names the missing migration when the queue is unavailable', async () => {
    mockFetch(() => ({ status: 503, body: { detail: 'review_queue_unavailable' } }))
    renderQueue()
    const state = await screen.findByTestId('operator-reviews-error')

    expect(state.textContent).toContain('020_operator_review.sql')
  })

  it('does not blame Aurora when the operator is signed out', async () => {
    mockFetch(() => ({ status: 401, body: { detail: 'authentication_required' } }))
    renderQueue()

    const state = await screen.findByTestId('operator-reviews-error')
    expect(state).toHaveTextContent('Operator sign-in required')
    expect(state).toHaveTextContent('No database request was attempted')
    expect(state).not.toHaveTextContent('Aurora did not return')
    expect(within(state).getByTestId('operator-state-sign-in')).toBeInTheDocument()
  })

  it('separates decided reviews from ones still waiting', async () => {
    const decided = {
      ...PENDING_REVIEW,
      reviewId: 9,
      status: 'approved' as const,
      humanState: 'confirmed' as const,
      decidedBy: 'operator-1',
    }
    mockFetch(() => ({
      body: { reviews: [PENDING_REVIEW, decided], total: 2, pendingCount: 1 },
    }))
    renderQueue()
    await screen.findByTestId('operator-reviews')

    expect(screen.getByTestId('operator-review-pending')).toBeInTheDocument()
    expect(screen.getByTestId('operator-review-decided')).toBeInTheDocument()
  })

  it('describes waiting time in relative terms, and tolerates a missing one', () => {
    const now = new Date('2026-08-26T12:00:00Z')
    expect(relativeTime('2026-08-26T10:00:00Z', now)).toBe('2 hours ago')
    expect(relativeTime('2026-08-26T11:59:30Z', now)).toBe('just now')
    expect(relativeTime(null, now)).toBeNull()
    expect(relativeTime('not-a-date', now)).toBeNull()
  })
})

describe('OperatorFrame review link', () => {
  it('starts the hosted sign-in flow straight from the operator shell', async () => {
    // No interstitial. The control used to open a dialog that captured nothing
    // and explained that the next click would sign you in, so signing in read
    // as two clicks for one intent. Cognito owns password entry, MFA, reset
    // and the social providers, and the gated page already explains why
    // sign-in is required.
    const assign = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...original, assign, pathname: '/operator', search: '' },
    })

    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    render(
      <MemoryRouter initialEntries={['/operator']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />} />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByTestId('operator-reviews-count')
    const signIn = screen.getByTestId('operator-sign-in')
    expect(signIn).toHaveClass('operator-auth-signin')
    expect(signIn).toHaveClass('pellier-account-pill')
    fireEvent.click(signIn)

    expect(authMock.login).not.toHaveBeenCalled()
    expect(assign).toHaveBeenCalledTimes(1)
    const target = String(assign.mock.calls[0][0])
    expect(target).toContain('/signin?returnTo=')
    // The return path brings the participant back to what they asked for.
    expect(target).toContain('returnTo=')

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: original,
    })
  })

  it('labels a pending queue state rather than rendering an unexplained count', async () => {
    mockFetch(() => ({ body: { reviews: [], total: 1, pendingCount: 3 } }))
    render(
      <MemoryRouter initialEntries={['/operator']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />} />
        </Routes>
      </MemoryRouter>,
    )
    const status = await screen.findByTestId('operator-reviews-count')
    expect(status).toHaveTextContent('3 pending')
    expect(status).toHaveAttribute('data-count', 'waiting')
  })

  it('states a clear queue as zero pending rather than leaving it ambiguous', async () => {
    // Zero is a fact an operator wants stated; omitting it would make an
    // empty Action Queue indistinguishable from an unread one.
    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    render(
      <MemoryRouter initialEntries={['/operator']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />} />
        </Routes>
      </MemoryRouter>,
    )
    const badge = await screen.findByTestId('operator-reviews-count')
    expect(badge).toHaveTextContent('0 pending')
    expect(badge).toHaveAttribute('data-count', 'clear')
  })

  it('names an unavailable queue rather than rendering a control-like symbol', async () => {
    // The distinction that matters: "no work" and "nobody could ask" are
    // different facts, and reporting the second as the first is a lie.
    mockFetch(() => ({ status: 503, body: { detail: 'review_queue_unavailable' } }))
    render(
      <MemoryRouter initialEntries={['/operator']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />} />
        </Routes>
      </MemoryRouter>,
    )
    const badge = await screen.findByTestId('operator-reviews-count')
    expect(badge).toHaveAttribute('data-count', 'unavailable')
    expect(badge).toHaveTextContent('Queue unavailable')
    expect(badge.textContent).not.toContain('0')
    expect(badge).toHaveAccessibleDescription(
      /could not be read/i,
    )
  })

  it('distinguishes operator sign-in from an unavailable queue', async () => {
    mockFetch(() => ({ status: 401, body: { detail: 'operator_sign_in_required' } }))
    render(
      <MemoryRouter initialEntries={['/operator']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />} />
        </Routes>
      </MemoryRouter>,
    )
    const badge = await screen.findByTestId('operator-reviews-count')
    expect(badge).toHaveAttribute('data-count', 'sign-in')
    // State, not a third copy of the instruction: the topbar already carries a
    // sign-in control and the gated page carries its own primary action.
    expect(badge).toHaveTextContent('Locked')
    expect(badge).not.toHaveTextContent('Sign in required')
    expect(badge).not.toHaveTextContent('Queue unavailable')
    expect(badge).toHaveAccessibleDescription(/sign in as an operator/i)
  })

  it('refreshes the waiting count after a nested review is confirmed', async () => {
    let confirmed = false
    const confirmedDetail = {
      ...REVIEW_DETAIL,
      review: {
        ...PENDING_REVIEW,
        status: 'approved' as const,
        humanState: 'confirmed' as const,
        decidedBy: 'operator-1',
        decidedAt: '2026-08-26T12:00:00Z',
        assurance: {
          human: 'CONFIRMED' as const,
          policy: 'PENDING' as const,
          aurora: 'NOT_EVALUATED' as const,
          evidence: 'PENDING' as const,
        },
      },
    }
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/confirm')) {
        confirmed = true
        return {
          body: {
            reviewId: 12,
            status: 'approved',
            humanState: 'confirmed',
            decidedBy: 'operator-1',
            decidedAt: '2026-08-26T12:00:00Z',
            assurance: confirmedDetail.review.assurance,
          },
        }
      }
      if (String(url) === '/api/operator/reviews') {
        return {
          body: {
            reviews: confirmed ? [confirmedDetail.review] : [PENDING_REVIEW],
            total: 1,
            pendingCount: confirmed ? 0 : 1,
          },
        }
      }
      return { body: confirmed ? confirmedDetail : REVIEW_DETAIL }
    })

    render(
      <MemoryRouter initialEntries={['/operator/reviews/12']}>
        <Routes>
          <Route path="/operator" element={<OperatorFrame />}>
            <Route path="reviews/:reviewId" element={<ReviewRecord />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(
      await screen.findByTestId('operator-reviews-count'),
    ).toHaveTextContent('1')
    fireEvent.click(await screen.findByTestId('operator-review-confirm'))
    await waitFor(() =>
      expect(screen.getByTestId('operator-reviews-count')).toHaveTextContent('0'),
    )
    expect(screen.getByTestId('operator-reviews-count')).toHaveAttribute('data-count', 'clear')
  })
})

// ---------------------------------------------------------------------------
// The review record
// ---------------------------------------------------------------------------

describe('ReviewRecord', () => {
  it('shows the original storefront ask as reported context', async () => {
    mockFetch(() => ({ body: REVIEW_DETAIL }))
    renderRecord()

    const requester = await screen.findByTestId('operator-review-requester')
    expect(requester).toHaveAttribute('data-requester', 'unverified')
    expect(requester).toHaveTextContent('No verified requester identity was saved')
    expect(requester).toHaveTextContent('separate from your current Operator sign-in')

    const handoff = await screen.findByTestId('operator-shopper-handoff')
    expect(handoff).toHaveTextContent('What Theo asked Pellier')
    expect(handoff).toHaveTextContent('My Wabi-Sabi Bowl arrived chipped')
    expect(handoff).toHaveTextContent('Reported context')
    expect(handoff).toHaveTextContent('Customer Service')
    expect(handoff).toHaveTextContent('get_return_policy, initiate_return')
  })

  beforeEach(() => {
    mockFetch((_url, init) => {
      if (init?.method === 'POST') {
        return {
          body: {
            reviewId: 12, status: 'approved', humanState: 'confirmed',
            decidedBy: 'operator-1', decidedAt: '2026-08-26T12:00:00Z',
            assurance: {
              human: 'CONFIRMED', policy: 'PENDING',
              aurora: 'NOT_EVALUATED', evidence: 'PENDING',
            },
          },
        }
      }
      return { body: REVIEW_DETAIL }
    })
  })

  it('renders the client with their current rung and descriptor', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    // Scoped to the client header: the name also appears in the breadcrumb, and
    // an unscoped text query finds both.
    const header = screen.getByTestId('operator-review-client')
    expect(header.textContent).toContain('Theo')
    expect(header.textContent).toContain('Registered')
    expect(header.textContent).toContain('standard client')
    expect(header.textContent).toContain('$940.00 in 12 months')
    expect(screen.getByTestId('operator-rung-registered')).toBeInTheDocument()
  })

  it('shows the issue, the order, and the proposed action with its parameters', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    expect(screen.getByTestId('operator-review-issue').textContent).toContain(
      'Wabi-Sabi Bowl arrived damaged',
    )
    expect(screen.getByTestId('operator-review-order').textContent).toContain('305')
    expect(screen.getByTestId('operator-review-param-reason').textContent).toContain(
      'damaged',
    )
    expect(screen.getByTestId('operator-review-param-product_id').textContent).toContain(
      '37',
    )
  })

  it('states replacement availability from live stock rather than a stored flag', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    expect(screen.getByTestId('operator-review-fulfilment').textContent).toContain(
      '35 units',
    )
  })

  it('surfaces the prior damaged return so a second remedy is a judgment call', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    expect(screen.getByTestId('operator-review-prior').textContent).toContain(
      '1 previous damaged return',
    )
  })

  it('offers the courtesy credit as optional, never as an entitlement', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    const secondary = screen.getByTestId('operator-review-secondary').textContent ?? ''
    expect(secondary).toContain('Optional')
    expect(secondary).toContain('$25.00')
    expect(secondary).toContain('not an entitlement')
  })

  it('offers both Confirm and Decline', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    expect(screen.getByTestId('operator-review-confirm')).toBeInTheDocument()
    expect(screen.getByTestId('operator-review-decline')).toBeInTheDocument()
  })

  it('renders the four assurance axes', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    for (const axis of ['human', 'policy', 'aurora', 'evidence']) {
      expect(screen.getByTestId(`operator-assurance-${axis}`)).toBeInTheDocument()
    }
    expect(screen.getByTestId('operator-assurance-human')).toHaveAttribute(
      'data-state',
      'CONFIRMATION_REQUIRED',
    )
  })

  it('echoes the displayed fingerprint when confirming', async () => {
    const fetchSpy = vi.fn()
    mockFetch((url, init) => {
      if (init?.method === 'POST') {
        fetchSpy(url, init.body)
        return {
          body: {
            reviewId: 12, status: 'approved', humanState: 'confirmed',
            decidedBy: 'operator-1', decidedAt: '2026-08-26T12:00:00Z',
            assurance: {
              human: 'CONFIRMED', policy: 'PENDING',
              aurora: 'NOT_EVALUATED', evidence: 'PENDING',
            },
          },
        }
      }
      return { body: REVIEW_DETAIL }
    })
    renderRecord()
    await screen.findByTestId('operator-review-record')

    fireEvent.click(screen.getByTestId('operator-review-confirm'))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())

    const [url, body] = fetchSpy.mock.calls[0]
    expect(url).toContain('/api/operator/reviews/12/confirm')
    expect(JSON.parse(String(body))).toEqual({ actionHash: THEO_HASH })
  })

  it('after confirming, Policy stays pending and Aurora stays not evaluated', async () => {
    // The load-bearing frontend assertion. A confirmed human axis must not drag
    // the other three with it.
    const confirmed = {
      ...REVIEW_DETAIL,
      review: {
        ...PENDING_REVIEW,
        status: 'approved' as const,
        humanState: 'confirmed' as const,
        decidedBy: 'operator-1',
        decidedAt: '2026-08-26T12:00:00Z',
        assurance: {
          human: 'CONFIRMED' as const, policy: 'PENDING' as const,
          aurora: 'NOT_EVALUATED' as const, evidence: 'PENDING' as const,
        },
      },
    }
    let posted = false
    mockFetch((_url, init) => {
      if (init?.method === 'POST') {
        posted = true
        return { body: { reviewId: 12, status: 'approved', humanState: 'confirmed',
          decidedBy: 'operator-1', decidedAt: '2026-08-26T12:00:00Z',
          assurance: confirmed.review.assurance } }
      }
      return { body: posted ? confirmed : REVIEW_DETAIL }
    })
    authMock.user = {
      sub: 'operator-1',
      email: 'operator@pellier.example.com',
    }
    authMock.isAuthenticated = true
    renderRecord()
    await screen.findByTestId('operator-review-record')
    fireEvent.click(screen.getByTestId('operator-review-confirm'))

    await waitFor(() =>
      expect(screen.getByTestId('operator-assurance-human')).toHaveAttribute(
        'data-state',
        'CONFIRMED',
      ),
    )
    expect(screen.getByTestId('operator-assurance-policy')).toHaveAttribute(
      'data-state',
      'PENDING',
    )
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveAttribute(
      'data-state',
      'NOT_EVALUATED',
    )
    expect(screen.getByTestId('operator-assurance-evidence')).toHaveAttribute(
      'data-state',
      'PENDING',
    )
    // And the decision is reported as recorded, not as executed.
    const decision = screen.getByTestId('operator-review-decided')
    expect(decision).toHaveTextContent('Confirmed by you')
    expect(decision).not.toHaveTextContent('operator-1')
    expect(screen.getByText('Audit identity')).toBeInTheDocument()
    expect(screen.getByText('operator-1')).toBeInTheDocument()
  })

  it('returns the decision to a person when the parameters changed', async () => {
    mockFetch((_url, init) => {
      if (init?.method === 'POST') {
        return { status: 409, body: { detail: 'parameters_changed' } }
      }
      return { body: REVIEW_DETAIL }
    })
    renderRecord()
    await screen.findByTestId('operator-review-record')
    fireEvent.click(screen.getByTestId('operator-review-confirm'))

    const error = await screen.findByTestId('operator-review-decision-error')
    expect(error.textContent).toContain('changed since this page loaded')
    // Still awaiting a human: the buttons are still there.
    expect(screen.getByTestId('operator-review-confirm')).toBeInTheDocument()
    expect(screen.getByTestId('operator-assurance-human')).toHaveAttribute(
      'data-state',
      'CONFIRMATION_REQUIRED',
    )
  })

  it('reports a decline with no policy or Aurora activity', async () => {
    const declined = {
      ...REVIEW_DETAIL,
      review: {
        ...PENDING_REVIEW,
        status: 'rejected' as const,
        humanState: 'declined' as const,
        decidedBy: 'operator-2',
        decidedAt: '2026-08-26T12:00:00Z',
        assurance: {
          human: 'DECLINED' as const, policy: 'NOT_EVALUATED' as const,
          aurora: 'NOT_REACHED' as const, evidence: 'NO_EXECUTION' as const,
        },
      },
    }
    let posted = false
    mockFetch((_url, init) => {
      if (init?.method === 'POST') {
        posted = true
        return { body: { reviewId: 12, status: 'rejected', humanState: 'declined',
          decidedBy: 'operator-2', decidedAt: '2026-08-26T12:00:00Z',
          assurance: declined.review.assurance } }
      }
      return { body: posted ? declined : REVIEW_DETAIL }
    })
    renderRecord()
    await screen.findByTestId('operator-review-record')
    fireEvent.click(screen.getByTestId('operator-review-decline'))

    await waitFor(() =>
      expect(screen.getByTestId('operator-assurance-human')).toHaveAttribute(
        'data-state',
        'DECLINED',
      ),
    )
    expect(screen.getByTestId('operator-assurance-policy')).toHaveAttribute(
      'data-state',
      'NOT_EVALUATED',
    )
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveAttribute(
      'data-state',
      'NOT_REACHED',
    )
  })

  it('labels a signed-out operator rather than failing silently', async () => {
    mockFetch((_url, init) => {
      if (init?.method === 'POST') {
        return { status: 401, body: { detail: 'operator_sign_in_required' } }
      }
      return { body: REVIEW_DETAIL }
    })
    renderRecord()
    await screen.findByTestId('operator-review-record')
    fireEvent.click(screen.getByTestId('operator-review-confirm'))

    const error = await screen.findByTestId('operator-review-decision-error')
    expect(error.textContent).toContain('verified operator sign-in is required')
  })

  it('links to the authoritative client record and to the originating turn', async () => {
    renderRecord()
    await screen.findByTestId('operator-review-record')

    expect(screen.getByTestId('operator-review-client-link')).toHaveAttribute(
      'href',
      '/operator/clients/CUST-THEO',
    )
    expect(
      screen.getByTestId('operator-review-observatory-link'),
    ).toHaveAttribute(
      'href',
      '/observatory/operator-lineage?customer=CUST-THEO&review=12',
    )
  })

  it('renders a labelled state for an unknown review', async () => {
    mockFetch(() => ({ status: 404, body: { detail: 'Unknown review: 12' } }))
    renderRecord()
    expect(await screen.findByTestId('operator-review-error')).toBeInTheDocument()
  })

  it('does not blame the prepared action when the operator is signed out', async () => {
    mockFetch(() => ({ status: 401, body: { detail: 'authentication_required' } }))
    renderRecord()

    const state = await screen.findByTestId('operator-review-error')
    expect(state).toHaveTextContent('Operator sign-in required')
    expect(state).toHaveTextContent('No database request was attempted')
    expect(state).not.toHaveTextContent('This prepared action is unavailable')
    expect(within(state).getByTestId('operator-state-sign-in')).toBeInTheDocument()
    expect(state.textContent).not.toMatch(/attempted\.Back to/)
  })

  it('renders a loading state', () => {
    renderRecord()
    expect(screen.getByTestId('operator-review-loading')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// The assurance component itself
// ---------------------------------------------------------------------------

describe('ActionAssurance', () => {
  it('is driven entirely by the states it is given', () => {
    render(
      <ActionAssurance
        assurance={{
          human: 'CONFIRMED',
          policy: 'PENDING',
          aurora: 'NOT_EVALUATED',
          evidence: 'PENDING',
        }}
      />,
    )
    expect(screen.getByTestId('operator-assurance-human').textContent).toContain(
      'Confirmed',
    )
    expect(screen.getByTestId('operator-assurance-policy').textContent).toContain(
      'Pending',
    )
    expect(screen.getByTestId('operator-assurance-aurora').textContent).toContain(
      'Not evaluated',
    )
  })

  it('carries state in text and a data attribute, never colour alone', () => {
    render(
      <ActionAssurance
        assurance={{
          human: 'DECLINED',
          policy: 'NOT_EVALUATED',
          aurora: 'NOT_REACHED',
          evidence: 'NO_EXECUTION',
        }}
      />,
    )
    const human = screen.getByTestId('operator-assurance-human')
    expect(human).toHaveAttribute('data-state', 'DECLINED')
    expect(human.textContent).toContain('Declined')
    expect(
      screen.getByTestId('operator-assurance-evidence').textContent,
    ).toContain('No execution')
  })

  it('is reusable rather than written around one persona, in every state', () => {
    // Asserted on what it renders, across every state each axis can hold.
    //
    // Two earlier versions of this test were too weak. One scanned the module
    // source and tripped on a comment stating this very rule. The next rendered
    // a single state, so persona copy hidden in the note for a *different* state
    // passed unnoticed - which an injected "Theo's Wabi-Sabi Bowl" in the
    // CONFIRMED note proved. Every combination is covered now.
    const humans = ['CONFIRMATION_REQUIRED', 'CONFIRMED', 'DECLINED'] as const
    const policies = ['PENDING', 'NOT_EVALUATED'] as const
    const auroras = ['NOT_EVALUATED', 'NOT_REACHED'] as const
    const evidences = ['PENDING', 'NO_EXECUTION'] as const

    let renderedStates = 0
    for (const human of humans) {
      for (const policy of policies) {
        for (const aurora of auroras) {
          for (const evidence of evidences) {
            const { container, unmount } = render(
              <ActionAssurance
                assurance={{ human, policy, aurora, evidence }}
              />,
            )
            const rendered = container.textContent ?? ''
            for (const token of [
              'Theo', 'CUST-', 'Wabi-Sabi', 'initiate_return', 'issue_credit', '$',
            ]) {
              expect(
                rendered,
                `${human}/${policy}/${aurora}/${evidence} leaked ${token}`,
              ).not.toContain(token)
            }
            expect(container.querySelectorAll('[data-axis]')).toHaveLength(4)
            renderedStates += 1
            unmount()
          }
        }
      }
    }
    expect(renderedStates).toBe(24)
  })
})

// ---------------------------------------------------------------------------
// Prompt 4: governed execution
// ---------------------------------------------------------------------------

const CONFIRMED_DETAIL = {
  ...REVIEW_DETAIL,
  review: {
    ...PENDING_REVIEW,
    status: 'approved' as const,
    humanState: 'confirmed' as const,
    decidedBy: 'operator-1',
    decidedAt: '2026-08-26T12:00:00Z',
    assurance: {
      human: 'CONFIRMED' as const,
      policy: 'PENDING' as const,
      aurora: 'NOT_EVALUATED' as const,
      evidence: 'PENDING' as const,
    },
  },
}

describe('ReviewRecord execution', () => {
  it('recovers an uncertain replacement using the same review and fingerprint after an explicit click', async () => {
    const posted: unknown[] = []
    const uncertain = {
      ...CONFIRMED_DETAIL,
      review: {
        ...CONFIRMED_DETAIL.review, action: 'replace_damaged_item',
        executionTurnId: 'turn-' + 'b'.repeat(32),
        assurance: { human: 'CONFIRMED', policy: 'ALLOW', aurora: 'OUTCOME_UNKNOWN', evidence: 'ATTEMPT_RECEIPT' },
      },
    }
    mockFetch((url, init) => {
      if (init?.method === 'POST' && url.endsWith('/execute')) {
        posted.push({ url, body: JSON.parse(String(init.body)) })
        return { status: 503, body: { detail: 'operator_unavailable' } }
      }
      return { body: uncertain }
    })
    renderRecord()
    const recover = await screen.findByRole('button', { name: 'Recover this approved action' })
    expect(posted).toHaveLength(0)
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveTextContent('Outcome needs checking')
    fireEvent.click(recover)
    await waitFor(() => expect(posted).toEqual([{
      url: '/api/operator/reviews/12/execute', body: { expectedActionHash: THEO_HASH },
    }]))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Recover this approved action' })).not.toBeInTheDocument())
  })

  it('offers execute only after a human has confirmed', async () => {
    mockFetch(() => ({ body: REVIEW_DETAIL }))
    renderRecord()
    await screen.findByTestId('operator-review-record')
    expect(screen.queryByTestId('operator-review-execute')).toBeNull()
    expect(screen.getByTestId('operator-review-confirm')).toBeInTheDocument()
  })

  it('shows execute once confirmed, and says the two questions are separate', async () => {
    mockFetch(() => ({ body: CONFIRMED_DETAIL }))
    renderRecord()
    await screen.findByTestId('operator-review-record')
    expect(await screen.findByTestId('operator-review-execute')).toBeInTheDocument()
    // Scoped to the decision section: the assurance caption also says
    // "Four separate questions", so an unscoped query matches both.
    const decision = screen.getByTestId('operator-review-decision')
    expect(decision.textContent).toContain('a separate question with its own answer')
  })

  it('sends no action parameters when executing', async () => {
    const posted: unknown[] = []
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        posted.push(JSON.parse(String(init.body)))
        return {
          body: {
            reviewId: 12, rail: 'in-process', executionTurnId: 'turn-' + 'b'.repeat(32),
            idempotencyKey: 'operator-review:12:abc', actorPrincipal: 'op-1',
            customerSubject: 'sub-theo', tool: 'initiate_return', result: { status: 'success' },
            notes: {},
            assurance: {
              human: 'CONFIRMED', policy: 'NOT_EVALUATED',
              aurora: 'PERMITTED', evidence: 'RECEIPTED',
            },
          },
        }
      }
      return { body: CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))
    await waitFor(() => expect(posted).toHaveLength(1))

    expect(posted[0]).toEqual({ expectedActionHash: THEO_HASH })
    for (const forbidden of ['customerId', 'productId', 'reason', 'amountCents']) {
      expect(JSON.stringify(posted[0])).not.toContain(forbidden)
    }
  })

  it('shows real in-flight policy and database states while execution is pending', async () => {
    let finishExecution: (() => void) | undefined
    const executionResult = {
      reviewId: 12,
      rail: 'gateway-mcp',
      executionTurnId: 'turn-' + 'b'.repeat(32),
      idempotencyKey: 'k',
      actorPrincipal: 'op-1',
      customerSubject: 'sub-theo',
      tool: 'initiate_return',
      result: { status: 'success' },
      notes: {},
      assurance: {
        human: 'CONFIRMED',
        policy: 'ALLOW',
        aurora: 'PERMITTED',
        evidence: 'RECEIPTED',
      },
    }
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        return new Promise((resolve) => {
          finishExecution = () => resolve({ body: executionResult })
        })
      }
      return { body: CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))

    expect(screen.getByTestId('operator-review-live-status')).toHaveTextContent(
      'Evaluating the governed action',
    )
    expect(screen.getByTestId('operator-assurance-policy')).toHaveTextContent('Resolving rail')
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveTextContent('Waiting on rail')
    expect(screen.getByTestId('operator-assurance-evidence')).toHaveTextContent('Awaiting result')

    finishExecution?.()
    await waitFor(() =>
      expect(screen.getByTestId('operator-review-execution')).toHaveTextContent('Action completed'),
    )
  })

  it('hydrates the durable execution receipt without a page reload', async () => {
    let executed = false
    const receipt = {
      receiptId: 9,
      producedReturnId: 44,
      executionTurnId: 'turn-' + 'c'.repeat(32),
      tool: 'initiate_return',
      gatewayActionId: 'pellier-target___initiate_return',
      rail: 'gateway-mcp' as const,
      actorPrincipal: 'operator-1',
      customerSubject: 'sub-theo',
      policyEngineId: 'pellier-policy',
      gatewayMode: 'ENFORCE',
      matchingForbids: [],
      idempotencyKey: 'operator-review:12:abc',
      notes: {},
      recordedAt: '2026-08-27T13:59:08Z',
    }
    const executedDetail = {
      ...CONFIRMED_DETAIL,
      review: {
        ...CONFIRMED_DETAIL.review,
        executionTurnId: receipt.executionTurnId,
        execution: receipt,
        assurance: {
          human: 'CONFIRMED' as const,
          policy: 'ALLOW' as const,
          aurora: 'PERMITTED' as const,
          evidence: 'RECEIPTED' as const,
        },
      },
    }
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        executed = true
        return {
          body: {
            reviewId: 12,
            rail: receipt.rail,
            executionTurnId: receipt.executionTurnId,
            idempotencyKey: receipt.idempotencyKey,
            actorPrincipal: receipt.actorPrincipal,
            customerSubject: receipt.customerSubject,
            tool: receipt.tool,
            result: { status: 'success', return_id: 44 },
            notes: {},
            assurance: executedDetail.review.assurance,
          },
        }
      }
      return { body: executed ? executedDetail : CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))

    expect(await screen.findByTestId('operator-review-receipt')).toHaveTextContent('pellier-policy')
    expect(screen.getByRole('complementary', { name: 'Proposed action and decision' })).toHaveTextContent('Completed')
  })

  it('renders the allowed outcome from the execution, not from the confirmation', async () => {
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        return {
          body: {
            reviewId: 12, rail: 'gateway-mcp', executionTurnId: 'turn-' + 'b'.repeat(32),
            idempotencyKey: 'k', actorPrincipal: 'op-1', customerSubject: 'sub-theo',
            tool: 'initiate_return', result: { status: 'success', return_id: 9 },
            notes: { policy: 'AgentCore Policy permitted the action.' },
            assurance: {
              human: 'CONFIRMED', policy: 'ALLOW',
              aurora: 'PERMITTED', evidence: 'RECEIPTED',
            },
          },
        }
      }
      return { body: CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))

    await waitFor(() =>
      expect(screen.getByTestId('operator-assurance-policy')).toHaveAttribute(
        'data-state',
        'ALLOW',
      ),
    )
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveAttribute(
      'data-state',
      'PERMITTED',
    )
    expect(screen.getByTestId('operator-assurance-evidence')).toHaveAttribute(
      'data-state',
      'RECEIPTED',
    )
  })

  it('renders an ENFORCE denial without inventing a database outcome', async () => {
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        return {
          body: {
            reviewId: 12, rail: 'gateway-mcp', executionTurnId: 'turn-' + 'b'.repeat(32),
            idempotencyKey: 'k', actorPrincipal: 'op-1', customerSubject: 'sub-theo',
            tool: 'initiate_return',
            result: { status: 'policy_denied', denied_by: 'agentcore_policy' },
            notes: { policy: 'Cedar denied the action; the tool was never entered.' },
            assurance: {
              human: 'CONFIRMED', policy: 'DENY',
              aurora: 'NOT_REACHED', evidence: 'POLICY_PROOF',
            },
          },
        }
      }
      return { body: CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))

    await waitFor(() =>
      expect(screen.getByTestId('operator-assurance-policy')).toHaveAttribute(
        'data-state',
        'DENY',
      ),
    )
    // Aurora must not claim a denial it never made.
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveAttribute(
      'data-state',
      'NOT_REACHED',
    )
    expect(screen.getByTestId('operator-assurance-evidence')).toHaveAttribute(
      'data-state',
      'POLICY_PROOF',
    )
  })

  it('renders the LOG_ONLY dual verdict without saying Cedar blocked it', async () => {
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        return {
          body: {
            reviewId: 12, rail: 'gateway-mcp', executionTurnId: 'turn-' + 'b'.repeat(32),
            idempotencyKey: 'k', actorPrincipal: 'op-1', customerSubject: null,
            tool: 'initiate_return',
            result: { status: 'policy_blocked', denied_by: 'database_row_level_security' },
            notes: {
              policy:
                'process_return_damaged_only matched this action and would have denied it. The gateway is LOG_ONLY, so the decision was observed, not enforced.',
              aurora: 'Row-Level Security refused the read the write depends on, so nothing changed.',
            },
            assurance: {
              human: 'CONFIRMED', policy: 'WOULD_DENY',
              aurora: 'DENIED', evidence: 'ATTEMPT_RECEIPT',
            },
          },
        }
      }
      return { body: CONFIRMED_DETAIL }
    })
    const { container } = renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))

    await waitFor(() =>
      expect(screen.getByTestId('operator-assurance-policy')).toHaveAttribute(
        'data-state',
        'WOULD_DENY',
      ),
    )
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveAttribute(
      'data-state', 'DENIED',
    )
    const text = container.textContent ?? ''
    expect(text).toContain('observed, not enforced')
    // The one sentence this screen must never say.
    expect(text).not.toContain('Cedar blocked')
    expect(text).not.toContain('Policy blocked this request')
  })

  it('states plainly when a client has no identity mapping', async () => {
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        return {
          body: {
            reviewId: 12, rail: 'in-process', executionTurnId: 'turn-' + 'b'.repeat(32),
            idempotencyKey: 'k', actorPrincipal: 'op-1', customerSubject: null,
            tool: 'initiate_return', result: { status: 'error' }, notes: {},
            assurance: {
              human: 'CONFIRMED', policy: 'NOT_EVALUATED',
              aurora: 'DENIED', evidence: 'ATTEMPT_RECEIPT',
            },
          },
        }
      }
      return { body: CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))
    const line = await screen.findByTestId('operator-review-execution')
    expect(line.textContent).toContain('no identity mapping')
  })

  it('surfaces a stale-view refusal instead of retrying blindly', async () => {
    mockFetch((url, init) => {
      if (init?.method === 'POST' && String(url).endsWith('/execute')) {
        return { status: 409, body: { detail: 'parameters_changed' } }
      }
      return { body: CONFIRMED_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-execute'))
    const error = await screen.findByTestId('operator-review-decision-error')
    expect(error.textContent).toContain('changed since this page loaded')
  })
})

/**
 * The persisted execution receipt.
 *
 * The defect: this page kept the four axes in component state, so the verdicts of a
 * governed execution survived exactly as long as the tab. Reload and a Cedar DENY read
 * `Pending` again, and the "Execute this action" button came back for an action that
 * had already run. The server now resolves the axes from
 * `pellier.execution_receipts` and sends the attribution with them.
 */
describe('a stored execution receipt', () => {
  const RECEIPT = {
    receiptId: 9,
    producedReturnId: null,
    executionTurnId: 'turn-' + 'c'.repeat(32),
    tool: 'initiate_return',
    gatewayActionId: 'pellier-concierge-experience-target___initiate_return',
    rail: 'gateway-mcp' as const,
    actorPrincipal: 'operator-sub',
    customerSubject: null,
    policyEngineId: 'pellier_policy_engine-usqc5dbiek',
    gatewayMode: 'ENFORCE',
    matchingForbids: ['process_return_damaged_only'],
    idempotencyKey: 'operator-review:12:abc',
    notes: {
      policy: 'Cedar denied the action; the tool was never entered.',
      aurora: 'The tool was never entered, so no statement reached the database.',
    },
    recordedAt: '2026-08-27T13:59:08Z',
  }

  function denied(overrides: Record<string, unknown> = {}) {
    return {
      ...REVIEW_DETAIL,
      review: {
        ...PENDING_REVIEW,
        status: 'approved' as const,
        humanState: 'confirmed' as const,
        decidedBy: 'operator-sub',
        decidedAt: '2026-08-27T13:50:00Z',
        assurance: {
          human: 'CONFIRMED' as const,
          policy: 'DENY' as const,
          aurora: 'NOT_REACHED' as const,
          evidence: 'POLICY_PROOF' as const,
        },
        executionTurnId: RECEIPT.executionTurnId,
        execution: RECEIPT,
        ...overrides,
      },
    }
  }

  const REVIEW_RECEIPT_ALLOW = {
    ...RECEIPT,
    notes: {
      policy: 'AgentCore Policy evaluated the action and permitted it.',
      aurora: 'The write already applied under this key; this call replayed it.',
    },
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the denial after a reload, with no execution in component state', async () => {
    mockFetch(() => ({ body: denied() }))
    renderRecord()
    const policy = await screen.findByTestId('operator-assurance-policy')
    expect(policy).toHaveAttribute('data-state', 'DENY')
    expect(policy.textContent).toContain('Deny')
    const aurora = screen.getByTestId('operator-assurance-aurora')
    expect(aurora).toHaveAttribute('data-state', 'NOT_REACHED')
  })

  it('uses the stored sentences rather than the static ones', async () => {
    mockFetch(() => ({ body: denied() }))
    renderRecord()
    const policy = await screen.findByTestId('operator-assurance-policy')
    // The server knows WHICH policy matched; the component's generic line does not.
    expect(policy.textContent).toContain('the tool was never entered')
  })

  it('does not offer to execute an action that already ran', async () => {
    mockFetch(() => ({ body: denied() }))
    renderRecord()
    await screen.findByTestId('operator-review-record')
    expect(screen.queryByTestId('operator-review-execute')).toBeNull()
  })

  it('still offers to execute a confirmed action with no attempt on record', async () => {
    mockFetch(() => ({
      body: denied({ execution: null, executionTurnId: null,
        assurance: {
          human: 'CONFIRMED' as const, policy: 'PENDING' as const,
          aurora: 'NOT_EVALUATED' as const, evidence: 'PENDING' as const,
        } }),
    }))
    renderRecord()
    expect(await screen.findByTestId('operator-review-execute')).toBeTruthy()
  })

  it('names the engine, the mode and the action that was evaluated', async () => {
    mockFetch(() => ({ body: denied() }))
    renderRecord()
    const receipt = await screen.findByTestId('operator-review-receipt')
    expect(receipt.textContent).toContain('pellier_policy_engine-usqc5dbiek')
    expect(receipt.textContent).toContain('a denial would have been enforced')
    expect(receipt.textContent).toContain(
      'pellier-concierge-experience-target___initiate_return',
    )
    expect(receipt.textContent).toContain('process_return_damaged_only')
  })

  it('says LOG_ONLY in words, not only in colour', async () => {
    mockFetch(() => ({
      body: denied({ execution: { ...RECEIPT, gatewayMode: 'LOG_ONLY' } }),
    }))
    renderRecord()
    const receipt = await screen.findByTestId('operator-review-receipt')
    // The tint is a second cue. A greyscale screenshot must still carry the fact.
    expect(receipt.textContent).toContain('observed, not enforced')
    expect(receipt).toHaveAttribute('data-mode', 'LOG_ONLY')
  })

  it('does not claim a denied action executed', async () => {
    // The old copy said "Executed on the managed Gateway rail" for a Cedar DENY and
    // then explained the row scope, of which neither is true: the tool was never
    // entered and nothing reached the database to be scoped.
    mockFetch(() => ({ body: denied() }))
    renderRecord()
    const line = await screen.findByTestId('operator-review-execution')
    expect(line.textContent).toContain('managed Gateway rail')
    expect(line.textContent).toContain('refused before the tool was entered')
    expect(line.textContent).not.toContain('Executed on')
    expect(line.textContent).not.toContain('no identity mapping')
  })

  it('reports the absent row scope where it applies — an ALLOW that Aurora refused', async () => {
    mockFetch(() => ({
      body: denied({
        assurance: {
          human: 'CONFIRMED' as const, policy: 'ALLOW' as const,
          aurora: 'DENIED' as const, evidence: 'ATTEMPT_RECEIPT' as const,
        },
      }),
    }))
    renderRecord()
    const line = await screen.findByTestId('operator-review-execution')
    expect(line.textContent).toContain('Executed on')
    expect(line.textContent).toContain('no identity mapping')
  })

  it('drops the separator when a review carries no issue text', async () => {
    // Rachel's review has issue "", which left "Rachel Green ·" trailing a middle dot
    // with nothing after it.
    mockFetch(() => ({ body: denied({ issue: '' }) }))
    renderRecord()
    const origin = await screen.findByTestId('operator-review-origin')
    expect(origin.textContent).toBe('Prepared from Pellier · Theo')
  })

  it('renders nothing about what decided it when nothing has executed', async () => {
    mockFetch(() => ({ body: denied({ execution: null }) }))
    renderRecord()
    await screen.findByTestId('operator-review-record')
    expect(screen.queryByTestId('operator-review-receipt')).toBeNull()
  })

  it('does not count the return it produced as prior history', async () => {
    // The client's return history and this review's own outcome live in the same
    // table. Once the returns query was fixed, review 40 saw return 37 — which it had
    // just created — and reported it as a "previous damaged return".
    mockFetch(() => ({
      body: {
        ...denied({
          execution: { ...REVIEW_RECEIPT_ALLOW, producedReturnId: 37 },
          assurance: {
            human: 'CONFIRMED' as const, policy: 'ALLOW' as const,
            aurora: 'PERMITTED' as const, evidence: 'RECEIPTED' as const,
          },
        }),
        returns: [
          { returnId: 37, productId: '37', reason: 'damaged', status: 'pending',
            requestedAt: '2026-08-27T12:57:27Z', resolvedAt: null },
          { returnId: 28, productId: '31', reason: 'damaged', status: 'approved',
            requestedAt: '2026-08-19T00:00:00Z', resolvedAt: null },
        ],
      },
    }))
    renderRecord()
    const prior = await screen.findByTestId('operator-review-prior')
    expect(prior.textContent).toContain('1 previous damaged return ')
    expect(prior.textContent).toContain('most recently approved')
    // But the returns section still reports the table as it stands, both rows.
    expect(screen.getByTestId('operator-review-returns').textContent).toContain(
      '2 on file',
    )
  })

  it('reports no prior history when the only return is the one it created', async () => {
    mockFetch(() => ({
      body: {
        ...denied({ execution: { ...REVIEW_RECEIPT_ALLOW, producedReturnId: 37 } }),
        returns: [
          { returnId: 37, productId: '37', reason: 'damaged', status: 'pending',
            requestedAt: '2026-08-27T12:57:27Z', resolvedAt: null },
        ],
      },
    }))
    renderRecord()
    await screen.findByTestId('operator-review-record')
    expect(screen.queryByTestId('operator-review-prior')).toBeNull()
  })

  it('keeps an ALLOW beside an Aurora denial without resolving them', async () => {
    mockFetch(() => ({
      body: denied({
        assurance: {
          human: 'CONFIRMED' as const, policy: 'ALLOW' as const,
          aurora: 'DENIED' as const, evidence: 'ATTEMPT_RECEIPT' as const,
        },
        execution: {
          ...RECEIPT,
          notes: {
            policy: 'AgentCore Policy evaluated the action and permitted it.',
            aurora: 'Row-Level Security refused the read the write depends on, so nothing changed.',
          },
        },
      }),
    }))
    renderRecord()
    expect(await screen.findByTestId('operator-assurance-policy')).toHaveAttribute(
      'data-state', 'ALLOW',
    )
    expect(screen.getByTestId('operator-assurance-aurora')).toHaveAttribute(
      'data-state',
      'DENIED',
    )
    expect(screen.getByTestId('operator-assurance-evidence')).toHaveAttribute(
      'data-state', 'ATTEMPT_RECEIPT',
    )
  })
})

describe('issueLine', () => {
  it('makes a sentence of a piece and a problem', () => {
    expect(issueLine('Wabi-Sabi Bowl', 'arrived damaged')).toBe(
      'Wabi-Sabi Bowl arrived damaged',
    )
  })

  it('does not repeat a piece the issue already names', () => {
    // `prepare_proposal` defaults the issue to the item name when the operator stated
    // no problem, which rendered "Ivory Cashmere Throw Ivory Cashmere Throw".
    expect(issueLine('Ivory Cashmere Throw', 'Ivory Cashmere Throw')).toBe(
      'Ivory Cashmere Throw',
    )
    expect(issueLine('Wabi-Sabi Bowl', 'The Wabi-Sabi Bowl cracked in transit')).toBe(
      'The Wabi-Sabi Bowl cracked in transit',
    )
  })

  it('falls back to whichever half exists', () => {
    expect(issueLine(undefined, 'arrived damaged')).toBe('arrived damaged')
    expect(issueLine('Vetiver Quietude', '')).toBe('Vetiver Quietude')
    expect(issueLine(undefined, '')).toBe('')
  })
})

describe('outcomeLine', () => {
  function review(over: Record<string, unknown> = {}) {
    return {
      ...PENDING_REVIEW,
      execution: null,
      executionTurnId: null,
      ...over,
    } as never
  }
  const AXES = (policy: string, aurora: string) => ({
    human: 'CONFIRMED', policy, aurora, evidence: 'RECEIPTED',
  })
  const RECEIPT = { receiptId: 1 }

  it('says what a pending review is waiting for', () => {
    expect(outcomeLine(review())).toBe('Return proposed, awaiting a person')
  })

  it('says nothing was submitted for a declined review', () => {
    expect(
      outcomeLine(review({ humanState: 'declined' })),
    ).toBe('Return declined. Nothing was submitted.')
  })

  it('distinguishes approved-but-not-run from carried out', () => {
    // A confirmation is not an execution, and the queue said "awaiting a person" for
    // both of these plus every failure below.
    expect(
      outcomeLine(review({ humanState: 'confirmed' })),
    ).toBe('Return approved, not yet carried out')
    expect(
      outcomeLine(review({
        humanState: 'confirmed', execution: RECEIPT,
        assurance: AXES('ALLOW', 'PERMITTED'),
      })),
    ).toBe('Return carried out')
  })

  it('names a policy refusal', () => {
    expect(
      outcomeLine(review({
        humanState: 'confirmed', execution: RECEIPT,
        assurance: AXES('DENY', 'NOT_REACHED'),
      })),
    ).toBe('Return refused by AgentCore Policy')
  })

  it('keeps a policy allow and a database refusal in one sentence', () => {
    expect(
      outcomeLine(review({
        humanState: 'confirmed', execution: RECEIPT,
        assurance: AXES('ALLOW', 'DENIED'),
      })),
    ).toBe('Return permitted, then refused by Aurora')
  })

  it('does not report an unenforced would-deny as a refusal', () => {
    expect(
      outcomeLine(review({
        humanState: 'confirmed', execution: RECEIPT,
        assurance: AXES('WOULD_DENY', 'PERMITTED'),
      })),
    ).toBe('Return carried out; policy warning observed with enforcement off')
  })

  it('admits when an attempt produced no recorded outcome', () => {
    expect(
      outcomeLine(review({
        humanState: 'confirmed', execution: RECEIPT,
        assurance: AXES('NOT_EVALUATED', 'NOT_ENFORCED'),
      })),
    ).toBe('Return attempted; the outcome was not recorded')
  })
})

describe('the empty review queue', () => {
  // A clean workshop starts at approvals = 0, so this is the first thing an operator
  // sees. It has to look designed rather than broken.
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('states the mechanism rather than instructing the reader', async () => {
    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    renderQueue()
    const empty = await screen.findByTestId('operator-reviews-empty')
    expect(empty.textContent).toContain('No actions waiting')
    expect(empty.textContent).toContain('appear here for an operator to confirm')
  })

  it('avoids the all-caught-up register and any emoji', async () => {
    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    renderQueue()
    const text = (await screen.findByTestId('operator-reviews-empty')).textContent ?? ''
    for (const banned of ['caught up', 'Nothing here', 'All done', 'Great']) {
      expect(text).not.toContain(banned)
    }
    // No emoji anywhere in the empty state.
    expect(/\p{Extended_Pictographic}/u.test(text)).toBe(false)
  })

  it('shows no decided section when nothing has been decided', async () => {
    mockFetch(() => ({ body: { reviews: [], total: 0, pendingCount: 0 } }))
    renderQueue()
    await screen.findByTestId('operator-reviews-empty')
    expect(screen.queryByTestId('operator-review-decided-head')).toBeNull()
  })
})


describe('review state reconciliation', () => {
  it('retains a committed confirmation when its follow-up read fails', async () => {
    let posted = false
    mockFetch((_url, init) => {
      if (init?.method === 'POST') {
        posted = true
        return { body: { reviewId: 12, status: 'approved', humanState: 'confirmed', decidedBy: 'operator-1', decidedAt: null,
          assurance: { ...PENDING_REVIEW.assurance, human: 'CONFIRMED' } } }
      }
      return posted ? { status: 503, body: { detail: 'operator_unavailable' } } : { body: REVIEW_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-confirm'))
    expect(await screen.findByText(/response was recorded successfully/i)).toBeInTheDocument()
    expect(screen.queryByTestId('operator-review-confirm')).not.toBeInTheDocument()
    expect(screen.getByTestId('operator-review-execute')).toBeDisabled()
    expect(screen.getByTestId('operator-review-decision')).not.toHaveTextContent(/nothing was recorded/i)
  })

  it('gates a timed-out decision until a persisted read reconciles it', async () => {
    mockFetch((_url, init) => {
      if (init?.method === 'POST') throw new TypeError('connection lost')
      return { body: REVIEW_DETAIL }
    })
    renderRecord()
    fireEvent.click(await screen.findByTestId('operator-review-confirm'))
    await screen.findByTestId('operator-review-decision-error')
    expect(screen.getByTestId('operator-review-confirm')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh record' }))
    await waitFor(() => expect(screen.getByTestId('operator-review-confirm')).toBeEnabled())
  })

  it('discards an obsolete review response after route navigation', async () => {
    let finish!: (value: MockFetchResult) => void
    const old = new Promise<MockFetchResult>((resolve) => { finish = resolve })
    mockFetch((url) => url.endsWith('/13') ? old : { body: {
      ...REVIEW_DETAIL, review: { ...PENDING_REVIEW, reviewId: 14 }, client: { ...REVIEW_DETAIL.client, name: 'Current client' },
    } })
    render(<MemoryRouter initialEntries={['/operator/reviews/13']}>
      <Link to="/operator/reviews/14">Next review</Link>
      <Routes><Route path="/operator/reviews/:reviewId" element={<ReviewRecord />} /></Routes>
    </MemoryRouter>)
    expect(screen.queryByTestId('operator-review-confirm')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Next review'))
    await screen.findByRole('heading', { name: 'Current client' })
    await act(async () => { finish({ body: { ...REVIEW_DETAIL, review: { ...PENDING_REVIEW, reviewId: 13 } } }); await old })
    expect(screen.getByRole('heading', { name: 'Current client' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Theo' })).not.toBeInTheDocument()
  })

  it('keeps the global pending total when a filter has no matches', async () => {
    mockFetch(() => ({ body: { reviews: [PENDING_REVIEW], total: 1, pendingCount: 1 } }))
    renderQueue()
    await screen.findByTestId('operator-review-12')
    fireEvent.click(screen.getByTestId('operator-outcome-filter-declined'))
    expect(screen.getByTestId('operator-reviews-filter-empty')).toHaveTextContent('1 action in the full queue')
    expect(screen.queryByText('No actions waiting')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all actions' }))
    expect(screen.getByTestId('operator-review-12')).toBeInTheDocument()
  })

  it.each([
    ['WOULD_DENY', 'PERMITTED', 'RECEIPTED', 'executed'],
    ['WOULD_DENY', 'NOT_EVALUATED', 'PENDING', 'unknown'],
    ['ALLOW', 'DENIED', 'NO_EXECUTION', 'refused'],
    ['DENY', 'NOT_REACHED', 'NO_EXECUTION', 'refused'],
    ['ALLOW', 'PERMITTED', 'PENDING', 'unknown'],
  ])('classifies %s / %s / %s from independent evidence', (policy, aurora, evidence, outcome) => {
    expect(outcomeKind({ ...PENDING_REVIEW, humanState: 'confirmed', execution: { receiptId: 1 }, assurance: { human: 'CONFIRMED', policy, aurora, evidence } } as never)).toBe(outcome)
  })
})
