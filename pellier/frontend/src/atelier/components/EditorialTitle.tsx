/**
 * EditorialTitle — Page-level title block (eyebrow + Fraunces title + summary paragraph).
 *
 * Used at the top of each Atelier surface for consistent editorial hierarchy.
 *
 * Requirements: 15.3, 15.7
 */

import React from 'react';
import { Eyebrow } from './Eyebrow';

export interface EditorialTitleProps {
  eyebrow: string;
  title: string;
  summary?: string;
  className?: string;
}

export const EditorialTitle: React.FC<EditorialTitleProps> = ({
  eyebrow,
  title,
  summary,
  className = '',
}) => {
  return (
    <header
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        marginBottom: '32px',
      }}
    >
      <Eyebrow label={eyebrow} />

      <h1
        className="font-display italic text-espresso"
        style={{
          fontSize: 'clamp(44px, 6vw, 76px)',
          lineHeight: 1.05,
          letterSpacing: '-0.015em',
          fontWeight: 400,
          margin: 0,
        }}
      >
        {title}
      </h1>

      {summary && (
        <p
          className="font-sans text-ink-soft"
          style={{
            fontSize: 'clamp(15px, 1.2vw, 17px)',
            lineHeight: 1.65,
            maxWidth: '640px',
            margin: 0,
          }}
        >
          {summary}
        </p>
      )}
    </header>
  );
};
