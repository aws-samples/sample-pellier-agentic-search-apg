/**
 * ChatTab — Two-column chat thread with context rail.
 *
 * Renders the multi-turn chat conversation for a session with inline
 * tool calls, product recommendations, plan rows, confidence indicators,
 * memory pills, and a context rail showing memory, agents, and skills.
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9,
 *               3.10, 3.11, 3.12, 3.13, 3.14, 3.15
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { ContextRail, ExpCard, Eyebrow, StatusDot } from '../../components';
import { resolveProductImageUrl } from '../../../utils/resolveProductImageUrl';
import { searchCatalog } from '../../services/catalogSearch';
import type { SessionOutletContext } from './SessionView';
import type {
  ChatTurn,
  ToolCall,
  ProductCard,
  PlanRow,
  ConfidenceRow,
  MemoryPill,
  SessionDetail,
} from '../../types';

/* =======================================================================
 * SQL keyword highlighter
 * ======================================================================= */

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'ORDER', 'BY', 'LIMIT', 'INSERT', 'UPDATE',
  'DELETE', 'CREATE', 'DROP', 'ALTER', 'JOIN', 'LEFT', 'RIGHT', 'INNER',
  'OUTER', 'ON', 'AND', 'OR', 'NOT', 'IN', 'AS', 'IS', 'NULL', 'LIKE',
  'ILIKE', 'GROUP', 'HAVING', 'DISTINCT', 'UNION', 'ALL', 'SET', 'INTO',
  'VALUES', 'TABLE', 'INDEX', 'WITH', 'CASE', 'WHEN', 'THEN', 'ELSE',
  'END', 'ASC', 'DESC', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
]);

function highlightSQL(sql: string): React.ReactNode[] {
  // Split on word boundaries while preserving whitespace and symbols
  const tokens = sql.split(/(\b\w+\b)/g);
  return tokens.map((token, i) => {
    if (SQL_KEYWORDS.has(token.toUpperCase())) {
      return (
        <span key={i} style={{ color: 'var(--at-red-1)', fontWeight: 600 }}>
          {token}
        </span>
      );
    }
    return <span key={i}>{token}</span>;
  });
}

/* =======================================================================
 * Persona strip
 * ======================================================================= */

const PersonaStrip: React.FC<{
  personaId: string;
  openingQuery: string;
}> = ({ personaId }) => {
  // Derive persona display info from the session's personaId
  const name = personaId.charAt(0).toUpperCase() + personaId.slice(1);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
        padding: '16px 20px',
        background: 'var(--at-cream-2)',
        borderRadius: 'var(--at-card-radius)',
        marginBottom: '24px',
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          backgroundColor: 'var(--at-red-1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--at-cream-1)',
          fontFamily: 'var(--at-sans)',
          fontSize: '20px',
          fontWeight: 400,
          flexShrink: 0,
        }}
      >
        {name.charAt(0)}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '17px',
            color: 'var(--at-ink-1)',
            lineHeight: 1.3,
          }}
        >
          {name}
        </div>
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-2)',
            marginTop: '2px',
          }}
        >
          Returning customer · 3 prior orders · CUST-{personaId.toUpperCase()}
        </div>
      </div>
    </div>
  );
};

/* =======================================================================
 * Tool call chip (collapsible)
 * ======================================================================= */

