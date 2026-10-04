/**
 * The Builder view's layer chip: Router, Aurora, Memory, Identity, Approval,
 * Policy, Skills. Mono, copper-tinted, never a status.
 */
import type { ReactNode } from 'react'

export default function LayerTag({ children }: { children: ReactNode }) {
  return <span className="tn-layer" data-testid="layer-tag">{children}</span>
}
