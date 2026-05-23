/**
 * Atelier Observatory — Memory types
 *
 * Represents the STM and LTM memory state for a persona.
 *
 * Requirements: 16.5
 */

export interface MemoryState {
  persona: string;
  stm: {
    turnCount: number;
    recentIntents: string[];
    items: MemoryItem[];
  };
  ltm: {
    preferences: string[];
    priorOrders: string[];
    behavioralPatterns: string[];
    items: MemoryItem[];
    /**
     * True when items[] was overlaid from a live Aurora read of
     * pellier.customer_episodic_seed. False/absent when the items
     * came from the per-persona fixture only (DB unavailable or no
     * matching customer_id rows).
     */
    live?: boolean;
  };
}

export interface MemoryItem {
  id: string;
  content: string;
  tier: 'stm' | 'ltm';
  timestamp?: string;
  similarity?: number;
}
