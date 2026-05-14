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

import React from 'react';
import { Link } from 'react-router-dom';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  StatusDot,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { RoutingPattern } from '../../types';

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

interface RoutingCardProps {
  pattern: RoutingPattern;
  numeral: string;
}

const RoutingCard: React.FC<RoutingCardProps> = ({ pattern, numeral }) => {
  const isActive = pattern.isActive;

  return (
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
              fontStyle: 'italic',
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

      {/* Description — sans Inter for body prose, matches the
          AtelierWelcome summary treatment. The italic Fraunces
          pattern title above still carries the editorial voice. */}
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

      {/* Code snippet */}
      <pre
        className="dl-code-block"
        style={{
          marginBottom: '18px',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
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
    </ExpCard>
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
        fontStyle: 'italic',
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
        fontStyle: 'italic',
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
 * Active routing pattern (Pattern III · Dispatcher) is keyword-based,
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
      is intentional — pricing wins over inventory for ambiguous
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
                fontStyle: 'italic' as const,
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
 * Main component
 * ----------------------------------------------------------------------- */

const Routing: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<RoutingPattern[]>({
    key: 'routing',
  });

  const patterns = data ?? [];
  const activePattern = patterns.find((p) => p.isActive);

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Routing · three patterns"
        title="How requests find their specialist."
        summary={
          activePattern
            ? `Three orchestration strategies. ${activePattern.name} is the active pattern for boutique sessions — it classifies intent and dispatches to the best-fit specialist. The other two are alternative patterns you can explore.`
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
          {patterns.map((pattern, idx) => (
            <RoutingCard
              key={pattern.slug}
              pattern={pattern}
              numeral={ROMAN_NUMERALS[idx] ?? String(idx + 1)}
            />
          ))}
          {/* Dispatcher (Pattern III) is the active path; the intent
              table makes the keyword-to-specialist mapping concrete. */}
          <DispatcherIntentCard />
        </div>
      )}

      {/* Cross-link to the Architecture concept brief on State Management
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
          → Read the architecture brief on State Management
        </Link>
      </div>
    </div>
  );
};

export default Routing;
