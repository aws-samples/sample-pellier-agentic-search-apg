/**
 * ArchitectureDetail — Router component for architecture detail pages.
 *
 * Reads `:concept` from useParams and renders the matching detail page.
 * Returns a 404-style message for unknown concepts.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React, { lazy, Suspense } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Eyebrow } from '../../../components';

/* -----------------------------------------------------------------------
 * Lazy-loaded detail page components
 * ----------------------------------------------------------------------- */

const MemoryDetail = lazy(() => import('./MemoryDetail'));
const McpDetail = lazy(() => import('./McpDetail'));
const StateDetail = lazy(() => import('./StateDetail'));
const ToolRegistryDetail = lazy(() => import('./ToolRegistryDetail'));
const SkillsDetail = lazy(() => import('./SkillsDetail'));
const RuntimeDetail = lazy(() => import('./RuntimeDetail'));
const EvaluationsDetail = lazy(() => import('./EvaluationsDetail'));
const GroundingDetail = lazy(() => import('./GroundingDetail'));

/* -----------------------------------------------------------------------
 * Concept slug → component mapping
 * ----------------------------------------------------------------------- */

const conceptComponents: Record<string, React.LazyExoticComponent<React.FC>> = {
  memory: MemoryDetail,
  mcp: McpDetail,
  'state-management': StateDetail,
  'tool-registry': ToolRegistryDetail,
  skills: SkillsDetail,
  runtime: RuntimeDetail,
  evaluations: EvaluationsDetail,
  grounding: GroundingDetail,
};

/* -----------------------------------------------------------------------
 * Loading fallback
 * ----------------------------------------------------------------------- */

const LoadingFallback: React.FC = () => (
  <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Eyebrow skeleton */}
      <div
        style={{
          width: '200px',
          height: '12px',
          background: 'var(--at-cream-2)',
          borderRadius: '4px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
      {/* Title skeleton */}
      <div
        style={{
          width: '400px',
          height: '48px',
          background: 'var(--at-cream-2)',
          borderRadius: '8px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
      {/* Prose skeleton */}
      <div
        style={{
          width: '600px',
          height: '60px',
          background: 'var(--at-cream-2)',
          borderRadius: '8px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
      {/* Content skeleton */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginTop: '20px' }}>
        {[0, 1].map((i) => (
          <div
            key={i}
            style={{
              height: '240px',
              background: 'var(--at-cream-2)',
              borderRadius: 'var(--at-card-radius)',
              opacity: 0.5,
              animation: 'pulse 1.5s ease-in-out infinite',
            }}
          />
        ))}
      </div>
    </div>
  </div>
);

/* -----------------------------------------------------------------------
 * Not found state
 * ----------------------------------------------------------------------- */

const NotFoundState: React.FC<{ concept: string }> = ({ concept }) => {
  const navigate = useNavigate();

  return (
    <div
      style={{
        padding: '40px 48px',
        maxWidth: '1100px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '400px',
        textAlign: 'center',
      }}
    >
      <Eyebrow label="Not found" variant="muted" />
      <h1
        style={{
          fontFamily: 'var(--at-serif)',
          fontSize: '36px',
          fontWeight: 400,
          fontStyle: 'italic',
          lineHeight: 1.15,
          color: 'var(--at-ink-1)',
          margin: '16px 0 0 0',
        }}
      >
        Unknown concept.
      </h1>
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: 'var(--at-body-size)',
          lineHeight: 'var(--at-body-leading)',
          color: 'var(--at-ink-1)',
          maxWidth: '420px',
          marginTop: '12px',
        }}
      >
        There's no architecture detail page for "{concept}". Check the URL or
        return to the architecture index.
      </p>
      <button
        onClick={() => navigate('/atelier/architecture')}
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
        Back to Architecture
      </button>
    </div>
  );
};

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const ArchitectureDetailRouter: React.FC = () => {
  const { concept } = useParams<{ concept: string }>();

  if (!concept) {
    return <NotFoundState concept="" />;
  }

  const DetailComponent = conceptComponents[concept];

  if (!DetailComponent) {
    return <NotFoundState concept={concept} />;
  }

  return (
    <Suspense fallback={<LoadingFallback />}>
      <DetailComponent />
    </Suspense>
  );
};

export default ArchitectureDetailRouter;