const ToolCallChip: React.FC<{ tool: ToolCall }> = ({ tool }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{
        border: '1px solid var(--at-rule-2)',
        borderRadius: '10px',
        overflow: 'hidden',
        marginBottom: '8px',
      }}
    >
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          width: '100%',
          padding: '10px 14px',
          background: 'var(--at-cream-elev)',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--at-ink-1)',
          }}
        >
          {tool.toolName}
        </span>
        <span
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            color: 'var(--at-ink-1)',
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {tool.description}
        </span>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-ink-2)',
            whiteSpace: 'nowrap',
          }}
        >
          {tool.durationMs}ms
        </span>
        <span
          style={{
            fontSize: '12px',
            color: 'var(--at-ink-2)',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s ease',
          }}
        >
          ▼
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div style={{ padding: '12px 14px', borderTop: '1px solid var(--at-rule-1)' }}>
          {tool.sql && (
            <div
              style={{
                background: 'var(--at-cream-2)',
                borderRadius: '8px',
                padding: '12px 14px',
                marginBottom: tool.resultSummary ? '10px' : 0,
                fontFamily: 'var(--at-mono)',
                fontSize: '13px',
                lineHeight: 'var(--at-mono-leading)',
                color: 'var(--at-ink-2)',
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {highlightSQL(tool.sql)}
            </div>
          )}
          {tool.resultSummary && (
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '15px',
                color: 'var(--at-ink-1)',
                margin: 0,
                lineHeight: 1.5,
              }}
            >
              {tool.resultSummary}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

/* =======================================================================
 * Product recommendation grid
 * ======================================================================= */

const ProductTile: React.FC<{ product: ProductCard }> = ({ product }) => {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = Boolean(product.imageUrl) && !imgFailed;

  return (
    <div
      style={{
        border: '1px solid var(--at-rule-1)',
        borderRadius: '10px',
        overflow: 'hidden',
        background: 'var(--at-cream-elev)',
      }}
    >
      <div
        style={{
          height: '100px',
          background: 'var(--at-cream-2)',
          overflow: 'hidden',
        }}
      >
        {showImage ? (
          <img
            src={resolveProductImageUrl(product.imageUrl)}
            alt={product.name}
            onError={() => setImgFailed(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                color: 'var(--at-ink-4)',
                textTransform: 'uppercase',
                letterSpacing: '0.14em',
              }}
            >
              {product.brand}
            </span>
          </div>
        )}
      </div>
      <div style={{ padding: '10px 12px' }}>
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            color: 'var(--at-ink-2)',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            marginBottom: '4px',
          }}
        >
          {product.brand}
        </div>
        <div
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            color: 'var(--at-ink-1)',
            lineHeight: 1.3,
            marginBottom: '6px',
          }}
        >
          {product.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '13px',
            color: 'var(--at-ink-2)',
            fontWeight: 600,
          }}
        >
          ${product.price}
        </div>
      </div>
    </div>
  );
};

const ProductGrid: React.FC<{ products: ProductCard[] }> = ({ products }) => (
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: '12px',
      marginTop: '12px',
      marginBottom: '8px',
    }}
  >
    {products.map((product, i) => (
      <ProductTile key={`${product.name}-${i}`} product={product} />
    ))}
  </div>
);

/* =======================================================================
 * Plan row
 * ======================================================================= */

/** Infer step count from flow arrows when fixtures omit `stepCount`. */
function inferPlanStepCountFromFlow(flowSummary: string): number {
  const t = flowSummary.trim();
  if (!t) return 1;
  return (t.match(/→/g)?.length ?? 0) + 1;
}

/** Defaults match the live follow-up plan row (Search / N steps / summary). */
function normalizePlanRow(plan: PlanRow): {
  routingPattern: string;
  stepCount: number;
  flowSummary: string;
  traceLink?: string;
} {
  const flowSummary = plan.flowSummary ?? '';
  return {
    routingPattern: plan.routingPattern?.trim() || 'steps',
    stepCount:
      typeof plan.stepCount === 'number' && Number.isFinite(plan.stepCount)
        ? plan.stepCount
        : inferPlanStepCountFromFlow(flowSummary),
    flowSummary,
    traceLink: plan.traceLink,
  };
}

const PlanRowDisplay: React.FC<{ plan: PlanRow }> = ({ plan: rawPlan }) => {
  const plan = normalizePlanRow(rawPlan);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 14px',
        background: 'var(--at-cream-2)',
        borderRadius: '8px',
        marginBottom: '12px',
        flexWrap: 'wrap',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '2px 8px',
          borderRadius: '4px',
          backgroundColor: 'var(--at-red-soft)',
          color: 'var(--at-red-1)',
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}
      >
        {plan.routingPattern}
      </span>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          color: 'var(--at-ink-1)',
        }}
      >
        {plan.stepCount} steps
      </span>
      <span
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          color: 'var(--at-ink-2)',
          flex: 1,
        }}
      >
        {plan.flowSummary}
      </span>
      {plan.traceLink && (
        <a
          href={plan.traceLink}
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-red-1)',
            textDecoration: 'none',
            whiteSpace: 'nowrap',
          }}
        >
          view trace →
        </a>
      )}
    </div>
  );
};

