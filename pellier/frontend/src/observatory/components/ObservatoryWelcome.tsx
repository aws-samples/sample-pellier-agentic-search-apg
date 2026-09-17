/**
 * ObservatoryWelcome — Editorial welcome band for the default Observatory surface.
 *
 * Sits above the Sessions list on first load. Three pieces:
 *   1. Burgundy dot + eyebrow ("Welcome to Observatory")
 *   2. Display italic headline (Fraunces stack, matches Pellier hero) +
 *   3. Three "cheat sheet" cards explaining the three verbs:
 *      Observe, Understand, Evaluate
 *
 * Designed to be dismissible via sessionStorage so returning attendees
 * skip straight to the sessions list. Renders once per browser session.
 */
import React, { useState } from 'react';
import { X } from 'lucide-react';

const DISMISS_KEY = 'observatory-welcome-dismissed';

function hasBeenDismissed(): boolean {
  try {
    return sessionStorage.getItem(DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

interface PillarCardProps {
  verb: string;
  title: string;
  description: string;
}

const PillarCard: React.FC<PillarCardProps> = ({ verb, title, description }) => (
  <div
    style={{
      background: 'var(--obs-cream-2)',
      border: '1px solid var(--obs-rule-1)',
      borderRadius: '8px',
      padding: '18px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
    }}
  >
    <div
      style={{
        fontFamily: 'var(--obs-heading)',
        fontSize: '11px',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: 'var(--obs-red-1)',
        fontWeight: 600,
      }}
    >
      {verb}
    </div>
    <div
      style={{
        fontFamily: 'var(--obs-heading)',
        fontSize: 'clamp(18px, 1.8vw, 22px)',
        fontWeight: 600,
        letterSpacing: 0,
        lineHeight: 1.2,
      }}
    >
      {title}
    </div>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '13px',
        lineHeight: 1.55,
        color: 'var(--obs-ink-2)',
        margin: 0,
      }}
    >
      {description}
    </p>
  </div>
);

export const ObservatoryWelcome: React.FC = () => {
  const [dismissed, setDismissed] = useState(hasBeenDismissed);

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, '1');
    } catch {
      /* ignore */
    }
    setDismissed(true);
  };

  if (dismissed) return null;

  return (
    <section
      aria-label="Welcome to Pellier Observatory"
      style={{
        position: 'relative',
        background:
          'linear-gradient(180deg, var(--obs-cream-1) 0%, var(--obs-cream-2) 100%)',
        border: '1px solid var(--obs-rule-1)',
        borderRadius: '8px',
        padding: '32px 36px 30px',
        marginBottom: '36px',
        overflow: 'hidden',
      }}
    >
      {/* Dismiss */}
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss welcome"
        style={{
          position: 'absolute',
          top: 14,
          right: 14,
          width: 30,
          height: 30,
          borderRadius: '50%',
          border: 'none',
          background: 'rgba(31, 20, 16, 0.04)',
          color: 'var(--obs-ink-2)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background 150ms ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(31, 20, 16, 0.08)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(31, 20, 16, 0.04)';
        }}
      >
        <X size={14} strokeWidth={2.5} />
      </button>

      {/* Eyebrow */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: '14px',
        }}
      >
        <span
          aria-hidden
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: 'var(--obs-red-1)',
            display: 'inline-block',
            boxShadow: '0 0 0 3px rgba(168, 66, 58, 0.18)',
          }}
        />
        <span
          style={{
            fontFamily: 'var(--obs-heading)',
            fontSize: '11px',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--obs-red-1)',
            fontWeight: 600,
          }}
        >
          Welcome to Pellier Observatory
        </span>
      </div>

      {/* Headline */}
      <h1
        className="font-display italic text-espresso"
        style={{
          fontSize: 'clamp(44px, 6vw, 76px)',
          fontWeight: 400,
          lineHeight: 1.05,
          letterSpacing: 0,
          margin: '0 0 14px',
          maxWidth: '900px',
        }}
      >
        The operator's side of Pellier.
      </h1>

      {/* Summary */}
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '16px',
          lineHeight: 1.6,
          color: 'var(--obs-ink-2)',
          margin: '0 0 26px',
          maxWidth: '680px',
        }}
      >
        Pellier is where shoppers ask. Pellier Observatory is where you verify what happened.
        Every agent decision, tool call, memory read, and routing hop shows
        up here in governed, inspectable detail.
      </p>

      {/* Pillar cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '14px',
        }}
      >
        <PillarCard
          verb="Observe"
          title="Sessions & Observatory"
          description="Replay any shopper conversation turn-by-turn. See the wide-angle dashboard for live agent state, tool activity, and memory counts."
        />
        <PillarCard
          verb="Understand"
          title="Agents, Tools, Memory"
          description="Specialists, published tools, skills, and the memory surfaces that explain what persisted."
        />
        <PillarCard
          verb="Evaluate"
          title="Proof Board & Policy"
          description="Required checkpoints first, then optional routing patterns when the lab asks for contrast."
        />
      </div>
    </section>
  );
};

export default ObservatoryWelcome;
