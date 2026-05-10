/**
 * Eyebrow — Monospace uppercase label with burgundy dot.
 *
 * JetBrains Mono, 9-10px, letter-spacing 0.22em. Used as a section
 * identifier throughout the Atelier design system.
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
      className={`font-sans ${className}`.trim()}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '13px',
        fontWeight: 600,
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: textColor,
        lineHeight: 1,
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
