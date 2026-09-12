/**
 * Micro-eval: the same query, two rerank candidate pools.
 *
 * The reranker can only reorder what retrieval handed it, so the size of the
 * candidate pool is a retrieval decision wearing a ranking costume. This card
 * puts both pools in one table and states the trade in a line, so "make it
 * faster" is weighed against what the faster pool stops finding.
 *
 * Every number is measured server-side, and every caption here names what the
 * backend actually computes: the definitions live in
 * `services/planned_hybrid_retrieval.py::micro_eval_variant`, and a caption
 * that drifts from them is worse than no caption. When the endpoint is not
 * there the card says so rather than drawing an empty table.
 *
 * The run is asked for, never automatic. One press is two pool sizes times
 * the endpoint's repetition count of live Aurora retrieval, each with a
 * Cohere Rerank call, so firing on mount would bill every participant who
 * scrolled past the Performance surface.
 */
import React, { useEffect, useRef, useState } from 'react';

import { ExpCard, Eyebrow } from '../../components';
import {
  fetchMicroEval,
  poolCostReading,
  type MicroEvalResult,
} from '../../../services/microEval';

type Format = 'rate' | 'ratio' | 'count' | 'flag' | 'ms';

/**
 * The variant fields this table renders as a single number.
 *
 * Named explicitly rather than as `keyof MicroEvalVariant`, which now also
 * covers the sample-count and cache objects: those describe the measurement
 * and belong in the disclosure line under the table, not in a cell.
 */
type NumericField =
  | 'candidate_coverage'
  | 'context_precision'
  | 'mrr'
  | 'hard_constraint_violations'
  | 'short_result_rate'
  | 'citation_coverage'
  | 'latency_cold_ms'
  | 'latency_warm_ms_p50';

interface MetricRow {
  label: string;
  field: NumericField;
  format: Format;
  /** What the backend computes for this field, in the participant's terms. */
  note: string;
}

/**
 * The table, in the backend's own definitions.
 *
 * `golden ids` are the labeled relevant rows for the canonical query, pinned
 * in `CANONICAL_ANNA_GOLDEN_IDS`; `returned` is the top `limit` rows after
 * the eligibility recheck.
 */
const METRICS: readonly MetricRow[] = [
  {
    label: 'Candidate coverage',
    field: 'candidate_coverage',
    format: 'rate',
    note: 'labelled relevant rows that reached the rerank pool',
  },
  {
    label: 'Context precision',
    field: 'context_precision',
    format: 'rate',
    note: 'returned rows that are labelled relevant',
  },
  {
    label: 'Reciprocal rank',
    field: 'mrr',
    format: 'ratio',
    note: 'one over the rank of the first labelled relevant row; 1.00 is top',
  },
  {
    label: 'Hard-constraint violations',
    field: 'hard_constraint_violations',
    format: 'count',
    note: 'returned rows over the price ceiling or out of stock',
  },
  {
    label: 'Short result',
    field: 'short_result_rate',
    format: 'flag',
    note: 'the pass returned fewer rows than the limit asked for',
  },
  {
    label: 'Citable-result coverage',
    field: 'citation_coverage',
    format: 'rate',
    note: 'returned rows carrying a citable product id — not whether the answer’s claims are supported',
  },
  // Cold and warm are reported apart because they measure different paths, and
  // the endpoint no longer blends them. There is exactly one cold pass, so a
  // percentile over it would be that single number wearing a statistic's name
  // -- which is what the old "Latency p50 / p95" pair displayed, twice, from
  // the same observation.
  {
    label: 'Latency, cold pass',
    field: 'latency_cold_ms',
    format: 'ms',
    note: 'the first pass, which pays the Bedrock Rerank call',
  },
  {
    label: 'Latency, warm median',
    field: 'latency_warm_ms_p50',
    format: 'ms',
    note: 'median of the repetitions, which are rerank cache hits while the cache is on',
  },
];

// An absent figure is unknown, not zero: a runtime older than the cold/warm
// split does not send these, and a single-pass run has no warm path to report.
// Rendering either as "0 ms" would invent a measurement.
function formatValue(value: number | null | undefined, format: Format): string {
  if (value === null || value === undefined) return 'not reported';
  if (format === 'rate') return `${Math.round(value * 100)}%`;
  // A reciprocal rank is 1, 1/2, 1/3 ...: a position, not a rate. Rendering
  // it as a percentage invited "83% of what?".
  if (format === 'ratio') return value.toFixed(2);
  if (format === 'flag') return value > 0 ? 'Yes' : 'No';
  if (format === 'ms') return `${Math.round(value)} ms`;
  return String(value);
}

