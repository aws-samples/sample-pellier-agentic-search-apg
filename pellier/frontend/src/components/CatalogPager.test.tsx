import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import CatalogPager from './CatalogPager'

describe('large catalog navigation', () => {
  it.each([1, 2083, 4167])('bounds controls and preserves navigation on page %i', page => {
    const onNavigate = vi.fn()
    render(<MemoryRouter initialEntries={['/?persona=anna']}>
      <CatalogPager page={page} pages={4167} onNavigate={onNavigate} />
    </MemoryRouter>)
    const pager = within(screen.getByRole('navigation'))
    const links = pager.getAllByTestId('home-pager-page')
    expect(links.length).toBeLessThanOrEqual(7)
    expect(pager.getByRole('link', { name: `Page ${page}` })).toHaveAttribute('aria-current', 'page')
    expect(pager.getByRole('link', { name: 'Page 1' })).toHaveAttribute('href', '/?persona=anna')
    const last = pager.getByRole('link', { name: 'Page 4167' })
    expect(last).toHaveAttribute('href', '/?persona=anna&page=4167')
    fireEvent.click(last)
    expect(onNavigate).toHaveBeenCalledWith(4167)
    expect(pager.getByTestId('home-pager-status')).toHaveTextContent(`Page ${page} of 4167`)
  })

  it('shows a lone skipped page instead of an ellipsis that hides only it', () => {
    render(<MemoryRouter initialEntries={['/?page=5']}>
      <CatalogPager page={5} pages={84} onNavigate={vi.fn()} />
    </MemoryRouter>)
    const pager = within(screen.getByRole('navigation'))
    expect(pager.getAllByTestId('home-pager-page').map(link => link.textContent))
      .toEqual(['1', '2', '3', '4', '5', '6', '7', '84'])
    expect(screen.getAllByText('…')).toHaveLength(1)
  })
})
