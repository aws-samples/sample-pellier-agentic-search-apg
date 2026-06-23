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
import { useCatalogStats } from '../../../../hooks/useCatalogStats';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';
import { ARCHITECTURE_CODE_BLOCK, ARCHITECTURE_CODE_BLOCK_COMPACT } from './codeStyles';

const GroundingDetail: React.FC = () => {
  const { data, loading, error, refetch } = useAtelierData<ArchitectureConcept[]>({
    key: 'architecture',
  });
  const catalogStats = useCatalogStats();

  const concept = data?.find((c) => c.slug === 'grounding');
  const productCount =
    catalogStats?.product_count != null ? String(catalogStats.product_count) : '–';

  return (
    <DetailPageShell
      numeral="I"
      conceptName="Grounding"
      category="live"
      title="Grounding, factual."
      prose="The live Boutique path grounds recommendations in Aurora PostgreSQL: catalog rows, inventory quantities, return policy data, and pgvector/FTS retrieval. The point is not a generic knowledge base; it is product facts the UI can verify."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Every product recommendation is verified against the catalog. If the product doesn\'t exist in Aurora, the agent doesn\'t recommend it.',
        },
        {
          numeral: 'ii.',
          text: 'Semantic grounding uses pgvector and Postgres FTS to find relevant catalog rows. Prices, quantities, and policies still come from structured Aurora data.',
        },
        {
          numeral: 'iii.',
          text: 'Grounding is what keeps the assistant from inventing products. Aurora is the source of truth; model prose is the presentation layer.',
        },
      ]}
      liveState={{
        label: 'Current grounding state. Shows the Aurora-backed sources the assistant uses to anchor responses in facts.',
        values: [
          { label: 'Products', value: productCount },
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
              <h3 style={titleStyle}>Four sources, one truth.</h3>
              <p style={proseStyle}>
                The assistant grounds shopper-facing answers in Aurora PostgreSQL data: product
                catalog rows, inventory quantities, return policies, and the tool registry used
                by workshop discovery. Retrieval finds candidates; structured columns keep the
                answer factual.
              </p>
            </div>
          </ExpCard>

          {/* Source cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <SourceCard
              name="product_catalog"
              description="Products with names, brands, prices, descriptions, tags, quantities, and 1024-dim Cohere Embed v4 vectors."
              query="SELECT product_id, name, brand, price, quantity FROM product_catalog WHERE product_id = $1;"
            />
            <SourceCard
              name="return_policies"
              description="Return rules and conditions per product category. The agent cites these when answering return questions."
              query="SELECT policy_text FROM return_policies WHERE category = $1;"
            />
            <SourceCard
              name="description_tsv + embedding"
              description="Hybrid retrieval uses pgvector for meaning and Postgres FTS for literal terms before optional rerank."
              query="SELECT name, ts_rank_cd(description_tsv, $1) AS text_rank FROM product_catalog WHERE description_tsv @@ $1;"
            />
            <SourceCard
              name="tools (registry)"
              description="Aurora-backed teaching surface for tool discovery; optional Gateway can publish the same tool surface over MCP."
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
          ...ARCHITECTURE_CODE_BLOCK_COMPACT,
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
  fontFamily: 'var(--at-serif)', fontSize: '22px', fontWeight: 500,
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

export default GroundingDetail;
