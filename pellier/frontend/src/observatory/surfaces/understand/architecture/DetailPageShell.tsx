/**
 * DetailPageShell — Reusable template for all 8 architecture detail pages.
 *
 * Renders:
 *   - EditorialTitle: back link, section label with a CategoryBadge beside
 *     it, the shared Fraunces page title, and the hero prose as its summary
 *   - Slot for concept-specific content (children)
 *   - Cheat-sheet strip of takeaways, one EvidenceCard each
 *   - Live state callout with Fraunces figures
 *
 * These pages used to carry their own title grammar -- an italic 56px hero
 * over a mono roman-numeral label -- against the Fraunces 400 page title
 * every other Observatory route uses. They now come through EditorialTitle,
 * so there is one page-title step on the surface; the numeral and concept
 * name are unchanged, they simply take the shared label register.
 *
 * Requirements: 7.1, 7.4, 7.5
 */

import React from 'react';
import { EditorialTitle, CategoryBadge, StatusDot } from '../../../components';
import type { CategoryType } from '../../../components/CategoryBadge';
import { EvidenceCard, SectionEyebrow, SurfaceCrossLink } from '../../../../shared';

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
    /** Static design facts are the default; live requires measured data. */
    measured?: boolean;
  };
  /**
   * Optional "See this in Pellier" cross-link. When set, renders
   * a small italic anchor next to the hero title that drops the
   * attendee onto the storefront with a query that exercises this
   * concept. Keeps the Observatory↔Pellier round trip one click away on
   * every deep-dive page.
   */
  seeInPellier?: {
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
  // `auto-fit` with a floor is what makes either collapse: the fixed
  // `repeat(3, 1fr)` this used to be kept three columns at 375px, which left
  // each tile about 80px wide and pushed its text off the page.
  const minTile = items.length === 4 ? '260px' : '200px';

  return (
    <section style={{ marginTop: '48px' }}>
      <SectionEyebrow tone="muted">Cheat sheet</SectionEyebrow>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${minTile}), 1fr))`,
          gap: '20px',
          marginTop: '20px',
        }}
      >
        {items.map((item, idx) => (
          <EvidenceCard key={idx} quiet padding="compact">
            <div
              style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}
            >
              <SectionEyebrow tone="muted" dot={false}>
                {item.numeral}
              </SectionEyebrow>
              <p
                style={{
                  fontFamily: 'var(--obs-sans)',
                  fontSize: '13px',
                  lineHeight: 1.55,
                  color: 'var(--obs-ink-1)',
                  margin: 0,
                }}
              >
                {item.text}
              </p>
            </div>
          </EvidenceCard>
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
  measured?: boolean;
}

const LiveStateCallout: React.FC<LiveStateCalloutProps> = ({ label, values, measured = false }) => (
  <section style={{ marginTop: '40px' }}>
    <EvidenceCard>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Header with pulsing indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {measured && <StatusDot status="live" size={8} />}
          <SectionEyebrow dot={false}>{measured ? 'Live state' : 'Design reference'}</SectionEyebrow>
        </div>

        {/* Context description */}
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            lineHeight: 1.5,
            color: 'var(--obs-ink-1)',
            margin: 0,
            maxWidth: '560px',
          }}
        >
          {label}
        </p>

        {/* Metric values. Fraunces, because a measured quantity is a figure
            and every figure on these surfaces is set in the display face. */}
        <div
          style={{
            display: 'flex',
            gap: '32px',
            flexWrap: 'wrap',
            paddingTop: '12px',
            borderTop: '1px solid var(--obs-rule-1)',
          }}
        >
          {values.map((v, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
              }}
            >
              <SectionEyebrow tone="muted" dot={false}>
                {v.label}
              </SectionEyebrow>
              <span
                style={{
                  fontFamily: 'var(--obs-display)',
                  fontSize: '30px',
                  fontWeight: 400,
                  color: 'var(--obs-ink-1)',
                  letterSpacing: '-0.02em',
                  lineHeight: 1,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {v.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </EvidenceCard>
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
  seeInPellier,
}) => (
  <div
    style={{
      padding: '40px clamp(20px, 4vw, 48px)',
      maxWidth: '1100px',
    }}
  >
    {/* One title block: back link, section label with the category beside
        it, the shared Fraunces page title, and the hero prose as summary. */}
    <EditorialTitle
      eyebrow={`${numeral} · ${conceptName}`}
      title={title}
      summary={prose}
      backTo={{
        to: '/observatory/architecture',
        label: 'Back to Architecture',
      }}
      aside={<CategoryBadge category={category} />}
    />

    {/* "See this in Pellier" cross-link - appears below the hero prose on
        every architecture detail page that supplies one. Pairs the deep-dive
        explainer with a one-click drop back onto the storefront so the round
        trip is always available. The title block already sets the 32px gap
        below itself, so this only needs its own trailing space. */}
    {seeInPellier && (
      <div style={{ margin: '-12px 0 32px 0' }}>
        <SurfaceCrossLink
          direction="to-pellier"
          href={seeInPellier.href}
          label={seeInPellier.label}
          italic={false}
        />
      </div>
    )}

    {/* Concept-specific content */}
    {children}

    {/* Cheat-sheet strip */}
    <CheatSheetStrip items={cheatSheet} />

    {/* Live state callout */}
    {liveState && (
      <LiveStateCallout {...liveState} />
    )}
  </div>
);

export default DetailPageShell;
