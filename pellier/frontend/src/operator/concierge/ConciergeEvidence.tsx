/**
 * Facts with their source and confidence attached.
 *
 * Two-column definition rows rather than a dense Markdown table, and each row shows
 * whether the fact was established, asserted by something weaker, or unavailable.
 * That distinction is load-bearing: Jessica has a support ticket stating a return was
 * received while `pellier.returns` holds no row, and the surface must be able to show
 * the disagreement rather than resolving it into a false certainty.
 */

import React from 'react'
import { Link } from 'react-router-dom'
import ServiceIdentity from '../../shared/ServiceIdentity'

import type { ConciergeEvidenceItem } from '../../services/operatorConcierge'

const STATUS_COPY: Record<string, string> = {
  verified: 'Established',
  unverified: 'Not confirmed',
  unavailable: 'Unavailable',
}

/** The epistemic role, stated plainly rather than implied by styling alone. */
const ROLE_COPY: Record<string, string> = {
  fact: 'Fact',
  context: 'Reported',
  inference: 'Inference',
}

interface Props {
  items: ConciergeEvidenceItem[]
  customerId?: string
}

const ConciergeEvidence: React.FC<Props> = ({ items, customerId }) => {
  if (!items.length) return null
  const incomplete = items.some((i) => i.status !== 'verified')

  return (
    <section className="operator-concierge-evidence"
             data-testid="operator-concierge-evidence">
      <span className="operator-concierge-eyebrow">Evidence</span>
      <dl className="operator-concierge-evidence-rows">
        {items.map((item, index) => (
          <div className="operator-concierge-evidence-row" key={`${item.kind}-${index}`}
               data-evidence-status={item.status}
               data-evidence-role={item.role ?? 'fact'}>
            <dt>{item.label ?? item.kind}</dt>
            <dd>
              {item.note ? (
                <span className="operator-concierge-evidence-note">{item.note}</span>
              ) : null}
              <span className="operator-concierge-evidence-meta">
                {ROLE_COPY[item.role ?? 'fact'] ?? item.role}
                {' · '}
                {STATUS_COPY[item.status] ?? item.status}
                {item.recordId ? ` · ${item.recordId}` : ''}
              </span>
              {item.source ? <ServiceIdentity source={item.source} /> : null}
              {item.kind === 'replacement_operation' && item.recordId && customerId ? (
                <Link className="operator-client-chat-link" to={`/observatory/replacement?customer=${encodeURIComponent(customerId)}&replacement=${encodeURIComponent(item.recordId)}`}>Inspect recovery evidence</Link>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
      {/* Nuance, not failure. No "Conflict!" or "Data mismatch!". */}
      {incomplete ? (
        <p className="operator-concierge-evidence-caveat">Evidence is incomplete.</p>
      ) : null}
    </section>
  )
}

export default ConciergeEvidence
