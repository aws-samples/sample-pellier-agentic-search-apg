/**
 * The prepared-not-carried-out notice.
 *
 * Measured on 2026-08-27 against the live stack: the specialist prompt asks for two
 * sentences on a governed-boundary refusal, and the model produced only the first —
 * "I found your order and prepared the damaged-return request for the bowl" — which
 * reads as filed. So the sentence is backend-owned and arrives as its own SSE event.
 *
 * These tests assert the surface renders it and does not borrow the escalation rules.
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import PellierChatBody from './PellierChatBody'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const NOTICE =
  'A person at Pellier will review the store credit you asked about. ' +
  'Nothing on your account has changed yet.'

function message(over: Partial<AgentChatMessage> = {}): AgentChatMessage {
  return {
    role: 'assistant',
    content:
      'I passed your store credit request for the robe and the diffuser to a person at Pellier.',
    timestamp: new Date('2026-08-27T14:44:00Z'),
    agentStatus: 'complete',
    ...over,
  }
}

function renderBody(messages: AgentChatMessage[]) {
  return render(
    <MemoryRouter>
      <PellierChatBody
        messages={messages}
        sendMessage={vi.fn()}
        retryMessage={vi.fn()}
        onEditRequest={vi.fn()}
        onAuthenticate={vi.fn()}
        addToCart={vi.fn()}
        persona={null}
      />
    </MemoryRouter>,
  )
}

describe('the credit-request notice', () => {
  it('renders the backend sentence', () => {
    renderBody([message({ creditRequestPending: { tool: 'store_credit_request', message: NOTICE } })])
    const notice = screen.getByTestId('pellier-credit-request-pending')
    expect(notice.textContent).toBe(NOTICE)
  })

  it('says nothing changed, which the prose alone did not', () => {
    renderBody([message({ creditRequestPending: { tool: 'store_credit_request', message: NOTICE } })])
    const notice = screen.getByTestId('pellier-credit-request-pending')
    expect(notice.textContent?.toLowerCase()).toContain('will review')
    expect(notice.textContent?.toLowerCase()).toContain('nothing on your account has changed')
  })

  it('is absent when no mutation was refused', () => {
    renderBody([message()])
    expect(screen.queryByTestId('pellier-credit-request-pending')).toBeNull()
  })

  it('never shows the shopper the internal tool name', () => {
    renderBody([message({ creditRequestPending: { tool: 'store_credit_request', message: NOTICE } })])
    const notice = screen.getByTestId('pellier-credit-request-pending')
    expect(notice.textContent).not.toContain('store_credit_request')
  })

  it('announces itself to assistive technology without being an alert', () => {
    // A boundary working as designed is not an error, so `status` rather than `alert`.
    renderBody([message({ creditRequestPending: { tool: 'store_credit_request', message: NOTICE } })])
    expect(screen.getByTestId('pellier-credit-request-pending')).toHaveAttribute('role', 'status')
  })

  it('leaves the answer prose alone', () => {
    // The notice sits beside the answer; it does not rewrite or replace it.
    renderBody([message({ creditRequestPending: { tool: 'store_credit_request', message: NOTICE } })])
    expect(
      screen.getByText(/passed your store credit request/),
    ).toBeTruthy()
  })

  it('does not merchandise a product beside the request', () => {
    renderBody([
      message({
        creditRequestPending: { tool: 'store_credit_request', message: NOTICE },
        products: [
          {
            id: 37,
            name: 'Wabi-Sabi Bowl',
            category: 'Kitchen and table',
            price: 65,
            image: '',
            rating: 4.9,
            reviews: 167,
          },
        ],
      }),
    ])

    expect(screen.queryByText('Pulled for you')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add to bag' })).toBeNull()
  })

  it('hands the request to the client record on the Operator desk', () => {
    renderBody([
      message({
        creditRequestPending: {
          tool: 'store_credit_request',
          message: NOTICE,
          requestId: 44,
          customerId: 'CUST-JESSICA',
        },
      }),
    ])

    expect(
      screen.getByRole('link', { name: /Open the request in Operator/i }),
    ).toHaveAttribute('href', '/operator/clients/CUST-JESSICA')
  })

  it('names no amount', () => {
    renderBody([message({ creditRequestPending: { tool: 'store_credit_request', message: NOTICE } })])
    expect(screen.getByTestId('pellier-credit-request-pending').textContent).not.toMatch(/\$|\d/)
  })
})
