/**
 * ToolRegistryDetail — Architecture detail page for Tool Registry / Gateway.
 *
 * Semantic tool discovery and invocation via pgvector embeddings.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';

const ToolRegistryDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'tool-registry');

  return (
    <DetailPageShell
      numeral="IV"
      conceptName="Tool Registry"
      category="both"
      title="Tools, discovered."
      prose="Nine tools registered in Aurora PostgreSQL with pgvector embeddings. The gateway enables semantic discovery — agents find tools by describing what they need, not by knowing function names. HNSW indexing provides sub-millisecond lookup."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Tools are registered with name, description, and a 1024-dim Cohere Embed v4 vector. The embedding captures what the tool does, not just its name.',
        },
        {
          numeral: 'ii.',
          text: 'Discovery is a cosine similarity query: embed the agent\'s need, find the closest tools. HNSW indexing makes this sub-millisecond.',
        },
        {
          numeral: 'iii.',
          text: 'Six tools are shipped, three are exercises. The registry doesn\'t care — it discovers whatever is registered.',
        },
      ]}
      liveState={{
        label: 'Current tool registry state. Tools are registered at boot with pgvector embeddings for semantic discovery.',
        values: [
          { label: 'Tools registered', value: '9' },
          { label: 'Shipped', value: '6' },
          { label: 'Index', value: 'HNSW' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Tool Registry" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Discovery flow */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="Discovery flow" />
              <h3 style={titleStyle}>Describe the need, find the tool.</h3>
              <p style={proseStyle}>
                The agent doesn't hardcode tool names. It describes what it needs in natural
                language, and the registry returns the closest matches by cosine similarity.
                This is the architectural punchline — semantic discovery over a vector index.
              </p>
            </div>
          </ExpCard>

          {/* Registration + Discovery code */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <ExpCard>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <SectionLabel label="Registration" />
                <pre style={codeStyle}>{`# Register tool with embedding
INSERT INTO tools (name, description, embedding)
VALUES ($1, $2, $3);`}</pre>
              </div>
            </ExpCard>
            <ExpCard>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <SectionLabel label="Discovery" />
                <pre style={codeStyle}>{`# Discover by semantic similarity
SELECT name,
       1 - (embedding <=> $1) AS similarity
FROM tools
ORDER BY embedding <=> $1
LIMIT 5;`}</pre>
              </div>
            </ExpCard>
          </div>

          {/* Tool list */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="Registered tools" />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
                {[
                  { name: 'find_pieces', status: 'shipped' },
                  { name: 'explore_collection', status: 'shipped' },
                  { name: 'side_by_side', status: 'shipped' },
                  { name: 'whats_trending', status: 'shipped' },
                  { name: 'price_intelligence', status: 'shipped' },
                  { name: 'returns_and_care', status: 'shipped' },
                  { name: 'floor_check', status: 'exercise' },
                  { name: 'restock_shelf', status: 'exercise' },
                  { name: 'low_stock', status: 'exercise' },
                ].map((tool) => (
                  <div
                    key={tool.name}
                    style={{
                      padding: '10px 14px',
                      borderRadius: '8px',
                      border: tool.status === 'shipped'
                        ? '1px solid var(--at-card-border)'
                        : '1px dashed var(--at-red-1)',
                      backgroundColor: tool.status === 'shipped'
                        ? 'var(--at-cream-2)'
                        : 'transparent',
                    }}
                  >
                    <span
                      style={{
                        fontFamily: 'var(--at-mono)',
                        fontSize: '12px',
                        color: tool.status === 'shipped' ? 'var(--at-ink-1)' : 'var(--at-red-1)',
                      }}
                    >
                      {tool.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </ExpCard>
        </div>
      )}
    </DetailPageShell>
  );
};

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

export default ToolRegistryDetail;
