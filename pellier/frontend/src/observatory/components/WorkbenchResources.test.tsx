import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import WorkbenchResources from './WorkbenchResources';

describe('WorkbenchResources', () => {
  it('organizes optional depth by participant question', () => {
    render(
      <MemoryRouter>
        <WorkbenchResources />
      </MemoryRouter>,
    );

    for (const question of [
      'What ran?',
      'Why was it allowed?',
      'What reached PostgreSQL?',
      'How does this operate?',
    ]) {
      expect(
        screen.getByRole('region', { name: question }),
      ).toBeInTheDocument();
    }

    expect(screen.getByText(/psql/)).toBeInTheDocument();
    expect(screen.getByText(/AgentCore CLI/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Sessions & traces/ }))
      .toHaveAttribute('href', '/observatory/sessions');
    expect(screen.getByRole('link', { name: /Govern: identity, access & policy/ }))
      .toHaveAttribute('href', '/observatory/govern');
  });

  it('keeps all nine destinations and their source details available', async () => {
    const user = userEvent.setup();
    const { container } = render(<MemoryRouter><WorkbenchResources /></MemoryRouter>);
    expect(container.querySelectorAll('.workbench-resource-view a')).toHaveLength(9);
    expect(screen.getByText('9 reference views')).toBeVisible();
    const sources = container.querySelector('.workbench-source-disclosure')!;
    expect(sources).not.toHaveAttribute('open');
    await user.click(sources.querySelector('summary')!);
    expect(sources).toHaveAttribute('open');
    expect(screen.getByText('governed_turn_receipts')).toBeVisible();
  });

  it('sets a queryable source in mono and a described source in prose', () => {
    const { container } = render(
      <MemoryRouter>
        <WorkbenchResources />
      </MemoryRouter>,
    );

    const register = (text: string) =>
      Array.from(container.querySelectorAll('.workbench-resource-source'))
        .find((node) => node.textContent === text)
        ?.getAttribute('data-register');

    // Mono means "paste this into psql". A relation, with or without a
    // qualifier, qualifies; a source described in words does not.
    expect(register('governed_turn_receipts')).toBe('identifier');
    expect(register('governed_receipts (Cedar)')).toBe('identifier');
    expect(register('measured on Aurora at run time')).toBe('prose');
    expect(register('MCP schemas')).toBe('prose');

    const monoSource = Array.from(
      container.querySelectorAll('.workbench-resource-source'),
    ).find((node) => node.textContent === 'tool_audit');
    expect(monoSource?.querySelector('code')).not.toBeNull();
  });

  it('keeps every source string whole when it splits the column into tokens', () => {
    const { container } = render(
      <MemoryRouter>
        <WorkbenchResources />
      </MemoryRouter>,
    );

    // The column is presented as tokens, but no character of the data may be
    // dropped in the process.
    const cells = Array.from(
      container.querySelectorAll('.workbench-resource-sources'),
    ).map((node) =>
      Array.from(node.querySelectorAll('.workbench-resource-source'))
        .map((token) => token.textContent)
        .join(', '),
    );

    expect(cells).toEqual([
      'governed_turn_receipts, evidence_ledger_event_refs',
      'policy, tool_audit and write receipts per lab',
      'approvals, replacements, replacement_outbox, replacement_events',
      'governed_receipts (Cedar), tool_audit',
      'tool registry, MCP schemas',
      'retrieval_receipts, live EXPLAIN',
      'measured on Aurora at run time',
      'source tree, deploy templates',
      'evaluation scorecards, golden journeys',
    ]);
  });

  it('keeps the workbench index out of the initial evidence viewport until requested', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <WorkbenchResources collapsible defaultExpanded={false} />
      </MemoryRouter>,
    );

    const disclosure = screen.getByRole('button', {
      name: /Explore reference views/i,
    });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(
      screen.queryByRole('heading', {
        name: 'Telemetry & system references',
      }),
    ).not.toBeInTheDocument();

    await user.click(disclosure);

    expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    expect(
      screen.getByRole('heading', {
        name: 'Telemetry & system references',
      }),
    ).toBeVisible();
    expect(screen.getByText('What reached PostgreSQL?')).toBeVisible();
  });
});
