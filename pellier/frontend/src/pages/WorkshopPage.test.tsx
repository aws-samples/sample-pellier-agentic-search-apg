/**
 * WorkshopPage tests — /atelier ("The Atelier") coverage.
 *
 * Post–Phase 5 rewrite: the old dashboards (MemoryDashboard,
 * GatewayToolsPanel, RuntimeStatusPanel) are gone. Every architecture
 * card with a detail page now opens one of the atelier-arch/* pages
 * via the ArchDetailWrapper slot. These tests lock down:
 *
 *   1. Chrome renders the Atelier title + subtitle.
 *   2. Seven architecture cards render in the locked chapter order.
 *   3. Six of them open their arch-* detail page inline (not modal).
 *   4. Grounding stays "in progress" (no detail page yet).
 *   5. Responsive breakpoints select the right layout variant.
 *   6. Tab default + persistence behavior.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { TEST_ROUTER_FUTURE_FLAGS } from '../test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// --- Mocks -----------------------------------------------------------

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    accessToken: null,
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
    preferences: null,
    prefsVersion: 0,
  }),
}))

// Stub the heavy child components so the test focuses on layout
// chrome, not their internal render paths. WorkshopChat kicks off a
// fetch to /api/atelier/status which we don't want here.
vi.mock('../components/WorkshopChat', () => ({
  default: () => <div data-testid="stub-workshop-chat">chat</div>,
}))
vi.mock('../components/WorkshopTelemetry', () => ({
  default: () => <div data-testid="stub-workshop-telemetry">telemetry</div>,
}))
vi.mock('../components/PgvectorBenchSections', () => ({
  HnswBenchmarkSection: () => <div data-testid="stub-hnsw-bench">hnsw bench</div>,
  QuantizationSection: () => <div data-testid="stub-quantization">quantization</div>,
  IterativeScanSection: () => <div data-testid="stub-iterative-scan">iterative scan</div>,
}))

// Stub each atelier-arch page so the test asserts routing without
// pulling the full page body (and its shared-catalog fetch, etc.).
vi.mock('../components/atelier-arch/MemoryArchPage', () => ({
  default: () => <div data-testid="stub-arch-memory">memory arch</div>,
}))
vi.mock('../components/atelier-arch/McpArchPage', () => ({
  default: () => <div data-testid="stub-arch-mcp">mcp arch</div>,
}))
vi.mock('../components/atelier-arch/ToolRegistryArchPage', () => ({
  default: () => <div data-testid="stub-arch-tool-registry">tool registry arch</div>,
}))
vi.mock('../components/atelier-arch/RuntimeArchPage', () => ({
  default: () => <div data-testid="stub-arch-runtime">runtime arch</div>,
}))
vi.mock('../components/atelier-arch/StateManagementArchPage', () => ({
  default: () => <div data-testid="stub-arch-state">state arch</div>,
}))
vi.mock('../components/atelier-arch/EvaluationsArchPage', () => ({
  default: () => <div data-testid="stub-arch-evaluations">evaluations arch</div>,
}))
vi.mock('../components/atelier-arch/GroundingArchPage', () => ({
  default: () => <div data-testid="stub-arch-grounding">grounding arch</div>,
}))
vi.mock('../components/SkillsPanel', () => ({
  default: () => <div data-testid="stub-skills-panel">skills</div>,
}))

vi.mock('../components/Footer', () => ({
  default: () => <div data-testid="stub-footer">footer</div>,
}))
vi.mock('../components/Header', () => ({
  default: () => <div data-testid="stub-header">header</div>,
}))
vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({ openModal: vi.fn(), setChatSurface: vi.fn() }),
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: null,
    switchPersona: vi.fn(),
    signOut: vi.fn(),
    switching: false,
  }),
}))

// matchMedia is jsdom-missing by default. We control it per-test so we
// can drive the three responsive bands deterministically.
type MatchFactory = (query: string) => boolean

function installMatchMedia(matches: MatchFactory) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: matches(query),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  })
}

import WorkshopPage from './WorkshopPage'

function renderPage(opts: { startTab?: 'telemetry' | 'architecture' | 'performance' } = {}) {
  // The Atelier now defaults to the telemetry tab. Tests that care
  // about architecture content need to seed localStorage so the
  // architecture tab is already selected on first paint. Omit the
  // option to exercise the new default.
  const startTab = opts.startTab
  if (startTab) {
    try {
      localStorage.setItem('pellier-atelier-tab', startTab)
    } catch {
      // jsdom quirks — fall through.
    }
  }
  return render(
    <MemoryRouter initialEntries={['/atelier']} future={TEST_ROUTER_FUTURE_FLAGS}>
      <WorkshopPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  // Default to laptop viewport — three-zone layout.
  installMatchMedia((q) => q.includes('min-width: 1280px'))
})

afterEach(() => {
  vi.restoreAllMocks()
})

// --- Tests ------------------------------------------------------------

describe('WorkshopPage — chrome', () => {
  it('renders the AtelierHero with the italic display title + epigraph', () => {
    renderPage()
    expect(screen.getByText(/^The Atelier\.$/)).toBeInTheDocument()
    expect(
      screen.getByText(/Where Agents think aloud/i),
    ).toBeInTheDocument()
  })

  it('renders the hero zone (hero + atmosphere strip + metrics row)', () => {
    renderPage()
    expect(screen.getByTestId('atelier-header-zone')).toBeInTheDocument()
    expect(screen.getByTestId('atelier-hero')).toBeInTheDocument()
    expect(screen.getByTestId('atmosphere-strip')).toBeInTheDocument()
    expect(screen.getByTestId('metrics-row')).toBeInTheDocument()
  })

  it('no longer renders the DAT406 kicker, old subtitle, or back-to-storefront pill', () => {
    renderPage()
    expect(screen.queryByTestId('back-to-storefront')).not.toBeInTheDocument()
    expect(screen.queryByText(/DAT406/)).not.toBeInTheDocument()
    expect(
      screen.queryByText(/Workshop · agentic telemetry/),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/^Where Pellier works\./)).not.toBeInTheDocument()
  })
})

describe('WorkshopPage — architecture cards render', () => {
  // Architecture tab is no longer the default — seed the stored
  // preference so the cards render on first paint.
  beforeEach(() => {
    try { localStorage.setItem('pellier-atelier-tab', 'architecture') } catch { /* noop */ }
  })

  it('renders 8 cards covering the seven chapters plus Grounding', () => {
    renderPage()
    const ids = [
      'memory',
      'skills',
      'mcp',
      'state',
      'tool-registry',
      'runtime',
      'evaluations',
      'grounding',
    ]
    for (const id of ids) {
      expect(screen.getByTestId(`arch-card-${id}`)).toBeInTheDocument()
    }
  })

  it('renders an action CTA on every card (all 8 chapters wired)', () => {
    renderPage()
    // All eight architecture cards open a detail page.
    expect(screen.getByTestId('arch-card-open-memory')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-skills')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-mcp')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-state')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-tool-registry')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-runtime')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-evaluations')).toBeInTheDocument()
    expect(screen.getByTestId('arch-card-open-grounding')).toBeInTheDocument()
  })

  it('no longer renders an in-progress pill on Grounding — its arch page ships', () => {
    renderPage()
    expect(
      screen.queryByTestId('arch-card-inprogress-grounding'),
    ).not.toBeInTheDocument()
  })

  it('MCP body copy resolves the protocol-vs-primitive distinction', () => {
    renderPage()
    const mcp = screen.getByTestId('arch-card-mcp')
    expect(mcp.textContent).toContain('open standard')
    expect(mcp.textContent).toContain('managed MCP server')
  })

  it('Evaluations body copy describes AgentCore Evaluations', () => {
    renderPage()
    const evals = screen.getByTestId('arch-card-evaluations')
    expect(evals.textContent).toContain('AgentCore Evaluations')
    expect(evals.textContent).toContain('LLM-as-a-Judge')
  })
})

