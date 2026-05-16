/**
 * Tools — Registered tool functions surface (fixture-backed).
 *
 * WorkshopProgressStrip: one segment per tool; shipped vs exercise from
 * build state (`/api/atelier/build-state`) with live overlay when
 * `floor_check` is wired — matches Builder's Session Part I.
 *
 * Shipped tools: solid borders, sage status.
 * Exercise tools: dashed borders, burgundy status.
 * "Related" callout card linking to Agents and Architecture · Tool Registry.
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 16.3
 */

import React, { useState, useCallback, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  StatusDot,
  StatusPill,
  WorkshopProgressStrip,
} from '../../components';
import type { Segment } from '../../components/WorkshopProgressStrip';
import { useAtelierData } from '../../hooks/useAtelierData';
import { useBuildState } from '../../hooks/useBuildState';
import { useToolDiscovery } from '../../hooks/useToolDiscovery';
import type { Tool, ToolDiscoveryResult } from '../../types';
import {
  DISCOVERY_EXAMPLES,
  discoveryQueryForTool,
  filterTools,
  type ToolFilter,
} from './toolsDiscoveryUtils';

/* -----------------------------------------------------------------------
 * Build Segment[] from tool data for WorkshopProgressStrip
 * ----------------------------------------------------------------------- */

function buildSegments(tools: Tool[]): Segment[] {
  return tools.map((tool) => ({
    id: String(tool.numeral),
    label: tool.functionName,
    status: tool.status,
  }));
}

/* -----------------------------------------------------------------------
 * Discovery Demo Card
 * ----------------------------------------------------------------------- */

const DEFAULT_QUERY = 'find products matching customer preferences';

const FILTER_OPTIONS: Array<{ id: ToolFilter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'shipped', label: 'Shipped' },
  { id: 'exercise', label: 'Exercise' },
  { id: 'read', label: 'Read' },
  { id: 'write', label: 'Write' },
];

interface DiscoveryDemoCardProps {
  tools: Tool[];
  highlightedToolName: string | null;
  onSelectTool: (functionName: string) => void;
  runRequest?: { query: string; nonce: number } | null;
  onResultsChange?: (results: ToolDiscoveryResult[]) => void;
}

