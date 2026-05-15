/**
 * RefinementPanel tests — multi-select chip panel below the product grid.
 *
 * Validates Requirements 1.8.1, 1.8.2, and 1.8.3, plus the task-level
 * integration test: chip toggles should drive a grid re-fetch with the
 * correct AND-composed query string.
 *
 * Coverage:
 *   - Renders the prompt + the four chips in storefront-documented order
 *     (Req 1.8.1).
 *   - Chips compose with AND semantics — toggling multiple yields a set
 *     rather than a single-select (Req 1.8.3).
 *   - `onChange` fires with the full active set after each toggle, in
 *     declaration order (Req 1.8.2).
 *   - Integration: driving the panel + a parent harness with a mocked
 *     fetch exercises the task-level acceptance: chip toggles -> grid
 *     re-fetch with the AND-composed query params.
 */
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { useEffect, useState, type ReactElement } from 'react'

import RefinementPanel, { type RefinementChip } from './RefinementPanel'
import CategoryChips, { type CategoryLabel } from './CategoryChips'
import { REFINEMENT } from '../copy'
import { PersonaProvider } from '../contexts/PersonaContext'

// RefinementPanel now reads usePersona() for its prompt. Wrap every
// render in PersonaProvider — the provider's default is null (fresh),
// which maps back to the default prompt from copy.ts.
function render(ui: ReactElement) {
  return rtlRender(<PersonaProvider>{ui}</PersonaProvider>)
}

describe('RefinementPanel — static copy (Req 1.8.1)', () => {
  it('renders the "Pellier here" prompt and all four chips', () => {
    render(<RefinementPanel />)

    expect(screen.getByTestId('refinement-prompt')).toHaveTextContent(
      'Pellier here, want me to narrow this down?',
    )
    expect(screen.getByTestId('refinement-b-mark')).toHaveTextContent('P')

    const chips = screen.getAllByRole('button')
    expect(chips).toHaveLength(REFINEMENT.CHIPS.length)
    expect(chips.map(c => c.textContent)).toEqual([
      'Under $100',
      'Ships by Friday',
      'Gift-wrappable',
      'From smaller makers',
    ])
  })

  it('starts with no chip active', () => {
    render(<RefinementPanel />)
    for (const chip of screen.getAllByRole('button')) {
      expect(chip).toHaveAttribute('data-active', 'false')
    }
    // And the decorative hairline is absent until a chip is active.
    expect(
      screen.queryByTestId('refinement-active-hairline'),
    ).not.toBeInTheDocument()
  })
})

describe('RefinementPanel — AND-composed toggles (Req 1.8.3)', () => {
  it('toggling a second chip keeps the first active and emits both', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<RefinementPanel onChange={onChange} />)

    await user.click(screen.getByTestId('refinement-chip-under-dollar100'))
    expect(onChange).toHaveBeenLastCalledWith(['Under $100'])

    await user.click(screen.getByTestId('refinement-chip-ships-by-friday'))
    // Declaration order preserved: "Under $100" comes before
    // "Ships by Friday" in copy.ts.
    expect(onChange).toHaveBeenLastCalledWith([
      'Under $100',
      'Ships by Friday',
    ])

    expect(screen.getByTestId('refinement-chip-under-dollar100')).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(screen.getByTestId('refinement-chip-ships-by-friday')).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(
      screen.getByTestId('refinement-active-hairline'),
    ).toBeInTheDocument()
  })

  it('toggling an active chip removes it from the set', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<RefinementPanel onChange={onChange} />)

    await user.click(screen.getByTestId('refinement-chip-gift-wrappable'))
    await user.click(screen.getByTestId('refinement-chip-from-smaller-makers'))
    await user.click(screen.getByTestId('refinement-chip-gift-wrappable'))

    expect(onChange).toHaveBeenLastCalledWith(['From smaller makers'])
    expect(screen.getByTestId('refinement-chip-gift-wrappable')).toHaveAttribute(
      'data-active',
      'false',
    )
    expect(
      screen.getByTestId('refinement-chip-from-smaller-makers'),
    ).toHaveAttribute('data-active', 'true')
  })

  it('emits the set in copy.ts declaration order regardless of click order', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<RefinementPanel onChange={onChange} />)

    // Click last chip first, then first chip.
    await user.click(screen.getByTestId('refinement-chip-from-smaller-makers'))
    await user.click(screen.getByTestId('refinement-chip-under-dollar100'))

    expect(onChange).toHaveBeenLastCalledWith([
      'Under $100',
      'From smaller makers',
    ])
  })
})

describe('RefinementPanel — teaching caption', () => {
  it('does not render the teaching caption when no chip is active', () => {
    render(<RefinementPanel />)
    expect(
      screen.queryByTestId('refinement-teaching-caption'),
    ).not.toBeInTheDocument()
  })

  it('shows pgvector + metadata filter caption with the active chip count', async () => {
    const user = userEvent.setup()
    render(<RefinementPanel />)
    await user.click(screen.getByTestId('refinement-chip-under-dollar100'))
    const caption = screen.getByTestId('refinement-teaching-caption')
    expect(caption).toHaveTextContent(/pgvector/i)
    expect(caption).toHaveTextContent(/1 metadata filter/)
    expect(caption).toHaveTextContent(/~143ms/)

    await user.click(screen.getByTestId('refinement-chip-gift-wrappable'))
    expect(caption).toHaveTextContent(/2 metadata filters/)
  })
})

