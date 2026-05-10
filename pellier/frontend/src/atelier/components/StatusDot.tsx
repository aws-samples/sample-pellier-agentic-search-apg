/**
 * StatusDot — Live (burgundy pulsing), idle (ink-4 muted), or empty (burgundy outline).
 *
 * Live uses the .at-pulse-live animation class from base.css.
 *
 * Requirements: 15.5
 */

import React from 'react';

export interface StatusDotProps {
  status: 'live' | 'idle' | 'empty';
  size?: number;
  className?: string;
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status,
  size = 8,
  className = '',
}) => {
  const baseStyle: React.CSSProperties = {
    display: 'inline-block',
    width: `${size}px`,
    height: `${size}px`,
    borderRadius: '50%',
    flexShrink: 0,
  };

  const statusLabel =
    status === 'live' ? 'Live' : status === 'idle' ? 'Idle' : 'Empty';

  if (status === 'live') {
    return (
      <span
        role="status"
        aria-label={statusLabel}
        className={`at-pulse-live ${className}`}
        style={{
          ...baseStyle,
          backgroundColor: 'var(--at-dot-live)',
        }}
      />
    );
  }

  if (status === 'idle') {
    return (
      <span
        role="status"
        aria-label={statusLabel}
        className={className}
        style={{
          ...baseStyle,
          backgroundColor: 'var(--at-dot-idle)',
        }}
      />
    );
  }

  // empty — outline only
  return (
    <span
      role="status"
      aria-label={statusLabel}
      className={className}
      style={{
        ...baseStyle,
        backgroundColor: 'transparent',
        border: `1.5px solid var(--at-dot-empty-border)`,
      }}
    />
  );
};
