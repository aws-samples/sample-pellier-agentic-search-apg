import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  openModal: vi.fn(),
  closeModal: vi.fn(),
  dismissDrawer: vi.fn(),
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
vi.mock('../contexts/UIContext', async importOriginal => ({
  ...await importOriginal<typeof import('../contexts/UIContext')>(),
  useUI: () => ({
    activeModal: 'drawer',
    openModal: state.openModal,
    closeModal: state.closeModal,
    dismissDrawer: state.dismissDrawer,
    drawerOpenedByShopper: () => false,
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
vi.mock('./StatusLines', () => ({ default: () => <dl data-testid="status-lines" /> }))

import ChatDrawer from './ChatDrawer'

describe('identity in the Ask Pellier panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('chooses a shopper at the top of the panel, and offers no other way in', () => {
    render(<ChatDrawer />)
    const group = screen.getByRole('group', { name: 'Signed in as' })
    expect(within(group).getAllByRole('button').map(chip => chip.textContent)).toEqual([
      'Anna', 'Marco', 'Theo', 'Jessica',
    ])
    expect(screen.getByTestId('persona-identity-boundary')).toBeInTheDocument()
    expect(screen.queryByTestId('workshop-sign-in')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sign in/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/scenario/i)).not.toBeInTheDocument()
  })

  it('asks for a customer while nobody is signed in, and points at the bar and the chips', () => {
    render(<ChatDrawer />)
    expect(screen.getByTestId('ask-panel-subtitle')).toHaveTextContent('Pick a customer to start')
    expect(screen.getByTestId('ask-panel-empty')).toHaveTextContent(
      'choose Anna, Marco, Theo or Jessica above to follow their story: finding, checking stock, remembering, then asking a person before money moves.',
    )
  })

  it('closes when the shopper asks, and remembers it', () => {
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Close Ask Pellier' }))
    expect(state.dismissDrawer).toHaveBeenCalledTimes(1)
  })

  it('keeps the session facts under the header', () => {
    render(<ChatDrawer />)
    expect(screen.getByText('Session details')).toBeInTheDocument()
    expect(screen.getByTestId('status-lines')).toBeInTheDocument()
  })
})
