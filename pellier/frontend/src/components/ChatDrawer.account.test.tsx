import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  authenticated: true,
  logout: vi.fn(),
  clearPersona: vi.fn(),
  openModal: vi.fn(),
  closeModal: vi.fn(),
  consumePendingQuery: vi.fn(() => null),
  setInputValue: vi.fn(),
  clearChat: vi.fn(),
  sendMessage: vi.fn(),
  retryMessage: vi.fn(),
  addToCart: vi.fn(),
}))

vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    isAuthenticated: state.authenticated,
    user: state.authenticated ? { givenName: 'marco', email: 'marco@example.com' } : null,
    logout: state.logout,
  }),
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: { id: 'marco', display_name: 'Marco Delgado', avatar_initial: 'M', avatar_color: '#333' },
    signOut: state.clearPersona,
  }),
}))
vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({
    activeModal: 'drawer',
    openModal: state.openModal,
    closeModal: state.closeModal,
    consumePendingQuery: state.consumePendingQuery,
  }),
}))
vi.mock('../contexts/LayoutContext', () => ({
  useLayout: () => ({ guardrailsEnabled: true }),
}))
vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({ addToCart: state.addToCart }),
}))
vi.mock('../hooks/useAgentChat', () => ({
  useAgentChat: () => ({
    messages: [],
    inputValue: '',
    isLoading: false,
    setInputValue: state.setInputValue,
    clearChat: state.clearChat,
    sendMessage: state.sendMessage,
    retryMessage: state.retryMessage,
  }),
}))
vi.mock('./PellierChatBody', () => ({ default: () => null }))
vi.mock('./PellierWelcome', () => ({ default: () => null }))

import ChatDrawer from './ChatDrawer'

describe('Shopper account handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    state.authenticated = true
  })

  it('signs out of the verified account instead of only clearing the scenario', () => {
    render(<ChatDrawer />)
    fireEvent.click(screen.getByText('Scenario & account details'))
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(state.logout).toHaveBeenCalledOnce()
    expect(state.clearPersona).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Sign in for account requests' })).not.toBeInTheDocument()
  })

  it('offers account sign-in even when the Marco scenario is already selected', () => {
    state.authenticated = false
    render(<ChatDrawer />)
    fireEvent.click(screen.getByText('Scenario & account details'))
    fireEvent.click(screen.getByRole('button', { name: 'Sign in for account requests' }))
    expect(state.openModal).toHaveBeenCalledWith('auth')
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()
  })
})
