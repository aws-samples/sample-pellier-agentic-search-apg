/**
 * Pellier Observatory top bar.
 *
 * Two places: the Lab Collection, where the labs start, and the Workbench.
 * Every other view belongs to a lab and is reached from the lab guide under
 * the shared navigation, or from the page that needs it. Govern was a third
 * tab and also Lab 4's reference view; it now lives with Lab 4 only.
 */

import React from 'react';
import { LibraryBig, ScanLine } from 'lucide-react';
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
] as const;

const TopBar: React.FC = () => {
  const { pathname } = useLocation();
  const { persona } = usePersona();
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
          const isActive = tab.path === '/observatory' ? isCollection : !isCollection;
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