/* =======================================================================
 * Confidence row
 * ======================================================================= */

const ConfidenceDisplay: React.FC<{ confidence: ConfidenceRow }> = ({
  confidence,
}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '10px 14px',
      background: 'var(--at-green-soft)',
      borderRadius: '8px',
      marginTop: '8px',
    }}
  >
    <span
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '22px',
        fontWeight: 400,
        color: 'var(--at-green-1)',
        whiteSpace: 'nowrap',
      }}
    >
      {confidence.percentage}%
    </span>
    <span
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '15px',
        color: 'var(--at-ink-2)',
        lineHeight: 1.45,
      }}
    >
      {confidence.reasoning}
    </span>
  </div>
);

/* =======================================================================
 * Memory pills
 * ======================================================================= */

const MemoryPillDisplay: React.FC<{ pill: MemoryPill }> = ({ pill }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '4px 10px',
      borderRadius: '999px',
      border: '1.5px dashed var(--at-red-1)',
      fontFamily: 'var(--at-sans)',
      fontSize: '14px',
      color: 'var(--at-ink-2)',
      lineHeight: 1.4,
    }}
  >
    <span
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '11px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: 'var(--at-red-1)',
      }}
    >
      {pill.tier}
    </span>
    {pill.content}
  </span>
);

/* =======================================================================
 * Chat turn renderer
 * ======================================================================= */

const ChatTurnDisplay: React.FC<{ turn: ChatTurn }> = ({ turn }) => {
  if (turn.role === 'user') {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          marginBottom: '20px',
        }}
      >
        <div
          style={{
            maxWidth: '70%',
            padding: '14px 18px',
            backgroundColor: 'var(--at-ink-1)',
            color: 'var(--at-cream-1)',
            borderRadius: '14px',
            fontFamily: 'var(--at-sans)',
            fontSize: '16px',
            lineHeight: 'var(--at-body-leading)',
          }}
        >
          {turn.content}
        </div>
      </div>
    );
  }

  // Assistant turn
  return (
    <div style={{ marginBottom: '24px' }}>
      {/* Plan row at start of assistant turn */}
      {turn.plan && <PlanRowDisplay plan={turn.plan} />}

      {/* Tool calls */}
      {turn.toolCalls && turn.toolCalls.length > 0 && (
        <div style={{ marginBottom: '12px' }}>
          {turn.toolCalls.map((tool, i) => (
            <ToolCallChip key={i} tool={tool} />
          ))}
        </div>
      )}

      {/* Assistant prose */}
      <div
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '16px',
          lineHeight: 'var(--at-body-leading)',
          color: 'var(--at-ink-1)',
          maxWidth: '85%',
        }}
      >
        {turn.content}
      </div>

      {/* Product recommendations */}
      {turn.products && turn.products.length > 0 && (
        <ProductGrid products={turn.products} />
      )}

      {/* Confidence */}
      {turn.confidence && <ConfidenceDisplay confidence={turn.confidence} />}

      {/* Memory pills */}
      {turn.memoryPills && turn.memoryPills.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            marginTop: '10px',
          }}
        >
          {turn.memoryPills.map((pill, i) => (
            <MemoryPillDisplay key={i} pill={pill} />
          ))}
        </div>
      )}
    </div>
  );
};

/* =======================================================================
 * Follow-up hints + live catalog search
 * ======================================================================= */

function followUpHintsForSession(session: SessionDetail): string[] {
  const q = session.openingQuery.toLowerCase();
  const persona = session.personaId.toLowerCase();
  const contextual: string[] = [];

  if (q.includes('overshirt') || q.includes('pair')) {
    contextual.push('Cheapest piece that goes with the overshirt');
  }
  if (q.includes('linen') || persona === 'marco') {
    contextual.push('Three linen pieces under $150');
  }
  if (q.includes('warehouse') || q.includes('brooklyn')) {
    contextual.push('What is in stock at Brooklyn right now?');
  }
  if (persona === 'anna') {
    contextual.push('Gift-ready home accents under $80');
  }
  if (persona === 'theo') {
    contextual.push('Ceramic tabletop in warm neutrals');
  }

  const generic = [
    'What ships fastest from Brooklyn?',
    'One more option under $100',
    'Close substitute if my size is gone',
  ];

  return Array.from(new Set([...contextual, ...generic])).slice(0, 5);
}

