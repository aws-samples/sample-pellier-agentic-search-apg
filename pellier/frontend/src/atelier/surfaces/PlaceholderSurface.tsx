/**
 * PlaceholderSurface — Temporary placeholder for surfaces not yet implemented.
 *
 * Renders the surface name in the Atelier editorial style. Each surface
 * will be replaced with its real implementation in later phases.
 */

import React from 'react';

interface PlaceholderSurfaceProps {
  name: string;
  description?: string;
}

const PlaceholderSurface: React.FC<PlaceholderSurfaceProps> = ({
  name,
  description,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        textAlign: 'center',
        maxWidth: '480px',
        margin: '0 auto',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: 'var(--at-eyebrow-size)',
          fontWeight: 500,
          letterSpacing: 'var(--at-eyebrow-tracking)',
          textTransform: 'uppercase',
          color: 'var(--at-ink-4)',
          marginBottom: '12px',
        }}
      >
        Coming soon
      </div>
      <h2
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '36px',
          lineHeight: 1.1,
          color: 'var(--at-ink-1)',
          marginBottom: '16px',
          fontWeight: 400,
        }}
      >
        {name}
      </h2>
      {description && (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.6,
            color: 'var(--at-ink-1)',
          }}
        >
          {description}
        </p>
      )}
    </div>
  );
};

export default PlaceholderSurface;
