/**
 * Settings — Persona selection interface for the Atelier Observatory.
 *
 * Displays available personas as editorial cards. Selecting a persona
 * updates the PersonaContext, which scopes all Atelier surfaces to that
 * persona's data. Defaults to Marco as the active persona.
 *
 * The Sidebar footer automatically reflects the active persona's name,
 * avatar initial (colored circle), and role label (JetBrains Mono uppercase)
 * via the shared PersonaContext.
 *
 * Requirements: 18.1, 18.2, 18.3, 18.4
 */

import React, { useEffect, useState } from 'react';
import { EditorialTitle, Eyebrow } from '../components';
import { usePersona, type PersonaListItem } from '../../contexts/PersonaContext';
import { getPersonaPhoto } from '../../data/personaPhotos';

/* -----------------------------------------------------------------------
 * Persona card
 * ----------------------------------------------------------------------- */

interface PersonaCardProps {
  persona: PersonaListItem;
  isActive: boolean;
  onSelect: () => void;
  switching: boolean;
}

const PersonaCard: React.FC<PersonaCardProps> = ({
  persona,
  isActive,
  onSelect,
  switching,
}) => {
  return (
    <button
      onClick={onSelect}
      disabled={switching}
      aria-pressed={isActive}
      aria-label={`Select persona: ${persona.display_name}`}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        padding: '24px 26px 22px',
        background: isActive ? 'var(--at-card-bg)' : 'transparent',
        border: isActive
          ? '2px solid var(--at-red-1)'
          : '1px solid var(--at-card-border)',
        borderRadius: 'var(--at-card-radius)',
        cursor: switching ? 'wait' : 'pointer',
        textAlign: 'left',
        overflow: 'hidden',
        transition: 'border-color 0.2s, background 0.2s, box-shadow 0.2s',
        width: '100%',
        outline: 'none',
        boxShadow: isActive ? '0 2px 12px rgba(168, 66, 58, 0.08)' : 'none',
      }}
    >
      {/* Burgundy accent line at top-left (active only) */}
      {isActive && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 0,
            left: '20px',
            width: 'var(--at-card-accent-width)',
            height: '3px',
            backgroundColor: 'var(--at-card-accent-color)',
            borderRadius: '0 0 2px 2px',
          }}
        />
      )}

      {/* Head: avatar + name + role + active badge */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '14px',
        }}
      >
        {/* Avatar — photo when available, monogram fallback */}
        {(() => {
          const photoUrl = getPersonaPhoto(persona.id);
          return photoUrl ? (
            <img
              src={photoUrl}
              alt={persona.display_name}
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '50%',
                objectFit: 'cover',
                flexShrink: 0,
                border: '2px solid var(--at-card-border)',
              }}
            />
          ) : (
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '50%',
                background: persona.avatar_color === 'transparent'
                  ? 'var(--at-cream-2)'
                  : persona.avatar_color,
                border: persona.avatar_color === 'transparent'
                  ? '1.5px dashed var(--at-rule-3)'
                  : 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--at-sans)',
                fontSize: '18px',
                fontWeight: 600,
                color: persona.avatar_color === 'transparent'
                  ? 'var(--at-ink-1)'
                  : '#fff',
                flexShrink: 0,
              }}
            >
              {persona.avatar_initial}
            </div>
          );
        })()}

        {/* Name + role */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
              fontSize: '22px',
              fontWeight: 400,
              color: 'var(--at-ink-1)',
              letterSpacing: '-0.01em',
              lineHeight: 1.15,
            }}
          >
            {persona.display_name}
          </div>
          <div
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '9px',
              fontWeight: 500,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: isActive ? 'var(--at-red-1)' : 'var(--at-ink-4)',
              marginTop: '4px',
            }}
          >
            {persona.role_tag}
          </div>
        </div>

        {/* Active indicator */}
        {isActive && (
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '9px',
              fontWeight: 500,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: '#fff',
              backgroundColor: 'var(--at-red-1)',
              padding: '4px 10px',
              borderRadius: '100px',
              flexShrink: 0,
            }}
          >
            Active
          </span>
        )}
      </div>

      {/* Blurb */}
      <p
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '14px',
          lineHeight: 1.55,
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {persona.blurb}
      </p>

      {/* Stats row */}
      <div
        style={{
          display: 'flex',
          gap: '20px',
          paddingTop: '10px',
          borderTop: '1px solid var(--at-rule-1)',
        }}
      >
        <StatChip label="Visits" value={persona.stats.visits} />
        <StatChip label="Orders" value={persona.stats.orders} />
        <StatChip
          label="Last seen"
          value={
            persona.stats.last_seen_days !== null
              ? `${persona.stats.last_seen_days}d ago`
              : 'Never'
          }
        />
      </div>
    </button>
  );
};

/* -----------------------------------------------------------------------
 * Stat chip — small metric display
 * ----------------------------------------------------------------------- */

