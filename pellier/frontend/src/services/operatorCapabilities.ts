/**
 * Capability and inventory truth, typed. No live state is decided here.
 *
 * Both contracts are backend-derived on purpose. Capability state comes from live
 * Gateway and policy state — `initiate_return` is currently published with zero
 * matching permits while `issue_credit` is not published at all, and those are
 * different causes that a frontend constant cannot tell apart. Inventory status
 * comes from one canonical object so a narrative sentence and a product card can
 * never disagree about the same product.
 *
 * This module holds types, a client, and label maps. It must not contain a
 * per-tool capability matrix.
 */

export type CapabilityState =
  | 'available'
  | 'review_required'
  | 'temporarily_unavailable'
  | 'not_enabled'

export interface Capability {
  state: CapabilityState
  /** Coarse cause. Never Cedar source, policy ids, or AWS configuration. */
  reason: string
}

export interface CapabilitySnapshot {
  capabilities: Record<string, Capability>
  observedAt: string
  source: 'agentcore' | 'unverified'
  ttlSeconds: number
  governedActionsAvailable: boolean
  cached: boolean
}

/** Restrained copy. A deliberately closed system is not an error. */
export const CAPABILITY_LABELS: Record<CapabilityState, string> = {
  available: 'Available',
  review_required: 'Review required',
  temporarily_unavailable: 'Temporarily unavailable',
  not_enabled: 'Not enabled',
}

/**
 * The banner copy for the surface as a whole.
 *
 * Never "Disconnected", "Offline", "Broken" or "Error" when governance has closed
 * the write rail on purpose: the reads are working, the operator can still do most
 * of their job, and alarming them would be inaccurate as well as unkind.
 */
export interface GovernedUnavailableCopy {
  title: string
  detail: string
}

export const GOVERNED_UNAVAILABLE_COPY: GovernedUnavailableCopy = {
  title: 'Governed actions temporarily unavailable',
  detail: 'Client investigation and recommendations remain available.',
}

/**
 * Explain a fail-closed managed state without exposing control-plane ids or
 * policy source. A missing managed resource is a deployment-readiness fact,
 * not the same thing as a Gateway whose policy deliberately closes a write.
 */
export function governedUnavailableCopy(
  capabilities: CapabilitySnapshot,
): GovernedUnavailableCopy {
  const capabilityMap = capabilities.capabilities ?? {}
  const governed = [
    'initiate_return',
    'escalate_to_human',
    'issue_credit',
  ]
    .map((tool) => capabilityMap[tool])
    .filter((capability): capability is Capability => Boolean(capability))

  if (
    governed.length > 0
    && governed.every(
      (capability) =>
        capability.state === 'temporarily_unavailable'
        && capability.reason === 'managed_resources_missing',
    )
  ) {
    return {
      title: 'Managed action boundary not ready',
      detail:
        'This environment has not completed managed-action provisioning. Client investigation and recommendations remain available.',
    }
  }

  return GOVERNED_UNAVAILABLE_COPY
}

/**
 * `verified` is reserved for ledger-reconciled state, which nothing produces yet.
 * A reading from `warehouse_inventory` is an observation of a cache — migration 013
 * names `inventory_ledger` the source of truth and both quantity columns caches.
 */
export type InventoryStatus =
  | 'observed_in_stock'
  | 'observed_out_of_stock'
  | 'availability_not_verified'

export interface InventoryLocation {
  warehouseId: string
  quantity: number
  displayName: string
  city: string
  shipWindow: string
}

export interface InventoryEvidence {
  productId: string
  status: InventoryStatus
  /** Null whenever the status is not verified: there is no number to render. */
  availableQuantity: number | null
  scope: 'warehouse' | null
  locations: InventoryLocation[]
  source: string
  observedAt: string
  /**
   * The aggregate column, carried for transparency and NOT an availability claim.
   * It is a seed value, so it establishes nothing about real stock.
   */
  catalogCacheQuantity: number | null
  /** 'cache' or 'source_of_truth'. Never present a cache reading as reconciled. */
  authority: 'cache' | 'source_of_truth' | null
  reconciledToLedger: boolean
  note: string
  isObserved: boolean
  supportsAvailabilityClaim: boolean
}

/** The only sentence a surface may print about availability. */
export function describeAvailability(evidence: InventoryEvidence): string {
  if (evidence.status === 'availability_not_verified') return 'Availability not verified.'
  if (evidence.status === 'observed_out_of_stock') return 'No units currently available.'
  const count = evidence.availableQuantity ?? 0
  const unit = count === 1 ? 'unit' : 'units'
  if (evidence.locations.length === 1) {
    return `${count} ${unit} currently available at ${evidence.locations[0].warehouseId}.`
  }
  return `${count} ${unit} currently available across ${evidence.locations.length} locations.`
}
