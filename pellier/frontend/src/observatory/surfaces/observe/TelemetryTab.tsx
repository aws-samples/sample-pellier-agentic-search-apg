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
import { Link, useLocation, useOutletContext } from 'react-router-dom';
import {
  ContextRail,
  ExpCard,
  Eyebrow,
  StatusDot,
  ModeStrip,
} from '../../components';
import type { SessionOutletContext } from './SessionView';
import type { ProductCard, TelemetryPanel } from '../../types';
import { RetrievalReceipt } from '../../components/RetrievalReceipt';
import { parseRetrievalReceipt } from '../../labs/retrievalReceipt';
import { BEDROCK_INFERENCE_PROFILES } from '../../constants/bedrockModels';
import { EmptyState } from '../../../shared';
import type { EvidenceSufficiencyStatus } from '../../../shared/evidenceLedger';
import { resolveProductImageUrl } from '../../../utils/resolveProductImageUrl';
import {
  blurbForProduct,
  buildWhyThisPickReasons,
  estimateTokenCount,
  findRecommendationTurn,
  getTopPickProduct,
  parseTelemetryPanelIndex,
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

/**
 * Map a telemetry panel title to a memory type or operational history.
 */
function detectMemorySubstrate(
  title: string,
): 'Working' | 'Semantic' | 'Episodic' | 'Procedural' | 'Operational' {
  const t = title.toLowerCase();
  if (t.includes('operational') || t.includes('tool activity')) return 'Operational';
  if (t.includes('procedural')) return 'Procedural';
  if (t.includes('episodic')) return 'Episodic';
  if (t.includes('semantic')) return 'Semantic';
  if (t.includes('working')) return 'Working';
  // Legacy fallbacks: STM ≈ working (session turns), LTM ≈ semantic (durable preferences).
  if (t.includes('stm')) return 'Working';
  if (t.includes('ltm')) return 'Semantic';
  return 'Working';
}

function getStatusColor(status: TelemetryPanel['status']): string {
  switch (status) {
    case 'complete':
    case 'succeeded':
      return 'var(--obs-green-1)';
    case 'running':
      return 'var(--obs-red-1)';
    case 'failed':
    case 'denied':
      return 'var(--obs-red-1)';
    case 'not_enforced':
      return '#9a6f21';
    case 'queued':
    case 'planned':
    case 'not_reached':
    case 'unavailable':
      return 'var(--obs-ink-4)';
    default:
      return 'var(--obs-ink-4)';
  }
}

function getStatusLabel(status: TelemetryPanel['status']): string {
  switch (status) {
    case 'complete':
      return 'Complete';
    case 'succeeded':
      return 'Succeeded';
    case 'running':
      return 'Running';
    case 'queued':
      return 'Queued';
    case 'planned':
      return 'Planned';
    case 'failed':
      return 'Failed';
    case 'denied':
      return 'Denied';
    case 'not_reached':
      return 'Not reached';
    case 'not_enforced':
      return 'Not enforced';
    case 'unavailable':
      return 'Unavailable';
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

const DARK_CODE_BLOCK: React.CSSProperties = {
  fontFamily: 'var(--obs-mono)',
  fontSize: '12px',
  lineHeight: 1.6,
  background: 'var(--dl-ink)',
  color: 'var(--dl-accent-soft)',
  borderRadius: 'var(--dl-r-lg)',
  border: '1px solid color-mix(in srgb, var(--dl-accent-soft) 18%, transparent)',
  padding: '14px 16px',
  overflow: 'auto',
  margin: 0,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

function highlightSQL(sql: string): React.ReactNode[] {
  const tokens = sql.split(/(\b\w+\b)/g);
  return tokens.map((token, i) => {
    if (SQL_KEYWORDS.has(token.toUpperCase())) {
      return (
        <span key={i} style={{ color: '#f7c873', fontWeight: 600 }}>
          {token}
        </span>
      );
    }
    if (/^'.*'$/.test(token) || token.includes('%')) {
      return (
        <span key={i} style={{ color: '#e8927c' }}>
          {token}
        </span>
      );
    }
    return <span key={i}>{token}</span>;
  });
}

type StepType =
  | 'Route'
  | 'Plan'
  | 'Memory'
  | 'Skill'
  | 'Query'
  | 'Tool'
  | 'Policy'
  | 'Operator review'
  | 'Model'
  | 'Rerank'
  | 'Reply'
  | 'Write'
  | 'Event';

function stepTypeForPanel(panel: TelemetryPanel): StepType {
  const eventKind = panel.eventKind;
  if (!eventKind) return 'Event';
  const labels: Record<NonNullable<TelemetryPanel['eventKind']>, StepType> = {
    route: 'Route',
    plan: 'Plan',
    memory: 'Memory',
    retrieval: 'Query',
    rerank: 'Rerank',
    model: 'Model',
    tool: 'Tool',
    policy: 'Policy',
    operator_review: 'Operator review',
    aurora: 'Query',
    write: 'Write',
    response: 'Reply',
  };
  return labels[eventKind];
}

const STEP_TYPE_COLORS: Record<StepType, { color: string; bg: string }> = {
  Route: { color: 'var(--obs-green-1)', bg: 'var(--obs-green-soft)' },
  Plan: { color: 'var(--obs-green-1)', bg: 'var(--obs-green-soft)' },
  Memory: { color: '#7b5f92', bg: 'rgba(123, 95, 146, 0.12)' },
  Skill: { color: '#b88a3a', bg: 'rgba(184, 138, 58, 0.12)' },
  Query: { color: 'var(--obs-burgundy)', bg: 'var(--obs-red-soft)' },
  Tool: { color: 'var(--obs-burgundy)', bg: 'var(--obs-red-soft)' },
  Policy: { color: '#7b5f21', bg: 'rgba(123, 95, 33, 0.12)' },
  'Operator review': {
    color: 'var(--obs-red-1)',
    bg: 'var(--obs-red-soft)',
  },
  Model: { color: 'var(--obs-ink-2)', bg: 'rgba(31, 20, 16, 0.06)' },
  Rerank: { color: 'var(--obs-burgundy)', bg: 'var(--obs-red-soft)' },
  Reply: { color: 'var(--obs-ink-2)', bg: 'rgba(31, 20, 16, 0.06)' },
  Write: { color: 'var(--obs-burgundy)', bg: 'var(--obs-red-soft)' },
  Event: { color: 'var(--obs-ink-2)', bg: 'rgba(31, 20, 16, 0.06)' },
};

const StepTypeBadge: React.FC<{ type: StepType }> = ({ type }) => {
  const { color, bg } = STEP_TYPE_COLORS[type];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: '4px',
        backgroundColor: bg,
        color,
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        fontWeight: 600,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        lineHeight: 1.4,
        whiteSpace: 'nowrap',
      }}
    >
      {type}
    </span>
  );
};

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
  const stepType = stepTypeForPanel(panel);

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
            backgroundColor: isActive ? 'var(--obs-ink-1)' : 'var(--obs-cream-2)',
            border: isActive ? 'none' : '1px solid var(--obs-rule-2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            fontWeight: 600,
            color: isActive ? 'var(--obs-cream-1)' : 'var(--obs-ink-1)',
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
              backgroundColor: 'var(--obs-rule-2)',
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
        aria-label={`Step ${panel.index} · ${panel.title}`}
        aria-pressed={isActive}
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
          borderRadius: 'var(--obs-card-radius)',
          background: isActive ? 'var(--obs-cream-elev)' : 'transparent',
          border: isActive ? '1px solid var(--obs-rule-1)' : '1px solid transparent',
          boxShadow: isActive ? '0 2px 8px rgba(31, 20, 16, 0.06)' : 'none',
          cursor: 'pointer',
          transition: 'background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
        }}
      >
        {/* Top row: step-type badge + status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '6px',
          }}
        >
          <StepTypeBadge type={stepType} />
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
                fontFamily: 'var(--obs-mono)',
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
            fontFamily: 'var(--obs-sans)',
            fontSize: '17px',
            fontWeight: 400,
            color: 'var(--obs-ink-1)',
            margin: '0 0 4px 0',
            lineHeight: 1.3,
          }}
        >
          {panel.title}
        </h4>

        {/* Description */}
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '15px',
            color: 'var(--obs-ink-1)',
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
            flexWrap: 'wrap',
            gap: '10px',
          }}
        >
          {panel.agent && (
            <span
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: '12px',
                color: 'var(--obs-ink-2)',
                padding: '2px 8px',
                border: '1px solid var(--obs-rule-2)',
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
              fontFamily: 'var(--obs-mono)',
              fontSize: '13px',
              color: 'var(--obs-ink-2)',
              marginLeft: panel.agent ? '0' : 'auto',
            }}
          >
            {panel.durationMs}ms
          </span>
          {panel.provenance ? (
            <span
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                color: 'var(--obs-ink-4)',
              }}
            >
              {panel.provenance}
            </span>
          ) : null}
          {panel.evidenceRef ? (
            <code
              title={`${panel.evidenceRef.kind}:${panel.evidenceRef.id}`}
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: 'var(--text-label)',
                color: 'var(--obs-ink-4)',
                overflowWrap: 'anywhere',
              }}
            >
              {panel.evidenceRef.kind}:{panel.evidenceRef.id}
            </code>
          ) : null}
        </div>

        {/* Expanded SQL (only for active panel with SQL) */}
        {isActive && panel.sql && (
          <pre
            style={{
              ...DARK_CODE_BLOCK,
              marginTop: '12px',
            }}
          >
            <span style={{ color: '#8a8270' }}>-- panel {panel.index}: {panel.title}</span>
            {'\n'}
            {highlightSQL(panel.sql)}
          </pre>
        )}

        {/* Expanded details: the receipt fields the ledger attached to this
            event. Retrieval and rerank events carry the candidate ranks and
            scores; tool events carry the recorded args and result. The
            backend has always sent these rows; the tab used to drop them. */}
        {isActive ? <PanelDetails panel={panel} /> : null}
      </div>
    </div>
  );
};



