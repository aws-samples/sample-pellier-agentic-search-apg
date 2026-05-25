/**
 * ProductionPatterns — Four production patterns underneath every shipped agent.
 *
 * Identity, Guardrails, Multi-tenancy & STM hygiene, Tool publishing & discovery.
 * The default builder path runs without any of them by design — they're the
 * seams you reach for once the prototype is real.
 *
 * This surface consolidates two cards that previously lived under Architecture
 * (MCP Gateway + Tool Registry) into the Tool Publishing pattern, and adds
 * three new patterns that don't have a home elsewhere in the Atelier.
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard, Eyebrow } from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type {
  ProductionPattern,
  ProductionPatternsData,
  IdentityPattern,
  GuardrailsPattern,
  MultitenancyPattern,
  ToolPublishingPattern,
} from '../../types';

/* -----------------------------------------------------------------------
 * Shared styles
 * ----------------------------------------------------------------------- */

const SNIPPET_STYLE: React.CSSProperties = {
  margin: 0,
  padding: '12px 14px',
  borderRadius: '8px',
  background: 'var(--at-cream-2)',
  border: '1px solid var(--at-card-border)',
  fontFamily: 'var(--at-mono)',
  fontSize: '13px',
  lineHeight: 1.55,
  color: 'var(--at-ink-2)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const CATEGORY_TONE: Record<ProductionPattern['category'], { label: string; color: string }> = {
  auth: { label: 'Auth', color: 'var(--at-red-1)' },
  policy: { label: 'Policy', color: 'var(--at-green-1)' },
  ops: { label: 'Ops', color: '#7c6f64' },
  scaling: { label: 'Scaling', color: 'var(--at-red-1)' },
};

/* -----------------------------------------------------------------------
 * Status pills — Shipped vs Available
 * ----------------------------------------------------------------------- */

const StatusPill: React.FC<{ shipped: boolean }> = ({ shipped }) => {
  const color = shipped ? 'var(--at-green-1)' : 'var(--at-ink-3)';
  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: 'var(--at-mono)',
        fontSize: '10px',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color,
        border: `1px solid ${color}`,
        borderRadius: '999px',
        padding: '3px 9px',
      }}
    >
      {shipped ? 'Shipped' : 'Available'}
    </span>
  );
};

/* -----------------------------------------------------------------------
 * Pattern card header — numeral + category badge + title + role
 * ----------------------------------------------------------------------- */

const PatternHeader: React.FC<{ pattern: ProductionPattern }> = ({ pattern }) => {
  const tone = CATEGORY_TONE[pattern.category];
  return (
    <>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '6px',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            letterSpacing: '0.22em',
            color: 'var(--at-ink-3)',
            fontWeight: 500,
          }}
        >
          {pattern.numeral}.
        </span>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '10px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: tone.color,
            backgroundColor: `color-mix(in srgb, ${tone.color} 12%, transparent)`,
            padding: '2px 8px',
            borderRadius: '4px',
            fontWeight: 600,
          }}
        >
          {tone.label}
        </span>
        <StatusPill shipped={pattern.shipped} />
      </div>
      <h2
        className="font-display"
        style={{
          fontSize: '28px',
          fontWeight: 400,
          lineHeight: 1.15,
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {pattern.title}
      </h2>
      <p
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '17px',
          color: 'var(--at-ink-2)',
          marginTop: '6px',
          margin: '6px 0 0',
        }}
      >
        {pattern.role}
      </p>
    </>
  );
};

const PatternSummary: React.FC<{ pattern: ProductionPattern }> = ({ pattern }) => (
  <>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '15px',
        lineHeight: 1.55,
        color: 'var(--at-ink-1)',
        marginTop: '14px',
      }}
    >
      {pattern.summary}
    </p>
    {pattern.shipped && pattern.shippedNote && (
      <p
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          color: 'var(--at-green-1)',
          marginTop: '8px',
          letterSpacing: '0.04em',
        }}
      >
        ✓ {pattern.shippedNote}
      </p>
    )}
  </>
);

/* -----------------------------------------------------------------------
 * Cross-link strip
 * ----------------------------------------------------------------------- */

const CrossLinkStrip: React.FC<{ links: { label: string; to: string }[] }> = ({
  links,
}) => {
  if (!links.length) return null;
  return (
    <div
      style={{
        marginTop: '18px',
        paddingTop: '14px',
        borderTop: '1px solid var(--at-card-border)',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '8px',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '10px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--at-ink-3)',
          marginRight: '4px',
        }}
      >
        See also ·
      </span>
      {links.map((l) => (
        <Link
          key={l.to}
          to={l.to}
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            letterSpacing: '0.04em',
            color: 'var(--at-red-1)',
            textDecoration: 'none',
            border: '1px solid var(--at-card-border)',
            borderRadius: '999px',
            padding: '4px 10px',
            backgroundColor: 'var(--at-cream-1)',
          }}
        >
          {l.label} →
        </Link>
      ))}
    </div>
  );
};

