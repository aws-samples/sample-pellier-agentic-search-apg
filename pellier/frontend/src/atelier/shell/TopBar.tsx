/**
 * TopBar — Horizontal bar above the Atelier canvas.
 *
 * Contains the SurfaceToggle (reused from existing component),
 * a BreadcrumbTrail derived from the current route, live status
 * metadata, and the persona avatar.
 *
 * Requirements: 1.9, 1.10, 1.11, 1.12
 */

import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import SurfaceToggle from '../../components/SurfaceToggle';
import { BreadcrumbTrail } from '../components/BreadcrumbTrail';
import { usePersona } from '../../contexts/PersonaContext';
import { getPersonaPhoto } from '../../data/personaPhotos';

/* -----------------------------------------------------------------------
 * Route → breadcrumb mapping
 * ----------------------------------------------------------------------- */

/** Prettify a route segment into a human-readable breadcrumb label. */
function prettifySegment(segment: string): string {
  // Known labels
  const labels: Record<string, string> = {
    atelier: 'Atelier',
    sessions: 'Sessions',
    observatory: 'Observatory',
    architecture: 'Architecture',
    agents: 'Agents',
    tools: 'Tools',
    routing: 'Routing',
    memory: 'Memory',
    performance: 'Performance',
    evaluations: 'Evaluations',
    settings: 'Settings',
    chat: 'Chat',
    telemetry: 'Telemetry',
    brief: 'Brief',
  };

  return labels[segment.toLowerCase()] ?? segment;
}

function useBreadcrumbs(): string[] {
  const { pathname } = useLocation();

  return useMemo(() => {
    const parts = pathname
      .split('/')
      .filter(Boolean)
      .map(prettifySegment);

    // Always start with "Atelier" — it's the root
    if (parts.length === 0) return ['Atelier'];
    return parts;
  }, [pathname]);
}

/* -----------------------------------------------------------------------
 * TopBar component
 * ----------------------------------------------------------------------- */

const TopBar: React.FC = () => {
  const breadcrumbs = useBreadcrumbs();
  const { persona } = usePersona();

  const avatarInitial = persona?.avatar_initial ?? 'M';
  const avatarColor = persona?.avatar_color ?? '#a8423a';

  return (
    <header
      data-testid="atelier-topbar"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '12px 24px',
        borderBottom: '1px solid var(--at-rule-1)',
        background: 'var(--at-cream-1)',
        minHeight: '52px',
      }}
    >
      {/* Surface toggle */}
      <SurfaceToggle />

      {/* Breadcrumb trail */}
      <BreadcrumbTrail segments={breadcrumbs} />

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Live status metadata */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          fontFamily: 'var(--at-mono)',
          fontSize: '10px',
          fontWeight: 500,
          letterSpacing: '0.08em',
          color: 'var(--at-ink-4)',
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: 'var(--at-green-1)',
            flexShrink: 0,
          }}
        />
        CONNECTED
      </div>

      {/* Persona avatar */}
      {(() => {
        const photoUrl = getPersonaPhoto(persona?.id);
        return photoUrl ? (
          <img
            src={photoUrl}
            alt={persona?.display_name ?? 'Marco'}
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              objectFit: 'cover',
              flexShrink: 0,
              border: '1.5px solid rgba(31, 20, 16, 0.1)',
            }}
          />
        ) : (
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              background: avatarColor,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--at-sans)',
              fontSize: '13px',
              fontWeight: 600,
              color: '#fff',
              flexShrink: 0,
            }}
            title={persona?.display_name ?? 'Marco'}
          >
            {avatarInitial}
          </div>
        );
      })()}
    </header>
  );
};

export default TopBar;
