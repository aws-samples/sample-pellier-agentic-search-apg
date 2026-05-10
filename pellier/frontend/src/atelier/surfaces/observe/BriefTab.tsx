/**
 * BriefTab — Curator's Brief: magazine-style editorial deconstruction.
 *
 * Single-column layout (max-width 620px, centered) with editorial typography.
 * Renders the full brief content from session data: title block, metadata grid,
 * numbered editorial sections with drop-caps, evidence panels, memory rows,
 * product cards, confidence display, and editorial footer.
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10
 */

import React from 'react';
import { useOutletContext } from 'react-router-dom';
import { Eyebrow, ExpCard } from '../../components';
import type { SessionOutletContext } from './SessionView';
import type { BriefSection, ProductCard } from '../../types';

/* =======================================================================
 * SQL keyword highlighter — reused from ChatTab pattern
 * ======================================================================= */

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'ORDER', 'BY', 'LIMIT', 'INSERT', 'UPDATE',
  'DELETE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'ON', 'AND', 'OR', 'AS',
  'ILIKE', 'LIKE', 'IN', 'NOT', 'NULL', 'IS', 'GROUP', 'HAVING', 'DISTINCT',
  'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'CREATE', 'TABLE', 'INDEX', 'DROP',
  'ALTER', 'SET', 'VALUES', 'INTO', 'BETWEEN', 'EXISTS', 'CASE', 'WHEN',
  'THEN', 'ELSE', 'END', 'ASC', 'DESC', 'OFFSET', 'FETCH', 'WITH',
]);

function highlightSql(sql: string): React.ReactNode[] {
  return sql.split(/(\s+|[(),;])/).map((token, i) => {
    if (SQL_KEYWORDS.has(token.toUpperCase())) {
      return (
        <span key={i} style={{ color: 'var(--at-red-1)', fontWeight: 600 }}>
          {token}
        </span>
      );
    }
    return <span key={i}>{token}</span>;
  });
}

/* =======================================================================
 * Helper: format ISO timestamp to readable date
 * ======================================================================= */

function formatFiledTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/* =======================================================================
 * Sub-components
 * ======================================================================= */

/** Inline trace pill — burgundy monospace badge referencing a telemetry step */
const TracePill: React.FC<{ label: string }> = ({ label }) => (
  <span
    style={{
      display: 'inline-block',
      fontFamily: 'var(--at-mono)',
      fontSize: '12px',
      fontWeight: 600,
      letterSpacing: '0.05em',
      color: 'var(--at-red-1)',
      backgroundColor: 'var(--at-red-soft)',
      border: '1px solid var(--at-red-1)',
      borderRadius: '4px',
      padding: '2px 7px',
      marginLeft: '6px',
      verticalAlign: 'middle',
      lineHeight: 1.4,
    }}
  >
    {label}
  </span>
);

/** Drop-cap paragraph — first letter styled as a large serif initial */
const DropCapParagraph: React.FC<{ text: string }> = ({ text }) => {
  if (!text || text.length === 0) return null;
  const firstLetter = text[0];
  const rest = text.slice(1);

  return (
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: 'var(--at-brief-size)',
        lineHeight: 'var(--at-brief-leading)',
        color: 'var(--at-ink-1)',
        margin: '0 0 16px 0',
      }}
    >
      <span
        style={{
          float: 'left',
          fontFamily: 'var(--at-serif)',
          fontSize: '52px',
          lineHeight: '42px',
          fontWeight: 400,
          color: 'var(--at-ink-1)',
          paddingRight: '8px',
          paddingTop: '4px',
        }}
      >
        {firstLetter}
      </span>
      {rest}
    </p>
  );
};

/** Regular prose paragraph */
const Paragraph: React.FC<{ text: string }> = ({ text }) => (
  <p
    style={{
      fontFamily: 'var(--at-serif)',
      fontSize: 'var(--at-brief-size)',
      lineHeight: 'var(--at-brief-leading)',
      color: 'var(--at-ink-1)',
      margin: '0 0 16px 0',
    }}
  >
    {text}
  </p>
);

