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

import React, { useMemo, useState } from 'react';
import ResolutionTrace, { traceStatus } from '../../../shared/trace/ResolutionTrace';
import { Link, useOutletContext } from 'react-router-dom';
import { ContextRail, ExpCard, Eyebrow, StatusDot } from '../../components';
import { resolveProductImageUrl } from '../../../utils/resolveProductImageUrl';
import type { SessionOutletContext } from './SessionView';
import type {
  ChatTurn,
  ToolCall,
  ProductCard,
  PlanRow,
  ConfidenceRow,
  MemoryPill,
  SessionDetail,
  TelemetryPanel,
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

const DARK_CODE_BLOCK: React.CSSProperties = {
  fontFamily: 'var(--obs-mono)',
  fontSize: '12px',
  lineHeight: 1.6,
  background: 'var(--dl-ink)',
  color: 'var(--dl-accent-soft)',
  borderRadius: 'var(--dl-r-lg)',
  border: '1px solid color-mix(in srgb, var(--dl-accent-soft) 18%, transparent)',
  padding: '14px 16px',
  overflow: 'auto',
  margin: 0,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

function highlightSQL(sql: string): React.ReactNode[] {
  // Split on word boundaries while preserving whitespace and symbols
  const tokens = sql.split(/(\b\w+\b)/g);
  return tokens.map((token, i) => {
    if (SQL_KEYWORDS.has(token.toUpperCase())) {
      return (
        <span key={i} style={{ color: '#f7c873', fontWeight: 600 }}>
          {token}
        </span>
      );
    }
    if (/^'.*'$/.test(token) || token.includes('%')) {
      return (
        <span key={i} style={{ color: '#e8927c' }}>
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
}> = ({ personaId, openingQuery }) => {
  // This strip is intentionally limited to durable Aurora session fields.
  const name = personaId.charAt(0).toUpperCase() + personaId.slice(1);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
        padding: '16px 20px',
        background: 'var(--obs-cream-2)',
        borderRadius: 'var(--obs-card-radius)',
        marginBottom: '24px',
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          backgroundColor: 'var(--obs-red-1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--obs-cream-1)',
          fontFamily: 'var(--obs-sans)',
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
            fontFamily: 'var(--obs-sans)',
            fontSize: '17px',
            color: 'var(--obs-ink-1)',
            lineHeight: 1.3,
          }}
        >
          {name}
        </div>
        <div
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            color: 'var(--obs-ink-2)',
            marginTop: '2px',
          }}
        >
          Aurora-recorded shopper session · CUST-{personaId.toUpperCase()}
        </div>
        <div
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            color: 'var(--obs-ink-2)',
            marginTop: '5px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={openingQuery}
        >
          {openingQuery}
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
        border: '1px solid var(--obs-rule-2)',
        borderRadius: '10px',
        overflow: 'hidden',
        marginBottom: '8px',
      }}
    >
      {/* Collapsed header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} ${tool.toolName} tool call`}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          width: '100%',
          padding: '10px 14px',
          background: 'var(--obs-cream-elev)',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--obs-ink-1)',
          }}
        >
          {tool.toolName}
        </span>
        <span
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '14px',
            color: 'var(--obs-ink-1)',
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
            fontFamily: 'var(--obs-mono)',
            fontSize: '12px',
            color: 'var(--obs-ink-2)',
            whiteSpace: 'nowrap',
          }}
        >
          {tool.durationMs}ms
        </span>
        <span
          style={{
            fontSize: '12px',
            color: 'var(--obs-ink-2)',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s ease',
          }}
        >
          ▼
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div style={{ padding: '12px 14px', borderTop: '1px solid var(--obs-rule-1)' }}>
          {tool.sql && (
            <pre
              style={{
                ...DARK_CODE_BLOCK,
                marginBottom: tool.subSteps?.length || tool.writes?.length || tool.resultSummary ? '10px' : 0,
              }}
            >
              <span style={{ color: '#8a8270' }}>-- {tool.toolName}</span>
              {'\n'}
              {highlightSQL(tool.sql)}
            </pre>
          )}
          {tool.subSteps && tool.subSteps.length > 0 && (
            <div style={{ display: 'grid', gap: '8px', marginBottom: tool.writes?.length || tool.resultSummary ? '10px' : 0 }}>
              {tool.subSteps.map((step) => (
                <div
                  key={step.label}
                  style={{
                    border: '1px solid var(--obs-rule-1)',
                    borderRadius: '8px',
                    background: 'var(--obs-cream-2)',
                    padding: '10px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: '12px',
                      marginBottom: step.sql ? '8px' : 0,
                      fontFamily: 'var(--obs-mono)',
                      fontSize: '11px',
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      color: 'var(--obs-ink-2)',
                    }}
                  >
                    <span>{step.label}</span>
                    <span>{step.durationMs}ms</span>
                  </div>
                  {step.sql && (
                    <pre
                      style={{
                        ...DARK_CODE_BLOCK,
                        fontSize: '12px',
                      }}
                    >
                      <span style={{ color: '#8a8270' }}>-- {step.label}</span>
                      {'\n'}
                      {highlightSQL(step.sql)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
          {tool.writes && tool.writes.length > 0 && (
            <div style={{ display: 'grid', gap: '8px', marginBottom: tool.resultSummary ? '10px' : 0 }}>
              {tool.writes.map((write, index) => (
                <div
                  key={`${write.table}-${write.operation}-${write.rowId}-${index}`}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'auto 1fr auto',
                    gap: '10px',
                    alignItems: 'center',
                    padding: '8px 10px',
                    borderRadius: '8px',
                    background: 'var(--obs-cream-2)',
                    border: '1px solid var(--obs-rule-1)',
                    fontFamily: 'var(--obs-mono)',
                    fontSize: '12px',
                    color: 'var(--obs-ink-2)',
                  }}
                >
                  <span style={{ color: 'var(--obs-red-1)', fontWeight: 600 }}>
                    {write.operation}
                  </span>
                  <span>
                    {write.table}
                    {write.field ? `.${write.field}` : ''}
                    {write.before !== undefined && write.after !== undefined
                      ? ` ${write.before} \u2192 ${write.after}`
                      : ''}
                  </span>
                  <span>#{write.rowId}</span>
                </div>
              ))}
            </div>
          )}
          {tool.resultSummary && (
            <p
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '15px',
                color: 'var(--obs-ink-1)',
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
        border: '1px solid var(--obs-rule-1)',
        borderRadius: '10px',
        overflow: 'hidden',
        background: 'var(--obs-cream-elev)',
      }}
    >
      <div
        style={{
          height: '100px',
          borderRadius: 'var(--pellier-image-radius-md)',
          background: 'var(--obs-cream-2)',
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
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                color: 'var(--obs-ink-4)',
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
            fontFamily: 'var(--obs-mono)',
            fontSize: '11px',
            color: 'var(--obs-ink-2)',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            marginBottom: '4px',
          }}
        >
          {product.brand}
        </div>
        <div
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '15px',
            color: 'var(--obs-ink-1)',
            lineHeight: 1.3,
            marginBottom: '6px',
          }}
        >
          {product.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '13px',
            color: 'var(--obs-ink-2)',
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

const PlanRowDisplay: React.FC<{ plan: PlanRow; sessionId: string }> = ({
  plan: rawPlan,
  sessionId,
}) => {
  const plan = normalizePlanRow(rawPlan);
  const traceTarget = plan.traceLink
    ? `/observatory/sessions/${sessionId}/telemetry${plan.traceLink.startsWith('#') ? plan.traceLink : `#${plan.traceLink}`}`
    : undefined;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '8px 14px',
        background: 'var(--obs-cream-2)',
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
          backgroundColor: 'var(--obs-red-soft)',
          color: 'var(--obs-red-1)',
          fontFamily: 'var(--obs-mono)',
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
          fontFamily: 'var(--obs-mono)',
          fontSize: '13px',
          color: 'var(--obs-ink-1)',
        }}
      >
        {plan.stepCount} steps
      </span>
      <span
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '15px',
          color: 'var(--obs-ink-2)',
          flex: 1,
        }}
      >
        {plan.flowSummary}
      </span>
      {traceTarget && (
        <Link
          to={traceTarget}
          style={{
            fontFamily: 'var(--obs-mono)',
            fontSize: '12px',
            color: 'var(--obs-red-1)',
            textDecoration: 'none',
            whiteSpace: 'nowrap',
          }}
        >
          view trace →
        </Link>
      )}
    </div>
  );
};

/* =======================================================================
 * Evidence row
 * ======================================================================= */

const EvidenceDisplay: React.FC<{ confidence: ConfidenceRow }> = ({
  confidence,
}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: '12px',
      padding: '10px 14px',
      background: 'var(--obs-cream-2)',
      border: '1px solid var(--obs-card-border)',
      borderRadius: '8px',
      marginTop: '8px',
    }}
  >
    <span
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        fontWeight: 600,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color: 'var(--obs-green-1)',
        whiteSpace: 'nowrap',
        paddingTop: '3px',
      }}
    >
      Evidence
    </span>
    <span
      style={{
        fontFamily: 'var(--obs-sans)',
        fontSize: '14px',
        color: 'var(--obs-ink-2)',
        lineHeight: 1.5,
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
      border: '1.5px dashed var(--obs-card-border)',
      fontFamily: 'var(--obs-sans)',
      fontSize: '14px',
      color: 'var(--obs-ink-2)',
      lineHeight: 1.4,
    }}
  >
    <span
      style={{
        fontFamily: 'var(--obs-mono)',
        fontSize: '11px',
        fontWeight: 500,
        textTransform: 'uppercase',
        letterSpacing: '0.18em',
        color: 'var(--obs-ink-1)',
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

const ChatTurnDisplay: React.FC<{ turn: ChatTurn; sessionId: string }> = ({
  turn,
  sessionId,
}) => {
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
            backgroundColor: 'var(--obs-ink-1)',
            color: 'var(--obs-cream-1)',
            borderRadius: '14px',
            fontFamily: 'var(--obs-sans)',
            fontSize: '16px',
            lineHeight: 'var(--obs-body-leading)',
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
      {turn.plan && <PlanRowDisplay plan={turn.plan} sessionId={sessionId} />}

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
          fontFamily: 'var(--obs-sans)',
          fontSize: '16px',
          lineHeight: 'var(--obs-body-leading)',
          color: 'var(--obs-ink-1)',
          maxWidth: '85%',
        }}
      >
        {turn.content}
      </div>

      {/* Product recommendations */}
      {turn.products && turn.products.length > 0 && (
        <ProductGrid products={turn.products} />
      )}

      {/* Evidence */}
      {turn.confidence && <EvidenceDisplay confidence={turn.confidence} />}

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
 * Synced replay timeline (chat column + trace rail)
 * ======================================================================= */

/* =======================================================================
 * Evidence-only replay guidance and empty state
 * ======================================================================= */

const ReplayOnlyNotice: React.FC = () => (
  <aside
    style={{
      marginTop: '24px',
      padding: '14px 16px',
      border: '1px solid var(--obs-rule-2)',
      borderRadius: '10px',
      background: 'var(--obs-cream-2)',
      color: 'var(--obs-ink-2)',
      fontFamily: 'var(--obs-sans)',
      fontSize: '14px',
      lineHeight: 1.55,
    }}
  >
    This is a durable Aurora replay. Run a new request in the{' '}
    <Link to="/observatory/workbench" style={{ color: 'var(--obs-burgundy)' }}>
      Labs & Workbench
    </Link>{' '}
    or storefront to create fresh evidence.
  </aside>
);

const EmptyState: React.FC = () => {
  const suggestions: string[] = [];

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
          fontFamily: 'var(--obs-sans)',
          fontSize: '22px',
          color: 'var(--obs-ink-1)',
          marginTop: '16px',
          marginBottom: '20px',
        }}
      >
        No recorded conversation
      </p>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
        {suggestions.map((s) => (
          <span
            key={s}
            style={{
              padding: '6px 14px',
              borderRadius: '999px',
              border: '1px solid var(--obs-rule-2)',
              fontFamily: 'var(--obs-sans)',
              fontSize: '15px',
              color: 'var(--obs-ink-2)',
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
  phase?: string;
  provenance?: string;
  status?: string;
};

function collectLiveTraceSteps(
  turns: ChatTurn[],
  telemetry: TelemetryPanel[],
): LiveTraceStep[] {
  const out: LiveTraceStep[] = [];
  turns.forEach((turn, ti) => {
    if (turn.role !== 'assistant') return;
    if (turn.plan) {
      const np = normalizePlanRow(turn.plan);
      out.push({
        id: `t${ti}-plan`,
        title: np.routingPattern,
        subtitle: `${np.stepCount} steps · ${np.flowSummary}`,
        phase: 'routing',
        status: 'recorded',
      });
    }
    (turn.toolCalls ?? []).forEach((tool, j) => {
      out.push({
        id: `t${ti}-tool-${j}`,
        title: tool.toolName,
        subtitle: tool.description,
        durationMs: tool.durationMs,
        phase: 'execution',
        status: 'recorded',
      });
    });
  });

  if (out.length > 0) return out;

  return telemetry.map((panel) => ({
    id: `telemetry-${panel.index}`,
    title: panel.title,
    subtitle: panel.description,
    durationMs: panel.durationMs,
    phase: panel.phase,
    provenance: panel.provenance,
    status: panel.status,
  }));
}

type RecordedMemoryItem = {
  id: string;
  label: string;
  detail: string;
  source: string;
};

function recordedMemoryItems(session: SessionDetail): RecordedMemoryItem[] {
  const pills = session.chat.flatMap((turn, turnIndex) =>
    (turn.memoryPills ?? []).map((pill, pillIndex) => ({
      id: `pill-${turnIndex}-${pillIndex}`,
      label: pill.tier,
      detail: pill.content,
      source: 'recorded conversation',
    })),
  );
  const events = session.telemetry
    .filter((panel) => panel.eventKind === 'memory')
    .map((panel) => ({
      id: `memory-event-${panel.index}`,
      label: panel.title,
      detail: panel.description,
      source: panel.provenance?.replace(/-/g, ' ') ?? 'recorded telemetry',
    }));
  return [...pills, ...events];
}

const MemoryCard: React.FC<{ session: SessionDetail }> = ({ session }) => {
  const items = recordedMemoryItems(session);

  return (
    <ExpCard className="observatory-session-context-card">
      <div className="observatory-session-card-heading">
        <Eyebrow label="Memory" />
        <Link
          to="/observatory/architecture/memory"
          className="observatory-session-card-link"
        >
          Memory architecture
        </Link>
      </div>
      {items.length === 0 ? (
        <p className="observatory-session-empty-evidence">
          No durable memory event is attached to this replay.
        </p>
      ) : (
        <div className="observatory-session-evidence-list">
          {items.map((item) => (
            <div key={item.id}>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
              <span>{item.source}</span>
            </div>
          ))}
        </div>
      )}
    </ExpCard>
  );
};

function displayAgentName(agent: string, routingPattern: string): string {
  if (agent === 'agent') {
    return routingPattern.toLowerCase().includes('gateway')
      ? 'Managed gateway agent'
      : 'Storefront agent';
  }
  if (agent === 'gateway') return 'AgentCore Gateway';
  return agent
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function recordedAgents(session: SessionDetail): string[] {
  const agents = new Set<string>();
  session.chat.forEach((turn) => {
    if (turn.meta?.agent) agents.add(turn.meta.agent);
  });
  session.telemetry.forEach((panel) => {
    if (panel.agent) agents.add(panel.agent);
  });
  return [...agents].map((agent) =>
    displayAgentName(agent, session.routingPattern),
  );
}

const AgentsCard: React.FC<{ session: SessionDetail }> = ({ session }) => {
  const agents = recordedAgents(session);
  return (
    <ExpCard className="observatory-session-context-card">
      <div className="observatory-session-card-heading">
        <Eyebrow label="Agents" />
        <span>{agents.length} observed</span>
      </div>
      {agents.length === 0 ? (
        <p className="observatory-session-empty-evidence">
          No agent attribution was recorded for this session.
        </p>
      ) : (
        <div className="observatory-session-agent-list">
          {agents.map((agent) => (
            <div key={agent}>
              <StatusDot status="live" size={8} />
              <span>{agent}</span>
              <small>Recorded</small>
            </div>
          ))}
        </div>
      )}
    </ExpCard>
  );
};

/** Skills card — prompt overlays (`skills.json` bundles) */
const SKILLS_LIST = [
  'the-packing-list',
  'the-gift-table',
  'the-makers-shelf',
  'the-care-card',
  'the-proof-counter',
];

function activeSkillsForSession(session: SessionDetail): Set<string> {
  const active = new Set<string>();
  for (const turn of session.chat) {
    if (turn.meta?.skill) active.add(turn.meta.skill);
    for (const pill of turn.memoryPills ?? []) {
      for (const skill of SKILLS_LIST) {
        if (pill.content.includes(skill)) active.add(skill);
      }
    }
  }
  for (const panel of session.telemetry) {
    const text = `${panel.title} ${panel.description} ${panel.agent ?? ''}`;
    for (const skill of SKILLS_LIST) {
      if (text.includes(skill)) active.add(skill);
    }
  }
  return active;
}

const SkillsCard: React.FC<{ session: SessionDetail }> = ({ session }) => {
  const activeSkills = activeSkillsForSession(session);

  return (
    <ExpCard className="observatory-session-context-card">
      <div className="observatory-session-card-heading">
        <Eyebrow label="Skills" />
        <span>{activeSkills.size} recorded</span>
      </div>
      {activeSkills.size === 0 ? (
        <p className="observatory-session-empty-evidence">
          No runtime skill overlay was recorded for this session.
        </p>
      ) : (
        <div className="observatory-session-agent-list">
          {[...activeSkills].map((skill) => (
            <div key={skill}>
              <StatusDot status="live" size={8} />
              <span className="observatory-session-skill-name">{skill}</span>
              <small>Recorded</small>
            </div>
          ))}
        </div>
      )}
    </ExpCard>
  );
};

/* =======================================================================
 * Main ChatTab component
 * ======================================================================= */

const ChatTab: React.FC = () => {
  const { session, replayNonce } = useOutletContext<SessionOutletContext>();
  return <RecordedTurn key={`${session.id}:${replayNonce}`} session={session} />;
};

function RecordedTurn({ session }: { session: SessionDetail }) {
  const recordedTurns = session.chat ?? [];
  const traceSteps = useMemo(() => collectLiveTraceSteps(recordedTurns, session.telemetry ?? []).map(step => ({
    id: step.id, title: step.title, summary: step.subtitle,
    status: traceStatus(step.status), durationMs: step.durationMs,
    source: step.provenance?.replace(/-/g, ' '),
    detail: [step.phase, step.status?.replace(/_/g, ' ')].filter(Boolean).join(' · '),
  })), [recordedTurns, session.telemetry]);
  const [replayDone, setReplayDone] = useState(false);
  return (
    <div className="observatory-session-replay-layout">
      <div className="observatory-session-replay-main">
        <PersonaStrip personaId={session.personaId} openingQuery={session.openingQuery} />
        {traceSteps.length > 0 && <ResolutionTrace
          title="Shopper turn trace" mode="recorded" autoPlay steps={traceSteps}
          request={session.openingQuery} recordingKey={session.id}
          recordingLabel="Recorded application events from this Aurora session."
          onReplayComplete={() => setReplayDone(true)}
          outcome={{ label: 'Evidence ready to inspect', status: 'unknown', body: `${traceSteps.length} recorded evidence events ready to inspect` }}
        />}
        {recordedTurns.length > 0 ? (
          <details className="observatory-recorded-transcript" open={traceSteps.length === 0 || replayDone}>
            <summary>Recorded conversation</summary>
            {recordedTurns.map((turn, i) => <ChatTurnDisplay key={`recorded-${i}`} turn={turn} sessionId={session.id} />)}
          </details>
        ) : traceSteps.length === 0 ? <EmptyState /> : null}
        <ReplayOnlyNotice />
      </div>
      <ContextRail>
        <MemoryCard session={session} />
        <AgentsCard session={session} />
        <SkillsCard session={session} />
      </ContextRail>
    </div>
  );
}

export default ChatTab;
