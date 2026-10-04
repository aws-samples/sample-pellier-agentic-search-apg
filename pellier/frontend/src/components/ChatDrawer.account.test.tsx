import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  openModal: vi.fn(),
  closeModal: vi.fn(),
  consumePendingQuery: vi.fn(() => null),
  setInputValue: vi.fn(),
  clearChat: vi.fn(),
  sendMessage: vi.fn(),
  retryMessage: vi.fn(),
  addToCart: vi.fn(),
}))

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: { id: 'marco', display_name: 'Marco Delgado', avatar_initial: 'M', avatar_color: '#333' },
    switchPersona: vi.fn(),
    signOut: vi.fn(),
  }),
}))
vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({
    activeModal: 'drawer',
    openModal: state.openModal,
    closeModal: state.closeModal,
    consumePendingQuery: state.consumePendingQuery,
    setTurnRunning: vi.fn(),
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
vi.mock('./WorkshopSignIn', () => ({ default: () => <div data-testid="workshop-sign-in" /> }))
vi.mock('./StatusLines', () => ({ default: () => <dl data-testid="status-lines" /> }))

import ChatDrawer from './ChatDrawer'

describe('the account handoff in Ask Pellier', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mounts the one-click shopper sign-in in place of the sign-out, sign-in, scenario, verify sequence', () => {
    render(<ChatDrawer />)
    expect(screen.getByTestId('workshop-sign-in')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in for account requests' })).not.toBeInTheDocument()
    expect(screen.queryByText('Scenario & account details')).not.toBeInTheDocument()
  })

  it('keeps the session facts beneath the chips', () => {
    render(<ChatDrawer />)
    expect(screen.getByText('Session details')).toBeInTheDocument()
    expect(screen.getByTestId('status-lines')).toBeInTheDocument()
  })
})
