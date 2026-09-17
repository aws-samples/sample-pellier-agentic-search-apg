import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  sendChatMessageStreaming: vi.fn(),
  fetch: vi.fn(),
  switchPersona: vi.fn(),
  persona: null as null | {
    id: string;
    display_name: string;
    customer_id: string;
  },
}));

vi.mock('../../../services/chat', () => ({
  sendChatMessageStreaming: mocks.sendChatMessageStreaming,
}));

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: mocks.persona,
    switchPersona: mocks.switchPersona,
    switching: false,
    switchError: null,
  }),
}));

import { PERSONA_HERO_PILLS } from '../../../data/personaCurations';
import { WORKSHOP_JOURNEYS } from '../../../data/workshopJourneys';
import ObservatoryWorkbench from './ObservatoryWorkbench';
import { WORKBENCH_VIEW_KEY } from './workbenchView';

/**
 * There is no free-text box any more: a run starts by inspecting one of the
 * curated turns, and the query the agent receives is the canonical string from
 * personaCurations. Tests drive the surface the same way a participant does.
 */
const FRESH_TURNS = PERSONA_HERO_PILLS.marco;

async function inspectTurn(
  user: ReturnType<typeof userEvent.setup>,
  query: string,
) {
  await user.click(
    await screen.findByRole('button', { name: `Inspect: ${query}` }),
  );
}

/** Tool and skill names appear on the turn cards too, so trace-panel
 *  assertions must be scoped rather than matched globally. */
function tracePanel(container: HTMLElement): HTMLElement {
  const panel = container.querySelector<HTMLElement>(
    '.observatory-trace-panel',
  );
  if (!panel) throw new Error('trace panel not rendered');
  return panel;
}

