/**
 * Focus mode: one panel at a time, in the order a participant works.
 *
 * Run, then inspect the evidence, then reconcile the answer against it. The
 * three-panel grid stays one toggle away for anyone who wants the whole
 * instrument at once, and the choice survives a reload.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  sendChatMessageStreaming: vi.fn(),
}));

vi.mock('../../../services/chat', () => ({
  sendChatMessageStreaming: mocks.sendChatMessageStreaming,
}));

const MARCO = {
  id: 'marco',
  display_name: 'Marco',
  customer_id: 'CUST-MARCO',
};

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: MARCO,
    switchPersona: vi.fn(),
    switching: false,
    switchError: null,
  }),
}));

import ObservatoryWorkbench from './ObservatoryWorkbench';
import { WORKBENCH_VIEW_KEY } from './workbenchView';

const PROMPTS = ['First guided turn', 'Second guided turn', 'Third guided turn'];

function scenariosResponse(): Response {
  return new Response(
    JSON.stringify({
      persona: 'marco',
      scenarios: PROMPTS.map((prompt, index) => ({
        id: index + 1,
        ordinal: index + 1,
        prompt,
        productName: null,
        imageUrl: null,
      })),
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

function renderWorkbench() {
  return render(
    <MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
      <ObservatoryWorkbench />
    </MemoryRouter>,
  );
}

function grid(): HTMLElement {
  const node = document.querySelector<HTMLElement>('.observatory-workbench-grid');
  if (!node) throw new Error('grid not rendered');
  return node;
}

function activePanel(): string | null {
  const node = document.querySelector<HTMLElement>('[data-focus-active="true"]');
  return node?.getAttribute('data-motion-panel') ?? null;
}

describe('Observatory workbench focus mode', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(WORKBENCH_VIEW_KEY, 'focus');
    mocks.sendChatMessageStreaming.mockReset();
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'A grounded answer.',
      products: [],
      suggestions: [],
    });
    vi.stubGlobal('fetch', vi.fn(async () => scenariosResponse()));
  });

  it('opens a saved focus view on the Run step with the other panels stepped back', async () => {
    renderWorkbench();

    expect(grid()).toHaveAttribute('data-view', 'focus');
    const stepper = screen.getByRole('navigation', { name: 'Workbench steps' });
    const steps = Array.from(stepper.querySelectorAll('button')).map(
      (button) => button.textContent?.replace(/^\d+\s*/, '').trim(),
    );
    expect(steps).toEqual(['Run', 'Inspect evidence', 'Reconcile answer']);
    // The step number is aria-hidden decoration, so the accessible name is
    // the step's own label.
    expect(screen.getByRole('button', { name: 'Run' })).toHaveAttribute(
      'aria-current',
      'step',
    );
    expect(activePanel()).toBe('requests');
    expect(screen.getAllByRole('status', { name: 'Run proof summary' })).toHaveLength(1);
    expect(screen.getByRole('status', { name: 'Run proof summary' })).toBeVisible();
  });

  it('stays on Run while the turn streams and moves to Inspect when it completes', async () => {
    const user = userEvent.setup();
    // Hold the turn open so "running" and "complete" are two observable
    // moments. During the stream the evidence panel has nothing in it, so
    // the request rail is the view worth being on.
    let settle: (() => void) | null = null;
    mocks.sendChatMessageStreaming.mockImplementation(
      () =>
        new Promise((resolve) => {
          settle = () =>
            resolve({ response: 'A grounded answer.', products: [], suggestions: [] });
        }),
    );
    renderWorkbench();

    await user.click(await screen.findByRole('button', { name: `Inspect: ${PROMPTS[0]}` }));

    await waitFor(() => expect(settle).not.toBeNull());
    expect(activePanel()).toBe('requests');
    expect(screen.getByRole('status', { name: 'Run proof summary' })).toHaveTextContent('Running');
    expect(screen.getByRole('button', { name: 'Run' })).toHaveAttribute(
      'aria-current',
      'step',
    );

    await act(async () => {
      settle!();
    });

    await waitFor(() => expect(activePanel()).toBe('trace'));
    expect(
      screen.getByRole('button', { name: /Inspect evidence/ }),
    ).toHaveAttribute('aria-current', 'step');

    await user.click(screen.getByRole('button', { name: /Reconcile answer/ }));
    expect(activePanel()).toBe('results');
    expect(screen.getByRole('status', { name: 'Run proof summary' })).toBeVisible();
    expect(screen.getByRole('status', { name: 'Run proof summary' })).toHaveTextContent('Completed');
  });

  it('restores the three-panel grid under Expert view and remembers it', async () => {
    const user = userEvent.setup();
    const { unmount } = renderWorkbench();

    const toggle = screen.getByRole('button', { name: 'Expert view' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await user.click(toggle);

    expect(grid()).toHaveAttribute('data-view', 'expert');
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.queryByRole('navigation', { name: 'Workbench steps' }),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem(WORKBENCH_VIEW_KEY)).toBe('expert');

    unmount();
    renderWorkbench();
    expect(grid()).toHaveAttribute('data-view', 'expert');
  });

  it('reveals the linked receipt when Open event is used from Reconcile', async () => {
    mocks.sendChatMessageStreaming.mockResolvedValue({
      response: 'An answer with a database receipt.',
      products: [],
      evidence_ledger: {
        version: '1', authority: 'canonical-receipt-projection',
        principalScoped: true, turnId: 'linked-turn',
        events: [{
          sequence: 1, eventKind: 'aurora', phase: 'execution',
          status: 'succeeded', provenance: 'aurora-receipt',
          turnId: 'linked-turn', evidenceRef: { kind: 'sql_query_log', id: '1' },
          title: 'Warehouse query', summary: 'One row returned.',
          sql: 'SELECT 1', details: { row_count: 1 },
        }],
        evidenceSufficiency: [],
      },
    });
    renderWorkbench();
    await userEvent.click(await screen.findByRole('button', { name: `Inspect: ${PROMPTS[0]}` }));
    await waitFor(() => expect(activePanel()).toBe('trace'));
    await userEvent.click(screen.getByRole('button', { name: 'Reconcile answer' }));
    await userEvent.click(screen.getByRole('button', { name: 'Open event' }));
    expect(activePanel()).toBe('trace');
    expect(screen.getByRole('button', { name: 'Inspect evidence' })).toHaveAttribute('aria-current', 'step');
    expect(document.querySelector('[data-linked="true"]')).toHaveTextContent('Warehouse query');
  });
});
