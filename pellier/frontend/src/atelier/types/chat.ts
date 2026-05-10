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
}

export interface ToolCall {
  toolName: string;
  description: string;
  durationMs: number;
  sql?: string;
  resultSummary?: string;
  expanded?: boolean;
}

export interface ProductCard {
  name: string;
  brand: string;
  price: number;
  imageUrl: string;
  traceRef?: string;
}

export interface PlanRow {
  routingPattern: string;
  stepCount: number;
  flowSummary: string;
  traceLink?: string;
}

export interface ConfidenceRow {
  percentage: number;
  reasoning: string;
}

export interface MemoryPill {
  tier: 'stm' | 'ltm';
  content: string;
}
