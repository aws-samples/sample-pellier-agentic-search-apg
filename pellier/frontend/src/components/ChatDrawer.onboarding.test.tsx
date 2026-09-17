import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UIProvider, useUI } from '../contexts/UIContext'
import ChatDrawer from './ChatDrawer'
import Header from './Header'

const ANNA = {
  id: 'anna', display_name: 'Anna', customer_id: 'C-ANNA',
  avatar_initial: 'A', avatar_color: '#333', role_tag: 'Gift-giver',
  stats: { visits: 6, orders: 5, last_seen_days: 9 },
}
let persona: typeof ANNA | null = null
let cartOpen = false
const chat = vi.hoisted(() => ({
  sendMessage: vi.fn(), clearChat: vi.fn(), setInputValue: vi.fn(), retryMessage: vi.fn(),
}))
const switchPersona = vi.fn(async () => { persona = ANNA; return true })
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({ persona, switchPersona, switching: false, signOut: vi.fn() }),
}))
vi.mock('../contexts/AuthContext', () => ({ useOptionalAuth: () => null }))
vi.mock('../contexts/LayoutContext', () => ({ useLayout: () => ({ guardrailsEnabled: true }) }))
vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({ items: [], addToCart: vi.fn(), setCartOpen: vi.fn(), cartOpen }),
}))
vi.mock('../hooks/useAgentChat', () => ({
  useAgentChat: () => ({ messages: [], inputValue: '', isLoading: false, ...chat }),
}))
vi.mock('./PellierChatBody', () => ({ default: () => null }))
vi.mock('./PellierWelcome', () => ({ default: () => null }))

function EntryPoints() {
  const { openDrawerWithQuery } = useUI()
  return <>
    <Header />
    <button onClick={() => openDrawerWithQuery('Tell me about the Linen Shirt.')}>
      Ask about this piece
    </button>
    <ChatDrawer />
  </>
}
function App() {
  return <MemoryRouter><UIProvider><EntryPoints /></UIProvider></MemoryRouter>
}

describe('Storefront conversation entry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    persona = null
    cartOpen = false
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([ANNA]), { status: 200 })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('retains a product question until a scenario is selected, then sends it exactly once', async () => {
    const view = render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask about this piece' }))
    expect(await screen.findByTestId('persona-card-anna')).toBeInTheDocument()
    expect(chat.sendMessage).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('persona-card-anna'))
    await waitFor(() => expect(switchPersona).toHaveBeenCalledWith('anna'))
    view.rerender(<App />)
    expect(await screen.findByRole('dialog', { name: 'Chat with Pellier' })).toBeInTheDocument()
    expect(chat.sendMessage).toHaveBeenCalledExactlyOnceWith('Tell me about the Linen Shirt.')
    expect(chat.clearChat.mock.invocationCallOrder[0]).toBeLessThan(chat.sendMessage.mock.invocationCallOrder[0])
    view.rerender(<App />)
    expect(chat.sendMessage).toHaveBeenCalledTimes(1)
  })

  it('cancels the pending question when the chooser is dismissed', async () => {
    const view = render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask about this piece' }))
    await screen.findByTestId('persona-card-anna')
    fireEvent.click(screen.getByTestId('persona-modal-close'))
    persona = ANNA
    view.rerender(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask Pellier' }))
    expect(await screen.findByRole('dialog', { name: 'Chat with Pellier' })).toBeInTheDocument()
    expect(chat.sendMessage).not.toHaveBeenCalled()
  })

  it('continues from the header Ask action into the conversation after scenario selection', async () => {
    const view = render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask Pellier' }))
    fireEvent.click(await screen.findByTestId('persona-card-anna'))
    await waitFor(() => expect(switchPersona).toHaveBeenCalledWith('anna'))
    view.rerender(<App />)
    expect(await screen.findByRole('dialog', { name: 'Chat with Pellier' })).toBeInTheDocument()
    expect(chat.sendMessage).not.toHaveBeenCalled()
  })

  it('yields the conversation to the bag and resumes without resending the question', async () => {
    persona = ANNA
    const view = render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask about this piece' }))
    expect(await screen.findByRole('dialog', { name: 'Chat with Pellier' })).toBeInTheDocument()
    cartOpen = true
    view.rerender(<App />)
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Chat with Pellier' })).not.toBeInTheDocument())
    cartOpen = false
    view.rerender(<App />)
    expect(await screen.findByRole('dialog', { name: 'Chat with Pellier' })).toBeInTheDocument()
    expect(chat.sendMessage).toHaveBeenCalledExactlyOnceWith('Tell me about the Linen Shirt.')
  })
})
