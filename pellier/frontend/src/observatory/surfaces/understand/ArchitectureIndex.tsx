/**
 * ArchitectureIndex — 2-column grid of 8 architecture lens ExpCards.
 *
 * Each card displays a Roman numeral, CategoryBadge, title, role subtitle,
 * prose description, code snippet, and an "Open [concept]" link that
 * navigates to `/observatory/architecture/:slug`.
 *
 * A legend card explains what is owned, managed, optional, or teaching-only.
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow, CategoryBadge } from '../../components';
import type { CategoryType } from '../../components/CategoryBadge';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import type { ArchitectureConcept } from '../../types';

/* -----------------------------------------------------------------------
 * Legend data — explains the four category badges
 * ----------------------------------------------------------------------- */

const legendItems: { category: CategoryType; description: string }[] = [
  {
    category: 'live',
    description: "Used directly in Pellier's request path, which participants can replay in Sessions.",
  },
  {
    category: 'workshop',
    description: 'A teaching lens or demo surface that explains the system without running on every request.',
  },
  {
    category: 'optional',
    description: 'Infrastructure available when configured, not required for the default local workshop path.',
  },
  {
    category: 'quality',
    description: 'Evaluation and measurement layer used to decide what is worth shipping.',
  },
];

/* -----------------------------------------------------------------------
 * Architecture concept card
 * ----------------------------------------------------------------------- */

interface ConceptCardProps {
  concept: ArchitectureConcept;
  onOpen: () => void;
}

const ConceptCard: React.FC<ConceptCardProps> = ({ concept, onOpen }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Top row: Roman numeral + category badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            letterSpacing: '0.06em',
            color: 'var(--obs-red-1)',
            fontWeight: 500,
          }}
        >
          {concept.numeral}.
        </span>
        <CategoryBadge category={concept.category} />
      </div>

      {/* Title */}
      <h2
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: 'var(--obs-section-size)',
          fontWeight: 'var(--obs-section-weight)',
          lineHeight: 'var(--obs-section-leading)',
          letterSpacing: 'var(--obs-section-tracking)',
          color: 'var(--obs-ink-1)',
          margin: 0,
        }}
      >
        {concept.title}
      </h2>

      {/* Role subtitle */}
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          lineHeight: 1.45,
          color: 'var(--obs-red-1)',
          margin: 0,
        }}
      >
        {concept.role}
      </p>

      {/* Prose description */}
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: 'var(--obs-body-size)',
          lineHeight: 'var(--obs-body-leading)',
          color: 'var(--obs-ink-1)',
          margin: 0,
        }}
      >
        {concept.description}
      </p>

      {/* Code snippet */}
      <pre
        className="dl-code-block"
        style={{
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {concept.codeSnippet}
      </pre>

      {/* Open link */}
      <button
        onClick={onOpen}
        className="observatory-card-action"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          fontFamily: 'var(--obs-sans)',
          fontSize: '13px',
          fontWeight: 500,
          color: 'var(--obs-red-1)',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          alignSelf: 'flex-start',
        }}
      >
        Open {concept.title}
        <span aria-hidden="true" style={{ fontSize: '12px' }}>›</span>
      </button>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Legend card
 * ----------------------------------------------------------------------- */

const LegendCard: React.FC = () => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <Eyebrow label="Category legend" variant="muted" />
      <h2
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: '18px',
          fontWeight: 400,
          color: 'var(--obs-ink-1)',
          margin: 0,
          whiteSpace: 'nowrap',
        }}
      >
        Where this appears in Pellier
      </h2>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        {legendItems.map((item) => (
          <div
            key={item.category}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            <CategoryBadge category={item.category} />
            <p
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                lineHeight: 1.5,
                color: 'var(--obs-ink-1)',
                margin: 0,
              }}
            >
              {item.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div
    className="observatory-architecture-loading"
    style={{
      display: 'grid',
      gap: '24px',
      padding: '24px 0',
    }}
  >
    {Array.from({ length: 8 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--obs-cream-2)',
          borderRadius: 'var(--obs-card-radius)',
          height: '280px',
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
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the architecture concepts.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: 'var(--obs-mono-size)',
        color: 'var(--obs-ink-2)',
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
    <Eyebrow label="No concepts" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        lineHeight: 1.45,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No architecture concepts have been loaded.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: 'var(--obs-body-size)',
        color: 'var(--obs-ink-2)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Check that the architecture reference data is available and try again.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const ArchitectureIndex: React.FC = () => {
  const navigate = useNavigate();
  const { data, loading, error, refetch } = useObservatoryData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const labSlugs = new Set([
    'grounding',
    'state-management',
    'skills',
    'memory',
    'tool-registry',
    'runtime',
    'mcp',
  ]);
  const concepts = (data ?? []).filter((concept) => labSlugs.has(concept.slug));

  return (
    <div className="observatory-reading-page observatory-architecture-page">
      <EditorialTitle referenceId="architecture"
        backToReferences
        eyebrow="Start Here · Architecture Brief"
        title="Architecture"
        summary="A short map of the pieces the labs ask you to prove: Aurora grounding, dispatcher routing, skills, tool registry, memory, Runtime, and Gateway. Use it as orientation, then return to Code Editor or Pellier."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && concepts.length === 0 && <EmptyState />}

      {!loading && !error && concepts.length > 0 && (
        <div className="observatory-architecture-layout">
          {/* Left: 2-column grid of concept cards */}
          <div className="observatory-architecture-grid">
            {concepts.map((concept) => (
              <ConceptCard
                key={concept.slug}
                concept={concept}
                onOpen={() => navigate(`/observatory/architecture/${concept.slug}`)}
              />
            ))}
          </div>

          {/* Right: sticky legend rail */}
          <div className="observatory-architecture-legend">
            <LegendCard />
          </div>
        </div>
      )}
    </div>
  );
};

export default ArchitectureIndex;
