import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ChatFailureCard from './ChatFailureCard'

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
