import { fireEvent, render, screen } from '@testing-library/react'
import { Link, MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import SurfaceNavigation from './SurfaceNavigation'

function Probe() {
  const location = useLocation()
  const navigate = useNavigate()
  return <>
    <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>
    <Link to="/observatory/operator-turn?customer=CUST-THEO&session=s-3&turn=t-4">Inspect exact turn</Link>
    <button onClick={() => navigate(-1)}>Browser back</button>
  </>
}

describe('connected surface navigation', () => {
  it('returns to the exact review and exact evidence turn across surfaces', () => {
    render(<MemoryRouter initialEntries={['/operator/reviews/42#operator-review-decision']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter>)
    fireEvent.click(screen.getByRole('link', { name: 'Inspect exact turn' }))
    fireEvent.click(screen.getByRole('link', { name: 'Storefront' }))
    fireEvent.click(screen.getByRole('link', { name: 'Operator' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/operator/reviews/42#operator-review-decision')
    fireEvent.click(screen.getByRole('link', { name: 'Observatory' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/observatory/operator-turn?customer=CUST-THEO&session=s-3&turn=t-4')
    expect(screen.getByRole('link', { name: 'Observatory' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getAllByRole('link', { current: 'page' })).toHaveLength(1)
  })

  it('keeps a product location when browser history returns from another surface', () => {
    render(<MemoryRouter initialEntries={['/product/17']}>
      <SurfaceNavigation /><Probe />
    </MemoryRouter>)
    fireEvent.click(screen.getByRole('link', { name: 'Operator' }))
    fireEvent.click(screen.getByRole('button', { name: 'Browser back' }))
    expect(screen.getByRole('link', { name: 'Storefront' })).toHaveAttribute('href', '/product/17')
    expect(screen.getByRole('link', { name: 'Storefront' })).toHaveAttribute('aria-current', 'page')
  })
})
