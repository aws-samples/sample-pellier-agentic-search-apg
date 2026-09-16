import { fireEvent, render, screen } from '@testing-library/react';
import {
  MemoryRouter,
  Outlet,
  Route,
  Routes,
} from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionDetail } from '../../types';
import ChatTab from './ChatTab';
import SessionView, { type SessionOutletContext } from './SessionView';

const session: SessionDetail = {
  id: 'session-theo-live',
  personaId: 'theo',
  openingQuery: 'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
  elapsedMs: 6460,
  agentCount: 1,
  routingPattern: 'Storefront Dispatcher',
  timestamp: '2026-09-02T08:00:00.000Z',
  status: 'complete',
  chat: [],
  telemetry: [
    {
      index: 1,
      category: 'owned',
      title: 'get_return_policy',
      description: 'agent invocation recorded in Aurora.',
      status: 'succeeded',
      durationMs: 2188,
      agent: 'agent',
      eventKind: 'tool',
      phase: 'execution',
      provenance: 'aurora-receipt',
    },
    {
      index: 2,
      category: 'owned',
      title: 'initiate_return',
      description: 'governed review handoff recorded in Aurora.',
      status: 'not_enforced',
      durationMs: 4272,
      agent: 'agent',
      eventKind: 'policy',
      phase: 'governance',
      provenance: 'aurora-receipt',
    },
  ],
  evidenceLedger: null,
  brief: {
    folioNumber: 0,
    headline: 'Live session evidence',
    filedTime: '2026-09-02T08:00:00.000Z',
    sections: [],
    products: [],
  },
};

const mocks = vi.hoisted(() => ({
  useObservatoryData: vi.fn(),
}));

vi.mock('../../hooks/useObservatoryData', () => ({
  useObservatoryData: () => mocks.useObservatoryData(),
}));

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: {
      id: 'theo',
      display_name: 'Theo',
    },
  }),
}));

function OutletHarness() {
  return (
    <Outlet
      context={{ session, replayNonce: 0 } satisfies SessionOutletContext}
    />
  );
}

describe('recorded session replay', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation(() => ({
        matches: false,
        media: '(prefers-reduced-motion: reduce)',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    mocks.useObservatoryData.mockReturnValue({
      data: session,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('replays telemetry-only sessions instead of rendering an empty chat rail', () => {
    render(
      <MemoryRouter initialEntries={['/session']}>
        <Routes>
          <Route element={<OutletHarness />}>
            <Route path="/session" element={<ChatTab />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));

    expect(screen.getAllByText('get_return_policy').length).toBeGreaterThan(0);
    expect(screen.getAllByText('initiate_return').length).toBeGreaterThan(0);
    expect(
      screen.getByText('2 recorded evidence events ready to inspect'),
    ).toBeInTheDocument();
    expect(screen.getByText('Storefront agent')).toBeInTheDocument();
    expect(
      screen.getByText('No durable memory event is attached to this replay.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('No routing or tool steps in this thread yet.'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Inactive')).not.toBeInTheDocument();
  });

  it('provides a clear back path and restarts the evidence replay', () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/observatory/sessions/session-theo-live/chat',
        ]}
      >
        <Routes>
          <Route
            path="/observatory/sessions/:id"
            element={<SessionView />}
          >
            <Route path="chat" element={<ChatTab />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const back = screen.getByRole('link', { name: 'Sessions & traces' });
    expect(back).toHaveAttribute('href', '/observatory/sessions');

    fireEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(
      screen.getByText('2 recorded evidence events ready to inspect'),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Replay evidence' }),
    );

    expect(screen.getByText('0 / 2')).toBeInTheDocument();
    expect(screen.queryByText('initiate_return')).not.toBeInTheDocument();
  });
});
