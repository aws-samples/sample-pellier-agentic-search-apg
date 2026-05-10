/**
 * ModeStrip — Routing pattern pill toggles.
 *
 * Displays a row of pill-shaped toggles for switching between routing
 * patterns (Dispatcher, Agents-as-Tools, Graph). The active pattern
 * gets a filled style.
 *
 * Requirements: 15.3
 */

import React from 'react';

export interface ModeStripProps {
  patterns: string[];
  active: string;
  onSelect?: (pattern: string) => void;
  className?: string;
}

export const ModeStrip: React.FC<ModeStripProps> = ({
  patterns,
  active,
  onSelect,
  className = '',
}) => {
  return (
    <div
      role="radiogroup"
      aria-label="Routing pattern"
      className={className}
      style={{
        display: 'flex',
        gap: '8px',
        flexWrap: 'wrap',
      }}
    >
      {patterns.map((pattern) => {
        const isActive = pattern === active;

        return (
          <button
            key={pattern}
            role="radio"
            aria-checked={isActive}
            onClick={() => onSelect?.(pattern)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '5px 14px',
              borderRadius: '999px',
              border: isActive
                ? '1px solid var(--at-ink-1)'
                : '1px solid var(--at-rule-2)',
              backgroundColor: isActive ? 'var(--at-ink-1)' : 'transparent',
              color: isActive ? 'var(--at-cream-1)' : 'var(--at-ink-1)',
              fontFamily: 'var(--at-mono)',
              fontSize: '10px',
              fontWeight: 500,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              transition:
                'background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease',
              whiteSpace: 'nowrap',
            }}
          >
            {pattern}
          </button>
        );
      })}
    </div>
  );
};
