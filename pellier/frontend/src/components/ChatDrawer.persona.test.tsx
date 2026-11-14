import { fireEvent, render, screen } from '@testing-library/react'
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
  stopTurn: vi.fn(),
  signedInAs: null as string | null,
  isLoading: false,
  activeModal: 'drawer' as string | null,
  messages: [] as Array<{ role: 'user' | 'assistant'; content: string; timestamp: Date }>,
}))

const shopper = vi.hoisted(() => ({
  persona: null as { id: string; display_name: string } | null,
  switching: false,
  conversation: 0,
  newConversationFailed: false,
  startNewConversation: vi.fn(async () => true),
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: shopper.persona,
    switching: shopper.switching,
    switchPersona: vi.fn(),
    signOut: vi.fn(),
    conversation: shopper.conversation,
    newConversationFailed: shopper.newConversationFailed,
    startNewConversation: shopper.startNewConversation,
  }),
}))
vi.mock('../contexts/UIContext', async importOriginal => ({
  ...await importOriginal<typeof import('../contexts/UIContext')>(),
  useUI: () => ({
    activeModal: state.activeModal,
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
    messages: state.messages,
    inputValue: '',
    isLoading: state.isLoading,
    stopTurn: state.stopTurn,
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
    shopper.conversation = 0
    shopper.newConversationFailed = false
    state.isLoading = false
    state.activeModal = 'drawer'
    state.messages = []
    state.signedInAs = null
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

  it('keeps Stop available for a running turn while a shopper switch is in flight', () => {
    shopper.switching = true
    state.isLoading = true
    render(<ChatDrawer />)
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled()
  })

  it('keeps send disabled during a shopper switch when no turn is running', () => {
    shopper.switching = true
    render(<ChatDrawer />)
    expect(screen.getByRole('button', { name: 'Ask Pellier' })).toBeDisabled()
  })
})

describe('A new conversation as the same shopper', () => {
  const THEO = { id: 'theo', display_name: 'Theo' }
  const SAID = [
    { role: 'assistant' as const, content: 'Good morning, Theo.', timestamp: new Date() },
    { role: 'user' as const, content: "I'm drawn to deep indigo linen.", timestamp: new Date() },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom has no element scrolling; the panel follows the latest reply with it.
    Element.prototype.scrollTo = vi.fn() as unknown as Element['scrollTo']
    shopper.persona = THEO
    shopper.switching = false
    shopper.conversation = 0
    shopper.newConversationFailed = false
    shopper.startNewConversation.mockResolvedValue(true)
    state.signedInAs = 'theo'
    state.activeModal = 'drawer'
    state.messages = SAID
    state.isLoading = false
  })

  it('offers New conversation once the signed-in shopper has said something', () => {
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(shopper.startNewConversation).toHaveBeenCalledTimes(1)
    // The thread is dropped when the new session lands, not on the click.
    expect(state.clearChat).not.toHaveBeenCalled()
  })

  it('offers nothing to leave before the first message, or to a visitor nobody signed in', () => {
    state.messages = SAID.slice(0, 1)
    const { unmount } = render(<ChatDrawer />)
    expect(screen.queryByRole('button', { name: 'New conversation' })).toBeNull()
    unmount()
    state.messages = SAID
    state.signedInAs = null
    shopper.persona = null
    render(<ChatDrawer />)
    expect(screen.queryByRole('button', { name: 'New conversation' })).toBeNull()
  })

  it('drops the thread and the draft when the new session lands, keeps the shopper, and returns focus to the composer', () => {
    const { rerender } = render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    state.messages = SAID.slice(0, 1)
    shopper.conversation = 1
    rerender(<ChatDrawer />)
    expect(state.clearChat).toHaveBeenCalledTimes(1)
    expect(state.setInputValue).toHaveBeenCalledWith('')
    expect(screen.getByRole('status')).toHaveTextContent('New conversation. You are still signed in as Theo.')
    expect(screen.getByRole('textbox', { name: 'Message Pellier' })).toHaveFocus()
  })

  it('says so when no new conversation could be started, and keeps this one', () => {
    shopper.newConversationFailed = true
    render(<ChatDrawer />)
    expect(screen.getByRole('alert')).toHaveTextContent("Pellier couldn't start a new conversation. This one is still open.")
    expect(state.clearChat).not.toHaveBeenCalled()
  })

  it('starts a new conversation from the closed panel\'s Clear chat, so a reload cannot bring the old one back', () => {
    state.activeModal = null
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear chat' }))
    expect(shopper.startNewConversation).toHaveBeenCalledTimes(1)
    expect(state.clearChat).not.toHaveBeenCalled()
  })

  it('opens the panel when Clear chat could not start a new conversation, so the alert is seen', async () => {
    state.activeModal = null
    shopper.startNewConversation.mockResolvedValueOnce(false)
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear chat' }))
    await vi.waitFor(() => expect(state.openModal).toHaveBeenCalledWith('drawer'))
    expect(state.clearChat).not.toHaveBeenCalled()
  })

  it('keeps New conversation focusable while its request runs, and sends it once', () => {
    shopper.startNewConversation.mockImplementation(() => new Promise<boolean>(() => {}))
    render(<ChatDrawer />)
    const button = screen.getByRole('button', { name: 'New conversation' })
    button.focus()
    fireEvent.click(button)
    fireEvent.click(button)
    expect(button).not.toBeDisabled()
    expect(button).toHaveFocus()
    expect(shopper.startNewConversation).toHaveBeenCalledTimes(1)
  })

  it('still clears a signed-out visitor\'s chat in place', () => {
    state.activeModal = null
    state.signedInAs = null
    shopper.persona = null
    render(<ChatDrawer />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear chat' }))
    expect(state.clearChat).toHaveBeenCalledTimes(1)
    expect(shopper.startNewConversation).not.toHaveBeenCalled()
  })
})