/** Keys a tool or evidence row carries that are worth printing verbatim. */
const DETAIL_KEYS = ['args', 'result', 'caller', 'purpose', 'tool'] as const;

const PanelDetails: React.FC<{ panel: TelemetryPanel }> = ({ panel }) => {
  const row = panel.rows?.[0];
  if (!row || typeof row !== 'object') return null;
  if (panel.eventKind === 'retrieval' || panel.eventKind === 'rerank') {
    const view = parseRetrievalReceipt(row as Record<string, unknown>);
    if (!view) return null;
    return (
      <div className="observatory-root" style={{ marginTop: '12px' }}>
        <RetrievalReceipt view={view} />
      </div>
    );
  }
  const entries = DETAIL_KEYS.filter((key) => {
    const value = (row as Record<string, unknown>)[key];
    if (value === null || value === undefined || value === '') return false;
    if (typeof value === 'object' && Object.keys(value as object).length === 0) return false;
    return true;
  });
  if (entries.length === 0) return null;
  return (
    <dl
      data-testid="telemetry-panel-details"
      style={{
        marginTop: '12px',
        display: 'grid',
        gap: '6px 14px',
        gridTemplateColumns: 'max-content minmax(0, 1fr)',
        fontFamily: 'var(--obs-mono)',
        fontSize: '12px',
        color: 'var(--obs-ink-2)',
      }}
    >
      {entries.map((key) => {
        const value = (row as Record<string, unknown>)[key];
        return (
          <React.Fragment key={key}>
            <dt style={{ color: 'var(--obs-ink-3)' }}>{key}</dt>
            <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>
              <code>
                {typeof value === 'string' ? value : JSON.stringify(value)}
              </code>
            </dd>
          </React.Fragment>
        );
      })}
    </dl>
  );
};


