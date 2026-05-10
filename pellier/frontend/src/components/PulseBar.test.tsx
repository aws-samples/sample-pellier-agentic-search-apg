/**
 * PulseBar tests — storefront ambient 4-metric strip.
 *
 * Covers:
 *   - Renders skeleton before fetch resolves.
 *   - Renders 4 metrics from the /api/storefront/pulse payload.
 *   - Source dot carries the correct aria-label per tag.
 *   - Dismiss button hides the bar for the session.
 *   - 2-col mobile → 4-col laptop grid via Tailwind class presence.
 */
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PulseBar from './PulseBar'

const METRICS_FIXTURE = {
  metrics: [
    {
      id: 'catalog',
      label: 'Catalog',
      primary: '92 products',
      secondary: '6 categories · browse ready',
      source: 'real' as const,
    },
    {
      id: 'agent_activity',
      label: 'Agent activity',
      primary: '— grounded picks',
      secondary: 'lights up once tool_audit writes land',
      source: 'stub' as const,
    },
    {
      id: 'your_picks',
      label: 'Your picks',
      primary: 'pre-vetted',
      secondary: 'tap the chat to see',
      source: 'stub' as const,
    },
    {
      id: 'cost',
      label: 'Cost today',
      primary: '$0.0012',
      secondary: '3 embedding calls · process-scoped',
      source: 'partial' as const,
    },
  ],
  generated_at: '2026-04-25T20:15:02',
}

function mockFetchOk(body: unknown) {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => body })
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('PulseBar — render', () => {
  it('shows skeleton cells before the pulse fetch resolves', () => {
    // Fetch never resolves so we stay in the loading state.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<PulseBar />)

    const skeletons = screen.getAllByTestId('pulse-metric-skeleton')
    expect(skeletons).toHaveLength(4)
  })

  it('renders the four metrics returned by /api/storefront/pulse', async () => {
    vi.stubGlobal('fetch', mockFetchOk(METRICS_FIXTURE))
    render(<PulseBar />)

    await waitFor(() =>
      expect(screen.getByTestId('pulse-metric-catalog')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('pulse-metric-agent_activity')).toBeInTheDocument()
    expect(screen.getByTestId('pulse-metric-your_picks')).toBeInTheDocument()
    expect(screen.getByTestId('pulse-metric-cost')).toBeInTheDocument()
    expect(screen.getByText('92 products')).toBeInTheDocument()
    expect(screen.getByText('$0.0012')).toBeInTheDocument()
  })

  it('labels each source dot honestly via aria-label', async () => {
    vi.stubGlobal('fetch', mockFetchOk(METRICS_FIXTURE))
    render(<PulseBar />)

    await waitFor(() =>
      expect(screen.getByTestId('pulse-metric-catalog-dot')).toBeInTheDocument(),
    )
    expect(
      screen.getByTestId('pulse-metric-catalog-dot').getAttribute('aria-label'),
    ).toMatch(/live data/i)
    expect(
      screen
        .getByTestId('pulse-metric-agent_activity-dot')
        .getAttribute('aria-label'),
    ).toMatch(/placeholder/i)
    expect(
      screen.getByTestId('pulse-metric-cost-dot').getAttribute('aria-label'),
    ).toMatch(/process restart/i)
  })

  it('uses a 2-col grid that expands to 4-col on laptop via tailwind classes', async () => {
    vi.stubGlobal('fetch', mockFetchOk(METRICS_FIXTURE))
    render(<PulseBar />)
    await waitFor(() =>
      expect(screen.getByTestId('pulse-metric-catalog')).toBeInTheDocument(),
    )
    const grid = screen.getByTestId('pulse-bar-grid')
    expect(grid.className).toContain('grid-cols-2')
    expect(grid.className).toContain('lg:grid-cols-4')
  })
})

describe('PulseBar — dismissal', () => {
  it('hides the pulse bar when dismiss is clicked', async () => {
    vi.useRealTimers() // userEvent interacts badly with fake timers
    vi.stubGlobal('fetch', mockFetchOk(METRICS_FIXTURE))
    const user = userEvent.setup()
    render(<PulseBar />)

    await waitFor(() =>
      expect(screen.getByTestId('pulse-metric-catalog')).toBeInTheDocument(),
    )
    await user.click(screen.getByTestId('pulse-bar-dismiss'))
    expect(screen.queryByTestId('pulse-bar')).not.toBeInTheDocument()
  })
})

describe('PulseBar — refresh interval', () => {
  it('polls /api/storefront/pulse every 30s while visible', async () => {
    const fetchSpy = mockFetchOk(METRICS_FIXTURE)
    vi.stubGlobal('fetch', fetchSpy)
    render(<PulseBar />)

    // First call fires immediately on mount.
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))

    // Advance 30s — second poll.
    await act(async () => {
      vi.advanceTimersByTime(30_000)
    })
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2))

    // Another 30s — third.
    await act(async () => {
      vi.advanceTimersByTime(30_000)
    })
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3))
  })
})
