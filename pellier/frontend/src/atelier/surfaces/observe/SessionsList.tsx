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

import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow } from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { Session } from '../../types';
import { usePersona } from '../../../contexts/PersonaContext';
import { PERSONA_HERO_PILLS, PERSONA_TURN_TRACES } from '../../../data/personaCurations';

/* -----------------------------------------------------------------------
 * Sort helper — exported for property-based testing (Property 1)
 * ----------------------------------------------------------------------- */

/**
 * Sort sessions by timestamp ascending (earliest first) so the
 * instructor-view list reads Marco → Anna → Theo, matching the
 * canonical persona order used everywhere else in the Atelier.
 * Returns a new array; does not mutate the input.
 */
export function sortSessionsByRecency(sessions: Session[]): Session[] {
  return [...sessions].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
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

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const CANONICAL_PERSONAS = ['marco', 'anna', 'theo'] as const;
type CanonicalPersona = (typeof CANONICAL_PERSONAS)[number];

const PERSONA_LABELS: Record<CanonicalPersona, string> = {
  marco: 'Marco',
  anna: 'Anna',
  theo: 'Theo',
};

const REPLAY_BY_PERSONA_TURN: Record<CanonicalPersona, string[]> = {
  marco: [
    'marco-opening-demo',
    'marco-opening-demo',
    'marco-opening-demo',
    'marco-midpoint-checkpoint',
    'marco-capstone',
  ],
  anna: [
    'anna-morning-ritual',
    'anna-under-100',
    'anna-candle-pairing',
    'anna-birthday-gift',
    'anna-housewarming',
  ],
  theo: [
    'theo-pour-over',
    'theo-pour-over-pairing',
    'theo-linen-seasons',
    'theo-ceramics-return',
    'theo-home-not-wardrobe',
  ],
};

function activeCanonicalPersona(personaId: string | null | undefined): CanonicalPersona | null {
  return CANONICAL_PERSONAS.includes(personaId as CanonicalPersona)
    ? (personaId as CanonicalPersona)
    : null;
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

interface PersonaTurnCardProps {
  personaId: CanonicalPersona;
  turnIndex: number;
  query: string;
  replayId: string;
  onOpenReplay: (id: string) => void;
}

const PersonaTurnCard: React.FC<PersonaTurnCardProps> = ({
  personaId,
  turnIndex,
  query,
  replayId,
  onOpenReplay,
}) => {
  const trace = PERSONA_TURN_TRACES[personaId][turnIndex];
  return (
    <ExpCard>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-ink-4)',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}
          >
            {PERSONA_LABELS[personaId]} · turn {turnIndex + 1}
          </span>
          <button
            type="button"
            onClick={() => onOpenReplay(replayId)}
            aria-label={`Open replay for ${PERSONA_LABELS[personaId]} turn ${turnIndex + 1}`}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--at-red-1)',
              background: 'transparent',
              border: '1px solid var(--at-card-border)',
              borderRadius: '999px',
              padding: '5px 10px',
              cursor: 'pointer',
            }}
          >
            Open replay
          </button>
        </div>

        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '18px',
            lineHeight: 1.35,
            color: 'var(--at-ink-1)',
            margin: 0,
          }}
        >
          {query}
        </p>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            alignItems: 'center',
          }}
        >
          {trace.skill && (
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                color: 'var(--at-green-1)',
                background: 'var(--at-green-soft)',
                borderRadius: '4px',
                padding: '3px 8px',
              }}
            >
              skill.{trace.skill}
            </span>
          )}
          {trace.tools.map((tool) => (
            <span
              key={tool}
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                color: 'var(--at-red-1)',
                background: 'var(--at-red-soft)',
                borderRadius: '4px',
                padding: '3px 8px',
              }}
            >
              tool.{tool}
            </span>
          ))}
        </div>
      </div>
    </ExpCard>
  );
};

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
      type="button"
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
  const { persona } = usePersona();
  const scopedPersona = activeCanonicalPersona(persona?.id);
  const [showAllPersonas, setShowAllPersonas] = useState(false);
  const { data, loading, error, refetch } = useAtelierData<Session[]>({
    key: 'sessions',
  });

  const sorted = data ? sortSessionsByRecency(data) : [];
  const personaTurns = useMemo(() => {
    if (!scopedPersona) return [];
    return PERSONA_HERO_PILLS[scopedPersona].map((query, index) => ({
      query,
      replayId: REPLAY_BY_PERSONA_TURN[scopedPersona][index],
    }));
  }, [scopedPersona]);
  const showingPersonaJourney = Boolean(scopedPersona && !showAllPersonas);
  const activePersonaLabel = scopedPersona ? PERSONA_LABELS[scopedPersona] : 'Persona';

  return (
    <div style={{ padding: '40px 48px', maxWidth: '960px' }}>
      {/* Atelier-wide welcome band lives on Observatory now (the
          default landing surface). Sessions is zoom-in, no need
          to repeat the intro here. */}
      <EditorialTitle
        eyebrow="Observe · Sessions"
        title={showingPersonaJourney ? `${activePersonaLabel}'s five-turn journey` : 'Sessions'}
        summary={
          showingPersonaJourney
            ? 'Sessions opens on the signed-in persona so participants follow one coherent Boutique story. Each turn mirrors the Boutique pill text and expected skill/tool trace; instructor view reveals all recorded replays.'
            : 'Instructor view shows every recorded conversation across personas, captured and ready for inspection. Select a session to explore its chat thread, telemetry timeline, and curator brief.'
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
          border: '1px solid var(--at-card-border)',
          borderRadius: 'var(--at-card-radius)',
          background: 'var(--at-cream-1)',
        }}
      >
        <div>
          <Eyebrow
            label={showingPersonaJourney ? `${activePersonaLabel} scoped` : 'Instructor view'}
            variant="muted"
          />
          <p
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '14px',
              lineHeight: 1.45,
              color: 'var(--at-ink-3)',
              margin: '6px 0 0',
            }}
          >
            {showingPersonaJourney
              ? 'Only this persona appears by default; the five cards below match the Boutique hero pills turn by turn.'
              : 'Showing Marco, Anna, and Theo together for facilitation and QA.'}
          </p>
        </div>
        {scopedPersona && (
          <button
            type="button"
            onClick={() => setShowAllPersonas((value) => !value)}
            aria-label={showAllPersonas ? `View ${activePersonaLabel} only` : 'View all personas'}
            aria-pressed={showAllPersonas}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--at-cream-1)',
              background: 'var(--at-ink-1)',
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

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && scopedPersona && !showAllPersonas && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          {personaTurns.map((turn, index) => (
            <PersonaTurnCard
              key={`${scopedPersona}-${index}`}
              personaId={scopedPersona}
              turnIndex={index}
              query={turn.query}
              replayId={turn.replayId}
              onOpenReplay={(id) => navigate(`/atelier/sessions/${id}`)}
            />
          ))}
        </div>
      )}

      {!loading && !error && !showingPersonaJourney && sorted.length === 0 && <EmptyState />}

      {!loading && !error && !showingPersonaJourney && sorted.length > 0 && (
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
