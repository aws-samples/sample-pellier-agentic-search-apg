/**
 * MemoryDetail — Architecture detail page for the Memory concept.
 *
 * Displays:
 *   - Two tier cards (STM and LTM) side by side with tier name,
 *     CategoryBadge, title, role, prose, and code snippet
 *   - Orbit centerpiece visualization: persona at center, STM items
 *     on inner ring, LTM items on outer ring, labeled connector dots
 *   - Live state callout: STM turn count, LTM fact count
 *   - Fallback to fixture data when live data unavailable
 *
 * Requirements: 7.2, 7.3, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard, CategoryBadge } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { MemoryState, MemoryItem } from '../../../types';

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

  function truncate(text: string, max: number): string {
    return text.length > max ? text.slice(0, max - 1) + '\u2026' : text;
  }

  return (
    <svg
      viewBox="0 0 600 600"
      width="100%"
      style={{ maxWidth: '800px', display: 'block', margin: '0 auto' }}
      role="img"
      aria-label={`Memory orbit for ${persona}: ${stmItems.length} STM items, ${ltmItems.length} LTM items`}
    >
      {/* Orbit rings */}
      <circle
        cx={cx} cy={cy} r={ltmRadius}
        fill="none" stroke="var(--at-rule-1)" strokeWidth="1"
        strokeDasharray="6 4" opacity={0.5}
      />
      <circle
        cx={cx} cy={cy} r={stmRadius}
        fill="none" stroke="var(--at-rule-2)" strokeWidth="1"
        strokeDasharray="4 3" opacity={0.6}
      />

      {/* Connector lines — LTM */}
      {ltmPositions.map((pos, i) => (
        <line
          key={`ltm-line-${ltmItems[i].id}`}
          x1={cx} y1={cy} x2={pos.x} y2={pos.y}
          stroke="var(--at-rule-1)" strokeWidth="0.5" opacity={0.25}
        />
      ))}

      {/* Connector lines — STM */}
      {stmPositions.map((pos, i) => (
        <line
          key={`stm-line-${stmItems[i].id}`}
          x1={cx} y1={cy} x2={pos.x} y2={pos.y}
          stroke="var(--at-red-1)" strokeWidth="0.5" opacity={0.3}
        />
      ))}

      {/* LTM dots + labels */}
      {ltmPositions.map((pos, i) => {
        const item = ltmItems[i];
        return (
          <g key={`ltm-${item.id}`}>
            <circle
              cx={pos.x} cy={pos.y} r={8}
              fill="var(--at-cream-2)" stroke="var(--at-ink-1)" strokeWidth="1.5"
            />
            <text
              x={pos.x} y={pos.y + 18} textAnchor="middle"
              style={{
                fontFamily: 'var(--at-mono)', fontSize: '10px',
                fill: 'var(--at-ink-1)', letterSpacing: '0.04em',
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
            <circle cx={pos.x} cy={pos.y} r={7} fill="var(--at-red-1)" opacity={0.85} />
            <text
              x={pos.x} y={pos.y + 16} textAnchor="middle"
              style={{
                fontFamily: 'var(--at-mono)', fontSize: '10px',
                fill: 'var(--at-ink-2)', letterSpacing: '0.04em',
              }}
            >
              {truncate(item.content, 28)}
            </text>
          </g>
        );
      })}

      {/* Persona center circle */}
      <circle cx={cx} cy={cy} r={32} fill="var(--at-ink-1)" />
      <text
        x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="central"
        style={{
          fontFamily: 'var(--at-serif)', fontStyle: 'italic',
          fontSize: '18px', fill: 'var(--at-cream-1)', letterSpacing: '-0.02em',
        }}
      >
        {persona.charAt(0).toUpperCase()}
      </text>
      <text
        x={cx} y={cy + 50} textAnchor="middle"
        style={{
          fontFamily: 'var(--at-mono)', fontSize: '9px',
          fill: 'var(--at-ink-4)', letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        {persona}
      </text>

      {/* Ring labels */}
      <text
        x={cx} y={cy - stmRadius - 10} textAnchor="middle"
        style={{
          fontFamily: 'var(--at-mono)', fontSize: '10px',
          fill: 'var(--at-red-1)', letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        STM
      </text>
      <text
        x={cx} y={cy - ltmRadius - 10} textAnchor="middle"
        style={{
          fontFamily: 'var(--at-mono)', fontSize: '10px',
          fill: 'var(--at-ink-4)', letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        LTM
      </text>
    </svg>
  );
};

/* -----------------------------------------------------------------------
 * Tier Card — reusable for STM and LTM
 * ----------------------------------------------------------------------- */

interface TierCardProps {
  tierName: string;
  category: 'managed' | 'both';
  title: string;
  role: string;
  prose: string;
  codeSnippet: string;
}

const TierCard: React.FC<TierCardProps> = ({
  tierName,
  category,
  title,
  role,
  prose,
  codeSnippet,
}) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Tier name + badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '9px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--at-ink-4)',
            fontWeight: 500,
          }}
        >
          {tierName}
        </span>
        <CategoryBadge category={category} />
      </div>

      {/* Title */}
      <h3
        style={{
          fontFamily: 'var(--at-serif)',
          fontSize: '22px',
          fontWeight: 400,
          lineHeight: 1.15,
          letterSpacing: '-0.012em',
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {title}
      </h3>

      {/* Role */}
      <p
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '15px',
          lineHeight: 1.4,
          color: 'var(--at-red-1)',
          margin: 0,
        }}
      >
        {role}
      </p>

      {/* Prose */}
      <p
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: 'var(--at-body-size)',
          lineHeight: 'var(--at-body-leading)',
          color: 'var(--at-ink-1)',
          margin: 0,
        }}
      >
        {prose}
      </p>

      {/* Code snippet */}
      <pre
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '14px',
          lineHeight: 1.7,
          color: 'var(--at-ink-1)',
          backgroundColor: 'var(--at-cream-2)',
          borderRadius: '8px',
          padding: '16px 20px',
          margin: 0,
          overflowX: 'auto',
          whiteSpace: 'pre',
        }}
      >
        {codeSnippet}
      </pre>
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const MemoryDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<MemoryState>({
    key: 'memory-marco',
  });

  const stmCount = data?.stm.turnCount ?? 0;
  const ltmCount = data?.ltm.items.length ?? 0;

  return (
    <DetailPageShell
      numeral="I"
      conceptName="Memory"
      category="both"
      title="Memory, two-tiered."
      prose="Two tiers of memory power every conversation. Short-term memory (STM) holds the current session context — intents, turns, fresh items. Long-term memory (LTM) stores preferences, order history, and behavioral patterns in Aurora pgvector for semantic recall across sessions."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'STM is a small ring buffer — cheap, bounded, always relevant. Read it first on every turn.',
        },
        {
          numeral: 'ii.',
          text: 'LTM is a vector index over facts — past purchases, preferences, behavioral patterns. Only reach into it when the turn earns the latency.',
        },
        {
          numeral: 'iii.',
          text: 'Different privacy boundaries: STM is session-scoped, LTM is customer-scoped. Scope the data that way.',
        },
      ]}
      liveState={
        data
          ? {
              label: `Current memory state for the active persona. STM holds the recent conversation context, LTM stores recalled facts from Aurora pgvector.`,
              values: [
                { label: 'STM turns', value: String(stmCount) },
                { label: 'LTM facts', value: String(ltmCount) },
                { label: 'Persona', value: data.persona },
              ],
            }
          : undefined
      }
    >
      {/* Loading state */}
      {loading && <MemoryLoadingState />}

      {/* Error state */}
      {error && <MemoryErrorState message={error} onRetry={refetch} />}

      {/* Content */}
      {!loading && !error && data && (
        <>
          {/* Two tier cards side by side */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '20px',
              marginBottom: '36px',
            }}
          >
            <TierCard
              tierName="STM · Short-Term"
              category="managed"
              title="Session context"
              role="Ephemeral, session-scoped conversation state"
              prose="Conversation state managed by AgentCore. Last twelve turns, in order, fully read on every request. Cheap and bounded — the agent reads STM first on every turn."
              codeSnippet={`# STM — session-scoped via AgentCore Memory
await memory.store(session_id, turn_context)

# Read last 12 turns
stm = session.get(limit=12)
# → list[Message]`}
            />
            <TierCard
              tierName="LTM · Long-Term"
              category="both"
              title="Semantic recall"
              role="Persistent cross-session memory via pgvector"
              prose="Persistent memory stored in Aurora pgvector — preferences, order history, and behavioral patterns recalled via semantic similarity. Queried only when the turn earns the latency."
              codeSnippet={`# LTM — pgvector semantic recall
SELECT content,
       1 - (embedding <=> $1) AS similarity
FROM memory_items
WHERE persona_id = $2 AND tier = 'ltm'
ORDER BY embedding <=> $1 LIMIT 5;`}
            />
          </div>

          {/* Orbit centerpiece visualization */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    display: 'inline-block',
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--at-red-1)',
                    flexShrink: 0,
                  }}
                  aria-hidden="true"
                />
                <span
                  style={{
                    fontFamily: 'var(--at-mono)',
                    fontSize: '9px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--at-red-1)',
                    fontWeight: 500,
                  }}
                >
                  Memory orbit
                </span>
              </div>
              <p
                style={{
                  fontFamily: 'var(--at-serif)',
                  fontStyle: 'italic',
                  fontSize: '14px',
                  color: 'var(--at-ink-1)',
                  lineHeight: 1.5,
                  margin: 0,
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
            </div>
          </ExpCard>
        </>
      )}

      {/* Empty / no data fallback */}
      {!loading && !error && !data && <MemoryEmptyState />}
    </DetailPageShell>
  );
};

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const MemoryLoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
      {[0, 1].map((i) => (
        <div
          key={i}
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '280px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
    <div
      style={{
        background: 'var(--at-cream-2)',
        borderRadius: 'var(--at-card-radius)',
        height: '400px',
        opacity: 0.5,
        animation: 'pulse 1.5s ease-in-out infinite',
      }}
    />
  </div>
);

/* -----------------------------------------------------------------------
 * Error state
 * ----------------------------------------------------------------------- */

const MemoryErrorState: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
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
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
      }}
    >
      We couldn't load the memory data.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '14px',
        color: 'var(--at-ink-4)',
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
        fontSize: '14px',
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

const MemoryEmptyState: React.FC = () => (
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
    <p
      style={{
        fontFamily: 'var(--at-serif)',
        fontStyle: 'italic',
        fontSize: '20px',
        lineHeight: 1.35,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
      }}
    >
      No memory data available for this persona.
    </p>
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: 'var(--at-body-size)',
        color: 'var(--at-ink-4)',
        maxWidth: '380px',
        marginTop: '8px',
      }}
    >
      Start a conversation in the boutique to build memory, or check that the
      memory fixture data is available.
    </p>
  </div>
);

export default MemoryDetail;
