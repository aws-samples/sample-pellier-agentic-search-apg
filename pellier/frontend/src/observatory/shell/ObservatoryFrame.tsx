/**
 * Full-width Pellier Observatory shell for live agent inspection.
 */

import React, { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import TopBar from './TopBar';
import ObservatoryContextBanner from './ObservatoryContextBanner';
import ObservatoryModeBanner from './ObservatoryModeBanner';
import ObservatoryErrorBoundary from './ObservatoryErrorBoundary';
import { interactionForPath } from './observatoryInteraction';
import '../styles/base.css';

/**
 * Tab, history and bookmark titles for each Observatory route. Every route
 * used to inherit the storefront's title from index.html, so a participant
 * with several Observatory tabs open could not tell them apart.
 */
const ROUTE_TITLES: ReadonlyArray<[prefix: string, title: string]> = [
  ['/observatory/govern/authentication', 'Authentication & JWTs'],
  ['/observatory/govern/permissions', 'Roles & permissions'],
  ['/observatory/govern/agent-access', 'Agent Access'],
  ['/observatory/govern/policies', 'Cedar policies'],
  ['/observatory/govern/actions', 'Governed actions'],
  ['/observatory/govern/verification', 'Evidence & verification'],
  ['/observatory/govern', 'Govern'],
  ['/observatory/proof-board', 'Proof Board'],
  ['/observatory/audit-proof', 'Audit proof'],
  ['/observatory/operator-lineage', 'Operator lineage'],
  ['/observatory/operator-turn', 'Operator turn evidence'],
  ['/observatory/replacement', 'Replacement recovery'],
  ['/observatory/workbench', 'Workbench'],
  ['/observatory/labs', 'Lab'],
  ['/observatory/sessions', 'Sessions'],
  ['/observatory/architecture', 'Architecture'],
  ['/observatory/tools', 'Tool Registry'],
  ['/observatory/search', 'Search pipeline'], // copy-allow: route title
  ['/observatory/skills', 'Skills'],
  ['/observatory/routing', 'Routing'],
  ['/observatory/memory', 'Memory'],
  ['/observatory/performance', 'Retrieval comparison'],
  ['/observatory/evaluations', 'Evaluations'],
  ['/observatory/production-patterns', 'Production patterns'],
  ['/observatory/workshop-map', 'Workshop map'],
  ['/observatory/settings', 'Settings'],
];

export function observatoryTitleForPath(pathname: string): string {
  const match = ROUTE_TITLES.find(
    ([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  const page = match ? match[1] : 'Lab Collection';
  return `${page} · Pellier Observatory`;
}

const ObservatoryFrame: React.FC = () => {
  // Key the error boundary on the pathname so a crash on one surface doesn't
  // strand the operator on every other surface — navigating remounts it,
  // clearing stale error state.
  const { pathname } = useLocation();
  const isLabsSurface =
    pathname === '/observatory' ||
    pathname === '/observatory/' ||
    pathname.startsWith('/observatory/labs');

  useEffect(() => {
    const previous = document.title;
    document.title = observatoryTitleForPath(pathname);
    return () => {
      document.title = previous;
    };
  }, [pathname]);

  return (
    <div className="observatory-root pellier-page-surface">
      <div className="observatory-frame">
        <div className="observatory-canvas">
          <TopBar />
          <ObservatoryContextBanner />
          <main
            className="observatory-surface"
            data-mode={interactionForPath(pathname)}
            data-labs={isLabsSurface ? 'true' : undefined}
            data-workbench={
              pathname === '/observatory/workbench' ||
              pathname.startsWith('/observatory/workbench/')
                ? 'true'
                : 'false'
            }
          >
            <ObservatoryModeBanner />
            <ObservatoryErrorBoundary key={pathname}>
              <Outlet />
            </ObservatoryErrorBoundary>
          </main>
        </div>
      </div>
    </div>
  );
};

export default ObservatoryFrame;
