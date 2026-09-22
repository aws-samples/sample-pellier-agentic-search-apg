import { apiFetch } from '../../services/apiBase'
/**
 * Settings — Persona selection interface for the Pellier Observatory.
 *
 * Displays available personas as editorial cards. Selecting a persona
 * updates the PersonaContext, which scopes all Observatory surfaces to that
 * persona's live Aurora data.
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
        background: isActive ? 'var(--obs-card-bg)' : 'transparent',
        border: isActive
          ? '2px solid var(--obs-red-1)'
          : '1px solid var(--obs-card-border)',
        borderRadius: 'var(--obs-card-radius)',
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
            width: 'var(--obs-card-accent-width)',
            height: '3px',
            backgroundColor: 'var(--obs-card-accent-color)',
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
                border: '2px solid var(--obs-card-border)',
              }}
            />
          ) : (
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '50%',
                background: persona.avatar_color === 'transparent'
                  ? 'var(--obs-cream-2)'
                  : persona.avatar_color,
                border: persona.avatar_color === 'transparent'
                  ? '1.5px dashed var(--obs-rule-3)'
                  : 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--obs-sans)',
                fontSize: '18px',
                fontWeight: 600,
                color: persona.avatar_color === 'transparent'
                  ? 'var(--obs-ink-1)'
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
              fontFamily: 'var(--obs-heading)',
              fontSize: '22px',
              fontWeight: 400,
              color: 'var(--obs-ink-1)',
              letterSpacing: '-0.01em',
              lineHeight: 1.15,
            }}
          >
            {persona.display_name}
          </div>
          <div
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: 'var(--text-label)',
              fontWeight: 500,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: isActive ? 'var(--obs-red-1)' : 'var(--obs-ink-4)',
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
              fontFamily: 'var(--obs-mono)',
              fontSize: 'var(--text-label)',
              fontWeight: 500,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: '#fff',
              backgroundColor: 'var(--obs-red-1)',
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
          fontFamily: 'var(--obs-heading)',
          fontSize: '14px',
          lineHeight: 1.55,
          color: 'var(--obs-ink-1)',
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
          borderTop: '1px solid var(--obs-rule-1)',
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
        fontFamily: 'var(--obs-mono)',
        fontSize: 'var(--text-label)',
        fontWeight: 500,
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: 'var(--obs-ink-4)',
      }}
    >
      {label}
    </span>
    <span
      style={{
        fontFamily: 'var(--obs-heading)',
        fontSize: '16px',
        fontWeight: 400,
        color: 'var(--obs-ink-1)',
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
          background: 'var(--obs-cream-2)',
          borderRadius: 'var(--obs-card-radius)',
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
        fontFamily: 'var(--obs-heading)',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the personas.
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
    <button
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
    </button>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Settings: React.FC = () => {
  const { persona, switchPersona, switching } = usePersona();
  const [personas, setPersonas] = useState<PersonaListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const activeId = persona?.id ?? '';

  /** Fetch only the durable Aurora profiles available to this workshop. */
  const fetchPersonas = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch('/api/observatory/personas');
      if (!res.ok) throw new Error(`Failed to load personas: ${res.status}`);
      const data: PersonaListItem[] = await res.json();
      setPersonas(data.filter((profile) => profile.id !== 'fresh'));
    } catch (reason) {
      setPersonas([]);
      setError(
        reason instanceof Error ? reason.message : 'Live personas are unavailable.',
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPersonas();
  }, []);

  const handleSelect = (personaId: string) => {
    if (personaId !== activeId && !switching) {
      switchPersona(personaId);
    }
  };

  return (
    <div style={{ padding: '40px 48px', maxWidth: '720px' }}>
      <EditorialTitle
        eyebrow="Settings · Persona · workshop identity"
        title="Persona"
        summary="Select a persona to scope every Pellier Observatory surface to their history, preferences, and memory. The sidebar, sessions, and memory dashboard all follow the active persona."
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
              fontFamily: 'var(--obs-heading)',
              fontSize: '20px',
              color: 'var(--obs-ink-1)',
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
              background: 'var(--obs-cream-2)',
              borderRadius: '8px',
              fontFamily: 'var(--obs-mono)',
              fontSize: '11px',
              lineHeight: 1.6,
              color: 'var(--obs-ink-1)',
              letterSpacing: '0.02em',
            }}
          >
            <span
              style={{
                color: 'var(--obs-red-1)',
                fontWeight: 500,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                fontSize: 'var(--text-label)',
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