const cellStyle: React.CSSProperties = {
  padding: '9px 12px',
  borderTop: '1px solid var(--obs-rule-1)',
  fontFamily: 'var(--obs-mono)',
  fontSize: '13px',
  color: 'var(--obs-ink-1)',
  textAlign: 'right',
  whiteSpace: 'nowrap',
};

const headerStyle: React.CSSProperties = {
  padding: '0 12px 8px',
  fontFamily: 'var(--obs-heading)',
  fontSize: '12px',
  fontWeight: 600,
  letterSpacing: '0.04em',
  color: 'var(--obs-ink-3)',
  textAlign: 'right',
};

const runButtonStyle: React.CSSProperties = {
  marginTop: '14px',
  /* 44px is the touch floor in DESIGN.md; the authored padding gave 39px. */
  minHeight: '44px',
  padding: '9px 18px',
  border: '1px solid var(--obs-ink-1)',
  borderRadius: '4px',
  backgroundColor: 'var(--obs-ink-1)',
  color: 'var(--obs-cream-1)',
  fontFamily: 'var(--obs-heading)',
  fontSize: '12px',
  fontWeight: 600,
  letterSpacing: 0,
  textTransform: 'uppercase',
};

const noteStyle: React.CSSProperties = {
  marginTop: '12px',
  fontFamily: 'var(--obs-sans)',
  fontSize: '14px',
  lineHeight: 1.5,
  color: 'var(--obs-ink-3)',
};

type RunState = 'idle' | 'running' | 'done';

