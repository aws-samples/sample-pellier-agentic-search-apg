/**
 * Workshop Map — the route index for the Observatory.
 *
 * Named for what it shows. The file was called `Observatory.tsx` while the
 * navigation labelled it "Workshop Map", which left the surface's own name
 * pointing at one page inside it. The shell is the Observatory; this is the
 * map of it.
 *
 * The page mirrors the four required labs so participants never have to
 * translate between two workshop taxonomies.
 */

import React from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

type LinkItem = {
  to: string;
  label: string;
  detail: string;
  testId?: string;
};

type LabItem = {
  lab: string;
  title: string;
  summary: string;
  primary: LinkItem;
  secondary: LinkItem[];
};

type PillarItem = {
  verb: string;
  title: string;
  description: string;
};

const PILLARS: PillarItem[] = [
  {
    verb: 'Verify',
    title: 'Proof Board',
    description:
      'Read live evidence checkpoints in the same order as the four required labs, with a terminal or SQL fallback on every card.',
  },
  {
    verb: 'Inspect',
    title: 'Tools, retrieval, memory, policy',
    description:
      'Open one focused view when the lab calls for it, then return to Pellier or Code Editor for the canonical proof.',
  },
];

const LABS: LabItem[] = [
  {
    lab: 'Lab 1',
    title: 'Build a PostgreSQL-Grounded Agent',
    summary:
      "Complete Inventory Agent and check_inventory, then prove Marco's warehouse turn against live Aurora inventory and tool_audit.",
    primary: {
      to: '/observatory/proof-board#marco-floor-check',
      label: 'Open check_inventory proof',
      detail: 'Lab 1 checkpoint',
      testId: 'observatory-cta-proof-board',
    },
    secondary: [
      {
        to: '/observatory/tools',
        label: 'Tool Registry',
        detail: 'Before-and-after visual',
      },
    ],
  },
  {
    lab: 'Lab 2',
    title: 'Build and Measure PostgreSQL Hybrid Retrieval',
    summary:
      "Verify recorded rank fusion, inspect a query plan, and widen Anna's rerank candidate pool. Prove one eligible candidate was recovered without relaxing price or stock constraints.",
    primary: {
      to: '/observatory/performance',
      label: 'Open retrieval comparison',
      detail: 'Pellier Observatory visual',
    },
    secondary: [
      {
        to: '/observatory/proof-board#retrieval-comparison',
        label: 'Retrieval checkpoint',
        detail: 'Lab 2 proof card',
      },
      {
        to: '/observatory/search',
        label: 'Search Pipeline',
        detail: 'Mechanism read',
      },
    ],
  },
  {
    lab: 'Lab 3',
    title: 'Deploy and Operate Agents with Amazon Bedrock AgentCore',
    summary:
      "Publish Theo's customer-scoped read and deploy. Use a learned preference in a new conversation, check current products in Aurora, and verify the running build and trace.",
    primary: {
      to: '/observatory/proof-board#managed-rail',
      label: 'Open Lab 3 proofs',
      detail: 'Managed rail and audit evidence',
    },
    secondary: [
      {
        to: '/observatory/memory',
        label: 'Memory',
        detail: 'Conversation events and learned preferences',
      },
      {
        to: '/observatory/proof-board#audit-ledger',
        label: 'Audit proof',
        detail: 'SQL remains canonical',
      },
    ],
  },
  {
    lab: 'Lab 4',
    title: 'Build Governed Agent Actions with Cedar',
    summary:
      'Build the Cedar ownership rule and keyed absence query. Distinguish denial, business refusal, committed return, and replay. Test RLS independently and investigate Jessica\'s case as Operator.',
    primary: {
      to: '/observatory/govern/policies',
      label: 'Open Cedar policies',
      detail: 'Pellier Observatory visual',
    },
    secondary: [
      {
        to: '/observatory/proof-board#runtime-gateway-policy',
        label: 'Policy checkpoint',
        detail: 'Lab 4 proof card',
      },
      {
        to: '/observatory/proof-board#managed-rail',
        label: 'Governed receipt',
        detail: 'Runtime, Gateway, and JWT',
      },
    ],
  },
];

const cardStyle: React.CSSProperties = {
  border: '1px solid var(--obs-card-border)',
  borderRadius: '8px',
  background: 'var(--obs-card-bg)',
  boxShadow: '0 2px 10px rgba(45, 24, 16, 0.04)',
};

const eyebrowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  fontFamily: 'var(--obs-mono)',
  fontSize: '11px',
  fontWeight: 600,
  letterSpacing: '0.18em',
  lineHeight: 1,
  textTransform: 'uppercase',
  color: 'var(--obs-red-1)',
};

const SectionEyebrow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={eyebrowStyle}>
    <span
      aria-hidden="true"
      style={{
        width: '6px',
        height: '6px',
        borderRadius: '50%',
        background: 'var(--obs-red-1)',
        flexShrink: 0,
      }}
    />
    {children}
  </div>
);