describe('RefinementPanel — controlled mode', () => {
  it('reflects the `activeFilters` prop and does not mutate internal state on click', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    const { rerender } = render(
      <RefinementPanel
        activeFilters={['Ships by Friday']}
        onChange={onChange}
      />,
    )
    expect(screen.getByTestId('refinement-chip-ships-by-friday')).toHaveAttribute(
      'data-active',
      'true',
    )

    await user.click(screen.getByTestId('refinement-chip-under-dollar100'))
    // Controlled: the parent hasn't rerendered, so visual state is unchanged.
    expect(screen.getByTestId('refinement-chip-under-dollar100')).toHaveAttribute(
      'data-active',
      'false',
    )
    expect(onChange).toHaveBeenLastCalledWith([
      'Under $100',
      'Ships by Friday',
    ])

    rerender(
      <PersonaProvider>
        <RefinementPanel
          activeFilters={['Under $100', 'Ships by Friday']}
          onChange={onChange}
        />
      </PersonaProvider>,
    )
    expect(screen.getByTestId('refinement-chip-under-dollar100')).toHaveAttribute(
      'data-active',
      'true',
    )
  })
})

// ---------------------------------------------------------------------------
// Integration: chip toggles -> grid re-fetch (task 4.5 "done when")
// ---------------------------------------------------------------------------

/**
 * A small parent harness that mimics what the home page will do in task
 * 4.6: own the category + refinement state, and re-fetch `/api/products`
 * every time either changes. The harness also increments a `renderKey`
 * whenever a refetch lands so we can assert that parallax-re-observation
 * happens on grid remount (the Req 1.8.2 + 1.6.6 intersection).
 */
function GridHarness({ fetchImpl }: { fetchImpl: typeof fetch }) {
  const [category, setCategory] = useState<CategoryLabel>('All')
  const [filters, setFilters] = useState<RefinementChip[]>([])
  const [renderKey, setRenderKey] = useState(0)

  useEffect(() => {
    const params = new URLSearchParams()
    if (category !== 'All') params.set('category', category)
    for (const f of filters) params.append('filter', f)
    const qs = params.toString()
    const url = qs ? `/api/products?${qs}` : '/api/products'

    let cancelled = false
    fetchImpl(url)
      .then(r => r.json())
      .then(() => {
        if (!cancelled) setRenderKey(k => k + 1)
      })
      .catch(() => {
        /* swallow for the test */
      })
    return () => {
      cancelled = true
    }
  }, [category, filters, fetchImpl])

  return (
    <div>
      <CategoryChips
        selected={category}
        onChange={next => setCategory(next)}
      />
      <div
        data-testid="grid"
        data-render-key={renderKey}
        key={renderKey}
      >
        grid-mount-{renderKey}
      </div>
      <RefinementPanel
        activeFilters={filters}
        onChange={next => setFilters(next)}
      />
    </div>
  )
}

describe('Integration — chip toggles drive a grid re-fetch', () => {
  it('sends AND-composed filter + category params on each toggle and remounts the grid', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ products: [] }),
    } as unknown as Response)

    const user = userEvent.setup()
    render(<GridHarness fetchImpl={fetchImpl as unknown as typeof fetch} />)

    // Initial mount triggers the first fetch (no params).
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/products'))

    // Click the Linen category.
    await user.click(screen.getByTestId('category-chip-linen'))
    await waitFor(() =>
      expect(fetchImpl).toHaveBeenCalledWith('/api/products?category=Linen'),
    )

    // Add an Under $100 refinement.
    await user.click(screen.getByTestId('refinement-chip-under-dollar100'))
    await waitFor(() =>
      expect(fetchImpl).toHaveBeenCalledWith(
        '/api/products?category=Linen&filter=Under+%24100',
      ),
    )

    // Add a Ships by Friday refinement (AND semantics, Req 1.8.3).
    await user.click(screen.getByTestId('refinement-chip-ships-by-friday'))
    await waitFor(() =>
      expect(fetchImpl).toHaveBeenCalledWith(
        '/api/products?category=Linen&filter=Under+%24100&filter=Ships+by+Friday',
      ),
    )

    // Grid remounted on each successful re-fetch so parallax re-observes
    // (Req 1.6.6). The render key must have incremented at least 3 times:
    // initial mount + category change + two refinement toggles.
    await waitFor(() => {
      const grid = screen.getByTestId('grid')
      expect(Number(grid.getAttribute('data-render-key'))).toBeGreaterThanOrEqual(
        3,
      )
    })
  })

  it('removes a filter when its chip is toggled off', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ products: [] }),
    } as unknown as Response)

    const user = userEvent.setup()
    render(<GridHarness fetchImpl={fetchImpl as unknown as typeof fetch} />)

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/products'))

    await user.click(screen.getByTestId('refinement-chip-gift-wrappable'))
    await waitFor(() =>
      expect(fetchImpl).toHaveBeenCalledWith(
        '/api/products?filter=Gift-wrappable',
      ),
    )

    await user.click(screen.getByTestId('refinement-chip-gift-wrappable'))
    await waitFor(() => {
      // Last call should be the empty-filter URL.
      const calls = (fetchImpl as unknown as { mock: { calls: string[][] } }).mock
        .calls
      const lastUrl = calls[calls.length - 1][0]
      expect(lastUrl).toBe('/api/products')
    })
  })
})
