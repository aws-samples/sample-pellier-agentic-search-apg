import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../../contexts/PersonaContext', () => ({
  usePersona: () => ({ persona: null }),
}))

vi.mock('../../shared', () => ({
  PresencePill: () => null,
}))

import TopBar from './TopBar'
import SurfaceNavigation from '../../components/SurfaceNavigation'

function LocationProbe() {
  const { pathname } = useLocation()
  return <output data-testid="location">{pathname}</output>
}

describe('Pellier Observatory TopBar', () => {
  it.each([
    ['/observatory/', 'Lab Collection'],
    ['/observatory/labs/grounded-inventory', 'Lab Collection'],
    ['/observatory/workbench', 'Workbench'],
    ['/observatory/proof-board', 'Workbench'],
    ['/observatory/govern', 'Govern'],
    ['/observatory/govern/policies', 'Govern'],
    ['/observatory/write-path', 'Govern'],
  ])('marks exactly one destination current at %s', (route, label) => {
    render(<MemoryRouter initialEntries={[route]}><TopBar /></MemoryRouter>)
    const current = screen.getAllByRole('link', { current: 'page' })
    expect(current).toHaveLength(1)
    expect(current[0]).toHaveAccessibleName(label)
  })

  it('uses the shared navigation for all three surface destinations', () => {
    render(
      <MemoryRouter initialEntries={['/observatory/proof-board']}>
        <SurfaceNavigation />
        <TopBar />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Storefront' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Operator' })).toHaveAttribute('href', '/operator/reviews')
    expect(screen.getByRole('link', { name: 'Observatory' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: 'Back to Pellier' })).not.toBeInTheDocument()
  })

  it('keeps supporting routes inside the one Observatory workspace', () => {
    render(
      <MemoryRouter initialEntries={['/observatory/proof-board']}>
        <TopBar />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('link', { name: 'Workbench' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(
      screen.queryByRole('link', { name: 'Proof & References' }),
    ).not.toBeInTheDocument()
  })

  it('distinguishes the collection from the workbench', () => {
    render(
      <MemoryRouter initialEntries={['/observatory']}>
        <TopBar />
        <LocationProbe />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Pellier Observatory' })).toHaveAttribute(
      'href',
      '/observatory',
    )
    expect(screen.queryByRole('button', { name: /Pellier Observatory view/i })).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Lab Collection' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Workbench' })).not.toHaveAttribute('aria-current');
    expect(
      screen.queryByRole('link', { name: 'Proof & References' }),
    ).not.toBeInTheDocument()
  })

  it('keeps collection, detail, and live routes in one workbench tab', () => {
    render(
      <MemoryRouter
        initialEntries={['/observatory/workbench?lab=fail-closed-policy']}
      >
        <TopBar />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('link', { name: 'Workbench' }),
    ).toHaveAttribute('aria-current', 'page')
  })

  it('keeps persona selection in the scenario-card flow, not the Observatory header', () => {
    render(
      <MemoryRouter initialEntries={['/observatory/workbench']}>
        <TopBar />
      </MemoryRouter>,
    )

    expect(
      screen.queryByRole('button', { name: /switch persona/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('observatory-persona-switcher'),
    ).not.toBeInTheDocument()
  })
})