function isoTimestamp(): string {
  return new Date().toISOString();
}

/* =======================================================================
 * Synced replay timeline (chat column + trace rail)
 * ======================================================================= */

type ReplayEntry =
  | { id: string; kind: 'user'; turn: ChatTurn }
  | { id: string; kind: 'plan'; plan: PlanRow }
  | { id: string; kind: 'tool'; tool: ToolCall }
  | { id: string; kind: 'assistant_tail'; turn: ChatTurn };

function buildReplayTimeline(turns: ChatTurn[]): ReplayEntry[] {
  const out: ReplayEntry[] = [];
  turns.forEach((turn, ti) => {
    if (turn.role === 'user') {
      out.push({ id: `replay-${ti}-user`, kind: 'user', turn });
      return;
    }
    if (turn.plan) {
      out.push({ id: `replay-${ti}-plan`, kind: 'plan', plan: turn.plan });
    }
    (turn.toolCalls ?? []).forEach((tool, j) => {
      out.push({ id: `replay-${ti}-tool-${j}`, kind: 'tool', tool });
    });
    out.push({ id: `replay-${ti}-tail`, kind: 'assistant_tail', turn });
  });
  return out;
}

function traceVisibleCountFromReplay(
  replayVisible: number,
  timeline: ReplayEntry[],
): number {
  return timeline
    .slice(0, replayVisible)
    .filter((e) => e.kind === 'plan' || e.kind === 'tool').length;
}

/** One row of the staggered transcript replay */
const ReplayEntryDisplay: React.FC<{ entry: ReplayEntry }> = ({ entry }) => {
  switch (entry.kind) {
    case 'user':
      return (
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            marginBottom: '20px',
          }}
        >
          <div
            style={{
              maxWidth: '70%',
              padding: '14px 18px',
              backgroundColor: 'var(--at-ink-1)',
              color: 'var(--at-cream-1)',
              borderRadius: '14px',
              fontFamily: 'var(--at-sans)',
              fontSize: '16px',
              lineHeight: 'var(--at-body-leading)',
            }}
          >
            {entry.turn.content}
          </div>
        </div>
      );
    case 'plan':
      return <PlanRowDisplay plan={entry.plan} />;
    case 'tool':
      return <ToolCallChip tool={entry.tool} />;
    case 'assistant_tail': {
      const turn = entry.turn;
      return (
        <div style={{ marginBottom: '24px' }}>
          <div
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '16px',
              lineHeight: 'var(--at-body-leading)',
              color: 'var(--at-ink-1)',
              maxWidth: '85%',
            }}
          >
            {turn.content}
          </div>
          {turn.products && turn.products.length > 0 && (
            <ProductGrid products={turn.products} />
          )}
          {turn.confidence && <ConfidenceDisplay confidence={turn.confidence} />}
          {turn.memoryPills && turn.memoryPills.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '8px',
                marginTop: '10px',
              }}
            >
              {turn.memoryPills.map((pill, i) => (
                <MemoryPillDisplay key={i} pill={pill} />
              ))}
            </div>
          )}
        </div>
      );
    }
  }
};

/* =======================================================================
 * Composer bar — live POST /api/search + suggestion pills
 * ======================================================================= */