/** Evidence panel — SQL query and ranked tool list */
const EvidencePanel: React.FC<{
  sql: string;
  toolRanking: { name: string; distance: number }[];
}> = ({ sql, toolRanking }) => (
  <ExpCard>
    <Eyebrow label="Evidence · pgvector Discovery" variant="muted" />

    {/* SQL block */}
    <pre
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '13px',
        lineHeight: 'var(--at-mono-leading)',
        backgroundColor: 'var(--at-cream-2)',
        border: '1px solid var(--at-rule-1)',
        borderRadius: '8px',
        padding: '16px',
        margin: '12px 0 16px 0',
        overflowX: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      <code>{highlightSql(sql)}</code>
    </pre>

    {/* Ranked tool list */}
    <div style={{ marginTop: '8px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: 'var(--at-eyebrow-size)',
          letterSpacing: 'var(--at-eyebrow-tracking)',
          textTransform: 'uppercase',
          color: 'var(--at-ink-2)',
          display: 'block',
          marginBottom: '8px',
        }}
      >
        Ranked Tools
      </span>
      {toolRanking.map((tool, i) => (
        <div
          key={tool.name}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 0',
            borderBottom:
              i < toolRanking.length - 1
                ? '1px solid var(--at-rule-1)'
                : 'none',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '14px',
              color: 'var(--at-ink-1)',
            }}
          >
            {i + 1}. {tool.name}
          </span>
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              color: 'var(--at-ink-2)',
            }}
          >
            {tool.distance.toFixed(2)} cos
          </span>
        </div>
      ))}
    </div>
  </ExpCard>
);

/** Memory tier row */
const MemoryRow: React.FC<{ tier: string; content: string }> = ({
  tier,
  content,
}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: '12px',
      padding: '10px 0',
      borderBottom: '1px solid var(--at-rule-1)',
    }}
  >
    <span
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '12px',
        fontWeight: 600,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color:
          tier.toUpperCase() === 'LTM'
            ? 'var(--at-green-1)'
            : 'var(--at-red-1)',
        backgroundColor:
          tier.toUpperCase() === 'LTM'
            ? 'var(--at-green-soft)'
            : 'var(--at-red-soft)',
        borderRadius: '4px',
        padding: '2px 6px',
        flexShrink: 0,
        lineHeight: 1.6,
      }}
    >
      {tier}
    </span>
    <span
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '15px',
        lineHeight: 1.5,
        color: 'var(--at-ink-2)',
      }}
    >
      {content}
    </span>
  </div>
);

/** Product card for the brief products grid */
const BriefProductCard: React.FC<{ product: ProductCard }> = ({ product }) => (
  <div
    style={{
      background: 'var(--at-cream-2)',
      border: '1px solid var(--at-rule-1)',
      borderRadius: '10px',
      overflow: 'hidden',
    }}
  >
    {/* Image placeholder */}
    <div
      style={{
        width: '100%',
        height: '140px',
        backgroundColor: 'var(--at-cream-2)',
        borderBottom: '1px solid var(--at-rule-1)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          color: 'var(--at-ink-2)',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}
      >
        Image
      </span>
    </div>

    {/* Card content */}
    <div style={{ padding: '12px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: 'var(--at-ink-2)',
          display: 'block',
          marginBottom: '4px',
        }}
      >
        {product.brand}
      </span>
      <span
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          lineHeight: 1.3,
          color: 'var(--at-ink-1)',
          display: 'block',
          marginBottom: '6px',
        }}
      >
        {product.name}
      </span>
      {product.traceRef && <TracePill label={product.traceRef} />}
    </div>
  </div>
);

/* =======================================================================
 * Editorial section renderer
 * ======================================================================= */

