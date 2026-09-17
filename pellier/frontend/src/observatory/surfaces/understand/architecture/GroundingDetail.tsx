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
import { useObservatoryData } from '../../../hooks/useObservatoryData';
import { useCatalogStats } from '../../../../hooks/useCatalogStats';
import type { ArchitectureConcept } from '../../../types';
import { DetailLoadingState, DetailErrorState, DetailEmptyState } from './DetailStates';
import { ARCHITECTURE_CODE_BLOCK, ARCHITECTURE_CODE_BLOCK_COMPACT } from './codeStyles';
import { SectionEyebrow } from '../../../../shared';

const GroundingDetail: React.FC = () => {
  const { data, loading, error, refetch } = useObservatoryData<ArchitectureConcept[]>({
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
      prose="The live Pellier path grounds recommendations in Aurora PostgreSQL: catalog rows, inventory quantities, return policy data, and pgvector/FTS retrieval. The point is not a generic knowledge base; it is product facts the UI can verify."
      cheatSheet={[
        {
          numeral: 'i.',
          text: 'Validate product identifiers and claims against the returned Aurora rows. A grounded tool result alone does not prove that every sentence in the model response is correct.',
        },
        {
          numeral: 'ii.',
          text: 'Semantic grounding uses pgvector and Postgres FTS to find relevant catalog rows. Prices, quantities, and policies still come from structured Aurora data.',
        },
        {
          numeral: 'iii.',
          text: 'Aurora supplies product facts. Use the tool rows and final answer together to check whether the response preserves those facts.',
        },
      ]}
      liveState={{
        label: 'The product count comes from catalog statistics; embedding dimensions and index type describe the source configuration. Inspect the query plan to verify the executed access path.',
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
              description="Aurora ranks tool descriptions for discovery. Gateway publishes a separate canonical schema set; caller policy controls visible and callable tools."
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
          fontFamily: 'var(--obs-mono)',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--obs-ink-1)',
        }}
      >
        {name}
      </span>
      <p style={{ fontFamily: 'var(--obs-sans)', fontSize: '14px', lineHeight: 1.5, color: 'var(--obs-ink-1)', margin: 0 }}>
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

/* One label register on the surface. This was six identical copies of a mono
   0.22em recipe, one per detail page; mono here marked prose, not an
   identifier, which is the distinction the shared primitive restores. */
const SectionLabel: React.FC<{ label: string }> = ({ label }) => (
  <SectionEyebrow tone="muted" dot={false}>
    {label}
  </SectionEyebrow>
);

const titleStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-heading)', fontSize: '22px', fontWeight: 500,
  lineHeight: 1.15, color: 'var(--obs-ink-1)', margin: 0,
};

const proseStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-sans)', fontSize: 'var(--obs-body-size)', lineHeight: 'var(--obs-body-leading)',
  color: 'var(--obs-ink-1)', margin: 0, maxWidth: '560px',
};

const codeStyle: React.CSSProperties = {
  ...ARCHITECTURE_CODE_BLOCK,
  whiteSpace: 'pre',
};

export default GroundingDetail;
