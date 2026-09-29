import { afterEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ReferenceBrief from './ReferenceBrief';
import { writeLabProgress } from '../../shared/labProgress';

afterEach(() => localStorage.clear());
it('leaves the way back to a lab reference to the lab strip', () => {
  render(<MemoryRouter><ReferenceBrief id="memory" /></MemoryRouter>);
  expect(screen.queryByRole('link', { name: /Return to Lab/ })).not.toBeInTheDocument();
});
it('returns an extension to the saved lab and step, which no strip offers', () => {
  writeLabProgress({ lab: 'managed-agent-path', step: 'reconcile', nextAction: '' });
  render(<MemoryRouter><ReferenceBrief id="evaluations" /></MemoryRouter>);
  expect(screen.getByRole('link', { name: 'Return to Lab 3 in Workbench' })).toHaveAttribute('href', '/observatory/workbench?lab=managed-agent-path&step=reconcile');
});
it('returns an extension to its own lab when there is no saved place', () => {
  render(<MemoryRouter><ReferenceBrief id="evaluations" /></MemoryRouter>);
  expect(screen.getByRole('link', { name: 'Return to Lab 2 in Workbench' })).toHaveAttribute('href', '/observatory/workbench?lab=retrieval-acceptance');
});
describe('Evidence boundaries', () => {
  it('discloses technical reasoning without presenting it as a recorded result', async () => {
    render(<MemoryRouter><ReferenceBrief id="search" /></MemoryRouter>);
    const example = screen.getByText(/RRF combines ranks rather than incomparable raw scores/);
    expect(example).not.toBeVisible();
    await userEvent.click(screen.getByText('Failure cases'));
    expect(example).toBeVisible();
    expect(screen.getByText(/not results observed in this deployment/)).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Reranking never returns the expected product.' })).toBeVisible();
  });
  it('identifies a new mechanism query separately from constrained receipt proof', () => {
    render(<MemoryRouter><ReferenceBrief id="search" /></MemoryRouter>);
    expect(screen.getByText(/does not replay a shopper turn/)).toBeVisible();
    expect(screen.getByText(/persist a retrieval receipt/)).toBeVisible();
  });
});
describe('Brief layout', () => {
  it('keeps the question and evidence boundary open and the rest on demand', () => {
    render(<MemoryRouter><ReferenceBrief id="tools" /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Is this tool implemented, published, visible, and permitted?' })).toBeVisible();
    expect(screen.getByText(/is not the caller-visible Gateway catalogue/)).toBeVisible();
    expect(screen.getByText(/Inspect check_inventory’s input contract/)).not.toBeVisible();
    for (const label of ['How to inspect', 'Failure cases', 'Implementation']) expect(screen.getByText(label).closest('details')).not.toHaveAttribute('open');
  });
});