const DiscoveryDemoCard: React.FC<DiscoveryDemoCardProps> = ({
  tools,
  highlightedToolName,
  onSelectTool,
  runRequest,
  onResultsChange,
}) => {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const { results, loading, error, durationMs, sql, discover, usedOfflineFallback } =
    useToolDiscovery(tools);

  React.useEffect(() => {
    if (!runRequest?.query) return;
    setQuery(runRequest.query);
    discover(runRequest.query);
  }, [runRequest?.nonce, runRequest?.query, discover]);

  React.useEffect(() => {
    onResultsChange?.(results);
  }, [results, onResultsChange]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (query.trim()) {
        discover(query.trim());
      }
    },
    [query, discover],
  );

  const runExample = useCallback(
    (exampleQuery: string) => {
      setQuery(exampleQuery);
      discover(exampleQuery);
    },
    [discover],
  );

  return (
    <ExpCard>
      {/* Head */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: '12px',
        }}
      >
        <h3
          style={{
            fontFamily: 'var(--at-serif)',
            fontWeight: 400,
            fontSize: '24px',
            letterSpacing: '-0.012em',
            color: 'var(--at-ink-1)',
            margin: 0,
          }}
        >
          Discovery demo{' '}
          <em style={{ fontStyle: 'italic', color: 'var(--at-red-1)' }}>
            · pgvector
          </em>
        </h3>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase' as const,
            color: 'var(--at-ink-2)',
            fontWeight: 500,
          }}
        >
          Live endpoint
        </span>
      </div>

      {/* Prose — same Instrument Sans treatment as AtelierWelcome's
          summary paragraph so explanatory copy reads consistently
          across every Atelier surface (no stray italics). */}
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '16px',
          lineHeight: 1.6,
          color: 'var(--at-ink-2)',
          margin: '0 0 26px',
          maxWidth: '680px',
        }}
      >
        Type a natural-language query. The registry finds the closest tools
        using cosine similarity over Cohere Embed v4 embeddings — the same
        primitive that powers product search. Click a result to jump to that tool
        in the registry below.
      </p>

      {/* Example queries */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          marginBottom: '14px',
        }}
      >
        {DISCOVERY_EXAMPLES.map((ex) => (
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

      {/* Query input */}
      <form onSubmit={handleSubmit}>
        <div
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: '8px',
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            marginBottom: '18px',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.22em',
              textTransform: 'uppercase' as const,
              color: 'var(--at-red-1)',
              fontWeight: 500,
              flexShrink: 0,
            }}
          >
            Query
          </span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe what you need..."
            aria-label="Tool discovery query"
            style={{
              flex: 1,
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
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
            disabled={loading || !query.trim()}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase' as const,
              fontWeight: 500,
              color: 'var(--at-cream-1)',
              backgroundColor: loading
                ? 'var(--at-ink-4)'
                : 'var(--at-ink-1)',
              border: 'none',
              borderRadius: '6px',
              padding: '7px 14px',
              cursor: loading ? 'wait' : 'pointer',
              flexShrink: 0,
            }}
          >
            {loading ? 'Searching…' : 'Discover'}
          </button>
        </div>
      </form>

      {/* Error state */}
      {error && (
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-red-1)',
            padding: '10px 12px',
            background: 'var(--at-red-soft)',
            borderRadius: '6px',
            marginBottom: '14px',
          }}
        >
          {error}
        </div>
      )}

      {/* Results list */}
      {results.length > 0 && (
        <div style={{ marginBottom: '4px' }}>
          {results.map((result: ToolDiscoveryResult, idx: number) => {
            const isHighlighted = highlightedToolName === result.name;
            return (
            <button
              key={result.toolId ?? result.name ?? idx}
              type="button"
              onClick={() => onSelectTool(result.name)}
              style={{
                display: 'grid',
                width: '100%',
                textAlign: 'left',
                gridTemplateColumns: '30px 1fr auto auto',
                gap: '14px',
                alignItems: 'center',
                padding: '10px 12px',
                borderRadius: '6px',
                marginBottom: '4px',
                border: isHighlighted
                  ? '1px solid var(--at-red-1)'
                  : '1px solid transparent',
                background:
                  idx === 0 || isHighlighted
                    ? 'var(--at-green-soft)'
                    : 'transparent',
                borderLeft:
                  idx === 0 || isHighlighted
                    ? '2px solid var(--at-green-1)'
                    : '2px solid transparent',
                paddingLeft: '10px',
                cursor: 'pointer',
              }}
            >
              {/* Rank */}
              <span
                style={{
                  fontFamily: 'var(--at-serif)',
                  fontStyle: 'italic',
                  fontSize: '17px',
                  color: 'var(--at-red-1)',
                }}
              >
                {result.rank ?? idx + 1}.
              </span>

              {/* Name */}
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '14px',
                  color:
                    result.status === 'exercise'
                      ? 'var(--at-ink-1)'
                      : 'var(--at-ink-1)',
                  fontWeight: 500,
                }}
              >
                {result.name}
              </span>

              {/* Status */}
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '11px',
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase' as const,
                  fontWeight: 500,
                  color:
                    result.status === 'shipped'
                      ? 'var(--at-green-1)'
                      : 'var(--at-red-1)',
                }}
              >
                {result.status}
              </span>

              {/* Distance / Similarity */}
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '13px',
                  color: 'var(--at-ink-1)',
                  fontWeight: 500,
                  letterSpacing: '0.02em',
                  textAlign: 'right' as const,
                  minWidth: '50px',
                }}
              >
                {typeof result.similarity === 'number'
                  ? result.similarity.toFixed(4)
                  : '—'}
              </span>
            </button>
          );
          })}
        </div>
      )}

      {usedOfflineFallback && results.length > 0 && (
        <p
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-ink-4)',
            margin: '0 0 8px',
          }}
        >
          Offline workshop ranking — live endpoint unavailable; scores are illustrative.
        </p>
      )}

      {/* Empty state after search */}
      {!loading && !error && results.length === 0 && (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            color: 'var(--at-ink-2)',
            textAlign: 'center' as const,
            padding: '16px 0',
            lineHeight: 1.55,
          }}
        >
          Press Discover to run a pgvector similarity query against the tool
          registry.
        </p>
      )}

      {/* Footer with timing + SQL */}
      {(durationMs > 0 || sql) && (
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontStyle: 'italic',
            fontSize: '13px',
            color: 'var(--at-ink-1)',
            letterSpacing: '0.04em',
            paddingTop: '14px',
            marginTop: '14px',
            borderTop: '1px dashed var(--at-rule-1)',
          }}
        >
          {durationMs > 0 && (
            <>
              <span style={{ color: 'var(--at-red-1)', fontStyle: 'normal' }}>
                {durationMs}ms
              </span>{' '}
              round-trip ·{' '}
            </>
          )}
          {sql && (
            <span style={{ color: 'var(--at-ink-2)' }}>
              {sql.split('\n')[0]}
            </span>
          )}
        </div>
      )}
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Tool row card
 * ----------------------------------------------------------------------- */

