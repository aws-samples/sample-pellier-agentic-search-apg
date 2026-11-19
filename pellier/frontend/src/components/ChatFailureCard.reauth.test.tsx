import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ChatFailureCard, { type ReauthState } from './ChatFailureCard'

const QUERY = 'What is happening with my ticket?'
const WAIT = 'Sign in again once the current reply finishes.'
const FAILED = 'Pellier could not sign you in again. Try again in a moment.'

function card(reauth: ReauthState, query = QUERY) {
  return (
    <ChatFailureCard
      failure={{ code: 'authentication_required', retryable: false, query }}
      onRetry={vi.fn()}
      onEditRequest={vi.fn()}
      onAuthenticate={vi.fn()}
      reauth={reauth}
    />
  )
}

const idle: ReauthState = { query: null, pending: false, failed: false, blockedBy: null }

describe('Sign in again on an expired session', () => {
  it('shows progress on the request being sent again, disabled', () => {
    render(card({ ...idle, query: QUERY, pending: true }))
    expect(screen.getByRole('button', { name: 'Signing in again' })).toBeDisabled()
  })

  it('shows progress and failure only on the card for that request', () => {
    render(card({ ...idle, query: 'Another request', failed: true }))
    expect(screen.getByRole('button', { name: 'Sign in again' })).toBeEnabled()
    expect(screen.queryByText(FAILED)).toBeNull()
  })

  it('says why it waits while a reply runs, and shows no reason during a shopper switch', () => {
    const { rerender } = render(card({ ...idle, blockedBy: 'reply' }))
    expect(screen.getByRole('button', { name: 'Sign in again' })).toBeDisabled()
    expect(screen.getByText(WAIT)).toBeVisible()
    rerender(card({ ...idle, blockedBy: 'switch' }))
    expect(screen.getByRole('button', { name: 'Sign in again' })).toBeDisabled()
    expect(screen.queryByText(WAIT)).toBeNull()
  })

  it('names the failure on the card for that request and leaves the button retryable', () => {
    render(card({ ...idle, query: QUERY, failed: true }))
    expect(screen.getByText(FAILED)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Sign in again' })).toBeEnabled()
  })
})
