/**
 * Evaluations — Agent evaluation scorecards surface.
 *
 * Accuracy, latency percentiles, citation rates per agent.
 * Version-over-version quality trends for each evaluation recipe.
 * Follows ExpCard pattern with Eyebrows, editorial titles, monospace metadata.
 *
 * Requirements: 13.1, 13.2, 13.3, 13.4
 */

import React from 'react';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  StatusDot,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { EvaluationScorecard } from '../../types';

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
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: 'var(--at-ink-2)',
        fontWeight: 500,
      }}
    >
      {label}
    </span>
    <span
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '28px',
        fontWeight: 300,
        letterSpacing: '-0.02em',
        lineHeight: 1,
        color: highlight ? 'var(--at-ink-1)' : 'var(--at-ink-1)',
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
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          color: 'var(--at-ink-3)',
          fontStyle: 'italic',
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
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: 'var(--at-ink-2)',
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
          stroke="var(--at-red-1)"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.8}
        />
        {/* Data points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={3} fill="var(--at-red-1)" opacity={0.9} />
            {/* Version label */}
            <text
              x={p.x}
              y={height - 2}
              textAnchor="middle"
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                fill: 'var(--at-ink-2)',
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
}

const Scorecard: React.FC<ScorecardProps> = ({ card, index }) => {
  const active = isActive(card);
  const romanNumerals = ['i', 'ii', 'iii', 'iv', 'v'];
  const numeral = romanNumerals[index] ?? `${index + 1}`;

  return (
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
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: '24px',
              color: 'var(--at-red-1)',
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            {numeral}.
          </span>
          <h3
            style={{
              fontFamily: 'var(--at-serif)',
              fontWeight: 400,
              fontSize: '24px',
              letterSpacing: '-0.01em',
              lineHeight: 1.1,
              color: active ? 'var(--at-ink-1)' : 'var(--at-ink-2)',
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
              borderTop: '1px solid var(--at-card-border)',
            }}
          >
            <MetricPill label="Accuracy" value={pct(card.accuracy)} highlight />
            <MetricPill label="P50 latency" value={`${card.latencyP50}ms`} />
            <MetricPill label="P95 latency" value={`${card.latencyP95}ms`} />
            <MetricPill label="Citation rate" value={pct(card.citationRate)} highlight />
          </div>

          {/* Version trend */}
          <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--at-card-border)' }}>
            <VersionTrend trend={card.versionTrend} />
          </div>
        </>
      ) : (
        <div
          style={{
            paddingTop: '16px',
            borderTop: '1px dashed var(--at-rule-2)',
            fontFamily: 'var(--at-serif)',
            fontStyle: 'italic',
            fontSize: '16px',
            color: 'var(--at-ink-2)',
            lineHeight: 1.5,
          }}
        >
          This agent is an exercise. Evaluation data will appear once the agent is implemented and
          benchmarked.
        </div>
      )}
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px 0' }}>
    {Array.from({ length: 5 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
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
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '22px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      We couldn't load the evaluation data.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '16px',
        color: 'var(--at-ink-2)',
        maxWidth: '480px',
        marginTop: '8px',
      }}
    >
      {message}
    </p>
    <button
      onClick={onRetry}
      style={{
        marginTop: '24px',
        fontFamily: 'var(--at-sans)',
        fontSize: '16px',
        fontWeight: 500,
        color: 'var(--at-cream-1)',
        backgroundColor: 'var(--at-ink-1)',
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
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '24px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      No evaluation scorecards have been recorded yet.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '17px',
        color: 'var(--at-ink-2)',
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

const Evaluations: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<EvaluationScorecard[]>({
    key: 'evaluations',
  });

  const scorecards = data ?? [];

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Measure · Evaluations · accuracy · latency · citations"
        title="How good is good enough."
        summary="Agent evaluation scorecards with accuracy, latency percentiles, and citation rates. Version-over-version quality trends track improvement across evaluation recipes."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && scorecards.length === 0 && <EmptyState />}

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
                    fontFamily: 'var(--at-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--at-ink-2)',
                    fontWeight: 500,
                  }}
                >
                  Agents evaluated
                </span>
                <div
                  style={{
                    fontFamily: 'var(--at-sans)',
                    fontSize: '36px',
                    fontWeight: 300,
                    color: 'var(--at-ink-1)',
                    letterSpacing: '-0.02em',
                    marginTop: '4px',
                  }}
                >
                  {scorecards.filter(isActive).length}
                  <span style={{ fontSize: '20px', color: 'var(--at-ink-2)' }}>
                    /{scorecards.length}
                  </span>
                </div>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--at-ink-2)',
                    fontWeight: 500,
                  }}
                >
                  Avg accuracy
                </span>
                <div
                  style={{
                    fontFamily: 'var(--at-sans)',
                    fontSize: '36px',
                    fontWeight: 300,
                    color: 'var(--at-ink-1)',
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
                    : '—'}
                </div>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--at-ink-2)',
                    fontWeight: 500,
                  }}
                >
                  Avg citation rate
                </span>
                <div
                  style={{
                    fontFamily: 'var(--at-sans)',
                    fontSize: '36px',
                    fontWeight: 300,
                    color: 'var(--at-ink-1)',
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
                    : '—'}
                </div>
              </div>
            </div>
          </ExpCard>

          {/* Individual scorecards */}
          {scorecards.map((card, i) => (
            <Scorecard key={card.agentName} card={card} index={i} />
          ))}
        </div>
      )}
    </div>
  );
};

export default Evaluations;
