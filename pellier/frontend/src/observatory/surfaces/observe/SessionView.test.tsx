/**
 * SessionView — a 404 renders "not found", never the generic retry error.
 *
 * `:id` is a raw route param (a stale bookmark, a typo, an id from another
 * account). Before this fix, `useObservatoryData` collapsed every non-401/403
 * failure -- including a real 404 from the backend -- into the same
 * "temporarily unavailable, try again" message and error branch, which
 * fired before the component ever reached its own "Session not found"
 * render below. That dedicated not-found state existed in the source but
 * was dead code: a 404 always threw, so `error` was always truthy first.
 * VOICE.md and PRODUCT.md both require unavailable/not-found/invalid to
 * stay distinct failure states rather than collapsing into one.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockUseObservatoryData = vi.fn();
vi.mock('../../hooks/useObservatoryData', () => ({
  useObservatoryData: (...args: unknown[]) => mockUseObservatoryData(...args),
}));

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({ persona: null }),
}));

import SessionView from './SessionView';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/observatory/sessions/:id" element={<SessionView />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SessionView — failure states stay distinct', () => {
  it('renders the not-found state on a 404, with no retry affordance', () => {
    mockUseObservatoryData.mockReturnValue({
      data: null,
      loading: false,
      error: 'This evidence could not be found.',
      errorStatus: 404,
      refetch: vi.fn(),
    });

    renderAt('/observatory/sessions/does-not-exist');

    expect(screen.getByText('Session not found')).toBeInTheDocument();
    expect(
      screen.getByText('No session data found for #does-not-exist.'),
    ).toBeInTheDocument();
    // The generic error copy and its retry button belong to the other
    // branch; a 404 never resolves by retrying the same id.
    expect(screen.queryByText("We couldn't load session #does-not-exist.")).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('renders the generic error state with a retry button on a non-404 failure', () => {
    mockUseObservatoryData.mockReturnValue({
      data: null,
      loading: false,
      error: 'This evidence is temporarily unavailable. Please try again.',
      errorStatus: 503,
      refetch: vi.fn(),
    });

    renderAt('/observatory/sessions/anna-001');

    expect(screen.getByText("We couldn't load session #anna-001.")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.queryByText('Session not found')).not.toBeInTheDocument();
  });

  it('renders the loading skeleton while the request is in flight', () => {
    mockUseObservatoryData.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      errorStatus: null,
      refetch: vi.fn(),
    });

    renderAt('/observatory/sessions/anna-001');

    expect(screen.getByText('Session #anna-001')).toBeInTheDocument();
    expect(screen.queryByText('Session not found')).not.toBeInTheDocument();
  });
});
