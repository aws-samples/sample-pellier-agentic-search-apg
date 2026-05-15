/**
 * TelemetryTab — Session telemetry timeline with context rail.
 *
 * Two-column layout: numbered timeline (left) + ContextRail (right).
 * Includes mode strip, eyebrow with panel count, expansion area,
 * and footer strip.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import type { ProductCard, TelemetryPanel } from '../../types';
import { BEDROCK_INFERENCE_PROFILES } from '../../constants/bedrockModels';
import { resolveProductImageUrl } from '../../../utils/resolveProductImageUrl';
import {
  blurbForProduct,
  buildWhyThisPickReasons,
  estimateTokenCount,
  findRecommendationTurn,
  getTopPickProduct,
  resolveTracePanelIndex,
} from './telemetryTrace';

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
      id={`telemetry-${panel.index}`}
      data-testid={`telemetry-panel-${panel.index}`}
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
        data-telemetry-panel
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

interface ProductRecommendationCardProps {
  product: ProductCard;
  blurb: string;
  reasons: string[];
  confidencePct: number;
  tokenEstimate: number;
  tracePanelIndex: number;
  onTracePick: () => void;
}

const ProductRecommendationCard: React.FC<ProductRecommendationCardProps> = ({
  product,
  blurb,
  reasons,
  confidencePct,
  tokenEstimate,
  tracePanelIndex,
  onTracePick,
}) => {
  const imageUrl = resolveProductImageUrl(product.imageUrl);
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
        alt={product.name}
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
      {product.brand}
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
      {product.name}
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
      ${product.price}
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
      {blurb}
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
        {reasons.map((reason, i) => (
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

    {/* Trace this pick — scrolls timeline to the panel that decided this product */}
    <button
      type="button"
      data-testid="trace-this-pick"
      aria-label={`Trace this pick in telemetry panel ${tracePanelIndex}`}
      onClick={onTracePick}
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
          {confidencePct}%
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
        {tokenEstimate.toLocaleString()} tokens
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

const ROUTING_PATTERNS = ['Dispatcher', 'Agents-as-Tools', 'Graph'] as const;
type RoutingPattern = (typeof ROUTING_PATTERNS)[number];

function canonicalRoutingPattern(raw: string | undefined): RoutingPattern {
  const s = (raw ?? '').trim().toLowerCase();
  if (s.includes('graph')) return 'Graph';
  if (s.includes('agents') && s.includes('tools')) return 'Agents-as-Tools';
  return 'Dispatcher';
}

/**
 * When the selected pill does not match how this session was recorded,
 * show an illustrative timeline so each pattern has a distinct teaching shape.
 */