/* =======================================================================
 * Context rail — Product recommendation card
 * ======================================================================= */

interface ProductRecommendationCardProps {
  product: ProductCard;
  blurb: string;
  reasons: string[];
  tokenEstimate: number;
  tracePanelIndex: number;
  onTracePick: () => void;
}

const ProductRecommendationCard: React.FC<ProductRecommendationCardProps> = ({
  product,
  blurb,
  reasons,
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
        borderRadius: 'var(--pellier-image-radius-md)',
        overflow: 'hidden',
        marginTop: '14px',
        marginBottom: '14px',
        background: 'var(--obs-cream-2)',
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
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        color: 'var(--obs-ink-2)',
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
        fontFamily: 'var(--obs-sans)',
        fontSize: '17px',
        fontWeight: 500,
        color: 'var(--obs-ink-1)',
        lineHeight: 1.6,
        marginBottom: '4px',
      }}
    >
      {product.name}
    </div>

    {/* Price */}
    <div
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '15px',
        fontWeight: 600,
        color: 'var(--obs-ink-2)',
        marginBottom: '12px',
      }}
    >
      ${product.price}
    </div>

    {/* Editorial blurb */}
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '15px',
        color: 'var(--obs-ink-1)',
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
          fontFamily: 'var(--obs-mono)',
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          color: 'var(--obs-ink-2)',
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
              fontFamily: 'var(--obs-sans)',
              fontSize: '14px',
              color: 'var(--obs-ink-2)',
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
        border: '1px solid var(--obs-ink-1)',
        backgroundColor: 'transparent',
        color: 'var(--obs-ink-1)',
        fontFamily: 'var(--obs-mono)',
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

    {/* Evidence + token count */}
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
            fontFamily: 'var(--obs-mono)',
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            color: 'var(--obs-green-1)',
          }}
        >
          Evidence
        </span>
        <span
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '11px',
            color: 'var(--obs-ink-2)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          Tool-backed
        </span>
      </div>
      <div
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '13px',
          color: 'var(--obs-ink-2)',
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
  // Collect memory panels for "Memory substrate"
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
                    fontFamily: 'var(--obs-mono)',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--obs-ink-1)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    marginBottom: '6px',
                  }}
                >
                  Panel {p.index} · {p.title}
                </div>
                <pre
                  style={{
                    ...DARK_CODE_BLOCK,
                    fontSize: '12px',
                  }}
                >
                  <span style={{ color: '#8a8270' }}>-- panel {p.index}: {p.title}</span>
                  {'\n'}
                  {highlightSQL(p.sql!)}
                </pre>
              </div>
            ))
          ) : (
            <p
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '15px',
                color: 'var(--obs-ink-4)',
                margin: 0,
              }}
            >
              No SQL panels in this session.
            </p>
          )}
        </div>
      </ExpCard>

      {/* Memory types with operational history kept separate */}
      <ExpCard>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <Eyebrow label="Memory substrate" />
          <Link
            to="/observatory/architecture/memory"
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '11px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--obs-burgundy)',
              textDecoration: 'none',
            }}
          >
            → Memory types and operational history
          </Link>
        </div>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            marginTop: '14px',
          }}
        >
          {memoryPanels.length > 0 ? (
            memoryPanels.map((p) => {
              const substrate = detectMemorySubstrate(p.title);
              return (
                <div
                  key={p.index}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '10px',
                    padding: '10px 12px',
                    background: 'var(--obs-cream-2)',
                    borderRadius: '8px',
                  }}
                >
                  <span
                    style={{
                      fontFamily: 'var(--obs-mono)',
                      fontSize: '11px',
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.18em',
                      color: 'var(--obs-ink-1)',
                      padding: '1px 6px',
                      border: '1px solid var(--obs-card-border)',
                      borderRadius: '3px',
                      flexShrink: 0,
                      marginTop: '1px',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {substrate}
                  </span>
                  <div>
                    <div
                      style={{
                        fontFamily: 'var(--obs-sans)',
                        fontSize: '14px',
                        color: 'var(--obs-ink-2)',
                        lineHeight: 1.5,
                      }}
                    >
                      {p.description}
                    </div>
                    <div
                      style={{
                        fontFamily: 'var(--obs-mono)',
                        fontSize: '12px',
                        color: 'var(--obs-ink-2)',
                        marginTop: '4px',
                      }}
                    >
                      {p.durationMs}ms
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <p
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '15px',
                color: 'var(--obs-ink-4)',
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
                  background: 'var(--obs-cream-2)',
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
                      fontFamily: 'var(--obs-sans)',
                      fontSize: '15px',
                      fontWeight: 500,
                      color: 'var(--obs-ink-1)',
                    }}
                  >
                    {name}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--obs-mono)',
                      fontSize: '12px',
                      color: 'var(--obs-ink-2)',
                      marginTop: '2px',
                    }}
                  >
                    {agentPanels.length} panel{agentPanels.length !== 1 ? 's' : ''} · {totalMs}ms
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: 'var(--obs-mono)',
                    fontSize: '11px',
                    fontWeight: 500,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    color: allComplete ? 'var(--obs-green-1)' : 'var(--obs-red-1)',
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
        background: 'var(--obs-cream-2)',
        borderRadius: 'var(--obs-card-radius)',
        flexWrap: 'wrap',
      }}
    >
      {/* Pull quote */}
      <div
        style={{
          flex: 1,
          minWidth: '200px',
          fontFamily: 'var(--obs-sans)',
          fontSize: '15px',
          color: 'var(--obs-ink-1)',
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
                fontFamily: 'var(--obs-heading)',
                fontSize: '22px',
                fontWeight: 400,
                color: 'var(--obs-ink-1)',
                lineHeight: 1,
              }}
            >
              {stat.value}
            </span>
            <span
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                color: 'var(--obs-ink-2)',
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

