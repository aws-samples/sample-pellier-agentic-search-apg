/**
 * SessionsList — Sessions list surface for the Atelier Observatory.
 *
 * Displays a paginated list of session ExpCards for the active persona,
 * sorted by most recent first. Each card shows the session hex ID,
 * opening query, elapsed time, agent count, routing pattern badge,
 * and timestamp.
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { AtelierWelcome, EditorialTitle, ExpCard, Eyebrow } from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { Session } from '../../types';

/* -----------------------------------------------------------------------
 * Sort helper — exported for property-based testing (Property 1)
 * ----------------------------------------------------------------------- */

/**
 * Sort sessions by timestamp descending (most recent first).
 * Returns a new array; does not mutate the input.
 */
export function sortSessionsByRecency(sessions: Session[]): Session[] {
  return [...sessions].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
}

/* -----------------------------------------------------------------------
 * Formatting helpers
 * ----------------------------------------------------------------------- */

/** Format elapsed milliseconds as a human-readable duration (e.g., "4.2s"). */
function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format an ISO timestamp relative to NOW so fixture dates from 2025
 * render as if they happened recently. Computes the offset between
 * the newest fixture date and now, then shifts all dates forward by
 * that offset. This way "today" and "yesterday" labels are always
 * accurate regardless of when the workshop runs.
 */
const FIXTURE_ANCHOR = new Date('2025-01-15T19:42:00Z').getTime();
const NOW_ANCHOR = Date.now();
const OFFSET_MS = NOW_ANCHOR - FIXTURE_ANCHOR;

function formatTimestamp(iso: string): string {
  const shifted = new Date(new Date(iso).getTime() + OFFSET_MS);
  return shifted.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/* -----------------------------------------------------------------------
 * Sub-components
 * ----------------------------------------------------------------------- */

interface SessionCardProps {
  session: Session;
  onClick: () => void;
}

const SessionCard: React.FC<SessionCardProps> = ({ session, onClick }) => (
  <ExpCard onClick={onClick}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Top row: hex ID + timestamp */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: 'var(--at-mono-size)',
            color: 'var(--at-ink-4)',
            letterSpacing: '0.06em',
          }}
        >
          #{session.id}
        </span>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: 'var(--at-mono-size)',
            color: 'var(--at-ink-4)',
          }}
        >
          {formatTimestamp(session.timestamp)}
        </span>
      </div>

      {/* Opening query */}
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '18px',
          lineHeight: 1.35,
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {session.openingQuery}
      </p>

      {/* Metadata row: elapsed, agents, routing pattern */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: 'var(--at-mono-size)',
            color: 'var(--at-ink-1)',
          }}
        >
          {formatElapsed(session.elapsedMs)}
        </span>

        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: 'var(--at-mono-size)',
            color: 'var(--at-ink-1)',
          }}
        >
          {session.agentCount} agent{session.agentCount !== 1 ? 's' : ''}
        </span>

        {/* Routing pattern badge */}
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '2px 8px',
            borderRadius: '4px',
            backgroundColor: 'var(--at-red-soft)',
            color: 'var(--at-red-1)',
            fontFamily: 'var(--at-mono)',
            fontSize: '9px',
            fontWeight: 600,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            lineHeight: 1.4,
            whiteSpace: 'nowrap',
          }}
        >
          {session.routingPattern}
        </span>
      </div>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Empty state
 * ----------------------------------------------------------------------- */

const EmptyState: React.FC = () => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '80px 24px',
      textAlign: 'center',
    }}
  >
    <Eyebrow label="No sessions" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '22px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No sessions have been recorded yet for this persona.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: 'var(--at-body-size)',
        color: 'var(--at-ink-4)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Start a conversation in the Boutique and return here to observe the
      session telemetry.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      padding: '24px 0',
    }}
  >
    {[1, 2, 3].map((i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: '120px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
    ))}
  </div>
);

/* -----------------------------------------------------------------------
 * Error state
 * ----------------------------------------------------------------------- */

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '80px 24px',
      textAlign: 'center',
    }}
  >
    <Eyebrow label="Something went wrong" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the sessions list.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: 'var(--at-mono-size)',
        color: 'var(--at-ink-4)',
        maxWidth: '480px',
        marginTop: '8px',
      }}
    >
      {message}
    </p>
    <button
      onClick={onRetry}
      style={{
        marginTop: '24px',
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
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

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const SessionsList: React.FC = () => {
  const navigate = useNavigate();
  const { data, loading, error, refetch } = useAtelierData<Session[]>({
    key: 'sessions',
  });

  const sorted = data ? sortSessionsByRecency(data) : [];

  return (
    <div style={{ padding: '40px 48px', maxWidth: '960px' }}>
      {/* Welcome band — dismissible editorial intro to the Atelier.
          Shows once per browser session; dismiss sticks via sessionStorage. */}
      <AtelierWelcome />

      <EditorialTitle
        eyebrow="Observe · Sessions"
        title="Sessions"
        summary="Every conversation between a persona and the agentic system, captured and ready for inspection. Select a session to explore its chat thread, telemetry timeline, and curator's brief."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && sorted.length === 0 && <EmptyState />}

      {!loading && !error && sorted.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          {sorted.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              onClick={() => navigate(`/atelier/sessions/${session.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default SessionsList;
