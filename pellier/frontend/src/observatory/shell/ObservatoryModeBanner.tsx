/**
 * States whether the current Labs view can be operated or only inspected.
 */

import React from 'react';
import { BookOpen } from 'lucide-react';
import { useLocation } from 'react-router-dom';

import { interactionForPath, modeCopyForPath } from './observatoryInteraction';

const ObservatoryModeBanner: React.FC = () => {
  const { pathname } = useLocation();
  const mode = interactionForPath(pathname);
  const copy = modeCopyForPath(pathname);

  // These retired guide routes redirect to the corresponding workspace.
  if (pathname.startsWith('/observatory/labs/') || pathname.startsWith('/observatory/guide/')) return null;

  return (
    <div className="labs-mode-banner" data-mode={mode}>
      <span className="labs-mode-banner-label">
        {mode === 'reference' ? (
          <BookOpen size={13} strokeWidth={1.8} aria-hidden="true" />
        ) : null}
        {copy.label}
      </span>
      <p className="labs-mode-banner-detail">{copy.detail}</p>
    </div>
  );
};

export default ObservatoryModeBanner;
