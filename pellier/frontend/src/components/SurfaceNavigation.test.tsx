import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
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

  it('lives in the header, starts on, and moves every reader together', () => {
    localStorage.removeItem(BUILDER_VIEW_KEY)
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation /><Reader /><SkillModeToggle />
    </MemoryRouter></UIProvider>)
    const toggle = screen.getByRole('switch', { name: 'Builder view' })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('builder-reader')).toHaveTextContent('on')
    // The skills switch belongs to the dock and shows only with Builder view on.
    expect(screen.getByRole('switch', { name: 'Agent loads its skills' })).toBeInTheDocument()

    act(() => toggle.click())
    expect(screen.getByRole('switch', { name: 'Builder view' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByTestId('builder-reader')).toHaveTextContent('off')
    expect(localStorage.getItem(BUILDER_VIEW_KEY)).toBe('off')
    expect(screen.queryByRole('switch', { name: 'Agent loads its skills' })).toBeNull()
    act(() => screen.getByRole('switch', { name: 'Builder view' }).click())
    expect(localStorage.getItem(BUILDER_VIEW_KEY)).toBe('on')
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

describe('the header landmark and accessible names', () => {
  it('holds every switch inside a labelled region, with the Builder switch named', () => {
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation />
    </MemoryRouter></UIProvider>)
    const region = screen.getByRole('region', { name: 'Pellier controls' })
    expect(region).toContainElement(screen.getByRole('switch', { name: 'Builder view' }))
    expect(region).toContainElement(screen.getByTestId('theme-control'))
    expect(region).toContainElement(screen.getByRole('link', { name: 'Operator' }))
    expect(region).toContainElement(screen.getByTestId('header-ask-pellier'))
    expect(screen.queryByTestId('surface-menu-button')).toBeNull()
  })
})

describe('the header on a phone', () => {
  function phone(matches: boolean) {
    vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
      matches: matches && query.includes('max-width: 560px'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  }
  afterEach(() => vi.restoreAllMocks())

  it('folds the surface switch, Builder view and theme into a menu beside Ask Pellier', () => {
    phone(true)
    localStorage.removeItem(BUILDER_VIEW_KEY)
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation />
    </MemoryRouter></UIProvider>)
    const button = screen.getByRole('button', { name: 'Open menu' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByTestId('header-ask-pellier')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Operator' })).toBeNull()
    expect(screen.queryByRole('switch', { name: 'Builder view' })).toBeNull()
    expect(screen.queryByTestId('theme-control')).toBeNull()

    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'Close menu' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('link', { name: 'Operator' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Builder view' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('theme-control')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveFocus()
    expect(screen.queryByRole('link', { name: 'Operator' })).toBeNull()
  })

  it('holds the storefront links on the Storefront, so a phone has one menu', () => {
    phone(true)
    render(<UIProvider><MemoryRouter initialEntries={['/about']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter></UIProvider>)
    expect(screen.queryByRole('navigation', { name: 'Storefront' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
    const links = within(screen.getByRole('navigation', { name: 'Storefront' })).getAllByRole('link')
    expect(links.map(link => link.textContent)).toEqual(['Shop', 'Stories', 'About'])
    expect(links[2]).toHaveAttribute('aria-current', 'page')
    fireEvent.click(links[0])
    expect(screen.getByTestId('location').textContent).toBe('/#shop')
    expect(screen.queryByRole('navigation', { name: 'Storefront' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open menu' })).toBeInTheDocument()
  })

  it('closes the menu when Shop scrolls the same page to the collection', () => {
    phone(true)
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter></UIProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Storefront' })).getByRole('link', { name: 'Shop' }))
    expect(screen.getByTestId('location').textContent).toBe('/#shop')
    expect(screen.queryByRole('navigation', { name: 'Storefront' })).toBeNull()
  })

  it('leaves the storefront links out on the Operator and on a wider screen', () => {
    phone(true)
    const { unmount } = render(<UIProvider><MemoryRouter initialEntries={['/operator/reviews']}>
      <SurfaceNavigation />
    </MemoryRouter></UIProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
    expect(screen.queryByRole('navigation', { name: 'Storefront' })).toBeNull()
    unmount()

    phone(false)
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation />
    </MemoryRouter></UIProvider>)
    expect(screen.queryByRole('navigation', { name: 'Storefront' })).toBeNull()
  })

  it('closes the menu once a surface is chosen', () => {
    phone(true)
    render(<UIProvider><MemoryRouter initialEntries={['/']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter></UIProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
    fireEvent.click(screen.getByRole('link', { name: 'Operator' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/operator/reviews')
    expect(screen.getByRole('button', { name: 'Open menu' })).toBeInTheDocument()
  })
})
