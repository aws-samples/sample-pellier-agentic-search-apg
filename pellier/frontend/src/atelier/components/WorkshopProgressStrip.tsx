/**
 * WorkshopProgressStrip — Segment bar with solid (shipped) and dashed (exercise) segments.
 *
 * Displays a horizontal bar of segments where shipped items are solid fills
 * and exercise items are dashed outlines, plus a shipped/total fraction label.
 *
 * Requirements: 15.3, 17.3
 */

import React from 'react';

export interface Segment {
  id: string;
  label: string;
  status: 'shipped' | 'exercise';
}

export interface WorkshopProgressStripProps {
  segments: Segment[];
  shipped: number;
  total: number;
  className?: string;
}

export const WorkshopProgressStrip: React.FC<WorkshopProgressStripProps> = ({
  segments,
  shipped,
  total,
  className = '',
}) => {
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
      }}
    >
      {/* Segment bar */}
      <div
        role="img"
        aria-label={`Workshop progress: ${shipped} of ${total} shipped`}
        style={{
          display: 'flex',
          gap: '4px',
          flex: 1,
        }}
      >
        {segments.map((seg) => (
          <div
            key={seg.id}
            title={seg.label}
            style={{
              flex: 1,
              height: '6px',
              borderRadius: '3px',
              ...(seg.status === 'shipped'
                ? {
                    backgroundColor: 'var(--at-green-1)',
                  }
                : {
                    backgroundColor: 'transparent',
                    border: '1.5px dashed var(--at-red-1)',
                  }),
            }}
          />
        ))}
      </div>

      {/* Fraction label */}
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          fontWeight: 500,
          color: 'var(--at-ink-1)',
          letterSpacing: '0.04em',
          whiteSpace: 'nowrap',
        }}
      >
        {shipped}/{total}
      </span>
    </div>
  );
};
