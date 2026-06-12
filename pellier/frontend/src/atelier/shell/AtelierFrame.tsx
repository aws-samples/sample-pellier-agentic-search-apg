/**
 * AtelierFrame — Root layout shell for the Atelier Observatory.
 *
 * Renders a 240px sidebar + flexible canvas grid. The canvas area
 * contains the TopBar and a React Router `<Outlet />` for nested
 * route rendering.
 *
 * Requirements: 1.1, 20.1
 */

import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import AtelierErrorBoundary from './AtelierErrorBoundary';
import '../styles/base.css';

const AtelierFrame: React.FC = () => {
  // Key the error boundary on the pathname so a crash on one surface doesn't
  // strand the operator on every other surface — navigating remounts it,
  // clearing stale error state.
  const { pathname } = useLocation();
  return (
    <div className="atelier-root">
      <div className="atelier-frame">
        <Sidebar />
        <div className="atelier-canvas">
          <TopBar />
          <main className="atelier-surface">
            <AtelierErrorBoundary key={pathname}>
              <Outlet />
            </AtelierErrorBoundary>
          </main>
        </div>
      </div>
    </div>
  );
};

export default AtelierFrame;
