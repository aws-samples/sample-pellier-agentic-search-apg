/**
 * Routing — Three routing pattern cards surface.
 *
 * Displays Dispatcher, Agents-as-Tools, and Graph patterns as ExpCards.
 * Each card: pattern name (Fraunces), description, code snippet (monospace,
 * cream-2 bg), agent list as chips, active indicator (StatusDot + "Active"
 * pill for Dispatcher).
 *
 * Dispatcher is shown as active for boutique sessions.
 * Falls back to fixture data when unavailable.
 * Includes loading, error, and empty states.
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
 */

import React, { useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  ModeStrip,
  StatusDot,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { RoutingPattern } from '../../types';

/** Readable emphasis on cream cards — avoid browser bold (700) on sans/mono. */
const EMPHASIS: React.CSSProperties = {
  fontWeight: 500,
  color: 'var(--at-ink-1)',
};

/** Light mono callout for teaching copy on ExpCard (not dark `.dl-code-block`). */
const SNIPPET_STYLE: React.CSSProperties = {
  margin: 0,
  padding: '12px 14px',
  borderRadius: '8px',
  background: 'var(--at-cream-2)',
  border: '1px solid var(--at-card-border)',
  fontFamily: 'var(--at-mono)',
  fontSize: '13px',
  fontWeight: 400,
  lineHeight: 1.55,
  color: 'var(--at-ink-2)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const Emphasis: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={EMPHASIS}>{children}</span>
);

/* -----------------------------------------------------------------------
 * Active pill — custom pill for the active routing pattern.
 * StatusPill only supports shipped/exercise, so we render a custom one
 * matching the design system (sage green, like "Shipped" but labeled "Active").
 * ----------------------------------------------------------------------- */

const ActivePill: React.FC = () => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '3px 10px',
      borderRadius: '999px',
      backgroundColor: 'var(--at-status-shipped-bg)',
      color: 'var(--at-status-shipped-text)',
      fontFamily: 'var(--at-mono)',
      fontSize: '12px',
      fontWeight: 500,
      letterSpacing: '0.06em',
      textTransform: 'uppercase' as const,
      lineHeight: 1.4,
      whiteSpace: 'nowrap' as const,
    }}
  >
    Active
  </span>
);

/* -----------------------------------------------------------------------
 * Routing pattern card
 * ----------------------------------------------------------------------- */

const ROUTING_SCENARIOS: Array<{ label: string; hint: string }> = [
  {
    label: 'Marco · pairing',
    hint: 'Dispatcher classifies “goes with” → Style Advisor + find_pieces',
  },
  {
    label: 'Anna · gift search',
    hint: 'Hybrid retrieval + gift-table skill – latency-sensitive',
  },
  {
    label: 'Theo · return',
    hint: 'Write-path tools – Graph or Agents-as-Tools for multi-step audit',
  },
];

interface RoutingCardProps {
  pattern: RoutingPattern;
  numeral: string;
  isFocused: boolean;
  cardRef: (el: HTMLDivElement | null) => void;
  onFocus: () => void;
  scenarioHint?: string;
}

