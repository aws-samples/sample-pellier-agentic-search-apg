/**
 * SessionView — Container for session detail tabs (Chat, Telemetry, Brief).
 *
 * Reads `:id` from route params, loads session data via useObservatoryData,
 * renders TabNav for tab switching, and passes session data to child
 * tabs via React Router's outlet context.
 *
 * Requirements: 3.1, 20.2
 */

import React, { useEffect, useState } from 'react';
import {
  Link,
  Outlet,
  useParams,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import { ArrowLeft, RotateCcw } from 'lucide-react';
import { TabNav, Eyebrow } from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import type { SessionDetail } from '../../types';
import { usePersona } from '../../../contexts/PersonaContext';

/** Context shape passed to child tabs via useOutletContext. */
export interface SessionOutletContext {
  session: SessionDetail;
  replayNonce: number;
}

const SESSION_TABS = [
  { id: 'chat', label: 'Replay' },
  { id: 'telemetry', label: 'Evidence' },
  { id: 'brief', label: 'Brief' },
];

function formatElapsed(elapsedMs: number): string {
  if (elapsedMs < 1000) return `${elapsedMs}ms`;
  if (elapsedMs < 60_000) return `${(elapsedMs / 1000).toFixed(1)}s`;
  const minutes = Math.floor(elapsedMs / 60_000);
  const seconds = Math.round((elapsedMs % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

const SessionView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { persona } = usePersona();
  const [replayNonce, setReplayNonce] = useState(0);

  // Derive active tab from the current URL path segment
  const pathSegments = location.pathname.split('/');
  const lastSegment = pathSegments[pathSegments.length - 1];
  const activeTab = SESSION_TABS.some((t) => t.id === lastSegment)
    ? lastSegment
    : 'chat';

  // Load session detail from fixture keyed by session ID
  const { data: session, loading, error, errorStatus, refetch } = useObservatoryData<SessionDetail>({
    key: `session-${id?.toLowerCase()}`,
  });
  // `:id` is a raw route param -- a stale bookmark or a typo both 404. That
  // is "this session does not exist", not "the evidence service is down",
  // so it renders the dedicated not-found state below (no "Try again": a
  // 404 never resolves by retrying the same id) instead of falling into
  // the generic error branch, which used to make the not-found state
  // below unreachable.
  const notFound = errorStatus === 404;

  // Each persona has their own history — viewing another persona's session
  // while signed in as someone else creates a confusing split screen
  // (TopBar pill says "Marco", body shows Theo's chat). Send the user
  // back to the sessions list so they can pick from their own history.
  useEffect(() => {
    if (!persona || !session) return;
    if (session.personaId !== persona.id) {
      navigate('/observatory/sessions', { replace: true });
    }
  }, [persona, session, navigate]);

  const handleTabChange = (tabId: string) => {
    navigate(`/observatory/sessions/${id}/${tabId}`);
  };

  const handleReplay = () => {
    setReplayNonce((current) => current + 1);
    if (activeTab !== 'chat') {
      navigate(`/observatory/sessions/${id}/chat`);
    }
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
            background: 'var(--obs-cream-2)',
            borderRadius: 'var(--obs-card-radius)',
            height: '48px',
            width: '320px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
            marginBottom: '24px',
          }}
        />
        <div
          style={{
            background: 'var(--obs-cream-2)',
            borderRadius: 'var(--obs-card-radius)',
            height: '400px',
            opacity: 0.4,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      </div>
    );
  }

  /* Error state (excludes 404 -- handled as "not found" below) */
  if (error && !notFound) {
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
            fontFamily: 'var(--obs-sans)',
            fontSize: '24px',
            lineHeight: 1.35,
            color: 'var(--obs-ink-1)',
            maxWidth: '420px',
            marginTop: '16px',
          }}
        >
          We couldn't load session #{id}.
        </p>
        <p
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            color: 'var(--obs-ink-4)',
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
            fontFamily: 'var(--obs-sans)',
            fontSize: '15px',
            fontWeight: 500,
            color: 'var(--obs-cream-1)',
            backgroundColor: 'var(--obs-ink-1)',
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

  /* No data (404 "session does not exist", or a 200 with an empty body) */
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
            fontFamily: 'var(--obs-sans)',
            fontSize: '24px',
            lineHeight: 1.35,
            color: 'var(--obs-ink-1)',
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
    <main className="observatory-reading-page observatory-session-page">
      <div className="observatory-session-actions">
        <Link
          to="/observatory/sessions"
          className="observatory-reference-return"
        >
          <ArrowLeft aria-hidden="true" size={16} strokeWidth={1.8} />
          Sessions &amp; traces
        </Link>
        <button
          type="button"
          className="observatory-session-replay-button"
          onClick={handleReplay}
        >
          <RotateCcw aria-hidden="true" size={16} strokeWidth={1.8} />
          Replay evidence
        </button>
      </div>

      <header className="observatory-session-header">
        <div className="observatory-session-heading">
          <Eyebrow label={`Recorded session · ${session.routingPattern}`} />
          <h1>{session.openingQuery}</h1>
          <p>
            Reconstruct this session from its stored conversation, telemetry,
            and durable Aurora evidence.
          </p>
        </div>
        <dl className="observatory-session-facts">
          <div>
            <dt>Status</dt>
            <dd>{session.status === 'active' ? 'Active' : 'Recorded'}</dd>
          </div>
          <div>
            <dt>Elapsed</dt>
            <dd>{formatElapsed(session.elapsedMs)}</dd>
          </div>
          <div>
            <dt>Agents</dt>
            <dd>{session.agentCount}</dd>
          </div>
        </dl>
      </header>

      {/* Tab navigation */}
      <TabNav
        tabs={SESSION_TABS}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        className="observatory-session-tabs"
      />

      {/* Tab content — child routes receive session via outlet context */}
      <div className="observatory-session-content">
        <Outlet
          context={{ session, replayNonce } satisfies SessionOutletContext}
        />
      </div>
    </main>
  );
};

export default SessionView;
