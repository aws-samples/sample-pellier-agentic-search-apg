/**
 * SessionView — Container for session detail tabs (Chat, Telemetry, Brief).
 *
 * Reads `:id` from route params, loads session data via useAtelierData,
 * renders TabNav for tab switching, and passes session data to child
 * tabs via React Router's outlet context.
 *
 * Requirements: 3.1, 20.2
 */

import React from 'react';
import { Outlet, useParams, useNavigate, useLocation } from 'react-router-dom';
import { TabNav, Eyebrow } from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { SessionDetail } from '../../types';

/** Context shape passed to child tabs via useOutletContext. */
export interface SessionOutletContext {
  session: SessionDetail;
}

const SESSION_TABS = [
  { id: 'chat', label: 'i. Chat' },
  { id: 'telemetry', label: 'ii. Telemetry' },
  { id: 'brief', label: 'iii. Brief' },
];

const SessionView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  // Derive active tab from the current URL path segment
  const pathSegments = location.pathname.split('/');
  const lastSegment = pathSegments[pathSegments.length - 1];
  const activeTab = SESSION_TABS.some((t) => t.id === lastSegment)
    ? lastSegment
    : 'chat';

  // Load session detail from fixture keyed by session ID
  const { data: session, loading, error, refetch } = useAtelierData<SessionDetail>({
    key: `session-${id?.toLowerCase()}`,
  });

  const handleTabChange = (tabId: string) => {
    navigate(`/atelier/sessions/${id}/${tabId}`);
  };

  /* Loading state */
  if (loading) {
    return (
      <div style={{ padding: '40px 48px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '24px',
          }}
        >
          <Eyebrow label={`Session #${id}`} variant="muted" />
        </div>
        <div
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '48px',
            width: '320px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
            marginBottom: '24px',
          }}
        />
        <div
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '400px',
            opacity: 0.4,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      </div>
    );
  }

  /* Error state */
  if (error) {
    return (
      <div
        style={{
          padding: '80px 48px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
        }}
      >
        <Eyebrow label="Something went wrong" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '24px',
            lineHeight: 1.35,
            color: 'var(--at-ink-1)',
            maxWidth: '420px',
            marginTop: '16px',
          }}
        >
          We couldn't load session #{id}.
        </p>
        <p
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-4)',
            maxWidth: '480px',
            marginTop: '8px',
          }}
        >
          {error}
        </p>
        <button
          onClick={refetch}
          style={{
            marginTop: '24px',
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            fontWeight: 500,
            color: 'var(--at-cream-1)',
            backgroundColor: 'var(--at-ink-1)',
            border: 'none',
            borderRadius: '8px',
            padding: '10px 24px',
            cursor: 'pointer',
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  /* No data */
  if (!session) {
    return (
      <div
        style={{
          padding: '80px 48px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
        }}
      >
        <Eyebrow label="Session not found" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '24px',
            lineHeight: 1.35,
            color: 'var(--at-ink-1)',
            maxWidth: '420px',
            marginTop: '16px',
          }}
        >
          No session data found for #{id}.
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 48px' }}>
      {/* Session header */}
      <div style={{ marginBottom: '20px' }}>
        <Eyebrow label={`Session #${session.id} · ${session.routingPattern}`} />
        <h2
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '28px',
            fontWeight: 400,
            lineHeight: 1.2,
            color: 'var(--at-ink-1)',
            margin: '8px 0 0 0',
          }}
        >
          {session.openingQuery}
        </h2>
      </div>

      {/* Tab navigation */}
      <TabNav
        tabs={SESSION_TABS}
        activeTab={activeTab}
        onTabChange={handleTabChange}
      />

      {/* Tab content — child routes receive session via outlet context */}
      <div style={{ marginTop: '24px' }}>
        <Outlet context={{ session } satisfies SessionOutletContext} />
      </div>
    </div>
  );
};

export default SessionView;
