/**
 * Evaluations — Agent evaluation scorecards surface.
 *
 * Accuracy, latency percentiles, citation rates per agent.
 * Version-over-version quality trends for each evaluation recipe.
 * Follows ExpCard pattern with Eyebrows, editorial titles, monospace metadata.
 *
 * Requirements: 13.1, 13.2, 13.3, 13.4
 */

import React, { useState, useRef } from 'react';
import './Performance.css';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  StatusDot,
} from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import type { EvaluationScorecard } from '../../types';
import {
  EVALUATION_METHODS,
  PELLIER_EVAL_STACK_NOTE,
  type EvaluationMethod,
} from './evalMethods';
import {
  EVALUATION_METRICS,
  EVAL_METRIC_TIER_LABEL,
  RETRIEVAL_EVAL_PIPELINE_NOTE,
  filterMetricsByTier,
  type EvalMetricTier,
  type EvaluationMetric,
} from './evalMetrics';

/* -----------------------------------------------------------------------
 * Helpers
 * ----------------------------------------------------------------------- */

function pct(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function isActive(card: EvaluationScorecard): boolean {
  return card.accuracy > 0 || card.latencyP50 > 0;
}

/* -----------------------------------------------------------------------
 * Metric Pill — small inline metric display
 * ----------------------------------------------------------------------- */

interface MetricPillProps {
  label: string;
  value: string;
  highlight?: boolean;
}

const MetricPill: React.FC<MetricPillProps> = ({ label, value, highlight }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
      alignItems: 'center',
    }}
  >
    <span
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: 'var(--obs-ink-2)',
        fontWeight: 500,
      }}
    >
      {label}
    </span>
    <span
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '28px',
        fontWeight: 400,
        letterSpacing: '-0.02em',
        lineHeight: 1,
        color: highlight ? 'var(--obs-ink-1)' : 'var(--obs-ink-1)',
      }}
    >
      {value}
    </span>
  </div>
);

/* -----------------------------------------------------------------------
 * Version Trend — SVG sparkline
 * ----------------------------------------------------------------------- */

interface VersionTrendProps {
  trend: EvaluationScorecard['versionTrend'];
}

