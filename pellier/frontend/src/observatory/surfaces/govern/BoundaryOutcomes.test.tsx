import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import BoundaryOutcomes, { type BoundaryPayload } from './BoundaryOutcomes';

let state: { data: BoundaryPayload | null; loading: boolean; error: string | null; errorStatus?: number };
vi.mock('../../hooks/useObservatoryData', () => ({ useObservatoryData: () => ({ ...state, refetch: vi.fn() }) }));
beforeEach(() => { state = { data: null, loading: false, error: null }; });

describe('Lab 4 boundary outcomes', () => {
  it('teaches all five outcomes without manufacturing observed evidence', () => {
    render(<MemoryRouter><BoundaryOutcomes /></MemoryRouter>);
    expect(screen.getAllByText('Not yet proved')).toHaveLength(5);
    expect(screen.getByText(/No five-outcome run is recorded/)).toBeInTheDocument();
    expect(screen.queryByText('All five outcomes and controls held.')).not.toBeInTheDocument();
  });
  it('distinguishes unavailable evidence from a run with no rows', () => {
    state.error = 'unavailable';
    state.errorStatus = 503;
    render(<MemoryRouter><BoundaryOutcomes /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent('No outcome can be established');
    expect(screen.queryByText(/No five-outcome run is recorded/)).not.toBeInTheDocument();
  });
  it('keeps the operator boundary explicit', () => {
    state.error = 'forbidden'; state.errorStatus = 403;
    render(<MemoryRouter><BoundaryOutcomes /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent('Operator account');
    expect(screen.getByRole('link', { name: 'Sign in to inspect the five outcomes' })).toHaveAttribute('href', '/signin?returnTo=%2Fobservatory%2Fgovern%2Fverification');
  });
  it('shows a suppressed response beside execution and a committed effect', () => {
    state.data = { source: 'CLI observations + keyed Aurora snapshots', runs: [{
      runId: 'run-one', observedAt: '2026-09-17T12:00:00Z', complete: false,
      outcomes: { output_suppressed: true }, attempts: [{
        id: 1, case: 'suppressed-output', operationKey: 'credit-key', invocationId: 'invoke-one',
        tool: 'issue_credit', principal: 'operator', observedAt: '2026-09-17T12:00:00Z',
        outcome: 'output_suppressed', control: 'Managed output Guardrail', toolExecuted: true, dataChanged: true,
        authentication: 'VERIFIED', authorization: 'ALLOW', output: 'SUPPRESSED', contradiction: null,
        database: { executionRows: 1, writeRows: 1, committedRows: 1, domainRows: 1, ledgerRows: 0 },
      }],
    }] };
    render(<MemoryRouter><BoundaryOutcomes /></MemoryRouter>);
    const row = screen.getByRole('row', { name: /suppressed-output/ });
    expect(within(row).getAllByText('Yes')).toHaveLength(2);
    expect(within(row).getByText('Suppressed')).toBeInTheDocument();
    expect(screen.getByText(/Suppression is not rollback/)).toBeInTheDocument();
    expect(screen.getByText('This proof is incomplete.')).toBeInTheDocument();
  });
  it('preserves unknown execution and data state after an incomplete read', () => {
    state.data = { source: 'observations', runs: [{ runId: 'run', observedAt: '2026-09-17T12:00:00Z', complete: false,
      outcomes: {}, attempts: [{ id: 2, case: 'interrupted', operationKey: 'key', invocationId: 'invocation', tool: 'issue_credit',
        principal: 'operator', observedAt: '', outcome: 'inconclusive', control: 'Not established', toolExecuted: null,
        dataChanged: null, authentication: 'VERIFIED', authorization: 'UNKNOWN', output: 'UNKNOWN', database: {}, contradiction: null }],
    }] };
    render(<MemoryRouter><BoundaryOutcomes /></MemoryRouter>);
    expect(screen.getAllByText('Unknown')).toHaveLength(2);
    expect(screen.getByText('? / ? / ? / ? / ?')).toBeInTheDocument();
  });
});
