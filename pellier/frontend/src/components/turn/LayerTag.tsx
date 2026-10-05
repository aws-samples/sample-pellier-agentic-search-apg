/**
 * The Builder view's layer chip: Router, Aurora, Memory, Identity, Approval,
 * Request, Policy, Skills. Mono, copper-tinted, never a status. A shopper's
 * credit ask is a Request; only a credit a person approves is an Approval.
 */
import type { ReactNode } from 'react'

export default function LayerTag({ children }: { children: ReactNode }) {
  return <span className="tn-layer" data-testid="layer-tag">{children}</span>
}
