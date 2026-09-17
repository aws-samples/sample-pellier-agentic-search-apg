import { afterEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ReferenceBrief, { referenceReturnHref } from './ReferenceBrief';
import { writeLabProgress } from '../../shared/labProgress';

afterEach(() => localStorage.clear());
it('returns to the saved lab and step, regardless of which reference was opened', () => {
  writeLabProgress({ lab: 'managed-agent-path', step: 'reconcile', nextAction: '' });
  render(<MemoryRouter><ReferenceBrief id="search" /></MemoryRouter>);
  expect(screen.getByRole('link', { name: 'Return to Lab 3 in Workbench' })).toHaveAttribute('href', '/observatory/workbench?lab=managed-agent-path&step=reconcile');
  expect(referenceReturnHref()).toBe('/observatory/workbench?lab=managed-agent-path&step=reconcile#resources');
});
it('defaults to the reference lab when there is no saved place', () => {
  render(<MemoryRouter><ReferenceBrief id="memory" /></MemoryRouter>);
  expect(screen.getByRole('link', { name: 'Return to Lab 3 in Workbench' })).toHaveAttribute('href', '/observatory/workbench?lab=managed-agent-path');
  expect(referenceReturnHref()).toBe('/observatory#resources');
});
describe('Evidence boundaries', () => {
  it('discloses technical reasoning without presenting it as a recorded result', async () => {
    render(<MemoryRouter><ReferenceBrief id="search" /></MemoryRouter>);
    const example = screen.getByText(/RRF combines ranks rather than incomparable raw scores/);
    expect(example).not.toBeVisible();
    await userEvent.click(screen.getByText('Reason through failure cases'));
    expect(example).toBeVisible();
    expect(screen.getByText(/not results observed in this deployment/)).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Reranking never returns the expected product.' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Return to Lab 2 in Workbench' })).toBeVisible();
  });
  it('identifies a new mechanism query separately from constrained receipt proof', () => {
    render(<MemoryRouter><ReferenceBrief id="search" /></MemoryRouter>);
    expect(screen.getByText(/does not replay a shopper turn/)).toBeVisible();
    expect(screen.getByText(/persist a retrieval receipt/)).toBeVisible();
  });
});
