/**
 * ExpCard — Elevated cream card with burgundy accent line.
 *
 * cream-elev background, 1px rule-1 border, 14px border-radius,
 * 24px burgundy accent line at top-left.
 *
 * Requirements: 15.3
 */

import React from 'react';

export interface ExpCardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const ExpCard: React.FC<ExpCardProps> = ({
  children,
  className = '',
  onClick,
}) => {
  const isClickable = !!onClick;

  return (
    <div
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={className}
      style={{
        position: 'relative',
        background: 'var(--at-card-bg)',
        border: '1px solid var(--at-card-border)',
        borderRadius: 'var(--at-card-radius)',
        padding: '24px',
        cursor: isClickable ? 'pointer' : undefined,
        overflow: 'hidden',
      }}
    >
      {/* Burgundy accent line at top-left */}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          left: '20px',
          width: 'var(--at-card-accent-width)',
          height: '3px',
          backgroundColor: 'var(--at-card-accent-color)',
          borderRadius: '0 0 2px 2px',
        }}
      />
      {children}
    </div>
  );
};
