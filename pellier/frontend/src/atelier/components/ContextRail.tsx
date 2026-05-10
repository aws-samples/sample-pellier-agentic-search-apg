/**
 * ContextRail — 360px right column wrapper for session detail views.
 *
 * Provides a fixed-width sidebar container used in two-column layouts
 * (ChatTab, TelemetryTab) for contextual information cards.
 *
 * Requirements: 15.3
 */

import React from 'react';

export interface ContextRailProps {
  children: React.ReactNode;
  className?: string;
}

export const ContextRail: React.FC<ContextRailProps> = ({
  children,
  className = '',
}) => {
  return (
    <aside
      className={className}
      style={{
        width: '360px',
        minWidth: '360px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        borderLeft: '1px solid var(--at-rule-1)',
        paddingLeft: '24px',
      }}
    >
      {children}
    </aside>
  );
};
