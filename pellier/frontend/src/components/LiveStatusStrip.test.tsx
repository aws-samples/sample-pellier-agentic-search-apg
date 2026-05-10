/**
 * LiveStatusStrip tests — reassuring status line above the category
 * chips.
 *
 * The previous version fetched /api/inventory and rendered an amber
 * "Catalog refreshing…" warning when stale=true. That warning showed
 * up too often in demo envs and distracted from the boutique voice,
 * so it was removed along with the network round-trip. The test spec
 * is rewritten here as a living contract around what the component
 * does now — render three pieces of static copy — and an explicit
 * negative assertion that the stale-warning element is gone.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import LiveStatusStrip from './LiveStatusStrip'

describe('LiveStatusStrip — static copy', () => {
  it('renders the LIVE_STATUS line and the three right-side links', () => {
    render(<LiveStatusStrip />)
    expect(screen.getByTestId('live-status-copy')).toHaveTextContent(
      /Live inventory/,
    )
    expect(screen.getByTestId('live-status-copy')).toHaveTextContent(
      /refreshed daily/,
    )
    expect(screen.getByTestId('live-status-copy')).toHaveTextContent(
      /curated by hand/,
    )
    expect(screen.getByTestId('live-status-shipping')).toHaveTextContent(
      /Free shipping over \$150/,
    )
    expect(screen.getByTestId('live-status-returns')).toHaveTextContent(
      /Ships within 1 to 2 days/,
    )
    expect(screen.getByTestId('live-status-secure')).toHaveTextContent(
      'Secure checkout',
    )
  })

  it('no longer renders the "Catalog refreshing…" stale warning', () => {
    render(<LiveStatusStrip />)
    // Negative assertion — the stale-warning element was removed
    // when the /api/inventory polling was retired.
    expect(
      screen.queryByTestId('live-status-stale-warning'),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/Catalog refreshing/)).not.toBeInTheDocument()
  })
})
