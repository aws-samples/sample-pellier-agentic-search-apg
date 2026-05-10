/**
 * Agents — Five specialist agents surface.
 *
 * WorkshopProgressStrip (5 segments: 3 shipped, 2 exercise) + 5 agent row cards.
 * Shipped agents: solid borders, cream-elev bg, sage "Shipped" pills.
 * Exercise agents: dashed borders, transparent bg, burgundy "Exercise" pills.
 * "Related" callout card linking to Skills and Routing surfaces.
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
 */

import React from 'react';
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
import type { Agent } from '../../types';

/* -----------------------------------------------------------------------
 * Build Segment[] from agent data for WorkshopProgressStrip
 * ----------------------------------------------------------------------- */

function buildSegments(agents: Agent[]): Segment[] {
  return agents.map((agent) => ({
    id: agent.numeral,
    label: agent.name,
    status: agent.status,
  }));
}

/* -----------------------------------------------------------------------
 * Agent row card
 * ----------------------------------------------------------------------- */

interface AgentRowProps {
  agent: Agent;
}

const AgentRow: React.FC<AgentRowProps> = ({ agent }) => {
  const isExercise = agent.status === 'exercise';

  return (
    <div
      style={{
        position: 'relative',
        background: isExercise ? 'transparent' : 'var(--at-card-bg)',
        border: isExercise
          ? '1.5px dashed var(--at-rule-3)'
          : '1px solid var(--at-card-border)',
        borderRadius: 'var(--at-card-radius)',
        padding: '22px 26px 20px',
        overflow: 'hidden',
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

      {/* Head: numeral + name + role on left, status on right */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: '18px',
          alignItems: 'flex-start',
          marginBottom: '14px',
        }}
      >
        {/* Identity: numeral + name block */}
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
            {(agent.numeral ?? '').toLowerCase()}.
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 }}>
            <h3
              style={{
                fontFamily: 'var(--at-serif)',
                fontWeight: 400,
                fontSize: '24px',
                letterSpacing: '-0.012em',
                lineHeight: 1.1,
                color: isExercise ? 'var(--at-ink-1)' : 'var(--at-ink-1)',
                margin: 0,
              }}
            >
              {agent.name}
            </h3>
            <p
              style={{
                fontFamily: 'var(--at-serif)',
                fontStyle: 'italic',
                fontSize: '16px',
                color: 'var(--at-ink-1)',
                lineHeight: 1.4,
                margin: 0,
              }}
            >
              {agent.role}
            </p>
          </div>
        </div>

        {/* Status: dot + pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            flexShrink: 0,
            paddingTop: '6px',
          }}
        >
          <StatusDot status={isExercise ? 'empty' : 'idle'} />
          <StatusPill status={agent.status} />
        </div>
      </div>

      {/* Body: tools + meta */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: '24px',
          alignItems: 'center',
          paddingTop: '14px',
          borderTop: isExercise
            ? '1px dashed var(--at-rule-2)'
            : '1px solid var(--at-card-border)',
        }}
      >
        {/* Tools */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '11px',
              letterSpacing: '0.22em',
              textTransform: 'uppercase' as const,
              color: isExercise ? 'var(--at-red-1)' : 'var(--at-ink-2)',
              marginRight: '6px',
              fontWeight: 500,
            }}
          >
            {isExercise ? 'Tools to wire' : 'Tools'}
          </span>
          {agent.tools.map((tool) => (
            <span
              key={tool}
              style={{
                fontFamily: 'var(--at-mono)',
                fontSize: '13px',
                padding: '3px 9px',
                background: isExercise ? 'transparent' : 'var(--at-cream-2)',
                border: isExercise
                  ? '1px dashed var(--at-red-1)'
                  : '1px solid var(--at-card-border)',
                borderRadius: '100px',
                color: isExercise ? 'var(--at-red-1)' : 'var(--at-ink-1)',
                letterSpacing: '0.02em',
              }}
            >
              {tool}
            </span>
          ))}
        </div>

        {/* Meta: model tag + open link */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flexShrink: 0 }}>
          <span
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              letterSpacing: '0.1em',
              color: 'var(--at-ink-2)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span style={{ color: 'var(--at-ink-1)', fontWeight: 500 }}>
              {agent.model}
            </span>
            {' · '}
            {agent.temperature}
          </span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              fontFamily: 'var(--at-serif)',
              fontStyle: 'italic',
              fontSize: '16px',
              fontWeight: 400,
              color: 'var(--at-red-1)',
              cursor: 'pointer',
              borderBottom: isExercise
                ? '1px solid var(--at-red-1)'
                : '1px solid transparent',
            }}
          >
            Open {agent.name}
            <span aria-hidden="true" style={{ fontStyle: 'italic', fontSize: '16px' }}>→</span>
          </span>
        </div>
      </div>

      {/* Exercise files list */}
      {isExercise && agent.exerciseFiles && agent.exerciseFiles.length > 0 && (
        <div
          style={{
            marginTop: '12px',
            paddingTop: '12px',
            borderTop: '1px dashed var(--at-rule-1)',
            fontFamily: 'var(--at-mono)',
            fontSize: '12px',
            lineHeight: 1.7,
            color: 'var(--at-ink-1)',
          }}
        >
          <span
            style={{
              color: 'var(--at-red-1)',
              letterSpacing: '0.22em',
              textTransform: 'uppercase' as const,
              fontSize: '11px',
              marginRight: '8px',
              fontWeight: 500,
            }}
          >
            Files
          </span>
          {agent.exerciseFiles.map((file, idx) => (
            <React.Fragment key={file}>
              <span style={{ color: 'var(--at-ink-2)' }}>{file}</span>
              {idx < (agent.exerciseFiles?.length ?? 0) - 1 && (
                <span style={{ color: 'var(--at-ink-5)', margin: '0 6px' }}>·</span>
              )}
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
};

/* -----------------------------------------------------------------------
 * Related callout card — links to Skills and Routing surfaces
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
        to agents
      </div>

      {/* Skills cell */}
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
          Skills{' '}
          <span style={{ color: 'var(--at-red-1)' }}>· two voices</span>
        </div>
        <p
          style={{
            fontFamily: 'var(--at-serif)',
            fontStyle: 'italic',
            fontSize: '15px',
            color: 'var(--at-ink-1)',
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          <em style={{ color: 'var(--at-ink-1)', fontStyle: 'italic' }}>style-advisor</em> and{' '}
          <em style={{ color: 'var(--at-ink-1)', fontStyle: 'italic' }}>gift-concierge</em>.
          Loaded per-turn by SkillRouter (Haiku 4.5 · 0.0). Injected into the specialist's
          system prompt — they change{' '}
          <em style={{ color: 'var(--at-ink-1)', fontStyle: 'italic' }}>voice and handling</em>,
          not product selection.
        </p>
        <Link
          to="/atelier/architecture/skills"
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
          Open Skills surface
          <span
            aria-hidden="true"
            style={{ fontFamily: 'var(--at-serif)', fontStyle: 'italic' }}
          >
            →
          </span>
        </Link>
      </div>

      {/* Routing cell */}
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
          Routing{' '}
          <span style={{ color: 'var(--at-red-1)' }}>· three patterns</span>
        </div>
        <p
          style={{
            fontFamily: 'var(--at-serif)',
            fontStyle: 'italic',
            fontSize: '15px',
            color: 'var(--at-ink-1)',
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          Three patterns:{' '}
          <em style={{ color: 'var(--at-ink-1)', fontStyle: 'italic' }}>Dispatcher</em> (active
          in the boutique),{' '}
          <em style={{ color: 'var(--at-ink-1)', fontStyle: 'italic' }}>Agents-as-Tools</em>,{' '}
          <em style={{ color: 'var(--at-ink-1)', fontStyle: 'italic' }}>Graph</em>. The first
          runs without an orchestrator; the other two use a Haiku 4.5 router. None of the five
          specialists is a lead — that's the routing layer's job.
        </p>
        <Link
          to="/atelier/routing"
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
          Open Routing surface
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
  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '24px 0' }}>
    {Array.from({ length: 5 }, (_, i) => (
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
      We couldn't load the agents.
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
    <Eyebrow label="No agents" variant="muted" />
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
      No specialist agents have been loaded.
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
      Check that the agents fixture data is available and try again.
    </p>
  </div>
);

/* -----------------------------------------------------------------------
 * Main component
 * ----------------------------------------------------------------------- */

const Agents: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<Agent[]>({
    key: 'agents',
  });
  const buildState = useBuildState();

  // Apply build state overrides — when the backend reports a different status
  // than the fixture, the override takes precedence (exercise → shipped transition)
  const agents: Agent[] = (data ?? []).map((agent) => {
    const override = buildState.agentStatus[agent.name];
    if (override && override !== agent.status) {
      return { ...agent, status: override };
    }
    return agent;
  });

  const shippedCount = agents.filter((a) => a.status === 'shipped').length;
  const totalCount = agents.length;
  const segments = buildSegments(agents);

  return (
    <div style={{ padding: '40px 48px', maxWidth: '1100px' }}>
      <EditorialTitle
        eyebrow="Understand · Agents · five peers · all Opus 4.6 · 0.2"
        title="The cast of five."
        summary="Five peer specialists. None is a lead — routing happens at a separate layer (currently Dispatcher in the boutique). Three are shipped reference; two are yours to wire in Module 2."
      />

      {loading && <LoadingState />}

      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && agents.length === 0 && <EmptyState />}

      {!loading && !error && agents.length > 0 && (
        <>
          {/* Workshop Progress Strip */}
          <div style={{ marginBottom: '32px' }}>
            <WorkshopProgressStrip
              segments={segments}
              shipped={shippedCount}
              total={totalCount}
            />
          </div>

          {/* Agent rows */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              marginBottom: '32px',
            }}
          >
            {agents.map((agent) => (
              <AgentRow key={agent.numeral} agent={agent} />
            ))}
          </div>

          {/* Related callout card */}
          <RelatedCard />
        </>
      )}
    </div>
  );
};

export default Agents;
