/**
 * Search — the hybrid retrieval pipeline, made visible.
 *
 * Level-400 rooms run Anna's hybrid-search-and-rerank journey live but
 * never see the mechanism. This surface fixes that: type a query, and the
 * GET /api/atelier/search/explain endpoint walks the real pipeline a
 * single query takes —
 *
 *     EMBED → VECTOR → LEXICAL → FUSION → RERANK
 *
 * — returning each stage's real artifact: the literal branch SQL for
 * VECTOR/LEXICAL (byte-identical to what the live path runs), the
 * per-branch ranks the FUSION stage merges, and the position delta the
 * RERANK stage produces. The reordering between FUSION and RERANK is the
 * teaching moment, and it is live data — nothing here is fabricated.
 *
 * This is the *mechanism* view. Performance (EVALUATE · Performance) keeps
 * the *outcome* view — which products win, how fast, at what cost. A
 * code-read walkthrough at the bottom ties the panels back to the real
 * files so a participant can read the layering for themselves.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { EditorialTitle, ExpCard } from '../../components';
import { useSearchExplain } from '../../hooks/useSearchExplain';
import type { SearchStage, SearchTagClass } from '../../types';

const DARK_CODE_BLOCK: React.CSSProperties = {
  fontFamily: 'var(--dl-font-mono)',
  fontSize: '12.5px',
  lineHeight: 1.6,
  background: 'var(--dl-ink)',
  color: 'var(--dl-accent-soft)',
  borderRadius: 'var(--dl-r-lg)',
  border: '1px solid color-mix(in srgb, var(--dl-accent-soft) 18%, transparent)',
  padding: '14px 16px',
  overflow: 'auto',
  margin: 0,
  whiteSpace: 'pre-wrap',
};

const DEFAULT_QUERY = 'something beautiful for a slow morning, under $100';

const EXAMPLES: Array<{ label: string; query: string }> = [
  { label: 'Anna · morning ritual', query: 'a thoughtful gift for someone who loves morning rituals' },
  { label: 'Anna · under $100', query: 'something beautiful under $100' },
  { label: 'Marco · linen for Goa', query: 'breathable linen shirts for ten days in Goa' },
  { label: 'Lexical anchor', query: 'cashmere cardigan' },
];

/* Map the backend tagClass to the Atelier accent palette. */
function tagColor(tagClass: SearchTagClass): string {
  switch (tagClass) {
    case 'amber':
      return 'var(--at-red-1)';
    case 'green':
      return 'var(--at-green-1)';
    case 'cyan':
    default:
      return 'var(--at-ink-1)';
  }
}

/* -----------------------------------------------------------------------
 * One pipeline stage rendered as a panel card
 * ----------------------------------------------------------------------- */

