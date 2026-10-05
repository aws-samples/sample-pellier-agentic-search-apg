import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  sendChatMessageStreaming: vi.fn(),
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
  usePersona: () => ({ persona: mocks.persona }),
}));

import {
  PERSONA_HERO_PILLS,
  PERSONA_LAB_THREADS,
} from '../../../data/personaCurations';
import PellierLabsWorkbench from './PellierLabsWorkbench';

/**
 * There is no free-text box any more: a run starts by inspecting one of the
 * curated turns, and the query the agent receives is the canonical string from
 * personaCurations. Tests drive the surface the same way a participant does.
 */
const FRESH_TURNS = PERSONA_HERO_PILLS.fresh;

async function inspectTurn(
  user: ReturnType<typeof userEvent.setup>,
  query: string,
) {
  await user.click(screen.getByRole('button', { name: `Inspect: ${query}` }));
}

/** Tool and skill names appear on the turn cards too, so trace-panel
 *  assertions must be scoped rather than matched globally. */
function tracePanel(container: HTMLElement): HTMLElement {
  const panel = container.querySelector<HTMLElement>(
    '.pellier-labs-trace-panel',
  );
  if (!panel) throw new Error('trace panel not rendered');
  return panel;
}

describe('Pellier Labs live agent workbench', () => {
  beforeEach(() => {
    mocks.sendChatMessageStreaming.mockReset();
    mocks.persona = null;
  });

  it('opens as an inspectable doorway with no request to compose', () => {
    render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', {
        name: 'Live Workbench',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Run a shopper request and inspect the agents, retrieval, memory, and Aurora evidence behind the answer.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Live agent surface')).toBeInTheDocument();
    expect(
      tracePanel(document.body).querySelector('canvas.labs-hero-field'),
    ).not.toBeInTheDocument();
    const proofSummary = screen.getByRole('status', {
      name: 'Run proof summary',
    });
    expect(proofSummary).toHaveTextContent('Ready to inspect');
    expect(proofSummary).toHaveTextContent(
      'Choose one of five canonical shopper turns.',
    );

    // The free-text box is gone: nothing here asks a participant to build.
    expect(screen.queryByLabelText('Shopper request')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Run agent' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByText(/recorded/i)).not.toBeInTheDocument();

    // Five curated turns, straight from the shared storefront source.
    expect(FRESH_TURNS).toHaveLength(5);
    for (const query of FRESH_TURNS) {
      expect(
        screen.getByRole('button', { name: `Inspect: ${query}` }),
      ).toBeEnabled();
    }

    expect(
      screen.getByText('Advanced run settings').closest('details'),
    ).not.toHaveAttribute('open');
    expect(screen.getByText('Response mode')).not.toBeVisible();
    expect(screen.getAllByText('Dispatcher')).toHaveLength(2);
    expect(screen.getByTestId('shopper-answer-sparkle')).toHaveClass(
      'pellier-labs-agent-sparkle',
    );
    expect(
      screen.queryByRole('button', { name: 'Graph' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('Grounded products from this turn will appear here.'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Captured SQL')).not.toBeInTheDocument();
  });

  it('keeps the idle ledger and metrics honest before a run', () => {
    const { container } = render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    expect(
      screen.queryByRole('heading', { name: 'Execution summary' }),
    ).not.toBeInTheDocument();
    expect(
      within(tracePanel(container)).getByText(
        'Select a guided request to populate the live trace.',
      ),
    ).toBeInTheDocument();
    expect(
      container.querySelectorAll('.pellier-labs-trace-node'),
    ).toHaveLength(6);

    // Every metric reads "-" rather than 0, so an untouched page claims nothing.
    const metrics = screen.getByText('Elapsed').closest('dl');
    expect(metrics).not.toBeNull();
    expect(tracePanel(container)).toContainElement(metrics);
    expect(within(metrics!).getAllByText('-')).toHaveLength(4);
  });

  it('carries a three-turn persona thread through real conversation history', async () => {
    mocks.persona = {
      id: 'anna',
      display_name: 'Anna',
      customer_id: 'CUST-ANNA',
    };
    mocks.sendChatMessageStreaming.mockImplementation(
      async (query: string) => ({
        response: `Grounded reply for ${query}`,
        products: [],
        suggestions: [],
      }),
    );

    const thread = PERSONA_LAB_THREADS.anna;
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await user.click(
      screen.getByRole('button', {
        name: 'Start three-turn memory and retrieval thread',
      }),
    );

    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenNthCalledWith(
        1,
        thread.turns[0],
        [],
        expect.any(Function),
        undefined,
        false,
        'CUST-ANNA',
        'dispatcher',
        'balanced',
      );
    });

    await user.click(
      screen.getByRole('button', {
        name: `Continue thread: ${thread.turns[1]}`,
      }),
    );

    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenNthCalledWith(
        2,
        thread.turns[1],
        [
          {
            role: 'user',
            content: thread.turns[0],
            timestamp: expect.any(Date),
          },
          {
            role: 'assistant',
            content: `Grounded reply for ${thread.turns[0]}`,
            timestamp: expect.any(Date),
            products: [],
          },
        ],
        expect.any(Function),
        undefined,
        false,
        'CUST-ANNA',
        'dispatcher',
        'balanced',
      );
    });

    await user.click(
      screen.getByRole('button', {
        name: `Continue thread: ${thread.turns[2]}`,
      }),
    );

    await waitFor(() => {
      const thirdHistory = mocks.sendChatMessageStreaming.mock.calls[2][1];
      expect(mocks.sendChatMessageStreaming.mock.calls[2][0]).toBe(
        thread.turns[2],
      );
      expect(thirdHistory).toHaveLength(4);
      expect(thirdHistory[0]?.content).toBe(thread.turns[0]);
      expect(thirdHistory[2]?.content).toBe(thread.turns[1]);
      expect(
        screen.getByRole('button', {
          name: 'Restart three-turn memory and retrieval thread',
        }),
      ).toBeInTheDocument();
    });
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
          model_id: 'global.anthropic.claude-opus-5',
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
          tool: 'find_pieces',
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
        <PellierLabsWorkbench />
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
        null,
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
      within(tracePanel(container)).getByText('find_pieces'),
    ).toBeInTheDocument();
    expect(screen.getByText('Recommendation')).toBeInTheDocument();
    expect(screen.getByText('Claude Opus 5')).toBeInTheDocument();
    expect(screen.getByText('Routing decision')).toBeInTheDocument();
    expect(screen.getByText('Deterministic')).toBeInTheDocument();
    expect(
      screen.getByText('global.anthropic.claude-opus-5'),
    ).toBeInTheDocument();
    expect(screen.getByText('In process')).toBeInTheDocument();
    expect(
      screen.getByText('Dispatcher / Recommendation'),
    ).toBeInTheDocument();
    expect(
      within(tracePanel(container)).getByRole('heading', {
        name: 'SELECT / product_catalog',
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Captured SQL')).toHaveTextContent(
      /SELECT name, price\s+FROM pellier\.product_catalog\s+LIMIT 12/,
    );
    const sqlReceipt = screen
      .getByText('Aurora SQL receipt')
      .closest('.pellier-labs-proof-block');
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
    expect(proofSummary).toHaveTextContent('Run complete');
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
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    await waitFor(() => {
      const current = tracePanel(container).querySelector(
        '.pellier-labs-trace-step[data-current="true"]',
      );
      expect(current).toBeInTheDocument();
      expect(current).toHaveTextContent('Skill routing');
      expect(
        tracePanel(container).querySelector(
          '.pellier-labs-trace-progress',
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
        <PellierLabsWorkbench />
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
        <PellierLabsWorkbench />
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

  it('applies the selected live configuration to the request', async () => {
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'Configured response',
      products: [],
      suggestions: [],
    });

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await user.click(screen.getByText('Advanced run settings'));
    await user.click(screen.getByRole('radio', { name: 'Graph' }));
    await user.click(screen.getByRole('radio', { name: 'Editorial' }));
    await user.click(
      screen.getByRole('switch', { name: /Input safety inspection/i }),
    );
    await inspectTurn(user, FRESH_TURNS[0]);

    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenCalledWith(
        FRESH_TURNS[0],
        [],
        expect.any(Function),
        undefined,
        true,
        null,
        'graph',
        'editorial',
      );
    });
  });

  it('keeps shopper and operator writes on Dispatcher', async () => {
    mocks.persona = {
      id: 'theo',
      display_name: 'Theo',
      customer_id: 'CUST-THEO',
    };
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'Operator response',
      products: [],
      suggestions: [],
    });

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await user.click(screen.getByText('Advanced run settings'));
    await user.click(
      screen.getByRole('radio', { name: 'Agents-as-Tools' }),
    );

    expect(
      screen.getByRole('button', {
        name: `Inspect: ${PERSONA_HERO_PILLS.theo[2]}`,
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: /Restock product 37/i }),
    ).toBeDisabled();

    await user.click(
      screen.getByRole('button', { name: /Review low stock/i }),
    );
    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenLastCalledWith(
        'Which pieces are running low?',
        [],
        expect.any(Function),
        undefined,
        false,
        null,
        'agents_as_tools',
        'balanced',
      );
    });

    await user.click(screen.getByRole('radio', { name: 'Dispatcher' }));
    await user.click(
      screen.getByRole('button', { name: /Restock product 37/i }),
    );
    await waitFor(() => {
      expect(mocks.sendChatMessageStreaming).toHaveBeenLastCalledWith(
        'Restock product 37 by 12 units.',
        [],
        expect.any(Function),
        undefined,
        false,
        null,
        'dispatcher',
        'balanced',
      );
    });
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
          type: 'memory_context',
          memory: {
            source: 'aurora',
            customer_id: 'CUST-MARCO',
            facts_loaded: 3,
            orders_loaded: 1,
            applied: true,
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
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await user.click(screen.getByText('Advanced run settings'));
    await user.click(
      screen.getByRole('switch', { name: /Input safety inspection/i }),
    );
    // Marco is the active persona here, so the card offers Marco's turns.
    await inspectTurn(user, PERSONA_HERO_PILLS.marco[0]);

    const trace = () => within(tracePanel(container));
    await waitFor(() =>
      expect(
        trace().getByText('3 profile facts and 1 past order loaded'),
      ).toBeInTheDocument(),
    );
    expect(
      trace().getByText('Request evaluated before agent execution'),
    ).toBeInTheDocument();
    expect(
      trace().getByText('pass-through / NONE / inspect only'),
    ).toBeInTheDocument();
    expect(screen.getByText('Dispatcher / Recommendation')).toBeInTheDocument();
  });

  it('promotes the first named product above its curated pairings', async () => {
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
            productId: 34,
            name: 'Soft Leather Travel Pouch',
            price: 96,
          },
        });
        onUpdate({
          type: 'complete',
          response: {
            response:
              'Lead with the Italian Linen Camp Shirt, then add the Merino Travel Socks and Soft Leather Travel Pouch for the flight.',
            products: [],
            rail: 'in-process',
          },
        });
        return {
          response:
            'Lead with the Italian Linen Camp Shirt, then add the Merino Travel Socks and Soft Leather Travel Pouch for the flight.',
          products: [],
          suggestions: [],
        };
      },
    );

    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);
    await screen.findByRole('heading', {
      name: 'Italian Linen Camp Shirt',
    });

    expect(screen.getByText('Best match')).toBeInTheDocument();
    expect(screen.getByText('Curated pairings')).toBeInTheDocument();
    expect(screen.getByText('2 supporting pieces')).toBeInTheDocument();
    expect(
      container.querySelector('[data-product-role="best-match"] h4'),
    ).toHaveTextContent('Italian Linen Camp Shirt');
    const pairingNames = Array.from(
      container.querySelectorAll('[data-product-role="pairing"] h4'),
    ).map((heading) => heading.textContent);
    expect(pairingNames).toEqual([
      'Merino Travel Socks',
      'Soft Leather Travel Pouch',
    ]);

    const productNames = Array.from(
      container.querySelectorAll('.pellier-labs-product-copy h4'),
    ).map((heading) => heading.textContent);
    expect(productNames).toEqual([
      'Italian Linen Camp Shirt',
      'Merino Travel Socks',
      'Soft Leather Travel Pouch',
    ]);

    const shopperAnswer = screen.getByRole('region', {
      name: 'Recommended result',
    });
    expect(
      within(shopperAnswer).getByText('Italian Linen Camp Shirt', {
        selector: 'strong',
      }),
    ).toBeInTheDocument();
    expect(
      within(shopperAnswer).queryByText('Merino Travel Socks', {
        selector: 'strong',
      }),
    ).not.toBeInTheDocument();
  });

  // A representative turn from each persona must stay byte-for-byte aligned.
  it.each([
    ['Marco', 'marco', 'CUST-MARCO'],
    ['Anna', 'anna', 'CUST-ANNA'],
    ['Theo', 'theo', 'CUST-THEO'],
  ] as const)(
    'sends %s their canonical curated turn verbatim, with live memory',
    async (displayName, id, customerId) => {
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
        <MemoryRouter>
          <PellierLabsWorkbench />
        </MemoryRouter>,
      );

      const turn4 = PERSONA_HERO_PILLS[id][3];
      expect(mocks.sendChatMessageStreaming).not.toHaveBeenCalled();
      await inspectTurn(user, turn4);

      await waitFor(() => {
        expect(mocks.sendChatMessageStreaming).toHaveBeenCalledWith(
          turn4,
          [],
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

  it("keeps Marco's Turn 5 aligned with the warehouse ask in workshop content", () => {
    mocks.persona = {
      id: 'marco',
      display_name: 'Marco',
      customer_id: 'CUST-MARCO',
    };
    render(
      <MemoryRouter>
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('button', {
        name: 'Inspect: Hadley availability in Brooklyn',
      }),
    ).toBeInTheDocument();
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
        <PellierLabsWorkbench />
      </MemoryRouter>,
    );

    await inspectTurn(user, FRESH_TURNS[0]);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Agent run did not complete');
    expect(alert).toHaveTextContent('Agent execution timed out');
    expect(screen.getAllByText('Error')).toHaveLength(1);
    expect(screen.queryByText('Live run complete')).not.toBeInTheDocument();
  });
});
