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
  };
}

export interface MemoryItem {
  id: string;
  content: string;
  tier: 'stm' | 'ltm';
  timestamp?: string;
  similarity?: number;
}
