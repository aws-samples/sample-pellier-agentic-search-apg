/**
 * ConciergeBriefing tests — concierge modal's shift-handover empty state.
 *
 * Covers:
 *   - Skeleton renders before fetch resolves.
 *   - Greeting + line + 3 action pills appear after fetch.
 *   - Action click fires onAction with the action id + label.
 *   - Product chip click fires onProductChip.
 *   - Stub chips render with their placeholder styling + title.
 *   - Network failure shows the degraded fallback copy.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ConciergeBriefing from './ConciergeBriefing'

const BRIEFING_FIXTURE = {
  greeting: 'Good evening, Shayon.',
  line: "I've been watching the boutique — 92 products across 6 categories. Today's standout: Ethiopia Guji Natural in Beans.",
  chips: [
    {
      label: '92',
      kind: 'stat' as const,
      meaning: 'products in catalog',
      source: 'real' as const,
    },
    {
      label: 'Ethiopia Guji Natural',
      kind: 'product' as const,
      product_id: 'PSPRT0044',
      source: 'real' as const,
    },
    {
      label: 'pre-vetted picks',
      kind: 'stat' as const,
      meaning: 'grounded by fact-check',
      source: 'stub' as const,
    },
  ],
  actions: [
    { id: 'show_picks', label: "Show me today's picks", primary: true },
    { id: 'whats_new', label: "What's new since my last visit" },
    { id: 'why_these', label: 'Why did the agent pick these?' },
  ],
  generated_at: '2026-04-25T20:15:02',
}

function mockFetchOk(body: unknown) {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => body })
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ConciergeBriefing — render', () => {
  it('renders a skeleton before the fetch resolves', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<ConciergeBriefing onAction={vi.fn()} />)
    expect(
      screen.getByTestId('concierge-briefing-skeleton'),
    ).toBeInTheDocument()
  })

  it('renders the greeting + line + 3 action pills', async () => {
    vi.stubGlobal('fetch', mockFetchOk(BRIEFING_FIXTURE))
    render(<ConciergeBriefing onAction={vi.fn()} />)

    await waitFor(() =>
      expect(
        screen.getByTestId('concierge-briefing-greeting'),
      ).toHaveTextContent('Good evening, Shayon.'),
    )
    expect(screen.getByTestId('concierge-briefing-line').textContent).toContain(
      'watching the boutique',
    )
    expect(screen.getByTestId('briefing-action-show_picks')).toBeInTheDocument()
    expect(screen.getByTestId('briefing-action-whats_new')).toBeInTheDocument()
    expect(screen.getByTestId('briefing-action-why_these')).toBeInTheDocument()
  })

  it('shows the stub chip in the fallback row so the scaffolding is honest', async () => {
    vi.stubGlobal('fetch', mockFetchOk(BRIEFING_FIXTURE))
    render(<ConciergeBriefing onAction={vi.fn()} />)

    await waitFor(() =>
      expect(
        screen.getByTestId('concierge-briefing-greeting'),
      ).toBeInTheDocument(),
    )
    // "pre-vetted picks" is in the stub chip row (it isn't in the line).
    expect(screen.getByText('pre-vetted picks')).toBeInTheDocument()
  })
})

describe('ConciergeBriefing — interactions', () => {
  it('fires onAction with the action id + label when clicked', async () => {
    vi.stubGlobal('fetch', mockFetchOk(BRIEFING_FIXTURE))
    const onAction = vi.fn()
    const user = userEvent.setup()
    render(<ConciergeBriefing onAction={onAction} />)

    await waitFor(() =>
      expect(
        screen.getByTestId('briefing-action-show_picks'),
      ).toBeInTheDocument(),
    )
    await user.click(screen.getByTestId('briefing-action-show_picks'))

    expect(onAction).toHaveBeenCalledWith('show_picks', "Show me today's picks")
  })

  it('fires onProductChip when a product chip is clicked', async () => {
    vi.stubGlobal('fetch', mockFetchOk(BRIEFING_FIXTURE))
    const onProductChip = vi.fn()
    const user = userEvent.setup()
    render(
      <ConciergeBriefing
        onAction={vi.fn()}
        onProductChip={onProductChip}
      />,
    )

    await waitFor(() =>
      expect(screen.getByTestId('briefing-chip-PSPRT0044')).toBeInTheDocument(),
    )
    await user.click(screen.getByTestId('briefing-chip-PSPRT0044'))
    expect(onProductChip).toHaveBeenCalledWith('PSPRT0044')
  })
})

describe('ConciergeBriefing — degraded state', () => {
  it('renders the warm fallback copy when the fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<ConciergeBriefing onAction={vi.fn()} />)

    await waitFor(() =>
      expect(
        screen.getByTestId('concierge-briefing-fallback'),
      ).toBeInTheDocument(),
    )
    expect(
      screen.getByText(/what are you looking for today/i),
    ).toBeInTheDocument()
  })
})
