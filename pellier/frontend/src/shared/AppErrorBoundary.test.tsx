/**
 * AppErrorBoundary — a render throw anywhere in the route tree must not
 * blank the whole app.
 *
 * Before this component existed, `App.tsx` mounted every route (Pellier,
 * Operator, and Observatory's own lazy chunk) behind only a `<Suspense>`
 * loading fallback, with no `componentDidCatch` above it. A throw during
 * render — including a stale content-hashed chunk after a redeploy, which
 * `vite.config.ts` explicitly hashes for "workshop reliability" — crashed
 * past React's tree with nothing to show and no recovery action. Only the
 * Observatory's own nested outlet had a boundary of its own.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppErrorBoundary from './AppErrorBoundary'
import ObservatoryErrorBoundary from '../observatory/shell/ObservatoryErrorBoundary'

function Bomb(): never {
  throw new Error('boom: simulated render failure')
}

describe('AppErrorBoundary', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    // componentDidCatch intentionally logs; keep the test output clean
    // without hiding a real failure to log (assert the call count below).
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it('renders children normally when nothing throws', () => {
    render(
      <MemoryRouter>
        <AppErrorBoundary>
          <p>ordinary content</p>
        </AppErrorBoundary>
      </MemoryRouter>,
    )
    expect(screen.getByText('ordinary content')).toBeInTheDocument()
  })

  it('catches a render throw and shows a distinct recovery state instead of a blank page', () => {
    render(
      <MemoryRouter>
        <AppErrorBoundary>
          <Bomb />
        </AppErrorBoundary>
      </MemoryRouter>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('This page did not load')).toBeInTheDocument()
    expect(screen.queryByText(/boom: simulated render failure/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return to Pellier' })).toBeInTheDocument()
    expect(consoleErrorSpy).toHaveBeenCalled()
  })

  it('does not claim lab progress or evidence was lost', () => {
    render(
      <MemoryRouter>
        <AppErrorBoundary>
          <Bomb />
        </AppErrorBoundary>
      </MemoryRouter>,
    )
    // VOICE.md forbids collapsed, alarming failure language. This boundary
    // covers Storefront and Operator too, so it must not claim workshop
    // progress specifically -- it names the render failure and the recovery.
    expect(screen.queryByText(/lab progress/i)).not.toBeInTheDocument()
  })

  for (const [name, Boundary] of [['App', AppErrorBoundary], ['Observatory', ObservatoryErrorBoundary]] as const) {
    it(`${name} recovers from a failed route when navigation changes`, () => {
      const { rerender } = render(
        <MemoryRouter><Boundary resetKey="/failed"><Bomb /></Boundary></MemoryRouter>,
      )
      expect(screen.queryByText('Recovered route')).not.toBeInTheDocument()
      rerender(
        <MemoryRouter><Boundary resetKey="/healthy"><p>Recovered route</p></Boundary></MemoryRouter>,
      )
      expect(screen.getByText('Recovered route')).toBeInTheDocument()
    })

    it(`${name} keeps healthy child state when the route changes`, () => {
      const { rerender } = render(
        <MemoryRouter><Boundary resetKey="/replay"><input aria-label="Session note" /></Boundary></MemoryRouter>,
      )
      fireEvent.change(screen.getByLabelText('Session note'), { target: { value: 'Inspect this turn' } })
      rerender(
        <MemoryRouter><Boundary resetKey="/evidence"><input aria-label="Session note" /></Boundary></MemoryRouter>,
      )
      expect(screen.getByLabelText('Session note')).toHaveValue('Inspect this turn')
    })
  }
})