interface ToolRowProps {
  tool: Tool;
  isSelected: boolean;
  isDiscoveryMatch: boolean;
  rowRef: (el: HTMLDivElement | null) => void;
  onSelect: () => void;
  onTryDiscovery: () => void;
}

const ToolRow: React.FC<ToolRowProps> = ({
  tool,
  isSelected,
  isDiscoveryMatch,
  rowRef,
  onSelect,
  onTryDiscovery,
}) => {
  const isExercise = tool.status === 'exercise';

  return (
    <div
      ref={rowRef}
      data-testid={`tool-row-${tool.functionName}`}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect();
        }
      }}
      style={{
        position: 'relative',
        background: isExercise ? 'transparent' : 'var(--at-card-bg)',
        border: isSelected
          ? '2px solid var(--at-red-1)'
          : isExercise
            ? '1.5px dashed var(--at-rule-3)'
            : '1px solid var(--at-card-border)',
        borderRadius: 'var(--at-card-radius)',
        padding: '20px 24px 18px',
        overflow: 'hidden',
        cursor: 'pointer',
        boxShadow: isDiscoveryMatch
          ? '0 0 0 3px var(--at-green-soft)'
          : isSelected
            ? '0 4px 16px rgba(31, 20, 16, 0.08)'
            : undefined,
        transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
      }}
    >
      {/* Burgundy accent line at top-left (shipped only) */}
      {!isExercise && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 0,
            left: '20px',
            width: 'var(--at-card-accent-width)',
            height: '3px',
            backgroundColor: 'var(--at-card-accent-color)',
            borderRadius: '0 0 2px 2px',
          }}
        />
      )}

      {/* Head: numeral + name + description on left, status on right */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '32px 1fr auto',
          gap: '14px',
          alignItems: 'baseline',
          marginBottom: '8px',
        }}
      >
        {/* Numeral */}
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
          {tool.numeral}.
        </span>

        {/* Name + description */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '17px',
              fontWeight: 500,
              color: isExercise ? 'var(--at-ink-2)' : 'var(--at-ink-1)',
              letterSpacing: '0.005em',
            }}
          >
            {tool.functionName}
          </span>
          {/* Tool description — sans Instrument Sans so technical body prose
              reads as documentation, not editorial. Matches the
              AtelierWelcome summary treatment. */}
          <span
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '15px',
              color: 'var(--at-ink-2)',
              lineHeight: 1.55,
            }}
          >
            {tool.description}
          </span>
        </div>

        {/* Status: dot + pill + (optional) WRITE badge.
            The burgundy WRITE pill marks tools that mutate Aurora
            state — restock_shelf and process_return today. Read tools
            render no badge (the absence is the badge). Pattern matches
            the Shipped pill on Performance.tsx exactly: same Eyebrow
            shape, uppercase letterspacing, but var(--at-red-1) bg. */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexShrink: 0,
          }}
        >
          <StatusDot status={isExercise ? 'empty' : 'idle'} />
          <StatusPill status={tool.status} />
          {tool.mutationType === 'write' && (
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '10px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: 'var(--at-cream-1)',
                backgroundColor: 'var(--at-red-1)',
                padding: '2px 7px',
                borderRadius: '4px',
                fontWeight: 600,
              }}
              title="This tool mutates Aurora state. Cedar-gated; audited on every ALLOW."
            >
              Write
            </span>
          )}
        </div>
      </div>

      {/* Signature code block */}
      <div
        style={{
          background: isExercise ? 'transparent' : 'var(--at-cream-2)',
          border: isExercise ? '1px dashed var(--at-rule-2)' : 'none',
          padding: '9px 12px',
          borderRadius: '6px',
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          color: 'var(--at-ink-1)',
          lineHeight: 1.5,
          margin: '12px 0 12px 46px',
          overflowX: 'auto' as const,
        }}
      >
        <code>
          <span style={{ color: 'var(--at-red-1)' }}>def</span>{' '}
          {tool.functionName}
          <span style={{ color: 'var(--at-ink-1)' }}>
            ({tool.signature.split('(')[1]?.split(')')[0] ?? ''})
          </span>
          <span style={{ color: 'var(--at-ink-2)' }}>
            {' '}
            → {tool.signature.split('->')[1]?.trim() ?? 'str'}
          </span>
        </code>
      </div>

      {/* Meta row: used-by + invocation count + version */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '32px 1fr auto',
          gap: '14px',
          alignItems: 'center',
        }}
      >
        {/* Spacer for numeral column */}
        <span />

        {/* Used by + meta */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '18px',
            alignItems: 'center',
          }}
        >
          {/* Used by chips */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px',
              alignItems: 'center',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase' as const,
                color: 'var(--at-ink-2)',
                marginRight: '4px',
                fontWeight: 500,
              }}
            >
              Used by
            </span>
            {tool.usedBy.map((agent) => (
              <span
                key={agent}
                style={{
                  fontFamily: 'var(--at-serif)',
                  fontStyle: 'italic',
                  fontSize: '13px',
                  padding: '2px 9px',
                  background: isExercise
                    ? 'transparent'
                    : 'var(--at-cream-1)',
                  border: isExercise
                    ? '1px dashed var(--at-red-1)'
                    : '1px solid var(--at-rule-2)',
                  borderRadius: '100px',
                  color: isExercise ? 'var(--at-red-1)' : 'var(--at-ink-1)',
                }}
              >
                {agent}
              </span>
            ))}
          </div>

          {/* Invocation count + version */}
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              letterSpacing: '0.04em',
              color: 'var(--at-ink-2)',
            }}
          >
            <span
              style={{ color: 'var(--at-ink-1)', fontWeight: 500 }}
            >
              {tool.invocationCount.toLocaleString()}
            </span>{' '}
            invocations · v
            <span style={{ color: 'var(--at-ink-1)', fontWeight: 500 }}>
              {tool.version}
            </span>
          </span>
        </div>

        {/* Spacer for right column */}
        <span />
      </div>

      {isSelected && (
        <div
          style={{
            marginTop: '14px',
            marginLeft: '46px',
            padding: '12px 14px',
            borderRadius: '8px',
            background: 'var(--at-cream-2)',
            border: '1px dashed var(--at-rule-2)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '10px',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <span
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '14px',
              color: 'var(--at-ink-2)',
              flex: '1 1 200px',
            }}
          >
            Run discovery with a query tuned for this tool.
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onTryDiscovery();
            }}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              fontWeight: 600,
              color: 'var(--at-cream-1)',
              background: 'var(--at-ink-1)',
              border: 'none',
              borderRadius: '6px',
              padding: '7px 12px',
              cursor: 'pointer',
            }}
          >
            Try in discovery
          </button>
        </div>
      )}
    </div>
  );
};