describe('WorkshopPage — architecture cards open their arch-* detail page inline', () => {
  beforeEach(() => {
    try { localStorage.setItem('pellier-atelier-tab', 'architecture') } catch { /* noop */ }
  })

  const routes: Array<[string, string]> = [
    ['arch-card-open-memory', 'stub-arch-memory'],
    ['arch-card-open-mcp', 'stub-arch-mcp'],
    ['arch-card-open-tool-registry', 'stub-arch-tool-registry'],
    ['arch-card-open-runtime', 'stub-arch-runtime'],
    ['arch-card-open-state', 'stub-arch-state'],
    ['arch-card-open-evaluations', 'stub-arch-evaluations'],
    ['arch-card-open-grounding', 'stub-arch-grounding'],
  ]

  it.each(routes)('%s opens %s inline', async (cta, panel) => {
    const user = userEvent.setup()
    renderPage()

    expect(screen.queryByTestId('detail-panel-slot')).not.toBeInTheDocument()

    await user.click(screen.getByTestId(cta))

    await waitFor(() =>
      expect(screen.getByTestId(panel)).toBeInTheDocument(),
    )
    expect(screen.getByTestId('detail-panel-slot')).toBeInTheDocument()
  })

  it('swaps panels when a second card is clicked', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByTestId('arch-card-open-memory'))
    await waitFor(() => screen.getByTestId('stub-arch-memory'))

    await user.click(screen.getByTestId('arch-card-open-tool-registry'))
    await waitFor(() => {
      expect(screen.getByTestId('stub-arch-tool-registry')).toBeInTheDocument()
      expect(screen.queryByTestId('stub-arch-memory')).not.toBeInTheDocument()
    })
  })
})

