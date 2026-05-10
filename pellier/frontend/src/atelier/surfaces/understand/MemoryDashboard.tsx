/**
 * MemoryDashboard — STM + LTM tiers for the active persona.
 *
 * Displays short-term and long-term memory state with an orbit
 * visualization showing the persona at center, STM items on an inner
 * ring, and LTM items on an outer ring with labeled connector dots.
 *
 * Includes loading, error, and empty states.
 *
 * Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
 */

import React from 'react';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { MemoryState, MemoryItem } from '../../types';

/* -----------------------------------------------------------------------
 * Orbit Visualization — SVG with persona at center, STM inner ring,
 * LTM outer ring, labeled connector dots/lines.
 * ----------------------------------------------------------------------- */

interface OrbitVisualizationProps {
  persona: string;
  stmItems: MemoryItem[];
  ltmItems: MemoryItem[];
}

const OrbitVisualization: React.FC<OrbitVisualizationProps> = ({
  persona,
  stmItems,
  ltmItems,
}) => {
  const cx = 300;
  const cy = 300;
  const stmRadius = 120;
  const ltmRadius = 230;
  const viewBox = '0 0 600 600';

  /** Place items evenly around a ring, returning (x, y) for each. */
  function ringPositions(count: number, radius: number): { x: number; y: number }[] {
    if (count === 0) return [];
    return Array.from({ length: count }, (_, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      return {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    });
  }

  const stmPositions = ringPositions(stmItems.length, stmRadius);
  const ltmPositions = ringPositions(ltmItems.length, ltmRadius);

  /** Truncate label to fit in the visualization. */
  function truncate(text: string, max: number): string {
    return text.length > max ? text.slice(0, max - 1) + '\u2026' : text;
  }

  return (
    <svg
      viewBox={viewBox}
      width="100%"
      style={{ maxWidth: '800px', display: 'block', margin: '0 auto' }}
      role="img"
      aria-label={`Memory orbit for ${persona}: ${stmItems.length} short-term items, ${ltmItems.length} long-term items`}
    >
      {/* Orbit rings */}
      <circle
        cx={cx}
        cy={cy}
        r={ltmRadius}
        fill="none"
        stroke="var(--at-rule-1)"
        strokeWidth="1"
        strokeDasharray="6 4"
        opacity={0.5}
      />
      <circle
        cx={cx}
        cy={cy}
        r={stmRadius}
        fill="none"
        stroke="var(--at-rule-2)"
        strokeWidth="1"
        strokeDasharray="4 3"
        opacity={0.6}
      />

      {/* Connector lines — LTM */}
      {ltmPositions.map((pos, i) => (
        <line
          key={`ltm-line-${ltmItems[i].id}`}
          x1={cx}
          y1={cy}
          x2={pos.x}
          y2={pos.y}
          stroke="var(--at-rule-1)"
          strokeWidth="0.5"
          opacity={0.25}
        />
      ))}

      {/* Connector lines — STM */}
      {stmPositions.map((pos, i) => (
        <line
          key={`stm-line-${stmItems[i].id}`}
          x1={cx}
          y1={cy}
          x2={pos.x}
          y2={pos.y}
          stroke="var(--at-red-1)"
          strokeWidth="0.5"
          opacity={0.3}
        />
      ))}

      {/* LTM dots + labels */}
      {ltmPositions.map((pos, i) => {
        const item = ltmItems[i];
        return (
          <g key={`ltm-${item.id}`}>
            <circle
              cx={pos.x}
              cy={pos.y}
              r={6}
              fill="var(--at-cream-2)"
              stroke="var(--at-ink-1)"
              strokeWidth="1.5"
            />
            <text
              x={pos.x}
              y={pos.y + 18}
              textAnchor="middle"
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                fill: 'var(--at-ink-1)',
                letterSpacing: '0.04em',
              }}
            >
              {truncate(item.content, 32)}
            </text>
          </g>
        );
      })}

      {/* STM dots + labels */}
      {stmPositions.map((pos, i) => {
        const item = stmItems[i];
        return (
          <g key={`stm-${item.id}`}>
            <circle
              cx={pos.x}
              cy={pos.y}
              r={5}
              fill="var(--at-red-1)"
              opacity={0.85}
            />
            <text
              x={pos.x}
              y={pos.y + 16}
              textAnchor="middle"
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '12px',
                fill: 'var(--at-ink-2)',
                letterSpacing: '0.04em',
              }}
            >
              {truncate(item.content, 28)}
            </text>
          </g>
        );
      })}

      {/* Persona center circle */}
      <circle
        cx={cx}
        cy={cy}
        r={32}
        fill="var(--at-ink-1)"
      />
      <text
        x={cx}
        y={cy + 1}
        textAnchor="middle"
        dominantBaseline="central"
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '20px',
          fill: 'var(--at-cream-1)',
          letterSpacing: '-0.02em',
        }}
      >
        {persona.charAt(0).toUpperCase()}
      </text>
      <text
        x={cx}
        y={cy + 50}
        textAnchor="middle"
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          fill: 'var(--at-ink-2)',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        {persona}
      </text>

      {/* Ring labels */}
      <text
        x={cx}
        y={cy - stmRadius - 10}
        textAnchor="middle"
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          fill: 'var(--at-red-1)',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        STM
      </text>
      <text
        x={cx}
        y={cy - ltmRadius - 10}
        textAnchor="middle"
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '13px',
          fill: 'var(--at-ink-2)',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        LTM
      </text>
    </svg>
  );
};