const ROUTING_PATTERNS = ['Dispatcher', 'Graph'] as const;
type RoutingPattern = (typeof ROUTING_PATTERNS)[number];

export function canonicalRoutingPattern(
  raw: string | undefined,
): RoutingPattern | null {
  const s = (raw ?? '').trim().toLowerCase();
  if (s.includes('graph')) return 'Graph';
  if (s.includes('dispatcher')) return 'Dispatcher';
  return null;
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
        'Dispatcher scores the utterance and hands the turn to one owning agent (Personalization Agent, Search Agent, …). One hop per decision – the shape the Pellier storefront runs in production.',
      status: 'complete',
      durationMs: 58,
      agent: 'Dispatcher',
      eventKind: 'route',
      phase: 'routing',
      provenance: 'presentation-only',
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
      eventKind: 'plan',
      phase: 'routing',
      provenance: 'presentation-only',
    },
    {
      index: 3,
      category: 'both',
      title: 'Hybrid retrieval',
      description:
        'Managed agent invokes search_products_hybrid: pgvector + Postgres FTS in parallel, then RRF merge.',
      status: 'complete',
      durationMs: 312,
      agent: 'Personalization Agent · search_products_hybrid',
      eventKind: 'retrieval',
      phase: 'evidence',
      provenance: 'presentation-only',
      sql:
        'SELECT id, embedding <=> $1::vector AS dist FROM pellier.product_catalog ORDER BY dist LIMIT 20;',
    },
    {
      index: 4,
      category: 'both',
      title: 'Rerank',
      description:
        'Cohere Rerank v3.5 over the fused pool – Bedrock inference profile matches workshop stack.',
      status: 'complete',
      durationMs: 265,
      agent: 'Personalization Agent · search_products_hybrid',
      eventKind: 'rerank',
      phase: 'evidence',
      provenance: 'presentation-only',
    },
    {
      index: 5,
      category: 'managed',
      title: 'Concierge reply',
      description:
        'Single visible assistant turn after the specialist returns – easy to narrate in demos and in shopper-facing UX.',
      status: 'complete',
      durationMs: 980,
      agent: 'Personalization Agent',
      eventKind: 'response',
      phase: 'terminal',
      provenance: 'presentation-only',
    },
  ],
  Graph: [
    {
      index: 1,
      category: 'owned',
      title: 'Review checkpoint already persisted',
      description:
        'The storefront refusal has already created a durable pending row in pellier.approvals and an immutable shopper handoff. The later Operator graph reads that checkpoint; it does not create it.',
      status: 'complete',
      durationMs: 14,
      agent: 'Pellier application · PostgreSQL',
      eventKind: 'write',
      phase: 'execution',
      provenance: 'presentation-only',
      sql:
        "INSERT INTO pellier.approvals (customer_id, tool, args, status, source_turn_id, action_hash) VALUES ($1, $2, $3::jsonb, 'pending', $4, $5);",
    },
    {
      index: 2,
      category: 'both',
      title: 'Case Investigator',
      description:
        'The first agent reads current orders, returns, support records, and the durable shopper handoff from PostgreSQL, preserving fact versus reported context.',
      status: 'complete',
      durationMs: 82,
      agent: 'Case Investigator Agent',
      eventKind: 'model',
      phase: 'reasoning',
      provenance: 'presentation-only',
    },
    {
      index: 3,
      category: 'managed',
      title: 'Resolution Planner',
      description:
        'The second agent turns verified evidence into a bounded resolution brief. It may prepare a proposal, but it cannot record the human decision or execute a write.',
      status: 'complete',
      durationMs: 241,
      agent: 'Resolution Planner Agent',
      eventKind: 'model',
      phase: 'reasoning',
      provenance: 'presentation-only',
    },
    {
      index: 4,
      category: 'owned',
      title: 'Graph artifact persisted',
      description:
        'Pellier appends the assistant turn and its structured Strands Graph artifact to pellier.messages, including the existing review id and action hash.',
      status: 'complete',
      durationMs: 14,
      agent: 'Pellier application · PostgreSQL',
      eventKind: 'write',
      phase: 'execution',
      provenance: 'presentation-only',
      sql:
        "INSERT INTO pellier.messages (session_id, role, content, metadata) VALUES ($1, 'assistant', $2, $3::jsonb);",
    },
    {
      index: 5,
      category: 'managed',
      title: 'Runtime returns to the operator',
      description:
        'The graph invocation completes. A later authenticated request records the human decision and, only after policy allows it, attempts governed execution.',
      status: 'complete',
      durationMs: 33,
      agent: 'Operator Concierge',
      eventKind: 'response',
      phase: 'terminal',
      provenance: 'presentation-only',
    },
  ],
};

const introParagraphStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-sans)',
  fontSize: '14px',
  lineHeight: 1.55,
  color: 'var(--obs-ink-2)',
  margin: 0,
};

const RoutingPatternIntro: React.FC = () => (
  <div style={{ marginBottom: '16px' }}>
  <ExpCard>
    <Eyebrow label="Routing patterns" />
    <p style={{ ...introParagraphStyle, marginTop: '12px' }}>
      <strong style={{ color: 'var(--obs-ink-1)' }}>Dispatcher</strong> is what the{' '}
      <strong style={{ color: 'var(--obs-ink-1)' }}>Pellier storefront</strong> uses in production:
      each shopper turn is routed to one owning specialist at a time, the concierge stays easy
      to reason about, and latency/token paths map cleanly to support and compliance reviews. Workshop
      sessions on this tab are captured from that same path, so the default timeline matches what ships.
    </p>
    <p style={{ ...introParagraphStyle, marginTop: '12px' }}>
      <strong style={{ color: 'var(--obs-ink-1)' }}>Graph</strong> is what the{' '}
      <strong style={{ color: 'var(--obs-ink-1)' }}>Operator Concierge</strong> uses
      for ordered case work: Case Investigator, then Resolution Planner. The graph
      reads a review checkpoint already persisted by the storefront boundary and
      appends its artifact before returning, so a person never waits inside a
      running model process.
    </p>
  </ExpCard>
  </div>
);