const ILLUSTRATIVE_TELEMETRY: Record<RoutingPattern, TelemetryPanel[]> = {
  Dispatcher: [
    {
      index: 1,
      category: 'managed',
      title: 'Intent → specialist',
      description:
        'Dispatcher scores the utterance and hands the turn to one owning agent (Curator, Style Advisor, …). One hop per decision — the shape the Boutique storefront runs in production.',
      status: 'complete',
      durationMs: 58,
      agent: 'Dispatcher',
    },
    {
      index: 2,
      category: 'owned',
      title: 'Skill load',
      description:
        'SkillRouter binds persona + intent path (e.g. the-gift-table). Owned data plane; no LLM call.',
      status: 'complete',
      durationMs: 36,
      agent: 'SkillRouter',
    },
    {
      index: 3,
      category: 'both',
      title: 'Hybrid retrieval',
      description:
        'Managed agent invokes find_pieces_hybrid: pgvector + BM25 in parallel, then RRF merge.',
      status: 'complete',
      durationMs: 312,
      agent: 'Curator · find_pieces_hybrid',
      sql:
        'SELECT id, embedding <=> $1::vector AS dist FROM product_catalog ORDER BY dist LIMIT 20;',
    },
    {
      index: 4,
      category: 'both',
      title: 'Rerank',
      description:
        'Cohere Rerank v3.5 over the fused pool — Bedrock inference profile matches workshop stack.',
      status: 'complete',
      durationMs: 265,
      agent: 'Curator · find_pieces_hybrid',
    },
    {
      index: 5,
      category: 'managed',
      title: 'Concierge reply',
      description:
        'Single visible assistant turn after the specialist returns — easy to narrate in demos and in shopper-facing UX.',
      status: 'complete',
      durationMs: 980,
      agent: 'Curator',
    },
  ],
  'Agents-as-Tools': [
    {
      index: 1,
      category: 'managed',
      title: 'Orchestrator turn',
      description:
        'One long-lived model frame plans the turn: which specialist-shaped tools to call and in what order.',
      status: 'complete',
      durationMs: 44,
      agent: 'Orchestrator',
    },
    {
      index: 2,
      category: 'owned',
      title: 'Tools registered',
      description:
        'Specialists are exposed as first-class tools (e.g. curator_agent, value_analyst_agent) with schemas — same contract style as find_pieces, but nested under the parent agent.',
      status: 'complete',
      durationMs: 11,
      agent: 'Gateway',
    },
    {
      index: 3,
      category: 'both',
      title: 'Tool: curator_agent',
      description:
        'Parent invokes Curator as a tool; Curator runs its own retrieval + Opus composition and returns structured JSON to the parent — no second shopper message.',
      status: 'complete',
      durationMs: 428,
      agent: 'Orchestrator → Curator',
    },
    {
      index: 4,
      category: 'both',
      title: 'Tool: value_analyst_agent',
      description:
        'Parallel or follow-up tool call in the same orchestrator turn for price/stock narrative — composition without extra microservices per hop.',
      status: 'complete',
      durationMs: 119,
      agent: 'Orchestrator → Value Analyst',
    },
    {
      index: 5,
      category: 'managed',
      title: 'Merge & voice',
      description:
        'Orchestrator stitches tool payloads into one conversational reply. More flexibility in one turn; prompts carry more coupling across tools.',
      status: 'complete',
      durationMs: 240,
      agent: 'Orchestrator',
    },
  ],
  Graph: [
    {
      index: 1,
      category: 'managed',
      title: 'Graph entry',
      description:
        'Request enters a declared DAG: nodes are steps or agents, edges encode gating and fan-out/fan-in.',
      status: 'complete',
      durationMs: 18,
      agent: 'Graph runtime',
    },
    {
      index: 2,
      category: 'managed',
      title: 'Node: classify',
      description:
        'Router node branches on intent features (gift vs replenishment vs fit) before expensive retrieval.',
      status: 'complete',
      durationMs: 41,
      agent: 'Router',
    },
    {
      index: 3,
      category: 'both',
      title: 'Node: search_cluster',
      description:
        'Embeddings + lexical branch inside one node; emits scored candidates for downstream nodes.',
      status: 'complete',
      durationMs: 276,
      agent: 'Style Advisor',
      sql:
        'SELECT id, ts_rank_cd(description_tsv, plainto_tsquery($1)) AS r FROM product_catalog WHERE description_tsv @@ plainto_tsquery($1) LIMIT 20;',
    },
    {
      index: 4,
      category: 'managed',
      title: 'Edge: IF high_confidence',
      description:
        'Conditional edge skips rerank when cosine ceiling clears threshold; otherwise routes to rerank node — auditable control flow.',
      status: 'complete',
      durationMs: 6,
      agent: 'Graph runtime',
    },
    {
      index: 5,
      category: 'both',
      title: 'Node: compose',
      description:
        'Terminal node merges parallel paths and emits the assistant payload. Best when policy must look like an explicit state machine.',
      status: 'complete',
      durationMs: 502,
      agent: 'Composer',
    },
  ],
};

const introParagraphStyle: React.CSSProperties = {
  fontFamily: 'var(--at-sans)',
  fontSize: '14px',
  lineHeight: 1.55,
  color: 'var(--at-ink-2)',
  margin: 0,
};

