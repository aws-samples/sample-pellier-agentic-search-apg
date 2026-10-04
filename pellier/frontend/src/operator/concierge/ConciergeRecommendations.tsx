/**
 * Replacement recommendations, as an editorial row rather than a product grid.
 *
 * Two or three cards, each one hydrated entirely from the backend's canonical
 * recommendation object. Price, product identity and availability come from that
 * object and from nowhere else, so the narrative above and the card below cannot
 * disagree — the failure this whole workflow was built around.
 *
 * What is deliberately absent: sale badges, star ratings, review counts, discount
 * copy, loyalty savings, and any control that would send, swap or reserve. This
 * surface performs no write, so it offers no affordance that implies one.
 */

import React from 'react'

import ResponsiveImage from '../../components/ResponsiveImage'
import type {
  ConciergeRecommendation,
  ConciergeReplacement,
} from '../../services/operatorConcierge'

const ROLE_LABELS: Record<string, string> = {
  best_match: 'Best match',
  alternative: 'Alternative',
}

function money(value: number): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

/** Availability tone, for the one visual cue that is never the only cue. */
function availabilityTone(status: string): string {
  if (status === 'reconciled_in_stock') return 'reconciled'
  if (status === 'ledger_cache_disagreement') return 'disagreement'
  if (status === 'observed_in_stock' || status === 'observed_out_of_stock') {
    return 'observed'
  }
  return 'unverified'
}

const Card: React.FC<{ item: ConciergeRecommendation }> = ({ item }) => {
  const evidence = item.inventoryEvidence
  const tone = availabilityTone(evidence.status)
  return (
    <li
      className="operator-concierge-product"
      data-role={item.role}
      data-availability={tone}
      data-testid={`operator-concierge-product-${item.productId}`}
    >
      <div className="operator-concierge-product-figure">
        {item.imgUrl ? (
          <ResponsiveImage
            src={item.imgUrl}
            alt={item.name}
            loading="lazy"
            decoding="async"
            /* The catalog ships 4:5 masters at 1122x1402 with 480/960 derivatives. */
            width={104}
            height={130}
            sizes="104px"
          />
        ) : null}
      </div>
      <div className="operator-concierge-product-body">
        <span className="operator-concierge-eyebrow">
          {ROLE_LABELS[item.role] ?? item.role}
        </span>
        <p className="operator-concierge-product-name">{item.name}</p>
        <p className="operator-concierge-product-meta">
          {[item.brand, item.category].filter(Boolean).join(' · ')}
        </p>
        <p className="operator-concierge-product-price">{money(item.price)}</p>

        <div className="operator-concierge-product-availability">
          <span className="operator-concierge-eyebrow">Current availability</span>
          {/* The backend's own sentence. Never assembled here, so it cannot drift
              from the evidence object it came from. */}
          <p data-testid={`operator-concierge-availability-${item.productId}`}>
            {item.availabilitySentence}
          </p>
          {evidence.aggregateCacheStale ? (
            <p className="operator-concierge-product-note">
              Per-warehouse stock reconciles; the aggregate catalog cache reads{' '}
              {evidence.catalogCacheQuantity} against the ledger&rsquo;s{' '}
              {evidence.catalogLedgerQuantity}.
            </p>
          ) : null}
          {evidence.disagreements?.length ? (
            <p className="operator-concierge-product-note">
              {evidence.disagreements.length === 1 ? 'One location' : 'Locations'}{' '}
              disagree with the ledger:{' '}
              {evidence.disagreements
                .map(
                  (d) =>
                    `${d.warehouseId} cache ${d.cacheQuantity}, ledger ${d.ledgerQuantity}`,
                )
                .join('; ')}
              .
            </p>
          ) : null}
        </div>

        {item.fitReasons.length ? (
          <div className="operator-concierge-product-fit">
            <span className="operator-concierge-eyebrow">Why it fits</span>
            <ul>
              {item.fitReasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* Labelled. A bare "1" under a product card reads as a list number or a
            footnote rather than as the identifier an operator quotes. */}
        <span className="operator-concierge-product-sku">SKU {item.productId}</span>
      </div>
    </li>
  )
}

interface Props {
  replacement: ConciergeReplacement
}

const ConciergeRecommendations: React.FC<Props> = ({ replacement }) => {
  const available = replacement.available ?? []
  const close = replacement.closeMatches ?? []
  const grounding = replacement.grounding
  const retrieval = replacement.retrieval
  const controls = replacement.plan?.describeHardControls ?? []

  // The request could not be grounded. Showing the order lines it could have meant is
  // more useful than an apology, and it is the operator who picks — not a model.
  if (grounding && grounding.resolved === false) {
    return (
      <section
        className="operator-concierge-replacement"
        data-testid="operator-concierge-clarify"
      >
        {grounding.candidates?.length ? (
          <>
            <span className="operator-concierge-eyebrow">Order lines that match</span>
            <ul className="operator-concierge-candidates">
              {grounding.candidates.map((candidate) => (
                <li key={candidate.orderId}>
                  <span className="operator-concierge-candidate-order">
                    #{candidate.orderId}
                  </span>
                  <span className="operator-concierge-candidate-name">
                    {candidate.name}
                  </span>
                  <span className="operator-concierge-candidate-price">
                    paid {money(candidate.pricePaid)}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
    )
  }

  if (!available.length && !close.length) {
    return replacement.coverageNote ? (
      <section
        className="operator-concierge-replacement"
        data-testid="operator-concierge-recommendations"
      >
        <p className="operator-concierge-product-note">{replacement.coverageNote}</p>
      </section>
    ) : null
  }

  return (
    <section
      className="operator-concierge-replacement"
      data-testid="operator-concierge-recommendations"
    >
      {available.length ? (
        <>
          <span className="operator-concierge-eyebrow">
            Available replacements
          </span>
          <ul className="operator-concierge-products">
            {available.map((item) => (
              <Card item={item} key={item.productId} />
            ))}
          </ul>
        </>
      ) : null}

      {close.length ? (
        <>
          {/* A separate heading, because these are NOT available replacements. The
              operator has to be able to tell at a glance which set is which. */}
          <span className="operator-concierge-eyebrow">
            Close matches &middot; availability not verified
          </span>
          <ul className="operator-concierge-products">
            {close.map((item) => (
              <Card item={item} key={item.productId} />
            ))}
          </ul>
        </>
      ) : null}

      {replacement.coverageNote ? (
        <p className="operator-concierge-product-note">{replacement.coverageNote}</p>
      ) : null}

      {retrieval ? (
        <dl
          className="operator-concierge-retrieval"
          data-testid="operator-concierge-retrieval"
        >
          <div>
            <dt>Hybrid search</dt>
            <dd>
              {retrieval.poolSize} candidates
              {retrieval.rerankApplied ? ` · ${retrieval.reranked} reranked` : ''}
            </dd>
          </div>
          {controls.length ? (
            <div>
              <dt>Hard constraints</dt>
              {/* Enforced in PostgreSQL before ranking, which is why they can be
                  stated as facts about the result rather than as intentions. */}
              <dd>{controls.join(' · ')}</dd>
            </div>
          ) : null}
          {typeof retrieval.reconciledCount === 'number' ? (
            <div>
              <dt>Reconciled to ledger</dt>
              <dd>
                {retrieval.reconciledCount} of {retrieval.reranked}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </section>
  )
}

export default ConciergeRecommendations
