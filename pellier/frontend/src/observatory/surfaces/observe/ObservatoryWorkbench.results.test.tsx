/**
 * What the Grounded answer column and the ledger say in the three states a
 * participant actually meets: before a turn, after one that produced evidence,
 * and after one that was refused and produced none.
 *
 * The middle column's two result sections used to render before the first turn,
 * each explaining that nothing was there yet, inside a column whose own empty
 * state already said so. They are a finding now, not a promise: absent until a
 * turn settles, then present even when they are empty, because "this run linked
 * no claim" is the result a participant needs to read.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: { id: 'marco', display_name: 'Marco', customer_id: 'CUST-MARCO' },
    switchPersona: vi.fn(),
    switching: false,
    switchError: null,
  }),
}));

import ObservatoryWorkbench from './ObservatoryWorkbench';
import { WORKBENCH_VIEW_KEY } from './workbenchView';

const PROMPT = 'First guided turn';

function scenariosResponse(): Response {
  return new Response(
    JSON.stringify({
      persona: 'marco',
      scenarios: [
        {
          id: 1,
          ordinal: 1,
          prompt: PROMPT,
          journeyRole: 'required',
          journeyStage: 'establish',
          productName: null,
          imageUrl: null,
        },
      ],
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

function ledgerEvent(over: Record<string, unknown>) {
  return {
    sequence: 1,
    eventKind: 'tool',
    phase: 'execution',
    status: 'succeeded',
    provenance: 'aurora-receipt',
    turnId: 'turn-1',
    evidenceRef: { kind: 'tool_audit', id: '1' },
    title: 'Warehouse read',
    summary: 'Five rows for the Brooklyn warehouse.',
    ...over,
  };
}

function streamResponse(ledger: Record<string, unknown>): Response {
  const lines = [
    `data: ${JSON.stringify({ type: 'turn_start', turn_id: 'turn-1' })}`,
    `data: ${JSON.stringify({
      type: 'complete',
      response: {
        response: 'The answer.',
        products: [],
        rail: 'in-process',
        evidence_ledger: {
          version: '1',
          authority: 'canonical-receipt-projection',
          principalScoped: true,
          turnId: 'turn-1',
          ...ledger,
        },
      },
    })}`,
  ];
  return new Response(`${lines.join('\n\n')}\n\n`, { status: 200 });
}

function mount(ledger: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes('/api/chat/stream')) return streamResponse(ledger);
      return scenariosResponse();
    }),
  );
  return render(
    <MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
      <ObservatoryWorkbench />
    </MemoryRouter>,
  );
}

describe('workbench result states', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(WORKBENCH_VIEW_KEY, 'expert');
  });

  it('offers one empty state before the first turn, and no result sections', async () => {
    const { container } = mount({ events: [], evidenceSufficiency: [] });
    await screen.findByRole('button', { name: `Inspect: ${PROMPT}` });

    expect(
      screen.getByText('Choose a shopper turn to inspect its answer and evidence.'),
    ).toBeInTheDocument();
    expect(container.querySelector('.observatory-evidence-sufficiency')).toBeNull();
    expect(container.querySelector('.observatory-verified-claims')).toBeNull();

    // The seven categories state their own state rather than looking loaded.
    const skeleton = container.querySelectorAll('[data-skeleton="true"] .observatory-trace-step');
    expect(skeleton).toHaveLength(7);
    expect(skeleton[0]?.textContent).toContain('Not run');
    expect(container.querySelector('.observatory-trace-ghost')).toBeNull();
    // No index numbers: a turn does not walk these in a fixed order.
    expect(
      container.querySelector('[data-skeleton="true"] .observatory-trace-index'),
    ).toBeNull();
  });

  it('names what each ledger status means once a turn has produced evidence', async () => {
    const { container } = mount({
      events: [
        ledgerEvent({ sequence: 1, status: 'succeeded' }),
        ledgerEvent({
          sequence: 2,
          eventKind: 'policy',
          phase: 'governance',
          status: 'not_enforced',
          evidenceRef: { kind: 'governed_receipts', id: '2' },
          title: 'Policy boundary',
          summary: 'The managed rail was not used for this turn.',
        }),
        ledgerEvent({
          sequence: 3,
          eventKind: 'memory',
          phase: 'context',
          status: 'unavailable',
          evidenceRef: { kind: 'memory', id: '3' },
          title: 'Prior context',
          summary: 'The memory read did not return.',
        }),
      ],
      evidenceSufficiency: [
        { id: 's1', label: 'Durable receipt', status: 'satisfied', detail: 'Projected.' },
      ],
    });
    await screen.findByRole('button', { name: `Inspect: ${PROMPT}` });
    await userEvent.click(screen.getByRole('button', { name: `Inspect: ${PROMPT}` }));

    await waitFor(() =>
      expect(container.querySelector('.observatory-evidence-sufficiency')).not.toBeNull(),
    );
    expect(screen.getByText('Evidence available')).toBeInTheDocument();
    expect(screen.getByText('Not applicable to this run')).toBeInTheDocument();
    expect(screen.getByText('Evidence lookup failed')).toBeInTheDocument();
    // The raw enum is what these replaced.
    expect(screen.queryByText('not enforced')).toBeNull();
  });

  it('keeps both result sections after a refused turn that produced neither', async () => {
    const { container } = mount({
      events: [
        ledgerEvent({
          eventKind: 'policy',
          phase: 'governance',
          status: 'denied',
          evidenceRef: { kind: 'governed_receipts', id: '9' },
          title: 'Cedar decision',
          summary: 'DENY for a customer the caller does not own.',
        }),
      ],
      evidenceSufficiency: [],
    });
    await screen.findByRole('button', { name: `Inspect: ${PROMPT}` });
    await userEvent.click(screen.getByRole('button', { name: `Inspect: ${PROMPT}` }));

    // An empty result is the finding, so both sections stay on screen.
    await waitFor(() =>
      expect(container.querySelector('.observatory-evidence-sufficiency')).not.toBeNull(),
    );
    expect(container.querySelector('.observatory-verified-claims')).not.toBeNull();
    expect(screen.getByText('This turn linked no claim to an emitted event.')).toBeInTheDocument();
    expect(screen.getByText('Denied')).toBeInTheDocument();
  });
});
