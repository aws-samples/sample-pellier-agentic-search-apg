/**
 * SurfaceToggle tests — global Boutique ↔ Atelier segmented control.
 *
 * Covers:
 *   - Both segments render with the correct labels + testids.
 *   - The active segment reflects the current route (/ → storefront,
 *     /atelier → atelier, /atelier/x → atelier).
 *   - The inactive segment links to the other surface.
 *   - aria-current + data-active are only set on the active segment.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import SurfaceToggle from './SurfaceToggle'
import { SURFACE_TOGGLE } from '../copy'
import { TEST_ROUTER_FUTURE_FLAGS } from '../test-utils'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={TEST_ROUTER_FUTURE_FLAGS}>
      <SurfaceToggle />
    </MemoryRouter>,
  )
}

describe('SurfaceToggle — render', () => {
  it('renders both segments with the canonical copy', () => {
    renderAt('/')
    const storefront = screen.getByTestId('surface-toggle-storefront')
    const atelier = screen.getByTestId('surface-toggle-atelier')
    expect(storefront).toHaveTextContent(SURFACE_TOGGLE.STOREFRONT)
    expect(atelier).toHaveTextContent(SURFACE_TOGGLE.ATELIER)
  })

  it('wraps the group with an aria-label for assistive tech', () => {
    renderAt('/')
    const group = screen.getByTestId('surface-toggle')
    expect(group.getAttribute('aria-label')).toBe(SURFACE_TOGGLE.ARIA_LABEL)
    expect(group.getAttribute('role')).toBe('group')
  })
})

describe('SurfaceToggle — active state reflects route', () => {
  it('marks Boutique active on /', () => {
    renderAt('/')
    expect(
      screen.getByTestId('surface-toggle-storefront').getAttribute('data-active'),
    ).toBe('true')
    expect(
      screen.getByTestId('surface-toggle-storefront').getAttribute('aria-current'),
    ).toBe('page')
    expect(
      screen.getByTestId('surface-toggle-atelier').getAttribute('data-active'),
    ).toBe('false')
  })

  it('marks Atelier active on /atelier', () => {
    renderAt('/atelier')
    expect(
      screen.getByTestId('surface-toggle-atelier').getAttribute('data-active'),
    ).toBe('true')
    expect(
      screen.getByTestId('surface-toggle-storefront').getAttribute('data-active'),
    ).toBe('false')
  })

  it('treats /atelier subroutes as atelier', () => {
    renderAt('/atelier/something-deep')
    expect(
      screen.getByTestId('surface-toggle-atelier').getAttribute('data-active'),
    ).toBe('true')
  })
})

describe('SurfaceToggle — links to the correct target surface', () => {
  it('atelier segment links to /atelier', () => {
    renderAt('/')
    expect(
      screen.getByTestId('surface-toggle-atelier').getAttribute('href'),
    ).toBe('/atelier')
  })

  it('storefront segment links to /', () => {
    renderAt('/atelier')
    expect(
      screen.getByTestId('surface-toggle-storefront').getAttribute('href'),
    ).toBe('/')
  })
})
