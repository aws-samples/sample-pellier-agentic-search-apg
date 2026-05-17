/**
 * CategoryBadge — participant-facing Architecture location badges.
 *
 * Each category maps to a specific color token from the design system.
 *
 * Requirements: 15.3
 */

import React from 'react';

export type CategoryType = 'live' | 'workshop' | 'optional' | 'quality';

export interface CategoryBadgeProps {
  category: CategoryType;
  className?: string;
}

const categoryConfig: Record<
  CategoryType,
  { label: string; color: string; bg: string }
> = {
  live: {
    label: 'Live path',
    color: 'var(--at-cat-both)',
    bg: 'var(--at-red-soft)',
  },
  workshop: {
    label: 'Workshop lens',
    color: 'var(--at-cat-teaching)',
    bg: 'rgba(31, 20, 16, 0.06)',
  },
  optional: {
    label: 'Optional infra',
    color: 'var(--at-cat-managed)',
    bg: 'var(--at-green-soft)',
  },
  quality: {
    label: 'Quality layer',
    color: 'var(--at-cat-owned)',
    bg: 'rgba(184, 138, 58, 0.12)',
  },
};

export const CategoryBadge: React.FC<CategoryBadgeProps> = ({
  category,
  className = '',
}) => {
  const { label, color, bg } = categoryConfig[category];

  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: '4px',
        backgroundColor: bg,
        color: color,
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        fontWeight: 600,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        lineHeight: 1.4,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
};