const VersionTrend: React.FC<VersionTrendProps> = ({ trend }) => {
  if (trend.length === 0) {
    return (
      <div
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '12px',
          color: 'var(--obs-ink-3)',
          padding: '8px 0',
        }}
      >
        No version data
      </div>
    );
  }

  const width = 200;
  const height = 48;
  const padding = { top: 6, bottom: 18, left: 4, right: 4 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const scores = trend.map((t) => t.score);
  const minScore = Math.min(...scores) * 0.95;
  const maxScore = Math.max(...scores) * 1.02;
  const range = maxScore - minScore || 1;

  const points = trend.map((t, i) => {
    const x = padding.left + (i / Math.max(trend.length - 1, 1)) * chartW;
    const y = padding.top + chartH - ((t.score - minScore) / range) * chartH;
    return { x, y, ...t };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  return (
    <div style={{ marginTop: '8px' }}>
      <span
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: 'var(--obs-ink-2)',
          fontWeight: 500,
        }}
      >
        Quality trend
      </span>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Quality trend: ${trend.map((t) => `v${t.version}: ${pct(t.score)}`).join(', ')}`}
        style={{ display: 'block', marginTop: '4px' }}
      >
        {/* Trend line */}
        <path
          d={linePath}
          fill="none"
          stroke="var(--obs-red-1)"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.8}
        />
        {/* Data points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={3} fill="var(--obs-red-1)" opacity={0.9} />
            {/* Version label */}
            <text
              x={p.x}
              y={height - 2}
              textAnchor="middle"
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                fill: 'var(--obs-ink-2)',
              }}
            >
              v{p.version}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
};

/* -----------------------------------------------------------------------
 * Scorecard — single agent evaluation card
 * ----------------------------------------------------------------------- */

interface ScorecardProps {
  card: EvaluationScorecard;
  index: number;
  isSelected: boolean;
  rowRef: (el: HTMLDivElement | null) => void;
  onSelect: () => void;
}

const Scorecard: React.FC<ScorecardProps> = ({ card, index, isSelected, rowRef, onSelect }) => {
  const active = isActive(card);
  const romanNumerals = ['i', 'ii', 'iii', 'iv', 'v'];
  const numeral = romanNumerals[index] ?? `${index + 1}`;

  return (
    <div
      ref={rowRef}
      role="button"
      tabIndex={0}
      aria-label={`Select ${card.agentName} scorecard`}
      aria-pressed={isSelected}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect();
        }
      }}
      style={{
        outline: isSelected ? '2px solid var(--obs-red-1)' : undefined,
        borderRadius: 'var(--obs-card-radius)',
        cursor: 'pointer',
      }}
    >
    <ExpCard>
      {/* Header: numeral + name + status */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
          <span
            style={{
              fontFamily: 'var(--obs-heading)',
              fontWeight: 400,
              fontSize: '24px',
              color: 'var(--obs-red-1)',
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            {numeral}.
          </span>
          <h3
            style={{
              fontFamily: 'var(--obs-heading)',
              fontWeight: 400,
              fontSize: '24px',
              letterSpacing: '-0.01em',
              lineHeight: 1.1,
              color: active ? 'var(--obs-ink-1)' : 'var(--obs-ink-2)',
              margin: 0,
            }}
          >
            {card.agentName}
          </h3>
        </div>
        <StatusDot status={active ? 'idle' : 'empty'} />
      </div>

      {active ? (
        <>
          {/* Metrics row */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '16px',
              paddingTop: '16px',
              borderTop: '1px solid var(--obs-card-border)',
            }}
          >
            <MetricPill label="Accuracy" value={pct(card.accuracy)} highlight />
            <MetricPill label="P50 latency" value={`${card.latencyP50}ms`} />
            <MetricPill label="P95 latency" value={`${card.latencyP95}ms`} />
            <MetricPill label="Citation rate" value={pct(card.citationRate)} highlight />
          </div>

          {/* Version trend */}
          <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--obs-card-border)' }}>
            <VersionTrend trend={card.versionTrend} />
          </div>
        </>
      ) : (
        <div
          style={{
            paddingTop: '16px',
            borderTop: '1px dashed var(--obs-rule-2)',
            fontFamily: 'var(--obs-heading)',
            fontSize: '16px',
            color: 'var(--obs-ink-2)',
            lineHeight: 1.5,
          }}
        >
          This agent is an exercise. Evaluation data will appear once the agent is implemented and
          benchmarked.
        </div>
      )}
    </ExpCard>
    </div>
  );
};

const FIT_LABEL: Record<EvaluationMethod['pellierFit'], string> = {
  strong: 'Strong fit',
  partial: 'Partial fit',
  workshop: 'Production path',
};

const EvaluationMethodsPanel: React.FC<{
  selectedId: string;
  onSelect: (id: string) => void;
}> = ({ selectedId, onSelect }) => {
  const method = EVALUATION_METHODS.find((m) => m.id === selectedId) ?? EVALUATION_METHODS[0];

  return (
    <ExpCard>
      <Eyebrow label="Evaluation methods · what to use when" />
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '15px',
          lineHeight: 1.6,
          color: 'var(--obs-ink-2)',
          margin: '8px 0 16px',
          maxWidth: '720px',
        }}
      >
        {PELLIER_EVAL_STACK_NOTE}
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '18px' }}>
        {EVALUATION_METHODS.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onSelect(m.id)}
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '999px',
              border:
                selectedId === m.id ? '1px solid var(--obs-ink-1)' : '1px solid var(--obs-rule-2)',
              background: selectedId === m.id ? 'var(--obs-ink-1)' : 'var(--obs-cream-2)',
              color: selectedId === m.id ? 'var(--obs-cream-1)' : 'var(--obs-ink-2)',
              cursor: 'pointer',
            }}
          >
            {m.name}
          </button>
        ))}
      </div>
      <div
        style={{
          padding: '16px 18px',
          background: 'var(--obs-cream-2)',
          borderRadius: '8px',
          border: '1px solid var(--obs-card-border)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            gap: '12px',
            marginBottom: '10px',
          }}
        >
          <h3
            style={{
              fontFamily: 'var(--obs-heading)',
              fontSize: '22px',
              fontWeight: 400,
              margin: 0,
              color: 'var(--obs-ink-1)',
            }}
          >
            {method.name}
          </h3>
          <span
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '11px',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color:
                method.pellierFit === 'strong'
                  ? 'var(--obs-green-1)'
                  : method.pellierFit === 'workshop'
                    ? 'var(--obs-red-1)'
                    : 'var(--obs-ink-3)',
            }}
          >
            {FIT_LABEL[method.pellierFit]}
          </span>
        </div>
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            color: 'var(--obs-ink-2)',
            margin: '0 0 12px',
          }}
        >
          {method.tagline} · <span>{method.vendor}</span>
        </p>
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            lineHeight: 1.55,
            color: 'var(--obs-ink-1)',
            margin: '0 0 14px',
          }}
        >
          {method.workshopNote}
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '16px',
          }}
        >
          <div>
            <span
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                color: 'var(--obs-ink-3)',
              }}
            >
              Best for
            </span>
            <ul
              style={{
                margin: '8px 0 0',
                paddingLeft: '18px',
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                color: 'var(--obs-ink-2)',
                lineHeight: 1.5,
              }}
            >
              {method.bestFor.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
          <div>
            <span
              style={{
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                color: 'var(--obs-ink-3)',
              }}
            >
              Watch outs
            </span>
            <ul
              style={{
                margin: '8px 0 0',
                paddingLeft: '18px',
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                color: 'var(--obs-ink-2)',
                lineHeight: 1.5,
              }}
            >
              {method.watchOuts.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </ExpCard>
  );
};

const METRIC_TIER_OPTIONS: Array<{ id: EvalMetricTier | 'all'; label: string }> = [
  { id: 'all', label: 'All layers' },
  { id: 'retrieval', label: 'Retrieval' },
  { id: 'generation', label: 'Generation' },
  { id: 'agent', label: 'Agent' },
];

const EvaluationMetricsPanel: React.FC<{
  selectedId: string;
  onSelect: (id: string) => void;
  tierFilter: EvalMetricTier | 'all';
  onTierChange: (tier: EvalMetricTier | 'all') => void;
}> = ({ selectedId, onSelect, tierFilter, onTierChange }) => {
  const filtered = filterMetricsByTier(EVALUATION_METRICS, tierFilter);
  const metric =
    filtered.find((m) => m.id === selectedId) ??
    EVALUATION_METRICS.find((m) => m.id === selectedId) ??
    filtered[0] ??
    EVALUATION_METRICS[0];

  const tierCounts = {
    all: EVALUATION_METRICS.length,
    retrieval: EVALUATION_METRICS.filter((m) => m.tier === 'retrieval').length,
    generation: EVALUATION_METRICS.filter((m) => m.tier === 'generation').length,
    agent: EVALUATION_METRICS.filter((m) => m.tier === 'agent').length,
  };

  return (
    <ExpCard>
      <Eyebrow label="Metrics · retrieval → grounding → answer" />
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '15px',
          lineHeight: 1.6,
          color: 'var(--obs-ink-2)',
          margin: '8px 0 12px',
          maxWidth: '720px',
        }}
      >
        {RETRIEVAL_EVAL_PIPELINE_NOTE}
      </p>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          marginBottom: '12px',
        }}
      >
        {METRIC_TIER_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => onTierChange(opt.id)}
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '12px',
              padding: '5px 12px',
              borderRadius: '999px',
              border:
                tierFilter === opt.id ? '1px solid var(--obs-ink-1)' : '1px solid var(--obs-rule-2)',
              background: tierFilter === opt.id ? 'var(--obs-ink-1)' : 'var(--obs-cream-2)',
              color: tierFilter === opt.id ? 'var(--obs-cream-1)' : 'var(--obs-ink-2)',
              cursor: 'pointer',
            }}
          >
            {opt.label} ({tierCounts[opt.id]})
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '18px' }}>
        {filtered.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onSelect(m.id)}
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '12px',
              padding: '6px 12px',
              borderRadius: '999px',
              border:
                metric.id === m.id ? '1px solid var(--obs-red-1)' : '1px solid var(--obs-rule-2)',
              background: metric.id === m.id ? 'var(--obs-red-soft)' : 'var(--obs-cream-2)',
              color: metric.id === m.id ? 'var(--obs-ink-1)' : 'var(--obs-ink-2)',
              cursor: 'pointer',
            }}
          >
            {m.shorthand}
          </button>
        ))}
      </div>

      <MetricDetailCard metric={metric} />
    </ExpCard>
  );
};

const MetricDetailCard: React.FC<{ metric: EvaluationMetric }> = ({ metric }) => (
  <div
    style={{
      padding: '16px 18px',
      background: 'var(--obs-cream-2)',
      borderRadius: '8px',
      border: '1px solid var(--obs-card-border)',
    }}
  >
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: '12px',
        marginBottom: '8px',
      }}
    >
      <h3
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: '22px',
          fontWeight: 400,
          margin: 0,
          color: 'var(--obs-ink-1)',
        }}
      >
        {metric.name}
      </h3>
      <span
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '11px',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: 'var(--obs-ink-3)',
        }}
      >
        {EVAL_METRIC_TIER_LABEL[metric.tier]}
      </span>
    </div>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '14px',
        lineHeight: 1.55,
        color: 'var(--obs-ink-2)',
        margin: '0 0 14px',
      }}
    >
      {metric.definition}
    </p>
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '14px',
        marginBottom: '14px',
      }}
    >
      <MetricField label="Formula (plain language)" value={metric.formula} />
      <MetricField label="What it catches" value={metric.catches} />
    </div>
    <MetricField label="Pellier example" value={metric.pellierExample} />
    <div style={{ marginTop: '12px' }}>
      <span
        style={{
          fontFamily: 'var(--obs-mono)',
          fontSize: '11px',
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: 'var(--obs-ink-3)',
        }}
      >
        Often measured via
      </span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
        {metric.measuredVia.map((v) => (
          <span
            key={v}
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '12px',
              padding: '3px 10px',
              borderRadius: '999px',
              background: 'var(--obs-cream-1)',
              border: '1px solid var(--obs-rule-2)',
              color: 'var(--obs-ink-2)',
            }}
          >
            {v}
          </span>
        ))}
      </div>
    </div>
  </div>
);

const MetricField: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <span
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: 'var(--obs-ink-3)',
      }}
    >
      {label}
    </span>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '13px',
        lineHeight: 1.5,
        color: 'var(--obs-ink-1)',
        margin: '6px 0 0',
      }}
    >
      {value}
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px 0' }}>
    {Array.from({ length: 5 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--obs-cream-2)',
          borderRadius: 'var(--obs-card-radius)',
          height: '200px',
          opacity: 0.5,
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      />
    ))}
  </div>
);

/* -----------------------------------------------------------------------
 * Error state
 * ----------------------------------------------------------------------- */

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry }) => (
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
    <Eyebrow label="Something went wrong" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--obs-heading)',
        fontSize: '22px',
        lineHeight: 1.35,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the evaluation data.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '16px',
        color: 'var(--obs-ink-2)',
        maxWidth: '480px',
        marginTop: '8px',
      }}
    >
      {message}
    </p>
    <button
      type="button"
      onClick={onRetry}
      style={{
        marginTop: '24px',
        fontFamily: 'var(--obs-sans)',
        fontSize: '16px',
        fontWeight: 500,
        color: 'var(--obs-cream-1)',
        backgroundColor: 'var(--obs-ink-1)',
        border: 'none',
        borderRadius: '8px',
        padding: '10px 24px',
        cursor: 'pointer',
      }}
    >
      Try again
    </button>
  </div>
);

/* -----------------------------------------------------------------------
 * Empty state
 * ----------------------------------------------------------------------- */

const EmptyState: React.FC = () => (
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
    <Eyebrow label="No evaluations" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--obs-heading)',
        fontSize: '24px',
        lineHeight: 1.35,
        color: 'var(--obs-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No evaluation scorecards have been recorded yet.
    </p>
    <p
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '17px',
        color: 'var(--obs-ink-2)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Evaluation data will appear once agents have been benchmarked against evaluation recipes.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

/**
 * Provenance envelope returned by `GET /api/observatory/evaluations`.
 *
 * The backend reports provenance states that must never be styled alike:
 * `fixture` (illustrative, describes no run), `localGate` (real commit,
 * golden input), and `managed` (real deployed Runtime, trace-backed).
 * A fixture scorecard rendered identically to a measured one invites an
 * attendee to read an illustration as a result.
 */
interface EvaluationProvenanceState {
  label: string;
  available: boolean;
  describes: string;
  sources?: string[];
  operation?: string;
}

interface EvaluationsEnvelope {
  provenance: 'fixture' | 'local-gate' | 'managed';
  states: {
    fixture: EvaluationProvenanceState;
    localGate: EvaluationProvenanceState;
    managed: EvaluationProvenanceState;
  };
  scorecards: EvaluationScorecard[];
}

/** Read the scorecards from either the envelope or a bare array.
 *
 * The fixture loader still returns a bare array (the JSON file is a
 * list), while the live endpoint returns the provenance envelope. Both
 * shapes are handled so the surface renders offline and online. */
function readScorecards(
  data: EvaluationsEnvelope | EvaluationScorecard[] | null,
): EvaluationScorecard[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return data.scorecards ?? [];
}

function readEnvelope(
  data: EvaluationsEnvelope | EvaluationScorecard[] | null,
): EvaluationsEnvelope | null {
  return data && !Array.isArray(data) ? data : null;
}

const PROVENANCE_TONE: Record<EvaluationsEnvelope['provenance'], string> = {
  fixture: 'var(--obs-ink-3)',
  'local-gate': 'var(--obs-amber-1)',
  managed: 'var(--obs-green-1)',
};

const ProvenanceStrip: React.FC<{ envelope: EvaluationsEnvelope }> = ({
  envelope,
}) => {
  // Render the states the API actually returned. This used to hard-code three
  // keys — fixture, localGate, managed — but the endpoint answers with
  // localGate and managed only, so `envelope.states.fixture` was undefined and
  // reading `.available` off it crashed the route into the error boundary.
  // Each state carries its own `label`, so the list stays self-describing if
  // the backend adds or drops one.
  const entries: [string, EvaluationProvenanceState][] = Object.entries(
    envelope.states ?? {},
  )
    .filter((entry): entry is [string, EvaluationProvenanceState] =>
      Boolean(entry[1]),
    )
    .map(([key, state]) => [state.label ?? key, state]);
  return (
    <div
      style={{
        padding: '14px 16px',
        backgroundColor: 'var(--obs-cream-2)',
        border: '1px dashed var(--obs-rule-2)',
        borderRadius: '4px',
      }}
    >
      <Eyebrow
        label={`Where this evidence came from · active: ${envelope.provenance}`}
        variant="muted"
      />
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '13px',
          lineHeight: 1.6,
          color: 'var(--obs-ink-2)',
          margin: '8px 0 10px',
        }}
      >
        These states are not interchangeable. The scorecards below are{' '}
        <strong>{envelope.provenance}</strong> data.
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {entries.map(([name, state]) => (
          <span
            key={name}
            style={{
              fontFamily: 'var(--obs-mono)',
              fontSize: '12px',
              color: state.available
                ? 'var(--obs-ink-1)'
                : 'var(--obs-ink-4)',
              backgroundColor: 'var(--obs-cream-1)',
              border: `1px solid ${
                state.available ? PROVENANCE_TONE[envelope.provenance] : 'var(--obs-rule-1)'
              }`,
              borderRadius: '4px',
              padding: '3px 8px',
            }}
            title={state.describes}
          >
            {name}: {state.available ? 'available' : 'unavailable'} — {state.describes}
          </span>
        ))}
      </div>
    </div>
  );
};

const Evaluations: React.FC = () => {
  const { data, loading, error, refetch } = useObservatoryData<
    EvaluationsEnvelope | EvaluationScorecard[]
  >({
    key: 'evaluations',
  });

  const envelope = readEnvelope(data);
  const scorecards = readScorecards(data);
  const [selectedMethodId, setSelectedMethodId] = useState(EVALUATION_METHODS[0].id);
  const [selectedMetricId, setSelectedMetricId] = useState(EVALUATION_METRICS[0].id);
  const [metricTierFilter, setMetricTierFilter] = useState<EvalMetricTier | 'all'>('retrieval');
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  return (
    <div className="observatory-reading-page">
      <EditorialTitle referenceId="evaluations"
        backToReferences
        eyebrow="Measure · Evaluations · accuracy · latency · citations"
        title="Evaluations"
        summary="Read evaluation configuration and recorded scorecards with their provenance. Extend the lab acceptance checks into a controlled measurement protocol before making broader quality claims."
      />

      <details className="reference-evaluation-methods">
        <summary>Extend the lab checks: evaluation methods and metric definitions</summary>
        <p>Design reference. Choosing a method or metric here does not run an evaluation.</p>
          <EvaluationMethodsPanel
            selectedId={selectedMethodId}
            onSelect={setSelectedMethodId}
          />

          <EvaluationMetricsPanel
            selectedId={selectedMetricId}
            onSelect={setSelectedMetricId}
            tierFilter={metricTierFilter}
            onTierChange={(tier) => {
              setMetricTierFilter(tier);
              const next = filterMetricsByTier(EVALUATION_METRICS, tier);
              if (next.length > 0 && !next.some((m) => m.id === selectedMetricId)) {
                setSelectedMetricId(next[0].id);
              }
            }}
          />

      </details>

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && scorecards.length === 0 && <EmptyState />}

      {!loading && !error && envelope && (
        <div style={{ marginBottom: '16px' }}>
          <ProvenanceStrip envelope={envelope} />
        </div>
      )}

      {!loading && !error && scorecards.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Summary strip */}
          <ExpCard>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: '24px',
                textAlign: 'center',
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: 'var(--obs-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--obs-ink-2)',
                    fontWeight: 500,
                  }}
                >
                  Agents evaluated
                </span>
                <div
                  style={{
                    fontFamily: 'var(--obs-sans)',
                    fontSize: '36px',
                    fontWeight: 400,
                    color: 'var(--obs-ink-1)',
                    letterSpacing: '-0.02em',
                    marginTop: '4px',
                  }}
                >
                  {scorecards.filter(isActive).length}
                  <span style={{ fontSize: '20px', color: 'var(--obs-ink-2)' }}>
                    /{scorecards.length}
                  </span>
                </div>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: 'var(--obs-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--obs-ink-2)',
                    fontWeight: 500,
                  }}
                >
                  Avg accuracy
                </span>
                <div
                  style={{
                    fontFamily: 'var(--obs-sans)',
                    fontSize: '36px',
                    fontWeight: 400,
                    color: 'var(--obs-ink-1)',
                    letterSpacing: '-0.02em',
                    marginTop: '4px',
                  }}
                >
                  {scorecards.filter(isActive).length > 0
                    ? pct(
                        scorecards
                          .filter(isActive)
                          .reduce((sum, c) => sum + c.accuracy, 0) /
                          scorecards.filter(isActive).length,
                      )
                    : '–'}
                </div>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: 'var(--obs-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--obs-ink-2)',
                    fontWeight: 500,
                  }}
                >
                  Avg citation rate
                </span>
                <div
                  style={{
                    fontFamily: 'var(--obs-sans)',
                    fontSize: '36px',
                    fontWeight: 400,
                    color: 'var(--obs-ink-1)',
                    letterSpacing: '-0.02em',
                    marginTop: '4px',
                  }}
                >
                  {scorecards.filter(isActive).length > 0
                    ? pct(
                        scorecards
                          .filter(isActive)
                          .reduce((sum, c) => sum + c.citationRate, 0) /
                          scorecards.filter(isActive).length,
                      )
                    : '–'}
                </div>
              </div>
            </div>
          </ExpCard>

          <p
            style={{
              fontFamily: 'var(--obs-sans)',
              fontSize: '13px',
              color: 'var(--obs-ink-4)',
            }}
          >
            Click a scorecard to focus an agent.
          </p>

          {scorecards.map((card, i) => (
            <Scorecard
              key={card.agentName}
              card={card}
              index={i}
              isSelected={selectedAgent === card.agentName}
              rowRef={(el) => {
                rowRefs.current[card.agentName] = el;
              }}
              onSelect={() =>
                setSelectedAgent((prev) =>
                  prev === card.agentName ? null : card.agentName,
                )
              }
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default Evaluations;
