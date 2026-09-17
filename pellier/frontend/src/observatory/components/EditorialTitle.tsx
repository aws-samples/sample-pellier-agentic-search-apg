/**
 * EditorialTitle — the one page-title block on the Observatory.
 *
 * Back link, section label, Fraunces title, summary. Three title grammars
 * used to ship at once: this one, the architecture detail pages' italic
 * 56px with a mono roman-numeral label, and the workbench's sans 38/600.
 * The detail pages now come through here, so the surface has one page-title
 * step and one label register.
 *
 * `aside` is the slot the detail pages needed: a CategoryBadge sits beside
 * the section label rather than becoming a second, competing label.
 *
 * Requirements: 15.3, 15.7
 */

import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Eyebrow } from './Eyebrow';
import ReferenceBrief, { referenceReturnHref } from './ReferenceBrief';
import type { ReferenceId } from './referenceCatalog';

export interface EditorialTitleBackLink {
  /** Route to return to. */
  to: string;
  /** Visible label, e.g. "Back to Architecture". */
  label: string;
  /** Accessible name, when the visible label needs more context. */
  ariaLabel?: string;
}

export interface EditorialTitleProps {
  eyebrow: string;
  title: string;
  summary?: string;
  className?: string;
  backToReferences?: boolean;
  referenceId?: ReferenceId;
  /** A back link to somewhere other than the workbench resources index. */
  backTo?: EditorialTitleBackLink;
  /** Rendered inline after the eyebrow. One badge, not a second label. */
  aside?: React.ReactNode;
}

const REFERENCES_BACK_LINK: EditorialTitleBackLink = {
  to: '/observatory#resources',
  label: 'Lab references',
  ariaLabel: 'Back to lab references',
};

export const EditorialTitle: React.FC<EditorialTitleProps> = ({
  eyebrow,
  title,
  summary,
  className = '',
  backToReferences = false,
  referenceId,
  backTo,
  aside,
}) => {
  const back = backTo ?? (backToReferences ? { ...REFERENCES_BACK_LINK, to: referenceReturnHref() } : undefined);

  return (
    <>
    <header
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        marginBottom: '32px',
      }}
    >
      {back ? (
        <Link
          to={back.to}
          className="observatory-reference-return"
          aria-label={back.ariaLabel ?? back.label}
        >
          <ArrowLeft size={15} strokeWidth={1.8} aria-hidden="true" />
          <span>{back.label}</span>
        </Link>
      ) : null}

      {aside ? (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '10px',
            flexWrap: 'wrap',
          }}
        >
          <Eyebrow label={eyebrow} />
          {aside}
        </span>
      ) : (
        <Eyebrow label={eyebrow} />
      )}

      {/* Size, leading, weight and tracking come from
          `.observatory-page-title` so every route shares one page-title step.
          Inline values here previously won over the class and let each surface
          drift to its own size. */}
      <h1
        className="observatory-page-title font-display text-espresso"
        style={{ margin: 0 }}
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
    {referenceId && <ReferenceBrief id={referenceId} />}
    </>
  );
};