const EditorialSection: React.FC<{ section: BriefSection }> = ({
  section,
}) => (
  <section style={{ marginBottom: '40px' }}>
    {/* Section numeral and title */}
    <div style={{ marginBottom: '16px' }}>
      <span
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          color: 'var(--at-red-1)',
          display: 'block',
          marginBottom: '4px',
        }}
      >
        {section.numeral}
      </span>
      <h3
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '24px',
          fontWeight: 400,
          lineHeight: 1.25,
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {section.title}
      </h3>
    </div>

    {/* Paragraphs — first paragraph gets drop-cap */}
    {section.paragraphs.map((text, i) =>
      i === 0 ? (
        <DropCapParagraph key={i} text={text} />
      ) : (
        <Paragraph key={i} text={text} />
      )
    )}

    {/* Inline trace pills */}
    {section.tracePills && section.tracePills.length > 0 && (
      <div style={{ marginTop: '4px', marginBottom: '16px' }}>
        {section.tracePills.map((pill) => (
          <TracePill key={pill} label={pill} />
        ))}
      </div>
    )}

    {/* Evidence panel (tool selection section) */}
    {section.evidencePanel && (
      <div style={{ marginTop: '20px' }}>
        <EvidencePanel
          sql={section.evidencePanel.sql}
          toolRanking={section.evidencePanel.toolRanking}
        />
      </div>
    )}

    {/* Memory rows */}
    {section.memoryRows && section.memoryRows.length > 0 && (
      <div
        style={{
          marginTop: '20px',
          background: 'var(--at-cream-elev)',
          border: '1px solid var(--at-rule-1)',
          borderRadius: '10px',
          padding: '16px',
        }}
      >
        <Eyebrow label="Memory" variant="muted" />
        <div style={{ marginTop: '8px' }}>
          {section.memoryRows.map((row, i) => (
            <MemoryRow key={i} tier={row.tier} content={row.content} />
          ))}
        </div>
      </div>
    )}
  </section>
);

/* =======================================================================
 * Main BriefTab component
 * ======================================================================= */

