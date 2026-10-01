/**
 * Explore prompts are runnable whenever the workbench is idle.
 *
 * They sit outside the ordered three-turn journey, so they are side
 * excursions rather than turn 4 and turn 5 of a conversation. The rail
 * already rendered them enabled; `runAgent` used to gate every index on the
 * one before it, so pressing an explore prompt out of order returned with no
 * run, no error and no state change. This asserts the button's enabled state
 * and the run's willingness are the same answer.
 *
 * Runs in expert view so the request rail stays mounted, as in
 * ObservatoryWorkbench.history.test.tsx.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
import { mockWorkbenchWidth } from '../../../test-support/workbenchViewport';

/** Mirrors the seeded shape: three required turns, then two explore prompts. */
const REQUIRED = ['First guided turn', 'Second guided turn', 'Third guided turn'];
const EXPLORE = ['First explore prompt', 'Second explore prompt'];

function scenariosResponse(): Response {
  const scenarios = [
    ...REQUIRED.map((prompt, index) => ({
      id: index + 1,
      ordinal: index + 1,
      prompt,
      journeyRole: 'required',
      journeyStage: (['establish', 'exercise', 'prove'] as const)[index],
      productName: null,
      imageUrl: null,
    })),
    ...EXPLORE.map((prompt, index) => ({
      id: REQUIRED.length + index + 1,
      ordinal: REQUIRED.length + index + 1,
      prompt,
      journeyRole: 'explore',
      journeyStage: null,
      productName: null,
      imageUrl: null,
    })),
  ];
  return new Response(JSON.stringify({ persona: 'marco', scenarios }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function streamResponse(): Response {
  const lines = [
    `data: ${JSON.stringify({ type: 'turn_start', turn_id: 'turn-explore' })}`,
    `data: ${JSON.stringify({
      type: 'complete',
      response: { response: 'Explore answer', products: [], rail: 'in-process' },
    })}`,
  ];
  return new Response(`${lines.join('\n\n')}\n\n`, { status: 200 });
}

const chatBodies: Array<Record<string, unknown>> = [];

describe('Observatory explore prompts', () => {
  beforeEach(() => {
    localStorage.clear();
    mockWorkbenchWidth(1440);
    chatBodies.length = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.includes('/api/chat/stream')) {
          chatBodies.push(JSON.parse(String(init?.body)));
          return streamResponse();
        }
        return scenariosResponse();
      }),
    );
  });

  it('runs the second explore prompt before any required turn has completed', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await screen.findByRole('button', { name: `Run request: ${REQUIRED[0]}` });
    await user.click(screen.getByText('Explore further'));

    const secondExplore = screen.getByRole('button', {
      name: `Run request: ${EXPLORE[1]}`,
    });
    // The rail offers it, so pressing it has to do something.
    expect(secondExplore).toBeEnabled();

    await user.click(secondExplore);

    await waitFor(() => expect(chatBodies).toHaveLength(1));
    expect(chatBodies[0].message).toBe(EXPLORE[1]);
    expect(chatBodies[0].conversation_history).toEqual([]);
  });

  it('still gates the required turns on the turn before them', async () => {
    render(
      <MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    await screen.findByRole('button', { name: `Run request: ${REQUIRED[0]}` });
    await userEvent.click(screen.getByText('Explore further'));

    expect(screen.getByRole('button', { name: `Run request: ${REQUIRED[0]}` })).toBeEnabled();
    expect(screen.getByRole('button', { name: `Run request: ${REQUIRED[1]}` })).toBeDisabled();
    expect(screen.getByRole('button', { name: `Run request: ${REQUIRED[2]}` })).toBeDisabled();
    expect(screen.getByRole('button', { name: `Run request: ${EXPLORE[0]}` })).toBeEnabled();
  });

  it('uses explicit roles when required requests have nonconsecutive seed ordinals', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes('/api/chat/stream')) {
        chatBodies.push(JSON.parse(String(init?.body)));
        return streamResponse();
      }
      return new Response(JSON.stringify({ scenarios: [
        { id: 1, ordinal: 1, prompt: REQUIRED[0], journeyRole: 'required', journeyStage: 'establish' },
        { id: 2, ordinal: 2, prompt: EXPLORE[0], journeyRole: 'explore' },
        { id: 3, ordinal: 3, prompt: REQUIRED[1], journeyRole: 'required', journeyStage: 'prove' },
      ] }), { status: 200 });
    }));
    render(<MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
      <ObservatoryWorkbench />
    </MemoryRouter>);
    await screen.findByRole('button', { name: `Run request: ${REQUIRED[0]}` });
    expect(screen.getByText('Turn 2 · Prove outcome')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Defend the result' })).not.toBeInTheDocument();
    await user.click(screen.getByText('Explore further'));
    expect(screen.getByText('Explore 1')).toBeInTheDocument();
    const optional = screen.getByRole('button', { name: `Run request: ${EXPLORE[0]}` });
    expect(optional).toBeEnabled();
    await user.click(optional);
    await waitFor(() => expect(chatBodies).toHaveLength(1));
    expect(chatBodies[0].message).toBe(EXPLORE[0]);
    expect(screen.getByRole('button', { name: `Run request: ${REQUIRED[1]}` })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: `Run request: ${REQUIRED[0]}` }));
    await waitFor(() => expect(screen.getByRole('button', { name: `Run request: ${REQUIRED[1]}` })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: `Run request: ${REQUIRED[1]}` }));
    await screen.findByRole('heading', { name: 'Defend the result' });
    expect(chatBodies.at(-1)?.conversation_history).toHaveLength(2);
    expect(chatBodies.at(-1)?.message).toBe(REQUIRED[1]);
    expect(screen.getByText(/A finished conversation alone does not complete the lab/)).toBeInTheDocument();
  });
});
