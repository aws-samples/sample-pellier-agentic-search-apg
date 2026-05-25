/**
 * Atelier Observatory — Memory types
 *
 * The Memory architecture lens has four substrates, each with its
 * own storage, lifetime, and write contract:
 *
 *   working    — AgentCore Memory session turns
 *   semantic   — AgentCore Memory KV preferences
 *   episodic   — Aurora customer_episodic_seed / orders / returns
 *   procedural — Aurora tool_audit aggregate patterns
 *
 * Each substrate carries an explicit ``source`` so the UI can show
 * provenance honestly (live read vs. fixture vs. sketch over a
 * partial schema).
 */

export type MemorySubstrate = 'working' | 'semantic' | 'episodic' | 'procedural';

/**
 * Provenance of the items in a substrate panel.
 *
 *   live    — read from the real source on this request
 *   fixture — served from a per-persona JSON fixture (DB unreachable
 *             or no rows for this persona; AgentCore not provisioned)
 *   sketch  — derived from a partial schema (e.g. tool_audit lacks
 *             intent/persona columns today). Honest about the gap.
 */
export type MemorySource = 'live' | 'fixture' | 'sketch';

export interface MemoryItem {
  id: string;
  content: string;
  substrate: MemorySubstrate;
  /** ISO timestamp for working-memory turns; absent for the others. */
  timestamp?: string;
  /** Cosine similarity 0..1 when the item came from a vector recall. */
  similarity?: number;
  /** Days into the past for episodic seed rows (negative or zero). */
  tsOffsetDays?: number;
}

export interface MemorySubstratePanel {
  /** Display label (e.g. "Working · AgentCore Memory"). */
  label: string;
  /** Backing store name shown as a small caption. */
  store: string;
  /** Where these items came from on this request. */
  source: MemorySource;
  /** Items to render. May be empty (cold start, fresh persona, etc.). */
  items: MemoryItem[];
  /** Optional one-line caption shown when the panel is sketch-only. */
  caveat?: string;
}

export interface MemoryState {
  persona: string;
  working: MemorySubstratePanel;
  semantic: MemorySubstratePanel;
  episodic: MemorySubstratePanel;
  procedural: MemorySubstratePanel;
}