const BriefTab: React.FC = () => {
  const { session } = useOutletContext<SessionOutletContext>();
  const brief = session.brief;

  if (!brief) {
    return (
      <div
        style={{
          padding: '80px 48px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
        }}
      >
        <Eyebrow label="No brief available" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '24px',
            lineHeight: 1.35,
            color: 'var(--at-ink-1)',
            maxWidth: '420px',
            marginTop: '16px',
          }}
        >
          The curator's brief has not been composed for this session yet.
        </p>
      </div>
    );
  }

  return (
    <article
      style={{
        maxWidth: '620px',
        margin: '0 auto',
        padding: '8px 0 80px 0',
      }}
    >
      {/* ================================================================
       * Title block
       * ================================================================ */}
      <header style={{ textAlign: 'center', marginBottom: '40px' }}>
        <Eyebrow
          label={`Curator's Brief · Folio ${brief.folioNumber}`}
        />
        <h1
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '36px',
            fontWeight: 400,
            lineHeight: 1.15,
            color: 'var(--at-ink-1)',
            margin: '16px 0 12px 0',
            letterSpacing: '-0.01em',
          }}
        >
          {brief.headline}
        </h1>
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-2)',
            display: 'flex',
            justifyContent: 'center',
            gap: '16px',
            flexWrap: 'wrap',
          }}
        >
          <span>Filed {formatFiledTime(brief.filedTime)}</span>
          <span>·</span>
          <span>Session #{session.id}</span>
        </div>
      </header>

      {/* Divider */}
      <hr
        style={{
          border: 'none',
          borderTop: '1px solid var(--at-rule-2)',
          margin: '0 0 32px 0',
        }}
      />

      {/* ================================================================
       * Metadata grid
       * ================================================================ */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '16px 32px',
          marginBottom: '40px',
          padding: '20px',
          background: 'var(--at-cream-2)',
          borderRadius: '10px',
          border: '1px solid var(--at-rule-1)',
        }}
      >
        {[
          { label: 'Customer', value: session.personaId },
          {
            label: 'Request',
            value: session.openingQuery,
          },
          { label: 'Plan', value: session.routingPattern },
          { label: 'Elapsed', value: formatElapsed(session.elapsedMs) },
        ].map((field) => (
          <div key={field.label}>
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                letterSpacing: '0.15em',
                textTransform: 'uppercase',
                color: 'var(--at-ink-2)',
                display: 'block',
                marginBottom: '4px',
              }}
            >
              {field.label}
            </span>
            <span
              style={{
                fontFamily: 'var(--at-serif)',
                fontSize: '16px',
                lineHeight: 1.4,
                color: 'var(--at-ink-1)',
              }}
            >
              {field.value}
            </span>
          </div>
        ))}
      </div>

      {/* ================================================================
       * Editorial sections
       * ================================================================ */}
      {brief.sections.map((section) => (
        <EditorialSection key={section.numeral} section={section} />
      ))}

      {/* ================================================================
       * Products section
       * ================================================================ */}
      {brief.products && brief.products.length > 0 && (
        <section style={{ marginBottom: '40px' }}>
          <Eyebrow label="Recommended Products" variant="muted" />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '16px',
              marginTop: '16px',
            }}
          >
            {brief.products.map((product) => (
              <BriefProductCard key={product.name} product={product} />
            ))}
          </div>
        </section>
      )}

      {/* ================================================================
       * Confidence section
       * ================================================================ */}
      {brief.confidence && (
        <section
          style={{
            marginBottom: '48px',
            textAlign: 'center',
            padding: '32px 0',
          }}
        >
          <hr
            style={{
              border: 'none',
              borderTop: '1px solid var(--at-rule-2)',
              margin: '0 0 32px 0',
            }}
          />

          {/* Large confidence percentage */}
          <div
            style={{
              fontFamily: 'var(--at-serif)',
              fontSize: '76px',
              fontWeight: 400,
              lineHeight: 1,
              color: 'var(--at-green-1)',
              marginBottom: '8px',
            }}
          >
            {brief.confidence.percentage}%
          </div>
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: 'var(--at-eyebrow-size)',
              letterSpacing: 'var(--at-eyebrow-tracking)',
              textTransform: 'uppercase',
              color: 'var(--at-ink-2)',
            }}
          >
            Confidence Score
          </span>

          {/* Supporting statistics */}
          {brief.confidence.stats && brief.confidence.stats.length > 0 && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${Math.min(brief.confidence.stats.length, 4)}, 1fr)`,
                gap: '16px',
                marginTop: '24px',
                padding: '20px',
                background: 'var(--at-cream-2)',
                borderRadius: '10px',
                border: '1px solid var(--at-rule-1)',
                textAlign: 'center',
              }}
            >
              {brief.confidence.stats.map((stat, i) => (
                <div key={stat.label}>
                  <span
                    style={{
                      fontFamily: 'var(--at-sans)',
                      fontSize: '14px',
                      color: 'var(--at-ink-2)',
                      display: 'block',
                      marginBottom: '2px',
                    }}
                  >
                    {i + 1}.
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--at-serif)',
                      fontSize: '20px',
                      fontWeight: 400,
                      color: 'var(--at-ink-1)',
                      display: 'block',
                      marginBottom: '4px',
                    }}
                  >
                    {stat.value}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--at-mono)',
                      fontSize: '11px',
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      color: 'var(--at-ink-2)',
                    }}
                  >
                    {stat.label}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ================================================================
       * Editorial footer
       * ================================================================ */}
      <footer
        style={{
          textAlign: 'center',
          paddingTop: '24px',
          borderTop: '1px solid var(--at-rule-2)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '24px',
            color: 'var(--at-ink-4)',
            display: 'block',
            marginBottom: '12px',
          }}
        >
          fin.
        </span>
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            lineHeight: 1.5,
            color: 'var(--at-ink-1)',
            maxWidth: '400px',
            margin: '0 auto',
          }}
        >
          This brief was composed from session telemetry and is intended as a
          read-only editorial record of how the system arrived at its
          recommendations.
        </p>
      </footer>
    </article>
  );
};

export default BriefTab;
