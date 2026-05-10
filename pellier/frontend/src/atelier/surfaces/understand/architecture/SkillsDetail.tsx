/**
 * SkillsDetail — Architecture detail page for Skills.
 *
 * Persona-routed runtime capabilities — style-advisor and gift-concierge.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';

const SkillsDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'skills');

  return (
    <DetailPageShell
      numeral="V"
      conceptName="Skills"
      category="teaching"
      title="Skills, persona-routed."
      prose="Two skills — style-advisor and gift-concierge — are injected at runtime based on persona context. The SkillRouter (Claude Haiku 4.5) evaluates each turn and activates the appropriate skill when the conversation signals a styling question or gift occasion."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Skills are not agents. They\'re capabilities injected into the agent\'s tool set at runtime based on persona context.',
        },
        {
          numeral: 'ii.',
          text: 'The SkillRouter is a lightweight classifier (Haiku 4.5) that evaluates each turn. If the conversation signals a styling question, style-advisor activates.',
        },
        {
          numeral: 'iii.',
          text: 'Skills are persona-routed: the same conversation with different personas may activate different skills based on their context and preferences.',
        },
      ]}
      liveState={{
        label: 'Current skill activation state. The SkillRouter evaluates each turn and activates skills based on persona context.',
        values: [
          { label: 'Skills available', value: '2' },
          { label: 'Router model', value: 'Haiku 4.5' },
          { label: 'Active', value: 'None' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Skills" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Two skill cards side by side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <SkillCard
              name="style-advisor"
              trigger="Styling questions, outfit advice, fabric recommendations"
              description="Boutique editorial voice for describing products, fit, fabric, and styling. Activates when the agent is recommending or describing pieces."
              example='"What would go well with linen trousers for a summer evening?"'
            />
            <SkillCard
              name="gift-concierge"
              trigger="Gift occasions, milestone celebrations, gift wrapping"
              description="Gift-occasion logic for recommendations — milestone vs casual, price-band etiquette, gift-message tone, packaging and timing."
              example='"I need a thoughtful gift for someone who loves ceramics."'
            />
          </div>

          {/* SkillRouter flow */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="The routing flow" />
              <h3 style={titleStyle}>Turn arrives, router decides.</h3>
              <p style={proseStyle}>
                Every turn passes through the SkillRouter before reaching the specialist agents.
                The router is a small classifier call (~120ms) that decides whether to inject a
                skill into the agent's tool set for this turn.
              </p>
              <pre style={codeStyle}>{concept.codeSnippet}</pre>
            </div>
          </ExpCard>
        </div>
      )}
    </DetailPageShell>
  );
};

/* ---- Sub-components ---- */

const SkillCard: React.FC<{
  name: string;
  trigger: string;
  description: string;
  example: string;
}> = ({ name, trigger, description, example }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--at-ink-1)',
        }}
      >
        {name}
      </span>
      <div>
        <span style={{ fontFamily: 'var(--at-mono)', fontSize: '9px', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--at-ink-4)' }}>
          Triggers on
        </span>
        <p style={{ fontFamily: 'var(--at-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--at-ink-1)', margin: '4px 0 0 0' }}>
          {trigger}
        </p>
      </div>
      <p style={{ fontFamily: 'var(--at-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--at-ink-1)', margin: 0 }}>
        {description}
      </p>
      <div
        style={{
          fontFamily: 'var(--at-serif)',
          fontStyle: 'italic',
          fontSize: '14px',
          color: 'var(--at-ink-1)',
          padding: '10px 14px',
          backgroundColor: 'var(--at-cream-2)',
          borderRadius: '8px',
          borderLeft: '2px solid var(--at-red-1)',
        }}
      >
        {example}
      </div>
    </div>
  </ExpCard>
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

export default SkillsDetail;