const RoutingPatternIntro: React.FC = () => (
  <div style={{ marginBottom: '16px' }}>
  <ExpCard>
    <Eyebrow label="Routing patterns" />
    <p style={{ ...introParagraphStyle, marginTop: '12px' }}>
      <strong style={{ color: 'var(--at-ink-1)' }}>Dispatcher</strong> is what the{' '}
      <strong style={{ color: 'var(--at-ink-1)' }}>Boutique storefront</strong> uses in production:
      each shopper turn is routed to <em>one</em> owning specialist at a time, the concierge stays easy
      to reason about, and latency/token paths map cleanly to support and compliance reviews. Workshop
      sessions on this tab are captured from that same path, so the default timeline matches what ships.
    </p>
    <p style={{ ...introParagraphStyle, marginTop: '12px' }}>
      <strong style={{ color: 'var(--at-ink-1)' }}>Agents-as-Tools</strong> fits when a{' '}
      <em>single</em> orchestrator turn should call several specialist-shaped tools (serial or parallel)
      without standing up a new service for every hop — specialists return structured payloads into the
      parent frame.
    </p>
    <p style={{ ...introParagraphStyle, marginTop: '12px' }}>
      <strong style={{ color: 'var(--at-ink-1)' }}>Graph</strong> fits when the workflow should read as
      an explicit DAG: named nodes, conditional edges, skippable steps, and parallel merge points — more
      authoring ceremony, highest clarity when policy must look like an auditable state machine.
    </p>
  </ExpCard>
  </div>
);

/** Mono strip so Telemetry names the same Bedrock profiles as the workshop stack. */
function WorkshopBedrockProfilesStrip() {
  const rows: Array<[string, string]> = [
    ['Claude Opus 4.6', BEDROCK_INFERENCE_PROFILES.CLAUDE_OPUS_46],
    ['Claude Haiku 4.5', BEDROCK_INFERENCE_PROFILES.CLAUDE_HAIKU_45],
    ['Cohere Embed v4', BEDROCK_INFERENCE_PROFILES.COHERE_EMBED_V4],
    ['Cohere Rerank v3.5', BEDROCK_INFERENCE_PROFILES.COHERE_RERANK_V35],
  ];
  return (
    <div
      role="region"
      aria-label="Bedrock inference profiles used in this workshop"
      style={{
        marginBottom: '20px',
        padding: '12px 16px',
        borderRadius: 'var(--at-card-radius)',
        border: '1px solid var(--at-rule-1)',
        background: 'var(--at-cream-2)',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '10px 20px',
      }}
    >
      {rows.map(([label, id]) => (
        <div
          key={id}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--at-ink-1)',
            }}
          >
            {label}
          </span>
          <code
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-ink-2)',
              wordBreak: 'break-all',
              lineHeight: 1.35,
            }}
          >
            {id}
          </code>
        </div>
      ))}
    </div>
  );
}

