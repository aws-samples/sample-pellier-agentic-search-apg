/**
 * DetailPageShell — Reusable template for all 8 architecture detail pages.
 *
 * Renders:
 *   - Detail Eyebrow (numeral + concept name + CategoryBadge)
 *   - Hero title (Fraunces 56px italic)
 *   - Hero prose
 *   - Slot for concept-specific content (children)
 *   - Cheat-sheet strip (3-column grid of takeaways with Roman numeral
 *     Eyebrows and italic text)
 *   - Live state callout (pulsing indicator, context description,
 *     current metric values)
 *
 * Requirements: 7.1, 7.4, 7.5
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Eyebrow, ExpCard, CategoryBadge, StatusDot } from '../../../components';
import type { CategoryType } from '../../../components/CategoryBadge';
import { SurfaceCrossLink } from '../../../../shared';

/* -----------------------------------------------------------------------
 * Types
 * ----------------------------------------------------------------------- */

export interface CheatSheetItem {
  numeral: string;
  text: string;
}

export interface LiveStateValue {
  label: string;
  value: string;
}

export interface DetailPageShellProps {
  /** Roman numeral for the concept (e.g., "I", "II"). */
  numeral: string;
  /** Concept name shown in the eyebrow (e.g., "Memory"). */
  conceptName: string;
  /** Category badge type. */
  category: CategoryType;
  /** Hero title — Fraunces 56px italic. */
  title: string;
  /** Hero prose paragraph below the title. */
  prose: string;
  /** Concept-specific content slot. */
  children: React.ReactNode;
  /** 3-column cheat-sheet strip of key takeaways. */
  cheatSheet: CheatSheetItem[];
  /** Optional live state callout with pulsing indicator and metrics. */
  liveState?: {
    label: string;
    values: LiveStateValue[];
  };
  /**
   * Optional "See this in the Boutique" cross-link. When set, renders
   * a small italic anchor next to the hero title that drops the
   * attendee onto the storefront with a query that exercises this
   * concept. Keeps the Atelier↔Boutique round trip one click away on
   * every deep-dive page.
   */
  seeInBoutique?: {
    /** Storefront href, optionally with `?ask=...`. */
    href: string;
    /** Override the default copy. */
    label?: string;
  };
}

/* -----------------------------------------------------------------------
 * Cheat-sheet strip
 * ----------------------------------------------------------------------- */

const CheatSheetStrip: React.FC<{ items: CheatSheetItem[] }> = ({ items }) => {
  if (items.length === 0) return null;

  // 4 items lay out best as a 2x2 grid; 3 (the common case) stays 3-up.
  const columns = items.length === 4 ? 2 : 3;

  return (
    <section style={{ marginTop: '48px' }}>
      <Eyebrow label="Cheat sheet" variant="muted" />
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${columns}, 1fr)`,
          gap: '20px',
          marginTop: '20px',
        }}
      >
        {items.map((item, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              padding: '20px',
              background: 'var(--at-cream-2)',
              borderRadius: '10px',
              border: '1px solid var(--at-card-border)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '9px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: 'var(--at-ink-4)',
                fontWeight: 500,
              }}
            >
              {item.numeral}
            </span>
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '13.5px',
                lineHeight: 1.55,
                color: 'var(--at-ink-1)',
                margin: 0,
              }}
            >
              {item.text}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
};

/* -----------------------------------------------------------------------
 * Live state callout
 * ----------------------------------------------------------------------- */

interface LiveStateCalloutProps {
  label: string;
  values: LiveStateValue[];
}

const LiveStateCallout: React.FC<LiveStateCalloutProps> = ({ label, values }) => (
  <section style={{ marginTop: '40px' }}>
    <ExpCard>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Header with pulsing indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <StatusDot status="live" size={8} />
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '9px',
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: 'var(--at-red-1)',
              fontWeight: 500,
            }}
          >
            Live state
          </span>
        </div>

        {/* Context description */}
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.5,
            color: 'var(--at-ink-1)',
            margin: 0,
            maxWidth: '560px',
          }}
        >
          {label}
        </p>

        {/* Metric values */}
        <div
          style={{
            display: 'flex',
            gap: '32px',
            flexWrap: 'wrap',
            paddingTop: '12px',
            borderTop: '1px solid var(--at-card-border)',
          }}
        >
          {values.map((v, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '9px',
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  color: 'var(--at-ink-4)',
                }}
              >
                {v.label}
              </span>
              <span
                style={{
                  fontFamily: 'var(--at-serif)',
                  fontSize: '28px',
                  fontWeight: 400,
                  color: 'var(--at-ink-1)',
                  letterSpacing: '-0.02em',
                  lineHeight: 1,
                }}
              >
                {v.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </ExpCard>
  </section>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const DetailPageShell: React.FC<DetailPageShellProps> = ({
  numeral,
  conceptName,
  category,
  title,
  prose,
  children,
  cheatSheet,
  liveState,
  seeInBoutique,
}) => {
  const navigate = useNavigate();

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      {/* Back link — returns to architecture index */}
      <button
        onClick={() => navigate('/atelier/architecture')}
        className="font-sans"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '14px',
          fontWeight: 500,
          color: 'var(--at-ink-1)',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: 0,
          marginBottom: '24px',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--at-ink-1)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--at-ink-1)'; }}
      >
        <ArrowLeft size={16} strokeWidth={1.75} />
        Back to Architecture
      </button>

      {/* Detail Eyebrow: numeral + concept name + CategoryBadge */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: '16px',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '9px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--at-ink-4)',
            fontWeight: 500,
          }}
        >
          {numeral} · {conceptName}
        </span>
        <CategoryBadge category={category} />
      </div>

      {/* Hero title — same Fraunces display stack as Boutique hero + EditorialTitle */}
      <h1
        className="font-display italic text-espresso"
        style={{
          fontSize: 'clamp(40px, 5vw, 56px)',
          fontWeight: 400,
          lineHeight: 1.08,
          letterSpacing: '-0.02em',
          margin: '0 0 16px 0',
        }}
      >
        {title}
      </h1>

      {/* Hero prose */}
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: 'var(--at-body-size)',
          lineHeight: 'var(--at-body-leading)',
          color: 'var(--at-ink-1)',
          maxWidth: '680px',
          margin: '0 0 16px 0',
        }}
      >
        {prose}
      </p>

      {/* "See this in the Boutique" cross-link — appears below the
          hero prose on every architecture detail page that supplies
          one. Pairs the deep-dive explainer with a one-click drop
          back onto the storefront so the round trip is always
          available. */}
      {seeInBoutique && (
        <div style={{ margin: '0 0 40px 0' }}>
          <SurfaceCrossLink
            direction="to-boutique"
            href={seeInBoutique.href}
            label={seeInBoutique.label}
            italic={false}
          />
        </div>
      )}
      {!seeInBoutique && <div style={{ height: 24 }} />}

      {/* Concept-specific content */}
      {children}

      {/* Cheat-sheet strip */}
      <CheatSheetStrip items={cheatSheet} />

      {/* Live state callout */}
      {liveState && (
        <LiveStateCallout label={liveState.label} values={liveState.values} />
      )}
    </div>
  );
};

export default DetailPageShell;