const ComposerBar: React.FC<{
  suggestions: string[];
  onSend: (text: string) => Promise<void>;
  busy: boolean;
  locked: boolean;
  error: string | null;
}> = ({ suggestions, onSend, busy, locked, error }) => {
  const [draft, setDraft] = useState('');

  const submit = async () => {
    const t = draft.trim();
    if (!t || busy || locked) return;
    setDraft('');
    await onSend(t);
  };

  const disabled = busy || locked;

  return (
    <div style={{ marginTop: '24px' }}>
      {suggestions.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            marginBottom: '12px',
          }}
        >
          {suggestions.map((hint) => (
            <button
              key={hint}
              type="button"
              disabled={disabled}
              onClick={() => void onSend(hint)}
              style={{
                padding: '6px 14px',
                borderRadius: '999px',
                border: '1px solid var(--at-rule-2)',
                background: 'var(--at-cream-elev)',
                fontFamily: 'var(--at-sans)',
                fontSize: '14px',
                color: 'var(--at-ink-2)',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.55 : 1,
              }}
            >
              {hint}
            </button>
          ))}
        </div>
      )}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '12px 16px',
          background: 'var(--at-cream-elev)',
          border: '1px solid var(--at-rule-2)',
          borderRadius: '12px',
        }}
      >
        <span style={{ fontSize: '17px', color: 'var(--at-red-1)', flexShrink: 0 }}>
          ✦
        </span>
        <input
          type="text"
          value={draft}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder="Ask a follow-up question…"
          aria-label="Follow-up question"
          style={{
            flex: 1,
            minWidth: 0,
            border: 'none',
            background: 'transparent',
            fontFamily: 'var(--at-sans)',
            fontSize: '15px',
            color: 'var(--at-ink-1)',
            outline: 'none',
          }}
        />
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-ink-2)',
            padding: '2px 6px',
            border: '1px solid var(--at-rule-2)',
            borderRadius: '4px',
            whiteSpace: 'nowrap',
          }}
        >
          ↵
        </span>
        <button
          type="button"
          disabled={disabled || !draft.trim()}
          onClick={() => void submit()}
          aria-label="Send message"
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            border: 'none',
            backgroundColor: 'var(--at-ink-1)',
            color: 'var(--at-cream-1)',
            cursor: disabled || !draft.trim() ? 'not-allowed' : 'pointer',
            opacity: disabled || !draft.trim() ? 0.4 : 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '15px',
            flexShrink: 0,
          }}
        >
          ↑
        </button>
      </div>
      {error && (
        <p
          style={{
            margin: '10px 0 0',
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            color: 'var(--at-red-1)',
            lineHeight: 1.45,
          }}
        >
          {error}
        </p>
      )}
      <p
        style={{
          margin: '8px 0 0',
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          color: 'var(--at-ink-4)',
          letterSpacing: '0.04em',
        }}
      >
        Follow-ups POST to /api/search (pgvector). Backend :8000 proxied by Vite.
      </p>
    </div>
  );
};

/* =======================================================================
 * Empty state with suggested queries
 * ======================================================================= */

