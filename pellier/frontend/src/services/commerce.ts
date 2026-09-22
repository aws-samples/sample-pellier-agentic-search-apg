import { apiFetch } from './apiBase'
export interface CommerceQuoteLine {
  productId: number
  name: string
  imageUrl?: string
  unitPrice: string
  quantity: number
  lineTotal: string
}

export interface CommerceAmounts {
  subtotal: string
  shipping: string
  tax: string
  total: string
}

export interface CommerceQuote {
  quoteId: string
  quoteHash: string
  status: 'open'
  currency: 'USD'
  lines: CommerceQuoteLine[]
  amounts: CommerceAmounts
  rules: {
    policy: string
    taxRate: string
    freeShippingThreshold: string
    standardShipping: string
    paymentProvider: 'pellier-sandbox'
    paymentMode: 'sandbox'
  }
  expiresAt: string
}

export interface ConfirmationGrant {
  confirmationGrantId: string
  quoteId: string
  quoteHash: string
  confirmedTotal: string
  currency: 'USD'
  status: 'granted'
  expiresAt: string
}

export interface CommerceReceipt {
  orderId: string
  orderNumber: string
  status: 'paid' | 'payment_declined' | 'payment_failed'
  paymentStatus: 'settled' | 'declined' | 'failed'
  currency: 'USD'
  amounts: CommerceAmounts
  payment: {
    attemptId: string
    eventIds: number[]
    provider: 'pellier-sandbox'
    mode: 'sandbox'
    status: 'settled' | 'declined' | 'failed'
    providerRef: string
    failureCode?: string | null
  }
  evidence: {
    identity: { principalSub: string; verified: boolean }
    context: { sessionId?: string | null; turnId?: string | null }
    quote: { quoteId: string; quoteHash: string; total: string; currency: string }
    order: {
      orderId: string
      orderNumber: string
      lines: Array<{
        productId: number
        name: string
        unitPrice: string
        quantity: number
        lineTotal: string
      }>
    }
    consent: { confirmationGrantId: string; acknowledgedAt: string }
    inventory: {
      reservationIds: string[]
      ledgerEntryIds: number[]
      status: 'captured' | 'released'
    }
    payment: CommerceReceipt['payment']
    outboxEventIds: string[]
    outcome: CommerceReceipt['status']
  }
  receipt: {
    receiptId: string
    receiptHash: string
    verified: boolean
    createdAt: string
  }
  createdAt: string
}

export class CommerceApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code)
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await apiFetch(path, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...init.headers,
      },
    })
  } catch {
    throw new CommerceApiError('commerce_unavailable', 503)
  }

  if (!response.ok) {
    let code = response.status === 401 ? 'sign_in_required' : 'commerce_unavailable'
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) code = body.detail
    } catch {
      // Keep the status-derived code when the response is not JSON.
    }
    throw new CommerceApiError(code, response.status)
  }
  return response.json() as Promise<T>
}

export function createCommerceQuote(
  lines: Array<{ productId: number; quantity: number }>,
  sessionId?: string,
): Promise<CommerceQuote> {
  return request('/api/commerce/quotes', {
    method: 'POST',
    body: JSON.stringify({
      lines,
      sessionId: sessionId || undefined,
    }),
  })
}

export function confirmCommerceQuote(
  quote: CommerceQuote,
): Promise<ConfirmationGrant> {
  return request(`/api/commerce/quotes/${quote.quoteId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({
      quoteHash: quote.quoteHash,
      acknowledged: true,
    }),
  })
}

export function executeCommerceOrder(
  confirmationGrantId: string,
  idempotencyKey: string,
): Promise<CommerceReceipt> {
  return request('/api/commerce/orders', {
    method: 'POST',
    body: JSON.stringify({
      confirmationGrantId,
      idempotencyKey,
    }),
  })
}
