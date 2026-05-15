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
  activeSegmentId?: string;
  onSegmentClick?: (segment: Segment) => void;
}

export const WorkshopProgressStrip: React.FC<WorkshopProgressStripProps> = ({
  segments,
  shipped,
  total,
  className = '',
  activeSegmentId,
  onSegmentClick,
}) => {
  const interactive = Boolean(onSegmentClick);

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
        role={interactive ? 'group' : 'img'}
        aria-label={`Workshop progress: ${shipped} of ${total} shipped`}
        style={{
          display: 'flex',
          gap: '4px',
          flex: 1,
        }}
      >
        {segments.map((seg) => {
          const isActive = activeSegmentId === seg.id;
          const segmentStyle: React.CSSProperties = {
            flex: 1,
            height: interactive ? '10px' : '6px',
            borderRadius: '3px',
            padding: 0,
            cursor: interactive ? 'pointer' : undefined,
            transform: isActive ? 'scaleY(1.35)' : undefined,
            transition: 'transform 0.15s ease, box-shadow 0.15s ease',
            ...(seg.status === 'shipped'
              ? {
                  backgroundColor: 'var(--at-green-1)',
                  boxShadow: isActive ? '0 0 0 2px var(--at-green-soft)' : undefined,
                }
              : {
                  backgroundColor: 'transparent',
                  border: '1.5px dashed var(--at-red-1)',
                  boxShadow: isActive ? '0 0 0 2px var(--at-red-soft)' : undefined,
                }),
          };

          if (interactive) {
            return (
              <button
                key={seg.id}
                type="button"
                title={seg.label}
                aria-label={`${seg.label} · ${seg.status}`}
                aria-pressed={isActive}
                onClick={() => onSegmentClick?.(seg)}
                style={segmentStyle}
              />
            );
          }

          return <div key={seg.id} title={seg.label} style={segmentStyle} />;
        })}
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