/** Mono strip so Telemetry names the same Bedrock profiles as the workshop stack. */
function WorkshopBedrockProfilesStrip() {
  const rows: Array<[string, string]> = [
    ['Claude Opus 5', BEDROCK_INFERENCE_PROFILES.CLAUDE_OPUS_5],
    ['Claude Sonnet 5', BEDROCK_INFERENCE_PROFILES.CLAUDE_SONNET_5],
    ['Claude Haiku 4.5', BEDROCK_INFERENCE_PROFILES.CLAUDE_HAIKU_4_5],
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
        borderRadius: 'var(--obs-card-radius)',
        border: '1px solid var(--obs-rule-1)',
        background: 'var(--obs-cream-2)',
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
              fontFamily: 'var(--obs-sans)',
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--obs-ink-1)',
            }}
          >
            {label}
          </span>
          <code
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '11px',
              color: 'var(--obs-ink-2)',
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

/**
 * The colour reinforcing one sufficiency status.
 *
 * `contradicted` is called out explicitly rather than left to the default:
 * it is a claim refuted by its own evidence, and the muted tone that suits
 * "does not apply" would have rendered a policy DENY sitting beside an
 * execution row for the same tool as though nothing notable had happened.
 * The visible status text remains the carrier; colour only reinforces it.
 */