describe('WorkshopPage — responsive breakpoints', () => {
  // Layout tests that inspect the detail panel need to land on the
  // architecture tab where the panel lives.
  beforeEach(() => {
    try { localStorage.setItem('pellier-atelier-tab', 'architecture') } catch { /* noop */ }
  })

  it('selects "three-zone" layout on ≥ 1280px viewports', () => {
    installMatchMedia((q) => q.includes('min-width: 1280px'))
    renderPage()
    const main = screen.getByTestId('workshop-main')
    expect(main.getAttribute('data-layout')).toBe('three-zone')
  })

  it('selects "tablet-overlay" layout on 1024-1280 viewports', () => {
    installMatchMedia((q) => q.includes('1024px) and (max-width: 1279.98px'))
    renderPage()
    const main = screen.getByTestId('workshop-main')
    expect(main.getAttribute('data-layout')).toBe('tablet-overlay')
  })

  it('selects "vertical-stack" layout on < 1024px viewports', () => {
    installMatchMedia(() => false)
    renderPage()
    const main = screen.getByTestId('workshop-main')
    expect(main.getAttribute('data-layout')).toBe('vertical-stack')
  })

  it('on vertical-stack, the detail panel renders as a stacked block', async () => {
    installMatchMedia(() => false)
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByTestId('arch-card-open-memory'))
    await waitFor(() =>
      expect(screen.getByTestId('detail-panel-stacked')).toBeInTheDocument(),
    )
  })

  it('on tablet-overlay, the detail panel renders as a docked overlay', async () => {
    installMatchMedia((q) => q.includes('1024px) and (max-width: 1279.98px'))
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByTestId('arch-card-open-memory'))
    await waitFor(() =>
      expect(screen.getByTestId('detail-panel-tablet-overlay')).toBeInTheDocument(),
    )
  })
})

describe('WorkshopPage — tab default + persistence', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaults to the Telemetry tab on first load (no stored preference)', () => {
    renderPage()
    expect(
      screen.getByTestId('workshop-tab-telemetry').getAttribute('aria-selected'),
    ).toBe('true')
    expect(
      screen.getByTestId('workshop-tab-architecture').getAttribute('aria-selected'),
    ).toBe('false')
  })

  it('renders tabs in the order Telemetry → Architecture → Patterns → Performance', () => {
    renderPage()
    const tabs = [
      screen.getByTestId('workshop-tab-telemetry'),
      screen.getByTestId('workshop-tab-architecture'),
      screen.getByTestId('workshop-tab-patterns'),
      screen.getByTestId('workshop-tab-performance'),
    ]
    const parent = tabs[0].parentElement!
    expect(parent.children[0]).toBe(tabs[0])
    expect(parent.children[1]).toBe(tabs[1])
    expect(parent.children[2]).toBe(tabs[2])
    expect(parent.children[3]).toBe(tabs[3])
  })

  it("persists the user's explicit tab choice to localStorage", async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByTestId('workshop-tab-performance'))
    expect(localStorage.getItem('pellier-atelier-tab')).toBe('performance')
  })

  it('opens to the stored tab choice on a subsequent render', () => {
    localStorage.setItem('pellier-atelier-tab', 'performance')
    renderPage()
    expect(
      screen.getByTestId('workshop-tab-performance').getAttribute('aria-selected'),
    ).toBe('true')
  })
})