const ToolFilterBar: React.FC<{
  filter: ToolFilter;
  counts: Record<ToolFilter, number>;
  onChange: (f: ToolFilter) => void;
}> = ({ filter, counts, onChange }) => (
  <div
    style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px',
      marginBottom: '16px',
      alignItems: 'center',
    }}
  >
    <span
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color: 'var(--at-ink-4)',
        marginRight: '4px',
      }}
    >
      Show
    </span>
    {FILTER_OPTIONS.map((opt) => {
      const active = filter === opt.id;
      return (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            padding: '5px 12px',
            borderRadius: '999px',
            border: active ? '1px solid var(--at-ink-1)' : '1px solid var(--at-rule-2)',
            background: active ? 'var(--at-ink-1)' : 'transparent',
            color: active ? 'var(--at-cream-1)' : 'var(--at-ink-2)',
            cursor: 'pointer',
          }}
        >
          {opt.label} ({counts[opt.id]})
        </button>
      );
    })}
  </div>
);

/* -----------------------------------------------------------------------
 * Related callout card — links to Agents and Architecture · Tool Registry
 * ----------------------------------------------------------------------- */

const RelatedCard: React.FC = () => (
  <ExpCard>
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '130px 1fr 1fr',
        gap: '24px',
        alignItems: 'start',
      }}
    >
      {/* Label */}
      <div
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-ink-2)',
          fontWeight: 500,
          paddingTop: '4px',
          lineHeight: 1.6,
        }}
      >
        Adjacent
        <br />
        to tools
      </div>

      {/* Agents cell */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          borderLeft: '1px solid var(--at-card-border)',
          paddingLeft: '24px',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--at-serif)',
            fontWeight: 400,
            fontStyle: 'italic',
            fontSize: '20px',
            color: 'var(--at-ink-1)',
            letterSpacing: '-0.01em',
          }}
        >
          Agents{' '}
          <span style={{ color: 'var(--at-red-1)' }}>· five peers</span>
        </div>
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            color: 'var(--at-ink-2)',
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          Five specialist agents invoke these tools. Each agent has a curated
          tool set — Search uses find_pieces and explore_collection;
          Recommendation uses find_pieces and side_by_side. The registry lets
          agents discover tools they weren't explicitly given.
        </p>
        <Link
          to="/atelier/agents"
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase' as const,
            color: 'var(--at-red-1)',
            textDecoration: 'none',
            fontWeight: 500,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            marginTop: '4px',
          }}
        >
          Open Agents surface
          <span
            aria-hidden="true"
            style={{ fontFamily: 'var(--at-serif)', fontStyle: 'italic' }}
          >
            →
          </span>
        </Link>
      </div>

      {/* Architecture · Tool Registry cell */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          borderLeft: '1px solid var(--at-card-border)',
          paddingLeft: '24px',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--at-serif)',
            fontWeight: 400,
            fontStyle: 'italic',
            fontSize: '20px',
            color: 'var(--at-ink-1)',
            letterSpacing: '-0.01em',
          }}
        >
          Tool Registry{' '}
          <span style={{ color: 'var(--at-red-1)' }}>· architecture</span>
        </div>
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            color: 'var(--at-ink-2)',
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          The{' '}
          <code
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13.5px',
              color: 'var(--at-ink-1)',
              background: 'var(--at-cream-2)',
              padding: '1px 6px',
              borderRadius: 4,
            }}
          >
            tool_registry
          </code>{' '}
          table stores each tool's name, description, and a 1024-dim Cohere
          Embed v4 embedding. Discovery is a single pgvector cosine query — the
          same primitive that powers product search, applied to capabilities.
        </p>
        <Link
          to="/atelier/architecture/tool-registry"
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase' as const,
            color: 'var(--at-red-1)',
            textDecoration: 'none',
            fontWeight: 500,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            marginTop: '4px',
          }}
        >
          Open Tool Registry detail
          <span
            aria-hidden="true"
            style={{ fontFamily: 'var(--at-serif)', fontStyle: 'italic' }}
          >
            →
          </span>
        </Link>
      </div>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '14px',
      padding: '24px 0',
    }}
  >
    {Array.from({ length: 6 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: '120px',
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
      textAlign: 'center' as const,
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
      We couldn't load the tools.
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
      textAlign: 'center' as const,
    }}
  >
    <Eyebrow label="No tools" variant="muted" />
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
      No tools have been loaded.
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
      Check that the tools fixture data is available and try again.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Tools: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<Tool[]>({
    key: 'tools',
  });
  const buildState = useBuildState();
  const [filter, setFilter] = useState<ToolFilter>('all');
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [discoveryMatchTool, setDiscoveryMatchTool] = useState<string | null>(null);
  const [discoveryRun, setDiscoveryRun] = useState<{
    query: string;
    nonce: number;
  } | null>(null);
  const toolRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const discoverySectionRef = useRef<HTMLDivElement>(null);

  // Apply build state overrides — when the backend reports a different status
  // than the fixture, the override takes precedence (exercise → shipped transition)
  const tools: Tool[] = (data ?? []).map((tool) => {
    const override = buildState.toolStatus[tool.functionName];
    if (override && override !== tool.status) {
      return { ...tool, status: override };
    }
    return tool;
  });

  const filterCounts = useMemo(
    (): Record<ToolFilter, number> => ({
      all: tools.length,
      shipped: tools.filter((t) => t.status === 'shipped').length,
      exercise: tools.filter((t) => t.status === 'exercise').length,
      read: tools.filter((t) => t.mutationType === 'read').length,
      write: tools.filter((t) => t.mutationType === 'write').length,
    }),
    [tools],
  );

  const filteredTools = useMemo(
    () => filterTools(tools, filter),
    [tools, filter],
  );

  const focusTool = useCallback((functionName: string) => {
    setSelectedTool(functionName);
    setFilter('all');
    requestAnimationFrame(() => {
      toolRowRefs.current[functionName]?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    });
  }, []);

  const handleSegmentClick = useCallback(
    (seg: Segment) => {
      const tool = tools.find((t) => String(t.numeral) === seg.id);
      if (tool) focusTool(tool.functionName);
    },
    [tools, focusTool],
  );

  const handleTryDiscovery = useCallback((tool: Tool) => {
    setDiscoveryRun({ query: discoveryQueryForTool(tool), nonce: Date.now() });
    discoverySectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const handleResultsChange = useCallback((results: ToolDiscoveryResult[]) => {
    setDiscoveryMatchTool(results[0]?.name ?? null);
  }, []);

  const shippedCount = tools.filter((t) => t.status === 'shipped').length;
  const totalCount = tools.length;
  const segments = buildSegments(tools);
  const activeSegmentId =
    selectedTool != null
      ? String(tools.find((t) => t.functionName === selectedTool)?.numeral ?? '')
      : undefined;

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Tools · twelve functions · pgvector-discoverable"
        title="The toolkit, by what each does."
        summary="Twelve tools in the registry. Eleven ship as reference in the Builder's Session image; floor_check is the sole hands-on wire in Part I. Each tool has an embedding — discovery ranks by cosine similarity. Replacing the stub updates GET /api/atelier/build-state so Stock Keeper and floor_check read as shipped."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && tools.length === 0 && <EmptyState />}

      {!loading && !error && tools.length > 0 && (
        <>
          {/* Workshop Progress Strip */}
          <div style={{ marginBottom: '28px' }}>
            <WorkshopProgressStrip
              segments={segments}
              shipped={shippedCount}
              total={totalCount}
              activeSegmentId={activeSegmentId}
              onSegmentClick={handleSegmentClick}
            />
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '12px',
                color: 'var(--at-ink-4)',
                marginTop: '8px',
              }}
            >
              Click a segment to jump to that tool.
            </p>
          </div>

          {/* Discovery Demo Card */}
          <div ref={discoverySectionRef} style={{ marginBottom: '32px' }}>
            <DiscoveryDemoCard
              tools={tools}
              highlightedToolName={selectedTool ?? discoveryMatchTool}
              onSelectTool={focusTool}
              runRequest={discoveryRun}
              onResultsChange={handleResultsChange}
            />
          </div>

          <ToolFilterBar filter={filter} counts={filterCounts} onChange={setFilter} />

          {/* Tool rows */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              marginBottom: '32px',
            }}
          >
            {filteredTools.length === 0 ? (
              <p
                style={{
                  fontFamily: 'var(--at-sans)',
                  fontSize: '15px',
                  color: 'var(--at-ink-4)',
                  textAlign: 'center',
                  padding: '24px 0',
                }}
              >
                No tools match this filter.
              </p>
            ) : (
              filteredTools.map((tool) => (
                <ToolRow
                  key={tool.numeral}
                  tool={tool}
                  isSelected={selectedTool === tool.functionName}
                  isDiscoveryMatch={discoveryMatchTool === tool.functionName}
                  rowRef={(el) => {
                    toolRowRefs.current[tool.functionName] = el;
                  }}
                  onSelect={() =>
                    setSelectedTool((prev) =>
                      prev === tool.functionName ? null : tool.functionName,
                    )
                  }
                  onTryDiscovery={() => handleTryDiscovery(tool)}
                />
              ))
            )}
          </div>

          {/* Related callout card */}
          <RelatedCard />
        </>
      )}
    </div>
  );
};

export default Tools;
