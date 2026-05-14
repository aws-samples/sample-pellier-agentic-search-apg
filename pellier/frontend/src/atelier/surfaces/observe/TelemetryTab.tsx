/**
 * TelemetryTab — Session telemetry timeline with context rail.
 *
 * Two-column layout: numbered timeline (left) + ContextRail (right).
 * Includes mode strip, eyebrow with panel count, expansion area,
 * and footer strip.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10
 */

import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  ContextRail,
  ExpCard,
  Eyebrow,
  CategoryBadge,
  StatusDot,
  ModeStrip,
} from '../../components';
import type { SessionOutletContext } from './SessionView';
import type { TelemetryPanel } from '../../types';

/* =======================================================================
 * Number-to-word mapping for eyebrow
 * ======================================================================= */

const NUMBER_WORDS: Record<number, string> = {
  0: 'Zero',
  1: 'One',
  2: 'Two',
  3: 'Three',
  4: 'Four',
  5: 'Five',
  6: 'Six',
  7: 'Seven',
  8: 'Eight',
  9: 'Nine',
  10: 'Ten',
  11: 'Eleven',
  12: 'Twelve',
  13: 'Thirteen',
  14: 'Fourteen',
  15: 'Fifteen',
  16: 'Sixteen',
  17: 'Seventeen',
  18: 'Eighteen',
  19: 'Nineteen',
  20: 'Twenty',
};

function numberToWord(n: number): string {
  return NUMBER_WORDS[n] ?? String(n);
}

/* =======================================================================
 * Status dot mapping for telemetry panels
 * ======================================================================= */

function getStatusColor(status: TelemetryPanel['status']): string {
  switch (status) {
    case 'complete':
      return 'var(--at-green-1)';
    case 'running':
      return 'var(--at-red-1)';
    case 'queued':
      return 'var(--at-ink-4)';
    default:
      return 'var(--at-ink-4)';
  }
}

function getStatusLabel(status: TelemetryPanel['status']): string {
  switch (status) {
    case 'complete':
      return 'Complete';
    case 'running':
      return 'Running';
    case 'queued':
      return 'Queued';
    default:
      return status;
  }
}


/* =======================================================================
 * SQL keyword highlighter (shared pattern from ChatTab)
 * ======================================================================= */

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'ORDER', 'BY', 'LIMIT', 'INSERT', 'UPDATE',
  'DELETE', 'CREATE', 'DROP', 'ALTER', 'JOIN', 'LEFT', 'RIGHT', 'INNER',
  'OUTER', 'ON', 'AND', 'OR', 'NOT', 'IN', 'AS', 'IS', 'NULL', 'LIKE',
  'ILIKE', 'GROUP', 'HAVING', 'DISTINCT', 'UNION', 'ALL', 'SET', 'INTO',
  'VALUES', 'TABLE', 'INDEX', 'WITH', 'CASE', 'WHEN', 'THEN', 'ELSE',
  'END', 'ASC', 'DESC', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
]);

