/**
 * RuntimeDetail — Architecture detail page for Runtime Envelope.
 *
 * Managed/deployment envelope around the app-layer dispatcher and tools.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';
import { ARCHITECTURE_CODE_BLOCK } from './codeStyles';

const RuntimeDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'runtime');

  return (
    <DetailPageShell
      numeral="VI"
      conceptName="Runtime Envelope"
      category="optional"
      title="Runtime, bounded."
      prose="Runtime is the envelope around execution: model calls, memory, optional Gateway, and observability. In this repository, the Boutique default flow lives in the app service layer; AgentCore Runtime concepts are introduced as the managed deployment pattern around those same contracts."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'The app-layer runtime is explicit: triage, dispatcher, specialist/tool call, SSE telemetry, reply. That is the path participants see in Sessions.',
        },
        {
          numeral: 'ii.',
          text: 'Managed runtime concepts matter at deployment: cold starts, identity, memory, Gateway connectivity, and trace export.',
        },
        {
          numeral: 'iii.',
          text: 'The workshop separates what the code owns from what the platform can operate, so the architecture page does not imply every request uses a hidden graph runtime.',
        },
      ]}
      liveState={{
        label: 'Current runtime envelope. Shows the app-layer execution path plus optional managed services.',
        values: [
          { label: 'Default path', value: 'Dispatcher' },
          { label: 'Memory', value: 'Active' },
          { label: 'Gateway', value: 'Optional' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Runtime Envelope" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Runtime layers */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="The layers" />
              <h3 style={titleStyle}>Seven visible steps, one request.</h3>
              <p style={proseStyle}>
                A Boutique request flows through visible steps: fast-path check, intent
                classification, skill routing, dispatcher handoff, specialist execution,
                tool invocation, and response streaming. Sessions and Telemetry render these
                steps directly.
              </p>
              <RuntimeLayersDiagram />
            </div>
          </ExpCard>

          {/* Layer cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <LayerCard
              name="Fast-path"
              timing="~5ms"
              description="Deterministic greeting, thanks, and meta handling before any specialist work."
            />
            <LayerCard
              name="Intent classification"
              timing="~120ms"
              description="Keyword and pattern routing in services/chat.py picks pricing, inventory, support, search, or recommendation."
            />
            <LayerCard
              name="Skill routing"
              timing="~120ms"
              description="SkillRouter may load one persona skill for this turn — the-packing-list (Marco), the-gift-table (Anna), or the-makers-shelf (Theo)."
            />
            <LayerCard
              name="Specialist execution"
              timing="~800ms"
              description="The owning specialist composes the response using persona context, memory, and tool results."
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

const LayerCard: React.FC<{
  name: string;
  timing: string;
  description: string;
}> = ({ name, timing, description }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
        <span style={{ fontFamily: 'var(--at-serif)', fontStyle: 'italic', fontSize: '16px', color: 'var(--at-ink-1)' }}>
          {name}
        </span>
        <span style={{ fontFamily: 'var(--at-mono)', fontSize: '11px', color: 'var(--at-ink-4)' }}>
          {timing}
        </span>
      </div>
      <p style={{ fontFamily: 'var(--at-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--at-ink-1)', margin: 0 }}>
        {description}
      </p>
    </div>
  </ExpCard>
);

const RuntimeLayersDiagram: React.FC = () => (
  <svg viewBox="0 0 700 280" width="100%" style={{ maxWidth: '800px', display: 'block', margin: '0 auto' }}>
    {/* Layer bars stacked */}
    {[
      { label: 'fast-path', width: 40, color: 'rgba(107,140,94,0.45)' },
      { label: 'intent', width: 110, color: 'rgba(168,66,58,0.35)' },
      { label: 'skill-router', width: 110, color: 'rgba(168,66,58,0.25)' },
      { label: 'orchestrator', width: 210, color: 'rgba(31,20,16,0.20)' },
      { label: 'specialist', width: 390, color: 'rgba(31,20,16,0.14)' },
      { label: 'tools', width: 280, color: 'rgba(168,66,58,0.18)' },
      { label: 'stream', width: 560, color: 'rgba(107,140,94,0.25)' },
    ].map((layer, i) => (
      <g key={layer.label}>
        <rect x="120" y={16 + i * 34} width={layer.width} height="26" rx="5" fill={layer.color} />
        <text x="110" y={34 + i * 34} textAnchor="end" fontFamily="JetBrains Mono, monospace" fontSize="13" fill="rgba(31,20,16,0.75)" letterSpacing="0.5">
          {layer.label}
        </text>
      </g>
    ))}
    {/* Time axis */}
    <line x1="120" y1="262" x2="680" y2="262" stroke="rgba(31,20,16,0.2)" strokeWidth="1" />
    <text x="400" y="276" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="11" fill="rgba(31,20,16,0.55)" letterSpacing="2">TIME →</text>
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

export default RuntimeDetail;
