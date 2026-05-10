/**
 * PgvectorBenchSections — three collapsible accordion sections that
 * replace the old modal-based IndexPerformanceDashboard.
 *
 * Each section is self-contained: owns its own state, fetch logic, and
 * UI. Styled with the Atelier cream/ink palette (inline styles for
 * color/font, Tailwind for layout).
 *
 * Exports:
 *   - HnswBenchmarkSection
 *   - QuantizationSection
 *   - IterativeScanSection
 */
import { useState, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'

// ---------------------------------------------------------------------------
// Design tokens
// ---------------------------------------------------------------------------
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'

const FONT_TITLE = 'Fraunces, Georgia, serif'
const FONT_BODY = 'Inter, system-ui, sans-serif'
const FONT_MONO = 'JetBrains Mono, ui-monospace, monospace'

const CARD_BORDER = '1px solid rgba(45, 24, 16, 0.12)'
const INPUT_BORDER = '1px solid rgba(45, 24, 16, 0.15)'

// Warm tints for result cards (replacing old neon greens/purples)
const TINT_A = 'rgba(45, 24, 16, 0.03)' // faint ink wash
const TINT_B = 'rgba(196, 69, 54, 0.04)' // faint accent wash
const TINT_C = 'rgba(166, 134, 104, 0.08)' // warm sand wash

// ---------------------------------------------------------------------------
// Shared interfaces
// ---------------------------------------------------------------------------

interface PerformanceResults {
  query: string
  ef_search: number
  limit: number
  dataset_size: number
  num_runs: number
  hnsw: {
    execution_time_ms: number
    median_time_ms: number
    all_times_ms: number[]
    result_count: number
    index_used: string
    ef_search: number
    index_type: string
    num_runs: number
  }
  sequential: {
    execution_time_ms: number
    median_time_ms: number
    all_times_ms: number[]
    result_count: number
    index_type: string
    num_runs: number
  }
  comparison: {
    speedup_factor: number
    time_saved_ms: number
    time_saved_pct: number
    recall_pct: number
    dataset_size: number
    dataset_context: {
      size_category: string
      size_note: string
      ef_search_note: string
      rows: number
      show_small_dataset_warning: boolean
    }
    recommendation: string
  }
}

interface QuantData {
  row_count: number
  dimensions: number
  full_precision: {
    type: string
    bytes_per_vector: number
    index_bytes: number
    index_size: string
  }
  scalar_quantization: {
    type: string
    bytes_per_vector: number
    estimated_index_bytes: number
    estimated_index_size: string
    memory_reduction: string
  }
  binary_quantization: {
    type: string
    bytes_per_vector: number
    estimated_index_bytes: number
    estimated_index_size: string
    memory_reduction: string
  }
  sql_examples: { sq: string; bq: string }
  note: string
}

interface QuantBenchResults {
  float32?: {
    execution_time_ms: number
    result_count: number
  }
  halfvec_available: boolean
  halfvec?: {
    execution_time_ms: number
    result_count: number
    recall_vs_float32: number
    error?: string
  }
  binary_available: boolean
  binary?: {
    execution_time_ms: number
    result_count: number
    recall_vs_float32: number
    error?: string
  }
}

interface IterativeScanResults {
  pgvector_080_available: boolean
  category_filter: string
  limit: number
  without_iterative_scan?: {
    result_count: number
    execution_time_ms: number
  }
  with_iterative_scan?: {
    result_count: number
    execution_time_ms: number
  }
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function AccordionHeader({
  eyebrow,
  title,
  open,
  onToggle,
}: {
  eyebrow: string
  title: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between gap-4"
      style={{
        padding: '18px 24px',
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      <div className="flex items-baseline gap-3">
        <span
          style={{
            fontFamily: FONT_BODY,
            fontSize: 11,
            fontWeight: 500,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: INK_QUIET,
          }}
        >
          {eyebrow}
        </span>
        <span
          style={{
            fontFamily: FONT_TITLE,
            fontSize: 20,
            fontWeight: 600,
            color: INK,
          }}
        >
          {title}
        </span>
      </div>
      <ChevronDown
        size={18}
        style={{
          color: INK_QUIET,
          transition: 'transform 250ms ease',
          transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          flexShrink: 0,
        }}
      />
    </button>
  )
}

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <div
      className="animate-spin rounded-full"
      style={{
        width: size,
        height: size,
        border: `2px solid ${INK_QUIET}`,
        borderTopColor: 'transparent',
      }}
    />
  )
}

function MonoCodeBlock({
  label,
  children,
}: {
  label?: string
  children: string
}) {
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: INPUT_BORDER }}
    >
      {label && (
        <div
          style={{
            padding: '8px 14px',
            fontFamily: FONT_BODY,
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            color: INK_SOFT,
            borderBottom: INPUT_BORDER,
            background: 'rgba(245, 232, 211, 0.5)',
          }}
        >
          {label}
        </div>
      )}
      <pre
        className="overflow-x-auto"
        style={{
          margin: 0,
          padding: '14px 16px',
          fontFamily: FONT_MONO,
          fontSize: 12.5,
          lineHeight: 1.6,
          color: INK,
          background: CREAM_WARM,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {children}
      </pre>
    </div>
  )
}

function ResultCard({
  title,
  tint,
  children,
}: {
  title: string
  tint?: string
  children: React.ReactNode
}) {
  return (
    <div
      className="rounded-lg flex-1"
      style={{
        padding: '18px 20px',
        background: tint || TINT_A,
        border: CARD_BORDER,
      }}
    >
      <h4
        style={{
          fontFamily: FONT_BODY,
          fontSize: 13,
          fontWeight: 600,
          color: INK,
          marginBottom: 12,
        }}
      >
        {title}
      </h4>
      {children}
    </div>
  )
}

function MetricRow({
  label,
  value,
  mono,
}: {
  label: string
  value: string | number
  mono?: boolean
}) {
  return (
    <div className="flex justify-between items-baseline" style={{ marginBottom: 6 }}>
      <span
        style={{
          fontFamily: FONT_BODY,
          fontSize: 12,
          color: INK_QUIET,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: mono ? FONT_MONO : FONT_BODY,
          fontSize: 13,
          fontWeight: 600,
          color: INK,
        }}
      >
        {value}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 1. HnswBenchmarkSection
// ---------------------------------------------------------------------------

export function HnswBenchmarkSection() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('luxury watch')
  const [efSearch, setEfSearch] = useState(40)
  const [limit, setLimit] = useState(10)
  const [results, setResults] = useState<PerformanceResults | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runComparison = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/performance/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, ef_search: efSearch, limit }),
      })
      if (!res.ok) throw new Error('Performance comparison failed')
      setResults(await res.json())
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to run comparison'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="rounded-xl"
      style={{
        background: 'white',
        border: CARD_BORDER,
        overflow: 'hidden',
      }}
    >
      <AccordionHeader
        eyebrow="iv."
        title="HNSW vs sequential scan."
        open={open}
        onToggle={() => setOpen(!open)}
      />

      {open && (
        <div style={{ padding: '0 24px 24px' }}>
          {/* Controls */}
          <div className="grid grid-cols-1 gap-4 mb-5 sm:grid-cols-3">
            {/* Query */}
            <div>
              <label
                style={{
                  display: 'block',
                  fontFamily: FONT_BODY,
                  fontSize: 12,
                  fontWeight: 500,
                  color: INK_SOFT,
                  marginBottom: 6,
                }}
              >
                Search query
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runComparison()}
                placeholder="Enter search query..."
                className="w-full rounded-lg"
                style={{
                  padding: '8px 12px',
                  fontFamily: FONT_BODY,
                  fontSize: 13,
                  color: INK,
                  background: 'white',
                  border: INPUT_BORDER,
                  outline: 'none',
                }}
              />
            </div>

            {/* ef_search slider */}
            <div>
              <label
                style={{
                  display: 'block',
                  fontFamily: FONT_BODY,
                  fontSize: 12,
                  fontWeight: 500,
                  color: INK_SOFT,
                  marginBottom: 6,
                }}
              >
                ef_search:{' '}
                <span style={{ fontFamily: FONT_MONO, color: INK }}>{efSearch}</span>
              </label>
              <input
                type="range"
                min="10"
                max="200"
                step="10"
                value={efSearch}
                onChange={(e) => setEfSearch(parseInt(e.target.value))}
                className="w-full"
                style={{ accentColor: ACCENT, marginTop: 4 }}
              />
              <div
                className="flex justify-between"
                style={{
                  fontFamily: FONT_BODY,
                  fontSize: 10,
                  color: INK_QUIET,
                  marginTop: 2,
                }}
              >
                <span>Fast (10)</span>
                <span>Accurate (200)</span>
              </div>
            </div>

            {/* Limit */}
            <div>
              <label
                style={{
                  display: 'block',
                  fontFamily: FONT_BODY,
                  fontSize: 12,
                  fontWeight: 500,
                  color: INK_SOFT,
                  marginBottom: 6,
                }}
              >
                Result limit
              </label>
              <input
                type="number"
                min={1}
                max={100}
                value={limit}
                onChange={(e) => setLimit(parseInt(e.target.value) || 10)}
                className="w-full rounded-lg"
                style={{
                  padding: '8px 12px',
                  fontFamily: FONT_MONO,
                  fontSize: 13,
                  color: INK,
                  background: 'white',
                  border: INPUT_BORDER,
                  outline: 'none',
                }}
              />
            </div>
          </div>

          {/* Run button */}
          <button
            onClick={runComparison}
            disabled={loading || !query.trim()}
            className="w-full flex items-center justify-center gap-2 rounded-lg"
            style={{
              padding: '10px 20px',
              fontFamily: FONT_BODY,
              fontSize: 13,
              fontWeight: 600,
              color: CREAM,
              background: INK,
              border: 'none',
              cursor: loading ? 'wait' : 'pointer',
              opacity: loading || !query.trim() ? 0.5 : 1,
              marginBottom: 20,
            }}
          >
            {loading ? (
              <>
                <Spinner /> Running 4 test runs with cache clearing...
              </>
            ) : (
              'Run comparison'
            )}
          </button>

          {/* Error */}
          {error && (
            <p
              className="rounded-lg"
              style={{
                padding: '10px 14px',
                fontFamily: FONT_BODY,
                fontSize: 13,
                color: ACCENT,
                background: 'rgba(196, 69, 54, 0.06)',
                border: '1px solid rgba(196, 69, 54, 0.15)',
                marginBottom: 16,
              }}
            >
              {error}
            </p>
          )}

          {/* Results */}
          {results && (
            <div className="flex flex-col gap-4">
              {/* Side-by-side cards */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <ResultCard title="HNSW Index" tint={TINT_A}>
                  <MetricRow
                    label={`Median time (${results.hnsw.num_runs} runs)`}
                    value={`${results.hnsw.median_time_ms}ms`}
                    mono
                  />
                  <MetricRow label="Results returned" value={results.hnsw.result_count} />
                  <MetricRow label="ef_search" value={results.hnsw.ef_search} mono />
                  {results.hnsw.all_times_ms && (
                    <p
                      style={{
                        fontFamily: FONT_MONO,
                        fontSize: 11,
                        color: INK_QUIET,
                        marginTop: 8,
                      }}
                    >
                      All runs: {results.hnsw.all_times_ms.join('ms, ')}ms
                    </p>
                  )}
                </ResultCard>

                <ResultCard title="Sequential Scan" tint={TINT_B}>
                  <MetricRow
                    label={`Median time (${results.sequential.num_runs} runs)`}
                    value={`${results.sequential.median_time_ms}ms`}
                    mono
                  />
                  <MetricRow
                    label="Results returned"
                    value={results.sequential.result_count}
                  />
                  <MetricRow label="Recall" value="100% (exact)" />
                  {results.sequential.all_times_ms && (
                    <p
                      style={{
                        fontFamily: FONT_MONO,
                        fontSize: 11,
                        color: INK_QUIET,
                        marginTop: 8,
                      }}
                    >
                      All runs: {results.sequential.all_times_ms.join('ms, ')}ms
                    </p>
                  )}
                </ResultCard>
              </div>

              {/* Comparison summary row */}
              <div
                className="grid grid-cols-2 gap-3 sm:grid-cols-4"
                style={{ marginTop: 4 }}
              >
                {[
                  {
                    label: 'Speedup',
                    value: `${results.comparison.speedup_factor}x`,
                  },
                  {
                    label: 'Time saved',
                    value: `${results.comparison.time_saved_ms}ms`,
                  },
                  {
                    label: 'Efficiency',
                    value: `${results.comparison.time_saved_pct}%`,
                  },
                  { label: 'Recall', value: `${results.comparison.recall_pct}%` },
                ].map((m) => (
                  <div
                    key={m.label}
                    className="rounded-lg text-center"
                    style={{
                      padding: '12px 8px',
                      background: TINT_C,
                      border: CARD_BORDER,
                    }}
                  >
                    <div
                      style={{
                        fontFamily: FONT_BODY,
                        fontSize: 11,
                        color: INK_QUIET,
                        marginBottom: 4,
                      }}
                    >
                      {m.label}
                    </div>
                    <div
                      style={{
                        fontFamily: FONT_MONO,
                        fontSize: 18,
                        fontWeight: 700,
                        color: INK,
                      }}
                    >
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Educational note — condensed */}
              {results.comparison.dataset_context.show_small_dataset_warning && (
                <p
                  style={{
                    fontFamily: FONT_BODY,
                    fontSize: 12.5,
                    fontStyle: 'italic',
                    lineHeight: 1.65,
                    color: INK_SOFT,
                    marginTop: 4,
                  }}
                >
                  This demo dataset has ~{results.comparison.dataset_context.rows.toLocaleString()}{' '}
                  rows ({results.comparison.dataset_context.size_category}).{' '}
                  {results.comparison.dataset_context.size_note}{' '}
                  PostgreSQL caches small datasets after the first query, so timing
                  varies between cold runs (200-400 ms) and warm runs (10-60 ms) --
                  this is expected buffer-pool behavior. The ef_search parameter's
                  impact becomes pronounced above 100 K rows where the working set
                  exceeds shared buffers.
                </p>
              )}
            </div>
          )}

          {/* Empty state */}
          {!results && !loading && !error && (
            <p
              style={{
                fontFamily: FONT_BODY,
                fontSize: 13,
                color: INK_QUIET,
                textAlign: 'center',
                padding: '24px 0 8px',
              }}
            >
              Enter a query and run the comparison to see HNSW vs sequential scan
              performance.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 2. QuantizationSection
// ---------------------------------------------------------------------------

export function QuantizationSection() {
  const [open, setOpen] = useState(false)
  const [quantData, setQuantData] = useState<QuantData | null>(null)
  const [quantLoading, setQuantLoading] = useState(false)
  const [fetched, setFetched] = useState(false)

  // Benchmark state
  const [qbQuery, setQbQuery] = useState('luxury watch')
  const [qbResults, setQbResults] = useState<QuantBenchResults | null>(null)
  const [qbLoading, setQbLoading] = useState(false)

  const fetchQuantization = async () => {
    setQuantLoading(true)
    try {
      const res = await fetch('/api/performance/quantization')
      if (res.ok) setQuantData(await res.json())
    } catch {
      /* quiet */
    } finally {
      setQuantLoading(false)
      setFetched(true)
    }
  }

  const runQuantBenchmark = async () => {
    if (!qbQuery.trim()) return
    setQbLoading(true)
    try {
      const res = await fetch('/api/performance/quantization-benchmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: qbQuery, limit: 10 }),
      })
      if (res.ok) setQbResults(await res.json())
    } catch {
      /* quiet */
    } finally {
      setQbLoading(false)
    }
  }

  // Fetch on first open
  useEffect(() => {
    if (open && !fetched) fetchQuantization()
  }, [open, fetched])

  return (
    <div
      className="rounded-xl"
      style={{
        background: 'white',
        border: CARD_BORDER,
        overflow: 'hidden',
      }}
    >
      <AccordionHeader
        eyebrow="v."
        title="Quantization strategies."
        open={open}
        onToggle={() => setOpen(!open)}
      />

      {open && (
        <div style={{ padding: '0 24px 24px' }}>
          {quantLoading && (
            <div className="flex items-center justify-center gap-2" style={{ padding: '40px 0' }}>
              <Spinner />
              <span
                style={{
                  fontFamily: FONT_BODY,
                  fontSize: 13,
                  color: INK_QUIET,
                }}
              >
                Loading quantization data...
              </span>
            </div>
          )}

          {quantData && (
            <div className="flex flex-col gap-5">
              {/* Three strategy cards */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {/* Full Precision */}
                <ResultCard title="Full Precision" tint={TINT_A}>
                  <div
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 22,
                      fontWeight: 700,
                      color: INK,
                      marginBottom: 4,
                    }}
                  >
                    {quantData.full_precision.index_size}
                  </div>
                  <p
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 11,
                      color: INK_QUIET,
                    }}
                  >
                    {quantData.full_precision.type} ·{' '}
                    {quantData.full_precision.bytes_per_vector} B/vec
                  </p>
                </ResultCard>

                {/* Scalar Quantization */}
                <ResultCard title="Scalar Quantization" tint={TINT_C}>
                  <div
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 22,
                      fontWeight: 700,
                      color: INK,
                      marginBottom: 4,
                    }}
                  >
                    {quantData.scalar_quantization.estimated_index_size}
                  </div>
                  <p
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 11,
                      color: INK_QUIET,
                    }}
                  >
                    {quantData.scalar_quantization.type} ·{' '}
                    {quantData.scalar_quantization.bytes_per_vector} B/vec
                  </p>
                  <p
                    style={{
                      fontFamily: FONT_BODY,
                      fontSize: 12,
                      fontWeight: 600,
                      color: INK_SOFT,
                      marginTop: 8,
                    }}
                  >
                    {quantData.scalar_quantization.memory_reduction} smaller
                  </p>
                </ResultCard>

                {/* Binary Quantization */}
                <ResultCard title="Binary Quantization" tint={TINT_B}>
                  <div
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 22,
                      fontWeight: 700,
                      color: INK,
                      marginBottom: 4,
                    }}
                  >
                    {quantData.binary_quantization.estimated_index_size}
                  </div>
                  <p
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 11,
                      color: INK_QUIET,
                    }}
                  >
                    {quantData.binary_quantization.type} ·{' '}
                    {quantData.binary_quantization.bytes_per_vector} B/vec
                  </p>
                  <p
                    style={{
                      fontFamily: FONT_BODY,
                      fontSize: 12,
                      fontWeight: 600,
                      color: INK_SOFT,
                      marginTop: 8,
                    }}
                  >
                    {quantData.binary_quantization.memory_reduction} smaller
                  </p>
                </ResultCard>
              </div>

              {/* Memory comparison bar chart */}
              <div>
                <h4
                  style={{
                    fontFamily: FONT_BODY,
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                    color: INK_QUIET,
                    marginBottom: 12,
                  }}
                >
                  Memory comparison
                </h4>
                <div className="flex flex-col gap-2.5">
                  {[
                    {
                      label: 'float32',
                      bytes: quantData.full_precision.index_bytes,
                      color: INK,
                    },
                    {
                      label: 'int8 (SQ)',
                      bytes: quantData.scalar_quantization.estimated_index_bytes,
                      color: INK_SOFT,
                    },
                    {
                      label: '1-bit (BQ)',
                      bytes: quantData.binary_quantization.estimated_index_bytes,
                      color: INK_QUIET,
                    },
                  ].map((item) => {
                    const pct =
                      (item.bytes / quantData!.full_precision.index_bytes) * 100
                    return (
                      <div key={item.label} className="flex items-center gap-3">
                        <span
                          className="w-16 text-right"
                          style={{
                            fontFamily: FONT_MONO,
                            fontSize: 11,
                            color: INK_QUIET,
                            flexShrink: 0,
                          }}
                        >
                          {item.label}
                        </span>
                        <div
                          className="flex-1 rounded"
                          style={{
                            height: 16,
                            background: 'rgba(45, 24, 16, 0.04)',
                          }}
                        >
                          <div
                            className="rounded"
                            style={{
                              height: '100%',
                              width: `${Math.max(pct, 1.5)}%`,
                              background: item.color,
                              opacity: 0.35,
                              transition: 'width 400ms ease',
                            }}
                          />
                        </div>
                        <span
                          className="w-10 text-right"
                          style={{
                            fontFamily: FONT_MONO,
                            fontSize: 11,
                            color: INK_QUIET,
                            flexShrink: 0,
                          }}
                        >
                          {pct.toFixed(0)}%
                        </span>
                      </div>
                    )
                  })}
                </div>
                <p
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 10,
                    color: INK_QUIET,
                    marginTop: 8,
                  }}
                >
                  {quantData.row_count.toLocaleString()} vectors ·{' '}
                  {quantData.dimensions} dimensions
                </p>
              </div>

              {/* SQL example */}
              <MonoCodeBlock label="CREATE INDEX (Scalar Quantization)">
                {quantData.sql_examples.sq}
              </MonoCodeBlock>
              <p
                style={{
                  fontFamily: FONT_BODY,
                  fontSize: 11,
                  color: INK_QUIET,
                  marginTop: -8,
                }}
              >
                {quantData.note}
              </p>

              {/* Live benchmark */}
              <div
                className="rounded-lg"
                style={{
                  padding: '18px 20px',
                  border: CARD_BORDER,
                  background: TINT_A,
                }}
              >
                <h4
                  style={{
                    fontFamily: FONT_BODY,
                    fontSize: 13,
                    fontWeight: 600,
                    color: INK,
                    marginBottom: 4,
                  }}
                >
                  Live benchmark
                </h4>
                <p
                  style={{
                    fontFamily: FONT_BODY,
                    fontSize: 11,
                    color: INK_QUIET,
                    marginBottom: 14,
                  }}
                >
                  Expression casts at query time -- no DDL required.
                </p>

                <div className="flex gap-3 mb-4">
                  <input
                    type="text"
                    value={qbQuery}
                    onChange={(e) => setQbQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && runQuantBenchmark()}
                    placeholder="Search query..."
                    className="flex-1 rounded-lg"
                    style={{
                      padding: '8px 12px',
                      fontFamily: FONT_BODY,
                      fontSize: 13,
                      color: INK,
                      background: 'white',
                      border: INPUT_BORDER,
                      outline: 'none',
                    }}
                  />
                  <button
                    onClick={runQuantBenchmark}
                    disabled={qbLoading || !qbQuery.trim()}
                    className="flex items-center gap-2 rounded-lg"
                    style={{
                      padding: '8px 18px',
                      fontFamily: FONT_BODY,
                      fontSize: 13,
                      fontWeight: 600,
                      color: INK,
                      background: 'transparent',
                      border: `1px solid ${INK}`,
                      cursor: qbLoading ? 'wait' : 'pointer',
                      opacity: qbLoading || !qbQuery.trim() ? 0.4 : 1,
                    }}
                  >
                    {qbLoading ? (
                      <>
                        <Spinner size={14} /> Benchmarking...
                      </>
                    ) : (
                      'Run benchmark'
                    )}
                  </button>
                </div>

                {/* Benchmark results */}
                {qbResults && (
                  <div className="flex flex-col gap-4">
                    {/* Three result cards */}
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      {qbResults.float32 && (
                        <ResultCard title="float32 (baseline)" tint={TINT_A}>
                          <div
                            style={{
                              fontFamily: FONT_MONO,
                              fontSize: 20,
                              fontWeight: 700,
                              color: INK,
                            }}
                          >
                            {qbResults.float32.execution_time_ms}ms
                          </div>
                          <p
                            style={{
                              fontFamily: FONT_BODY,
                              fontSize: 11,
                              color: INK_QUIET,
                              marginTop: 4,
                            }}
                          >
                            {qbResults.float32.result_count} results · 100% recall
                          </p>
                        </ResultCard>
                      )}

                      <ResultCard title="halfvec (SQ)" tint={TINT_C}>
                        {qbResults.halfvec_available &&
                        qbResults.halfvec &&
                        !qbResults.halfvec.error ? (
                          <>
                            <div
                              style={{
                                fontFamily: FONT_MONO,
                                fontSize: 20,
                                fontWeight: 700,
                                color: INK,
                              }}
                            >
                              {qbResults.halfvec.execution_time_ms}ms
                            </div>
                            <p
                              style={{
                                fontFamily: FONT_BODY,
                                fontSize: 11,
                                color: INK_QUIET,
                                marginTop: 4,
                              }}
                            >
                              {qbResults.halfvec.result_count} results ·{' '}
                              {qbResults.halfvec.recall_vs_float32}% recall
                            </p>
                          </>
                        ) : (
                          <p style={{ fontFamily: FONT_BODY, fontSize: 12, color: INK_QUIET }}>
                            {qbResults.halfvec?.error
                              ? 'Cast not supported'
                              : 'Unavailable'}
                          </p>
                        )}
                      </ResultCard>

                      <ResultCard title="binary (BQ)" tint={TINT_B}>
                        {qbResults.binary_available &&
                        qbResults.binary &&
                        !qbResults.binary.error ? (
                          <>
                            <div
                              style={{
                                fontFamily: FONT_MONO,
                                fontSize: 20,
                                fontWeight: 700,
                                color: INK,
                              }}
                            >
                              {qbResults.binary.execution_time_ms}ms
                            </div>
                            <p
                              style={{
                                fontFamily: FONT_BODY,
                                fontSize: 11,
                                color: INK_QUIET,
                                marginTop: 4,
                              }}
                            >
                              {qbResults.binary.result_count} results ·{' '}
                              {qbResults.binary.recall_vs_float32}% recall
                            </p>
                          </>
                        ) : (
                          <p style={{ fontFamily: FONT_BODY, fontSize: 12, color: INK_QUIET }}>
                            {qbResults.binary?.error
                              ? 'Cast not supported'
                              : 'Unavailable'}
                          </p>
                        )}
                      </ResultCard>
                    </div>

                    {/* Timing bar chart */}
                    {qbResults.float32 && (() => {
                      const items = [
                        {
                          label: 'float32',
                          time: qbResults.float32!.execution_time_ms,
                          available: true,
                        },
                        {
                          label: 'halfvec',
                          time: qbResults.halfvec?.execution_time_ms ?? 0,
                          available:
                            qbResults.halfvec_available &&
                            !qbResults.halfvec?.error,
                        },
                        {
                          label: 'binary',
                          time: qbResults.binary?.execution_time_ms ?? 0,
                          available:
                            qbResults.binary_available &&
                            !qbResults.binary?.error,
                        },
                      ].filter((i) => i.available && i.time > 0)

                      const maxTime = Math.max(...items.map((i) => i.time))

                      return (
                        <div>
                          <h5
                            style={{
                              fontFamily: FONT_BODY,
                              fontSize: 11,
                              fontWeight: 600,
                              letterSpacing: '0.06em',
                              textTransform: 'uppercase',
                              color: INK_QUIET,
                              marginBottom: 10,
                            }}
                          >
                            Execution time comparison
                          </h5>
                          <div className="flex flex-col gap-2">
                            {items.map((item) => {
                              const pct =
                                maxTime > 0
                                  ? (item.time / maxTime) * 100
                                  : 0
                              return (
                                <div
                                  key={item.label}
                                  className="flex items-center gap-3"
                                >
                                  <span
                                    className="w-14 text-right"
                                    style={{
                                      fontFamily: FONT_MONO,
                                      fontSize: 11,
                                      color: INK_QUIET,
                                      flexShrink: 0,
                                    }}
                                  >
                                    {item.label}
                                  </span>
                                  <div
                                    className="flex-1 rounded"
                                    style={{
                                      height: 14,
                                      background: 'rgba(45, 24, 16, 0.04)',
                                    }}
                                  >
                                    <div
                                      className="rounded"
                                      style={{
                                        height: '100%',
                                        width: `${Math.max(pct, 2)}%`,
                                        background: INK,
                                        opacity: 0.25,
                                        transition: 'width 400ms ease',
                                      }}
                                    />
                                  </div>
                                  <span
                                    className="w-14 text-right"
                                    style={{
                                      fontFamily: FONT_MONO,
                                      fontSize: 11,
                                      color: INK_SOFT,
                                      flexShrink: 0,
                                    }}
                                  >
                                    {item.time}ms
                                  </span>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })()}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Data not loaded and not loading */}
          {!quantData && !quantLoading && fetched && (
            <p
              style={{
                fontFamily: FONT_BODY,
                fontSize: 13,
                color: INK_QUIET,
                textAlign: 'center',
                padding: '24px 0 8px',
              }}
            >
              Failed to load quantization data. Try closing and reopening.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 3. IterativeScanSection
// ---------------------------------------------------------------------------

export function IterativeScanSection() {
  const [open, setOpen] = useState(false)
  const [categories, setCategories] = useState<string[]>([])
  const [category, setCategory] = useState('')
  const [query, setQuery] = useState('wireless headphones')
  const [efSearch, setEfSearch] = useState(40)
  const [results, setResults] = useState<IterativeScanResults | null>(null)
  const [loading, setLoading] = useState(false)
  const [categoriesFetched, setCategoriesFetched] = useState(false)

  const fetchCategories = async () => {
    try {
      const res = await fetch('/api/performance/categories')
      if (res.ok) {
        const data = await res.json()
        const cats: string[] = data.categories || []
        setCategories(cats)
        if (cats.length > 0 && !category) setCategory(cats[0])
      }
    } catch {
      /* quiet */
    } finally {
      setCategoriesFetched(true)
    }
  }

  // Fetch categories on first open
  useEffect(() => {
    if (open && !categoriesFetched) fetchCategories()
  }, [open, categoriesFetched])

  const runComparison = async () => {
    if (!query.trim() || !category) return
    setLoading(true)
    try {
      const res = await fetch('/api/performance/iterative-scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          category,
          ef_search: efSearch,
          limit: 10,
        }),
      })
      if (res.ok) setResults(await res.json())
    } catch {
      /* quiet */
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="rounded-xl"
      style={{
        background: 'white',
        border: CARD_BORDER,
        overflow: 'hidden',
      }}
    >
      <AccordionHeader
        eyebrow="vi."
        title="Iterative scan — the overfiltering fix."
        open={open}
        onToggle={() => setOpen(!open)}
      />

      {open && (
        <div style={{ padding: '0 24px 24px' }}>
          {/* Controls */}
          <div className="grid grid-cols-1 gap-4 mb-5 sm:grid-cols-3">
            {/* Category dropdown */}
            <div>
              <label
                style={{
                  display: 'block',
                  fontFamily: FONT_BODY,
                  fontSize: 12,
                  fontWeight: 500,
                  color: INK_SOFT,
                  marginBottom: 6,
                }}
              >
                Category filter
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-lg"
                style={{
                  padding: '8px 12px',
                  fontFamily: FONT_BODY,
                  fontSize: 13,
                  color: INK,
                  background: 'white',
                  border: INPUT_BORDER,
                  outline: 'none',
                }}
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>

            {/* Query */}
            <div>
              <label
                style={{
                  display: 'block',
                  fontFamily: FONT_BODY,
                  fontSize: 12,
                  fontWeight: 500,
                  color: INK_SOFT,
                  marginBottom: 6,
                }}
              >
                Search query
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && runComparison()}
                placeholder="Search query..."
                className="w-full rounded-lg"
                style={{
                  padding: '8px 12px',
                  fontFamily: FONT_BODY,
                  fontSize: 13,
                  color: INK,
                  background: 'white',
                  border: INPUT_BORDER,
                  outline: 'none',
                }}
              />
            </div>

            {/* ef_search slider */}
            <div>
              <label
                style={{
                  display: 'block',
                  fontFamily: FONT_BODY,
                  fontSize: 12,
                  fontWeight: 500,
                  color: INK_SOFT,
                  marginBottom: 6,
                }}
              >
                ef_search:{' '}
                <span style={{ fontFamily: FONT_MONO, color: INK }}>{efSearch}</span>
              </label>
              <input
                type="range"
                min="10"
                max="200"
                step="10"
                value={efSearch}
                onChange={(e) => setEfSearch(parseInt(e.target.value))}
                className="w-full"
                style={{ accentColor: ACCENT, marginTop: 4 }}
              />
            </div>
          </div>

          {/* Run button */}
          <button
            onClick={runComparison}
            disabled={loading || !query.trim() || !category}
            className="w-full flex items-center justify-center gap-2 rounded-lg"
            style={{
              padding: '10px 20px',
              fontFamily: FONT_BODY,
              fontSize: 13,
              fontWeight: 600,
              color: CREAM,
              background: INK,
              border: 'none',
              cursor: loading ? 'wait' : 'pointer',
              opacity: loading || !query.trim() || !category ? 0.5 : 1,
              marginBottom: 20,
            }}
          >
            {loading ? (
              <>
                <Spinner /> Running comparison...
              </>
            ) : (
              'Run comparison'
            )}
          </button>

          {/* Results */}
          {results && (
            <div className="flex flex-col gap-4">
              {/* pgvector 0.8.0 warning */}
              {!results.pgvector_080_available && (
                <p
                  className="rounded-lg"
                  style={{
                    padding: '10px 14px',
                    fontFamily: FONT_BODY,
                    fontSize: 12,
                    color: INK_SOFT,
                    background: 'rgba(196, 69, 54, 0.05)',
                    border: '1px solid rgba(196, 69, 54, 0.12)',
                  }}
                >
                  pgvector 0.8.0 not detected -- iterative scan is unavailable.
                  Showing standard filtered results only.
                </p>
              )}

              {/* Result count headline */}
              {results.without_iterative_scan && results.with_iterative_scan && (
                <div
                  className="text-center rounded-lg"
                  style={{
                    padding: '18px 16px',
                    background: TINT_C,
                    border: CARD_BORDER,
                  }}
                >
                  <p
                    style={{
                      fontFamily: FONT_BODY,
                      fontSize: 11,
                      letterSpacing: '0.06em',
                      textTransform: 'uppercase',
                      color: INK_QUIET,
                      marginBottom: 6,
                    }}
                  >
                    Result count improvement
                  </p>
                  <div
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 28,
                      fontWeight: 700,
                      color: INK,
                    }}
                  >
                    {results.without_iterative_scan.result_count} {'  '}
                    <span style={{ color: INK_QUIET, fontSize: 20 }}>{'-->'}</span>
                    {'  '}
                    {results.with_iterative_scan.result_count}
                  </div>
                  <p
                    style={{
                      fontFamily: FONT_BODY,
                      fontSize: 11,
                      color: INK_QUIET,
                      marginTop: 6,
                    }}
                  >
                    Requested {results.limit} results · Category: &quot;
                    {results.category_filter}&quot;
                  </p>
                </div>
              )}

              {/* Side-by-side */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {/* Without */}
                <ResultCard title="Without iterative scan" tint={TINT_B}>
                  <p
                    style={{
                      fontFamily: FONT_BODY,
                      fontSize: 11,
                      color: INK_QUIET,
                      marginBottom: 12,
                      marginTop: -4,
                    }}
                  >
                    Standard HNSW -- fixed candidate set, then filter
                  </p>
                  {results.without_iterative_scan ? (
                    <>
                      <MetricRow
                        label="Results returned"
                        value={`${results.without_iterative_scan.result_count} / ${results.limit}`}
                        mono
                      />
                      <MetricRow
                        label="Execution time"
                        value={`${results.without_iterative_scan.execution_time_ms}ms`}
                        mono
                      />
                      {results.without_iterative_scan.result_count <
                        results.limit && (
                        <p
                          className="rounded"
                          style={{
                            padding: '6px 10px',
                            fontFamily: FONT_BODY,
                            fontSize: 11,
                            color: ACCENT,
                            background: 'rgba(196, 69, 54, 0.06)',
                            marginTop: 8,
                          }}
                        >
                          Overfiltering: only{' '}
                          {results.without_iterative_scan.result_count} of{' '}
                          {results.limit} returned
                        </p>
                      )}
                    </>
                  ) : (
                    <p
                      style={{
                        fontFamily: FONT_BODY,
                        fontSize: 12,
                        color: INK_QUIET,
                      }}
                    >
                      No data
                    </p>
                  )}
                </ResultCard>

                {/* With */}
                <ResultCard title="With iterative scan" tint={TINT_C}>
                  <p
                    style={{
                      fontFamily: FONT_BODY,
                      fontSize: 11,
                      color: INK_QUIET,
                      marginBottom: 12,
                      marginTop: -4,
                    }}
                  >
                    pgvector 0.8.0 -- continues traversal until LIMIT met
                  </p>
                  {results.with_iterative_scan ? (
                    <>
                      <MetricRow
                        label="Results returned"
                        value={`${results.with_iterative_scan.result_count} / ${results.limit}`}
                        mono
                      />
                      <MetricRow
                        label="Execution time"
                        value={`${results.with_iterative_scan.execution_time_ms}ms`}
                        mono
                      />
                      {results.with_iterative_scan.result_count >=
                        results.limit && (
                        <p
                          className="rounded"
                          style={{
                            padding: '6px 10px',
                            fontFamily: FONT_BODY,
                            fontSize: 11,
                            color: INK_SOFT,
                            background: 'rgba(45, 24, 16, 0.04)',
                            marginTop: 8,
                          }}
                        >
                          Full {results.limit} results returned
                        </p>
                      )}
                    </>
                  ) : (
                    <p
                      style={{
                        fontFamily: FONT_BODY,
                        fontSize: 12,
                        color: INK_QUIET,
                      }}
                    >
                      {results.pgvector_080_available === false
                        ? 'Requires pgvector 0.8.0+'
                        : 'No data'}
                    </p>
                  )}
                </ResultCard>
              </div>

              {/* SQL example */}
              <MonoCodeBlock label="Enable iterative scan">
                {`SET hnsw.iterative_scan = 'relaxed_order';
SET hnsw.max_scan_tuples = 20000;

-- Then run your filtered query as normal
SELECT * FROM products
WHERE category = 'Electronics'
ORDER BY embedding <=> query_vector
LIMIT 10;`}
              </MonoCodeBlock>
            </div>
          )}

          {/* Empty state */}
          {!results && !loading && (
            <p
              style={{
                fontFamily: FONT_BODY,
                fontSize: 13,
                color: INK_QUIET,
                textAlign: 'center',
                padding: '24px 0 8px',
              }}
            >
              Select a category and run the comparison to see the overfiltering
              fix.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
