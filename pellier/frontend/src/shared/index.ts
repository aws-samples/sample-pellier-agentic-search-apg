/**
 * Shared atoms used by BOTH the Boutique storefront and the Atelier
 * observatory. Importing from `../../shared` (or `../shared`) keeps
 * the two surfaces visually and semantically aligned.
 */
export { TraceChip } from './TraceChip'
export type { TraceChipProps } from './TraceChip'

export { SurfaceCrossLink } from './SurfaceCrossLink'
export type { SurfaceCrossLinkProps, CrossLinkDirection } from './SurfaceCrossLink'

export { PresencePill } from './PresencePill'
export type { PresencePillProps, PresenceSurface, PresenceMode } from './PresencePill'

export {
  AGENT_VOCABULARY,
  lookupVocab,
} from './agentVocabulary'
export type { AgentToolName } from './agentVocabulary'
