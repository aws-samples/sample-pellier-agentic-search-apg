import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const FAILED = 'What is happening with my ticket?'

const state = vi.hoisted(() => ({
  persona: { id: 'theo', display_name: 'Theo', avatar_initial: 'T', avatar_color: '#333' } as
    { id: string; display_name: string; avatar_initial: string; avatar_color: string } | null,
  openModal: vi.fn(),
  switchPersona: vi.fn(),
  retryMessage: vi.fn(() => Promise.resolve()),
  // The shopper the last sign-in set the session for, which `/api/auth/me` then reports.
  cookie: '' as string,
  refresh: vi.fn(() => Promise.resolve(state.cookie || null)),
  workshopSignIn: vi.fn((id: string): Promise<unknown> => { state.cookie = id; return Promise.resolve({ ok: true }) }),
}))

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: state.persona,
    switching: false,
    switchPersona: state.switchPersona,
    signOut: vi.fn(),
  }),
}))
vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ isAuthenticated: false, user: null, refresh: state.refresh }),
}))
vi.mock('../services/passwordAuth', async importOriginal => ({
  ...await importOriginal<typeof import('../services/passwordAuth')>(),
  workshopSignIn: state.workshopSignIn,
}))
vi.mock('../contexts/UIContext', async importOriginal => ({
  ...await importOriginal<typeof import('../contexts/UIContext')>(),
  useUI: () => ({
    activeModal: 'drawer',
    openModal: state.openModal,
    closeModal: vi.fn(),
    dismissDrawer: vi.fn(),
    drawerOpenedByShopper: () => false,
    consumePendingQuery: vi.fn(() => null),
    setTurnRunning: vi.fn(),
  }),
}))
vi.mock('../contexts/LayoutContext', () => ({
  useLayout: () => ({ guardrailsEnabled: true }),
}))
vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({ addToCart: vi.fn() }),
}))
vi.mock('../hooks/useAgentChat', () => ({
  useAgentChat: () => ({
    messages: [
      { role: 'assistant', content: 'Welcome back.' },
      { role: 'user', content: FAILED },
    ],
    inputValue: '',
    isLoading: false,
    setInputValue: vi.fn(),
    clearChat: vi.fn(),
    sendMessage: vi.fn(),
    retryMessage: state.retryMessage,
  }),
}))
vi.mock('./PellierChatBody', () => ({
  default: ({ onAuthenticate }: { onAuthenticate: (query: string) => void }) => (
    <button type="button" onClick={() => onAuthenticate(FAILED)}>Sign in again</button>
  ),
}))
vi.mock('./PellierWelcome', () => ({ default: () => null }))
vi.mock('./StatusLines', () => ({ default: () => <dl data-testid="status-lines" /> }))

import ChatDrawer from './ChatDrawer'

describe('Sign in again after a demo shopper’s session expires', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // The thread follows its latest reply; jsdom has no Element.scrollTo.
    Element.prototype.scrollTo = vi.fn() as unknown as Element['scrollTo']
    state.persona = { id: 'theo', display_name: 'Theo', avatar_initial: 'T', avatar_color: '#333' }
    state.cookie = 'theo'
    state.workshopSignIn.mockImplementation(() => Promise.resolve({ ok: true }))
  })

  it('signs the same shopper in again, keeps the conversation and sends the request again', async () => {
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    await waitFor(() => expect(state.retryMessage).toHaveBeenCalledWith(FAILED))
    expect(state.workshopSignIn).toHaveBeenCalledWith('theo', expect.any(AbortSignal))
    expect(state.refresh).toHaveBeenCalledTimes(1)
    // A demo shopper has no password to type, and a switch would start a new conversation.
    expect(state.openModal).not.toHaveBeenCalled()
    expect(state.switchPersona).not.toHaveBeenCalled()
  })

  it('retries nothing when the sign-in does not complete', async () => {
    state.workshopSignIn.mockImplementation(() => Promise.reject(new Error('auth_unavailable')))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    await waitFor(() => expect(warn).toHaveBeenCalled())
    expect(state.retryMessage).not.toHaveBeenCalled()
    expect(state.openModal).not.toHaveBeenCalled()
    warn.mockRestore()
  })

  it('signs in once when Sign in again is pressed twice', async () => {
    let finish: (value: unknown) => void = () => {}
    state.workshopSignIn.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<ChatDrawer />)
    const button = screen.getByRole('button', { name: 'Sign in again' })
    fireEvent.click(button)
    fireEvent.click(button)
    finish({ ok: true })
    await waitFor(() => expect(state.retryMessage).toHaveBeenCalledTimes(1))
    expect(state.workshopSignIn).toHaveBeenCalledTimes(1)
  })

  it('does not send the request again for a shopper chosen during the sign-in', async () => {
    let finish: (value: unknown) => void = () => {}
    state.workshopSignIn.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { rerender } = render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    state.persona = { id: 'marco', display_name: 'Marco', avatar_initial: 'M', avatar_color: '#333' }
    rerender(<ChatDrawer />)
    finish({ ok: true })
    await waitFor(() => expect(state.refresh).toHaveBeenCalledTimes(1))
    expect(state.retryMessage).not.toHaveBeenCalled()
  })

  it('keeps the sign-in page for a shopper who is not one of the four demo shoppers', () => {
    state.persona = { id: 'fresh', display_name: 'Fresh', avatar_initial: 'F', avatar_color: '#333' }
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    expect(state.openModal).toHaveBeenCalledWith('auth')
    expect(state.workshopSignIn).not.toHaveBeenCalled()
  })

  it('keeps the sign-in page for a session that is not a demo shopper', () => {
    state.persona = null
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    expect(state.openModal).toHaveBeenCalledWith('auth')
    expect(state.workshopSignIn).not.toHaveBeenCalled()
  })
})
