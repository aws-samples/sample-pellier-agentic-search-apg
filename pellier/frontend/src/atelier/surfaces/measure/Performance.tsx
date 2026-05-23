/**
 * Performance — System performance metrics surface.
 *
 * Stat cards, cold start histogram, latency budget table, pgvector comparison,
 * storage usage bars, and measure controls.
 *
 * Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
 */

import React, { useState } from 'react';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { PerformanceData } from '../../types';

/* -----------------------------------------------------------------------
 * Helpers
 * ----------------------------------------------------------------------- */

function formatBytes(bytes: number): string {
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(1)} GB`;
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(0)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

function formatMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

const TYPE_COLORS: Record<string, string> = {
  llm: 'var(--at-red-1)',
  tool: 'var(--at-green-1)',
  memory: '#7c6f64',
};

const TYPE_LABELS: Record<string, string> = {
  llm: 'LLM',
  tool: 'Tool',
  memory: 'Memory',
};

/* -----------------------------------------------------------------------
 * Stat Card
 * ----------------------------------------------------------------------- */

interface StatCardProps {
  label: string;
  value: string;
  unit: string;
  detail: string;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, unit, detail }) => (
  <ExpCard>
    <Eyebrow label={label} variant="muted" />
    <div style={{ marginTop: '14px', display: 'flex', alignItems: 'baseline', gap: '6px' }}>
      <span
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '48px',
          fontWeight: 300,
          letterSpacing: '-0.03em',
          lineHeight: 1,
          color: 'var(--at-ink-1)',
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '14px',
          letterSpacing: '0.1em',
          color: 'var(--at-ink-2)',
          textTransform: 'uppercase',
        }}
      >
        {unit}
      </span>
    </div>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '12px',
        color: 'var(--at-ink-2)',
        marginTop: '8px',
        margin: '8px 0 0',
        letterSpacing: '0.04em',
      }}
    >
      {detail}
    </p>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Cold Start Histogram (SVG)
 * ----------------------------------------------------------------------- */

interface HistogramProps {
  histogram: PerformanceData['histogram'];
}

const ColdStartHistogram: React.FC<HistogramProps> = ({ histogram }) => {
  const maxCount = Math.max(...histogram.map((b) => b.count), 1);
  const barWidth = 64;
  const barGap = 18;
  const chartHeight = 180;
  const chartWidth = histogram.length * (barWidth + barGap) - barGap;
  const svgPadding = { top: 28, bottom: 68, left: 12, right: 12 };
  const totalWidth = chartWidth + svgPadding.left + svgPadding.right;
  const totalHeight = chartHeight + svgPadding.top + svgPadding.bottom;

  return (
    <ExpCard>
      <Eyebrow label="Cold start distribution" />
      <div style={{ marginTop: '16px', overflowX: 'auto' }}>
        <svg
          width={totalWidth}
          height={totalHeight}
          viewBox={`0 0 ${totalWidth} ${totalHeight}`}
          role="img"
          aria-label="Cold start histogram showing bimodal distribution of cold vs warm starts"
          style={{ display: 'block' }}
        >
          {histogram.map((bucket, i) => {
            const barHeight = (bucket.count / maxCount) * chartHeight;
            const x = svgPadding.left + i * (barWidth + barGap);
            const y = svgPadding.top + chartHeight - barHeight;
            const fill = bucket.type === 'warm' ? 'var(--at-green-1)' : 'var(--at-red-1)';

            return (
              <g key={bucket.bucket}>
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barHeight}
                  rx={4}
                  fill={fill}
                  opacity={0.8}
                />
                {/* Count label */}
                <text
                  x={x + barWidth / 2}
                  y={y - 6}
                  textAnchor="middle"
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '12px',
                    fill: 'var(--at-ink-1)',
                  }}
                >
                  {bucket.count}
                </text>
                {/* Bucket label */}
                <text
                  x={x + barWidth / 2}
                  y={svgPadding.top + chartHeight + 16}
                  textAnchor="middle"
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '10px',
                    fill: 'var(--at-ink-2)',
                  }}
                >
                  {bucket.bucket}
                </text>
                {/* Type label */}
                <text
                  x={x + barWidth / 2}
                  y={svgPadding.top + chartHeight + 30}
                  textAnchor="middle"
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '10px',
                    fill: bucket.type === 'warm' ? 'var(--at-green-1)' : 'var(--at-red-1)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.12em',
                  }}
                >
                  {bucket.type}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {/* Legend */}
      <div
        style={{
          display: 'flex',
          gap: '20px',
          marginTop: '12px',
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          color: 'var(--at-ink-2)',
          letterSpacing: '0.08em',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '2px',
              backgroundColor: 'var(--at-green-1)',
              opacity: 0.8,
              display: 'inline-block',
            }}
          />
          Warm reuse
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '2px',
              backgroundColor: 'var(--at-red-1)',
              opacity: 0.8,
              display: 'inline-block',
            }}
          />
          Cold start
        </span>
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Latency Budget Table
 * ----------------------------------------------------------------------- */

interface LatencyBudgetProps {
  budget: PerformanceData['latencyBudget'];
}

const LatencyBudgetTable: React.FC<LatencyBudgetProps> = ({ budget }) => {
  const maxMs = Math.max(...budget.map((r) => r.maxMs), 1);

  return (
    <ExpCard>
      <Eyebrow label="Per-panel latency · p50 / budget" />
      <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {budget.map((row) => {
          const barPct = Math.min((row.p50Ms / maxMs) * 100, 100);
          const color = TYPE_COLORS[row.type] ?? 'var(--at-ink-4)';

          return (
            <div key={row.panel} style={{ display: 'grid', gridTemplateColumns: '200px 1fr 116px', gap: '12px', alignItems: 'center' }}>
              {/* Panel name + type badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '11px',
                    letterSpacing: '0.18em',
                    textTransform: 'uppercase',
                    color,
                    backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {TYPE_LABELS[row.type] ?? row.type}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--at-sans)',
                    fontSize: '15px',
                    color: 'var(--at-ink-2)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {row.panel}
                </span>
              </div>

              {/* Bar */}
              <div
                style={{
                  height: '14px',
                  backgroundColor: 'var(--at-cream-2)',
                  borderRadius: '7px',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${barPct}%`,
                    backgroundColor: color,
                    borderRadius: '7px',
                    opacity: 0.7,
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>

              {/* Value */}
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '13px',
                  color: 'var(--at-ink-2)',
                  textAlign: 'right',
                  letterSpacing: '0.04em',
                  whiteSpace: 'nowrap',
                }}
              >
                {row.p50Ms}ms
                <span style={{ color: 'var(--at-ink-3)', marginLeft: '4px', fontSize: '13px' }}>
                  / {row.maxMs}ms
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * pgvector Comparison Table
 * ----------------------------------------------------------------------- */

