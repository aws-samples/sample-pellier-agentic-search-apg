/**
 * Observatory — Default /atelier landing: intro + where to go next.
 *
 * The dismissible AtelierWelcome band plus a short EditorialTitle orient
 * the attendee; a single row of deep links follows the sidebar learning
 * sequence so participants move from narrative map to replay to system map.
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { AtelierWelcome, EditorialTitle } from '../../components';

const CTA_ITEMS: Array<{
  to: string;
  testId: string;
  step: string;
  title: string;
  hint: string;
}> = [
  {
    to: '/atelier/persona-journeys',
    testId: 'observatory-cta-persona-journeys',
    step: '01',
    title: 'Persona journeys',
    hint: 'Zoom out to Marco, Anna, and Theo: 15 Boutique turns across three Aurora capabilities.',
  },
  {
    to: '/atelier/sessions',
    testId: 'observatory-cta-sessions',
    step: '02',
    title: 'Sessions',
    hint: 'Open the signed-in persona replay and inspect chat, telemetry, and brief.',
  },
  {
    to: '/atelier/architecture',
    testId: 'observatory-cta-architecture',
    step: '03',
    title: 'Architecture',
    hint: 'Then move into the system map: agents, skills, tools, routing, memory, and writes.',
  },
];

const Observatory: React.FC = () => {
  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <AtelierWelcome />

      <EditorialTitle
        eyebrow="Observe · Observatory · system overview"
        title="The wide-angle view."
        summary="A lightweight lobby before you drill in. Start with the persona story, replay one journey in depth, then open the architecture map once the moving parts have names."
      />

      <section aria-label="Where to go next">
        <p
          className="font-mono font-semibold uppercase"
          style={{
            fontSize: '11px',
            letterSpacing: '0.22em',
            color: 'var(--at-red-1)',
            margin: '0 0 14px',
          }}
        >
          Start here
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '16px',
          }}
        >
          {CTA_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                padding: '22px 24px',
                borderRadius: 'var(--at-card-radius)',
                border: '1px solid var(--at-card-border)',
                background: 'var(--at-card-bg)',
                textDecoration: 'none',
                color: 'inherit',
                boxShadow: '0 2px 10px rgba(45, 24, 16, 0.04)',
                transition: 'border-color 160ms ease, box-shadow 160ms ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--at-red-1)';
                e.currentTarget.style.boxShadow =
                  '0 4px 18px rgba(45, 24, 16, 0.08)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--at-card-border)';
                e.currentTarget.style.boxShadow =
                  '0 2px 10px rgba(45, 24, 16, 0.04)';
              }}
            >
              <span
                className="font-mono"
                style={{
                  fontSize: '11px',
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  color: 'var(--at-red-1)',
                }}
              >
                {item.step}
              </span>
              <span
                className="font-display italic text-espresso"
                style={{
                  fontSize: 'clamp(22px, 2.4vw, 28px)',
                  lineHeight: 1.15,
                  fontWeight: 400,
                  letterSpacing: '-0.015em',
                }}
              >
                {item.title}
              </span>
              <span
                className="font-sans text-ink-soft"
                style={{
                  fontSize: '14px',
                  lineHeight: 1.55,
                }}
              >
                {item.hint}
              </span>
              <span
                className="font-mono"
                style={{
                  marginTop: '4px',
                  fontSize: '11px',
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  color: 'var(--at-red-1)',
                }}
              >
                Open →
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
};

export default Observatory;
