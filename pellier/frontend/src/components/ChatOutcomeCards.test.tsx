import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ChatFailureCard from './ChatFailureCard'
import TurnReceipt from './TurnReceipt'

describe('ChatFailureCard', () => {
  it('renders governance denials as protected outcomes without a retry action', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const onEditRequest = vi.fn()

    render(
      <ChatFailureCard
        failure={{
          code: 'policy_denied',
          retryable: false,
          query: 'return this item',
          referenceId: 'deny-7f31',
        }}
        onRetry={onRetry}
        onEditRequest={onEditRequest}
        onAuthenticate={vi.fn()}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Protected action')
    expect(screen.getByRole('alert')).toHaveTextContent(
      'A storefront rule kept your account and inventory unchanged.',
    )
    expect(screen.getByText('deny-7f31')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Try again' }),
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit request' }))
    expect(onEditRequest).toHaveBeenCalledWith('return this item')
    expect(onRetry).not.toHaveBeenCalled()
  })

  it('offers the recovery action appropriate to auth and retryable failures', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const onAuthenticate = vi.fn()
    const { rerender } = render(
      <ChatFailureCard
        failure={{
          code: 'authentication_required',
          retryable: false,
          query: 'show my order',
        }}
        onRetry={onRetry}
        onEditRequest={vi.fn()}
        onAuthenticate={onAuthenticate}
        surface="observatory"
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Sign in again' }))
    expect(onAuthenticate).toHaveBeenCalledOnce()

    rerender(
      <ChatFailureCard
        failure={{
          code: 'request_timeout',
          retryable: true,
          query: 'find a linen jacket',
        }}
        onRetry={onRetry}
        onEditRequest={vi.fn()}
        onAuthenticate={onAuthenticate}
        surface="observatory"
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledWith('find a linen jacket')
  })
})

describe('TurnReceipt', () => {
  it('copies the complete turn reference while displaying a compact value', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const reference = 'turn-0123456789-abcdefghijklmnopqrstuvwxyz'

    render(<TurnReceipt reference={reference} surface="observatory" />)

    // "Response complete" is the transport fact. Evidence is a separate badge
    // that appears only when the ledger says so; see TurnReceipt.test.tsx.
    expect(screen.getByTestId('turn-receipt')).toHaveTextContent(
      'Response complete',
    )
    expect(screen.getByTestId('turn-receipt')).not.toHaveTextContent(
      'Evidence recorded',
    )
    expect(screen.getByTitle(reference)).not.toHaveTextContent(reference)

    await user.click(
      screen.getByRole('button', { name: 'Copy turn reference' }),
    )

    expect(writeText).toHaveBeenCalledWith(reference)
    expect(
      screen.getByRole('button', { name: 'Reference copied' }),
    ).toBeInTheDocument()
  })
})