const RoutingCard: React.FC<RoutingCardProps> = ({
  pattern,
  numeral,
  isFocused,
  cardRef,
  onFocus,
  scenarioHint,
}) => {
  const isActive = pattern.isActive;

  return (
    <div
      ref={cardRef}
      role="button"
      tabIndex={0}
      aria-label={pattern.name}
      aria-pressed={isFocused}
      onClick={onFocus}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onFocus();
        }
      }}
      style={{
        cursor: 'pointer',
        outline: isFocused ? '2px solid var(--at-red-1)' : undefined,
        borderRadius: 'var(--at-card-radius)',
        boxShadow: isFocused ? '0 4px 20px rgba(31, 20, 16, 0.1)' : undefined,
      }}
    >
    <ExpCard>
      {/* Head: numeral + name + status */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: '18px',
          alignItems: 'flex-start',
          marginBottom: '14px',
        }}
      >
        {/* Identity: numeral + name */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '38px 1fr',
            gap: '14px',
            alignItems: 'baseline',
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--at-serif)',
              fontWeight: 400,
              fontSize: '30px',
              color: 'var(--at-red-1)',
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            {numeral}.
          </span>
          <h3
            style={{
              fontFamily: 'var(--at-serif)',
              fontWeight: 400,
              fontSize: '24px',
              letterSpacing: '-0.012em',
              lineHeight: 1.1,
              color: 'var(--at-ink-1)',
              margin: 0,
            }}
          >
            {pattern.name}
          </h3>
        </div>

        {/* Status: dot + pill for active pattern */}
        {isActive && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              flexShrink: 0,
              paddingTop: '6px',
            }}
          >
            <StatusDot status="live" />
            <ActivePill />
          </div>
        )}
      </div>

      {/* Description — Instrument Sans body prose, matching AtelierWelcome.
          The italic Fraunces pattern title above still carries the editorial voice. */}
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '15px',
          lineHeight: 1.6,
          color: 'var(--at-ink-2)',
          margin: '0 0 18px 0',
          maxWidth: '680px',
        }}
      >
        {pattern.description}
      </p>

      {/* Code snippet — light mono on cream (readable, regular weight) */}
      <pre style={{ ...SNIPPET_STYLE, marginBottom: '18px' }}>
        {pattern.codeSnippet}
      </pre>

      {/* Agent list + meta row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          alignItems: 'center',
          paddingTop: '14px',
          borderTop: '1px solid var(--at-card-border)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase' as const,
            color: 'var(--at-ink-2)',
            marginRight: '6px',
            fontWeight: 500,
          }}
        >
          Agents
        </span>
        {pattern.agents.map((agent) => (
          <span
            key={agent}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              padding: '3px 9px',
              background: 'var(--at-cream-2)',
              border: '1px solid var(--at-card-border)',
              borderRadius: '100px',
              color: 'var(--at-ink-1)',
              letterSpacing: '0.02em',
            }}
          >
            {agent}
          </span>
        ))}
      </div>

      {isFocused && scenarioHint && (
        <p
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '14px',
            lineHeight: 1.55,
            color: 'var(--at-ink-2)',
            marginTop: '14px',
            padding: '10px 12px',
            background: 'var(--at-cream-2)',
            borderRadius: '6px',
          }}
        >
          {scenarioHint}
        </p>
      )}
    </ExpCard>
    </div>
  );
};

/* -----------------------------------------------------------------------
 * Roman numeral helper
 * ----------------------------------------------------------------------- */

const ROMAN_NUMERALS = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'];

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', padding: '24px 0' }}>
    {Array.from({ length: 3 }, (_, i) => (
      <div
        key={i}
        style={{
          background: 'var(--at-cream-2)',
          borderRadius: 'var(--at-card-radius)',
          height: '260px',
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
      We couldn't load the routing patterns.
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
    <Eyebrow label="No patterns" variant="muted" />
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
      No routing patterns have been loaded.
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
      Check that the routing fixture data is available and try again.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Dispatcher Intent Map
 *
 * Active routing pattern (Pattern I · Dispatcher) is keyword-based,
 * deterministic, no LLM call. This card shows the literal keyword sets
 * from services/chat.py — "what do I type to land on which specialist?".
 * Workshop participants reading the dispatcher's intent classifier in
 * code will see the same shape here.
 * ----------------------------------------------------------------------- */

interface IntentMapping {
  intent: string;
  specialist: string;
  fileTokens: string[];
  examples: string[];
}

const INTENT_MAPPINGS: IntentMapping[] = [
  {
    intent: 'pricing',
    specialist: 'Value Analyst',
    fileTokens: [
      'deal', 'cheap', 'price', 'pricing', 'discount', 'affordable',
      'budget', 'value', 'cost', 'save', 'best price', 'on sale',
      'bargain', 'compare price',
    ],
    examples: ["What's the price range for linen shirts?"],
  },
  {
    intent: 'inventory',
    specialist: 'Stock Keeper',
    fileTokens: [
      'restock', 'inventory', 'stock', 'out of stock', 'low stock',
      'available', 'availability', 'in stock', 'running low',
      'sold out', 'back in stock', 'warehouse',
      'at the brooklyn', 'at the austin', 'at the portland',
      'on the floor',
    ],
    examples: ['Is the Hadley shirt at the Brooklyn warehouse?'],
  },
  {
    intent: 'customer_support',
    specialist: 'Experience Guide',
    fileTokens: [
      'return', 'refund', 'policy', 'troubleshoot', 'issue', 'problem',
      'warranty', 'broken', 'defective', 'chipped', 'damaged',
      'arrived', 'what now',
    ],
    examples: ['My Wabi-Sabi Bowl arrived chipped.'],
  },
  {
    intent: 'search',
    specialist: 'Style Advisor',
    fileTokens: [
      'search for', 'looking for', 'where can I', 'compare', 'browse',
      'what do you have', 'do you have', 'show me', 'find me',
    ],
    examples: ['What linen do you have for 10 days in Goa?'],
  },
  {
    intent: 'recommendation (default)',
    specialist: 'Curator',
    fileTokens: [
      "(any query that doesn't match the above falls through here)",
    ],
    examples: ['What would go with the Hadley shirt?'],
  },
];

const StorefrontProductionCard: React.FC = () => (
  <ExpCard>
    <Eyebrow label="Storefront production · e-commerce concierge" />
    <h3
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '24px',
        fontWeight: 400,
        margin: '6px 0 14px',
        color: 'var(--at-ink-1)',
      }}
    >
      Rules first, one specialist per turn.
    </h3>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        lineHeight: 1.65,
        color: 'var(--at-ink-2)',
        marginBottom: '14px',
      }}
    >
      High-traffic commerce assistants optimize for predictability, latency, and
      cost. Pellier&apos;s Boutique keeps{' '}
      <Emphasis>Dispatcher + specialists</Emphasis> on the hot path – not an LLM
      intent resolver at temperature&nbsp;0 (still drifts with model updates).
    </p>
    <ul
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        lineHeight: 1.65,
        color: 'var(--at-ink-2)',
        margin: '0 0 14px 0',
        paddingLeft: '20px',
      }}
    >
      <li>
        <Emphasis>Rules / classifier first</Emphasis> – triage + keyword intent
        before any Bedrock call
      </li>
      <li>
        <Emphasis>Single owning agent</Emphasis> per turn – Style Advisor, Stock
        Keeper, etc.
      </li>
      <li>
        <Emphasis>LLM router elsewhere</Emphasis> – Agents-as-Tools and Graph in
        the Atelier; AgentCore Runtime on{' '}
        <code
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            fontWeight: 400,
            padding: '1px 5px',
            borderRadius: '3px',
            background: 'var(--at-cream-2)',
          }}
        >
          /api/agent/chat
        </code>
      </li>
      <li>
        <Emphasis>Semantic tool discovery</Emphasis> at scale – Tools panel /
        Gateway – not the default router for Marco&apos;s five pills
      </li>
    </ul>
    <pre style={SNIPPET_STYLE}>
      {`triage (rules) → intent (rules) → low confidence? → classifier / Haiku T=0
                              → else → one specialist (one LLM call)`}
    </pre>
  </ExpCard>
);

