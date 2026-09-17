import { afterEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
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
  it('identifies a new mechanism query separately from constrained receipt proof', () => {
    render(<MemoryRouter><ReferenceBrief id="search" /></MemoryRouter>);
    expect(screen.getByText(/does not replay a shopper turn/)).toBeVisible();
    expect(screen.getByText(/persist a retrieval receipt/)).toBeVisible();
  });
});
