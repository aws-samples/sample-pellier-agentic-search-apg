/**
 * Micro-eval client: what a smaller rerank candidate pool costs.
 *
 * The endpoint runs the canonical Anna query at two pool sizes, repeated, and
 * reports retrieval quality and latency for each. The frontend does no
 * arithmetic on the query itself: every number here was measured server-side,
 * and an absent endpoint returns `null` so the card can say so.
 */

import { API_BASE_URL, apiFetch } from './apiBase'

/**
 * Both pools in one request. `repetitions` is deliberately absent: the
 * endpoint owns the default and reports back the count it actually ran, so a
 * number pinned here would only ever be a second, staler source of truth.
 */
const MICRO_EVAL_PATH =
  '/api/observatory/search-strategies/micro-eval?pool_k=20&pool_k=3'

/**
 * How many observations each latency figure rests on.
 *
 * Stated because the two figures are not the same kind of measurement: `cold`
 * is always a single pass, so a percentile over it is that one number wearing
 * a statistic's name.
 */
export interface MicroEvalLatencySamples {
  cold: number
  warm: number
}

/** Whether the warm samples are cache hits, and for how long they stay so. */
export interface MicroEvalRerankCache {
  enabled: boolean
  ttl_seconds: number
  note: string
}

export interface MicroEvalVariant {
  pool_k: number
  candidate_coverage: number
  context_precision: number
  mrr: number
  hard_constraint_violations: number
  short_result_rate: number
  citation_coverage: number
  /**
   * Percentiles over whatever the endpoint measured.
   *
   * The endpoint passes the cold pass alone, so today these are that one
   * observation and p50 equals p95. Prefer `latency_cold_ms` and
   * `latency_warm_ms_p50`, which say which path they describe.
   */
  latency_ms_p50: number
  latency_ms_p95: number
  /**
   * The first pass, which pays the Bedrock Rerank call.
   *
   * Optional because a runtime deployed before this field existed does not
   * send it, and an absent figure is unknown, not zero.
   */
  latency_cold_ms?: number
  /**
   * Median of the repetitions, which are cache hits while the rerank cache is
   * enabled. `null` when only one pass ran, so there is no warm path to report.
   */
  latency_warm_ms_p50?: number | null
  latency_samples?: MicroEvalLatencySamples
  rerank_cache?: MicroEvalRerankCache
}

export interface MicroEvalHeldOutCaseVariant {
  pool_k: number
  passed: boolean
  context_precision?: number
  candidate_coverage?: number
  mrr?: number
  returned?: number
  leaked?: string[]
}

export interface MicroEvalHeldOutCase {
  id: string
  kind: 'labels' | 'must_not_return' | 'no_result'
  query: string
  rule: string
  golden_set_size: number
  variants: MicroEvalHeldOutCaseVariant[]
}

export interface MicroEvalResult {
  query: string
  limit: number
  repetitions: number
  /**
   * How many rows are labelled relevant for this query.
   *
   * Every quality metric is a ratio against that set, so zero labels make
   * coverage, precision and MRR read 0.0 for want of a denominator rather
   * than because retrieval failed. Lab 2b pins the labels; until then the
   * surface has to say which of the two it is looking at.
   *
   * Optional because a runtime deployed before this field existed does not
   * send it, and an absent count is unknown, not zero.
   */
  golden_set_size?: number
  variants: MicroEvalVariant[]
  /** The same pool sizes scored on provided labels for a query the tuning labels never described. */
  held_out?: {
    query: string
    golden_set_size: number
    variants: MicroEvalVariant[]
  }
  /** Four query cases the tuning labels never described, plus the slice, one pass per pool. */
  held_out_cases?: MicroEvalHeldOutCase[]
  /** Whether the pool that wins on the tuning labels also wins held out. */
  generalizes?: {
    tuning_best_pool_k: number | null
    held_out_best_pool_k: number | null
    held_out_means?: Array<{ pool_k: number; context_precision: number; mrr: number; candidate_coverage: number }>
    agree: boolean
  }
}