interface PgvectorComparisonProps {
  strategies: PerformanceData['pgvectorComparison'];
}

const PgvectorComparison: React.FC<PgvectorComparisonProps> = ({ strategies }) => {
  const headerStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '11px',
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: 'var(--at-ink-2)',
    fontWeight: 500,
    padding: '8px 12px',
    textAlign: 'left',
    borderBottom: '1px solid var(--at-card-border)',
  };

  const cellStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '14px',
    color: 'var(--at-ink-2)',
    padding: '10px 12px',
    letterSpacing: '0.02em',
  };

  return (
    <ExpCard>
      <Eyebrow label="pgvector index comparison" />
      <div style={{ marginTop: '16px', overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            borderSpacing: 0,
          }}
        >
          <thead>
            <tr>
              <th style={headerStyle}>Strategy</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Recall</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>QPS</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Build time</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Storage</th>
              <th style={{ ...headerStyle, textAlign: 'center' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => {
              const isShipped = s.isShipped;
              const rowBg = isShipped ? 'color-mix(in srgb, var(--at-green-1) 6%, transparent)' : 'transparent';

              return (
                <tr key={s.strategy} style={{ backgroundColor: rowBg }}>
                  <td style={{ ...cellStyle, fontWeight: isShipped ? 600 : 400, color: isShipped ? 'var(--at-ink-1)' : cellStyle.color }}>
                    {s.strategy}
                    {isShipped && (
                      <span
                        style={{
                          marginLeft: '8px',
                          fontFamily: 'var(--at-mono)',
                          fontSize: '11px',
                          letterSpacing: '0.18em',
                          textTransform: 'uppercase',
                          color: 'var(--at-green-1)',
                          backgroundColor: 'color-mix(in srgb, var(--at-green-1) 14%, transparent)',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontWeight: 600,
                        }}
                      >
                        Shipped
                      </span>
                    )}
                  </td>
                  <td style={{ ...cellStyle, textAlign: 'right' }}>{(s.recall * 100).toFixed(0)}%</td>
                  <td style={{ ...cellStyle, textAlign: 'right' }}>{s.qps.toLocaleString()}</td>
                  <td style={{ ...cellStyle, textAlign: 'right' }}>{s.buildTime}</td>
                  <td style={{ ...cellStyle, textAlign: 'right' }}>{s.storage}</td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        backgroundColor: isShipped ? 'var(--at-green-1)' : 'var(--at-ink-5)',
                      }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Advanced pgvector Tuning — production knobs behind the simple benchmark
 * ----------------------------------------------------------------------- */

interface PgvectorTuningProps {
  tuning: PerformanceData['pgvectorTuning'];
}

const STATUS_STYLES: Record<
  PerformanceData['pgvectorTuning'][number]['status'],
  { label: string; color: string }
> = {
  enabled: { label: 'Enabled', color: 'var(--at-green-1)' },
  available: { label: 'Available', color: 'var(--at-red-1)' },
};

const PgvectorTuning: React.FC<PgvectorTuningProps> = ({ tuning }) => {
  const headerStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '11px',
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: 'var(--at-ink-2)',
    fontWeight: 500,
    padding: '8px 12px',
    textAlign: 'left',
    borderBottom: '1px solid var(--at-card-border)',
  };

  const cellStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '13px',
    color: 'var(--at-ink-2)',
    padding: '12px',
    lineHeight: 1.45,
    verticalAlign: 'top',
  };

  return (
    <ExpCard>
      <Eyebrow label="Advanced pgvector tuning · recall · storage · speed" />
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          lineHeight: 1.5,
          color: 'var(--at-ink-2)',
          marginTop: '12px',
          maxWidth: '720px',
        }}
      >
        Retrieval performance is not only vector vs hybrid vs rerank. At
        production scale, pgvector index settings and representation choices
        decide whether filtered search returns enough candidates, how much RAM
        the index wants, and how much recall you trade for speed. For this
        workshop's 40-product catalog, halfvec and binary quantization are
        mostly production-awareness knobs, not wins you need to ship today.
      </p>

      <div
        style={{
          marginTop: '16px',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: '12px',
        }}
      >
        {[
          ['pgvector', '0.8.0'],
          ['iterative scan', 'relaxed_order'],
          ['baseline HNSW', '536 KB'],
        ].map(([label, value]) => (
          <div
            key={label}
            style={{
              backgroundColor: 'var(--at-cream-2)',
              border: '1px solid var(--at-card-border)',
              borderRadius: '8px',
              padding: '12px 14px',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '10px',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: 'var(--at-ink-3)',
              }}
            >
              {label}
            </div>
            <div
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '22px',
                fontWeight: 400,
                color: 'var(--at-ink-1)',
                marginTop: '6px',
              }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '16px', overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            borderSpacing: 0,
          }}
        >
          <thead>
            <tr>
              <th style={headerStyle}>Capability</th>
              <th style={headerStyle}>Knob</th>
              <th style={headerStyle}>Smoke result</th>
              <th style={headerStyle}>Tradeoff</th>
              <th style={{ ...headerStyle, textAlign: 'center' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {tuning.map((row) => {
              const status = STATUS_STYLES[row.status];
              const isEnabled = row.status === 'enabled';
              return (
                <tr
                  key={row.capability}
                  style={{
                    backgroundColor: isEnabled
                      ? 'color-mix(in srgb, var(--at-green-1) 6%, transparent)'
                      : 'transparent',
                  }}
                >
                  <td style={{ ...cellStyle, color: 'var(--at-ink-1)' }}>
                    <div style={{ fontWeight: 600 }}>{row.capability}</div>
                    <div
                      style={{
                        fontFamily: 'var(--at-sans)',
                        fontSize: '13px',
                        lineHeight: 1.45,
                        color: 'var(--at-ink-2)',
                        marginTop: '4px',
                      }}
                    >
                      {row.productionUse}
                    </div>
                  </td>
                  <td style={cellStyle}>
                    <code style={{ fontFamily: 'var(--at-mono)', fontSize: '12px' }}>
                      {row.knob}
                    </code>
                  </td>
                  <td style={cellStyle}>{row.smokeResult}</td>
                  <td style={cellStyle}>{row.tradeoff}</td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    <span
                      style={{
                        display: 'inline-block',
                        fontFamily: 'var(--at-mono)',
                        fontSize: '10px',
                        letterSpacing: '0.16em',
                        textTransform: 'uppercase',
                        color: status.color,
                        border: `1px solid ${status.color}`,
                        borderRadius: '999px',
                        padding: '3px 8px',
                      }}
                    >
                      {status.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div
        style={{
          marginTop: '16px',
          padding: '14px 16px',
          backgroundColor: 'var(--at-cream-2)',
          borderLeft: '3px solid var(--at-green-1)',
          borderRadius: '4px',
        }}
      >
        <Eyebrow label="Why this is not a fourth exercise" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.55,
            color: 'var(--at-ink-1)',
            marginTop: '8px',
          }}
        >
          The boutique catalog has only 40 products, so full benchmarking would
          be theater. The smoke probes prove the features exist on Aurora; the
          workshop keeps the hands-on moment on agent tools and uses this card
          to name the production knobs participants should tune at scale.
        </p>
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Search Strategy Comparison — Anna's anchor capability surfaced honestly
 *
 * Four rows: vector only / hybrid (RRF) / hybrid + rerank / agentic.
 * The card has two states:
 *   1. Default — fixture numbers from performance.json. Card always
 *      renders with sensible defaults so the page never has a hole.
 *   2. Live — when the user types a query and clicks "Run on Aurora",
 *      we hit /api/atelier/search-strategies/compare which executes all
 *      four strategies against the catalog and returns measured numbers
 *      + the actual top-5 product names per strategy. The recall@5
 *      column stays the static fixture value (we'd need labeled data
 *      to compute it live) but the p50Ms + products refresh, and the
 *      agentic row also surfaces extractedFilters chips so participants
 *      can see what Haiku pulled out and which filter-degradation step
 *      the pipeline ended up using.
 *
 * The teaching beat: workshop participants can see the rerank lift in
 * dollars AND latency AND product mix differences. The agentic row
 * adds a fourth axis — filter respect. A "$100 milestone gift" query
 * is the canonical case: only the agentic strategy actually keeps
 * results under $100 because Haiku extracted price_max_usd=100 into
 * a WHERE clause; the other three rank but never filter, so a $185
 * candle can still surface in the top-5.
 * ----------------------------------------------------------------------- */

/* -----------------------------------------------------------------------
 * Extracted Filters Strip — receipt for the agentic strategy
 *
 * Renders Haiku's structured extraction below the agentic row: category
 * pills, tag pills, optional price ceiling, optional in-stock badge,
 * the soft_signal phrase, and which filter-degradation step the
 * pipeline ended up using. The degradation badge is the honest one —
 * "drop_cats" tells participants the strict filter set returned too
 * few candidates and the pipeline relaxed.
 * ----------------------------------------------------------------------- */

const FILTER_USED_LABELS: Record<
  NonNullable<PerformanceData['searchStrategies'][number]['extractedFilters']>['filterUsed'],
  { label: string; tone: 'green' | 'red' }
> = {
  strict: { label: 'strict', tone: 'green' },
  drop_tags: { label: 'drop_tags', tone: 'red' },
  drop_cats: { label: 'drop_cats', tone: 'red' },
  drop_all: { label: 'drop_all', tone: 'red' },
};

interface ExtractedFiltersStripProps {
  filters: NonNullable<
    PerformanceData['searchStrategies'][number]['extractedFilters']
  >;
}

const ExtractedFiltersStrip: React.FC<ExtractedFiltersStripProps> = ({
  filters,
}) => {
  const used = FILTER_USED_LABELS[filters.filterUsed] ?? FILTER_USED_LABELS.strict;
  const usedColor = used.tone === 'green' ? 'var(--at-green-1)' : 'var(--at-red-1)';

  const chipStyle: React.CSSProperties = {
    display: 'inline-block',
    fontFamily: 'var(--at-mono)',
    fontSize: '11px',
    letterSpacing: '0.04em',
    padding: '2px 8px',
    borderRadius: '999px',
    border: '1px solid var(--at-card-border)',
    backgroundColor: 'var(--at-cream-1)',
    color: 'var(--at-ink-2)',
  };

  const labelStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '10px',
    letterSpacing: '0.18em',
    textTransform: 'uppercase',
    color: 'var(--at-ink-3)',
    marginRight: '8px',
  };

  const hasAnyFilter =
    filters.categories.length > 0 ||
    filters.tags.length > 0 ||
    filters.priceMaxUsd !== null ||
    filters.inStockOnly;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '10px 12px',
        backgroundColor: 'color-mix(in srgb, var(--at-green-1) 4%, transparent)',
        border: '1px solid var(--at-card-border)',
        borderRadius: '6px',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span style={labelStyle}>Haiku extract ·</span>
        {filters.categories.length > 0 &&
          filters.categories.map((c) => (
            <span key={`cat-${c}`} style={chipStyle}>
              cat: {c}
            </span>
          ))}
        {filters.tags.length > 0 &&
          filters.tags.map((t) => (
            <span key={`tag-${t}`} style={chipStyle}>
              #{t}
            </span>
          ))}
        {filters.priceMaxUsd !== null && (
          <span style={chipStyle}>≤ ${filters.priceMaxUsd}</span>
        )}
        {filters.inStockOnly && <span style={chipStyle}>in stock</span>}
        {!hasAnyFilter && (
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-ink-3)',
              fontStyle: 'italic',
            }}
          >
            no structured signal — degenerates to plain vector + rerank
          </span>
        )}
      </div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span style={labelStyle}>Soft signal →</span>
        <span
          style={{
            fontFamily: 'var(--at-serif)',
            fontStyle: 'italic',
            fontSize: '14px',
            color: 'var(--at-ink-1)',
          }}
        >
          "{filters.softSignal}"
        </span>
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span style={labelStyle}>Filter applied ·</span>
        <span
          style={{
            display: 'inline-block',
            fontFamily: 'var(--at-mono)',
            fontSize: '10px',
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: usedColor,
            border: `1px solid ${usedColor}`,
            borderRadius: '999px',
            padding: '2px 8px',
          }}
        >
          {used.label}
        </span>
        {used.tone === 'red' && (
          <span
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '12px',
              color: 'var(--at-ink-2)',
            }}
          >
            — strict filter returned too few candidates; pipeline relaxed
            gracefully
          </span>
        )}
      </div>
    </div>
  );
};