const MicroEvalCard: React.FC = () => {
  const [result, setResult] = useState<MicroEvalResult | null>(null);
  const [state, setState] = useState<RunState>('idle');
  const abortRef = useRef<AbortController | null>(null);

  // Unmounting is the only way a run in flight is abandoned: once the surface
  // is gone the request has nothing left to report to.
  useEffect(() => () => abortRef.current?.abort(), []);

  const run = () => {
    if (state === 'running') return;
    // Nothing is in flight at this point. The guard above and the disabled
    // button both refuse a press while a run is going, so this retires an
    // already-settled controller rather than cancelling live work.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState('running');
    void fetchMicroEval(controller.signal).then((payload) => {
      if (controller.signal.aborted) return;
      setResult(payload);
      setState('done');
    });
  };

  const runControl = (
    <button
      type="button"
      onClick={run}
      disabled={state === 'running'}
      data-testid="micro-eval-run"
      style={{
        ...runButtonStyle,
        cursor: state === 'running' ? 'not-allowed' : 'pointer',
        opacity: state === 'running' ? 0.4 : 1,
      }}
    >
      {state === 'running' ? 'Running\u2026' : 'Run both pools on Aurora'}
    </button>
  );

  if (state === 'idle') {
    return (
      <ExpCard>
        <Eyebrow label="Rerank pool micro-eval" variant="muted" />
        <p style={noteStyle}>
          Runs the canonical query at pool_k 20 and pool_k 3 and scores both
          against the labelled relevant rows. Every pass is live Aurora
          retrieval plus a Cohere Rerank call, so it runs when you ask.
        </p>
        {runControl}
      </ExpCard>
    );
  }

  if (state === 'running') {
    return (
      <ExpCard>
        <Eyebrow label="Rerank pool micro-eval" variant="muted" />
        <p data-testid="micro-eval-loading" role="status" style={noteStyle}>
          Running the canonical query at both pool sizes.
        </p>
        {runControl}
      </ExpCard>
    );
  }

  if (!result) {
    return (
      <ExpCard>
        <Eyebrow label="Rerank pool micro-eval" variant="muted" />
        <p data-testid="micro-eval-unavailable" style={noteStyle}>
          The micro-eval endpoint did not answer, so there is nothing measured
          to compare. Numbers invented here would describe no run.
        </p>
        {runControl}
      </ExpCard>
    );
  }

  const sorted = [...result.variants].sort((a, b) => b.pool_k - a.pool_k);
  const [wide, narrow] = sorted;

  // What the two latency rows rest on, said out loud. The cold figure is one
  // pass by construction, so without this a reader carries the repetition
  // count in the caption down onto both rows and reads a distribution into a
  // single observation.
  const samples = wide?.latency_samples;
  const cache = wide?.rerank_cache;
  const cacheClause = cache
    ? cache.enabled
      ? ` The repetitions are rerank cache hits (${cache.ttl_seconds}s TTL), not repeat Bedrock calls.`
      : ' The rerank cache is off, so every repetition pays its own Bedrock call.'
    : '';
  const samplesNote = samples
    ? `Latency rests on ${samples.cold} cold pass and ${samples.warm} warm ${
        samples.warm === 1 ? 'repetition' : 'repetitions'
      } per pool.${cacheClause}`
    : null;
  const heldOut = result.held_out;

  return (
    <ExpCard>
      <Eyebrow label="Rerank pool micro-eval" />
      <p
        style={{
          margin: '12px 0 4px',
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          lineHeight: 1.5,
          color: 'var(--obs-ink-2)',
        }}
      >
        <span style={{ fontFamily: 'var(--obs-mono)', fontSize: '13px' }}>
          {result.query}
        </span>
      </p>
      <p
        style={{
          margin: '0 0 14px',
          fontFamily: 'var(--obs-sans)',
          fontSize: '12px',
          color: 'var(--obs-ink-3)',
        }}
      >
        {`Top ${result.limit} results, ${result.repetitions} repetitions per pool, measured on Aurora.`}
      </p>

      {result.golden_set_size === 0 ? (
        <p
          data-testid="micro-eval-unlabelled"
          style={{
            margin: '0 0 14px',
            padding: '10px 12px',
            borderLeft: '2px solid var(--obs-accent)',
            background: 'var(--obs-surface-2)',
            fontFamily: 'var(--obs-sans)',
            fontSize: '13px',
            lineHeight: 1.5,
            color: 'var(--obs-ink-2)',
          }}
        >
          No rows are labelled relevant for this query yet, so coverage,
          precision and MRR below read 0.0 for want of a denominator, not
          because retrieval failed. Latency is measured either way. Inspect the
          provided label configuration before interpreting these diagnostics.
        </p>
      ) : null}

      <div style={{ overflowX: 'auto' }}>
        <table
          aria-label="Rerank pool comparison"
          style={{ width: '100%', borderCollapse: 'collapse' }}
        >
          <thead>
            <tr>
              <th scope="col" style={{ ...headerStyle, textAlign: 'left' }}>
                Metric
              </th>
              {sorted.map((variant) => (
                <th key={variant.pool_k} scope="col" style={headerStyle}>
                  {`pool_k ${variant.pool_k}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {METRICS.map((metric) => (
              <tr key={metric.field}>
                <th
                  scope="row"
                  style={{
                    ...cellStyle,
                    textAlign: 'left',
                    fontFamily: 'var(--obs-sans)',
                    fontWeight: 500,
                    whiteSpace: 'normal',
                  }}
                >
                  {metric.label}
                  <span
                    style={{
                      display: 'block',
                      fontSize: '11px',
                      color: 'var(--obs-ink-3)',
                    }}
                  >
                    {metric.note}
                  </span>
                </th>
                {sorted.map((variant) => (
                  <td key={variant.pool_k} style={cellStyle}>
                    {formatValue(variant[metric.field], metric.format)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {heldOut && heldOut.variants.length > 0 ? (
        <div data-testid="micro-eval-held-out" style={{ marginTop: '14px' }}>
          <p
            style={{
              margin: '0 0 8px',
              fontFamily: 'var(--obs-sans)',
              fontSize: '13px',
              lineHeight: 1.5,
              color: 'var(--obs-ink-2)',
            }}
          >
            {`Held-out check: the same pools scored on ${heldOut.golden_set_size} provided labels for "${heldOut.query}". These provided labels support an optional diagnostic comparison.`}
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table
              aria-label="Held-out rerank pool comparison"
              style={{ width: '100%', borderCollapse: 'collapse' }}
            >
              <thead>
                <tr>
                  <th scope="col" style={{ ...headerStyle, textAlign: 'left' }}>
                    Held-out metric
                  </th>
                  {[...heldOut.variants]
                    .sort((a, b) => b.pool_k - a.pool_k)
                    .map((variant) => (
                      <th key={variant.pool_k} scope="col" style={headerStyle}>
                        {`pool_k ${variant.pool_k}`}
                      </th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {METRICS.filter((metric) =>
                  ['candidate_coverage', 'context_precision', 'mrr'].includes(metric.field),
                ).map((metric) => (
                  <tr key={`held-out-${metric.field}`}>
                    <th
                      scope="row"
                      style={{
                        ...cellStyle,
                        textAlign: 'left',
                        fontFamily: 'var(--obs-sans)',
                        fontWeight: 500,
                        whiteSpace: 'normal',
                      }}
                    >
                      {metric.label}
                    </th>
                    {[...heldOut.variants]
                      .sort((a, b) => b.pool_k - a.pool_k)
                      .map((variant) => (
                        <td key={variant.pool_k} style={cellStyle}>
                          {formatValue(variant[metric.field], metric.format)}
                        </td>
                      ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.held_out_cases && result.held_out_cases.length > 0 ? (
            <div style={{ overflowX: 'auto', marginTop: '10px' }}>
              <table
                aria-label="Held-out query cases"
                data-testid="micro-eval-held-out-cases"
                style={{ width: '100%', borderCollapse: 'collapse' }}
              >
                <thead>
                  <tr>
                    <th scope="col" style={{ ...headerStyle, textAlign: 'left' }}>
                      Held-out case
                    </th>
                    {[...result.held_out_cases[0].variants]
                      .sort((a, b) => b.pool_k - a.pool_k)
                      .map((variant) => (
                        <th key={variant.pool_k} scope="col" style={headerStyle}>
                          {`pool_k ${variant.pool_k}`}
                        </th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {result.held_out_cases.map((heldOutCase) => (
                    <tr key={heldOutCase.id}>
                      <th
                        scope="row"
                        style={{
                          ...cellStyle,
                          textAlign: 'left',
                          fontFamily: 'var(--obs-sans)',
                          fontWeight: 500,
                          whiteSpace: 'normal',
                        }}
                      >
                        {heldOutCase.query}
                        <span
                          style={{ display: 'block', fontSize: '11px', color: 'var(--obs-ink-3)' }}
                        >
                          {heldOutCase.rule}
                        </span>
                      </th>
                      {[...heldOutCase.variants]
                        .sort((a, b) => b.pool_k - a.pool_k)
                        .map((variant) => (
                          <td key={variant.pool_k} style={cellStyle}>
                            {heldOutCase.kind === 'labels'
                              ? `precision ${formatValue(variant.context_precision, 'ratio')}`
                              : variant.passed
                                ? 'pass'
                                : `fail (${variant.returned ?? 0} returned)`}
                          </td>
                        ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {result.generalizes ? (
            <p
              data-testid="micro-eval-generalizes"
              style={{
                margin: '8px 0 0',
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                lineHeight: 1.5,
                color: 'var(--obs-ink-1)',
              }}
            >
              {result.generalizes.agree
                ? `pool_k ${result.generalizes.tuning_best_pool_k} wins on your labels and on the held-out labels.`
                : `pool_k ${result.generalizes.tuning_best_pool_k} wins on your labels, but pool_k ${result.generalizes.held_out_best_pool_k} wins held out. A finding, not a failure: decide which to ship, and say why the sets disagree.`}
            </p>
          ) : null}
        </div>
      ) : null}

      {samplesNote ? (
        <p
          data-testid="micro-eval-samples"
          style={{
            margin: '10px 0 0',
            fontFamily: 'var(--obs-sans)',
            fontSize: '12px',
            lineHeight: 1.5,
            color: 'var(--obs-ink-3)',
          }}
        >
          {samplesNote}
        </p>
      ) : null}

      {wide && narrow ? (
        <p
          data-testid="micro-eval-reading"
          style={{
            margin: '14px 0 0',
            paddingTop: '12px',
            borderTop: '1px solid var(--obs-rule-1)',
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            lineHeight: 1.5,
            color: 'var(--obs-ink-1)',
          }}
        >
          {poolCostReading(wide, narrow)}
        </p>
      ) : null}
      {runControl}
    </ExpCard>
  );
};

export default MicroEvalCard;