/* -----------------------------------------------------------------------
 * STM Tier Card
 * ----------------------------------------------------------------------- */

interface StmCardProps {
  turnCount: number;
  recentIntents: string[];
  items: MemoryItem[];
}

const StmCard: React.FC<StmCardProps> = ({ turnCount, recentIntents, items }) => (
  <ExpCard>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
      <span
        style={{
          display: 'inline-block',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: 'var(--at-red-1)',
          flexShrink: 0,
        }}
      />
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-red-1)',
          fontWeight: 500,
        }}
      >
        Short-Term Memory
      </span>
    </div>

    <h3
      style={{
        fontFamily: 'var(--at-serif)',
        fontWeight: 400,
        fontSize: '24px',
        letterSpacing: '-0.012em',
        lineHeight: 1.15,
        color: 'var(--at-ink-1)',
        margin: '0 0 6px 0',
      }}
    >
      Session context
    </h3>
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '16px',
        color: 'var(--at-ink-1)',
        lineHeight: 1.5,
        margin: '0 0 20px 0',
      }}
    >
      Ephemeral, session-scoped conversation state managed by AgentCore.
    </p>

    {/* Turn count */}
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: '10px',
        marginBottom: '18px',
        paddingBottom: '14px',
        borderBottom: '1px solid var(--at-card-border)',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--at-serif)',
          fontSize: '42px',
          fontWeight: 400,
          color: 'var(--at-ink-1)',
          letterSpacing: '-0.02em',
          lineHeight: 1,
        }}
      >
        {turnCount}
      </span>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '12px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-ink-2)',
        }}
      >
        turns this session
      </span>
    </div>

    {/* Recent intents */}
    <div style={{ marginBottom: '18px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-ink-2)',
          fontWeight: 500,
          display: 'block',
          marginBottom: '8px',
        }}
      >
        Recent intents
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
        {recentIntents.map((intent, idx) => (
          <div
            key={idx}
            style={{
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
              fontSize: '16px',
              lineHeight: 1.45,
              color: 'var(--at-ink-2)',
              paddingLeft: '14px',
              borderLeft: '2px solid var(--at-red-1)',
            }}
          >
            {intent}
          </div>
        ))}
      </div>
    </div>

    {/* Memory items */}
    {items.length > 0 && (
      <div>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase' as const,
            color: 'var(--at-ink-2)',
            fontWeight: 500,
            display: 'block',
            marginBottom: '8px',
          }}
        >
          Fresh items
        </span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {items.map((item) => (
            <span
              key={item.id}
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '13px',
                padding: '4px 10px',
                background: 'var(--at-cream-2)',
                border: '1px dashed var(--at-red-1)',
                borderRadius: '100px',
                color: 'var(--at-ink-2)',
                letterSpacing: '0.02em',
                maxWidth: '100%',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap' as const,
              }}
            >
              {item.content}
            </span>
          ))}
        </div>
      </div>
    )}
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * LTM Tier Card
 * ----------------------------------------------------------------------- */

interface LtmCardProps {
  preferences: string[];
  priorOrders: string[];
  behavioralPatterns: string[];
  items: MemoryItem[];
}

