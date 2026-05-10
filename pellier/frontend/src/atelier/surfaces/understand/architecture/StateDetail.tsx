/**
 * StateDetail — Architecture detail page for State Management.
 *
 * Centralized state management coordinates conversation context,
 * agent activation status, and routing decisions.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';

const StateDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'state-management');

  return (
    <DetailPageShell
      numeral="III"
      conceptName="State Management"
      category="managed"
      title="State, coordinated."
      prose="Centralized state management coordinates conversation context, agent activation status, and routing decisions across the multi-agent system. AgentCore Runtime maintains the state graph that the orchestrator traverses."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'State flows in one direction: intent classification determines which agents activate, which determines which tools fire.',
        },
        {
          numeral: 'ii.',
          text: 'The orchestrator holds the state graph. Specialists read from it but never write to it directly — they return results that the orchestrator folds back in.',
        },
        {
          numeral: 'iii.',
          text: 'Routing decisions are state transitions. Dispatcher, Agents-as-Tools, and Graph are three strategies for traversing the same state space.',
        },
      ]}
      liveState={{
        label: 'Current state management context for the active session. Shows the intent, active agents, and routing strategy.',
        values: [
          { label: 'Active agents', value: '3' },
          { label: 'Routing', value: 'Dispatcher' },
          { label: 'State keys', value: '4' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="State Management" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* State flow diagram */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="The state graph" />
              <h3 style={titleStyle}>Intent to response, one graph.</h3>
              <p style={proseStyle}>
                A request arrives with an intent. The orchestrator classifies it, activates the
                right specialists, and coordinates their tool calls. Each step is a state
                transition — the graph is the execution plan.
              </p>
              <StateFlowDiagram />
            </div>
          </ExpCard>

          {/* State keys */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <StateKeyCard
              keyName="intent"
              description="Classified user intent — pricing, inventory, support, search, or recommendation."
              example='classified_intent = "search"'
            />
            <StateKeyCard
              keyName="active_agents"
              description="List of specialist agents activated for this turn based on the classified intent."
              example="active_agents = [search, recommend]"
            />
            <StateKeyCard
              keyName="memory_context"
              description="STM items loaded for this session — recent turns and intents."
              example="memory_context = stm_items[:12]"
            />
            <StateKeyCard
              keyName="routing"
              description="Active routing strategy — Dispatcher (default), Agents-as-Tools, or Graph."
              example='routing = "dispatcher"'
            />
          </div>

          {/* Code snippet */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="Code" />
              <pre style={codeStyle}>{concept.codeSnippet}</pre>
            </div>
          </ExpCard>
        </div>
      )}
    </DetailPageShell>
  );
};

/* ---- Sub-components ---- */

const StateKeyCard: React.FC<{
  keyName: string;
  description: string;
  example: string;
}> = ({ keyName, description, example }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--at-ink-1)',
        }}
      >
        {keyName}
      </span>
      <p style={{ fontFamily: 'var(--at-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--at-ink-1)', margin: 0 }}>
        {description}
      </p>
      <pre
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          color: 'var(--at-ink-1)',
          backgroundColor: 'var(--at-cream-2)',
          borderRadius: '6px',
          padding: '8px 12px',
          margin: 0,
          whiteSpace: 'pre',
        }}
      >
        {example}
      </pre>
    </div>
  </ExpCard>
);

const StateFlowDiagram: React.FC = () => (
  <svg viewBox="0 0 500 200" width="100%" style={{ maxWidth: '500px', display: 'block', margin: '0 auto' }}>
    {/* Flow arrows */}
    <line x1="95" y1="100" x2="155" y2="100" stroke="rgba(168,66,58,0.5)" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
    <line x1="245" y1="100" x2="305" y2="100" stroke="rgba(168,66,58,0.5)" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
    <line x1="395" y1="100" x2="455" y2="100" stroke="rgba(168,66,58,0.5)" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
    <defs>
      <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="rgba(168,66,58,0.5)" />
      </marker>
    </defs>

    {/* Nodes */}
    <rect x="10" y="75" width="85" height="50" rx="8" fill="#1f1410" />
    <text x="52" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="#faf3e8">intent</text>

    <rect x="160" y="75" width="85" height="50" rx="8" fill="#faf3e8" stroke="#a8423a" strokeWidth="1" />
    <text x="202" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="#a8423a">agents</text>

    <rect x="310" y="75" width="85" height="50" rx="8" fill="#faf3e8" stroke="rgba(31,20,16,0.3)" strokeWidth="1" />
    <text x="352" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="#1f1410">tools</text>

    <rect x="460" y="75" width="30" height="50" rx="8" fill="var(--at-green-1, #6b8c5e)" opacity="0.15" stroke="var(--at-green-1, #6b8c5e)" strokeWidth="1" />
    <text x="475" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="11" fill="var(--at-green-1, #6b8c5e)">✓</text>

    {/* Labels */}
    <text x="52" y="145" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1">CLASSIFY</text>
    <text x="202" y="145" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1">ACTIVATE</text>
    <text x="352" y="145" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1">INVOKE</text>
    <text x="475" y="145" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1">DONE</text>
  </svg>
);

/* ---- Shared styles ---- */

const SectionLabel: React.FC<{ label: string }> = ({ label }) => (
  <span style={{ fontFamily: 'var(--at-mono)', fontSize: '9px', letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--at-ink-4)', fontWeight: 500 }}>
    {label}
  </span>
);

const titleStyle: React.CSSProperties = {
  fontFamily: 'var(--at-serif)', fontSize: '22px', fontWeight: 400, fontStyle: 'italic',
  lineHeight: 1.15, color: 'var(--at-ink-1)', margin: 0,
};

const proseStyle: React.CSSProperties = {
  fontFamily: 'var(--at-sans)', fontSize: 'var(--at-body-size)', lineHeight: 'var(--at-body-leading)',
  color: 'var(--at-ink-1)', margin: 0, maxWidth: '560px',
};

const codeStyle: React.CSSProperties = {
  fontFamily: 'var(--at-mono)', fontSize: '14px', lineHeight: 1.7,
  color: 'var(--at-ink-1)', backgroundColor: 'var(--at-cream-2)', borderRadius: '8px',
  padding: '14px 16px', margin: 0, overflowX: 'auto', whiteSpace: 'pre',
};

export default StateDetail;
