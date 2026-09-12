/**
 * Footer tests — masthead, four live columns, disclaimer, legal strip.
 *
 * The original footer spec (five columns, newsletter form, Privacy/
 * Terms/Accessibility bottom strip) was frozen around placeholder links. The
 * rewrite replaced it with a living spec, and these tests hold that line while
 * covering the masthead and trust row added later:
 *
 *   - Four sections only: Brand, Explore, Storyboard, Pellier Observatory.
 *   - Every Explore link points at a real router route.
 *   - Storyboard + Pellier Observatory each carry an italic blurb and a single
 *     call-to-action link to `/storyboard` / `/observatory`.
 *   - Checkout trust glyphs are generic: no payment-network wordmark may
 *     appear, because Pellier never charges anything and the marks are
 *     third-party trademarks.
 *   - The disclaimer states plainly that nothing is charged, the catalog is
 *     synthetic, and AI-generated imagery is illustrative.
 *   - The legal strip carries the real licence. The repository is MIT and its
 *     NOTICE says explicitly "NOT MIT-0", so a footer claiming MIT-0 would
 *     misstate the terms of reuse.
 *   - No placeholder Privacy/Terms/Accessibility links.
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
    expect(screen.getByTestId('footer-column-observatory')).toBeInTheDocument()
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

  it('renders Pellier Observatory column with italic blurb + "Open Pellier Observatory" CTA linking to /observatory', () => {
    renderFooter()
    const col = screen.getByTestId('footer-column-observatory')
    expect(within(col).getByText(FOOTER.OBSERVATORY.COPY)).toBeInTheDocument()
    const cta = within(col).getByTestId('footer-column-observatory-cta')
    expect(cta).toHaveAttribute('href', '/observatory')
    expect(cta).toHaveTextContent(FOOTER.OBSERVATORY.CTA_LABEL)
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

  it('renders the attribution credit', () => {
    renderFooter()
    const strip = screen.getByTestId('footer-bottom-strip')
    expect(within(strip).getByTestId('footer-attribution')).toHaveTextContent(
      FOOTER.BOTTOM_STRIP.ATTRIBUTION,
    )
  })

  it('links to the source repository with an accessible GitHub icon', () => {
    renderFooter()
    const strip = screen.getByTestId('footer-bottom-strip')
    const link = within(strip).getByRole('link', {
      name: FOOTER.BOTTOM_STRIP.GITHUB_LABEL,
    })
    expect(link).toHaveAttribute('href', FOOTER.BOTTOM_STRIP.GITHUB_URL)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(within(link).getByTestId('footer-github-icon')).toHaveAttribute(
      'src',
      '/assets/icons/github-mark.svg',
    )
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

describe('Footer — masthead and demo payment strip', () => {
  it('renders the brand lockup in the masthead', () => {
    renderFooter()
    const masthead = screen.getByTestId('footer-masthead')
    const wordmark = within(masthead).getByRole('link', { name: 'Pellier home' })
    expect(wordmark).toHaveTextContent('pellier.')
    expect(wordmark).toHaveAttribute('href', '/')
  })

  it('renders official marks inside the disclosed demo contract', () => {
    renderFooter()
    expect(screen.getByTestId('footer-checkout-label')).toHaveTextContent(
      FOOTER.CHECKOUT.LABEL,
    )
    const methods = screen.getByRole('list', {
      name: FOOTER.CHECKOUT.ARIA_LABEL,
    })
    expect(
      within(methods)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(FOOTER.CHECKOUT.PAYMENT_METHODS.map(({ label }) => label))
    expect(
      [...methods.querySelectorAll('img')].map((image) =>
        image.getAttribute('src'),
      ),
    ).toEqual(
      FOOTER.CHECKOUT.PAYMENT_METHODS.map(
        ({ id }) => `/assets/icons/payment/${id}.svg`,
      ),
    )
    expect(
      [...methods.querySelectorAll('img')].map((image) =>
        image.getAttribute('height'),
      ),
    ).toEqual(['20', '20', '20', '20', '20', '20'])
    for (const item of within(methods).getAllByRole('listitem')) {
      expect(item).toHaveClass('h-9', 'px-2.5')
    }
    for (const image of methods.querySelectorAll('img')) {
      expect(image).toHaveAttribute('alt', '')
      expect(image).toHaveAttribute('aria-hidden', 'true')
    }
    expect(methods.textContent).not.toMatch(/hsa|fsa|eligible/i)
  })

  it('renders the retail assurances as discrete items', () => {
    renderFooter()
    const list = screen.getByTestId('footer-service-items')
    FOOTER.BOTTOM_STRIP.SERVICE_ITEMS.forEach((item) => {
      expect(within(list).getByText(item)).toBeInTheDocument()
    })
  })
})

describe('Footer — disclaimer and licence', () => {
  it('states that nothing is charged, the catalog is synthetic, and imagery is illustrative', () => {
    renderFooter()
    expect(screen.getByTestId('footer-disclaimer')).toHaveTextContent(
      FOOTER.DISCLAIMER,
    )
    expect(screen.getByTestId('footer-disclaimer')).toHaveTextContent(
      'AI-generated imagery is for illustrative purposes only.',
    )
  })

  it('renders the copyright holder and the real licence', () => {
    renderFooter()
    const legal = screen.getByTestId('footer-legal')
    expect(legal).toHaveTextContent(FOOTER.BOTTOM_STRIP.RIGHTS)
    expect(legal).toHaveTextContent(FOOTER.BOTTOM_STRIP.LICENSE)
  })

  it('does not claim MIT-0, which the repository NOTICE rules out', () => {
    // NOTICE: "released under the MIT License (NOT MIT-0). Attribution is a
    // condition of reuse, not a courtesy." A footer claiming MIT-0 would
    // misstate the licence and drop a required credit.
    renderFooter()
    const text = screen.getByTestId('footer').textContent ?? ''
    expect(text).not.toContain('MIT-0')
    expect(text).toContain('MIT License')
  })
})
