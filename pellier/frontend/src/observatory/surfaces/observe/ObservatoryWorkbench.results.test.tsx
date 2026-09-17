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
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('motion/react', async (importOriginal) => ({
  ...await importOriginal<typeof import('motion/react')>(),
  useReducedMotion: () => true,
}));

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

function streamResponse(ledger: Record<string, unknown> | null): Response {
  const lines = [
    `data: ${JSON.stringify({ type: 'turn_start', turn_id: 'turn-1' })}`,
    `data: ${JSON.stringify({
      type: 'complete',
      response: {
        response: 'The answer.',
        products: [],
        rail: 'in-process',
        evidence_ledger: ledger === null ? undefined : {
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

function mount(
  ledger: Record<string, unknown> | null,
  stream?: () => Response,
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes('/api/chat/stream')) return stream?.() ?? streamResponse(ledger);
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
    expect(container.querySelector('.observatory-products-empty')).toBeNull();
    expect(container.querySelector('.observatory-answer-state')).toBeNull();
    expect(screen.getAllByRole('status', { name: 'Run proof summary' })).toHaveLength(1);
    expect(screen.getByRole('list', { name: 'Evidence categories' })).toBeVisible();

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
          summary: 'Policy outcome: WOULD_DENY.',
          details: { decision: 'WOULD_DENY', enforcement_mode: 'LOG_ONLY' },
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
    expect(screen.getByText('Would deny (not enforced)')).toBeInTheDocument();
    expect(screen.getByText('Memory unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Not applicable to this run')).toBeNull();
    expect(screen.queryByText('Evidence lookup failed')).toBeNull();
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

  it('distinguishes empty retrieval and null tool results from execution failures', async () => {
    mount({
      events: [
        ledgerEvent({
          sequence: 1, eventKind: 'retrieval', status: 'unavailable',
          title: 'No catalog citations', evidenceRef: { kind: 'retrieval_receipt', id: '1' },
          details: { citation_ids: [], candidate_count: 0 },
        }),
        ledgerEvent({
          sequence: 2, status: 'unavailable', title: 'Audited call without a result',
          details: { tool: 'check_inventory', result: null },
        }),
        ledgerEvent({
          sequence: 3, eventKind: 'aurora', status: 'failed', title: 'Query timeout',
          details: { accepted: true, execution_outcome: 'timeout' },
        }),
        ledgerEvent({
          sequence: 4, eventKind: 'model', status: 'failed', title: 'Model failure',
        }),
        ledgerEvent({
          sequence: 5, eventKind: 'operator_review', status: 'not_reached',
          title: 'Execution not entered', details: { evidence_outcome: 'NO_EXECUTION' },
        }),
        ledgerEvent({
          sequence: 6, eventKind: 'policy', status: 'not_enforced',
          title: 'Policy not evaluated', details: { decision: 'NOT_EVALUATED' },
        }),
      ],
      evidenceSufficiency: [],
    });
    await userEvent.click(await screen.findByRole('button', { name: `Inspect: ${PROMPT}` }));
    for (const label of [
      'No citations returned', 'No result recorded', 'Query execution failed',
      'Model invocation failed', 'Not reached', 'Not evaluated',
    ]) {
      expect(await screen.findByText(label)).toBeVisible();
    }
    expect(screen.queryByText('Evidence lookup failed')).toBeNull();
    expect(screen.queryByText('Not applicable to this run')).toBeNull();
  });

  it.each([401, 503])('keeps HTTP %s without a ledger distinct from an empty result', async (status) => {
    const { container } = mount(null, () => new Response(
      JSON.stringify({ detail: status === 401 ? 'authentication_required' : 'service_unavailable' }),
      { status, headers: { 'Content-Type': 'application/json' } },
    ));
    await userEvent.click(await screen.findByRole('button', { name: `Inspect: ${PROMPT}` }));
    expect(await screen.findByText(/Linked claims are unavailable/)).toBeVisible();
    expect(screen.getByText(/Evidence sufficiency is unavailable/)).toBeVisible();
    expect(screen.queryByText('This turn linked no claim to an emitted event.')).toBeNull();
    expect(screen.queryByText('Choose a shopper turn to inspect its answer and evidence.')).toBeNull();
    expect(screen.queryByRole('list', { name: 'Evidence categories' })).toBeNull();
    expect(container.querySelector('.observatory-products-empty')).toBeNull();
    const statusSummary = screen.getByRole('status', { name: 'Run proof summary' });
    expect(statusSummary).toHaveTextContent(status === 401 ? 'Sign-in required' : 'Run failed');
    if (status === 401) {
      expect(screen.getByRole('link', { name: 'Sign in to continue' })).toHaveAttribute(
        'href', expect.stringContaining('returnTo='),
      );
      expect(screen.queryByRole('button', { name: 'Retry turn' })).toBeNull();
      expect(screen.queryByText('Denied')).toBeNull();
    }
  });

  it('does not infer empty evidence from a complete answer without a ledger', async () => {
    mount(null);
    await userEvent.click(await screen.findByRole('button', { name: `Inspect: ${PROMPT}` }));
    expect(await screen.findByText('The answer.')).toBeVisible();
    expect(screen.getByText(/Linked claims are unavailable/)).toBeVisible();
    expect(screen.queryByText('This turn linked no claim to an emitted event.')).toBeNull();
    expect(screen.getByRole('status', { name: 'Run proof summary' })).not.toHaveTextContent('Evidence captured');
  });

  it('waits for completion before showing results and preserves a verified empty ledger', async () => {
    let stream!: ReadableStreamDefaultController<Uint8Array>;
    const encoder = new TextEncoder();
    const { container } = mount(null, () => new Response(new ReadableStream({
      start(controller) { stream = controller; },
    }), { headers: { 'Content-Type': 'text/event-stream' } }));
    await userEvent.click(await screen.findByRole('button', { name: `Inspect: ${PROMPT}` }));
    expect(screen.getByRole('status', { name: 'Run proof summary' })).toHaveTextContent('Running');
    expect(container.querySelector('.observatory-evidence-sufficiency')).toBeNull();
    expect(container.querySelector('.observatory-verified-claims')).toBeNull();
    expect(container.querySelector('.observatory-products-empty')).toBeNull();
    await act(async () => {
      stream.enqueue(encoder.encode(await streamResponse({ events: [], evidenceSufficiency: [] }).text()));
      stream.close();
    });
    expect(await screen.findByText('This turn linked no claim to an emitted event.')).toBeVisible();
    expect(screen.getByText('The recorded ledger contains no sufficiency checks for this turn.')).toBeVisible();
    expect(screen.getByText('The recorded ledger contains no events for this turn.')).toBeVisible();
  });

  it.each(['canonical', 'unavailable', 'wrong-turn', 'unscoped'])('reads exact-turn evidence after a streamed denial (%s)', async (receiptCase) => {
    const readable = receiptCase === 'canonical';
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.includes('/api/chat/stream')) {
        return new Response([
          `data: ${JSON.stringify({ type: 'turn_start', turn_id: 'denied-turn' })}`,
          `data: ${JSON.stringify({ type: 'tool_call', tool: 'Requested tool', status: 'executing' })}`,
          `data: ${JSON.stringify({ type: 'error', code: 'policy_denied', retryable: false, message: 'The ownership policy denied this request.' })}`,
        ].join('\n\n') + '\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
      }
      if (url.endsWith('/turns/denied-turn/ledger')) {
        return new Response(JSON.stringify(receiptCase !== 'unavailable' ? {
          version: '1', authority: 'canonical-receipt-projection', principalScoped: receiptCase !== 'unscoped',
          turnId: receiptCase === 'wrong-turn' ? 'another-turn' : 'denied-turn',
          events: [ledgerEvent({
            turnId: 'denied-turn', status: 'denied', eventKind: 'policy',
            title: 'Recorded Cedar denial', summary: 'Policy outcome: DENY.',
          })],
          evidenceSufficiency: [],
        } : { detail: 'evidence_ledger_unavailable' }), { status: receiptCase === 'unavailable' ? 503 : 200 });
      }
      return scenariosResponse();
    }));
    render(<MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
      <ObservatoryWorkbench />
    </MemoryRouter>);
    await userEvent.click(await screen.findByRole('button', { name: `Inspect: ${PROMPT}` }));
    expect(await screen.findByText(readable
      ? 'This turn linked no claim to an emitted event.'
      : 'Linked claims are unavailable because no durable ledger was received for this turn.',
    )).toBeVisible();
    expect(within(screen.getByRole('alert')).getByText('Policy denied')).toBeVisible();
    expect(screen.getByRole('status', { name: 'Run proof summary' })).toHaveTextContent('Denied');
    expect(screen.queryByRole('button', { name: 'Retry turn' })).toBeNull();
    expect(screen.queryByText('Running', { exact: true })).toBeNull();
    if (!readable) expect(screen.queryByText('Recorded Cedar denial')).toBeNull();
    expect(requests.filter(url => url.includes('/api/chat/stream'))).toHaveLength(1);
    expect(requests.filter(url => url.endsWith('/turns/denied-turn/ledger'))).toHaveLength(1);
  });
});
