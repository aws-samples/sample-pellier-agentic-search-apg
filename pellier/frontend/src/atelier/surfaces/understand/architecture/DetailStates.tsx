/**
 * DetailStates — Shared loading, error, and empty states for architecture detail pages.
 *
 * Provides consistent editorial-style feedback states across all 8 detail pages.
 *
 * Requirements: 19.1, 19.2, 19.3, 19.4
 */

import React from 'react';
import { Eyebrow } from '../../../components';

/* -----------------------------------------------------------------------
 * Loading state — skeleton placeholders
 * ----------------------------------------------------------------------- */

export const DetailLoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
      {[0, 1].map((i) => (
        <div
          key={i}
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '240px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
    <div
      style={{
        background: 'var(--at-cream-2)',
        borderRadius: 'var(--at-card-radius)',
        height: '180px',
        opacity: 0.5,
        animation: 'pulse 1.5s ease-in-out infinite',
      }}
    />
  </div>
);

/* -----------------------------------------------------------------------
 * Error state — editorial message with retry button
 * ----------------------------------------------------------------------- */

interface DetailErrorStateProps {
  message: string;
  onRetry: () => void;
}

export const DetailErrorState: React.FC<DetailErrorStateProps> = ({ message, onRetry }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '60px 24px',
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
      We couldn't load this architecture detail.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '14px',
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
 * Empty state — fixture fallback message
 * ----------------------------------------------------------------------- */

interface DetailEmptyStateProps {
  conceptName: string;
}

export const DetailEmptyState: React.FC<DetailEmptyStateProps> = ({ conceptName }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '60px 24px',
      textAlign: 'center',
    }}
  >
    <Eyebrow label="No data" variant="muted" />
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
      No data available for {conceptName}.
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
      Check that the architecture fixture data is available and try again.
    </p>
  </div>
);
