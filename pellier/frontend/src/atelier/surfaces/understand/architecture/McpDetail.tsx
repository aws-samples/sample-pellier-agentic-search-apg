/**
 * McpDetail — Architecture detail page for the MCP concept.
 *
 * Model Context Protocol gateway — standardized tool discovery and invocation.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';

const McpDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'mcp');

  return (
    <DetailPageShell
      numeral="II"
      conceptName="MCP"
      category="managed"
      title="MCP, the seam."
      prose="Model Context Protocol is how the agent discovers and calls tools. The Gateway publishes the surface; the agent consumes it. One address, one protocol, many tools. The agent never talks to a tool directly."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'The agent asks the Gateway for the tool catalog — names, signatures, descriptions. This is discovery.',
        },
        {
          numeral: 'ii.',
          text: 'The agent calls a tool by name through the Gateway. The Gateway routes to the implementation and returns the result. This is invocation.',
        },
        {
          numeral: 'iii.',
          text: 'The Gateway handles authentication, observability, and rate limiting. You don\'t run the protocol layer — Gateway does it.',
        },
      ]}
      liveState={{
        label: 'Current MCP Gateway state. Tools are registered at boot and discovered via semantic similarity at runtime.',
        values: [
          { label: 'Tools registered', value: '9' },
          { label: 'Gateway p50', value: '18ms' },
          { label: 'Protocol', value: 'MCP' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="MCP" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Network diagram card */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <ConceptEyebrow label="The network" />
              <h3 style={sectionTitleStyle}>Three nodes, two edges.</h3>
              <p style={sectionProseStyle}>
                The agent never talks to a tool directly. It asks the Gateway "what's available?",
                gets back a list of tool descriptions, and invokes the ones it needs through the
                same channel.
              </p>
              <McpNetworkDiagram />
            </div>
          </ExpCard>

          {/* Node descriptions */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
            <NodeCard
              nodeKey="A"
              name="The Agent"
              tag="Owned"
              description="Strands orchestrator (Haiku) plus five specialists (Opus). Fetches the tool catalog from the Gateway on startup."
            />
            <NodeCard
              nodeKey="B"
              name="The Gateway"
              tag="Managed"
              description="AgentCore Gateway. Publishes the tool surface as MCP, handles authentication, observability, and rate limiting."
            />
            <NodeCard
              nodeKey="C"
              name="The Tools"
              tag="Owned"
              description="Our @tool-decorated functions. Registered with the Gateway at boot. The Gateway exposes their signatures."
            />
          </div>

          {/* Code snippet */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <ConceptEyebrow label="Code" />
              <pre style={codeBlockStyle}>{concept.codeSnippet}</pre>
            </div>
          </ExpCard>
        </div>
      )}
    </DetailPageShell>
  );
};

/* ---- Sub-components ---- */

const NodeCard: React.FC<{
  nodeKey: string;
  name: string;
  tag: string;
  description: string;
}> = ({ nodeKey, name, tag, description }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          style={{
            fontFamily: 'var(--at-mono)',
            fontSize: '11px',
            fontWeight: 600,
            color: 'var(--at-red-1)',
            width: '20px',
            height: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '4px',
            backgroundColor: 'var(--at-red-soft)',
          }}
        >
          {nodeKey}
        </span>
        <span style={{ fontFamily: 'var(--at-serif)', fontStyle: 'italic', fontSize: '14px', color: 'var(--at-ink-1)' }}>
          {name}
        </span>
      </div>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '9px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--at-ink-4)',
        }}
      >
        {tag}
      </span>
      <p style={{ fontFamily: 'var(--at-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--at-ink-1)', margin: 0 }}>
        {description}
      </p>
    </div>
  </ExpCard>
);

const McpNetworkDiagram: React.FC = () => (
  <svg viewBox="0 0 480 320" width="100%" style={{ maxWidth: '480px', display: 'block', margin: '0 auto' }}>
    {/* Edges */}
    <line x1="240" y1="90" x2="120" y2="210" stroke="rgba(168,66,58,0.55)" strokeWidth="1.5" />
    <line x1="240" y1="90" x2="360" y2="210" stroke="rgba(168,66,58,0.55)" strokeWidth="1.5" />
    <line x1="120" y1="250" x2="360" y2="250" stroke="rgba(31,20,16,0.18)" strokeWidth="1" strokeDasharray="4,4" />

    {/* Edge labels */}
    <rect x="125" y="135" width="80" height="20" rx="10" fill="#faf3e8" stroke="rgba(168,66,58,0.4)" strokeWidth="1" />
    <text x="165" y="149" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="11" fill="#a8423a">discovers</text>
    <rect x="280" y="135" width="68" height="20" rx="10" fill="#faf3e8" stroke="rgba(168,66,58,0.4)" strokeWidth="1" />
    <text x="314" y="149" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="11" fill="#a8423a">invokes</text>

    {/* Agent (top) */}
    <rect x="180" y="50" width="120" height="55" rx="10" fill="#1f1410" />
    <text x="240" y="78" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="18" fill="#faf3e8">agent</text>
    <text x="240" y="94" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(250,243,232,0.55)" letterSpacing="1.5">orchestrator + 5 specs</text>

    {/* Gateway (bottom-left) */}
    <rect x="55" y="210" width="130" height="70" rx="10" fill="#faf3e8" stroke="#a8423a" strokeWidth="1.5" />
    <text x="120" y="240" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="18" fill="#a8423a">gateway</text>
    <text x="120" y="258" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1.5">AGENTCORE</text>

    {/* Tools (bottom-right) */}
    <rect x="295" y="210" width="130" height="70" rx="10" fill="#faf3e8" stroke="rgba(31,20,16,0.30)" strokeWidth="1" />
    <text x="360" y="240" textAnchor="middle" fontFamily="Fraunces, serif" fontStyle="italic" fontSize="18" fill="#1f1410">tools</text>
    <text x="360" y="258" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="rgba(31,20,16,0.42)" letterSpacing="1.5">REGISTERED</text>

    {/* Protocol label */}
    <text x="240" y="300" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="9" fill="rgba(31,20,16,0.42)" letterSpacing="2">PROTOCOL · MCP</text>
  </svg>
);

/* ---- Shared styles ---- */

const ConceptEyebrow: React.FC<{ label: string }> = ({ label }) => (
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
    {label}
  </span>
);

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: 'var(--at-serif)',
  fontSize: '22px',
  fontWeight: 400,
  fontStyle: 'italic',
  lineHeight: 1.15,
  color: 'var(--at-ink-1)',
  margin: 0,
};

const sectionProseStyle: React.CSSProperties = {
  fontFamily: 'var(--at-sans)',
  fontSize: 'var(--at-body-size)',
  lineHeight: 'var(--at-body-leading)',
  color: 'var(--at-ink-1)',
  margin: 0,
  maxWidth: '560px',
};

const codeBlockStyle: React.CSSProperties = {
  fontFamily: 'var(--at-mono)',
  fontSize: '14px',
  lineHeight: 1.7,
  color: 'var(--at-ink-1)',
  backgroundColor: 'var(--at-cream-2)',
  borderRadius: '8px',
  padding: '14px 16px',
  margin: 0,
  overflowX: 'auto',
  whiteSpace: 'pre',
};

export default McpDetail;
