/**
 * Eyebrow — Monospace uppercase label with burgundy dot.
 *
 * Uses Daylight mono + small size tokens (--at-mono / --dl-fs-small).
 *
 * Requirements: 15.4
 */

import React from 'react';

export interface EyebrowProps {
  label: string;
  variant?: 'burgundy' | 'muted';
  className?: string;
}

export const Eyebrow: React.FC<EyebrowProps> = ({
  label,
  variant = 'burgundy',
  className = '',
}) => {
  const dotColor =
    variant === 'burgundy' ? 'var(--at-red-1)' : 'var(--at-ink-4)';
  const textColor =
    variant === 'burgundy' ? 'var(--at-red-1)' : 'var(--at-ink-4)';

  return (
    <span
      className={className.trim()}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        fontFamily: 'var(--at-mono)',
        fontSize: 'var(--dl-fs-small)',
        fontWeight: 600,
        letterSpacing: 'var(--at-eyebrow-tracking)',
        textTransform: 'uppercase',
        color: textColor,
        lineHeight: 1,
        fontFeatureSettings: "'calt' 1, 'liga' 1",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          display: 'inline-block',
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          backgroundColor: dotColor,
          flexShrink: 0,
        }}
      />
      {label}
    </span>
  );
};