function highlightSQL(sql: string): React.ReactNode[] {
  const tokens = sql.split(/(\b\w+\b)/g);
  return tokens.map((token, i) => {
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
 * Timeline panel component
 * ======================================================================= */

interface TimelinePanelProps {
  panel: TelemetryPanel;
  isActive: boolean;
  isLast: boolean;
  onClick: () => void;
}

const TimelinePanelCard: React.FC<TimelinePanelProps> = ({
  panel,
  isActive,
  isLast,
  onClick,
}) => {
  const statusColor = getStatusColor(panel.status);
  const isRunning = panel.status === 'running';

  return (
    <div
      style={{
        display: 'flex',
        gap: '16px',
        position: 'relative',
      }}
    >
      {/* Left column: number + connecting line */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          width: '36px',
          flexShrink: 0,
        }}
      >
        {/* Numbered circle */}
        <div
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            backgroundColor: isActive ? 'var(--at-ink-1)' : 'var(--at-cream-2)',
            border: isActive ? 'none' : '1px solid var(--at-rule-2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            fontWeight: 600,
            color: isActive ? 'var(--at-cream-1)' : 'var(--at-ink-1)',
            flexShrink: 0,
            zIndex: 1,
          }}
        >
          {panel.index}
        </div>
        {/* Connecting line */}
        {!isLast && (
          <div
            style={{
              width: '1px',
              flex: 1,
              backgroundColor: 'var(--at-rule-2)',
              minHeight: '16px',
            }}
          />
        )}
      </div>

      {/* Right column: panel content */}
      <div
        role="button"
        tabIndex={0}
        onClick={onClick}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onClick();
          }
        }}
        style={{
          flex: 1,
          padding: '14px 18px',
          marginBottom: isLast ? 0 : '4px',
          borderRadius: 'var(--at-card-radius)',
          background: isActive ? 'var(--at-cream-elev)' : 'transparent',
          border: isActive ? '1px solid var(--at-rule-1)' : '1px solid transparent',
          boxShadow: isActive ? '0 2px 8px rgba(31, 20, 16, 0.06)' : 'none',
          cursor: 'pointer',
          transition: 'background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
        }}
      >
        {/* Top row: category badge + status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '6px',
          }}
        >
          <CategoryBadge category={panel.category} />
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
            {/* Status dot */}
            <span
              role="status"
              aria-label={getStatusLabel(panel.status)}
              className={isRunning ? 'at-pulse-live' : ''}
              style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: statusColor,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: statusColor,
              }}
            >
              {getStatusLabel(panel.status)}
            </span>
          </div>
        </div>

        {/* Title */}
        <h4
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '17px',
            fontWeight: 400,
            color: 'var(--at-ink-1)',
            margin: '0 0 4px 0',
            lineHeight: 1.3,
          }}
        >
          {panel.title}
        </h4>

        {/* Description */}
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            color: 'var(--at-ink-1)',
            margin: '0 0 8px 0',
            lineHeight: 1.5,
          }}
        >
          {panel.description}
        </p>

        {/* Bottom row: agent + timing */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          {panel.agent && (
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                color: 'var(--at-ink-2)',
                padding: '2px 8px',
                border: '1px solid var(--at-rule-2)',
                borderRadius: '4px',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {panel.agent}
            </span>
          )}
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              color: 'var(--at-ink-2)',
              marginLeft: panel.agent ? '0' : 'auto',
            }}
          >
            {panel.durationMs}ms
          </span>
        </div>

        {/* Expanded SQL (only for active panel with SQL) */}
        {isActive && panel.sql && (
          <div
            style={{
              marginTop: '12px',
              padding: '12px 14px',
              background: 'var(--at-cream-2)',
              borderRadius: '8px',
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              lineHeight: 'var(--at-mono-leading)',
              color: 'var(--at-ink-2)',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {highlightSQL(panel.sql)}
          </div>
        )}
      </div>
    </div>
  );
};


/* =======================================================================
 * Context rail — Product recommendation card
 * ======================================================================= */

const ProductRecommendationCard: React.FC = () => {
  const imageUrl = `${import.meta.env.BASE_URL ?? '/'}products/marco-linen-camp-shirt-indigo.png`;
  return (
  <ExpCard>
    <Eyebrow label="Top Pick" />

    {/* Product image */}
    <div
      style={{
        height: '160px',
        borderRadius: '8px',
        overflow: 'hidden',
        marginTop: '14px',
        marginBottom: '14px',
        background: 'var(--at-cream-2)',
      }}
    >
      <img
        src={imageUrl}
        alt="Italian Linen Camp Shirt"
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
        }}
      />
    </div>

    {/* Brand */}
    <div
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        color: 'var(--at-ink-2)',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        marginBottom: '4px',
      }}
    >
      Pellier Editions
    </div>

    {/* Name */}
    <div
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '17px',
        fontWeight: 500,
        color: 'var(--at-ink-1)',
        lineHeight: 1.6,
        marginBottom: '4px',
      }}
    >
      Italian Linen Camp Shirt
    </div>

    {/* Price */}
    <div
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '15px',
        fontWeight: 600,
        color: 'var(--at-ink-2)',
        marginBottom: '12px',
      }}
    >
      $228
    </div>

    {/* Editorial blurb */}
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '15px',
        color: 'var(--at-ink-1)',
        lineHeight: 1.55,
        margin: '0 0 14px 0',
      }}
    >
      Camp-collar shirt in deep indigo European linen. Relaxed fit, mother of pearl buttons.
      Pre-washed softness that earns its golden hour on any terrace.
    </p>

    {/* Why this pick */}
    <div style={{ marginBottom: '14px' }}>
      <div
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          color: 'var(--at-ink-2)',
          marginBottom: '8px',
        }}
      >
        Why this pick
      </div>
      <ul
        style={{
          margin: 0,
          paddingLeft: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        {[
          'Cosine similarity: 0.60 (linen + travel cluster)',
          'Matches "linen" + "warm evenings" query intent',
          'LTM recall: Marco prefers natural fibers, indigo',
          'Price within persona range ($68–$485)',
        ].map((reason, i) => (
          <li
            key={i}
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '14px',
              color: 'var(--at-ink-2)',
              lineHeight: 1.5,
            }}
          >
            {reason}
          </li>
        ))}
      </ul>
    </div>

    {/* Trace this pick button */}
    <button
      style={{
        width: '100%',
        padding: '10px 16px',
        borderRadius: '8px',
        border: '1px solid var(--at-ink-1)',
        backgroundColor: 'transparent',
        color: 'var(--at-ink-1)',
        fontFamily: 'var(--at-mono)',
        fontSize: '13px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        cursor: 'pointer',
        marginBottom: '14px',
      }}
    >
      Trace this pick
    </button>

    {/* Confidence + token count */}
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span
          style={{
            fontFamily: 'var(--at-serif)',
            fontSize: '22px',
            fontWeight: 400,
            color: 'var(--at-green-1)',
          }}
        >
          87%
        </span>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            color: 'var(--at-ink-2)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          Confidence
        </span>
      </div>
      <div
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          color: 'var(--at-ink-2)',
        }}
      >
        2,340 tokens
      </div>
    </div>
  </ExpCard>
  );
};


