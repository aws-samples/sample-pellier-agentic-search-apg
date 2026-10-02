/**
 * The canonical Lab 1 query.
 *
 * One string, used by the golden set, the micro-eval endpoint, the strategy
 * comparison card and the lab guide. It is not decorative copy: the labeled
 * relevant rows in `CANONICAL_ANNA_GOLDEN_IDS` were chosen for this exact
 * request, so a near-miss scores a different question and quietly changes
 * every number a participant is asked to read.
 *
 * Mirrors `services.planned_hybrid_retrieval.CANONICAL_ANNA_QUERY`.
 */
export const CANONICAL_ANNA_QUERY =
  'A housewarming gift under $100 that is currently in stock.'
