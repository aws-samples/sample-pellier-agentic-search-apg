import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import WorkbenchResources from './WorkbenchResources';

function renderIndex(props = {}) {
  return render(<MemoryRouter><WorkbenchResources {...props} /></MemoryRouter>);
}

describe('Lab reference directory', () => {
  it('keeps the four lab questions ahead of extensions and points at governed source', () => {
    renderIndex();
    for (const number of [1, 2, 3, 4]) expect(screen.getByRole('region', { name: new RegExp(`Lab ${number} ·`) })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Memory' })).toHaveAttribute('href', '/observatory/memory');
    expect(screen.getByRole('link', { name: 'Governed workshop source' })).toHaveAttribute('href', 'https://github.com/aws-samples/sample-pellier-agentic-search-apg/tree/governed');
    expect(screen.getByRole('link', { name: 'Replacement recovery' })).not.toBeVisible();
  });
  it('keeps only the after-the-labs extensions on the Workbench', async () => {
    // Each lab's own views are in the lab strip; repeating them here would be
    // a second navigation for the same destinations.
    renderIndex({ scope: 'extensions' });
    expect(screen.queryByRole('link', { name: 'Search pipeline' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Telemetry & system references' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('After the labs: evaluation and recovery'));
    for (const label of ['Evaluations', 'Production patterns', 'Replacement recovery']) expect(screen.getByRole('link', { name: label })).toBeVisible();
  });
  it('discloses advanced material explicitly after the labs', async () => {
    renderIndex();
    await userEvent.click(screen.getByText('After the labs: evaluation and recovery'));
    for (const label of ['Evaluations', 'Production patterns', 'Replacement recovery']) expect(screen.getByRole('link', { name: label })).toBeVisible();
    expect(screen.getByText(/outside the four required lab builds/)).toBeVisible();
  });
  it('keeps references closed on the workbench until requested', async () => {
    renderIndex({ collapsible: true, defaultExpanded: false });
    const button = screen.getByRole('button', { name: 'Explore reference views' });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(within(screen.getByRole('region', { name: 'Reference views' })).getByRole('heading', { name: 'Telemetry & system references' })).toBeVisible();
  });
  it('opens a directly linked resource hash even when collapsed by default', () => {
    render(<MemoryRouter initialEntries={['/observatory#resources']}><WorkbenchResources collapsible defaultExpanded={false} /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Telemetry & system references' })).toBeVisible();
  });
});