const NUMERIC_FIELDS: Array<keyof MicroEvalVariant> = [
  'pool_k',
  'candidate_coverage',
  'context_precision',
  'mrr',
  'hard_constraint_violations',
  'short_result_rate',
  'citation_coverage',
  'latency_ms_p50',
  'latency_ms_p95',
]

// The optional latency fields are deliberately absent from NUMERIC_FIELDS. A
// runtime older than they are still returns a usable variant, and requiring
// them here would reject the whole payload over a field the card renders as
// "not reported".
function isVariant(value: unknown): value is MicroEvalVariant {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return NUMERIC_FIELDS.every((field) => typeof record[field] === 'number')
}

function isResult(value: unknown): value is MicroEvalResult {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return (
    typeof record.query === 'string' &&
    // Any positive whole number: the endpoint chooses the count and reports
    // what it ran. Half a repetition, or none, describes no measurement.
    typeof record.repetitions === 'number' &&
    Number.isInteger(record.repetitions) &&
    record.repetitions > 0 &&
    Array.isArray(record.variants) &&
    record.variants.length > 0 &&
    record.variants.every(isVariant) &&
    (record.golden_set_size === undefined ||
      (typeof record.golden_set_size === 'number' &&
        Number.isInteger(record.golden_set_size) &&
        record.golden_set_size >= 0))
  )
}

/**
 * Run the micro-eval for pool_k 20 and 3.
 *
 * @param signal Optional abort signal for unmounting callers.
 * @returns The measured result, or `null` when the endpoint is missing or
 *   returned a shape this client does not recognise. Never a partial result:
 *   half a comparison invites a conclusion the run does not support.
 */
export async function fetchMicroEval(
  signal?: AbortSignal,
): Promise<MicroEvalResult | null> {
  try {
    const response = await apiFetch(`${API_BASE_URL}${MICRO_EVAL_PATH}`, { signal })
    if (!response.ok) return null
    const payload: unknown = await response.json()
    return isResult(payload) ? payload : null
  } catch {
    return null
  }
}

/** Percentage points between two 0..1 rates, rounded. */
function points(larger: number, smaller: number): number {
  return Math.round((larger - smaller) * 100)
}

/**
 * One line naming the trade the smaller pool makes.
 *
 * Latency is stated as saved time and quality as lost coverage, because that
 * is the direction of the decision a participant is being asked to weigh.
 */
export function poolCostReading(
  wide: MicroEvalVariant,
  narrow: MicroEvalVariant,
): string {
  // Cold, not p50. The endpoint measures one cold pass per pool and reports the
  // cache-hit repetitions separately, so `latency_ms_p50` is that same single
  // observation. Calling this difference a p50 would dress one sample as a
  // distribution -- the exact claim the split was made to stop making.
  const wideCold = wide.latency_cold_ms ?? wide.latency_ms_p50
  const narrowCold = narrow.latency_cold_ms ?? narrow.latency_ms_p50
  const savedMs = Math.round(wideCold - narrowCold)
  const savings =
    savedMs > 0
      ? `saves ${savedMs} ms on the cold pass`
      : `costs ${Math.abs(savedMs)} ms on the cold pass`
  const lost = points(wide.candidate_coverage, narrow.candidate_coverage)
  const violations =
    narrow.hard_constraint_violations - wide.hard_constraint_violations
  const violationClause =
    violations > 0
      ? ` and lets ${violations} hard-constraint ${
          violations === 1 ? 'violation' : 'violations'
        } through`
      : ''

  if (lost <= 0) {
    return (
      `Pool ${narrow.pool_k} ${savings} and gives up no candidate coverage on ` +
      `this query${violationClause}.`
    )
  }
  return (
    `Pool ${narrow.pool_k} ${savings} and gives up ${lost} points of ` +
    `candidate coverage${violationClause}.`
  )
}
