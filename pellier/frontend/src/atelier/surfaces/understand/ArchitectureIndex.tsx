/**
 * ArchitectureIndex — 2-column grid of 8 architecture concept ExpCards.
 *
 * Each card displays a Roman numeral, CategoryBadge, title, role subtitle,
 * prose description, code snippet, and an "Open [concept]" link that
 * navigates to `/atelier/architecture/:slug`.
 *
 * A legend card below the grid explains the four category badges.
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow, CategoryBadge } from '../../components';
import type { CategoryType } from '../../components/CategoryBadge';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../types';

/* -----------------------------------------------------------------------
 * Legend data — explains the four category badges
 * ----------------------------------------------------------------------- */

const legendItems: { category: CategoryType; label: string; description: string }[] = [
  {
    category: 'both',
    label: 'Both',
    description: 'Shared between AgentCore managed services and your owned application code.',
  },
  {
    category: 'managed',
    label: 'Managed',
    description: 'Fully managed by AgentCore — you configure, the platform operates.',
  },
  {
    category: 'owned',
    label: 'Owned',
    description: 'Your application code — you build, deploy, and maintain it.',
  },
  {
    category: 'teaching',
    label: 'Teaching',
    description: 'Workshop teaching concept — illustrates a pattern or technique.',
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
            fontFamily: 'var(--at-serif)',
            fontStyle: 'italic',
            fontSize: '16px',
            color: 'var(--at-red-1)',
            fontWeight: 400,
          }}
        >
          {concept.numeral}.
        </span>
        <CategoryBadge category={concept.category} />
      </div>

      {/* Title */}
      <h3
        style={{
          fontFamily: 'var(--at-serif)',
          fontSize: 'var(--at-section-size)',
          fontWeight: 'var(--at-section-weight)',
          lineHeight: 'var(--at-section-leading)',
          letterSpacing: 'var(--at-section-tracking)',
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {concept.title}
      </h3>

      {/* Role subtitle */}
      <p
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '15px',
          lineHeight: 1.4,
          color: 'var(--at-red-1)',
          margin: 0,
        }}
      >
        {concept.role}
      </p>

      {/* Prose description */}
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: 'var(--at-body-size)',
          lineHeight: 'var(--at-body-leading)',
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {concept.description}
      </p>

      {/* Code snippet */}
      <pre
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '14px',
          lineHeight: 1.7,
          color: 'var(--at-ink-1)',
          backgroundColor: 'var(--at-cream-2)',
          borderRadius: '8px',
          padding: '16px 20px',
          margin: 0,
          overflowX: 'auto',
          whiteSpace: 'pre',
        }}
      >
        {concept.codeSnippet}
      </pre>

      {/* Open link */}
      <button
        onClick={onOpen}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '14px',
          color: 'var(--at-red-1)',
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
      <h3
        style={{
          fontFamily: 'var(--at-serif)',
          fontSize: '18px',
          fontWeight: 400,
          color: 'var(--at-ink-1)',
          margin: 0,
          whiteSpace: 'nowrap',
        }}
      >
        Understanding the four badges
      </h3>
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
                fontFamily: 'var(--at-sans)',
                fontSize: '13px',
                lineHeight: 1.5,
                color: 'var(--at-ink-1)',
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
    style={{
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '24px',
      padding: '24px 0',
    }}
  >
    {Array.from({ length: 8 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
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
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the architecture concepts.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: 'var(--at-mono-size)',
        color: 'var(--at-ink-2)',
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
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '22px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No architecture concepts have been loaded.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: 'var(--at-body-size)',
        color: 'var(--at-ink-2)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Check that the architecture fixture data is available and try again.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const ArchitectureIndex: React.FC = () => {
  const navigate = useNavigate();
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concepts = data ?? [];

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1400px' }}>
      <EditorialTitle
        eyebrow="Understand · Architecture"
        title="Architecture"
        summary="Eight foundational concepts that power the agentic system — from memory and routing to tool discovery and grounding. Each card opens a deep-dive detail page with prose, code, and live state."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && concepts.length === 0 && <EmptyState />}

      {!loading && !error && concepts.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 320px',
            gap: '32px',
            alignItems: 'start',
          }}
        >
          {/* Left: 2-column grid of concept cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '24px',
            }}
          >
            {concepts.map((concept) => (
              <ConceptCard
                key={concept.slug}
                concept={concept}
                onOpen={() => navigate(`/atelier/architecture/${concept.slug}`)}
              />
            ))}
          </div>

          {/* Right: sticky legend rail */}
          <div
            style={{
              position: 'sticky',
              top: '100px',
            }}
          >
            <LegendCard />
          </div>
        </div>
      )}
    </div>
  );
};

export default ArchitectureIndex;
