/**
 * Atelier Observatory — Chat types
 *
 * Types for the multi-turn chat conversation within a session,
 * including tool calls, product cards, plan rows, confidence, and memory pills.
 *
 * Requirements: 16.5
 */

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  toolCalls?: ToolCall[];
  products?: ProductCard[];
  plan?: PlanRow;
  confidence?: ConfidenceRow;
  memoryPills?: MemoryPill[];
  meta?: {
    agent?: string | null;
    model?: string | null;
    skill?: string;
    searchMethod?: string;
    latencyMs?: number;
    note?: string;
  };
}

export interface ToolCall {
  toolName: string;
  description: string;
  durationMs: number;
  sql?: string;
  resultSummary?: string;
  subSteps?: ToolSubStep[];
  writes?: ToolWrite[];
  expanded?: boolean;
}

export interface ToolSubStep {
  label: string;
  durationMs: number;
  sql?: string;
}

export interface ToolWrite {
  table: string;
  operation: string;
  rowId: number | string;
  field?: string;
  before?: number | string;
  after?: number | string;
  via?: string;
}

export interface ProductCard {
  name: string;
  brand: string;
  price: number;
  imageUrl: string;
  traceRef?: string;
}

export interface PlanRow {
  /** When omitted (some fixtures), UI defaults to "steps" to match the plan chip row. */
  routingPattern?: string;
  /** When omitted, inferred from arrow segments in `flowSummary`. */
  stepCount?: number;
  flowSummary: string;
  traceLink?: string;
}

export interface ConfidenceRow {
  percentage?: number;
  reasoning: string;
}

export interface MemoryPill {
  tier: 'stm' | 'ltm' | 'skill';
  content: string;
}
