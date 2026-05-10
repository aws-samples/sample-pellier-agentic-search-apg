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

import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { ContextRail, ExpCard, Eyebrow, StatusDot } from '../../components';
import type { SessionOutletContext } from './SessionView';
import type {
  ChatTurn,
  ToolCall,
  ProductCard,
  PlanRow,
  ConfidenceRow,
  MemoryPill,
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
      <div
        key={i}
        style={{
          border: '1px solid var(--at-rule-1)',
          borderRadius: '10px',
          overflow: 'hidden',
          background: 'var(--at-cream-elev)',
        }}
      >
        {/* Image placeholder */}
        <div
          style={{
            height: '100px',
            background: 'linear-gradient(135deg, var(--at-cream-2) 0%, var(--at-cream-1) 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              color: 'var(--at-ink-2)',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
            }}
          >
            Image
          </span>
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
    ))}
  </div>
);

/* =======================================================================
 * Plan row
 * ======================================================================= */

const PlanRowDisplay: React.FC<{ plan: PlanRow }> = ({ plan }) => (
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
    {/* Routing pattern badge */}
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
 * Composer bar
 * ======================================================================= */

const ComposerBar: React.FC = () => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      padding: '12px 16px',
      background: 'var(--at-cream-elev)',
      border: '1px solid var(--at-rule-2)',
      borderRadius: '12px',
      marginTop: '24px',
    }}
  >
    {/* Sparkle icon */}
    <span style={{ fontSize: '17px', color: 'var(--at-red-1)', flexShrink: 0 }}>
      ✦
    </span>
    <span
      style={{
        flex: 1,
        fontFamily: 'var(--at-sans)',
        fontSize: '15px',
        color: 'var(--at-ink-2)',
      }}
    >
      Ask a follow-up question...
    </span>
    {/* Keyboard shortcut badge */}
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
      ⌘K
    </span>
    {/* Send button */}
    <button
      disabled
      aria-label="Send message"
      style={{
        width: '32px',
        height: '32px',
        borderRadius: '8px',
        border: 'none',
        backgroundColor: 'var(--at-ink-1)',
        color: 'var(--at-cream-1)',
        cursor: 'not-allowed',
        opacity: 0.4,
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
);

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

/** Skills card — style-advisor and gift-concierge with activation status */
const SKILLS_LIST = [
  { name: 'style-advisor', active: false },
  { name: 'gift-concierge', active: false },
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
  const chatTurns = session.chat ?? [];
  const hasMessages = chatTurns.length > 0;

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
        {/* Persona strip */}
        <PersonaStrip
          personaId={session.personaId}
          openingQuery={session.openingQuery}
        />

        {/* Chat messages or empty state */}
        {hasMessages ? (
          <div>
            {chatTurns.map((turn, i) => (
              <ChatTurnDisplay key={i} turn={turn} />
            ))}
          </div>
        ) : (
          <EmptyState />
        )}

        {/* Composer bar */}
        <ComposerBar />
      </div>

      {/* Right column — context rail */}
      <ContextRail>
        <MemoryCard turns={chatTurns} />
        <AgentsCard />
        <SkillsCard />
      </ContextRail>
    </div>
  );
};

export default ChatTab;
