/**
 * Observatory — Wide-angle dashboard for the entire agentic system.
 *
 * Summary ExpCards: active sessions, agent status (5 agents with live/idle dots),
 * tool invocations, memory state (STM/LTM counts), performance headlines.
 * Large serif numerals for key metrics, monospace labels.
 * Live pulsing indicator on dashboard.
 * Fallback to fixture data with note when no live data available.
 *
 * Requirements: 14.1, 14.2, 14.3, 14.4, 19.1, 19.2, 19.3, 19.4
 */

import React from 'react';
import {
  EditorialTitle,
  ExpCard,
  Eyebrow,
  StatusDot,
} from '../../components';
import { useAtelierData } from '../../hooks/useAtelierData';
import type { ObservatorySummary } from '../../types';

/* -----------------------------------------------------------------------
 * Metric Numeral — large serif numeral with monospace label
 * ----------------------------------------------------------------------- */

interface MetricNumeralProps {
  value: string | number;
  label: string;
  unit?: string;
}

const MetricNumeral: React.FC<MetricNumeralProps> = ({ value, label, unit }) => (
  <div>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
      <span
        style={{
          fontFamily: 'var(--at-sans)',
          fontSize: '52px',
          fontWeight: 400,
          letterSpacing: '-0.02em',
          lineHeight: 1,
          color: 'var(--at-ink-1)',
        }}
      >
        {value}
      </span>
      {unit && (
        <span
          style={{
            fontFamily: 'var(--at-sans)',
            fontSize: '17px',
            letterSpacing: '0.04em',
            color: 'var(--at-ink-2)',
          }}
        >
          {unit}
        </span>
      )}
    </div>
    <span
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '16px',
        letterSpacing: '0.06em',
        color: 'var(--at-ink-2)',
        marginTop: '8px',
        display: 'block',
      }}
    >
      {label}
    </span>
  </div>
);

/* -----------------------------------------------------------------------
 * Active Sessions Card
 * ----------------------------------------------------------------------- */

interface ActiveSessionsCardProps {
  active: number;
  total: number;
}

const ActiveSessionsCard: React.FC<ActiveSessionsCardProps> = ({ active, total }) => (
  <ExpCard>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
      <StatusDot status="live" size={10} />
      <Eyebrow label="Active sessions" />
    </div>
    <MetricNumeral value={active} label={`of ${total} total sessions`} />
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Agent Status Card
 * ----------------------------------------------------------------------- */

interface AgentStatusCardProps {
  agents: { name: string; status: 'live' | 'idle' }[];
}

const AgentStatusCard: React.FC<AgentStatusCardProps> = ({ agents }) => {
  const liveCount = agents.filter((a) => a.status === 'live').length;

  return (
    <ExpCard>
      <Eyebrow label="Agent status" />
      <div style={{ marginTop: '14px' }}>
        <MetricNumeral value={liveCount} label={`of ${agents.length} agents live`} />
      </div>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          marginTop: '20px',
        }}
      >
        {agents.map((agent) => (
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
                color: agent.status === 'live' ? 'var(--at-ink-1)' : 'var(--at-ink-2)',
              }}
            >
              {agent.name}
            </span>
            <span
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '11px',
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: agent.status === 'live' ? 'var(--at-green-1)' : 'var(--at-ink-3)',
                marginLeft: 'auto',
              }}
            >
              {agent.status}
            </span>
          </div>
        ))}
      </div>
    </ExpCard>
  );
};

/* -----------------------------------------------------------------------
 * Tool Invocations Card
 * ----------------------------------------------------------------------- */

interface ToolInvocationsCardProps {
  count: number;
}

const ToolInvocationsCard: React.FC<ToolInvocationsCardProps> = ({ count }) => (
  <ExpCard>
    <Eyebrow label="Tool invocations" />
    <div style={{ marginTop: '14px' }}>
      <MetricNumeral value={count.toLocaleString()} label="Total calls across all tools" />
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Memory State Card
 * ----------------------------------------------------------------------- */

interface MemoryStateCardProps {
  stm: number;
  ltm: number;
}

const MemoryStateCard: React.FC<MemoryStateCardProps> = ({ stm, ltm }) => (
  <ExpCard>
    <Eyebrow label="Memory state" />
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '20px',
        marginTop: '14px',
      }}
    >
      <MetricNumeral value={stm} label="STM items" />
      <MetricNumeral value={ltm} label="LTM items" />
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Performance Headlines Card
 * ----------------------------------------------------------------------- */