const DispatcherIntentCard: React.FC = () => (
  <ExpCard>
    <Eyebrow label="Active dispatcher · intent → specialist" />
    <h3
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '24px',
        fontWeight: 400,
        margin: '6px 0 14px',
        color: 'var(--at-ink-1)',
      }}
    >
      What you type maps to one specialist.
    </h3>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        lineHeight: 1.6,
        color: 'var(--at-ink-2)',
        marginBottom: '20px',
      }}
    >
      The dispatcher is a keyword classifier in{' '}
      <code style={{ fontFamily: 'var(--at-mono)' }}>
        services/chat.py
      </code>{' '}
      (look for{' '}
      <code style={{ fontFamily: 'var(--at-mono)' }}>classify_intent</code>).
      It checks the customer's query against five sets of token phrases
      and dispatches to one specialist. No LLM call. Order of evaluation
      is intentional – pricing wins over inventory for ambiguous
      product-mention queries.
    </p>

    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontFamily: 'var(--at-sans)',
        fontSize: '13px',
      }}
    >
      <thead>
        <tr style={{ textAlign: 'left' as const, color: 'var(--at-ink-3)' }}>
          <th style={{ padding: '8px 10px', borderBottom: '1px solid var(--at-card-border)' }}>
            intent
          </th>
          <th style={{ padding: '8px 10px', borderBottom: '1px solid var(--at-card-border)' }}>
            specialist
          </th>
          <th style={{ padding: '8px 10px', borderBottom: '1px solid var(--at-card-border)' }}>
            example tokens
          </th>
          <th style={{ padding: '8px 10px', borderBottom: '1px solid var(--at-card-border)' }}>
            example query
          </th>
        </tr>
      </thead>
      <tbody>
        {INTENT_MAPPINGS.map((m) => (
          <tr key={m.intent}>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
                fontFamily: 'var(--at-mono)',
                color: 'var(--at-ink-1)',
                whiteSpace: 'nowrap' as const,
              }}
            >
              {m.intent}
            </td>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
                fontFamily: 'var(--at-serif)',
                color: 'var(--at-ink-1)',
                whiteSpace: 'nowrap' as const,
              }}
            >
              {m.specialist}
            </td>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap' as const,
                  gap: '4px',
                }}
              >
                {m.fileTokens.slice(0, 6).map((t) => (
                  <code
                    key={t}
                    style={{
                      fontFamily: 'var(--at-mono)',
                      fontSize: '12px',
                      background: 'var(--at-cream-2)',
                      padding: '2px 6px',
                      borderRadius: '3px',
                      color: 'var(--at-ink-2)',
                    }}
                  >
                    {t}
                  </code>
                ))}
                {m.fileTokens.length > 6 && (
                  <span
                    style={{
                      fontFamily: 'var(--at-mono)',
                      fontSize: '12px',
                      color: 'var(--at-ink-3)',
                    }}
                  >
                    +{m.fileTokens.length - 6} more
                  </span>
                )}
              </div>
            </td>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
                color: 'var(--at-ink-2)',
              }}
            >
              {m.examples[0]}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * LangGraph comparison card
 *
 * Pins the editorial difference between Strands' three patterns and
 * LangGraph's single-graph mental model. Operators arriving from a
 * LangChain/LangGraph background ask the same question every workshop:
 * "where's the graph?" — this card answers it without the surface
 * pretending the comparison is a feature toggle.
 * ----------------------------------------------------------------------- */

