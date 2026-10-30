import { render } from '@testing-library/react'
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
  signedInAs: null as string | null,
}))

const shopper = vi.hoisted(() => ({
  persona: null as { id: string; display_name: string } | null,
  switching: false,
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: shopper.persona,
    switching: shopper.switching,
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
vi.mock('../hooks/useShopperSignIn', async importOriginal => ({
  ...await importOriginal<typeof import('../hooks/useShopperSignIn')>(),
  useSignedInShopper: () => state.signedInAs,
}))
vi.mock('./PellierChatBody', () => ({ default: () => null }))
vi.mock('./PellierWelcome', () => ({ default: () => null }))
vi.mock('./StatusLines', () => ({ default: () => <dl data-testid="status-lines" /> }))

import ChatDrawer from './ChatDrawer'

const MARCO = { id: 'marco', display_name: 'Marco Delgado' }
const ANNA = { id: 'anna', display_name: 'Anna Reyes' }

describe('Ask Pellier conversation across shoppers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    shopper.persona = null
    shopper.switching = false
  })

  it('keeps the saved conversation when the shopper is restored after a reload', () => {
    const { rerender } = render(<ChatDrawer />)
    shopper.persona = MARCO
    rerender(<ChatDrawer />)
    expect(state.clearChat).not.toHaveBeenCalled()
  })

  it('starts over when a shopper is chosen from the panel', () => {
    const { rerender } = render(<ChatDrawer />)
    shopper.switching = true
    rerender(<ChatDrawer />)
    shopper.persona = MARCO
    shopper.switching = false
    rerender(<ChatDrawer />)
    expect(state.clearChat).toHaveBeenCalledTimes(1)
  })

  it('starts over when one shopper replaces another', () => {
    shopper.persona = MARCO
    const { rerender } = render(<ChatDrawer />)
    shopper.persona = ANNA
    rerender(<ChatDrawer />)
    expect(state.clearChat).toHaveBeenCalledTimes(1)
  })
})
