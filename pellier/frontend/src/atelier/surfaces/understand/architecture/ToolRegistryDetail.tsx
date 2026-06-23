/**
 * ToolRegistryDetail — Architecture detail page for Aurora Tool Registry.
 *
 * Semantic tool discovery via pgvector embeddings.
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

const ToolRegistryDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'tool-registry');

  return (
    <DetailPageShell
      numeral="VII"
      conceptName="Tool Registry"
      category="workshop"
      title="Tools, discovered."
      prose="The Aurora tool registry is the live workshop teaching surface for semantic discovery. Tool descriptions are embedded, searched with pgvector, and compared with the optional MCP Gateway view. The Boutique default still calls in-process Strands tools unless Gateway is configured."
      seeInBoutique={{
        href: '/?ask=Show+me+linen+pieces+like+the+Camp+Shirt',
        label: 'See tool discovery fire on the storefront',
      }}
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Tools are registered with name, description, and a 1024-dim Cohere Embed v4 vector. The embedding captures what the tool does, not just its name.',
        },
        {
          numeral: 'ii.',
          text: 'Discovery is a cosine similarity query: embed the agent need, find the closest tool descriptions, and show the ranking as telemetry.',
        },
        {
          numeral: 'iii.',
          text: 'Fixture labels on the Understand · Tools surface: twelve shipped baseline; floor_check is the Builder\'s Session exercise until its stub is replaced – then /api/atelier/build-state reflects shipped.',
        },
      ]}
      liveState={{
        label: 'Current tool registry state. Aurora ranks tool descriptions for the workshop discovery demo; optional Gateway publishes the callable surface over MCP.',
        values: [
          { label: 'Tools registered', value: '13' },
          { label: 'Shipped (baseline image)', value: '12' },
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
                The workshop demo describes what the turn needs in natural language, embeds that
                description, and asks Aurora for the nearest tool records. This is semantic
                discovery over a vector index; the production dispatcher can still call the
                known in-process tool directly.
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
                  { name: 'find_pieces_hybrid', status: 'shipped' },
                  { name: 'explore_collection', status: 'shipped' },
                  { name: 'side_by_side', status: 'shipped' },
                  { name: 'style_match', status: 'shipped' },
                  { name: 'whats_trending', status: 'shipped' },
                  { name: 'price_intelligence', status: 'shipped' },
                  { name: 'floor_check', status: 'exercise' },
                  { name: 'running_low', status: 'shipped' },
                  { name: 'returns_and_care', status: 'shipped' },
                  { name: 'restock_shelf', status: 'shipped' },
                  { name: 'process_return', status: 'shipped' },
                  { name: 'escalate_to_stylist', status: 'shipped' },
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
  fontFamily: 'var(--at-serif)', fontSize: '22px', fontWeight: 400,
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

export default ToolRegistryDetail;
