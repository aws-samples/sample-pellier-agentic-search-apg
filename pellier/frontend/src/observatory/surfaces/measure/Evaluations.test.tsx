import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
vi.mock('../../hooks/useObservatoryData', () => ({ useObservatoryData: () => ({ data: { provenance: 'unavailable', states: {}, scorecards: [] }, loading: false, error: null }) }));
import Evaluations from './Evaluations';
describe('Evaluation design without recorded scorecards', () => {
  it('keeps the technical explanation usable and makes no measurement claim', async () => {
    render(<MemoryRouter><Evaluations /></MemoryRouter>);
    const summary = screen.getByText('Extend the lab checks: evaluation methods and metric definitions');
    expect(summary.closest('details')).not.toHaveAttribute('open');
    await userEvent.click(summary);
    expect(screen.getByText(/Choosing a method or metric here does not run an evaluation/)).toBeVisible();
    expect(screen.getByText(/Configured evaluators and local test definitions are not measured scorecards/)).toBeVisible();
  });
});
