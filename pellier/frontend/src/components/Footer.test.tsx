/**
 * Footer tests — brand + three live columns + bottom strip.
 *
 * The previous footer spec (five columns, newsletter form, Privacy/
 * Terms/Accessibility bottom strip) was frozen around placeholder
 * links. This rewrite replaces it with a living spec:
 *
 *   - Four sections only: Brand, Explore, Storyboard, Atelier.
 *   - Every Explore link points at a real router route.
 *   - Storyboard + Atelier each carry an italic blurb and a single
 *     call-to-action link to `/storyboard` / `/atelier`.
 *   - Bottom strip shows the copyright line and a signature tag.
 *     No placeholder Privacy/Terms/Accessibility links.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import Footer from './Footer'
import { FOOTER } from '../copy'

function renderFooter() {
  return render(
    <MemoryRouter>
      <Footer />
    </MemoryRouter>,
  )
}

describe('Footer — four live columns', () => {
  it('renders exactly four column sections in order', () => {
    renderFooter()
    const container = screen.getByTestId('footer-columns')
    const regions = within(container).getAllByRole('region', { hidden: true })
    expect(regions).toHaveLength(4)
    expect(screen.getByTestId('footer-column-brand')).toBeInTheDocument()
    expect(screen.getByTestId('footer-column-explore')).toBeInTheDocument()
    expect(screen.getByTestId('footer-column-storyboard')).toBeInTheDocument()
    expect(screen.getByTestId('footer-column-atelier')).toBeInTheDocument()
  })

  it('renders the brand column with the tagline from copy.ts', () => {
    renderFooter()
    expect(screen.getByTestId('footer-brand-tagline')).toHaveTextContent(
      FOOTER.BRAND.TAGLINE,
    )
  })

  it('renders every Explore link pointing at a real route', () => {
    renderFooter()
    const explore = screen.getByTestId('footer-column-explore')
    FOOTER.EXPLORE.ITEMS.forEach(({ label, href }) => {
      const link = within(explore).getByText(label).closest('a')
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', href)
    })
  })

  it('renders Storyboard column with italic blurb + "Read the latest" CTA linking to /storyboard', () => {
    renderFooter()
    const col = screen.getByTestId('footer-column-storyboard')
    expect(within(col).getByText(FOOTER.STORYBOARD.COPY)).toBeInTheDocument()
    const cta = within(col).getByTestId('footer-column-storyboard-cta')
    expect(cta).toHaveAttribute('href', '/storyboard')
    expect(cta).toHaveTextContent(FOOTER.STORYBOARD.CTA_LABEL)
  })

  it('renders Atelier column with italic blurb + "Open the Atelier" CTA linking to /atelier', () => {
    renderFooter()
    const col = screen.getByTestId('footer-column-atelier')
    expect(within(col).getByText(FOOTER.ATELIER.COPY)).toBeInTheDocument()
    const cta = within(col).getByTestId('footer-column-atelier-cta')
    expect(cta).toHaveAttribute('href', '/atelier')
    expect(cta).toHaveTextContent(FOOTER.ATELIER.CTA_LABEL)
  })
})

describe('Footer — bottom strip', () => {
  it('renders the copyright line with the current year', () => {
    renderFooter()
    const strip = screen.getByTestId('footer-bottom-strip')
    const copyright = within(strip).getByTestId('footer-copyright')
    expect(copyright.textContent).toContain(FOOTER.BOTTOM_STRIP.COPYRIGHT)
    expect(copyright.textContent).toContain(String(new Date().getFullYear()))
  })

  it('does not render Privacy / Terms / Accessibility placeholder links', () => {
    renderFooter()
    const strip = screen.getByTestId('footer-bottom-strip')
    // Explicit negative assertion: the placeholder links the earlier
    // footer shipped with should not surface in the rewrite.
    expect(within(strip).queryByText('Privacy')).not.toBeInTheDocument()
    expect(within(strip).queryByText('Terms')).not.toBeInTheDocument()
    expect(within(strip).queryByText('Accessibility')).not.toBeInTheDocument()
  })
})