const StagePanel: React.FC<{ stage: SearchStage; index: number }> = ({
  stage,
  index,
}) => {
  const accent = tagColor(stage.tagClass);
  return (
    <ExpCard>
      {/* Head: numbered tag + title on the left, optional latency right. */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: '16px',
          marginBottom: '10px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: accent,
              fontWeight: 600,
            }}
          >
            {index + 1} · {stage.tag}
          </span>
          <h3
            style={{
              fontFamily: 'var(--at-serif)',
              fontWeight: 400,
              fontSize: '22px',
              letterSpacing: '-0.012em',
              color: 'var(--at-ink-1)',
              margin: 0,
            }}
          >
            {stage.title}
          </h3>
        </div>
        {typeof stage.durationMs === 'number' && stage.durationMs > 0 && (
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              color: 'var(--at-red-1)',
              flexShrink: 0,
            }}
          >
            {stage.durationMs}ms
          </span>
        )}
      </div>

      {/* SQL block (VECTOR / LEXICAL only). */}
      {stage.sql && (
        <pre style={{ ...DARK_CODE_BLOCK, marginBottom: '14px' }}>
          <span style={{ color: '#8a8270' }}>
            {`-- the literal ${stage.stage} branch SQL (what actually ran)`}
          </span>
          {'\n'}
          {stage.sql}
        </pre>
      )}

      {/* Rows table. */}
      {stage.rows.length > 0 ? (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
            }}
          >
            <thead>
              <tr>
                {stage.columns.map((col) => (
                  <th
                    key={col}
                    style={{
                      textAlign: 'left',
                      padding: '6px 12px 6px 0',
                      borderBottom: '1px solid var(--at-rule-2)',
                      color: 'var(--at-ink-2)',
                      fontWeight: 600,
                      letterSpacing: '0.06em',
                      textTransform: 'uppercase',
                      fontSize: '10.5px',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stage.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      style={{
                        padding: '6px 12px 6px 0',
                        borderBottom: '1px solid var(--at-rule-1)',
                        color: ci === 0 ? 'var(--at-ink-1)' : 'var(--at-ink-2)',
                        fontWeight: ci === 0 ? 500 : 400,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            color: 'var(--at-ink-4)',
            fontStyle: 'italic',
            margin: '4px 0',
          }}
        >
          No rows from this stage for this query.
        </p>
      )}

      {/* Teaching note. */}
      {stage.meta && (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.6,
            color: 'var(--at-ink-2)',
            margin: '12px 0 0',
          }}
        >
          {stage.meta}
        </p>
      )}
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Code-read walkthrough — points at the real files behind the panels
 * ----------------------------------------------------------------------- */

const CODE_READ: Array<{ step: string; path: string; body: string }> = [
  {
    step: 'A search tool is a thin envelope',
    path: 'services/agent_tools.py',
    body: 'find_pieces is the same shape you wired for floor_check: guard the db service, lazily build BusinessLogic, call the method, json.dumps the result. The retrieval complexity lives below the tool, not in it.',
  },
  {
    step: 'The baseline: pure pgvector',
    path: 'services/vector_search.py — VectorSearch.vector_search (CHALLENGE 1)',
    body: 'Marco’s path. One CTE binds the query vector once; the <=> operator is HNSW cosine distance; similarity = 1 − distance. SET LOCAL hnsw.ef_search tunes recall per query; iterative_scan protects recall when WHERE clauses are strict.',
  },
  {
    step: 'The hybrid branches run in parallel',
    path: 'services/hybrid_search.py — _vector_search ∥ _bm25_search',
    body: 'asyncio.gather fires the vector branch and the Postgres full-text branch at once. FTS uses to_tsquery(‘english’, …) with OR-joined stems over the description_tsv GIN index, ranked by ts_rank_cd (cover density). The SQL you see in the VECTOR and LEXICAL panels above is these two strings, verbatim.',
  },
  {
    step: 'RRF fuses two rankings without shared scales',
    path: 'services/hybrid_search.py — _rrf_merge (k=60)',
    body: 'score(d) = Σ 1 / (k + rank) over each branch d appears in. It never compares a cosine similarity to a ts_rank_cd directly — only ranks — so the two scales never need to be reconciled. A row in both branches outscores a row in one. That’s the FUSION panel.',
  },
  {
    step: 'Rerank reorders the survivors',
    path: 'services/rerank.py — Cohere Rerank v3.5',
    body: 'The fused pool goes to Cohere Rerank v3.5, which reads the query + each candidate and returns calibrated relevance scores. The RERANK panel’s rrf_pos → reranked_pos column is the movement those scores buy. On a Bedrock outage the service returns [] and the caller falls back to RRF order — the documented degrade.',
  },
];

const CodeReadCard: React.FC = () => (
  <ExpCard>
    <span
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: 'var(--at-ink-2)',
        fontWeight: 600,
      }}
    >
      Read the code
    </span>
    <h3
      style={{
        fontFamily: 'var(--at-serif)',
        fontWeight: 400,
        fontSize: '24px',
        letterSpacing: '-0.012em',
        color: 'var(--at-ink-1)',
        margin: '6px 0 8px',
      }}
    >
      Five files, top to bottom.
    </h3>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '15px',
        lineHeight: 1.6,
        color: 'var(--at-ink-2)',
        margin: '0 0 22px',
        maxWidth: '680px',
      }}
    >
      The panels above are live output. These are the files that produced
      them, in the order a query flows through. Open them in the Code Editor
      alongside this surface — the SQL you read here is the SQL that ran.
    </p>

    <ol
      style={{
        listStyle: 'none',
        counterReset: 'cr',
        margin: 0,
        padding: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      {CODE_READ.map((item, i) => (
        <li
          key={item.step}
          style={{
            display: 'grid',
            gridTemplateColumns: '28px 1fr',
            gap: '14px',
            alignItems: 'start',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-serif)',
              fontSize: '20px',
              color: 'var(--at-red-1)',
              lineHeight: 1.2,
            }}
          >
            {i + 1}.
          </span>
          <div>
            <div
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '16px',
                fontWeight: 600,
                color: 'var(--at-ink-1)',
                marginBottom: '2px',
              }}
            >
              {item.step}
            </div>
            <code
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12.5px',
                color: 'var(--at-red-1)',
                background: 'var(--at-cream-2)',
                padding: '2px 7px',
                borderRadius: 4,
                display: 'inline-block',
                marginBottom: '6px',
              }}
            >
              {item.path}
            </code>
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '15px',
                lineHeight: 1.6,
                color: 'var(--at-ink-2)',
                margin: 0,
              }}
            >
              {item.body}
            </p>
          </div>
        </li>
      ))}
    </ol>

    <div
      style={{
        marginTop: '22px',
        paddingTop: '16px',
        borderTop: '1px solid var(--at-card-border)',
      }}
    >
      <Link
        to="/atelier/performance"
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--at-red-1)',
          textDecoration: 'none',
          fontWeight: 500,
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        See the outcome view · Performance
        <span aria-hidden="true" style={{ fontFamily: 'var(--at-serif)' }}>
          →
        </span>
      </Link>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Search: React.FC = () => {
  const { stages, params, query, loading, error, durationMs, explain } =
    useSearchExplain();
  const [input, setInput] = useState(DEFAULT_QUERY);
  // Tracks whether the participant has run a query themselves. We auto-fire
  // the default query on mount so the surface is never empty, but if that
  // auto-run fails (e.g. the backend is still warming up at page-open) we
  // show a calm "press Run on Aurora" prompt rather than a loud red banner
  // for something the participant did not trigger.
  const [hasRunManually, setHasRunManually] = useState(false);

  // Run the default query once on mount so the surface is never empty.
  useEffect(() => {
    explain(DEFAULT_QUERY);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (input.trim()) {
        setHasRunManually(true);
        explain(input.trim());
      }
    },
    [input, explain],
  );

  const runExample = useCallback(
    (q: string) => {
      setHasRunManually(true);
      setInput(q);
      explain(q);
    },
    [explain],
  );

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Search · embed → vector ∥ lexical → RRF → rerank"
        title="How one query becomes a ranking."
        summary="Anna's hybrid-search-and-rerank path runs live but is usually invisible. Type a query and watch the real pipeline: a Cohere Embed v4 vector, a pgvector HNSW cosine branch and a Postgres full-text branch running in parallel, Reciprocal Rank Fusion merging the two, and Cohere Rerank v3.5 reordering the survivors. The SQL is the SQL that ran; the reordering is live. This is the mechanism view – Performance keeps the outcome view."
      />

      {/* Query form + examples */}
      <form onSubmit={handleSubmit}>
        <div
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: '8px',
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            marginBottom: '12px',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: 'var(--at-red-1)',
              fontWeight: 500,
              flexShrink: 0,
            }}
          >
            Query
          </span>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe what you're shopping for..."
            aria-label="Search explain query"
            style={{
              flex: 1,
              fontFamily: 'var(--at-sans)',
              fontSize: '17px',
              color: 'var(--at-ink-1)',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              padding: 0,
            }}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              fontWeight: 500,
              color: 'var(--at-cream-1)',
              backgroundColor: loading ? 'var(--at-ink-4)' : 'var(--at-ink-1)',
              border: 'none',
              borderRadius: '6px',
              padding: '7px 14px',
              cursor: loading ? 'wait' : 'pointer',
              flexShrink: 0,
            }}
          >
            {loading ? 'Running…' : 'Run on Aurora'}
          </button>
        </div>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            marginBottom: '20px',
          }}
        >
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              disabled={loading}
              onClick={() => runExample(ex.query)}
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                padding: '5px 12px',
                borderRadius: '999px',
                border: '1px solid var(--at-rule-2)',
                background: 'var(--at-cream-2)',
                color: 'var(--at-ink-2)',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {ex.label}
            </button>
          ))}
        </div>
      </form>

      {/* Run summary line */}
      {!error && (query || params) && (
        <p
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-ink-4)',
            margin: '0 0 18px',
          }}
        >
          {query && (
            <>
              query <span style={{ color: 'var(--at-ink-1)' }}>“{query}”</span>
            </>
          )}
          {durationMs > 0 && (
            <>
              {' '}
              · <span style={{ color: 'var(--at-red-1)' }}>{durationMs}ms</span>{' '}
              round-trip
            </>
          )}
          {params && (
            <>
              {' '}
              · k_vector={params.k_vector} · k_bm25={params.k_bm25} · rrf_k=
              {params.rrf_k} · top_n={params.top_n}
            </>
          )}
        </p>
      )}

      {/* Error state — honest, no fabricated ranking */}
      {error && hasRunManually && (
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-red-1)',
            padding: '12px 14px',
            background: 'var(--at-red-soft)',
            borderRadius: '6px',
            marginBottom: '20px',
            lineHeight: 1.55,
          }}
        >
          Live search-explain endpoint unavailable ({error}). This surface
          shows real per-stage SQL and live rankings only — it does not
          fabricate a ranking offline. Start the backend and run again.
        </div>
      )}

      {error && !hasRunManually && !loading && (
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-2)',
            padding: '12px 14px',
            background: 'var(--at-cream-elev)',
            border: '1px solid var(--at-rule-1)',
            borderRadius: '6px',
            marginBottom: '20px',
            lineHeight: 1.55,
          }}
        >
          Edit the query and press <strong>Run on Aurora</strong> to trace the
          live pipeline. (The surface runs real per-stage SQL against the
          catalog, so it waits for your run rather than fabricating a ranking.)
        </div>
      )}

      {/* Stage panels */}
      {!error && stages.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            marginBottom: '32px',
          }}
        >
          {stages.map((stage, i) => (
            <StagePanel key={stage.stage} stage={stage} index={i} />
          ))}
        </div>
      )}

      {/* Code-read walkthrough */}
      <CodeReadCard />
    </div>
  );
};

export default Search;
