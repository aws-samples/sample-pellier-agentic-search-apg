/**
 * EvaluationsDetail — Architecture detail page for Evaluations.
 *
 * Agent quality measurement and tracking — accuracy, latency, citation rates.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';

const EvaluationsDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'evaluations');

  return (
    <DetailPageShell
      numeral="VII"
      conceptName="Evaluations"
      category="owned"
      title="Evaluations, measured."
      prose="Evaluation scorecards measure agent accuracy, latency percentiles, and citation rates. Version-over-version trends track quality improvements as agents are refined. Each evaluation recipe tests a specific capability."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Every agent has a scorecard: accuracy, latency P50/P95, and citation rate. These are the four numbers that matter.',
        },
        {
          numeral: 'ii.',
          text: 'Version-over-version trends show whether changes improve or regress quality. Track the trend, not just the snapshot.',
        },
        {
          numeral: 'iii.',
          text: 'Evaluation recipes are specific test cases. Each recipe tests one capability — search accuracy, recommendation relevance, pricing correctness.',
        },
      ]}
      liveState={{
        label: 'Current evaluation state across all agents. Shows aggregate accuracy and the number of evaluation recipes tracked.',
        values: [
          { label: 'Agents evaluated', value: '5' },
          { label: 'Avg accuracy', value: '91%' },
          { label: 'Recipes', value: '12' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Evaluations" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Scorecard structure */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="The scorecard" />
              <h3 style={titleStyle}>Four metrics, one card.</h3>
              <p style={proseStyle}>
                Each agent's scorecard captures accuracy (how often the response is correct),
                latency (P50 and P95 response times), and citation rate (how often the agent
                grounds its response in data). These four numbers tell you if the agent is
                working.
              </p>
            </div>
          </ExpCard>

          {/* Sample scorecards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <ScorecardCard
              agent="Search"
              accuracy={94}
              latencyP50={340}
              latencyP95={620}
              citationRate={88}
            />
            <ScorecardCard
              agent="Recommendation"
              accuracy={89}
              latencyP50={420}
              latencyP95={780}
              citationRate={92}
            />
            <ScorecardCard
              agent="Pricing"
              accuracy={97}
              latencyP50={180}
              latencyP95={310}
              citationRate={95}
            />
            <ScorecardCard
              agent="Inventory"
              accuracy={91}
              latencyP50={220}
              latencyP95={450}
              citationRate={85}
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

const ScorecardCard: React.FC<{
  agent: string;
  accuracy: number;
  latencyP50: number;
  latencyP95: number;
  citationRate: number;
}> = ({ agent, accuracy, latencyP50, latencyP95, citationRate }) => (
  <ExpCard>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <span style={{ fontFamily: 'var(--at-serif)', fontStyle: 'italic', fontSize: '18px', color: 'var(--at-ink-1)' }}>
        {agent}
      </span>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
        <MetricCell label="Accuracy" value={`${accuracy}%`} />
        <MetricCell label="P50 latency" value={`${latencyP50}ms`} />
        <MetricCell label="P95 latency" value={`${latencyP95}ms`} />
        <MetricCell label="Citation rate" value={`${citationRate}%`} />
      </div>
    </div>
  </ExpCard>
);

const MetricCell: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
    <span style={{ fontFamily: 'var(--at-mono)', fontSize: '9px', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--at-ink-4)' }}>
      {label}
    </span>
    <span style={{ fontFamily: 'var(--at-serif)', fontSize: '20px', fontWeight: 400, color: 'var(--at-ink-1)', letterSpacing: '-0.02em' }}>
      {value}
    </span>
  </div>
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

export default EvaluationsDetail;