/* -----------------------------------------------------------------------
 * Identity card — namespace switch + workload identity
 * ----------------------------------------------------------------------- */

const IdentityCard: React.FC<{ pattern: IdentityPattern }> = ({ pattern }) => (
  <ExpCard>
    <PatternHeader pattern={pattern} />
    <PatternSummary pattern={pattern} />

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Namespace pattern" variant="muted" />
      <div
        style={{
          marginTop: '8px',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '10px',
        }}
      >
        <div
          style={{
            border: '1px solid var(--at-card-border)',
            borderRadius: '8px',
            padding: '10px 12px',
            backgroundColor: 'var(--at-cream-2)',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--at-ink-3)',
            }}
          >
            Anonymous
          </div>
          <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px', color: 'var(--at-ink-1)' }}>
            {pattern.namespacePattern.anon}
          </code>
        </div>
        <div
          style={{
            border: '1px solid var(--at-card-border)',
            borderRadius: '8px',
            padding: '10px 12px',
            backgroundColor: 'var(--at-cream-2)',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--at-ink-3)',
            }}
          >
            Signed in
          </div>
          <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px', color: 'var(--at-ink-1)' }}>
            {pattern.namespacePattern.signedIn}
          </code>
        </div>
      </div>
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '13px',
          color: 'var(--at-ink-2)',
          marginTop: '8px',
          fontStyle: 'italic',
        }}
      >
        {pattern.namespacePattern.note}
      </p>
    </div>

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Code · workload identity + namespace switch" variant="muted" />
      <pre style={{ ...SNIPPET_STYLE, marginTop: '8px' }}>{pattern.codeSnippet}</pre>
    </div>

    <div
      style={{
        marginTop: '14px',
        padding: '12px 14px',
        backgroundColor: 'color-mix(in srgb, var(--at-red-1) 5%, transparent)',
        borderLeft: '3px solid var(--at-red-1)',
        borderRadius: '4px',
      }}
    >
      <Eyebrow label="When to reach for it" variant="muted" />
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '14px',
          lineHeight: 1.55,
          color: 'var(--at-ink-1)',
          marginTop: '6px',
        }}
      >
        {pattern.whatToReachFor}
      </p>
    </div>

    <CrossLinkStrip links={pattern.crossLinks} />
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Guardrails card — layered policy
 * ----------------------------------------------------------------------- */

const GuardrailsCard: React.FC<{ pattern: GuardrailsPattern }> = ({ pattern }) => (
  <ExpCard>
    <PatternHeader pattern={pattern} />
    <PatternSummary pattern={pattern} />

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Layered policy · model boundary → application" variant="muted" />
      <div
        style={{
          marginTop: '10px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        {pattern.layers.map((layer, i) => (
          <div
            key={layer.name}
            style={{
              display: 'grid',
              gridTemplateColumns: '36px 200px 1fr',
              gap: '12px',
              alignItems: 'start',
              padding: '10px 12px',
              border: '1px solid var(--at-card-border)',
              borderRadius: '8px',
              backgroundColor: 'var(--at-cream-1)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                color: 'var(--at-ink-3)',
                letterSpacing: '0.04em',
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>
            <div>
              <div
                style={{
                  fontFamily: 'var(--at-sans)',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: 'var(--at-ink-1)',
                }}
              >
                {layer.name}
              </div>
              <div
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '11px',
                  color: 'var(--at-ink-3)',
                  marginTop: '2px',
                  letterSpacing: '0.04em',
                }}
              >
                {layer.where}
              </div>
            </div>
            <div
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '14px',
                lineHeight: 1.5,
                color: 'var(--at-ink-2)',
              }}
            >
              {layer.what}
            </div>
          </div>
        ))}
      </div>
    </div>

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Code · allow-list + Bedrock guardrail" variant="muted" />
      <pre style={{ ...SNIPPET_STYLE, marginTop: '8px' }}>{pattern.codeSnippet}</pre>
    </div>

    <CrossLinkStrip links={pattern.crossLinks} />
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Multi-tenancy card — concerns + answers
 * ----------------------------------------------------------------------- */