const EmptyState: React.FC = () => {
  const suggestions = [
    'A linen shirt for warm evenings out',
    'What goes well with the pour-over set?',
    'Compare the camp shirt and the overshirt',
    'Something beautiful under $100 for a gift',
  ];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '60px 24px',
        textAlign: 'center',
      }}
    >
      <Eyebrow label="No messages yet" variant="muted" />
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '22px',
          color: 'var(--at-ink-1)',
          marginTop: '16px',
          marginBottom: '20px',
        }}
      >
        Try asking
      </p>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
        {suggestions.map((s) => (
          <span
            key={s}
            style={{
              padding: '6px 14px',
              borderRadius: '999px',
              border: '1px solid var(--at-rule-2)',
              fontFamily: 'var(--at-sans)',
              fontSize: '15px',
              color: 'var(--at-ink-2)',
              cursor: 'default',
            }}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
};

/* =======================================================================
 * Context rail cards
 * ======================================================================= */

type LiveTraceStep = {
  id: string;
  title: string;
  subtitle?: string;
  durationMs?: number;
};

function collectLiveTraceSteps(turns: ChatTurn[]): LiveTraceStep[] {
  const out: LiveTraceStep[] = [];
  turns.forEach((turn, ti) => {
    if (turn.role !== 'assistant') return;
    if (turn.plan) {
      const np = normalizePlanRow(turn.plan);
      out.push({
        id: `t${ti}-plan`,
        title: np.routingPattern,
        subtitle: `${np.stepCount} steps · ${np.flowSummary}`,
      });
    }
    (turn.toolCalls ?? []).forEach((tool, j) => {
      out.push({
        id: `t${ti}-tool-${j}`,
        title: tool.toolName,
        subtitle: tool.description,
        durationMs: tool.durationMs,
      });
    });
  });
  return out;
}

/**
 * Routing + tool steps; ``visibleCount`` stays in lockstep with the chat
 * replay timeline (plan/tool rows only). ``emphasizeLatest`` adds the red
 * accent on the newest row while the replay timer is running.
 */
const LiveTraceRail: React.FC<{
  steps: LiveTraceStep[];
  visibleCount: number;
  emphasizeLatest: boolean;
}> = ({ steps, visibleCount, emphasizeLatest }) => {
  if (steps.length === 0) {
    return (
      <ExpCard>
        <Eyebrow label="Live trace" />
        <p
          style={{
            margin: '14px 0 0',
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            color: 'var(--at-ink-4)',
            lineHeight: 1.5,
          }}
        >
          No routing or tool steps in this thread yet.
        </p>
      </ExpCard>
    );
  }

  const cap = Math.min(Math.max(visibleCount, 0), steps.length);
  const visible = steps.slice(0, cap);

  return (
    <ExpCard>
      <Eyebrow label="Live trace" />
      <div
        style={{
          marginTop: '14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        {visible.map((step, index) => {
          const isLatest = emphasizeLatest && index === visible.length - 1;
          return (
            <div
              key={step.id}
              style={{
                borderLeft: isLatest
                  ? '3px solid var(--at-red-1)'
                  : '3px solid var(--at-rule-1)',
                paddingLeft: '12px',
                paddingTop: '2px',
                paddingBottom: '2px',
                background: isLatest
                  ? 'var(--at-red-soft)'
                  : 'transparent',
                borderRadius: '0 8px 8px 0',
                transition: 'background 0.25s ease, border-color 0.25s ease',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  gap: '8px',
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '13px',
                    fontWeight: 600,
                    color: 'var(--at-ink-1)',
                    wordBreak: 'break-word',
                  }}
                >
                  {step.title}
                </span>
                {step.durationMs != null && (
                  <span
                    style={{
                      fontFamily: 'var(--at-mono)',
                      fontSize: '12px',
                      color: 'var(--at-ink-2)',
                      flexShrink: 0,
                    }}
                  >
                    {step.durationMs}ms
                  </span>
                )}
              </div>
              {step.subtitle && (
                <p
                  style={{
                    margin: '6px 0 0',
                    fontFamily: 'var(--at-sans)',
                    fontSize: '14px',
                    color: 'var(--at-ink-2)',
                    lineHeight: 1.45,
                  }}
                >
                  {step.subtitle}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </ExpCard>
  );
};

/** Memory card — STM/LTM tiers with item counts and chips */
const MemoryCard: React.FC<{ turns: ChatTurn[] }> = ({ turns }) => {
  // Collect all memory pills from the chat
  const allPills = turns.flatMap((t) => t.memoryPills ?? []);
  const stmPills = allPills.filter((p) => p.tier === 'stm');
  const ltmPills = allPills.filter((p) => p.tier === 'ltm');

  return (
    <ExpCard>
      <Eyebrow label="Memory" />
      <div style={{ marginTop: '14px' }}>
        {/* STM tier */}
        <div style={{ marginBottom: '14px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '8px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: 'var(--at-red-1)',
                padding: '1px 6px',
                border: '1px solid var(--at-red-1)',
                borderRadius: '3px',
              }}
            >
              STM
            </span>
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '13px',
                color: 'var(--at-ink-2)',
              }}
            >
              {stmPills.length} item{stmPills.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {stmPills.map((pill, i) => (
              <span
                key={i}
                style={{
                  fontFamily: 'var(--at-sans)',
                  fontSize: '14px',
                  color: 'var(--at-ink-2)',
                  padding: '4px 10px',
                  background: 'var(--at-cream-2)',
                  borderRadius: '6px',
                  lineHeight: 1.4,
                }}
              >
                {pill.content}
              </span>
            ))}
          </div>
        </div>

        {/* LTM tier */}
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '8px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: 'var(--at-green-1)',
                padding: '1px 6px',
                border: '1px solid var(--at-green-1)',
                borderRadius: '3px',
              }}
            >
              LTM
            </span>
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '13px',
                color: 'var(--at-ink-2)',
              }}
            >
              {ltmPills.length} item{ltmPills.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {ltmPills.map((pill, i) => (
              <span
                key={i}
                style={{
                  fontFamily: 'var(--at-sans)',
                  fontSize: '14px',
                  color: 'var(--at-ink-2)',
                  padding: '4px 10px',
                  background: 'var(--at-cream-2)',
                  borderRadius: '6px',
                  lineHeight: 1.4,
                }}
              >
                {pill.content}
              </span>
            ))}
          </div>
        </div>
      </div>
    </ExpCard>
  );
};

/** Agents card — 5 specialists with status dots */
const AGENTS_LIST = [
  { name: 'Search', status: 'live' as const },
  { name: 'Recommendation', status: 'live' as const },
  { name: 'Pricing', status: 'live' as const },
  { name: 'Inventory', status: 'idle' as const },
  { name: 'Customer Support', status: 'idle' as const },
];

const AgentsCard: React.FC = () => (
  <ExpCard>
    <Eyebrow label="Agents" />
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        marginTop: '14px',
      }}
    >
      {AGENTS_LIST.map((agent) => (
        <div
          key={agent.name}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <StatusDot status={agent.status} size={8} />
          <span
            style={{
              fontFamily: 'var(--at-sans)',
              fontSize: '15px',
              color:
                agent.status === 'live'
                  ? 'var(--at-ink-1)'
                  : 'var(--at-ink-4)',
            }}
          >
            {agent.name}
          </span>
        </div>
      ))}
    </div>
  </ExpCard>
);

/** Skills card — three persona skills (`skills.json` bundles) with placeholder status */
const SKILLS_LIST = [
  { name: 'the-packing-list', active: false },
  { name: 'the-gift-table', active: false },
  { name: 'the-makers-shelf', active: false },
];

const SkillsCard: React.FC = () => (
  <ExpCard>
    <Eyebrow label="Skills" />
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        marginTop: '14px',
      }}
    >
      {SKILLS_LIST.map((skill) => (
        <div
          key={skill.name}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <StatusDot status={skill.active ? 'live' : 'empty'} size={8} />
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              color: skill.active
                ? 'var(--at-ink-1)'
                : 'var(--at-ink-4)',
            }}
          >
            {skill.name}
          </span>
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-ink-2)',
              marginLeft: 'auto',
            }}
          >
            {skill.active ? 'Active' : 'Inactive'}
          </span>
        </div>
      ))}
    </div>
  </ExpCard>
);

