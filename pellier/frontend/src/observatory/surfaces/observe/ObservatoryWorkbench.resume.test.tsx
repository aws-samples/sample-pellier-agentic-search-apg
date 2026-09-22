/**
 * Resume returns a participant to the lab and step they left.
 *
 * The workbench records progress as it is used, and the header offers the way
 * back only when there is somewhere to go: no stored progress, no control.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/chat', () => ({
  sendChatMessageStreaming: vi.fn(),
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
import { mockWorkbenchWidth } from '../../../test-support/workbenchViewport';
import {
  LAB_PROGRESS_KEY,
  readLabProgress,
  writeLabProgress,
} from '../../../shared/labProgress';

function HistoryControls() {
  const location = useLocation();
  const navigate = useNavigate();
  return <>
    <output data-testid="location">{location.pathname}{location.search}</output>
    <button onClick={() => navigate(-1)}>Back</button>
    <button onClick={() => navigate(1)}>Forward</button>
  </>;
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <HistoryControls />
      <ObservatoryWorkbench />
    </MemoryRouter>,
  );
}

describe('Observatory workbench resume', () => {
  beforeEach(() => {
    localStorage.clear();
    // These cases exercise panel navigation at a narrow viewport.
    mockWorkbenchWidth(900);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ persona: 'marco', scenarios: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
  });

  it('records the lab and step the participant is on', async () => {
    const user = userEvent.setup();
    renderAt('/observatory/workbench?lab=retrieval-acceptance');

    await waitFor(() =>
      expect(readLabProgress()).toMatchObject({
        lab: 'retrieval-acceptance',
        step: 'run',
      }),
    );

    await user.click(screen.getByRole('button', { name: /Reconcile answer/ }));
    await waitFor(() =>
      expect(readLabProgress()?.step).toBe('reconcile'),
    );
    expect(readLabProgress()?.nextAction).toBeTruthy();
  });

  it('offers no Resume control when nothing has been recorded', () => {
    renderAt('/observatory/workbench?lab=grounded-inventory');
    expect(screen.queryByRole('link', { name: /^Resume/ })).not.toBeInTheDocument();
  });

  it('links back to the stored lab and step', async () => {
    writeLabProgress({
      lab: 'managed-agent-path',
      step: 'inspect',
      nextAction: 'Read the managed rail evidence.',
    });
    renderAt('/observatory/workbench?lab=grounded-inventory');

    const resume = await screen.findByRole('link', { name: /^Resume/ });
    expect(resume).toHaveAttribute(
      'href',
      '/observatory/workbench?lab=managed-agent-path&step=inspect',
    );
    expect(resume).toHaveAccessibleName(
      'Resume Lab 3: Establish the caller, Inspect evidence',
    );
    expect(localStorage.getItem(LAB_PROGRESS_KEY)).toBeTruthy();
  });

  it('opens on the step named in the URL', async () => {
    renderAt('/observatory/workbench?lab=grounded-inventory&step=reconcile');

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Reconcile answer/ }),
      ).toHaveAttribute('aria-current', 'step'),
    );
  });

  it('resumes a different step even when the page originally opened on the saved URL', async () => {
    writeLabProgress({
      lab: 'grounded-inventory', step: 'inspect', nextAction: 'Read the evidence.',
    });
    renderAt('/observatory/workbench?lab=grounded-inventory&step=inspect');
    expect(screen.queryByRole('link', { name: /^Resume/ })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'Reconcile answer' }));
    expect(screen.getByTestId('location')).toHaveTextContent('step=reconcile');
    await userEvent.click(screen.getByRole('link', { name: /^Resume/ }));

    expect(screen.getByRole('button', { name: 'Inspect evidence' })).toHaveAttribute('aria-current', 'step');
    expect(screen.getByTestId('location')).toHaveTextContent('step=inspect');
    expect(screen.queryByRole('link', { name: /^Resume/ })).toBeNull();
  });

  it('keeps focus steps in browser history', async () => {
    renderAt('/observatory/workbench?lab=grounded-inventory');
    await userEvent.click(screen.getByRole('button', { name: 'Inspect evidence' }));
    await userEvent.click(screen.getByRole('button', { name: 'Reconcile answer' }));
    await userEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('button', { name: 'Inspect evidence' })).toHaveAttribute('aria-current', 'step');
    await userEvent.click(screen.getByRole('button', { name: 'Forward' }));
    expect(screen.getByRole('button', { name: 'Reconcile answer' })).toHaveAttribute('aria-current', 'step');
  });

  it('does not offer a step-only Resume when a wide viewport already shows every panel', () => {
    mockWorkbenchWidth(1440);
    writeLabProgress({
      lab: 'grounded-inventory', step: 'reconcile', nextAction: 'Read the answer.',
    });
    renderAt('/observatory/workbench?lab=grounded-inventory');
    expect(screen.queryByRole('link', { name: /^Resume/ })).toBeNull();
  });
});
