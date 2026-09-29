/**
 * SessionsList — Sessions list surface for the Pellier Observatory.
 *
 * Displays a paginated list of session ExpCards for the active persona,
 * sorted by most recent first. Each card shows the session hex ID,
 * opening query, elapsed time, agent count, routing pattern badge,
 * and timestamp.
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow } from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import type { Session } from '../../types';
import { StateBadge } from '../../../shared';
import { usePersona } from '../../../contexts/PersonaContext';
import '../../styles/evidence-depth.css';

export const SESSION_PAGE_SIZE = 8;

/* -----------------------------------------------------------------------
 * Sort helper — exported for property-based testing (Property 1)
 * ----------------------------------------------------------------------- */

/**
 * Put the latest recorded activity first so a participant can find the turn
 * they just completed. The lab collection owns the teaching sequence.
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
  // Sessions span from a sub-second replay to hours of a workshop; one unit
  // per magnitude reads faster than "4229.8s".
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
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

/**
 * One recorded session in two lines: what the shopper asked and how it ended,
 * then its id, time, duration, agents and route. Five stacked rows made each
 * card 174px, so a 13-inch laptop showed one session in its first screen.
 */
const SessionCard: React.FC<SessionCardProps> = ({ session, onClick }) => (
  <ExpCard onClick={onClick}>
    <div className="observatory-session-row">
      <p className="observatory-session-row-query">{session.openingQuery}</p>
      <StateBadge tone={session.status === 'complete' ? 'ok' : session.status === 'failed' || session.status === 'denied-before-execution' ? 'attention' : 'neutral'}>
        {session.status === 'complete' ? 'Completed' : session.status === 'failed' ? 'Failure recorded' : session.status === 'denied-before-execution' ? 'Denied before execution' : session.status === 'active' ? 'In progress' : 'Outcome not recorded'}
      </StateBadge>
      <div className="observatory-session-row-meta">
        <code>#{session.id}</code>
        <span>{formatTimestamp(session.timestamp)}</span>
        <span>{formatElapsed(session.elapsedMs)}</span>
        <span>{session.agentCount} agent{session.agentCount !== 1 ? 's' : ''}</span>
        {session.provenance === 'direct' ? (
          <span className="observatory-session-row-direct">Outside a conversation</span>
        ) : null}
      </div>
      <span className="observatory-session-row-route">{session.routingPattern}</span>
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
        fontFamily: 'var(--obs-sans)',
        fontSize: '22px',
        lineHeight: 1.35,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No sessions have been recorded yet for this persona.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: 'var(--obs-body-size)',
        color: 'var(--obs-ink-4)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Start a conversation in Pellier and return here to observe the
      session telemetry.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div
    role="status"
    aria-label="Loading sessions"
    style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      padding: '24px 0',
    }}
  >
    <span className="sr-only">Loading sessions…</span>
    {[1, 2, 3].map((i) => (
      <div
        key={i}
        aria-hidden="true"
        className="motion-safe:animate-pulse"
        style={{
          background: 'var(--obs-cream-2)',
          borderRadius: 'var(--obs-card-radius)',
          height: '120px',
          opacity: 0.5,
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
  status: number | null;
  onRetry: () => void;
}

const ErrorState: React.FC<ErrorStateProps> = ({ message, status, onRetry }) => (
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
        fontFamily: 'var(--obs-sans)',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the sessions list.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: 'var(--obs-mono-size)',
        color: 'var(--obs-ink-4)',
        maxWidth: '480px',
        marginTop: '8px',
      }}
    >
      {message}
    </p>
    {(status === 401 || status === 403) ? (
      <Link className="observatory-reference-return" to="/signin?returnTo=%2Fobservatory%2Fsessions">
        {status === 403 ? 'Use a different account' : 'Sign in to read your sessions'}
      </Link>
    ) : <button
      type="button"
      onClick={onRetry}
      style={{
        marginTop: '24px',
        fontFamily: 'var(--obs-sans)',
        fontSize: '14px',
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
    </button>}
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const SessionsList: React.FC = () => {
  const navigate = useNavigate();
  const { persona } = usePersona();
  const scopedPersona = persona?.id ?? null;
  const [showAllPersonas, setShowAllPersonas] = useState(false);
  const [visibleCount, setVisibleCount] = useState(SESSION_PAGE_SIZE);
  // Forty-six recorded sessions do not fit a scan. A typed filter over the
  // opening query and id, plus a status chip, narrows without a round trip.
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | Session['status']>('all');
  // Conversations by default. Direct runs (probes, proofs, Gateway and Operator
  // calls) are one explicit choice away, kept in the URL so a shared link shows
  // the same list.
  const [searchParams, setSearchParams] = useSearchParams();
  const includeDirect = searchParams.get('direct') === '1';
  const toggleDirect = () => {
    const next = new URLSearchParams(searchParams);
    if (includeDirect) next.delete('direct');
    else next.set('direct', '1');
    setSearchParams(next, { replace: true });
  };
  const { data, loading, error, errorStatus, refetch } = useObservatoryData<Session[]>({
    key: 'sessions',
    params: includeDirect ? { include_direct: 'true' } : undefined,
  });

  const sorted = useMemo(
    () => (data ? sortSessionsByRecency(data) : []),
    [data],
  );
  const scopedSessions = useMemo(() => {
    const byPersona =
      scopedPersona && !showAllPersonas
        ? sorted.filter((session) => session.personaId === scopedPersona)
        : sorted;
    const needle = query.trim().toLowerCase();
    return byPersona.filter(
      (session) =>
        (statusFilter === 'all' || session.status === statusFilter) &&
        (!needle ||
          session.openingQuery.toLowerCase().includes(needle) ||
          session.id.toLowerCase().includes(needle)),
    );
  }, [scopedPersona, showAllPersonas, sorted, query, statusFilter]);
  const showingScopedSessions = Boolean(scopedPersona && !showAllPersonas);
  const activePersonaLabel = persona?.display_name || 'Current shopper';
  const visibleSessions = scopedSessions.slice(0, visibleCount);
  const remainingSessionCount = Math.max(
    0,
    scopedSessions.length - visibleSessions.length,
  );

  useEffect(() => {
    setVisibleCount(SESSION_PAGE_SIZE);
  }, [scopedPersona, showAllPersonas]);

  return (
    <div className="observatory-reading-page observatory-sessions-page">
      {/* Observatory-wide welcome band lives on Observatory now (the
          default landing surface). Sessions is zoom-in, no need
          to repeat the intro here. */}
      <EditorialTitle referenceId="sessions"
        backToReferences
        eyebrow="Observe · Sessions"
        title={showingScopedSessions ? `${activePersonaLabel}'s recorded sessions` : 'Sessions'}
        summary={
          showingScopedSessions
            ? 'Only durable Aurora evidence for the active shopper is shown. Select a recorded session to inspect its message history and tool ledger.'
            : 'Every durable recorded conversation captured during the workshop is available here. Select a session to inspect its message history and tool ledger.'
        }
      />

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          margin: '0 0 22px',
          padding: '14px 16px',
          border: '1px solid var(--obs-card-border)',
          borderRadius: 'var(--obs-card-radius)',
          background: 'var(--obs-cream-1)',
        }}
      >
        <div>
          <Eyebrow
            label={showingScopedSessions ? `${activePersonaLabel} scoped` : 'Workshop sessions'}
            variant="muted"
          />
          <p
            style={{
              fontFamily: 'var(--obs-sans)',
              fontSize: '14px',
              lineHeight: 1.45,
              color: 'var(--obs-ink-3)',
              margin: '6px 0 0',
            }}
          >
            {showingScopedSessions
              ? 'Recorded turns only — no fixture replays are mixed into this view.'
              : includeDirect
                ? 'Including runs outside a conversation: probes, proofs, and direct Gateway and Operator calls.'
                : 'Conversations recorded by Pellier’s chat. Probes, proofs, and direct Gateway and Operator calls are left out.'}
          </p>
        </div>
        <div
          className="observatory-sessions-filters"
          role="group"
          aria-label="Filter sessions"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}
        >
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find by opening query or id"
            aria-label="Find a session"
            data-testid="observatory-sessions-search"
            style={{
              fontFamily: 'var(--obs-sans)',
              fontSize: '13px',
              padding: '7px 12px',
              minWidth: '200px',
              border: '1px solid var(--obs-rule-2)',
              borderRadius: '6px',
              background: 'var(--obs-panel)',
              color: 'var(--obs-ink-1)',
            }}
          />
          {(['all', 'active', 'complete', 'failed', 'unknown'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className="observatory-sessions-filter"
              aria-pressed={statusFilter === value}
              data-testid={`observatory-sessions-status-${value}`}
              onClick={() => setStatusFilter(value)}
            >
              {value.charAt(0).toUpperCase() + value.slice(1)}
            </button>
          ))}
          <button
            type="button"
            className="observatory-sessions-filter"
            aria-pressed={includeDirect}
            data-testid="observatory-sessions-direct"
            onClick={toggleDirect}
          >
            Include runs outside a conversation
          </button>
        </div>
        {scopedPersona && (
          <button
            type="button"
            onClick={() => setShowAllPersonas((value) => !value)}
            aria-label={showAllPersonas ? `View ${activePersonaLabel} only` : 'View all personas'}
            aria-pressed={showAllPersonas}
            style={{
              fontFamily: 'var(--obs-sans)',
              fontSize: '13px',
              fontWeight: 500,
              color: 'var(--obs-cream-1)',
              background: 'var(--obs-ink-1)',
              border: 'none',
              borderRadius: '999px',
              padding: '9px 13px',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {showAllPersonas ? `View ${activePersonaLabel} only` : 'View all personas'}
          </button>
        )}
      </div>

      {loading && <LoadingState />}

      {error && <ErrorState message={error} status={errorStatus ?? null} onRetry={refetch} />}

      {!loading && !error && scopedSessions.length === 0 && <EmptyState />}

      {!loading && !error && scopedSessions.length > 0 && (
        <div
          className="observatory-session-list"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          {visibleSessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              onClick={() => navigate(`/observatory/sessions/${session.id}`)}
            />
          ))}
          <footer className="observatory-sessions-pagination">
            <p aria-live="polite">
              Showing {visibleSessions.length} of {scopedSessions.length}{' '}
              recorded sessions
            </p>
            {remainingSessionCount > 0 ? (
              <button
                type="button"
                data-testid="sessions-load-more"
                onClick={() =>
                  setVisibleCount((count) => count + SESSION_PAGE_SIZE)
                }
              >
                Load {Math.min(SESSION_PAGE_SIZE, remainingSessionCount)} more
              </button>
            ) : null}
          </footer>
        </div>
      )}
    </div>
  );
};

export default SessionsList;
