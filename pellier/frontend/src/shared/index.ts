/**
 * Shared atoms used by BOTH the Pellier storefront and the Observatory
 * observatory. Importing from `../../shared` (or `../shared`) keeps
 * the two surfaces visually and semantically aligned.
 */

/* ---- Design primitives ---------------------------------------------------
 * The five shapes the Observatory and the Operator desk both compose:
 * a section label, a card, a table, a state, and an absence. Their sizes are
 * inside the type-floor guard's scan roots, so a drift here fails a test
 * rather than reaching two surfaces at once.
 * ------------------------------------------------------------------------ */
export { SectionEyebrow } from './SectionEyebrow'
export type { SectionEyebrowProps, SectionEyebrowTone } from './SectionEyebrow'

export { EvidenceCard } from './EvidenceCard'
export type {
  EvidenceCardProps,
  EvidenceCardTone,
  EvidenceCardElement,
} from './EvidenceCard'

export { DataTable } from './DataTable'
export type { DataTableProps, DataTableColumn, DataTableAlign } from './DataTable'

export { StateBadge } from './StateBadge'
export type { StateBadgeProps, StateBadgeTone } from './StateBadge'

export { EmptyState } from './EmptyState'
export type { EmptyStateProps } from './EmptyState'

export { TraceChip } from './TraceChip'
export type { TraceChipProps } from './TraceChip'



export {
  AGENT_VOCABULARY,
  lookupVocab,
} from './agentVocabulary'
export type { AgentToolName } from './agentVocabulary'

export { GovernedSeal } from './GovernedSeal'
export type { GovernedSealProps } from './GovernedSeal'

export { PolicyDecisionBadge } from './PolicyDecisionBadge'
export type { PolicyDecisionBadgeProps } from './PolicyDecisionBadge'

export {
  PROVENANCE_DETAIL,
  PROVENANCE_LABEL,
  RAIL_STATE_DETAIL,
  RAIL_STATE_LABEL,
  resolveRailState,
} from './governedTypes'
export type {
  EvidenceProvenance,
  ExecutionRail,
  GovernedRailState,
  PolicyDecision,
  RailDecision,
  RailDegradation,
} from './governedTypes'