const ActionLink: React.FC<LinkItem & { primary?: boolean }> = ({
  to,
  label,
  detail,
  testId,
  primary = false,
}) => (
  <Link
    to={to}
    data-testid={testId}
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '12px',
      padding: primary ? '12px 0 13px' : '10px 0',
      color: 'inherit',
      textDecoration: 'none',
      borderTop: primary ? '1px solid var(--obs-rule-1)' : 'none',
      borderBottom: '1px solid var(--obs-rule-1)',
    }}
  >
    <span style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 0 }}>
      <span
        className="font-sans"
        style={{
          color: primary ? 'var(--obs-red-1)' : 'var(--obs-ink-1)',
          fontSize: primary ? '15px' : '14px',
          fontWeight: 600,
          lineHeight: 1.25,
        }}
      >
        {label}
      </span>
      <span
        className="font-mono"
        style={{
          color: 'var(--obs-ink-3)',
          fontSize: 'var(--text-label)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          lineHeight: 1.35,
        }}
      >
        {detail}
      </span>
    </span>
    <ArrowRight
      aria-hidden="true"
      size={16}
      strokeWidth={2}
      style={{ color: 'var(--obs-red-1)', flexShrink: 0 }}
    />
  </Link>
);

const PillarCard: React.FC<PillarItem> = ({ verb, title, description }) => (
  <article
    style={{
      border: '1px solid var(--obs-rule-1)',
      borderRadius: '8px',
      background: 'var(--obs-cream-2)',
      padding: '18px 20px',
    }}
  >
    <div
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: 'var(--text-label)',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color: 'var(--obs-red-1)',
        fontWeight: 600,
        marginBottom: '8px',
      }}
    >
      {verb}
    </div>
    <h3
      className="font-display italic text-espresso"
      style={{
        fontSize: '22px',
        fontWeight: 400,
        lineHeight: 1.2,
        letterSpacing: 0,
        margin: '0 0 8px',
      }}
    >
      {title}
    </h3>
    <p
      className="font-sans text-ink-soft"
      style={{
        fontSize: '13px',
        lineHeight: 1.55,
        margin: 0,
      }}
    >
      {description}
    </p>
  </article>
);

const LabCard: React.FC<LabItem> = ({ lab, title, summary, primary, secondary }) => (
  <article
    style={{
      ...cardStyle,
      padding: '22px',
      display: 'grid',
      gap: '18px',
    }}
  >
    <div>
      <SectionEyebrow>{lab}</SectionEyebrow>
      <h3
        className="font-display italic text-espresso"
        style={{
          fontSize: '30px',
          fontWeight: 400,
          lineHeight: 1.12,
          letterSpacing: 0,
          margin: '14px 0 10px',
        }}
      >
        {title}
      </h3>
      <p
        className="font-sans text-ink-soft"
        style={{
          fontSize: '15px',
          lineHeight: 1.55,
          margin: 0,
        }}
      >
        {summary}
      </p>
    </div>

    <ActionLink {...primary} primary />

    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        columnGap: '18px',
      }}
    >
      {secondary.map((item) => (
        <ActionLink key={`${lab}-${item.to}-${item.label}`} {...item} />
      ))}
    </div>
  </article>
);

const WorkshopMap: React.FC = () => {
  return (
    <div style={{ padding: '40px 48px', maxWidth: '1180px' }}>
      <section
        aria-labelledby="workshop-map-title"
        style={{
          padding: '8px 0 4px',
          marginBottom: '34px',
        }}
      >
        {/* The eyebrow used to read "Workshop map" while the title read "The
            workshop, in one view." — the label named the page and the heading
            sold it. The heading names it now, so the label is redundant. */}
        <h1
          id="workshop-map-title"
          className="observatory-page-title font-display text-espresso"
          style={{ margin: '0 0 14px', maxWidth: '820px' }}
        >
          Workshop map
        </h1>
        <p
          className="font-sans text-ink-soft"
          style={{
            fontSize: '16px',
            lineHeight: 1.6,
            margin: '0 0 26px',
            maxWidth: '760px',
          }}
        >
          Pellier and Code Editor remain the primary work surfaces. Pellier Observatory is
          the evidence layer: open the checkpoint named by the current lab,
          inspect it, then return to the required path.
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '14px',
          }}
        >
          {PILLARS.map((pillar) => (
            <PillarCard key={pillar.verb} {...pillar} />
          ))}
        </div>
      </section>

      <section aria-labelledby="workshop-path-title" style={{ marginBottom: '36px' }}>
        <SectionEyebrow>Workshop path</SectionEyebrow>
        <h2
          id="workshop-path-title"
          className="font-display italic text-espresso"
          style={{
            fontSize: '38px',
            fontWeight: 400,
            lineHeight: 1.1,
            letterSpacing: 0,
            margin: '14px 0 8px',
          }}
        >
          Start with the required path.
        </h2>
        <p
          className="font-sans text-ink-soft"
          style={{
            fontSize: '15px',
            lineHeight: 1.55,
            margin: '0 0 18px',
            maxWidth: '720px',
          }}
        >
          The labels and order below match Workshop Studio exactly. Each card
          points to the narrow Pellier Observatory view for that lab; terminal and SQL
          commands remain the canonical proof.
        </p>
        <div style={{ display: 'grid', gap: '16px' }}>
          {LABS.map((item) => (
            <LabCard key={item.lab} {...item} />
          ))}
        </div>
      </section>

    </div>
  );
};

export default WorkshopMap;
