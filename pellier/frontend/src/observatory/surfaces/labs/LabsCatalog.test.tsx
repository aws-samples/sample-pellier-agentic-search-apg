import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LAB_EXERCISES } from '../../labs/labCatalog';
import LabsCatalog from './LabsCatalog';

describe('LabsCatalog', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the four evidence-first labs without claiming completion', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: 'attention',
            managedReceipt: { present: false },
            cards: [],
          }),
          { status: 200 },
        ),
      ),
    );

    render(
      <MemoryRouter>
        <LabsCatalog />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Four technical labs')).toBeInTheDocument();
    expect(
      screen
        .getAllByRole('link')
        .filter((link) => link.classList.contains('labs-catalog-card-open')),
    ).toHaveLength(4);
    expect(screen.getByRole('link', { name: 'Start Lab 1' })).toHaveAttribute('href', '/observatory/workbench?lab=grounded-inventory');
    for (const lab of LAB_EXERCISES) {
      expect(screen.getByRole('link', { name: `Open Lab ${Number(lab.number)} in Workbench` })).toHaveAttribute('href', `/observatory/workbench?lab=${lab.id}`);
    }
    expect(screen.queryByText(/workshop complete/i)).not.toBeInTheDocument();
    const disclosure = screen.getByRole('button', { name: 'Explore reference views' });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(disclosure);
    expect(screen.getByRole('heading', { name: 'Telemetry & system references' })).toBeVisible();
    expect(screen.getByText('Which candidates survive, and why?')).toBeInTheDocument();

    expect(
      document.querySelectorAll('.labs-catalog-contact-sheet figure'),
    ).toHaveLength(4);
    expect(
      document.querySelector('.labs-catalog-hero > picture'),
    ).not.toBeInTheDocument();
  });

  it('anchors each lab to its named persona and portrait', () => {
    expect(
      LAB_EXERCISES.map(({ anchorName, image }) => ({ anchorName, image })),
    ).toEqual([
      {
        anchorName: 'Marco',
        image: '/assets/personas/marco-720.webp',
      },
      {
        anchorName: 'Anna',
        image: '/assets/personas/anna-720.webp',
      },
      {
        anchorName: 'Theo',
        image: '/assets/personas/theo-720.webp',
      },
      {
        anchorName: 'Jessica',
        image: '/assets/personas/jessica-720.webp',
      },
    ]);

    const managed = LAB_EXERCISES.find(
      (exercise) => exercise.id === 'managed-agent-path',
    );
    const governed = LAB_EXERCISES.find(
      (exercise) => exercise.id === 'fail-closed-policy',
    );

    expect(managed?.objective).toContain('Theo');
    expect(managed?.objective).toContain('new conversation');
    expect(managed?.participantTodo).toContain('Task 3B: deploy, challenge scope');
    expect(managed?.command).toContain(
      'Hand-thrown ceramics for a slower morning routine',
    );

    expect(governed).toMatchObject({
      image: '/assets/personas/jessica-720.webp',
      imageWidth: 720,
      imageHeight: 900,
    });
    expect(governed?.objective).toContain('five outcomes');
    expect(governed?.participantTodo).toContain('distinguish five outcomes');
    expect(governed?.participantTodo).toContain('test RLS and keyed evidence');
    expect(governed?.participantTodo).toContain('human-reviewed return');
    expect(governed?.command).toContain('scripts/prove_governance_outcomes.py');
    expect(governed?.evidenceHref).toBe('/observatory/govern/verification');
    expect(governed?.evidenceAssertion).toContain('confirmed terms and execution');
    expect(governed?.primaryAction).toEqual({
      label: 'Open Jessica in Operator',
      to: '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title',
    });
  });
});
