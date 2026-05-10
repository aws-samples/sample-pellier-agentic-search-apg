/**
 * UIContext tests — modal singleton + global keyboard shortcuts.
 *
 * Validates: Requirements 1.11.2, 1.11.3, 1.11.4, 1.11.5.
 */
import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
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
  const { activeModal, openModal, closeModal, toggleConcierge } = useUI()
  return (
    <div>
      <span data-testid="active">{activeModal ?? 'none'}</span>
      <button onClick={() => openModal('concierge')}>open-concierge</button>
      <button onClick={() => openModal('auth')}>open-auth</button>
      <button onClick={() => openModal('preferences')}>open-preferences</button>
      <button onClick={closeModal}>close</button>
      <button onClick={toggleConcierge}>toggle-concierge</button>
    </div>
  )
}

describe('UIContext modal singleton', () => {
  it('starts with no modal open', () => {
    render(<Probe />, { wrapper })
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('opening auth while concierge is open closes concierge (singleton)', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.click(screen.getByText('open-concierge'))
    expect(screen.getByTestId('active')).toHaveTextContent('concierge')

    await user.click(screen.getByText('open-auth'))
    // Only one modal is ever visible — auth replaced concierge.
    expect(screen.getByTestId('active')).toHaveTextContent('auth')
  })

  it('opening preferences while auth is open replaces auth', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('active')).toHaveTextContent('auth')

    await user.click(screen.getByText('open-preferences'))
    expect(screen.getByTestId('active')).toHaveTextContent('preferences')
  })

  it('closeModal() resets activeModal to null', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    await user.click(screen.getByText('open-concierge'))
    expect(screen.getByTestId('active')).toHaveTextContent('concierge')

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

  it('Escape closes whichever modal is active', async () => {
    const user = userEvent.setup()
    render(<Probe />, { wrapper })

    // Close concierge via Escape.
    await user.click(screen.getByText('open-concierge'))
    expect(screen.getByTestId('active')).toHaveTextContent('concierge')
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')

    // Close auth via Escape.
    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('active')).toHaveTextContent('auth')
    await user.keyboard('{Escape}')
    expect(screen.getByTestId('active')).toHaveTextContent('none')

    // Close preferences via Escape.
    await user.click(screen.getByText('open-preferences'))
    expect(screen.getByTestId('active')).toHaveTextContent('preferences')
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
    expect(() => renderHook(() => useUI())).toThrow(/UIProvider/)
  })

  it('toggleConcierge() respects current state', () => {
    const { result } = renderHook(() => useUI(), { wrapper })

    act(() => result.current.toggleConcierge())
    expect(result.current.activeModal).toBe('concierge')

    act(() => result.current.toggleConcierge())
    expect(result.current.activeModal).toBe(null)
  })
})
