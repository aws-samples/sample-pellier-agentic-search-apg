import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import WorkshopMap from './WorkshopMap';

describe('Observatory workshop map', () => {
  it('uses the exact governed lab sequence and destinations', () => {
    render(
      <MemoryRouter>
        <WorkshopMap />
      </MemoryRouter>,
    );

    expect(screen.getAllByText(/^Lab [1-4]$/).map((node) => node.textContent)).toEqual([
      'Lab 1',
      'Lab 2',
      'Lab 3',
      'Lab 4',
    ]);
    expect(
      screen.getByRole('heading', { name: 'Build a PostgreSQL-Grounded Agent' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        name: 'Build and Measure PostgreSQL Hybrid Retrieval',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        name: 'Deploy and Operate Agents with Amazon Bedrock AgentCore',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Build Governed Agent Actions with Cedar' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Act (I|II|III)$/)).not.toBeInTheDocument();

    expect(screen.getByRole('link', { name: /Open retrieval comparison/i })).toHaveAttribute(
      'href',
      '/observatory/performance',
    );
    expect(screen.getByRole('link', { name: /Open Lab 3 proofs/i })).toHaveAttribute(
      'href',
      '/observatory/proof-board#managed-rail',
    );
    expect(screen.getByRole('link', { name: /Open Cedar policies/i })).toHaveAttribute(
      'href',
      '/observatory/govern/policies',
    );
  });
});