describe('Pellier Observatory live agent workbench', () => {
  beforeEach(() => {
    // This suite is about what the workbench renders and sends, so it runs in
    // expert view where all three panels are mounted. Focus mode's one-panel
    // stepper is its own behaviour, covered by ObservatoryWorkbench.focus.test.tsx.
    localStorage.clear();
    localStorage.setItem(WORKBENCH_VIEW_KEY, 'expert');
    mocks.sendChatMessageStreaming.mockReset();
    mocks.fetch.mockReset();
    mocks.switchPersona.mockReset();
    mocks.persona = {
      id: 'marco',
      display_name: 'Marco',
      customer_id: 'CUST-MARCO',
    };
    mocks.fetch.mockImplementation(async (input: RequestInfo | URL) => {
      const requestUrl =
        input instanceof Request ? input.url : String(input);
      const url = new URL(requestUrl, 'http://localhost');
      const persona = url.searchParams.get('persona') ?? 'fresh';
      const prompts = PERSONA_HERO_PILLS[persona] ?? PERSONA_HERO_PILLS.fresh;
      return new Response(
        JSON.stringify({
          persona,
          scenarios: prompts.map((prompt, index) => ({
            id: index + 1,
            ordinal: index + 1,
            prompt,
            productName: null,
            imageUrl: null,
          })),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    });
    vi.stubGlobal('fetch', mocks.fetch);
  });

  it('opens as an inspectable doorway with no request to compose', async () => {
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', {
        name: 'Labs & Live Workbench',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Ground Marco’s warehouse answer in current Aurora rows/i,
      ),
    ).toBeInTheDocument();
    // The run state is reported once, by the ledger panel that runs.
    expect(screen.queryByText('Live trace surface')).not.toBeInTheDocument();
    expect(screen.getAllByText('Ready')).toHaveLength(1);
    expect(
      screen.getByRole('link', {
        name: 'Lab 1 Marco: Build a PostgreSQL-Grounded Agent',
      }),
    ).toHaveAttribute('aria-current', 'step');
    /*
     * A switcher, not a second lab gallery. The portraits introduce the four
     * scenarios on the Lab Collection; repeating them here opened the Workbench
     * with a copy of that tab. Four named options, the selected one marked, and
     * still links so deep links and Back/Forward are unchanged.
     */
    const labSwitch = screen.getByRole('navigation', { name: 'Select a lab' });
    expect(labSwitch).toBeVisible();
    expect(labSwitch.querySelectorAll('[data-lab-portrait]')).toHaveLength(0);
    expect(
      Array.from(labSwitch.querySelectorAll('a')).map((option) =>
        option.textContent?.trim(),
      ),
    ).toEqual(['1Marco', '2Anna', '3Theo', '4Jessica']);
    expect(
      labSwitch.querySelectorAll('a[data-selected="true"]'),
    ).toHaveLength(1);
    expect(
      tracePanel(document.body).querySelector('canvas.labs-hero-field'),
    ).not.toBeInTheDocument();
    const proofSummary = screen.getByRole('status', {
      name: 'Run proof summary',
    });
    expect(proofSummary).toHaveTextContent('Ready to inspect');
    expect(proofSummary).toHaveTextContent(
      'Choose an Aurora-backed guided shopper request.',
    );

    // The free-text box is gone: nothing here asks a participant to build.
    expect(screen.queryByLabelText('Shopper request')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Run agent' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByText(/^recorded$/i)).not.toBeInTheDocument();

    // Three required turns and two explicitly optional extensions, straight
    // from the shared storefront source.
    expect(FRESH_TURNS).toHaveLength(5);
    const requiredJourney = await screen.findByRole('region', {
      name: 'Required three-turn journey',
    });
    const exploreFurther = screen.getByRole('region', {
      name: 'Explore further',
    });
    expect(requiredJourney.querySelectorAll('button')).toHaveLength(3);
    expect(
      within(requiredJourney).getByText(
        'Each turn keeps the previous conversation.',
      ),
    ).toBeInTheDocument();
    expect(exploreFurther.querySelectorAll('button')).toHaveLength(2);
    // The required journey is a conversation: turn 1 is open, and turns 2 and
    // 3 wait for the turn before them. The explore prompts are optional
    // extensions and are never gated.
    expect(
      await screen.findByRole('button', { name: `Inspect: ${FRESH_TURNS[0]}` }),
    ).toBeEnabled();
    for (const query of FRESH_TURNS.slice(1, 3)) {
      expect(
        await screen.findByRole('button', { name: `Inspect: ${query}` }),
      ).toBeDisabled();
    }
    expect(within(requiredJourney).getByText('after turn 1')).toBeInTheDocument();
    for (const query of FRESH_TURNS.slice(3)) {
      expect(
        await screen.findByRole('button', { name: `Inspect: ${query}` }),
      ).toBeEnabled();
    }

    // The workbench exposes only the production shopper path at rest. The one
    // participant-facing model trade-off stays available but does not compete
    // with the canonical shopper turns until someone explicitly asks to tune it.
    expect(screen.queryByText('Edit controls')).not.toBeInTheDocument();
    expect(screen.getByText('Storefront Dispatcher')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show run setup' }))
      .toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Response mode')).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Balanced' })).not.toBeInTheDocument();
    expect(screen.queryByText('Agents-as-Tools')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Operator runs/i }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: /Input safety inspection/i }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: /Live trace visibility/i }))
      .not.toBeInTheDocument();
    expect(screen.getByTestId('shopper-answer-sparkle')).toHaveClass(
      'observatory-agent-sparkle',
    );
    expect(
      screen.queryByRole('button', { name: 'Graph' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('Grounded products from this turn will appear here.'),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Captured SQL')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Explore reference views/i }),
    ).toHaveAttribute('aria-expanded', 'false');
    expect(
      screen.queryByRole('heading', {
        name: 'Telemetry & system references',
      }),
    ).not.toBeInTheDocument();
  });

  it('anchors guided requests without changing the active shopper scenario', async () => {
    mocks.persona = {
      id: 'marco',
      display_name: 'Marco',
      customer_id: 'CUST-MARCO',
    };
    render(
      <MemoryRouter
        initialEntries={['/observatory/workbench?lab=retrieval-acceptance']}
      >
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('button', {
        name: `Inspect: ${WORKSHOP_JOURNEYS.anna.prompts[0]}`,
      }),
    ).toBeInTheDocument();
    expect(mocks.fetch).toHaveBeenCalledWith(
      '/api/observatory/scenarios?persona=anna',
    );
    expect(mocks.switchPersona).not.toHaveBeenCalled();
    expect(
      screen.queryByRole('button', {
        name: `Inspect: ${WORKSHOP_JOURNEYS.marco.prompts[0]}`,
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: `Inspect: ${WORKSHOP_JOURNEYS.anna.prompts[0]}`,
      }),
    ).toBeDisabled();
    expect(
      screen.queryByText(
        /Select Anna in the Storefront scenario switcher before the three-turn journey begins/i,
      ),
    ).not.toBeInTheDocument();
  });

  it('carries Jessica operator prompts into Lab 4 without running them as shopper turns', async () => {
    render(
      <MemoryRouter
        initialEntries={['/observatory/workbench?lab=fail-closed-policy']}
      >
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    for (const prompt of WORKSHOP_JOURNEYS.jessica.prompts) {
      expect(await screen.findByText(prompt)).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: `Inspect: ${prompt}` }),
      ).not.toBeInTheDocument();
    }
    expect(
      screen.getByRole('link', { name: /Open Jessica in Operator/i }),
    ).toHaveAttribute(
      'href',
      '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title',
    );
    expect(
      screen.getByRole('link', { name: /Open Jessica in Operator/i }),
    ).toHaveTextContent('Continue with the separately authenticated staff desk.')
    expect(screen.queryByRole('status', { name: 'Run proof summary' })).toBeNull();
    expect(screen.queryByText('Choose a shopper turn to inspect its answer and evidence.')).toBeNull();
    expect(screen.getByRole('link', { name: 'Review the Lab 4 proof' })).toHaveAttribute(
      'href', '/observatory/govern/verification',
    );
  });

  it('keeps the idle ledger and metrics honest before a run', () => {
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    expect(
      screen.queryByRole('heading', { name: 'Execution summary' }),
    ).not.toBeInTheDocument();
    // The seven rows are evidence categories, not a seven-step checklist a turn
    // walks in order, and the note now says so.
    expect(
      within(tracePanel(container)).getByText(
        /seven categories of evidence this turn can emit/i,
      ),
    ).toBeInTheDocument();
    expect(
      tracePanel(container).querySelector('.observatory-ledger-scroll'),
    ).toHaveAttribute('data-idle', 'true');
    /*
     * Seven categories, each stating its own state. They used to carry the
     * populated row's node glyph and a pulsing bar, which read as a row of
     * disabled controls that were still loading.
     */
    expect(
      container.querySelectorAll('[data-skeleton="true"] .observatory-trace-step'),
    ).toHaveLength(7);
    expect(
      container.querySelectorAll('[data-skeleton="true"] .observatory-trace-node'),
    ).toHaveLength(0);
    expect(
      within(tracePanel(container)).getAllByText('Not run'),
    ).toHaveLength(7);

    // Every metric reads "-" rather than 0, so an untouched page claims nothing.
    const metrics = screen.getByText('Elapsed').closest('dl');
    expect(metrics).not.toBeNull();
    expect(tracePanel(container)).toContainElement(metrics);
    expect(within(metrics!).getAllByText('-')).toHaveLength(4);
  });

  it('runs the real chat stream and renders only emitted evidence', async () => {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'intent_signal',
          intent: 'recommendation',
          classifier: 'deterministic',
          response_mode: 'balanced',
          model_family: 'opus',
          model_id: 'global.anthropic.claude-opus-4-6-v1',
        });
        onUpdate({
          type: 'skill_routing',
          routing: {
            loaded_skills: ['resort-styling'],
            considered: [{ name: 'resort-styling' }],
            elapsed_ms: 42,
          },
        });
        onUpdate({
          type: 'agent_step',
          agent: 'Orchestrator',
          action: 'Analyzing query',
          status: 'in_progress',
        });
        onUpdate({
          type: 'tool_call',
          tool: 'search_products_hybrid',
          status: 'executing',
        });
        onUpdate({
          type: 'content_delta',
          delta: 'I found a light linen option for the trip.',
        });
        onUpdate({
          type: 'product',
          product: {
            productId: 7,
            name: 'Pellier Linen Shirt',
            price: 128,
            category: 'Linen',
            imgurl: '/products/fresh-pellier-linen-shirt.png',
          },
        });
        onUpdate({
          type: 'db_queries',
          queries: [
            {
              op: 'select',
              table: 'product_catalog',
              sql: 'SELECT name, price FROM pellier.product_catalog LIMIT 12',
              duration_ms: 18,
            },
          ],
        });
        onUpdate({
          type: 'agent_step',
          agent: 'Orchestrator',
          action: 'Done',
          status: 'completed',
        });
        onUpdate({
          type: 'complete',
          response: {
            response: 'I found a light linen option for the trip.',
            products: [],
            rail: 'in-process',
            orchestration: {
              pattern: 'dispatcher',
              route: 'recommendation',
              router: 'deterministic',
            },
          },
        });
        return {
          response: 'I found a light linen option for the trip.',
          products: [],
          suggestions: [],
        };
      },
    );

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenCalledWith(
        FRESH_TURNS[0],
        [],
        expect.any(Function),
        undefined,
        false,
        'CUST-MARCO',
        'dispatcher',
        'balanced',
      );
    });

    expect(await screen.findByText('Pellier Linen Shirt')).toBeInTheDocument();
    expect(screen.getByText('Recommended result')).toBeInTheDocument();
    expect(screen.getByText('Best match')).toBeInTheDocument();
    expect(
      screen.getByText('First recommendation from this turn'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Curated pairings')).not.toBeInTheDocument();
    expect(
      screen.getByText('I found a light linen option for the trip.'),
    ).toBeInTheDocument();
    expect(
      within(tracePanel(container)).getByText('search_products_hybrid'),
    ).toBeInTheDocument();
    const toolTitle = within(tracePanel(container)).getByRole('heading', {
      name: 'search_products_hybrid',
    });
    expect(toolTitle).toHaveTextContent('search_products_hybrid');
    expect(toolTitle.querySelector('wbr')).toBeNull();
    expect(screen.getByText('Recommendation')).toBeInTheDocument();
    expect(screen.getByText('Claude Opus 4.6')).toBeInTheDocument();
    expect(screen.getByText('Routing decision')).toBeInTheDocument();
    expect(screen.getByText('Deterministic')).toBeInTheDocument();
    expect(
      screen.getByText('global.anthropic.claude-opus-4-6-v1'),
    ).toBeInTheDocument();
    expect(screen.getByText('In process')).toBeInTheDocument();
    expect(
      screen.getByText('Dispatcher / Recommendation'),
    ).toBeInTheDocument();
    const sqlTitle = within(tracePanel(container)).getByRole('heading', {
      name: 'SELECT / product_catalog',
    });
    expect(sqlTitle).toBeInTheDocument();
    expect(sqlTitle.querySelector('wbr')).toBeNull();
    expect(screen.getByLabelText('Captured SQL')).toHaveTextContent(
      /SELECT name, price\s+FROM pellier\.product_catalog\s+LIMIT 12/,
    );
    expect(
      screen.getByRole('button', {
        name: 'Hide the Aurora receipt for SELECT / product_catalog',
      }),
    ).toHaveTextContent('Receipt');
    const sqlReceipt = screen
      .getByText('Aurora SQL receipt')
      .closest('.observatory-proof-block');
    expect(sqlReceipt).not.toBeNull();
    const sqlReceiptElement = sqlReceipt as HTMLElement;
    expect(within(sqlReceiptElement).getByText('db_queries')).toBeInTheDocument();
    expect(within(sqlReceiptElement).getByText('None')).toBeInTheDocument();
    expect(within(sqlReceiptElement).getByText('Completed')).toBeInTheDocument();
    expect(
      within(sqlReceiptElement).getByRole('button', {
        name: 'Copy captured SQL',
      }),
    ).toBeInTheDocument();
    const proofSummary = screen.getByRole('status', {
      name: 'Run proof summary',
    });
    expect(within(proofSummary).getByText('Completed')).toBeInTheDocument();
    expect(proofSummary).toHaveTextContent('Evidence captured');
    expect(proofSummary).toHaveTextContent(
      '4 events. 1 agent. 1 SQL query. 1 product.',
    );

    const metrics = screen.getByText('Elapsed').closest('dl');
    expect(metrics).not.toBeNull();
    expect(within(metrics!).getByText('SQL')).toBeInTheDocument();
    expect(within(metrics!).getAllByText('1')).toHaveLength(2);
    expect(
      tracePanel(container).querySelector('[data-current="true"]'),
    ).not.toBeInTheDocument();
    expect(
      within(tracePanel(container)).queryByText('OpenTelemetry export'),
    ).not.toBeInTheDocument();
  });

  it('adds observability only when the completed response emits trace evidence', async () => {
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'Trace-backed response',
      products: [],
      suggestions: [],
      session_id: 'session-otel-1',
      agent_execution: {
        agent_steps: [],
        tool_calls: [],
        reasoning_steps: [],
        trace_id: '4bf92f3577b34da6a3ce929d0e0e4736',
        traceIds: [
          '4bf92f3577b34da6a3ce929d0e0e4736',
          '4bf92f3577b34da6a3ce929d0e0e4736',
        ],
        total_duration_ms: 42,
        success_rate: 1,
        otel_enabled: true,
      },
    });

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    const trace = within(tracePanel(container));
    expect(await trace.findByText('OpenTelemetry export')).toBeInTheDocument();
    expect(
      trace.getByText('1 trace identifier emitted for this completed turn'),
    ).toBeInTheDocument();
    expect(
      trace.getByText(/SDK-backed OTEL \/ agent \/ model \/ tool spans/),
    ).toBeInTheDocument();
    expect(trace.getByRole('link', { name: 'Open session telemetry' }))
      .toHaveAttribute(
        'href',
        '/observatory/sessions/session-otel-1/telemetry',
      );
  });

  it('renders Markdown emphasis in the grounded recommendation', async () => {
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response:
        'The **Merino Travel Socks** are practical, while the **Leather Journal** adds ceremony.',
      products: [
        {
          productId: 18,
          name: 'Merino Travel Socks',
          price: 38,
          category: 'Accessories',
        },
      ],
      suggestions: [],
    });

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);
    await screen.findByText('Best match');

    const answer = container.querySelector('.observatory-agent-response');
    expect(answer).not.toBeNull();
    expect(
      answer?.querySelector('.observatory-agent-response-label'),
    ).toHaveTextContent('Recommended result');
    expect(
      answer?.querySelector('.observatory-agent-prose'),
    ).not.toHaveClass('observatory-agent-response-label');
    expect(answer?.querySelectorAll('strong')).toHaveLength(2);
    expect(answer).toHaveTextContent('Merino Travel Socks');
    expect(answer).toHaveTextContent('Leather Journal');
    expect(answer).not.toHaveTextContent('**');
  });

  it('lights and follows only the latest evidence row while a run is active', async () => {
    let finishRun = () => {};
    mocks.sendChatMessageStreaming.mockImplementation(
      (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) =>
        new Promise((resolve) => {
          onUpdate({
            type: 'skill_routing',
            routing: {
              loaded_skills: ['resort-styling'],
              considered: [{ name: 'resort-styling' }],
              elapsed_ms: 21,
            },
          });
          finishRun = () =>
            resolve({
              response: 'Finished response',
              products: [],
              suggestions: [],
            });
        }),
    );

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    await waitFor(() => {
      const current = tracePanel(container).querySelector(
        '.observatory-trace-step[data-current="true"]',
      );
      expect(current).toBeInTheDocument();
      expect(current).toHaveTextContent('Skill routing');
      expect(
        tracePanel(container).querySelector(
          '.observatory-trace-progress',
        ),
      ).toBeInTheDocument();
    });

    finishRun();

    await waitFor(() => {
      expect(
        tracePanel(container).querySelector('[data-current="true"]'),
      ).not.toBeInTheDocument();
    });
  });

  it('keeps rich streamed prose when completion text is materially shorter', async () => {
    const streamed =
      'I found three linen layers that work together: a camp shirt for warm afternoons, an overshirt for evenings, and drawstring trousers for travel days.';
    const fallback = 'Here are some great options!';
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({ type: 'content_delta', delta: streamed });
        onUpdate({
          type: 'complete',
          response: { response: fallback, products: [] },
        });
        return { response: fallback, products: [], suggestions: [] };
      },
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    expect(await screen.findByText(streamed)).toBeInTheDocument();
    expect(screen.queryByText(fallback)).not.toBeInTheDocument();
  });

  it('offers a retry after a failed turn and reruns the same request', async () => {
    mocks.sendChatMessageStreaming
      .mockRejectedValueOnce(new Error('Temporary stream failure'))
      .mockResolvedValueOnce({
        response: 'Recovered response',
        products: [],
        suggestions: [],
      });

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    expect(
      await screen.findByText('Temporary stream failure'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('status', { name: 'Run proof summary' }),
    ).toHaveTextContent(
      'Turn 1 needs attention',
    );

    await user.click(screen.getByRole('button', { name: 'Retry turn' }));

    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenCalledTimes(2);
    });
    expect(mocks.sendChatMessageStreaming.mock.calls[1][0]).toBe(FRESH_TURNS[0]);
    expect(await screen.findByText('Recovered response')).toBeInTheDocument();
  });

  it('applies the compact response-mode tuning to the fixed Dispatcher request', async () => {
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'Configured response',
      products: [],
      suggestions: [],
    });

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: 'Show run setup' }));
    await user.click(screen.getByRole('radio', { name: 'Editorial' }));
    await inspectTurn(user, FRESH_TURNS[0]);

    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenCalledWith(
        FRESH_TURNS[0],
        [],
        expect.any(Function),
        undefined,
        false,
        'CUST-MARCO',
        'dispatcher',
        'editorial',
      );
    });
  });

  it('keeps operator actions out of the shopper workbench', () => {
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('button', { name: /Review low stock/i }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Restock product 37/i }))
      .not.toBeInTheDocument();
    expect(container).not.toHaveTextContent(/Operator Concierge/i);
  });

  it('renders live memory and guardrail receipts in the journey', async () => {
    // Persona set below, so this run uses Marco's curated turns, not fresh's.
    mocks.persona = {
      id: 'marco',
      display_name: 'Marco',
      customer_id: 'CUST-MARCO',
    };
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'guardrail_decision',
          guardrail: {
            allowed: true,
            action: 'NONE',
            violations: 0,
            mode: 'pass-through',
            enforced: false,
          },
        });
        onUpdate({
          type: 'aurora_profile_context',
          profile: {
            source: 'aurora',
            customer_id: 'CUST-MARCO',
            facts_available: 3,
            orders_available: 1,
            available: true,
          },
        });
        onUpdate({
          type: 'agentcore_memory',
          memory: {
            source: 'agentcore-memory',
            turns_loaded: 2,
            turns_persisted: 2,
            namespace_scope: 'verified-principal',
          },
        });
        onUpdate({
          type: 'complete',
          response: {
            response: 'A grounded response.',
            products: [],
            rail: 'in-process',
            orchestration: {
              pattern: 'dispatcher',
              route: 'recommendation',
              router: 'deterministic',
            },
          },
        });
        return {
          response: 'A grounded response.',
          products: [],
          suggestions: [],
        };
      },
    );

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    // Marco is the active persona here, so the card offers Marco's turns.
    await inspectTurn(user, PERSONA_HERO_PILLS.marco[0]);

    const trace = () => within(tracePanel(container));
    await waitFor(() =>
      expect(
        trace().getByText('3 profile facts and 1 past order available'),
      ).toBeInTheDocument(),
    );
    expect(
      trace().getByText('2 prior turns read; 2 new turns persisted'),
    ).toBeInTheDocument();
    expect(
      trace().getByText('Request evaluated before agent execution'),
    ).toBeInTheDocument();
    expect(
      trace().getByText('pass-through / NONE / inspect only'),
    ).toBeInTheDocument();
    expect(screen.getByText('Dispatcher / Recommendation')).toBeInTheDocument();
  });

  it('does not present a failed memory read as an empty history', async () => {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'agentcore_memory',
          memory: {
            source: 'agentcore-memory',
            turns_loaded: 0,
            turns_persisted: 2,
            read_status: 'failed',
            write_status: 'succeeded',
            retry_recommended: true,
            error_code: 'memory_read_failed',
          },
        });
        onUpdate({
          type: 'complete',
          response: {
            response: 'The action completed without prior memory context.',
            products: [],
            rail: 'in-process',
          },
        });
        return {
          response: 'The action completed without prior memory context.',
          products: [],
          suggestions: [],
        };
      },
    );

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    const trace = () => within(tracePanel(container));
    await waitFor(() =>
      expect(
        trace().getByText(
          'Prior managed-memory context was unavailable; this action ran without it',
        ),
      ).toBeInTheDocument(),
    );
    expect(trace().getByText(/prior context unavailable/)).toBeInTheDocument();
    expect(
      tracePanel(container).querySelector(
        '[data-kind="memory"][data-status="unavailable"]',
      ),
    ).not.toBeNull();
    expect(
      trace().queryByText('0 prior turns read; 2 new turns persisted'),
    ).not.toBeInTheDocument();
  });

  it('renders only products named by the shopper answer, in answer order', async () => {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'product',
          product: {
            productId: 20,
            name: 'Merino Travel Socks',
            price: 38,
          },
        });
        onUpdate({
          type: 'product',
          product: {
            productId: 11,
            name: 'Italian Linen Camp Shirt',
            price: 228,
          },
        });
        onUpdate({
          type: 'product',
          product: {
            productId: 40,
            name: 'Canvas Dopp Kit',
            price: 85,
          },
        });
        onUpdate({
          type: 'product',
          product: {
            productId: 12,
            name: 'Washed Cotton Oxford',
            price: 142,
          },
        });
        onUpdate({
          type: 'product',
          product: {
            productId: 34,
            name: 'Soft Leather Travel Pouch',
            price: 96,
          },
        });
        onUpdate({
          type: 'product',
          product: {
            productId: 99,
            name: 'Unselected catalog candidate',
            price: 40,
          },
        });
        onUpdate({
          type: 'complete',
          response: {
            response:
              'Lead with the Italian Linen Camp Shirt, then add the Merino Travel Socks, Canvas Dopp Kit, Washed Cotton Oxford, and Soft Leather Travel Pouch for the flight.',
            products: [],
            rail: 'in-process',
          },
        });
        return {
          response:
            'Lead with the Italian Linen Camp Shirt, then add the Merino Travel Socks, Canvas Dopp Kit, Washed Cotton Oxford, and Soft Leather Travel Pouch for the flight.',
          products: [],
          suggestions: [],
        };
      },
    );

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);
    await screen.findByText('Italian Linen Camp Shirt');

    expect(screen.getByText('Best match')).toBeInTheDocument();
    expect(screen.getByText('Grounded results')).toBeInTheDocument();
    expect(
      screen.getByText('4 additional products returned by this turn'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Unselected catalog candidate'),
    ).not.toBeInTheDocument();
    expect(
      container.querySelector('[data-product-role="best-match"] h4'),
    ).toHaveTextContent('Italian Linen Camp Shirt');
    const pairingNames = Array.from(
      container.querySelectorAll('[data-product-role="pairing"] h4'),
    ).map((heading) => heading.textContent);
    expect(pairingNames).toEqual([
      'Merino Travel Socks',
      'Canvas Dopp Kit',
      'Washed Cotton Oxford',
      'Soft Leather Travel Pouch',
    ]);

    const productNames = Array.from(
      container.querySelectorAll('.observatory-product-copy h4'),
    ).map((heading) => heading.textContent);
    expect(productNames).toEqual([
      'Italian Linen Camp Shirt',
      'Merino Travel Socks',
      'Canvas Dopp Kit',
      'Washed Cotton Oxford',
      'Soft Leather Travel Pouch',
    ]);
  });

  // A representative turn from each persona must stay byte-for-byte aligned.
  it.each([
    ['Marco', 'marco', 'CUST-MARCO', 'grounded-inventory'],
    ['Anna', 'anna', 'CUST-ANNA', 'retrieval-acceptance'],
    ['Theo', 'theo', 'CUST-THEO', 'managed-agent-path'],
  ] as const)(
    'sends %s their canonical curated turn verbatim, with live memory',
    async (displayName, id, customerId, labId) => {
      mocks.persona = {
        id,
        display_name: displayName,
        customer_id: customerId,
      };
      mocks.sendChatMessageStreaming.mockResolvedValue({
        response: 'Live response',
        products: [],
        suggestions: [],
      });

      const user = userEvent.setup();
      render(
        <MemoryRouter
          initialEntries={[`/observatory/workbench?lab=${labId}`]}
        >
          <ObservatoryWorkbench />
        </MemoryRouter>,
      );

      const requiredTurn = PERSONA_HERO_PILLS[id][2];
      expect(mocks.sendChatMessageStreaming).not.toHaveBeenCalled();

      // The third turn is the end of a conversation, so it is reached by
      // running the journey in order; it cannot be started on its own.
      await inspectTurn(user, PERSONA_HERO_PILLS[id][0]);
      await waitFor(() =>
        expect(mocks.sendChatMessageStreaming).toHaveBeenCalledTimes(1),
      );
      await inspectTurn(user, PERSONA_HERO_PILLS[id][1]);
      await waitFor(() =>
        expect(mocks.sendChatMessageStreaming).toHaveBeenCalledTimes(2),
      );
      await inspectTurn(user, requiredTurn);

      await waitFor(() => {
        expect(mocks.sendChatMessageStreaming).toHaveBeenCalledWith(
          requiredTurn,
          [
            expect.objectContaining({
              role: 'user',
              content: PERSONA_HERO_PILLS[id][0],
            }),
            expect.objectContaining({ role: 'assistant', content: 'Live response' }),
            expect.objectContaining({
              role: 'user',
              content: PERSONA_HERO_PILLS[id][1],
            }),
            expect.objectContaining({ role: 'assistant', content: 'Live response' }),
          ],
          expect.any(Function),
          undefined,
          false,
          customerId,
          'dispatcher',
          'balanced',
        );
      });
    },
  );

  it("keeps Marco's warehouse turn aligned with workshop content", async () => {
    mocks.persona = {
      id: 'marco',
      display_name: 'Marco',
      customer_id: 'CUST-MARCO',
    };
    render(
      <MemoryRouter
        initialEntries={['/observatory/workbench?lab=grounded-inventory']}
      >
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('button', {
        name: `Inspect: ${PERSONA_HERO_PILLS.marco[2]}`,
      }),
    ).toBeInTheDocument();
  });

  /**
   * A run that emits two Aurora receipts, so per-receipt disclosure, the bulk
   * control, and the claim-to-event link all have something real to act on.
   */
  function mockTwoReceiptRun() {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'intent_signal',
          intent: 'recommendation',
          classifier: 'deterministic',
          response_mode: 'balanced',
          model_family: 'opus',
          model_id: 'global.anthropic.claude-opus-4-6-v1',
        });
        onUpdate({
          type: 'skill_routing',
          routing: { loaded_skills: ['resort-styling'], elapsed_ms: 30 },
        });
        onUpdate({ type: 'tool_call', tool: 'search_products', status: 'executing' });
        onUpdate({
          type: 'product',
          product: {
            productId: 7,
            name: 'Pellier Linen Shirt',
            price: 128,
            category: 'Linen',
          },
        });
        onUpdate({
          type: 'db_queries',
          queries: [
            {
              op: 'select',
              table: 'product_catalog',
              sql: 'SELECT name FROM pellier.product_catalog WHERE name ILIKE %s',
              duration_ms: 21,
            },
            {
              op: 'insert',
              table: 'tool_audit',
              sql: 'INSERT INTO pellier.tool_audit (tool) VALUES (%s)',
              duration_ms: 9,
            },
          ],
        });
        onUpdate({
          type: 'complete',
          response: {
            response: 'A grounded linen answer.',
            products: [],
            rail: 'in-process',
            orchestration: {
              pattern: 'dispatcher',
              route: 'recommendation',
              router: 'deterministic',
            },
          },
        });
        return {
          response: 'A grounded linen answer.',
          products: [],
          suggestions: [],
        };
      },
    );
  }

  // A DENY says the tool never ran; a tool event exists only when a tool_audit
  // row proves it did. The receipt strip is where the three receipts are read
  // together, so it is where the disagreement has to be stated rather than left
  // for the reader to spot between two neighbouring cells.
  function ledgerWith(events: unknown[]) {
    return {
      version: '1.0',
      authority: 'canonical-receipt-projection',
      principalScoped: true,
      turnId: 'turn-1',
      sessionId: 'session-1',
      events,
      evidenceSufficiency: [],
    };
  }

  function policyEvent(tool: string, decision: string, status: string, auditId: number | null = 77) {
    return {
      sequence: 2,
      eventKind: 'policy',
      phase: 'governance',
      status,
      provenance: 'aurora-receipt',
      turnId: 'turn-1',
      evidenceRef: { kind: 'governed_turn_receipt_policy', id: 'turn-1:1' },
      title: 'Policy decision',
      summary: `Policy outcome: ${decision}.`,
      details: { decision, tool, audit_id: auditId },
    };
  }

  function toolEvent(tool: string) {
    return {
      sequence: 3,
      eventKind: 'tool',
      phase: 'execution',
      status: 'succeeded',
      provenance: 'aurora-receipt',
      turnId: 'turn-1',
      evidenceRef: { kind: 'tool_audit', id: '77' },
      title: 'Tool execution',
      summary: `agent executed ${tool}.`,
      details: { tool, caller: 'agent' },
    };
  }

  const routeEvent = {
    sequence: 1,
    eventKind: 'route',
    phase: 'routing',
    status: 'succeeded',
    provenance: 'aurora-receipt',
    turnId: 'turn-1',
    evidenceRef: { kind: 'governed_turn_receipt', id: 'turn-1' },
    title: 'Execution route recorded',
    summary: 'gateway-mcp rail captured at terminal persistence.',
    details: { rail: 'gateway-mcp' },
  };

  function streamLedger(events: unknown[]) {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        const evidenceLedger = ledgerWith(events);
        onUpdate({
          type: 'complete',
          response: {
            response: 'Answer.',
            products: [],
            evidence_ledger: evidenceLedger,
          },
        });
        return {
          response: 'Answer.',
          products: [],
          suggestions: [],
          evidence_ledger: evidenceLedger,
        };
      },
    );
  }

  it('names a DENY linked to the exact executed audit row as a conflict', async () => {
    streamLedger([
      routeEvent,
      policyEvent('issue_credit', 'DENY', 'denied'),
      toolEvent('issue_credit'),
    ]);
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    const conflict = await screen.findByTestId('observatory-receipt-conflict');
    expect(conflict).toHaveTextContent(/issue_credit/);
    expect(conflict).toHaveTextContent(/denied and executed/i);
  });

  it.each([
    { auditId: null, toolTurn: 'turn-1' },
    { auditId: 78, toolTurn: 'turn-1' },
    { auditId: 77, toolTurn: 'turn-2' },
  ])('does not infer a conflict from repeated tool names (%j)', async ({ auditId, toolTurn }) => {
    streamLedger([
      routeEvent,
      policyEvent('issue_credit', 'DENY', 'denied', auditId),
      { ...toolEvent('issue_credit'), turnId: toolTurn },
    ]);
    render(<MemoryRouter><ObservatoryWorkbench /></MemoryRouter>);
    await inspectTurn(userEvent.setup(), FRESH_TURNS[0]);
    expect(await screen.findByTestId('observatory-receipt-strip')).toBeInTheDocument();
    expect(screen.queryByTestId('observatory-receipt-conflict')).toBeNull();
  });

  it('reports missing receipts without asserting that nothing executed', async () => {
    streamLedger([routeEvent]);
    render(<MemoryRouter><ObservatoryWorkbench /></MemoryRouter>);
    await inspectTurn(userEvent.setup(), FRESH_TURNS[0]);
    const strip = await screen.findByTestId('observatory-receipt-strip');
    expect(strip).toHaveTextContent('no tool receipt recorded');
    expect(strip).toHaveTextContent('no Aurora query or write receipt recorded');
    expect(strip).not.toHaveTextContent('no tool ran');
    expect(strip).not.toHaveTextContent('nothing reached Aurora');
  });

  it('stays quiet when a DENY and an execution name different tools', async () => {
    // Ordinary governed behaviour: one tool refused, another allowed and run.
    streamLedger([
      routeEvent,
      policyEvent('issue_credit', 'DENY', 'denied'),
      toolEvent('check_inventory'),
    ]);
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    expect(await screen.findByTestId('observatory-receipt-strip')).toBeInTheDocument();
    expect(
      screen.queryByTestId('observatory-receipt-conflict'),
    ).not.toBeInTheDocument();
  });

  it('reconciles live events to the durable principal-scoped ledger', async () => {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({ type: 'tool_call', tool: 'search_products', status: 'executing' });
        const evidenceLedger = {
          version: '1.0',
          authority: 'canonical-receipt-projection',
          principalScoped: true,
          turnId: 'turn-1',
          sessionId: 'session-1',
          events: [
            {
              sequence: 1,
              eventKind: 'route',
              phase: 'routing',
              status: 'succeeded',
              provenance: 'aurora-receipt',
              turnId: 'turn-1',
              evidenceRef: { kind: 'governed_turn_receipt', id: 'turn-1' },
              title: 'Execution route recorded',
              summary: 'gateway-mcp rail captured at terminal persistence.',
              details: { rail: 'gateway-mcp' },
            },
            {
              sequence: 2,
              eventKind: 'response',
              phase: 'terminal',
              status: 'succeeded',
              provenance: 'aurora-receipt',
              turnId: 'turn-1',
              durationMs: 47,
              evidenceRef: { kind: 'governed_turn_receipt', id: 'turn-1' },
              title: 'Terminal turn receipt',
              summary: 'Turn ended complete with 1 citation and 0 tool receipts.',
              details: { terminal_status: 'complete' },
            },
            {
              sequence: 3,
              eventKind: 'operator_review',
              phase: 'follow_up',
              status: 'planned',
              provenance: 'aurora-receipt',
              turnId: 'turn-1',
              evidenceRef: { kind: 'operator_review', id: '41' },
              title: 'Operator review opened',
              summary:
                'initiate_return was prepared for Operator review. The shopper rail did not execute the mutation.',
              details: {
                lifecycle: 'review_opened',
                review_id: 41,
                action: 'initiate_return',
              },
            },
          ],
          evidenceSufficiency: [
            {
              id: 'terminal-receipt',
              label: 'Immutable terminal receipt',
              status: 'satisfied',
              detail: 'The turn is anchored by governed_turn_receipts.',
            },
          ],
        };
        onUpdate({
          type: 'complete',
          response: {
            response: 'Durably grounded answer.',
            products: [],
            evidence_ledger: evidenceLedger,
          },
        });
        return {
          response: 'Durably grounded answer.',
          products: [],
          suggestions: [],
          evidence_ledger: evidenceLedger,
        };
      },
    );
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    expect(await screen.findByText('Evidence sufficiency')).toBeInTheDocument();
    expect(screen.getByText('Immutable terminal receipt')).toBeInTheDocument();
    expect(
      screen.getAllByText(/governed_turn_receipt:turn-1/).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText('Operator review opened')).toBeInTheDocument();
    expect(screen.getByText('operator_review')).toBeInTheDocument();
    expect(
      tracePanel(container).querySelector('.observatory-append-only')
        ?.textContent,
    ).toBe('Durable receipt projection. 3 events, 0 SQL receipts.');
    expect(screen.queryByText('search_products')).not.toBeInTheDocument();
  });

  it('discloses each Aurora receipt independently and in bulk', async () => {
    mockTwoReceiptRun();
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    // The newest receipt opens itself so a finished run shows proof without a
    // click; the earlier one stays closed.
    const latestReceiptToggle = await screen.findByRole('button', {
      name: 'Hide the Aurora receipt for INSERT / tool_audit',
    });
    expect(latestReceiptToggle.parentElement).toHaveClass(
      'observatory-trace-step',
    );
    expect(latestReceiptToggle.closest('.observatory-trace-content')).toBeNull();
    expect(
      screen.getByRole('button', {
        name: 'Show the Aurora receipt for SELECT / product_catalog',
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByLabelText('Captured SQL')).toHaveLength(1);

    // Bulk disclosure exists only because there is more than one receipt, and
    // it offers to expand while any row is still closed.
    await user.click(screen.getByRole('button', { name: /Expand all/ }));
    expect(screen.getAllByLabelText('Captured SQL')).toHaveLength(2);

    // Collapse all closes every row, including the one the default opened.
    await user.click(screen.getByRole('button', { name: /Collapse all/ }));
    expect(screen.queryByLabelText('Captured SQL')).not.toBeInTheDocument();

    // A single row still discloses on its own afterwards.
    await user.click(
      screen.getByRole('button', {
        name: 'Show the Aurora receipt for SELECT / product_catalog',
      }),
    );
    expect(screen.getAllByLabelText('Captured SQL')).toHaveLength(1);

    // The footer counts what state holds, not a hardcoded total: routing,
    // one tool call, and the two Aurora receipts.
    expect(
      tracePanel(container).querySelector('.observatory-append-only')
        ?.textContent,
    ).toBe('Live run timeline. 4 events, 2 SQL receipts.');
  });

  it('opens the ledger event a verified claim rests on', async () => {
    mockTwoReceiptRun();
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);
    await screen.findByText('Pellier Linen Shirt');

    // Three claims, and every one resolves to an emitted event.
    expect(
      screen.getByText('3 of 3 linked to a ledger event'),
    ).toBeInTheDocument();
    const claimLinks = screen.getAllByRole('button', { name: /Open event/ });
    expect(claimLinks).toHaveLength(3);

    // The route claim points at the routing event, so opening it marks that
    // row rather than any other.
    const routeClaim = screen
      .getByText('Dispatcher route')
      .closest('li') as HTMLElement;
    await user.click(
      within(routeClaim).getByRole('button', { name: /Open event/ }),
    );
    const linked = tracePanel(container).querySelector(
      '.observatory-trace-step[data-linked="true"]',
    );
    expect(linked).toHaveTextContent('Skill routing');
  });

  it('builds the rationale only from signals the turn emitted', async () => {
    mockTwoReceiptRun();
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    // Nothing has run, so there is no rationale to show.
    expect(
      screen.queryByRole('heading', { name: 'Why this answer' }),
    ).not.toBeInTheDocument();

    await inspectTurn(user, FRESH_TURNS[0]);

    expect(
      await screen.findByRole('heading', { name: 'Why this answer' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Classified as a Recommendation request by the deterministic router, then composed by Claude Opus 4.6.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Dispatched through the Dispatcher pattern to Recommendation.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Grounded by the tool search_products.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Aurora returned 2 query receipts on the In process rail.'),
    ).toBeInTheDocument();
    // The provenance line keeps this from reading as the model's own account.
    expect(
      screen.getByText("Assembled from this turn's emitted events."),
    ).toBeInTheDocument();
  });

  it('offers no bulk disclosure when a run captured a single receipt', async () => {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'db_queries',
          queries: [
            {
              op: 'select',
              table: 'product_catalog',
              sql: 'SELECT 1',
              duration_ms: 4,
            },
          ],
        });
        return { response: 'One receipt.', products: [], suggestions: [] };
      },
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);
    await screen.findByLabelText('Captured SQL');

    expect(
      screen.queryByRole('button', { name: /Expand all/ }),
    ).not.toBeInTheDocument();
  });

  it('keeps an SSE failure in the error state', async () => {
    mocks.sendChatMessageStreaming.mockImplementation(
      async (
        _query: string,
        _history: unknown[],
        onUpdate: (event: unknown) => void,
      ) => {
        onUpdate({
          type: 'error',
          error: 'Agent execution timed out',
        });
        throw new Error('Agent execution timed out');
      },
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Agent run did not complete');
    expect(alert).toHaveTextContent('Agent execution timed out');
    expect(screen.getAllByText('Run failed')).toHaveLength(1);
    expect(screen.queryByText('Live run complete')).not.toBeInTheDocument();
  });

  it('presents the production shopper path as fixed rather than editable', () => {
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    const controls = container.querySelector('.observatory-run-controls');
    expect(controls).not.toBeNull();
    expect(within(controls as HTMLElement).getByText('Storefront Dispatcher'))
      .toBeInTheDocument();
    expect(
      within(controls as HTMLElement).queryByText('Orchestration pattern'),
    ).not.toBeInTheDocument();
    expect(controls?.querySelector('details')).toBeNull();
  });

  it('states the one model trade-off once per section', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    const controls = container.querySelector('.observatory-run-controls');
    expect(controls).not.toBeNull();

    await user.click(
      within(controls as HTMLElement).getByRole('button', {
        name: 'Show run setup',
      }),
    );

    const responseModes = within(controls as HTMLElement).getAllByRole('radio');
    expect(responseModes.map((mode) => mode.getAttribute('aria-label'))).toEqual(
      ['Editorial', 'Balanced', 'Fast'],
    );
    expect(responseModes[1]).toHaveAttribute('data-state', 'on');
    expect(within(controls as HTMLElement).getAllByText(/^Balanced$/))
      .toHaveLength(1);
    expect(
      within(controls as HTMLElement).getAllByText('Response mode'),
    ).toHaveLength(1);
  });

  it('keeps the generic workbench free of an operator route', () => {
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    expect(container.querySelector('.observatory-operator-runs')).toBeNull();
    const controls = container.querySelector('.observatory-run-controls');
    expect(controls).not.toBeNull();
    expect(
      within(controls as HTMLElement).queryByRole('link', {
        name: /operator/i,
      }),
    ).not.toBeInTheDocument();
  });

  it('keeps tunable setup collapsed until the participant explicitly expands it', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    const controls = container.querySelector('.observatory-run-controls');
    expect(controls).not.toBeNull();
    const panel = controls as HTMLElement;

    const toggle = within(panel).getByRole('button', {
      name: 'Show run setup',
    });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(panel.querySelectorAll('fieldset')).toHaveLength(0);
    expect(within(panel).queryAllByRole('radio')).toHaveLength(0);
    expect(panel).toHaveTextContent(
      'reconciled to principal-scoped Aurora receipts when the turn completes',
    );

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAccessibleName('Hide run setup');
    expect(panel.querySelectorAll('fieldset')).toHaveLength(1);
    expect(within(panel).getAllByRole('radio')).toHaveLength(3);
  });
});
