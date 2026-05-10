/**
 * GroundingDetail — Architecture detail page for Grounding.
 *
 * Factual anchoring via Aurora PostgreSQL — ensuring agent responses
 * are grounded in real data rather than hallucinated.
 *
 * Requirements: 7.1, 7.6, 7.7
 */

import React from 'react';
import DetailPageShell from './DetailPageShell';
import { ExpCard } from '../../../components';
import { useAtelierData } from '../../../hooks/useAtelierData';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';

const GroundingDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });

  const concept = data?.find((c) => c.slug === 'grounding');

  return (
    <DetailPageShell
      numeral="VIII"
      conceptName="Grounding"
      category="both"
      title="Grounding, factual."
      prose="All agent responses are grounded in data from Aurora PostgreSQL — product catalog, pricing, inventory, and return policies. pgvector embeddings enable semantic grounding, ensuring recommendations are factually anchored rather than hallucinated."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Every product recommendation is verified against the catalog. If the product doesn\'t exist in Aurora, the agent doesn\'t recommend it.',
        },
        {
          numeral: 'ii.',
          text: 'Semantic grounding uses pgvector to find related facts. The embedding decides what\'s relevant — prices, availability, return policies.',
        },
        {
          numeral: 'iii.',
          text: 'Grounding is the difference between a helpful agent and a hallucinating one. Aurora is the source of truth.',
        },
      ]}
      liveState={{
        label: 'Current grounding state. Shows the data sources the agent uses to anchor its responses in facts.',
        values: [
          { label: 'Products', value: '444' },
          { label: 'Embeddings', value: '1024d' },
          { label: 'Index', value: 'HNSW' },
        ],
      }}
    >
      {loading && <DetailLoadingState />}
      {error && <DetailErrorState message={error} onRetry={refetch} />}
      {!loading && !error && !concept && <DetailEmptyState conceptName="Grounding" />}
      {!loading && !error && concept && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Grounding sources */}
          <ExpCard>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <SectionLabel label="Data sources" />
              <h3 style={titleStyle}>Four tables, one truth.</h3>
              <p style={proseStyle}>
                The agent grounds every response in four Aurora PostgreSQL tables: product catalog
                (names, prices, descriptions), inventory (stock levels), return policies (rules
                and conditions), and the knowledge base (semantic facts via pgvector).
              </p>
            </div>
          </ExpCard>

          {/* Source cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <SourceCard
              name="product_catalog"
              description="444 products with names, brands, prices, descriptions, tags, and 1024-dim Cohere Embed v4 vectors."
              query="SELECT id, name, price, in_stock FROM product_catalog WHERE id = $1;"
            />
            <SourceCard
              name="return_policies"
              description="Return rules and conditions per product category. The agent cites these when answering return questions."
              query="SELECT policy_text FROM return_policies WHERE category = $1;"
            />
            <SourceCard
              name="knowledge_base"
              description="Semantic facts stored with pgvector embeddings. The agent queries by similarity to find relevant context."
              query="SELECT content FROM knowledge_base WHERE embedding <=> $1 < 0.3;"
            />
            <SourceCard
              name="tools (registry)"
              description="9 tool functions with semantic embeddings. Agents discover tools by describing what they need."
              query="SELECT name, similarity FROM tools ORDER BY embedding <=> $1 LIMIT 5;"
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

const SourceCard: React.FC<{
  name: string;
  description: string;
  query: string;
}> = ({ name, description, query }) => (
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
        {name}
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
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {query}
      </pre>
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

export default GroundingDetail;