/* =======================================================================
 * Three-column expansion area
 * ======================================================================= */

const ExpansionArea: React.FC<{ panels: TelemetryPanel[] }> = ({ panels }) => {
  // Collect SQL panels for "How we arrived"
  const sqlPanels = panels.filter((p) => p.sql);
  // Collect memory panels for "Memory orbit"
  const memoryPanels = panels.filter(
    (p) => p.title.toLowerCase().includes('memory'),
  );
  // Collect agent panels for "Team of specialists"
  const agentNames = [...new Set(panels.filter((p) => p.agent).map((p) => p.agent!))];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '16px',
        marginTop: '32px',
      }}
    >
      {/* How we arrived — SQL panels */}
      <ExpCard>
        <Eyebrow label="How we arrived" />
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            marginTop: '14px',
          }}
        >
          {sqlPanels.length > 0 ? (
            sqlPanels.map((p) => (
              <div key={p.index}>
                <div
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--at-ink-1)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    marginBottom: '6px',
                  }}
                >
                  Panel {p.index} · {p.title}
                </div>
                <div
                  style={{
                    padding: '10px 12px',
                    background: 'var(--at-cream-2)',
                    borderRadius: '8px',
                    fontFamily: 'var(--at-mono)',
                    fontSize: '12px',
                    lineHeight: 'var(--at-mono-leading)',
                    color: 'var(--at-ink-2)',
                    overflowX: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {highlightSQL(p.sql!)}
                </div>
              </div>
            ))
          ) : (
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '15px',
                color: 'var(--at-ink-4)',
                margin: 0,
              }}
            >
              No SQL panels in this session.
            </p>
          )}
        </div>
      </ExpCard>

      {/* Memory orbit — STM/LTM visualization */}
      <ExpCard>
        <Eyebrow label="Memory orbit" />
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            marginTop: '14px',
          }}
        >
          {memoryPanels.length > 0 ? (
            memoryPanels.map((p) => (
              <div
                key={p.index}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  padding: '10px 12px',
                  background: 'var(--at-cream-2)',
                  borderRadius: '8px',
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: p.title.includes('STM')
                      ? 'var(--at-red-1)'
                      : 'var(--at-green-1)',
                    padding: '1px 6px',
                    border: `1px solid ${
                      p.title.includes('STM')
                        ? 'var(--at-red-1)'
                        : 'var(--at-green-1)'
                    }`,
                    borderRadius: '3px',
                    flexShrink: 0,
                    marginTop: '1px',
                  }}
                >
                  {p.title.includes('STM') ? 'STM' : 'LTM'}
                </span>
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--at-sans)',
                      fontSize: '14px',
                      color: 'var(--at-ink-2)',
                      lineHeight: 1.5,
                    }}
                  >
                    {p.description}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--at-mono)',
                      fontSize: '12px',
                      color: 'var(--at-ink-2)',
                      marginTop: '4px',
                    }}
                  >
                    {p.durationMs}ms
                  </div>
                </div>
              </div>
            ))
          ) : (
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '15px',
                color: 'var(--at-ink-4)',
                margin: 0,
              }}
            >
              No memory operations in this session.
            </p>
          )}
        </div>
      </ExpCard>

      {/* Team of specialists — agent status cards */}
      <ExpCard>
        <Eyebrow label="Team of specialists" />
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            marginTop: '14px',
          }}
        >
          {agentNames.map((name) => {
            const agentPanels = panels.filter((p) => p.agent === name);
            const allComplete = agentPanels.every((p) => p.status === 'complete');
            const totalMs = agentPanels.reduce((sum, p) => sum + p.durationMs, 0);

            return (
              <div
                key={name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 12px',
                  background: 'var(--at-cream-2)',
                  borderRadius: '8px',
                }}
              >
                <StatusDot
                  status={allComplete ? 'idle' : 'live'}
                  size={8}
                />
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontFamily: 'var(--at-sans)',
                      fontSize: '15px',
                      fontWeight: 500,
                      color: 'var(--at-ink-1)',
                    }}
                  >
                    {name}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--at-mono)',
                      fontSize: '12px',
                      color: 'var(--at-ink-2)',
                      marginTop: '2px',
                    }}
                  >
                    {agentPanels.length} panel{agentPanels.length !== 1 ? 's' : ''} · {totalMs}ms
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '11px',
                    fontWeight: 500,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    color: allComplete ? 'var(--at-green-1)' : 'var(--at-red-1)',
                  }}
                >
                  {allComplete ? 'Done' : 'Active'}
                </span>
              </div>
            );
          })}
        </div>
      </ExpCard>
    </div>
  );
};


