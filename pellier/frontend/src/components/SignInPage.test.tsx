import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PasswordAuthError } from '../services/passwordAuth'

const calls = vi.hoisted(() => ({ passwordAuth: vi.fn() }))
vi.mock('../services/passwordAuth', async (original) => ({ ...await original<typeof import('../services/passwordAuth')>(), passwordAuth: calls.passwordAuth }))
import SignInPage from './SignInPage'

const originalLocation = window.location
const assign = vi.fn()
beforeEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: { origin: 'http://localhost', search: '?returnTo=%2Foperator', assign } })
  calls.passwordAuth.mockReset(); assign.mockReset()
})
afterEach(() => { Object.defineProperty(window, 'location', { configurable: true, value: originalLocation }) })

function credentials() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'operator' } })
  fireEvent.change(screen.getByLabelText('Password', { exact: true }), { target: { value: 'private-password' } })
}

describe('dedicated Pellier sign-in', () => {
  it('keeps credentials on a failed request and permits password visibility', async () => {
    calls.passwordAuth.mockRejectedValue(new PasswordAuthError('invalid_credentials'))
    render(<SignInPage />)
    credentials()
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(screen.getByLabelText('Password', { exact: true })).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('did not match')
    expect(screen.getByLabelText('Username')).toHaveValue('operator')
    expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('private-password')
    expect(assign).not.toHaveBeenCalled()
  })
  it('returns to the requested record after a verified server session', async () => {
    calls.passwordAuth.mockResolvedValue({ status: 'signed_in', returnTo: '/operator/clients/CUST-JESSICA' })
    render(<SignInPage />); credentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/operator/clients/CUST-JESSICA'))
    expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('')
  })
  it('continues additional verification without treating a challenge as sign-in', async () => {
    calls.passwordAuth.mockResolvedValue({ status: 'verification_required' })
    render(<SignInPage />); credentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    const link = await screen.findByRole('link', { name: 'Continue secure verification' })
    expect(link).toHaveAttribute('href', '/api/auth/signin?provider=email&returnTo=%2Foperator&surface=staff')
    expect(assign).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Password', { exact: true })).toHaveValue('')
  })
  it('writes the staff session when opened from the Operator', async () => {
    calls.passwordAuth.mockResolvedValue({ status: 'signed_in', returnTo: '/operator' })
    render(<SignInPage />); credentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/operator'))
    expect(calls.passwordAuth).toHaveBeenCalledWith(
      'sign-in', expect.objectContaining({ surface: 'staff', returnTo: '/operator' }), expect.any(AbortSignal),
    )
  })
  it('writes the shopper session from the storefront, and tells staff to use the desk', async () => {
    Object.defineProperty(window, 'location', { configurable: true, value: { origin: 'http://localhost', search: '?returnTo=%2F', assign } })
    calls.passwordAuth.mockRejectedValue(new PasswordAuthError('staff_use_operator'))
    render(<SignInPage />); credentials()
    expect(screen.getByRole('link', { name: 'Use another sign-in method' }))
      .toHaveAttribute('href', '/api/auth/signin?provider=email&returnTo=%2F&surface=shopper')
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This is a staff account. Sign in from the Operator desk instead.')
    expect(calls.passwordAuth).toHaveBeenCalledWith(
      'sign-in', expect.objectContaining({ surface: 'shopper' }), expect.any(AbortSignal),
    )
    expect(assign).not.toHaveBeenCalled()
  })
  it('requires matching passwords before confirming a recovery code', async () => {
    calls.passwordAuth.mockResolvedValueOnce({ status: 'recovery_requested' })
    render(<SignInPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Forgot password?' }))
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'operator' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send recovery code' }))
    await screen.findByLabelText('Recovery code')
    fireEvent.change(screen.getByLabelText('Recovery code'), { target: { value: '123456' } })
    fireEvent.change(screen.getByLabelText('New password', { exact: true }), { target: { value: 'first-password' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'different-password' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update password' })) })
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match')
    expect(calls.passwordAuth).toHaveBeenCalledTimes(1)
  })
})
