/**
 * Performance — System performance metrics surface.
 *
 * Stat cards, cold start histogram, latency budget table, pgvector comparison,
 * storage usage bars, and measure controls.
 *
 * Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
} from '../../components';
import { useAgentTraceData } from '../../hooks/useAgentTraceData';
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
                    width: '100%',
                    backgroundColor: color,
                    borderRadius: '7px',
                    opacity: 0.7,
                    transform: `scaleX(${barPct / 100})`,
                    transformOrigin: 'left center',
                    transition: 'transform 240ms cubic-bezier(0.23, 1, 0.32, 1)',
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

/**
 * Read the pgvector version from the running cluster.
 *
 * The extension version decides which of the knobs on this card actually
 * exist (`halfvec` and `binary_quantize` need 0.7+, `hnsw.iterative_scan`
 * needs 0.8.0+), so a hardcoded literal here would be a claim about an
 * environment we are not looking at. `/api/performance/stats` reads
 * `pg_extension.extversion`; anything else renders as unavailable rather
 * than guessing.
 */
const usePgvectorVersion = (): string | null => {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/performance/stats')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (cancelled) return;
        const reported = payload?.pgvector_version;
        setVersion(typeof reported === 'string' && reported ? reported : null);
      })
      .catch(() => {
        if (!cancelled) setVersion(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
};

const STATUS_STYLES: Record<
  PerformanceData['pgvectorTuning'][number]['status'],
  { label: string; color: string }
> = {
  enabled: { label: 'Enabled', color: 'var(--at-green-1)' },
  available: { label: 'Available', color: 'var(--at-red-1)' },
};

const PgvectorTuning: React.FC<PgvectorTuningProps> = ({ tuning }) => {
  const pgvectorVersion = usePgvectorVersion();
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
          ['pgvector version', pgvectorVersion ?? 'unavailable'],
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
        <Eyebrow label="Why this is not a third exercise" variant="muted" />
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.55,
            color: 'var(--at-ink-1)',
            marginTop: '8px',
          }}
        >
          The Pellier catalog has only 40 products, so full benchmarking would
          be theater. The smoke probes prove the features exist on Aurora; the
          workshop keeps the hands-on moment on agent tools and uses this card
          to name the production knobs participants should tune at scale.
        </p>
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Search comparison: reference timing and cost until a participant runs the
 * endpoint; then one intact response with its query and execution evidence.
 * Recall is not measured by this endpoint and is not shown as a live score.
 * ----------------------------------------------------------------------- */

/* -----------------------------------------------------------------------
 * Extracted Filters Strip — receipt for the agentic strategy
 *
 * Renders the Sonnet structured extraction below the agentic row: category
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
        <span style={labelStyle}>Sonnet extract ·</span>
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
        {filters.hardConstraintsEnforced === true && <span style={chipStyle}>Hard constraints enforced</span>}
        {!hasAnyFilter && (
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-ink-3)',
            }}
          >
            no structured signal – degenerates to plain vector + rerank
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
            – category or tag filters relaxed to widen the candidate pool
          </span>
        )}
      </div>
    </div>
  );
};

interface SearchStrategyComparisonProps {
  strategies: PerformanceData['searchStrategies'];
}

type ComparisonStrategy = Omit<
  PerformanceData['searchStrategies'][number],
  'recallAt5' | 'modeledLatencyMs' | 'isShipped'
> & { modeledLatencyMs?: number };

interface ComparisonResult {
  query: string;
  strategies: ComparisonStrategy[];
  sharedQueryEmbeddingObservedMs?: number;
  costModel?: Record<string, unknown>;
}

const SearchStrategyComparison: React.FC<SearchStrategyComparisonProps> = ({ strategies }) => {
  const [query, setQuery] = useState('A housewarming gift under $100 that is in stock');
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => () => {
    requestRef.current?.abort();
    requestRef.current = null;
  }, []);

  const handleRun = async () => {
    const submittedQuery = query.trim();
    if (!submittedQuery || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 75_000);
    setRunning(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/agent-trace/search-strategies/compare?query=${encodeURIComponent(submittedQuery)}`,
        { signal: controller.signal },
      );
      if (!response.ok) throw new Error(`Comparison request failed (HTTP ${response.status}).`);
      const payload: ComparisonResult = await response.json();
      const rows = payload.strategies;
      if (!Array.isArray(rows) || rows.length !== 4 || strategies.some(
        (expected) => rows.filter((row) => row.strategy === expected.strategy).length !== 1,
      ) || rows.some((row) =>
        !Number.isFinite(row.observedMs) || !Number.isFinite(row.modeledCostPerThousandUsd)
        || !Array.isArray(row.products),
      )) {
        throw new Error('The response did not contain four complete strategy rows.');
      }
      if (requestRef.current !== controller) return;
      // Keep the query and all evidence from the same response together.
      // Reference scores must never fill gaps in a live measurement.
      setResult({ ...payload, query: submittedQuery });
    } catch (failure) {
      if (requestRef.current !== controller) return;
      setError(controller.signal.aborted
        ? 'The comparison reached the 75-second limit. Use your saved response or the reference comparison to review the strategies. Mark the live check incomplete and continue with the guide.'
        : `${failure instanceof Error ? failure.message : 'The comparison could not finish.'} Check readiness and retry once, or use the lab’s recovery path.`);
    } finally {
      window.clearTimeout(timeout);
      if (requestRef.current === controller) {
        requestRef.current = null;
        setRunning(false);
      }
    }
  };

  const downloadResult = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'retrieval-comparison.json';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const rendered: ComparisonStrategy[] = result?.strategies ?? strategies;
  const degraded = result?.strategies.filter(
    (row) => row.strategy.includes('rerank') && row.rerankExecuted !== true,
  ) ?? [];
  const cellStyle: React.CSSProperties = {
    padding: '12px', textAlign: 'left', verticalAlign: 'top',
    borderBottom: '1px solid var(--at-rule-1)',
  };
  const buttonStyle: React.CSSProperties = {
    minHeight: '44px', padding: '10px 16px', borderRadius: '6px',
    border: '1px solid var(--at-ink-1)', background: 'var(--at-ink-1)',
    color: 'var(--at-cream-1)', fontWeight: 600,
  };

  return (
    <section id="retrieval-comparison" aria-labelledby="retrieval-comparison-title" style={{ scrollMarginTop: '100px', minWidth: 0 }}>
      <ExpCard>
        <h2 id="retrieval-comparison-title" style={{ fontFamily: 'var(--at-serif)', fontSize: '28px', color: 'var(--at-ink-1)' }}>
          Compare retrieval strategies
        </h2>
        <p style={{ marginTop: '8px', maxWidth: '70ch', lineHeight: 1.6 }}>
          Use Anna’s request to compare product order, hard constraints, time,
          and modeled cost. The terminal and this view call the same comparison
          endpoint. Opening this page does not run a comparison.
        </p>
        <form onSubmit={(event) => { event.preventDefault(); void handleRun(); }} style={{ marginTop: '20px' }}>
          <label htmlFor="retrieval-comparison-query" style={{ display: 'block', marginBottom: '8px', fontWeight: 600 }}>Shopper request</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
            <input
              id="retrieval-comparison-query"
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Query to run against all four search strategies"
              style={{ flex: '1 1 280px', minWidth: 0, width: '100%', padding: '12px', border: '1px solid var(--at-rule-2)', borderRadius: '6px', background: 'var(--at-cream-1)', color: 'var(--at-ink-1)' }}
            />
            <button type="submit" disabled={running || !query.trim()} style={{ ...buttonStyle, cursor: running ? 'wait' : 'pointer', opacity: running || !query.trim() ? 0.6 : 1 }}>
              {running ? 'Comparing…' : 'Run on Aurora'}
            </button>
          </div>
        </form>
        <p role="status" aria-live="polite" style={{ marginTop: '12px', lineHeight: 1.6 }}>
          {running && 'Running four strategies. Allow up to 75 seconds. '}
          {result
            ? `Showing the last completed response for “${result.query}”.`
            : 'Reference only: fixture baseline and modeled p50 values. No products or extracted filters have been measured for this request.'}
        </p>
        {error && <p role="alert" style={{ marginTop: '12px', color: 'var(--at-red-1)', lineHeight: 1.6 }}>{error}</p>}
        {degraded.length > 0 && (
          <p role="alert" style={{ marginTop: '12px', color: 'var(--at-red-1)', lineHeight: 1.6 }}>
            Reranking is unconfirmed for {degraded.map((row) => row.strategy).join(' and ')}.
            These rows do not prove rerank quality. Inspect their ordering and use the lab’s recovery path.
          </p>
        )}
        <div role="region" aria-label="Retrieval strategy results" tabIndex={0} style={{ marginTop: '16px', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', lineHeight: 1.5 }}>
            <caption style={{ textAlign: 'left', padding: '0 12px 12px', fontWeight: 600 }}>
              {result ? 'Observed results and modeled request cost' : 'Illustrative comparison · not a measurement from this environment'}
            </caption>
            <thead><tr>{['Strategy', 'Latency', 'Modeled USD / 1,000 queries', 'Ordering evidence'].map((label) => <th key={label} scope="col" style={cellStyle}>{label}</th>)}</tr></thead>
            <tbody>
              {rendered.map((row) => (
                <React.Fragment key={row.strategy}>
                  <tr>
                    <th scope="row" style={{ ...cellStyle, minWidth: '150px' }}>{row.strategy}</th>
                    <td style={{ ...cellStyle, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                      {formatMs(row.observedMs ?? row.modeledLatencyMs ?? 0)}<br />
                      <small>{result ? 'observed once' : 'modeled p50'}</small>
                    </td>
                    <td style={{ ...cellStyle, fontVariantNumeric: 'tabular-nums' }}>
                      ${row.modeledCostPerThousandUsd.toFixed(4)}
                    </td>
                    <td style={cellStyle}>
                      {!result ? 'Reference only' : row.strategy.includes('rerank')
                        ? row.rerankExecuted === true ? 'Rerank executed' : 'Rerank not confirmed'
                        : 'Retrieved order'}
                      {row.productOrderSource && <div>{row.productOrderSource}</div>}
                      {row.degradedReason && <div style={{ color: 'var(--at-red-1)' }}>{row.degradedReason}</div>}
                    </td>
                  </tr>
                  {result && (
                    <tr><td colSpan={4} style={cellStyle}>
                      <strong>Top results: </strong>{row.products?.length ? row.products.map((product) => product.name).join(' · ') : 'No matching products returned.'}
                      {row.costComponents && <p>Cost components: {row.costComponents.join(', ')}</p>}
                      {row.extractedFilters && <ExtractedFiltersStrip filters={row.extractedFilters} />}
                    </td></tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ marginTop: '16px', lineHeight: 1.6, maxWidth: '70ch' }}>
          A hard constraint determines which rows qualify; ranking orders the
          qualifying rows. This implementation applies price and stock filters
          in the agentic path. Other systems can apply explicit filters before
          any retrieval strategy. There is no required winner.
        </p>
        <p style={{ marginTop: '8px', lineHeight: 1.6, maxWidth: '70ch' }}>
          Latency is one observation per strategy after the shared query embedding.
          Cost models incremental requests and excludes provisioned Aurora compute.
          This comparison does not calculate recall or establish a benchmark.
        </p>
        {result && <>
          <p style={{ marginTop: '12px' }}>Shared query embedding: {result.sharedQueryEmbeddingObservedMs === undefined ? 'not reported' : `${result.sharedQueryEmbeddingObservedMs} ms`}.</p>
          <button type="button" onClick={downloadResult} style={{ ...buttonStyle, marginTop: '12px' }}>Save comparison JSON</button>
          <details style={{ marginTop: '16px' }}>
            <summary style={{ cursor: 'pointer', padding: '8px 0' }}>Inspect cost inputs and full response</summary>
            <pre style={{ overflowX: 'auto', padding: '16px', background: 'var(--at-cream-2)', fontSize: '13px' }}>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </>}
      </ExpCard>
    </section>
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
                  width: '100%',
                  backgroundColor: barColors[i % barColors.length],
                  borderRadius: '5px',
                  opacity: 0.7,
                  transform: `scaleX(${item.percentage / 100})`,
                  transformOrigin: 'left center',
                  transition: 'transform 240ms cubic-bezier(0.23, 1, 0.32, 1)',
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
            type="button"
            onClick={() => onWindowChange(w)}
            aria-pressed={activeWindow === w}
            aria-label={`Time window: ${w}`}
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
        type="button"
        disabled
        aria-label="Run benchmark – coming soon"
        title="Benchmark execution is not part of this Builders’ Session."
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          fontWeight: 500,
          color: 'var(--at-cream-1)',
          backgroundColor: 'var(--at-ink-1)',
          border: 'none',
          borderRadius: '8px',
          padding: '9px 22px',
          cursor: 'not-allowed',
          opacity: 0.55,
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
      type="button"
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
  const { data, loading, error, refetch } = useAgentTraceData<PerformanceData>({
    key: 'performance',
  });

  const [activeWindow, setActiveWindow] = useState('24h');
  const [sampleSize, setSampleSize] = useState(512);

  const isEmpty = !data || (data.sampleCount === 0 && data.histogram.length === 0);

  return (
    <div className="pellier-labs-reference-page" style={{ maxWidth: '1100px' }}>
      <EditorialTitle
        backToReferences
        eyebrow="Measure · Performance · latency · pgvector · storage"
        title="Latency and retrieval budgets"
        summary="Inspect turn timing, pgvector tradeoffs, retrieval comparisons, and storage pressure with live or fixture-backed measurements."
        references={[
          { label: 'Source', value: 'services/performance_log.py', code: true },
          { label: 'Pattern', value: 'turn telemetry + live probes', code: true },
        ]}
      />

      {!loading && data?.searchStrategies?.length ? (
        <SearchStrategyComparison strategies={data.searchStrategies} />
      ) : null}
      <p style={{ margin: '24px 0 12px', color: 'var(--at-ink-2)', lineHeight: 1.6 }}>
        The performance examples below use checked-in reference data. They are
        not measurements from your workshop seat. Live probes identify their
        own results separately.
      </p>

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