const TelemetryTab: React.FC = () => {
  const { session } = useOutletContext<SessionOutletContext>();
  const sessionPanels = session.telemetry ?? [];
  const sessionCanonical = canonicalRoutingPattern(session.routingPattern);
  const timelineRef = useRef<HTMLDivElement>(null);
  const pendingTracePanel = useRef<number | null>(null);

  const [activePattern, setActivePattern] = useState<RoutingPattern>(sessionCanonical);

  const displayPanels: TelemetryPanel[] =
    activePattern === sessionCanonical ? sessionPanels : ILLUSTRATIVE_TELEMETRY[activePattern];

  const [activeIndex, setActiveIndex] = useState(
    () => (sessionPanels.length > 0 ? sessionPanels[0].index : -1),
  );

  const topPick = useMemo(() => getTopPickProduct(session), [session]);

  const pickContext = useMemo(() => {
    if (!topPick) return null;
    const turn = findRecommendationTurn(session, topPick);
    const panelIndex = resolveTracePanelIndex(topPick, sessionPanels);
    return {
      product: topPick,
      blurb: blurbForProduct(turn, topPick),
      reasons: buildWhyThisPickReasons(session, topPick, sessionPanels),
      confidencePct:
        turn?.confidence?.percentage ?? session.brief?.confidence?.percentage ?? 85,
      tokenEstimate: estimateTokenCount(sessionPanels),
      tracePanelIndex: panelIndex,
    };
  }, [session, topPick, sessionPanels]);

  const scrollToTelemetryPanel = useCallback((panelIndex: number) => {
    const container = timelineRef.current;
    if (!container) return;
    const row = container.querySelector<HTMLElement>(`#telemetry-${panelIndex}`);
    if (!row) return;
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const card = row.querySelector<HTMLElement>('[data-telemetry-panel]');
    if (card) {
      card.setAttribute('data-flash', 'true');
      window.setTimeout(() => card.removeAttribute('data-flash'), 800);
    }
  }, []);

  const handlePatternSelect = useCallback(
    (p: string) => {
      const canonical = canonicalRoutingPattern(p);
      setActivePattern(canonical);
      const list =
        canonical === sessionCanonical ? sessionPanels : ILLUSTRATIVE_TELEMETRY[canonical];
      setActiveIndex(list.length > 0 ? list[0].index : -1);
    },
    [sessionCanonical, sessionPanels],
  );

  useEffect(() => {
    setActivePattern(sessionCanonical);
    setActiveIndex(sessionPanels.length > 0 ? sessionPanels[0].index : -1);
    pendingTracePanel.current = null;
  }, [session.id, sessionCanonical, sessionPanels.length]);

  useEffect(() => {
    if (pendingTracePanel.current == null) return;
    if (activePattern !== sessionCanonical) return;
    const panelIndex = pendingTracePanel.current;
    pendingTracePanel.current = null;
    setActiveIndex(panelIndex);
    requestAnimationFrame(() => scrollToTelemetryPanel(panelIndex));
  }, [activePattern, sessionCanonical, scrollToTelemetryPanel]);

  const handleTracePick = useCallback(() => {
    if (!pickContext) return;
    const { tracePanelIndex: panelIndex } = pickContext;
    pendingTracePanel.current = panelIndex;
    if (activePattern !== sessionCanonical) {
      setActivePattern(sessionCanonical);
      return;
    }
    pendingTracePanel.current = null;
    setActiveIndex(panelIndex);
    requestAnimationFrame(() => scrollToTelemetryPanel(panelIndex));
  }, [pickContext, activePattern, sessionCanonical, scrollToTelemetryPanel]);

  const panelCount = displayPanels.length;
  const showingSessionTrace = activePattern === sessionCanonical;
  const eyebrowLabel = `${numberToWord(panelCount)} panels \u00B7 ${panelCount}`;

  /* Empty state — no telemetry panels recorded */
  if (sessionPanels.length === 0) {
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
          <RoutingPatternIntro />
          <WorkshopBedrockProfilesStrip />
          <ModeStrip
            patterns={[...ROUTING_PATTERNS]}
            active={activePattern}
            onSelect={handlePatternSelect}
          />
          <div
            style={{
              marginTop: '10px',
              fontFamily: 'var(--at-sans)',
              fontSize: '12px',
              lineHeight: 1.45,
              color: 'var(--at-ink-4)',
            }}
          >
            {showingSessionTrace ? (
              <>
                Timeline matches this session&apos;s recorded trace (
                <span style={{ color: 'var(--at-ink-2)' }}>{sessionCanonical}</span>).
              </>
            ) : (
              <>
                Illustrative <span style={{ color: 'var(--at-ink-2)' }}>{activePattern}</span> steps
                — not this session&apos;s backend trace. This session was recorded as{' '}
                <span style={{ color: 'var(--at-ink-2)' }}>{sessionCanonical}</span>.
              </>
            )}
          </div>

          {/* Eyebrow with panel count */}
          <div style={{ marginTop: '20px', marginBottom: '20px' }}>
            <Eyebrow label={eyebrowLabel} />
          </div>

          {/* Timeline */}
          <div ref={timelineRef}>
            {displayPanels.map((panel, i) => (
              <TimelinePanelCard
                key={`${activePattern}-${panel.index}`}
                panel={panel}
                isActive={panel.index === activeIndex}
                isLast={i === displayPanels.length - 1}
                onClick={() => setActiveIndex(panel.index)}
              />
            ))}
          </div>
        </div>

        {/* Right column — context rail */}
        <ContextRail>
          {pickContext ? (
            <ProductRecommendationCard
              product={pickContext.product}
              blurb={pickContext.blurb}
              reasons={pickContext.reasons}
              confidencePct={pickContext.confidencePct}
              tokenEstimate={pickContext.tokenEstimate}
              tracePanelIndex={pickContext.tracePanelIndex}
              onTracePick={handleTracePick}
            />
          ) : null}
        </ContextRail>
      </div>

      {/* Three-column expansion area */}
      <ExpansionArea panels={displayPanels} />

      {/* Footer strip */}
      <FooterStrip panels={displayPanels} />
    </div>
  );
};

export default TelemetryTab;