interface StatChipProps {
  label: string;
  value: string | number;
}

const StatChip: React.FC<StatChipProps> = ({ label, value }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
    <span
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '8.5px',
        fontWeight: 500,
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: 'var(--at-ink-4)',
      }}
    >
      {label}
    </span>
    <span
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '16px',
        fontWeight: 400,
        color: 'var(--at-ink-1)',
        letterSpacing: '-0.01em',
      }}
    >
      {value}
    </span>
  </div>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '24px 0' }}>
    {Array.from({ length: 4 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: '160px',
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
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the personas.
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

/** Default persona ID when none is selected */
const DEFAULT_PERSONA_ID = 'marco';

/**
 * Fallback persona list — used when the API is unavailable.
 * Matches the structure returned by GET /api/atelier/personas.
 */
const FALLBACK_PERSONAS: PersonaListItem[] = [
  {
    id: 'marco',
    display_name: 'Marco',
    role_tag: 'Returning',
    blurb: 'Brooklyn-based, partial to natural fibers. Last visit, three weeks ago. Bought the oat Maren tunic.',
    avatar_color: '#5a3528',
    avatar_initial: 'M',
    stats: { visits: 11, orders: 7, last_seen_days: 21 },
  },
  {
    id: 'anna',
    display_name: 'Anna',
    role_tag: 'Gift-giver',
    blurb: 'Buys for others — partner, mother, friends. Never for herself. Recent searches lean milestone.',
    avatar_color: '#6b3d2a',
    avatar_initial: 'A',
    stats: { visits: 6, orders: 5, last_seen_days: 9 },
  },
  {
    id: 'theo',
    display_name: 'Theo',
    role_tag: 'Home + slow craft',
    blurb: 'Keeps a short list of quiet pieces — ceramics, linen throws, stoneware. Finishes what he buys, slowly.',
    avatar_color: '#5a4535',
    avatar_initial: 'T',
    stats: { visits: 8, orders: 4, last_seen_days: 14 },
  },
  // Fresh visitor removed — signed-out state IS the baseline.
  // The boutique renders editorial defaults when no persona is active.
];

const Settings: React.FC = () => {
  const { persona, switchPersona, switching } = usePersona();
  const [personas, setPersonas] = useState<PersonaListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const activeId = persona?.id ?? DEFAULT_PERSONA_ID;

  /** Fetch available personas from the API, fall back to hardcoded list. */
  const fetchPersonas = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/atelier/personas');
      if (!res.ok) throw new Error(`Failed to load personas: ${res.status}`);
      const data: PersonaListItem[] = await res.json();
      setPersonas(data.length > 0 ? data : FALLBACK_PERSONAS);
    } catch {
      // API unavailable — use fallback personas
      setPersonas(FALLBACK_PERSONAS);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPersonas();
  }, []);

  // Auto-select Marco if no persona is active yet (Requirement 18.2)
  useEffect(() => {
    if (!persona && !switching && personas.length > 0) {
      switchPersona(DEFAULT_PERSONA_ID);
    }
  }, [persona, switching, personas, switchPersona]);

  const handleSelect = (personaId: string) => {
    if (personaId !== activeId && !switching) {
      switchPersona(personaId);
    }
  };

  return (
    <div style={{ padding: '40px 48px', maxWidth: '720px' }}>
      <EditorialTitle
        eyebrow="Settings · Persona · workshop identity"
        title="Who walks in."
        summary="Select a persona to scope every Atelier surface to their history, preferences, and memory. The sidebar, sessions, and memory dashboard all follow the active persona."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={fetchPersonas} />}

      {!loading && !error && personas.length === 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '80px 24px',
            textAlign: 'center',
          }}
        >
          <Eyebrow label="No personas" variant="muted" />
          <p
            style={{
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
              fontSize: '20px',
              color: 'var(--at-ink-1)',
              marginTop: '16px',
            }}
          >
            No personas have been configured.
          </p>
        </div>
      )}

      {!loading && !error && personas.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
            marginTop: '8px',
          }}
        >
          {personas.map((p) => (
            <PersonaCard
              key={p.id}
              persona={p}
              isActive={p.id === activeId}
              onSelect={() => handleSelect(p.id)}
              switching={switching}
            />
          ))}

          {/* Info note */}
          <div
            style={{
              marginTop: '16px',
              padding: '16px 20px',
              background: 'var(--at-cream-2)',
              borderRadius: '8px',
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              lineHeight: 1.6,
              color: 'var(--at-ink-1)',
              letterSpacing: '0.02em',
            }}
          >
            <span
              style={{
                color: 'var(--at-red-1)',
                fontWeight: 500,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                fontSize: '9px',
                marginRight: '8px',
              }}
            >
              Note
            </span>
            Switching personas generates a new session and clears the chat
            history. Memory surfaces will show data scoped to the selected
            persona's STM and LTM.
          </div>
        </div>
      )}
    </div>
  );
};

export default Settings;