interface SearchStrategyComparisonProps {
  strategies: PerformanceData['searchStrategies'];
}

const SearchStrategyComparison: React.FC<SearchStrategyComparisonProps> = ({
  strategies,
}) => {
  const [query, setQuery] = useState('');
  const [liveStrategies, setLiveStrategies] =
    useState<PerformanceData['searchStrategies'] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rendered = liveStrategies ?? strategies;

  const handleRun = async () => {
    const q = query.trim();
    if (!q) return;
    setRunning(true);
    setError(null);
    try {
      const r = await fetch(
        `/api/atelier/search-strategies/compare?query=${encodeURIComponent(q)}`,
      );
      if (!r.ok) {
        throw new Error(`API error: ${r.status}`);
      }
      const j = await r.json();
      // Backend returns { strategies: [...] } where each strategy has
      // p50Ms + costPerThousandUsd + products. We merge those onto the
      // fixture's recallAt5 + isShipped so the card stays whole. The
      // agentic strategy additionally carries extractedFilters surfacing
      // what Haiku pulled out and which filter-degradation step ran.
      const merged: PerformanceData['searchStrategies'] = strategies.map((s) => {
        const live = (j.strategies || []).find(
          (l: { strategy: string }) => l.strategy === s.strategy,
        );
        if (!live) return s;
        return {
          ...s,
          p50Ms: live.p50Ms ?? s.p50Ms,
          costPerThousandUsd: live.costPerThousandUsd ?? s.costPerThousandUsd,
          products: live.products,
          extractedFilters: live.extractedFilters,
        };
      });
      setLiveStrategies(merged);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const headerStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '11px',
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: 'var(--at-ink-2)',
    fontWeight: 500,
    padding: '8px 12px',
    textAlign: 'left',
    borderBottom: '1px solid var(--at-card-border)',
  };

  const cellStyle: React.CSSProperties = {
    fontFamily: 'var(--at-mono)',
    fontSize: '14px',
    color: 'var(--at-ink-2)',
    padding: '10px 12px',
    letterSpacing: '0.02em',
  };

  return (
    <ExpCard>
      <Eyebrow label="Search strategy comparison · Anna's anchor capability" />
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          lineHeight: 1.5,
          color: 'var(--at-ink-2)',
          marginTop: '12px',
          maxWidth: '720px',
        }}
      >
        Vector finds meaning. Postgres FTS finds literals. Cohere Rerank reads
        the union and picks. The agentic row goes one step further: Haiku 4.5
        at T=0 splits the query into structured filters (categories, tags,
        price ceiling, in-stock) and a residual taste phrase, then the
        WHERE-clause filters run with{' '}
        <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px' }}>
          hnsw.iterative_scan = relaxed_order
        </code>{' '}
        so a strict filter doesn't silently drop recall. Each row is a real
        choice — recall vs latency vs cost vs filter respect — and the
        workshop teaches that the right answer depends on the query class,
        not the database.
      </p>

      {/* Live-fetch query input — runs all three strategies through the
          backend's /api/atelier/search-strategies/compare endpoint. */}
      <div
        style={{
          marginTop: '16px',
          display: 'flex',
          gap: '8px',
          alignItems: 'stretch',
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !running) handleRun();
          }}
          placeholder="under $100 milestone gift for a homeowner"
          aria-label="Query to run against all four search strategies"
          style={{
            flex: 1,
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            padding: '10px 12px',
            border: '1px solid var(--at-card-border)',
            borderRadius: '4px',
            backgroundColor: 'var(--at-cream-1)',
            color: 'var(--at-ink-1)',
          }}
        />
        <button
          type="button"
          onClick={handleRun}
          disabled={running || !query.trim()}
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            padding: '0 18px',
            border: '1px solid var(--at-ink-1)',
            borderRadius: '4px',
            backgroundColor: 'var(--at-ink-1)',
            color: 'var(--at-cream-1)',
            cursor: running || !query.trim() ? 'not-allowed' : 'pointer',
            opacity: running || !query.trim() ? 0.4 : 1,
          }}
        >
          {running ? 'Running…' : 'Run on Aurora'}
        </button>
      </div>

      {error && (
        <p
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-red-1)',
            marginTop: '10px',
          }}
        >
          {error}
        </p>
      )}

      {liveStrategies && !error && (
        <p
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--at-green-1)',
            marginTop: '10px',
          }}
        >
          Live · Aurora measurement for "{query}"
        </p>
      )}

      <div style={{ marginTop: '16px', overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            borderSpacing: 0,
          }}
        >
          <thead>
            <tr>
              <th style={headerStyle}>Strategy</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Recall@5</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>p50</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>$/1k queries</th>
              <th style={{ ...headerStyle, textAlign: 'center' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rendered.map((s) => {
              const isShipped = s.isShipped;
              const rowBg = isShipped
                ? 'color-mix(in srgb, var(--at-green-1) 6%, transparent)'
                : 'transparent';
              return (
                <React.Fragment key={s.strategy}>
                  <tr style={{ backgroundColor: rowBg }}>
                    <td
                      style={{
                        ...cellStyle,
                        fontWeight: isShipped ? 600 : 400,
                        color: isShipped ? 'var(--at-ink-1)' : cellStyle.color,
                      }}
                    >
                      {s.strategy}
                      {isShipped && (
                        <span
                          style={{
                            marginLeft: '8px',
                            fontFamily: 'var(--at-mono)',
                            fontSize: '11px',
                            letterSpacing: '0.18em',
                            textTransform: 'uppercase',
                            color: 'var(--at-green-1)',
                            backgroundColor:
                              'color-mix(in srgb, var(--at-green-1) 14%, transparent)',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontWeight: 600,
                          }}
                        >
                          Anna's path
                        </span>
                      )}
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'right' }}>
                      {(s.recallAt5 * 100).toFixed(0)}%
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'right' }}>
                      {formatMs(s.p50Ms)}
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'right' }}>
                      ${s.costPerThousandUsd.toFixed(2)}
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          backgroundColor: isShipped
                            ? 'var(--at-green-1)'
                            : 'var(--at-ink-5)',
                        }}
                      />
                    </td>
                  </tr>
                  {/* When live results are available, render the top-5
                      product names under each strategy as a secondary
                      row so the difference between strategies is
                      visible, not just claimed. */}
                  {s.products && s.products.length > 0 && (
                    <tr style={{ backgroundColor: rowBg }}>
                      <td colSpan={5} style={{ padding: '0 12px 12px' }}>
                        <div
                          style={{
                            fontFamily: 'var(--at-mono)',
                            fontSize: '12px',
                            color: 'var(--at-ink-2)',
                            lineHeight: 1.5,
                          }}
                        >
                          <span
                            style={{
                              letterSpacing: '0.18em',
                              textTransform: 'uppercase',
                              fontSize: '10px',
                              color: 'var(--at-ink-3)',
                            }}
                          >
                            Top 5 ·
                          </span>{' '}
                          {s.products.map((p) => p.name).join(' · ')}
                        </div>
                      </td>
                    </tr>
                  )}
                  {/* Agentic-only: surface the structured filters Haiku
                      extracted, the soft_signal the reranker scored
                      against, and which filter-degradation step the
                      pipeline ended up using. This is the receipt for
                      "Haiku → filter → vector → rerank". */}
                  {s.extractedFilters && (
                    <tr style={{ backgroundColor: rowBg }}>
                      <td colSpan={5} style={{ padding: '0 12px 14px' }}>
                        <ExtractedFiltersStrip filters={s.extractedFilters} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Why the agentic row is Anna's path — the framing the workshop
          lands on after participants compare the four strategies. */}
      <div
        style={{
          marginTop: '20px',
          padding: '14px 16px',
          backgroundColor: 'var(--at-cream-2)',
          borderLeft: '3px solid var(--at-green-1)',
          borderRadius: '4px',
        }}
      >
        <Eyebrow label="Why agentic is Anna's path" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.55,
            color: 'var(--at-ink-1)',
            marginTop: '8px',
          }}
        >
          The first three rows <em>rank</em>, but they never <em>filter</em>.
          A "$100 milestone gift" query running through hybrid+rerank can
          still surface a $185 candle in the top-5 — the price ceiling is
          a string the embedding never quite respects. The agentic row
          turns "$100" into a real{' '}
          <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px' }}>
            price &lt;= 100
          </code>{' '}
          predicate, runs cosine over only the rows that pass, and lets
          Cohere Rerank score against the residual taste phrase ("milestone
          gift for a homeowner"). The chips above are the receipt — you
          can see exactly what Haiku extracted, which filter-degradation
          step ran when the strict filter was too tight, and what soft
          signal the reranker actually scored.
        </p>
      </div>

      {/* Postgres FTS gotcha — kept as a teaching foil for the hybrid (RRF)
          row. The agentic strategy bypasses this entire class of bug
          because Haiku owns the lexical decomposition, but participants
          still need to know the failure mode if they ever deploy plain
          FTS. */}
      <div
        style={{
          marginTop: '12px',
          padding: '14px 16px',
          backgroundColor: 'var(--at-cream-2)',
          borderLeft: '3px solid var(--at-red-1)',
          borderRadius: '4px',
        }}
      >
        <Eyebrow label="Why hybrid (RRF) is a teaching foil, not Anna's path" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.55,
            color: 'var(--at-ink-1)',
            marginTop: '8px',
          }}
        >
          Both{' '}
          <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px' }}>
            plainto_tsquery
          </code>{' '}
          and{' '}
          <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px' }}>
            websearch_to_tsquery
          </code>{' '}
          AND-join every stem. A six-stem conversational query
          (<em>"thoughtful gift for someone who loves morning rituals"</em>)
          matches zero products if no description contains all six stems
          together — exactly the shape of query a boutique shopper asks.
          Pellier OR-joins content tokens via{' '}
          <code style={{ fontFamily: 'var(--at-mono)', fontSize: '13px' }}>
            HybridSearch._build_or_tsquery
          </code>{' '}
          to keep the row alive for comparison, but Anna's production
          path is the agentic row above: Haiku owns the structured
          decomposition, and FTS doesn't have to guess.
        </p>
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Storage Usage Bars
 * ----------------------------------------------------------------------- */

