/**
 * Sign in again, and a shopper chosen meanwhile, against the real providers.
 *
 * `ChatDrawer.session-refresh.test.tsx` pins what the drawer calls. This file pins where the
 * browser's session ends up when a slow sign-in for the previous shopper is still on its way
 * after the next shopper was chosen: the page and `/api/auth/me` must name the same shopper,
 * and nothing is sent again for the shopper who lost.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const FAILED = 'What is happening with my ticket?'

const chat = vi.hoisted(() => ({
  isLoading: false,
  retryMessage: vi.fn(() => Promise.resolve()),
}))

vi.mock('../contexts/UIContext', async importOriginal => ({
  ...await importOriginal<typeof import('../contexts/UIContext')>(),
  useUI: () => ({
    activeModal: 'drawer',
    openModal: vi.fn(),
    closeModal: vi.fn(),
    dismissDrawer: vi.fn(),
    drawerOpenedByShopper: () => false,
    consumePendingQuery: vi.fn(() => null),
    setTurnRunning: vi.fn(),
  }),
}))
vi.mock('../contexts/LayoutContext', () => ({ useLayout: () => ({ guardrailsEnabled: true }) }))
vi.mock('../contexts/CartContext', () => ({ useCart: () => ({ addToCart: vi.fn() }) }))
vi.mock('../hooks/useAgentChat', () => ({
  useAgentChat: () => ({
    messages: [
      { role: 'assistant', content: 'Welcome back.' },
      { role: 'user', content: FAILED },
    ],
    inputValue: '',
    isLoading: chat.isLoading,
    setInputValue: vi.fn(),
    clearChat: vi.fn(),
    sendMessage: vi.fn(),
    retryMessage: chat.retryMessage,
  }),
}))
vi.mock('./PellierChatBody', async () => {
  const { default: ChatFailureCard } = await import('./ChatFailureCard')
  return {
    default: ({ onAuthenticate, reauth }: { onAuthenticate: (query: string) => void, reauth?: unknown }) => {
      const extra: Record<string, unknown> = { reauth }
      return (
        <ChatFailureCard
          failure={{ code: 'authentication_required', retryable: false, query: FAILED }}
          onRetry={() => {}}
          onEditRequest={() => {}}
          onAuthenticate={onAuthenticate}
          {...extra}
        />
      )
    },
  }
})
vi.mock('./PellierWelcome', () => ({ default: () => null }))
vi.mock('./StatusLines', () => ({ default: () => <dl data-testid="status-lines" /> }))

import { AuthProvider } from '../contexts/AuthContext'
import { PersonaProvider } from '../contexts/PersonaContext'
import { useShopperSignIn } from '../hooks/useShopperSignIn'
import { installShopperSessionStandIn, type HeldSignIn, type ShopperSessionStandIn } from '../testing/shopperSessionStandIn'
import ChatDrawer from './ChatDrawer'

/** Starts the conversation as Theo, the way a chip in the panel does. */
function ChooseTheo() {
  const { choose } = useShopperSignIn()
  return <button type="button" onClick={() => void choose('theo')}>Start as Theo</button>
}

function DrawerTree() {
  return (
    <AuthProvider surface="shopper">
      <PersonaProvider>
        <ChooseTheo />
        <ChatDrawer />
      </PersonaProvider>
    </AuthProvider>
  )
}

const renderDrawer = () => render(<DrawerTree />)

let browser: ShopperSessionStandIn

/** The response arrives inside act, so the updates it causes are not reported as stray. */
const arrive = (signIn: HeldSignIn, how: 'release' | 'refuse' = 'release') =>
  act(async () => { signIn[how]() })

async function startAsTheo() {
  fireEvent.click(screen.getByRole('button', { name: 'Start as Theo' }))
  await arrive(await browser.nth(0))
  await waitFor(() => expect(screen.getByTestId('ask-signed-in-name')).toHaveTextContent('Theo'))
}

async function meSays(): Promise<string | undefined> {
  const response = await fetch('/api/auth/me?surface=shopper')
  return response.ok ? ((await response.json()) as { username: string }).username : undefined
}

describe('Sign in again while another shopper is chosen', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    chat.isLoading = false
    chat.retryMessage.mockClear()
    Element.prototype.scrollTo = vi.fn() as unknown as Element['scrollTo']
    browser = installShopperSessionStandIn()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('leaves the page, the session and the conversation with the shopper chosen last', async () => {
    renderDrawer()
    await startAsTheo()

    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    const theoAgain = await browser.nth(1)
    fireEvent.click(screen.getByTestId('ask-switch-shopper'))
    fireEvent.click(screen.getByTestId('ask-shopper-anna'))
    const anna = await browser.nth(2)
    await arrive(anna)
    await waitFor(() => expect(screen.getByTestId('ask-signed-in-name')).toHaveTextContent('Anna'))
    // Theo's slow response finally arrives.
    await arrive(theoAgain)

    await act(async () => { await new Promise(settle => setTimeout(settle, 50)) })
    expect(screen.getByTestId('ask-signed-in-name')).toHaveTextContent('Anna')
    expect(browser.jar.shopper).toBe('anna')
    expect(await meSays()).toBe('anna')
    expect(chat.retryMessage).not.toHaveBeenCalled()
  })

  it('signs the same shopper in again and sends the request exactly once', async () => {
    renderDrawer()
    await startAsTheo()

    const button = screen.getByRole('button', { name: 'Sign in again' })
    fireEvent.click(button)
    fireEvent.click(button)
    const pending = screen.getByRole('button', { name: 'Signing in again' })
    expect(pending).toBeDisabled()
    await arrive(await browser.nth(1))

    await waitFor(() => expect(chat.retryMessage).toHaveBeenCalledTimes(1))
    expect(chat.retryMessage).toHaveBeenCalledWith(FAILED)
    expect(browser.jar.shopper).toBe('theo')
    expect(browser.signIns).toHaveLength(2)
  })

  it('says so when it could not sign in, and a retry signs in and sends the request', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    renderDrawer()
    await startAsTheo()

    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    await arrive(await browser.nth(1), 'refuse')
    const message = await screen.findByText('Pellier could not sign you in again. Try again in a moment.')
    expect(message).toBeVisible()
    expect(chat.retryMessage).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Sign in again' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Sign in again' }))
    expect(screen.queryByText('Pellier could not sign you in again. Try again in a moment.')).toBeNull()
    await arrive(await browser.nth(2))
    await waitFor(() => expect(chat.retryMessage).toHaveBeenCalledExactlyOnceWith(FAILED))
    warn.mockRestore()
  })

  it('waits, and says why, while a reply is running instead of doing nothing', async () => {
    const { rerender } = renderDrawer()
    await startAsTheo()
    chat.isLoading = true
    rerender(<DrawerTree />)

    const button = screen.getByRole('button', { name: 'Sign in again' })
    expect(button).toBeDisabled()
    expect(screen.getByText('Sign in again once the current reply finishes.')).toBeVisible()
    fireEvent.click(button)
    expect(browser.signIns).toHaveLength(1)
    expect(chat.retryMessage).not.toHaveBeenCalled()
  })
})
