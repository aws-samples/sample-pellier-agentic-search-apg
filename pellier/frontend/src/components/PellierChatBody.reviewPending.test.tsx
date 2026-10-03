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
  'Your request is prepared and waiting for a Pellier specialist to confirm it. ' +
  'Nothing about your order has changed yet.'

function message(over: Partial<AgentChatMessage> = {}): AgentChatMessage {
  return {
    role: 'assistant',
    content:
      'I found your Wabi-Sabi Bowl order and prepared the damaged-return request.',
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

describe('the review-pending notice', () => {
  it('renders the backend sentence', () => {
    renderBody([message({ reviewPending: { tool: 'initiate_return', message: NOTICE } })])
    const notice = screen.getByTestId('pellier-review-pending')
    expect(notice.textContent).toBe(NOTICE)
  })

  it('says nothing changed, which the prose alone did not', () => {
    renderBody([message({ reviewPending: { tool: 'initiate_return', message: NOTICE } })])
    const notice = screen.getByTestId('pellier-review-pending')
    expect(notice.textContent?.toLowerCase()).toContain('waiting')
    expect(notice.textContent?.toLowerCase()).toContain('nothing about your order has changed')
  })

  it('is absent when no mutation was refused', () => {
    renderBody([message()])
    expect(screen.queryByTestId('pellier-review-pending')).toBeNull()
  })

  it('never shows the shopper the internal tool name', () => {
    renderBody([message({ reviewPending: { tool: 'initiate_return', message: NOTICE } })])
    const notice = screen.getByTestId('pellier-review-pending')
    expect(notice.textContent).not.toContain('initiate_return')
  })

  it('announces itself to assistive technology without being an alert', () => {
    // A boundary working as designed is not an error, so `status` rather than `alert`.
    renderBody([message({ reviewPending: { tool: 'initiate_return', message: NOTICE } })])
    expect(screen.getByTestId('pellier-review-pending')).toHaveAttribute('role', 'status')
  })

  it('leaves the answer prose alone', () => {
    // The notice sits beside the answer; it does not rewrite or replace it.
    renderBody([message({ reviewPending: { tool: 'initiate_return', message: NOTICE } })])
    expect(
      screen.getByText(/prepared the damaged-return request/),
    ).toBeTruthy()
  })

  it('does not merchandise the product used to resolve the return', () => {
    renderBody([
      message({
        reviewPending: { tool: 'initiate_return', message: NOTICE },
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

  it('hands the prepared return to its exact Operator review', () => {
    renderBody([
      message({
        reviewPending: {
          tool: 'initiate_return',
          message: NOTICE,
          reviewId: 44,
        },
      }),
    ])

    expect(
      screen.getByRole('link', { name: /Open prepared request in Operator/i }),
    ).toHaveAttribute('href', '/operator/reviews/44')
  })
})
