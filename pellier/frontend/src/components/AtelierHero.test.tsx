/**
 * AtelierHero tests — editorial hero above the /workshop split.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import AtelierHero from './AtelierHero'

describe('AtelierHero', () => {
  it('renders the display title and italic epigraph', () => {
    render(<AtelierHero />)
    expect(screen.getByText(/^The Atelier\.$/)).toBeInTheDocument()
    expect(screen.getByText(/Where Agents think aloud/)).toBeInTheDocument()
  })

  it('renders the ATELIER · NO. 06 kicker by default', () => {
    render(<AtelierHero />)
    expect(screen.getByText(/ATELIER · NO\. 06/)).toBeInTheDocument()
  })

  it('respects editionNumber prop and zero-pads single digits', () => {
    render(<AtelierHero editionNumber={3} />)
    expect(screen.getByText(/ATELIER · NO\. 03/)).toBeInTheDocument()
  })
})
