/**
 * BreadcrumbTrail — Dot-separated JetBrains Mono uppercase breadcrumb from route path.
 *
 * Renders a navigation breadcrumb trail with dot separators in the
 * Atelier monospace style.
 *
 * Requirements: 15.3
 */

import React from 'react';

export interface BreadcrumbTrailProps {
  segments: string[];
  className?: string;
}

export const BreadcrumbTrail: React.FC<BreadcrumbTrailProps> = ({
  segments,
  className = '',
}) => {
  if (segments.length === 0) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontFamily: 'var(--at-sans)',
        fontSize: '13px',
        fontWeight: 600,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: 'var(--at-ink-2)',
        lineHeight: 1,
      }}
    >
      <ol
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          listStyle: 'none',
          margin: 0,
          padding: 0,
        }}
      >
        {segments.map((segment, index) => {
          const isLast = index === segments.length - 1;

          return (
            <li
              key={index}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span
                style={{
                  color: isLast ? 'var(--at-ink-2)' : 'var(--at-ink-4)',
                }}
                aria-current={isLast ? 'page' : undefined}
              >
                {segment}
              </span>
              {!isLast && (
                <span
                  aria-hidden="true"
                  style={{
                    display: 'inline-block',
                    width: '3px',
                    height: '3px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--at-ink-5)',
                    flexShrink: 0,
                  }}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};