const LtmCard: React.FC<LtmCardProps> = ({
  preferences,
  priorOrders,
  behavioralPatterns,
  items,
}) => (
  <ExpCard>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
      <span
        style={{
          display: 'inline-block',
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          border: '2px solid var(--at-ink-1)',
          backgroundColor: 'transparent',
          flexShrink: 0,
        }}
      />
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
        Long-Term Memory
      </span>
    </div>

    <h3
      style={{
        fontFamily: 'var(--at-serif)',
        fontWeight: 400,
        fontSize: '24px',
        letterSpacing: '-0.012em',
        lineHeight: 1.15,
        color: 'var(--at-ink-1)',
        margin: '0 0 6px 0',
      }}
    >
      Semantic recall
    </h3>
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '16px',
        color: 'var(--at-ink-1)',
        lineHeight: 1.5,
        margin: '0 0 20px 0',
      }}
    >
      Persistent memory stored in Aurora pgvector — preferences, order history, and behavioral
      patterns recalled via semantic similarity.
    </p>

    {/* Preferences */}
    <div style={{ marginBottom: '16px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-ink-2)',
          fontWeight: 500,
          display: 'block',
          marginBottom: '8px',
        }}
      >
        Stored preferences
      </span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {preferences.map((pref) => (
          <span
            key={pref}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              padding: '3px 10px',
              background: 'var(--at-cream-2)',
              border: '1px solid var(--at-card-border)',
              borderRadius: '100px',
              color: 'var(--at-ink-1)',
              letterSpacing: '0.02em',
            }}
          >
            {pref}
          </span>
        ))}
      </div>
    </div>

    {/* Prior orders */}
    <div style={{ marginBottom: '16px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-ink-2)',
          fontWeight: 500,
          display: 'block',
          marginBottom: '8px',
        }}
      >
        Prior orders
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {priorOrders.map((order, idx) => (
          <div
            key={idx}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '13px',
              lineHeight: 1.5,
              color: 'var(--at-ink-2)',
              paddingLeft: '14px',
              borderLeft: '2px solid var(--at-ink-4)',
            }}
          >
            {order}
          </div>
        ))}
      </div>
    </div>

    {/* Behavioral patterns */}
    <div
      style={{
        marginBottom: '16px',
        paddingBottom: '16px',
        borderBottom: '1px solid var(--at-card-border)',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase' as const,
          color: 'var(--at-ink-2)',
          fontWeight: 500,
          display: 'block',
          marginBottom: '8px',
        }}
      >
        Behavioral patterns
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {behavioralPatterns.map((pattern, idx) => (
          <div
            key={idx}
            style={{
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
              fontSize: '15px',
              lineHeight: 1.5,
              color: 'var(--at-ink-1)',
            }}
          >
            {pattern}
          </div>
        ))}
      </div>
    </div>

    {/* Memory items with similarity scores */}
    {items.length > 0 && (
      <div>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase' as const,
            color: 'var(--at-ink-2)',
            fontWeight: 500,
            display: 'block',
            marginBottom: '8px',
          }}
        >
          Recalled facts
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {items.map((item) => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--at-mono)',
                  fontSize: '13px',
                  padding: '4px 10px',
                  background: 'var(--at-cream-2)',
                  border: '1px solid var(--at-card-border)',
                  borderRadius: '100px',
                  color: 'var(--at-ink-2)',
                  letterSpacing: '0.02em',
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap' as const,
                }}
              >
                {item.content}
              </span>
              {item.similarity != null && (
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '12px',
                    color: 'var(--at-green-1)',
                    fontWeight: 500,
                    flexShrink: 0,
                    letterSpacing: '0.04em',
                  }}
                >
                  {item.similarity.toFixed(2)}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    )}
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', padding: '24px 0' }}>
    <div
      style={{
        background: 'var(--at-cream-2)',
        borderRadius: 'var(--at-card-radius)',
        height: '400px',
        opacity: 0.5,
        animation: 'pulse 1.5s ease-in-out infinite',
      }}
    />
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
      {[0, 1].map((i) => (
        <div
          key={i}
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '320px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
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
      We couldn't load the memory dashboard.
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
 * Empty state — no memory data for persona
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
    <Eyebrow label="No memory" variant="muted" />
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
      No memory has been recorded for this persona.
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
      Start a conversation in the boutique to build short-term memory, or check that the
      memory fixture data is available.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const MemoryDashboard: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<MemoryState>({
    key: 'memory-marco',
  });

  const hasData =
    data != null &&
    (data.stm.items.length > 0 ||
      data.stm.recentIntents.length > 0 ||
      data.ltm.items.length > 0 ||
      data.ltm.preferences.length > 0);

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Memory · STM + LTM · persona-scoped"
        title="What the system remembers."
        summary="Two tiers of memory power every conversation. Short-term memory (STM) holds the current session context — intents, turns, fresh items. Long-term memory (LTM) stores preferences, order history, and behavioral patterns in Aurora pgvector for semantic recall across sessions."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && !hasData && <EmptyState />}

      {!loading && !error && hasData && data != null && (
        <>
          {/* Orbit visualization */}
          <div style={{ marginBottom: '36px' }}>
            <ExpCard>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  marginBottom: '12px',
                }}
              >
                <Eyebrow label="Memory orbit" />
              </div>
              <p
                style={{
                  fontFamily: 'var(--at-serif)',
                  fontStyle: 'italic',
                  fontSize: '16px',
                  color: 'var(--at-ink-1)',
                  lineHeight: 1.5,
                  margin: '0 0 16px 0',
                  maxWidth: '520px',
                }}
              >
                Persona at center. STM items orbit on the inner ring (burgundy dots), LTM items
                on the outer ring (outlined dots). Lines show recall connections.
              </p>
              <OrbitVisualization
                persona={data.persona}
                stmItems={data.stm.items}
                ltmItems={data.ltm.items}
              />
            </ExpCard>
          </div>

          {/* STM + LTM tier cards side by side */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '18px',
            }}
          >
            <StmCard
              turnCount={data.stm.turnCount}
              recentIntents={data.stm.recentIntents}
              items={data.stm.items}
            />
            <LtmCard
              preferences={data.ltm.preferences}
              priorOrders={data.ltm.priorOrders}
              behavioralPatterns={data.ltm.behavioralPatterns}
              items={data.ltm.items}
            />
          </div>
        </>
      )}
    </div>
  );
};

export default MemoryDashboard;