function sufficiencyColor(status: EvidenceSufficiencyStatus): string {
  if (status === 'satisfied') return 'var(--obs-green-1)'
  if (status === 'missing' || status === 'contradicted') return 'var(--obs-red-1)'
  return 'var(--obs-ink-4)'
}

const TelemetryTab: React.FC = () => {
  const { session } = useOutletContext<SessionOutletContext>();
  const location = useLocation();
  const sessionPanels = session.telemetry ?? [];
  const sessionCanonical = canonicalRoutingPattern(session.routingPattern);
  const initialPattern = sessionCanonical ?? 'Dispatcher';
  const timelineRef = useRef<HTMLDivElement>(null);
  const pendingTracePanel = useRef<number | null>(null);

  const [activePattern, setActivePattern] = useState<RoutingPattern>(initialPattern);

  const displayPanels: TelemetryPanel[] =
    sessionCanonical && activePattern === sessionCanonical
      ? sessionPanels
      : ILLUSTRATIVE_TELEMETRY[activePattern];

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
      if (!canonical) return;
      setActivePattern(canonical);
      const list =
        canonical === sessionCanonical ? sessionPanels : ILLUSTRATIVE_TELEMETRY[canonical];
      setActiveIndex(list.length > 0 ? list[0].index : -1);
    },
    [sessionCanonical, sessionPanels],
  );

  useEffect(() => {
    setActivePattern(initialPattern);
    setActiveIndex(sessionPanels.length > 0 ? sessionPanels[0].index : -1);
    pendingTracePanel.current = null;
  }, [session.id, initialPattern, sessionPanels.length]);

  useEffect(() => {
    const panelIndex = parseTelemetryPanelIndex(location.hash);
    if (panelIndex == null) return;
    if (!sessionCanonical) return;
    pendingTracePanel.current = panelIndex;
    if (activePattern !== sessionCanonical) {
      setActivePattern(sessionCanonical);
      return;
    }
    pendingTracePanel.current = null;
    setActiveIndex(panelIndex);
    requestAnimationFrame(() => scrollToTelemetryPanel(panelIndex));
  }, [location.hash, activePattern, sessionCanonical, scrollToTelemetryPanel]);

  useEffect(() => {
    if (pendingTracePanel.current == null) return;
    if (activePattern !== sessionCanonical) return;
    const panelIndex = pendingTracePanel.current;
    pendingTracePanel.current = null;
    setActiveIndex(panelIndex);
    requestAnimationFrame(() => scrollToTelemetryPanel(panelIndex));
  }, [activePattern, sessionCanonical, scrollToTelemetryPanel]);

  const handleTracePick = useCallback(() => {
    if (!pickContext || !sessionCanonical) return;
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

  /* Empty state: no telemetry panels recorded. The absence is the answer, so
     it is set in the shared EmptyState register rather than as muted grey. */
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
        <EmptyState
          align="center"
          eyebrow="No telemetry"
          headline="No telemetry panels have been recorded for this session."
          body="Telemetry panels appear here as the agentic system processes each step of the conversation."
        />
      </div>
    );
  }

  return (
    <div>
      {/* Two-column layout: timeline + context rail. The same classes ChatTab
          uses, so the rail stacks under the timeline at the 1120px breakpoint
          in base.css; the inline flex this replaced never stacked, and on a
          phone the timeline collapsed to a 42px column. */}
      <div className="observatory-session-replay-layout">
        {/* Left column — timeline */}
        <div className="observatory-session-replay-main">
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
              fontFamily: 'var(--obs-sans)',
              fontSize: '12px',
              lineHeight: 1.45,
              color: 'var(--obs-ink-4)',
            }}
          >
            {showingSessionTrace ? (
              <>
                Timeline matches this session&apos;s recorded trace (
                <span style={{ color: 'var(--obs-ink-2)' }}>{sessionCanonical}</span>).
              </>
            ) : (
              <>
                Illustrative <span style={{ color: 'var(--obs-ink-2)' }}>{activePattern}</span> steps
                – not this session&apos;s backend trace. This session was recorded as{' '}
                <span style={{ color: 'var(--obs-ink-2)' }}>{sessionCanonical}</span>.
              </>
            )}
          </div>

          {showingSessionTrace && session.evidenceLedger ? (
            <section
              aria-label="Evidence sufficiency"
              style={{
                marginTop: '16px',
                padding: '14px 16px',
                border: '1px solid var(--obs-rule-1)',
                borderRadius: 'var(--obs-card-radius)',
                background: 'var(--obs-cream-2)',
              }}
            >
              <div
                style={{
                  fontFamily: 'var(--obs-mono)',
                  fontSize: '11px',
                  fontWeight: 600,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: 'var(--obs-ink-2)',
                  marginBottom: '10px',
                }}
              >
                Evidence sufficiency
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
                  gap: '8px 16px',
                }}
              >
                {session.evidenceLedger.evidenceSufficiency.map((check) => (
                  <div key={check.id} style={{ minWidth: 0 }}>
                    <strong
                      style={{
                        display: 'block',
                        fontFamily: 'var(--obs-sans)',
                        fontSize: '13px',
                        fontWeight: 600,
                        color: 'var(--obs-ink-1)',
                      }}
                    >
                      {check.label}
                    </strong>
                    <span
                      style={{
                        display: 'block',
                        fontFamily: 'var(--obs-mono)',
                        fontSize: 'var(--text-label)',
                        color: sufficiencyColor(check.status),
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                      }}
                    >
                      {check.status.replace(/_/g, ' ')}
                    </span>
                    {check.detail ? (
                      <span
                        style={{
                          display: 'block',
                          marginTop: 2,
                          fontFamily: 'var(--obs-sans)',
                          fontSize: 'var(--text-label)',
                          color: 'var(--obs-ink-2)',
                        }}
                      >
                        {check.detail}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

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