const MultitenancyCard: React.FC<{ pattern: MultitenancyPattern }> = ({ pattern }) => (
  <ExpCard>
    <PatternHeader pattern={pattern} />
    <PatternSummary pattern={pattern} />

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Operational concerns" variant="muted" />
      <div
        style={{
          marginTop: '10px',
          display: 'grid',
          gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
          gap: '10px',
        }}
      >
        {pattern.concerns.map((row) => (
          <div
            key={row.concern}
            style={{
              padding: '12px 14px',
              border: '1px solid var(--at-card-border)',
              borderRadius: '8px',
              backgroundColor: 'var(--at-cream-1)',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '10px',
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: 'var(--at-ink-3)',
              }}
            >
              {row.concern}
            </div>
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '14px',
                lineHeight: 1.5,
                color: 'var(--at-ink-1)',
                marginTop: '6px',
              }}
            >
              {row.answer}
            </p>
          </div>
        ))}
      </div>
    </div>

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Code · namespaced writes + tenant-safe vector search" variant="muted" />
      <pre style={{ ...SNIPPET_STYLE, marginTop: '8px' }}>{pattern.codeSnippet}</pre>
    </div>

    <CrossLinkStrip links={pattern.crossLinks} />
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Tool publishing card — surfaces table (Gateway / Aurora registry)
 * ----------------------------------------------------------------------- */

const ToolPublishingCard: React.FC<{ pattern: ToolPublishingPattern }> = ({
  pattern,
}) => (
  <ExpCard>
    <PatternHeader pattern={pattern} />
    <PatternSummary pattern={pattern} />

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Two surfaces, different scaling shapes" variant="muted" />
      <div
        style={{
          marginTop: '10px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        {pattern.surfaces.map((s) => (
          <div
            key={s.name}
            style={{
              padding: '14px 16px',
              border: '1px solid var(--at-card-border)',
              borderRadius: '8px',
              backgroundColor: 'var(--at-cream-1)',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '15px',
                fontWeight: 500,
                color: 'var(--at-ink-1)',
              }}
            >
              {s.name}
            </div>
            <div
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                color: 'var(--at-ink-3)',
                marginTop: '3px',
                letterSpacing: '0.04em',
              }}
            >
              {s.where}
            </div>
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '14px',
                lineHeight: 1.55,
                color: 'var(--at-ink-2)',
                marginTop: '8px',
              }}
            >
              {s.purpose}
            </p>
            <p
              style={{
                fontFamily: 'var(--at-serif)',
                fontStyle: 'italic',
                fontSize: '13px',
                color: 'var(--at-ink-2)',
                marginTop: '6px',
              }}
            >
              Tradeoff — {s.tradeoff}
            </p>
          </div>
        ))}
      </div>
    </div>

    <div style={{ marginTop: '18px' }}>
      <Eyebrow label="Code · gateway fallback + tool registry" variant="muted" />
      <pre style={{ ...SNIPPET_STYLE, marginTop: '8px' }}>{pattern.codeSnippet}</pre>
    </div>

    <CrossLinkStrip links={pattern.crossLinks} />
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Card dispatcher
 * ----------------------------------------------------------------------- */

const PatternCard: React.FC<{ pattern: ProductionPattern }> = ({ pattern }) => {
  switch (pattern.slug) {
    case 'identity':
      return <IdentityCard pattern={pattern} />;
    case 'guardrails':
      return <GuardrailsCard pattern={pattern} />;
    case 'multitenancy':
      return <MultitenancyCard pattern={pattern} />;
    case 'tool-publishing':
      return <ToolPublishingCard pattern={pattern} />;
  }
};

/* -----------------------------------------------------------------------
 * Loading / error states
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px 0' }}>
    {[0, 1, 2, 3].map((i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: '320px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
    ))}
  </div>
);

const ErrorState: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '80px 24px',
      textAlign: 'center',
    }}
  >
    <Eyebrow label="Something went wrong" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '22px',
        color: 'var(--at-ink-1)',
        marginTop: '16px',
      }}
    >
      We couldn't load the production patterns.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '13px',
        color: 'var(--at-ink-2)',
        marginTop: '6px',
      }}
    >
      {message}
    </p>
    <button
      type="button"
      onClick={onRetry}
      style={{
        marginTop: '20px',
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        color: 'var(--at-cream-1)',
        backgroundColor: 'var(--at-ink-1)',
        border: 'none',
        borderRadius: '8px',
        padding: '10px 22px',
        cursor: 'pointer',
      }}
    >
      Try again
    </button>
  </div>
);

/* -----------------------------------------------------------------------
 * Main surface
 * ----------------------------------------------------------------------- */

const ProductionPatterns: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ProductionPatternsData>({
    key: 'production-patterns',
  });

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Measure · Production patterns · identity · guardrails · tenancy · tools"
        title="What you reach for once it's real."
        summary={
          data?.summary ??
          'Four production patterns sit underneath every shipped agent. The default builder path runs without any of them — they are the seams you reach for once the prototype is real.'
        }
      />

      {loading && <LoadingState />}
      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {data.patterns.map((p) => (
            <PatternCard key={p.slug} pattern={p} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ProductionPatterns;