interface StorageUsageProps {
  usage: PerformanceData['storageUsage'];
}

const StorageUsageBars: React.FC<StorageUsageProps> = ({ usage }) => {
  const barColors = ['var(--at-red-1)', 'var(--at-green-1)', '#7c6f64'];

  return (
    <ExpCard>
      <Eyebrow label="Storage usage" />
      <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {usage.map((item, i) => (
          <div key={item.label}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                marginBottom: '6px',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--at-sans)',
                  fontSize: '15px',
                  color: 'var(--at-ink-2)',
                }}
              >
                {item.label}
              </span>
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '13px',
                  color: 'var(--at-ink-2)',
                  letterSpacing: '0.04em',
                }}
              >
                {formatBytes(item.sizeBytes)} · {item.percentage}%
              </span>
            </div>
            <div
              style={{
                height: '10px',
                backgroundColor: 'var(--at-cream-2)',
                borderRadius: '5px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${item.percentage}%`,
                  backgroundColor: barColors[i % barColors.length],
                  borderRadius: '5px',
                  opacity: 0.7,
                  transition: 'width 0.4s ease',
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Measure Controls
 * ----------------------------------------------------------------------- */

interface MeasureControlsProps {
  activeWindow: string;
  onWindowChange: (w: string) => void;
  sampleSize: number;
  onSampleSizeChange: (s: number) => void;
}

const TIME_WINDOWS = ['1h', '6h', '24h', '7d'];

const MeasureControls: React.FC<MeasureControlsProps> = ({
  activeWindow,
  onWindowChange,
  sampleSize,
  onSampleSizeChange,
}) => (
  <ExpCard>
    <Eyebrow label="Measure controls" />
    <div
      style={{
        marginTop: '16px',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '24px',
      }}
    >
      {/* Time window pills */}
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--at-ink-2)',
            fontWeight: 500,
            marginRight: '6px',
          }}
        >
          Window
        </span>
        {TIME_WINDOWS.map((w) => (
          <button
            key={w}
            onClick={() => onWindowChange(w)}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              letterSpacing: '0.06em',
              padding: '5px 14px',
              borderRadius: '100px',
              border: activeWindow === w ? '1px solid var(--at-ink-1)' : '1px solid var(--at-card-border)',
              backgroundColor: activeWindow === w ? 'var(--at-ink-1)' : 'transparent',
              color: activeWindow === w ? 'var(--at-cream-1)' : 'var(--at-ink-1)',
              cursor: 'pointer',
              fontWeight: activeWindow === w ? 600 : 400,
              transition: 'all 0.15s ease',
            }}
          >
            {w}
          </button>
        ))}
      </div>

      {/* Sample size slider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
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
          Samples
        </span>
        <input
          type="range"
          min={50}
          max={2000}
          step={50}
          value={sampleSize}
          onChange={(e) => onSampleSizeChange(Number(e.target.value))}
          aria-label="Sample size"
          style={{
            width: '120px',
            accentColor: 'var(--at-red-1)',
          }}
        />
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-2)',
            minWidth: '40px',
            textAlign: 'right',
          }}
        >
          {sampleSize}
        </span>
      </div>

      {/* Run benchmark button */}
      <button
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          fontWeight: 500,
          color: 'var(--at-cream-1)',
          backgroundColor: 'var(--at-ink-1)',
          border: 'none',
          borderRadius: '8px',
          padding: '9px 22px',
          cursor: 'pointer',
          letterSpacing: '0.02em',
          transition: 'opacity 0.15s ease',
        }}
      >
        Run benchmark
      </button>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px 0' }}>
    {/* Stat card skeletons */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
      {[0, 1].map((i) => (
        <div
          key={i}
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '130px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
    {/* Chart skeletons */}
    {[0, 1, 2, 3].map((i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: i === 0 ? '260px' : '180px',
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
      We couldn't load the performance data.
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
    <Eyebrow label="No data" variant="muted" />
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
      No performance metrics have been recorded yet.
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
      Run a benchmark or wait for session data to populate performance metrics.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Performance: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<PerformanceData>({
    key: 'performance',
  });

  const [activeWindow, setActiveWindow] = useState('24h');
  const [sampleSize, setSampleSize] = useState(512);

  const isEmpty = !data || (data.sampleCount === 0 && data.histogram.length === 0);

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Measure · Performance · latency · pgvector · storage"
        title="Under the hood."
        summary="Cold start times, per-panel latency budgets, pgvector index benchmarks, retrieval strategy comparisons, and storage footprint. The Aurora-backed comparison card can run live; advanced pgvector tuning notes come from smoke probes."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && isEmpty && <EmptyState />}

      {!loading && !error && data && !isEmpty && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Stat cards row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <StatCard
              label="P50 cold start"
              value={formatMs(data.coldStartP50)}
              unit="median"
              detail={`${data.sampleCount} samples · bimodal distribution`}
            />
            <StatCard
              label="P50 warm reuse"
              value={formatMs(data.warmReuseP50)}
              unit="median"
              detail={`${data.sampleCount} samples · warm path`}
            />
          </div>

          {/* Cold start histogram */}
          <ColdStartHistogram histogram={data.histogram} />

          {/* Latency budget table */}
          <LatencyBudgetTable budget={data.latencyBudget} />

          {/* pgvector comparison table */}
          <PgvectorComparison strategies={data.pgvectorComparison} />

          {/* Production pgvector knobs — iterative scans and vector
              representation tradeoffs. */}
          {data.pgvectorTuning && data.pgvectorTuning.length > 0 && (
            <PgvectorTuning tuning={data.pgvectorTuning} />
          )}

          {/* Search strategy comparison — Anna's anchor capability.
              Renders even when the fixture defaults are static; the
              "Run on Aurora" textbox lets workshop participants drive
              the live numbers. */}
          {data.searchStrategies && data.searchStrategies.length > 0 && (
            <SearchStrategyComparison strategies={data.searchStrategies} />
          )}

          {/* Storage usage bars */}
          <StorageUsageBars usage={data.storageUsage} />

          {/* Measure controls */}
          <MeasureControls
            activeWindow={activeWindow}
            onWindowChange={setActiveWindow}
            sampleSize={sampleSize}
            onSampleSizeChange={setSampleSize}
          />
        </div>
      )}
    </div>
  );
};

export default Performance;
