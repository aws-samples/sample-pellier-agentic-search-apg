/**
 * StateDetail — Architecture detail page for Routing & State.
 *
 * Dispatcher-first routing plus the small state bundle carried through a turn.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';
import { ARCHITECTURE_CODE_BLOCK, ARCHITECTURE_CODE_BLOCK_COMPACT } from './codeStyles';

const StateDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'state-management');

  return (
    <DetailPageShell
      numeral="IV"
      conceptName="Routing & State"
      category="live"
      title="Routing, explicit."
      prose="The Boutique default path is dispatcher-first: services/chat.py triages small talk, classifies intent, optionally loads one persona skill, then hands the turn to one owning specialist/tool path. Agents-as-Tools and graph routing stay visible as teaching patterns, not the default storefront runtime."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'State flows in one direction: triage and intent classification determine the specialist path, then tool results and memory context shape the reply.',
        },
        {
          numeral: 'ii.',
          text: 'The dispatcher path keeps state small and auditable: query, persona, session id, loaded skill, intent, tool calls, and telemetry events.',
        },
        {
          numeral: 'iii.',
          text: 'Routing pages compare Dispatcher, Agents-as-Tools, and Graph patterns, but the Boutique uses Dispatcher because it is cheaper and easier to reason about.',
        },
      ]}
      liveState={{
        label: 'Current routing context for the active session. Shows the intent, selected specialist path, and routing strategy.',
        values: [
          { label: 'Owning path', value: '1' },
          { label: 'Routing', value: 'Dispatcher' },
          { label: 'State keys', value: '6' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Routing & State" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* State flow diagram */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="The dispatcher path" />
              <h3 style={titleStyle}>Intent to response, one owner.</h3>
              <p style={proseStyle}>
                A request arrives with a persona and session id. The dispatcher classifies the
                intent, loads the relevant skill when needed, and chooses one specialist/tool
                path for the turn. The telemetry tab records each step so the route is auditable.
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
              description="The owning specialist path for this turn. The Boutique default chooses one path, not a committee."
              example='owner = "Curator"'
            />
            <StateKeyCard
              keyName="memory_context"
              description="STM/LTM context scoped by persona and session namespace."
              example="memory_context = { stm, ltm }"
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
          ...ARCHITECTURE_CODE_BLOCK_COMPACT,
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
    <text x="52" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="var(--cream-warm)">intent</text>

    <rect x="160" y="75" width="85" height="50" rx="8" fill="var(--cream-warm)" stroke="var(--accent)" strokeWidth="1" />
    <text x="202" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="#a8423a">skill</text>

    <rect x="310" y="75" width="85" height="50" rx="8" fill="var(--cream-warm)" stroke="rgba(31,29,26,0.3)" strokeWidth="1" />
    <text x="352" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="13" fill="#1f1410">tools</text>

    <rect x="460" y="75" width="30" height="50" rx="8" fill="var(--at-green-1, #6b8c5e)" opacity="0.15" stroke="var(--at-green-1, #6b8c5e)" strokeWidth="1" />
    <text x="475" y="103" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="11" fill="var(--at-green-1, #6b8c5e)">✓</text>

    {/* Labels */}
    <text x="52" y="145" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1">CLASSIFY</text>
    <text x="202" y="145" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1">LOAD</text>
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
  ...ARCHITECTURE_CODE_BLOCK,
  whiteSpace: 'pre',
};

export default StateDetail;
