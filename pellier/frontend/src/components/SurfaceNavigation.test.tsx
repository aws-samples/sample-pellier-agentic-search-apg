import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { UIProvider } from '../contexts/UIContext'
import SurfaceNavigation from './SurfaceNavigation'
import { BUILDER_VIEW_KEY, SkillModeToggle, useBuilderView } from './turn'

function Probe() {
  const location = useLocation()
  const navigate = useNavigate()
  return <>
    <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>
    <button onClick={() => navigate(-1)}>Browser back</button>
  </>
}

describe('connected surface navigation', () => {
  it('returns to the exact review after visiting the storefront', () => {
    render(<UIProvider><MemoryRouter initialEntries={['/operator/reviews/42#operator-review-decision']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter></UIProvider>)
    fireEvent.click(screen.getByRole('link', { name: 'Storefront' }))
    fireEvent.click(screen.getByRole('link', { name: 'Operator' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/operator/reviews/42#operator-review-decision')
    expect(screen.getByRole('link', { name: 'Operator' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getAllByRole('link', { current: 'page' })).toHaveLength(1)
  })

  it('keeps a product location when browser history returns from another surface', () => {
    render(<UIProvider><MemoryRouter initialEntries={['/product/17']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter></UIProvider>)
    fireEvent.click(screen.getByRole('link', { name: 'Operator' }))
    fireEvent.click(screen.getByRole('button', { name: 'Browser back' }))
    expect(screen.getByRole('link', { name: 'Storefront' })).toHaveAttribute('href', '/product/17')
    expect(screen.getByRole('link', { name: 'Storefront' })).toHaveAttribute('aria-current', 'page')
  })
})

describe('the global Builder view switch', () => {
  function Reader() {
    const [on] = useBuilderView()
    return <output data-testid="builder-reader">{on ? 'on' : 'off'}</output>
  }

  it('lives in the header, starts off, and moves every reader together', () => {
    localStorage.removeItem(BUILDER_VIEW_KEY)
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation /><Reader /><SkillModeToggle />
    </MemoryRouter></UIProvider>)
    const toggle = screen.getByRole('switch', { name: 'Builder view' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByTestId('builder-reader')).toHaveTextContent('off')
    // The skills switch belongs to the dock and shows only with Builder view on.
    expect(screen.queryByRole('switch', { name: 'Agent loads its skills' })).toBeNull()

    act(() => toggle.click())
    expect(screen.getByRole('switch', { name: 'Builder view' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('builder-reader')).toHaveTextContent('on')
    expect(localStorage.getItem(BUILDER_VIEW_KEY)).toBe('on')
    expect(screen.getByRole('switch', { name: 'Agent loads its skills' })).toBeInTheDocument()
    act(() => screen.getByRole('switch', { name: 'Builder view' }).click())
    expect(localStorage.getItem(BUILDER_VIEW_KEY)).toBe('off')
  })

  it('shows on the Operator too, and not on sign-in', () => {
    const operator = render(<UIProvider><MemoryRouter initialEntries={['/operator']}>
      <SurfaceNavigation />
    </MemoryRouter></UIProvider>)
    expect(screen.getByRole('switch', { name: 'Builder view' })).toBeInTheDocument()
    operator.unmount()
    render(<UIProvider><MemoryRouter initialEntries={['/signin']}>
      <SurfaceNavigation />
    </MemoryRouter></UIProvider>)
    expect(screen.queryByRole('switch', { name: 'Builder view' })).toBeNull()
  })
})
