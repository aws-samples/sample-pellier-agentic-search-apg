import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Govern from './Govern';
import type { PolicySnapshot } from './governanceTypes';

vi.mock('../../../contexts/AuthContext', () => ({ useOptionalAuth: () => null }));

const snapshot: PolicySnapshot = {
  observedAt: '2026-09-16T12:00:00Z', source: 'managed-engine', engineId: 'engine',
  gatewayMode: 'ENFORCE', gatewayState: 'observed', attachmentMatches: true, complete: true,
  labPolicyState: 'not-observed', checkout: { revision: 'a'.repeat(40), modified: false, source: 'checkout' },
  policies: [{ id: 'p1', name: 'catalogue_reads', description: 'Read catalogue', mode: 'ACTIVE', cedar: 'permit(principal, action, resource);', definitionHash: 'b'.repeat(64), definitionState: 'observed' }],
};
let policyData: PolicySnapshot;
let fetchMock: ReturnType<typeof vi.fn>;

function mount(path = '/observatory/govern') {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/observatory/govern" element={<Govern />} />
    <Route path="/observatory/govern/:section" element={<Govern />} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  policyData = structuredClone(snapshot);
  fetchMock = vi.fn(async (url: string) => ({
    ok: true, status: 200,
    json: async () => url.endsWith('/policies') ? policyData : { state: 'anonymous', caller: null, observedAt: '2026-09-16T12:00:00Z' },
  }));
  vi.stubGlobal('fetch', fetchMock);
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.unstubAllGlobals());

describe('Govern reference', () => {
  it('navigates all topics and updates focus without starting a tool call', async () => {
    mount();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Governed agent access');
    fireEvent.click(screen.getAllByRole('link', { name: 'Authentication & JWTs' })[0]);
    await screen.findByText('No authenticated caller');
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus();
    expect(screen.getByRole('link', { name: 'Sign in to inspect your identity' })).toHaveAttribute('href', expect.stringContaining('returnTo='));
    fireEvent.click(screen.getAllByRole('link', { name: 'Agent Access' })[0]);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Agent Access');
    expect(fetchMock.mock.calls.every(call => !call[1] || call[1]?.method === 'GET')).toBe(true);
  });

  it('shows deployed modes, opens Cedar, and filters without a new AWS read', async () => {
    mount('/observatory/govern/policies');
    await screen.findByText('1 observed');
    expect(within(screen.getByRole('region', { name: 'Observed Gateway and policy configuration' })).getByText('ENFORCE')).toBeInTheDocument();
    const summary = screen.getByText('catalogue_reads').closest('summary')!;
    fireEvent.click(summary);
    expect(screen.getByText('permit(principal, action, resource);')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'no-matching-action' } });
    expect(screen.getByRole('status')).toHaveTextContent('0 matching policies');
    expect(screen.queryByText('catalogue_reads')).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('reports LOG_ONLY and a mismatched attachment without claiming denial', async () => {
    policyData.gatewayMode = 'LOG_ONLY';
    policyData.attachmentMatches = false;
    mount('/observatory/govern/policies');
    expect(await screen.findByText('Different engine')).toBeInTheDocument();
    expect(screen.getByText(/Gateway is observing, not enforcing/)).toBeInTheDocument();
    expect(screen.getByText(/cannot establish the Gateway’s effective protection/)).toBeInTheDocument();
  });

  it('does not turn a failed read into an empty policy set', async () => {
    policyData.source = 'unavailable';
    policyData.policies = [];
    policyData.complete = false;
    policyData.labPolicyState = 'unknown';
    mount('/observatory/govern/policies');
    expect(await screen.findByText('Deployment state unknown')).toBeInTheDocument();
    expect(screen.getByText(/A failed read is not an empty engine/)).toBeInTheDocument();
    expect(screen.queryByText('The managed engine returned an empty policy list.')).not.toBeInTheDocument();
  });

  it('does not treat a policy name as exercise completion', async () => {
    policyData.labPolicyState = 'present';
    mount('/observatory/govern/policies');
    await screen.findByText('Policy name observed');
    expect(screen.getByText(/A matching name does not establish the rule’s correctness/)).toBeInTheDocument();
    expect(screen.queryByText('PASS')).not.toBeInTheDocument();
  });

  it('clears the old snapshot during refresh and exposes a failed refresh', async () => {
    mount('/observatory/govern/policies');
    const observation = screen.getByRole('region', { name: 'Observed Gateway and policy configuration' });
    await within(observation).findByText('ENFORCE');
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh policies' }));
    await screen.findByText(/The policy snapshot is unavailable/);
    expect(within(observation).queryByText('ENFORCE')).not.toBeInTheDocument();
  });

  it('distinguishes an invalid identity from a policy decision', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401 });
    mount('/observatory/govern/authentication');
    await screen.findByText(/No Cedar decision was made by this identity check/);
    expect(screen.queryByText('Validated access token')).not.toBeInTheDocument();
  });

  it('keeps Operator-only evidence access explicit', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 403 });
    mount('/observatory/govern/verification');
    await screen.findByText(/Shopper sign-in alone does not grant access/);
    expect(screen.queryByText(/profile belongs to a different account/)).not.toBeInTheDocument();
  });

  it('copies the documented proof command without executing it', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401 });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    mount('/observatory/govern/verification');
    fireEvent.click(screen.getByRole('button', { name: 'Copy Lab 4 identity and Aurora proof' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('python3 scripts/prove_identity_boundary.py'));
    expect(screen.getByText(/performs real test return attempts/)).toBeInTheDocument();
  });

  it('offers a recovery link for unknown reference paths', () => {
    mount('/observatory/govern/unknown');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Topic not found');
    expect(screen.getByRole('link', { name: 'Return to Govern' })).toHaveAttribute('href', '/observatory/govern');
  });
});