/* =======================================================================
 * Footer strip
 * ======================================================================= */

const FooterStrip: React.FC<{ panels: TelemetryPanel[] }> = ({ panels }) => {
  const activeAgents = new Set(panels.filter((p) => p.agent).map((p) => p.agent)).size;
  const dataSources = panels.filter((p) => p.sql).length;
  const completePanels = panels.filter((p) => p.status === 'complete').length;
  const successRate = panels.length > 0
    ? Math.round((completePanels / panels.length) * 100)
    : 0;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '24px',
        padding: '20px 24px',
        marginTop: '24px',
        background: 'var(--at-cream-2)',
        borderRadius: 'var(--at-card-radius)',
        flexWrap: 'wrap',
      }}
    >
      {/* Pull quote */}
      <div
        style={{
          flex: 1,
          minWidth: '200px',
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          color: 'var(--at-ink-1)',
          lineHeight: 1.6,
        }}
      >
        "Every panel is a decision the system made on your behalf."
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        {[
          { label: 'Active agents', value: String(activeAgents) },
          { label: 'Data sources', value: String(dataSources) },
          { label: 'Decisions today', value: String(panels.length) },
          { label: 'Success rate', value: `${successRate}%` },
        ].map((stat) => (
          <div
            key={stat.label}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '2px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-serif)',
                fontSize: '22px',
                fontWeight: 400,
                color: 'var(--at-ink-1)',
                lineHeight: 1,
              }}
            >
              {stat.value}
            </span>
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                color: 'var(--at-ink-2)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                whiteSpace: 'nowrap',
              }}
            >
              {stat.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

/* =======================================================================
 * Main TelemetryTab component
 * ======================================================================= */

const ROUTING_PATTERNS = ['Dispatcher', 'Agents-as-Tools', 'Graph'];

const TelemetryTab: React.FC = () => {
  const { session } = useOutletContext<SessionOutletContext>();
  const panels = session.telemetry ?? [];
  const [activeIndex, setActiveIndex] = useState<number>(panels.length > 0 ? 1 : -1);
  const [activePattern, setActivePattern] = useState<string>(
    session.routingPattern || 'Dispatcher',
  );

  const panelCount = panels.length;
  const eyebrowLabel = `${numberToWord(panelCount)} panels \u00B7 ${panelCount}`;

  /* Empty state — no telemetry panels recorded */
  if (panelCount === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px 24px',
          textAlign: 'center',
        }}
      >
        <Eyebrow label="No telemetry" variant="muted" />
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
          No telemetry panels have been recorded for this session.
        </p>
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '16px',
            color: 'var(--at-ink-4)',
            maxWidth: '380px',
            marginTop: '8px',
          }}
        >
          Telemetry panels appear here as the agentic system processes each
          step of the conversation.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Two-column layout: timeline + context rail */}
      <div
        style={{
          display: 'flex',
          gap: '0',
          alignItems: 'flex-start',
        }}
      >
        {/* Left column — timeline */}
        <div style={{ flex: 1, minWidth: 0, paddingRight: '24px' }}>
          {/* Mode strip */}
          <ModeStrip
            patterns={ROUTING_PATTERNS}
            active={activePattern}
            onSelect={setActivePattern}
          />

          {/* Eyebrow with panel count */}
          <div style={{ marginTop: '20px', marginBottom: '20px' }}>
            <Eyebrow label={eyebrowLabel} />
          </div>

          {/* Timeline */}
          <div>
            {panels.map((panel, i) => (
              <TimelinePanelCard
                key={panel.index}
                panel={panel}
                isActive={panel.index === activeIndex}
                isLast={i === panels.length - 1}
                onClick={() => setActiveIndex(panel.index)}
              />
            ))}
          </div>
        </div>

        {/* Right column — context rail */}
        <ContextRail>
          <ProductRecommendationCard />
        </ContextRail>
      </div>

      {/* Three-column expansion area */}
      <ExpansionArea panels={panels} />

      {/* Footer strip */}
      <FooterStrip panels={panels} />
    </div>
  );
};

export default TelemetryTab;
