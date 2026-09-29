import { afterEach, describe, expect, it } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

import LabJourneyBar from './LabJourneyBar'
import SurfaceNavigation from './SurfaceNavigation'
import { LAB_JOURNEYS, openLabJourney, readLabJourney, setLabJourneyStep } from '../shared/labJourney'

afterEach(() => localStorage.clear())

function Where() {
  const { pathname } = useLocation()
  return <output data-testid="where">{pathname}</output>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SurfaceNavigation />
      <LabJourneyBar />
      <Where />
    </MemoryRouter>,
  )
}

describe('LabJourneyBar', () => {
  it('stays out of the way until a lab is open, leaving a way in', () => {
    renderAt('/')
    expect(screen.queryByTestId('lab-journey')).not.toBeInTheDocument()
    expect(screen.getByTestId('surface-labs-link')).toHaveAttribute('href', '/observatory')
  })

  it('shows the lab, every step, and marks the current one', () => {
    openLabJourney('fail-closed-policy')
    setLabJourneyStep('fail-closed-policy', 5)
    renderAt('/observatory/workbench')
    const guide = screen.getByRole('navigation', { name: 'Lab 4 guide' })
    const steps = within(guide).getAllByRole('listitem').filter(item => item.closest('.pellier-journey-steps'))
    expect(steps).toHaveLength(LAB_JOURNEYS['fail-closed-policy'].length)
    expect(steps.map(step => step.dataset.state)).toEqual(['visited', 'visited', 'visited', 'visited', 'visited', 'current', 'upcoming', 'upcoming'])
    expect(within(steps[5]).getByRole('button')).toHaveAttribute('aria-current', 'step')
    expect(screen.queryByTestId('surface-labs-link')).not.toBeInTheDocument()
  })

  it('sends you to the step’s surface when you are elsewhere', () => {
    openLabJourney('fail-closed-policy')
    setLabJourneyStep('fail-closed-policy', 5)
    renderAt('/observatory/workbench')
    const open = screen.getByRole('link', { name: 'Open in Operator' })
    expect(open).toHaveAttribute('href', '/operator/clients/CUST-JESSICA#operator-concierge')
  })

  it('offers the next step once you are where this one happens', () => {
    openLabJourney('grounded-inventory')
    renderAt('/product/2')
    fireEvent.click(screen.getByRole('button', { name: 'Next: Inventory contract' }))
    expect(readLabJourney().steps['grounded-inventory']).toBe(1)
    // A Code Editor step has no page, so the bar moves on rather than linking.
    expect(screen.getByRole('button', { name: 'Next: Wire the agent' })).toBeInTheDocument()
  })

  it('lists the lab’s Observatory views and switches labs from its menu', () => {
    openLabJourney('managed-agent-path')
    renderAt('/observatory/workbench')
    const views = screen.getByRole('region', { name: 'Lab 3 views' })
    expect(within(views).getAllByRole('link').map(link => link.textContent)).toEqual(['Workbench', 'Tool Registry', 'Memory'])
    fireEvent.click(screen.getByRole('link', { name: 'Lab 1 Marco: Build a PostgreSQL-Grounded Agent' }))
    expect(readLabJourney().lab).toBe('grounded-inventory')
    expect(screen.getByTestId('where')).toHaveTextContent('/observatory/workbench')
  })

  it('can be hidden, and the Labs link returns', () => {
    openLabJourney('retrieval-acceptance')
    renderAt('/')
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Hide the lab guide' })) })
    expect(screen.queryByTestId('lab-journey')).not.toBeInTheDocument()
    expect(screen.getByTestId('surface-labs-link')).toBeInTheDocument()
  })

  it('never renders on the sign-in page', () => {
    openLabJourney('grounded-inventory')
    renderAt('/signin')
    expect(screen.queryByTestId('lab-journey')).not.toBeInTheDocument()
  })
})