interface PerformanceHeadlinesCardProps {
  headlines: { label: string; value: string; unit?: string }[];
}

const PerformanceHeadlinesCard: React.FC<PerformanceHeadlinesCardProps> = ({ headlines }) => (
  <ExpCard>
    <Eyebrow label="Performance headlines" />
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, 1fr)',
        gap: '24px',
        marginTop: '14px',
      }}
    >
      {headlines.map((h) => (
        <MetricNumeral key={h.label} value={h.value} label={h.label} unit={h.unit} />
      ))}
    </div>
  </ExpCard>
);

/* -----------------------------------------------------------------------
 * Fixture Data Note
 * ----------------------------------------------------------------------- */

const FixtureDataNote: React.FC = () => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      padding: '10px 16px',
      backgroundColor: 'var(--at-cream-2)',
      borderRadius: '8px',
      border: '1px dashed var(--at-card-border)',
      marginTop: '8px',
    }}
  >
    <span
      style={{
        fontFamily: 'var(--at-mono)',
        fontSize: '12px',
        color: 'var(--at-ink-2)',
        letterSpacing: '0.04em',
      }}
    >
      Showing fixture data — wire to live telemetry in Phase 2
    </span>
  </div>
);

/* -----------------------------------------------------------------------
 * Loading state
 * ----------------------------------------------------------------------- */

const LoadingState: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px 0' }}>
    {/* Top row skeletons */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
      {[0, 1].map((i) => (
        <div
          key={i}
          style={{
            background: 'var(--at-cream-2)',
            borderRadius: 'var(--at-card-radius)',
            height: '140px',
            opacity: 0.5,
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
    {/* Middle row skeletons */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
      {[0, 1].map((i) => (
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
    {/* Bottom skeleton */}
    <div
      style={{
        background: 'var(--at-cream-2)',
        borderRadius: 'var(--at-card-radius)',
        height: '180px',
        opacity: 0.5,
        animation: 'pulse 1.5s ease-in-out infinite',
      }}
    />
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
        fontFamily: 'var(--at-sans)',
        fontSize: '17px',
        lineHeight: 1.6,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      The observatory lost its connection.
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
    <Eyebrow label="No data" variant="muted" />
    <p
      style={{
        fontFamily: 'var(--at-sans)',
        fontSize: '17px',
        lineHeight: 1.6,
        color: 'var(--at-ink-1)',
        maxWidth: '420px',
        marginTop: '16px',
      }}
    >
      The observatory is quiet.
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
      No telemetry has been recorded yet. Start a session to see the system come alive.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Observatory: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ObservatorySummary>({
    key: 'observatory',
  });

  const isEmpty =
    !data ||
    (data.activeSessions === 0 &&
      data.toolInvocations === 0 &&
      data.agentStatus.length === 0);

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      {/* Title block with live pulsing indicator */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
        <div style={{ flex: 1 }}>
          <EditorialTitle
            eyebrow="Observe · Observatory · system overview"
            title="The wide-angle view."
            summary="A real-time overview of the entire agentic system — sessions, agents, tools, memory, and performance at a glance."
          />
        </div>
        {/* Live pulsing indicator */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginTop: '8px',
            flexShrink: 0,
          }}
        >
          <StatusDot status="live" size={10} />
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--at-ink-2)',
            }}
          >
            Live
          </span>
        </div>
      </div>

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && isEmpty && <EmptyState />}

      {!loading && !error && data && !isEmpty && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Row 1: Active Sessions + Agent Status */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <ActiveSessionsCard
              active={data.activeSessions}
              total={data.totalSessions}
            />
            <AgentStatusCard agents={data.agentStatus} />
          </div>

          {/* Row 2: Tool Invocations + Memory State */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <ToolInvocationsCard count={data.toolInvocations} />
            <MemoryStateCard
              stm={data.memoryItems.stm}
              ltm={data.memoryItems.ltm}
            />
          </div>

          {/* Row 3: Performance Headlines (full width) */}
          <PerformanceHeadlinesCard headlines={data.performanceHeadlines} />

          {/* Fixture data note */}
          <FixtureDataNote />

          {/* Last updated timestamp */}
          <div
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              color: 'var(--at-ink-3)',
              letterSpacing: '0.06em',
              textAlign: 'right',
            }}
          >
            Last updated: {new Date(data.lastUpdated).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
};

export default Observatory;
