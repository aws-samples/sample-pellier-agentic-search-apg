/**
 * Guided runs carry real conversation history.
 *
 * Runs in expert view so all three panels stay mounted: focus mode's stepper
 * deliberately hides the request rail once a run starts, which is its own
 * behaviour and is covered by ObservatoryWorkbench.focus.test.tsx.
 *
 * The three-turn journey advertises "each turn keeps the previous
 * conversation". Until this test existed the workbench sent an empty history
 * on every turn, so turn 3's "without asking me to repeat" prompt was answered
 * by an agent that had never seen turns 1 and 2. This goes through the real
 * chat transport and asserts the request bodies, not a mocked call.
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

let turnCounter = 0;

function streamResponse(): Response {
  turnCounter += 1;
  const lines = [
    `data: ${JSON.stringify({ type: 'turn_start', turn_id: `turn-${turnCounter}` })}`,
    `data: ${JSON.stringify({
      type: 'complete',
      response: {
        response: `Answer ${turnCounter}`,
        products: [],
        rail: 'in-process',
      },
    })}`,
  ];
  return new Response(`${lines.join('\n\n')}\n\n`, { status: 200 });
}

const chatBodies: Array<Record<string, unknown>> = [];

describe('Observatory guided runs send real history', () => {
  beforeEach(() => {
    localStorage.clear();
    mockWorkbenchWidth(1440);
    turnCounter = 0;
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

  it('sends 0, 2, then 4 prior messages and gates each turn on the last', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/observatory/workbench?lab=grounded-inventory']}>
        <ObservatoryWorkbench />
      </MemoryRouter>,
    );

    const turn = (index: number) =>
      screen.getByRole('button', { name: `Inspect: ${PROMPTS[index]}` });

    await screen.findByRole('button', { name: `Inspect: ${PROMPTS[0]}` });
    expect(turn(1)).toBeDisabled();
    expect(turn(2)).toBeDisabled();

    await user.click(turn(0));
    await waitFor(() => expect(turn(1)).toBeEnabled());
    expect(turn(2)).toBeDisabled();

    await user.click(turn(1));
    await waitFor(() => expect(turn(2)).toBeEnabled());

    await user.click(turn(2));
    await waitFor(() => expect(chatBodies).toHaveLength(3));

    const histories = chatBodies.map(
      (body) => body.conversation_history as Array<{ role: string; content: string }>,
    );
    expect(histories.map((history) => history.length)).toEqual([0, 2, 4]);
    expect(histories[2].map((message) => [message.role, message.content])).toEqual([
      ['user', PROMPTS[0]],
      ['assistant', 'Answer 1'],
      ['user', PROMPTS[1]],
      ['assistant', 'Answer 2'],
    ]);
  });
});
