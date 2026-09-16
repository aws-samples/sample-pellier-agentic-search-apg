/**
 * Pellier Observatory top bar.
 *
 * The governed workbench is the primary destination. Deeper evidence routes
 * are linked from the collection and workbench rather than becoming another
 * first-level navigation surface.
 */

import React from 'react';
import { LibraryBig, ScanLine, ShieldCheck } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { usePersona } from '../../contexts/PersonaContext';
import { PresencePill } from '../../shared';
import { NAV } from '../../copy';

const OBSERVATORY_TABS = [
  {
    label: 'Lab Collection',
    path: '/observatory',
    icon: LibraryBig,
  },
  { label: 'Workbench', path: '/observatory/workbench', icon: ScanLine },
  { label: 'Govern', path: '/observatory/govern', icon: ShieldCheck },
] as const;

const TopBar: React.FC = () => {
  const { pathname } = useLocation();
  const { persona } = usePersona();
  const isGovern = pathname === '/observatory/govern' ||
    pathname.startsWith('/observatory/govern/') || pathname === '/observatory/write-path';
  const isCollection = pathname === '/observatory' || pathname === '/observatory/' ||
    pathname.startsWith('/observatory/labs');

  return (
    <header className="observatory-topbar" data-testid="observatory-topbar">
      <div className="observatory-topbar-start">
        <Link to="/observatory" className="observatory-wordmark">
          {NAV.OBSERVATORY}
        </Link>
      </div>

      <nav className="observatory-tabs" aria-label="Pellier Observatory views">
        {OBSERVATORY_TABS.map((tab) => {
          const isActive = tab.path === '/observatory'
            ? isCollection
            : tab.path === '/observatory/govern' ? isGovern : !isGovern && !isCollection;
          const TabIcon = tab.icon;
          return (
            <Link
              key={tab.path}
              to={tab.path}
              className="observatory-tab"
              data-active={isActive ? 'true' : undefined}
              aria-current={isActive ? 'page' : undefined}
            >
              <TabIcon size={17} strokeWidth={1.6} aria-hidden="true" />
              <span>{tab.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="observatory-topbar-end">
        <div className="observatory-presence">
          <PresencePill surface="observatory" personaId={persona?.id} />
        </div>

      </div>
    </header>
  );
};

export default TopBar;
