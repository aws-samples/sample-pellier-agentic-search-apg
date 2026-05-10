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
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import AtelierErrorBoundary from './AtelierErrorBoundary';
import '../styles/base.css';

const AtelierFrame: React.FC = () => {
  return (
    <div className="atelier-root">
      <div className="atelier-frame">
        <Sidebar />
        <div className="atelier-canvas">
          <TopBar />
          <main className="atelier-surface">
            <AtelierErrorBoundary>
              <Outlet />
            </AtelierErrorBoundary>
          </main>
        </div>
      </div>
    </div>
  );
};

export default AtelierFrame;