interface LangGraphMapping {
  pellier: string;
  langgraph: string;
  difference: string;
}

const LANGGRAPH_MAPPINGS: LangGraphMapping[] = [
  {
    pellier: 'Dispatcher (rules → specialist)',
    langgraph: 'Conditional edges from a router node',
    difference:
      'No graph object. The router is a Python function in services/chat.py – keyword rules, no LLM, ~60–120 ms.',
  },
  {
    pellier: 'Agents-as-Tools (orchestrator + @tool)',
    langgraph: 'Supervisor pattern with create_react_agent',
    difference:
      'Strands keeps specialists as @tool callables; the orchestrator is just an Agent. No StateGraph, no compile() step, no checkpointer wiring.',
  },
  {
    pellier: 'Graph (Strands GraphBuilder)',
    langgraph: 'StateGraph with add_node / add_edge',
    difference:
      'Closest analogue. Strands GraphBuilder is opt-in for multi-step ops; in LangGraph the graph is the default authoring surface from turn one.',
  },
];

const LangGraphComparisonCard: React.FC = () => (
  <ExpCard>
    <Eyebrow label="Coming from LangGraph · the editorial difference" />
    <h3
      style={{
        fontFamily: 'var(--at-serif)',
        fontSize: '24px',
        fontWeight: 400,
        margin: '6px 0 14px',
        color: 'var(--at-ink-1)',
      }}
    >
      Three patterns, not one graph.
    </h3>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '14px',
        lineHeight: 1.65,
        color: 'var(--at-ink-2)',
        marginBottom: '16px',
      }}
    >
      LangGraph asks you to{' '}
      <Emphasis>commit to a StateGraph from turn one</Emphasis> – every flow is
      nodes, edges, and a compiled state machine. Strands lets you start with{' '}
      <Emphasis>Dispatcher</Emphasis> (a Python function), graduate to{' '}
      <Emphasis>Agents-as-Tools</Emphasis> when one orchestrator needs to call
      specialists, and reach for <Emphasis>Graph</Emphasis> only when you
      genuinely need conditional multi-step topology. The patterns are
      progressive – you don&apos;t pay for a graph runtime until you actually
      need one.
    </p>

    <table
      data-testid="langgraph-comparison-table"
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontFamily: 'var(--at-sans)',
        fontSize: '13px',
        marginBottom: '16px',
      }}
    >
      <thead>
        <tr style={{ textAlign: 'left' as const, color: 'var(--at-ink-3)' }}>
          <th
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid var(--at-card-border)',
              width: '28%',
            }}
          >
            Pellier pattern
          </th>
          <th
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid var(--at-card-border)',
              width: '28%',
            }}
          >
            Closest LangGraph concept
          </th>
          <th
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid var(--at-card-border)',
            }}
          >
            Key difference
          </th>
        </tr>
      </thead>
      <tbody>
        {LANGGRAPH_MAPPINGS.map((row) => (
          <tr key={row.pellier} data-testid={`langgraph-row-${row.pellier.split(' ')[0].toLowerCase()}`}>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
                fontFamily: 'var(--at-serif)',
                color: 'var(--at-ink-1)',
                verticalAlign: 'top' as const,
              }}
            >
              {row.pellier}
            </td>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                color: 'var(--at-ink-2)',
                verticalAlign: 'top' as const,
              }}
            >
              {row.langgraph}
            </td>
            <td
              style={{
                padding: '10px',
                borderBottom: '1px solid var(--at-card-border)',
                color: 'var(--at-ink-2)',
                lineHeight: 1.5,
                verticalAlign: 'top' as const,
              }}
            >
              {row.difference}
            </td>
          </tr>
        ))}
      </tbody>
    </table>

    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '13px',
        lineHeight: 1.6,
        color: 'var(--at-ink-3)',
        margin: 0,
        paddingTop: '12px',
        borderTop: '1px solid var(--at-card-border)',
      }}
    >
      <Emphasis>When to reach for LangGraph instead:</Emphasis> long-running
      stateful workflows that need durable checkpointing, human-in-the-loop
      pause/resume, or cycle-heavy graphs (planner ↔ critic ↔ executor) where
      the topology itself is the design. Pellier&apos;s e-commerce concierge
      hot path is none of those – a keyword classifier plus one specialist
      call wins on latency every time.
    </p>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Routing: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<RoutingPattern[]>({
    key: 'routing',
  });

  const patterns = data ?? [];
  const activePattern = patterns.find((p) => p.isActive);
  const [focusedSlug, setFocusedSlug] = useState<string | null>(
    () => activePattern?.slug ?? patterns[0]?.slug ?? null,
  );
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const focusPattern = useCallback((slug: string) => {
    setFocusedSlug(slug);
    requestAnimationFrame(() => {
      cardRefs.current[slug]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, []);

  const scenarioHint = ROUTING_SCENARIOS[scenarioIdx]?.hint;

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Routing · three patterns"
        title="How requests find their specialist."
        summary={
          activePattern
            ? `Three orchestration strategies. ${activePattern.name} is the active pattern for boutique sessions – it classifies intent and dispatches to the best-fit specialist. The other two are alternative patterns you can explore.`
            : 'Three orchestration strategies for routing requests to specialist agents. Each pattern takes a different approach to intent classification and agent coordination.'
        }
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && patterns.length === 0 && <EmptyState />}

      {!loading && !error && patterns.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '18px',
          }}
        >
          <ExpCard>
            <Eyebrow label="Explore patterns" />
            <p
              style={{
                fontFamily: 'var(--at-sans)',
                fontSize: '15px',
                color: 'var(--at-ink-2)',
                lineHeight: 1.55,
                margin: '8px 0 14px',
              }}
            >
              Pick a pattern to compare orchestration styles. Boutique sessions use{' '}
              <Emphasis>Dispatcher</Emphasis> today – the others are alternatives you
              can trace in Observatory telemetry.
            </p>
            <ModeStrip
              patterns={patterns.map((p) => p.name)}
              active={patterns.find((p) => p.slug === focusedSlug)?.name ?? patterns[0].name}
              onSelect={(name) => {
                const p = patterns.find((x) => x.name === name);
                if (p) focusPattern(p.slug);
              }}
            />
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '8px',
                marginTop: '14px',
              }}
            >
              {ROUTING_SCENARIOS.map((sc, i) => (
                <button
                  key={sc.label}
                  type="button"
                  onClick={() => setScenarioIdx(i)}
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '12px',
                    padding: '5px 12px',
                    borderRadius: '999px',
                    border:
                      scenarioIdx === i
                        ? '1px solid var(--at-ink-1)'
                        : '1px solid var(--at-rule-2)',
                    background:
                      scenarioIdx === i ? 'var(--at-ink-1)' : 'var(--at-cream-2)',
                    color: scenarioIdx === i ? 'var(--at-cream-1)' : 'var(--at-ink-2)',
                    cursor: 'pointer',
                  }}
                >
                  {sc.label}
                </button>
              ))}
            </div>
          </ExpCard>

          {patterns.map((pattern, idx) => (
            <RoutingCard
              key={pattern.slug}
              pattern={pattern}
              numeral={ROMAN_NUMERALS[idx] ?? String(idx + 1)}
              isFocused={focusedSlug === pattern.slug}
              cardRef={(el) => {
                cardRefs.current[pattern.slug] = el;
              }}
              onFocus={() => focusPattern(pattern.slug)}
              scenarioHint={focusedSlug === pattern.slug ? scenarioHint : undefined}
            />
          ))}
          <StorefrontProductionCard />
          {/* Dispatcher (Pattern I) is the active path; the intent
              table makes the keyword-to-specialist mapping concrete. */}
          <DispatcherIntentCard />
          {/* LangGraph comparison — for operators arriving from LangChain.
              Pins the editorial difference: three progressive patterns vs
              one StateGraph from turn one. */}
          <LangGraphComparisonCard />
        </div>
      )}

      {/* Cross-link to the Architecture concept brief on Routing & State
          (where routing patterns live in the broader architecture). */}
      <div
        style={{
          marginTop: '32px',
          paddingTop: '20px',
          borderTop: '1px solid var(--at-card-border)',
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          color: 'var(--at-ink-2)',
        }}
      >
        <Link
          to="/atelier/architecture/state-management"
          style={{ color: 'var(--at-burgundy)', textDecoration: 'none' }}
        >
          → Read the architecture brief on Routing & State
        </Link>
      </div>
    </div>
  );
};

export default Routing;
