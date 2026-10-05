/**
 * UIContext tests — modal singleton + global keyboard shortcuts.
 *
 * Validates: Requirements 1.11.2, 1.11.3, 1.11.4, 1.11.5.
 */
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { UIProvider, useUI } from './UIContext'

function wrapper({ children }: { children: React.ReactNode }) {
  return <UIProvider>{children}</UIProvider>
}

/**
 * Small probe component that surfaces the current activeModal to the DOM and
 * exposes buttons we can click from the test to drive state transitions. Using
 * a real render (rather than pure renderHook dispatches) lets us verify the
 * global keydown listener installed by UIProvider reacts to window events.
 */
function Probe() {
  const { activeModal, openModal, closeModal, toggleDrawer } = useUI()
  return (
    <div>
      <span data-testid="active">{activeModal ?? 'none'}</span>
      <button onClick={() => openModal('drawer')}>open-drawer</button>
      <button onClick={() => openModal('auth')}>open-auth</button>
      <button onClick={() => openModal('cart')}>open-cart</button>
      <button onClick={() => closeModal()}>close</button>
      <button onClick={toggleDrawer}>toggle-drawer</button>
    </div>
  )
}

describe('UIContext modal singleton', () => {
  it('starts with no modal open', () => {
    render(<Probe />, { wrapper })
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('opening auth while the shopper drawer is open closes the drawer (singleton)', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.click(screen.getByText('open-drawer'))
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')

    await user.click(screen.getByText('open-auth'))
    // Only one modal is ever visible — auth replaced the drawer.
    expect(screen.getByTestId('active')).toHaveTextContent('auth')
  })

  it('opening the cart while auth is open replaces auth', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('active')).toHaveTextContent('auth')

    await user.click(screen.getByText('open-cart'))
    expect(screen.getByTestId('active')).toHaveTextContent('cart')
  })

  it('closeModal() resets activeModal to null', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.click(screen.getByText('open-drawer'))
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')

    await user.click(screen.getByText('close'))
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })
})

describe('UIContext global keyboard shortcuts', () => {
  it('Cmd+K toggles the chat surface open and closed (default: drawer)', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    expect(screen.getByTestId('active')).toHaveTextContent('none')

    await user.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')

    await user.keyboard('{Meta>}k{/Meta}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('Ctrl+K also toggles the chat surface (non-mac shortcut)', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.keyboard('{Control>}k{/Control}')
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')

    await user.keyboard('{Control>}k{/Control}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('leaves Cmd+K to the browser when the active route has no chat surface', () => {
    const { result } = renderHook(() => useUI(), { wrapper })

    act(() => {
      ;(result.current.setChatSurface as (surface: 'none') => void)('none')
    })
    fireEvent.keyDown(window, { key: 'k', metaKey: true })

    expect(result.current.activeModal).toBeNull()
  })

  it('Escape closes whichever modal is active', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    // Close the shopper drawer via Escape.
    await user.click(screen.getByText('open-drawer'))
    expect(screen.getByTestId('active')).toHaveTextContent('drawer')
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')

    // Close auth via Escape.
    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('active')).toHaveTextContent('auth')
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')

    // Close the cart via Escape.
    await user.click(screen.getByText('open-cart'))
    expect(screen.getByTestId('active')).toHaveTextContent('cart')
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('Escape is a no-op when no modal is active', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    expect(screen.getByTestId('active')).toHaveTextContent('none')
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })
})

describe('UIContext hook ergonomics', () => {
  it('useUI throws a clear error when used outside UIProvider', () => {
    // renderHook without a wrapper — useContext returns undefined and the
    // hook must throw rather than silently return an empty shape.
    const preventJSDOMError = (event: ErrorEvent) => event.preventDefault()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    window.addEventListener('error', preventJSDOMError)
    try {
      expect(() => renderHook(() => useUI())).toThrow(/UIProvider/)
    } finally {
      window.removeEventListener('error', preventJSDOMError)
      consoleError.mockRestore()
    }
  })

  it('toggleDrawer() respects current state', () => {
    const { result } = renderHook(() => useUI(), { wrapper })

    act(() => result.current.toggleDrawer())
    expect(result.current.activeModal).toBe('drawer')

    act(() => result.current.toggleDrawer())
    expect(result.current.activeModal).toBe(null)
  })
})

describe('Ask Pellier docked by default on a desktop width', () => {
  const width = window.innerWidth
  const setWidth = (value: number) =>
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value })

  afterEach(() => {
    setWidth(width)
    window.history.pushState({}, '', '/')
  })

  it('opens docked beside the store, without taking focus as an open the shopper asked for', () => {
    setWidth(1440)
    const { result } = renderHook(() => useUI(), { wrapper })
    expect(result.current.activeModal).toBe('drawer')
    expect(result.current.drawerOpenedByShopper()).toBe(false)

    act(() => result.current.openModal('drawer'))
    expect(result.current.drawerOpenedByShopper()).toBe(true)
  })

  it('stays closed where it stacks under the page, and on the Operator and sign-in pages', () => {
    setWidth(1079)
    expect(renderHook(() => useUI(), { wrapper }).result.current.activeModal).toBe(null)

    setWidth(1440)
    window.history.pushState({}, '', '/operator')
    expect(renderHook(() => useUI(), { wrapper }).result.current.activeModal).toBe(null)
    window.history.pushState({}, '', '/signin')
    expect(renderHook(() => useUI(), { wrapper }).result.current.activeModal).toBe(null)
  })

  it('docks again on the storefront after a route closed it, unless the shopper closed it', () => {
    setWidth(1440)
    const { result } = renderHook(() => useUI(), { wrapper })

    act(() => result.current.closeModal())
    act(() => result.current.restoreDock())
    expect(result.current.activeModal).toBe('drawer')

    act(() => result.current.dismissDrawer())
    act(() => result.current.restoreDock())
    expect(result.current.activeModal).toBe(null)

    act(() => result.current.openModal('drawer'))
    act(() => result.current.closeModal())
    act(() => result.current.restoreDock())
    expect(result.current.activeModal).toBe('drawer')
  })

  it('remembers Escape as the shopper closing the panel', () => {
    setWidth(1440)
    const { result } = renderHook(() => useUI(), { wrapper })
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(result.current.activeModal).toBe(null)
    act(() => result.current.restoreDock())
    expect(result.current.activeModal).toBe(null)
  })
})