/* =======================================================================
 * Main ChatTab component
 * ======================================================================= */

const ChatTab: React.FC = () => {
  const { session } = useOutletContext<SessionOutletContext>();
  const fixtureTurns = session.chat ?? [];
  const [liveTurns, setLiveTurns] = useState<ChatTurn[]>([]);
  const [replyBusy, setReplyBusy] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);

  const timeline = useMemo(() => buildReplayTimeline(fixtureTurns), [fixtureTurns]);
  const traceSteps = useMemo(() => collectLiveTraceSteps(fixtureTurns), [fixtureTurns]);
  const [replayVisible, setReplayVisible] = useState(0);
  const [replayDone, setReplayDone] = useState(false);

  useEffect(() => {
    if (timeline.length === 0) {
      setReplayVisible(0);
      setReplayDone(true);
      return;
    }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setReplayVisible(timeline.length);
      setReplayDone(true);
      return;
    }
    setReplayVisible(0);
    setReplayDone(false);
    let count = 0;
    const id = window.setInterval(() => {
      count += 1;
      setReplayVisible(Math.min(count, timeline.length));
      if (count >= timeline.length) {
        window.clearInterval(id);
        setReplayDone(true);
      }
    }, 400);
    return () => window.clearInterval(id);
  }, [timeline]);

  const visibleTraceCount = traceVisibleCountFromReplay(replayVisible, timeline);
  const traceEmphasizeLatest = !replayDone && timeline.length > 0;

  const displayTurns = useMemo(
    () => [...fixtureTurns, ...liveTurns],
    [fixtureTurns, liveTurns],
  );

  const hintPills = useMemo(() => followUpHintsForSession(session), [session]);

  const composerLocked = !replayDone && timeline.length > 0;

  const handleFollowUp = async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed || replyBusy || composerLocked) return;
    setReplyError(null);
    setReplyBusy(true);
    try {
      const data = await searchCatalog(trimmed, 6);
      const ts = isoTimestamp();
      const userTurn: ChatTurn = {
        role: 'user',
        content: trimmed,
        timestamp: ts,
      };
      const cards: ProductCard[] = data.products.map((p) => ({
        brand: p.brand,
        name: p.name,
        price: Math.round(p.price),
        imageUrl:
          p.imageUrl?.startsWith('http') || p.imageUrl?.startsWith('/')
            ? p.imageUrl
            : `/${p.imageUrl || ''}`,
        traceRef: `product:${p.id}`,
      }));
      const toolSql = [
        'WITH query_embedding AS (SELECT $1::vector AS emb)',
        'SELECT name, brand, price, 1 - (embedding <=> (SELECT emb FROM query_embedding)) AS similarity',
        'FROM pellier.product_catalog',
        'WHERE "imgUrl" IS NOT NULL',
        'ORDER BY embedding <=> (SELECT emb FROM query_embedding)',
        'LIMIT 6',
      ].join('\n');

      const assistantTurn: ChatTurn = {
        role: 'assistant',
        content: `Pulled ${data.products.length} rows from pellier.product_catalog (${data.searchMs}ms vector search · ${data.queryEmbeddingMs}ms embed).`,
        timestamp: ts,
        plan: {
          routingPattern: 'Search',
          stepCount: 1,
          flowSummary: 'Storefront POST /api/search → pgvector',
        },
        toolCalls: [
          {
            toolName: 'find_pieces',
            description: `Semantic search: ${trimmed.length > 140 ? `${trimmed.slice(0, 137)}…` : trimmed}`,
            durationMs: data.searchMs,
            sql: toolSql,
            resultSummary: `${data.products.length} products within cosine window.`,
          },
        ],
        products: cards,
      };
      setLiveTurns((prev) => [...prev, userTurn, assistantTurn]);
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setReplyBusy(false);
    }
  };

  const hasFixtureMessages = fixtureTurns.length > 0;

  return (
    <div
      style={{
        display: 'flex',
        gap: '0',
        alignItems: 'flex-start',
      }}
    >
      {/* Left column — chat thread */}
      <div style={{ flex: 1, minWidth: 0, paddingRight: '24px' }}>
        <PersonaStrip
          personaId={session.personaId}
          openingQuery={session.openingQuery}
        />

        {hasFixtureMessages ? (
          replayDone ? (
            <div>
              {fixtureTurns.map((turn, i) => (
                <ChatTurnDisplay key={`fixture-${i}`} turn={turn} />
              ))}
            </div>
          ) : (
            <div>
              {timeline.slice(0, replayVisible).map((entry) => (
                <ReplayEntryDisplay key={entry.id} entry={entry} />
              ))}
            </div>
          )
        ) : (
          <EmptyState />
        )}

        {liveTurns.length > 0 && (
          <div>
            {liveTurns.map((turn, i) => (
              <ChatTurnDisplay key={`live-${i}`} turn={turn} />
            ))}
          </div>
        )}

        <ComposerBar
          suggestions={hintPills}
          onSend={handleFollowUp}
          busy={replyBusy}
          locked={composerLocked}
          error={replyError}
        />
      </div>

      <ContextRail>
        <LiveTraceRail
          steps={traceSteps}
          visibleCount={
            replayDone ? traceSteps.length : visibleTraceCount
          }
          emphasizeLatest={traceEmphasizeLatest}
        />
        <MemoryCard turns={displayTurns} />
        <AgentsCard />
        <SkillsCard />
      </ContextRail>
    </div>
  );
};

export default ChatTab;
