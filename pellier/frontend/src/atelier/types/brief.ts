/**
 * Atelier Observatory — Brief types
 *
 * Types for the Curator's Brief — a magazine-style editorial deconstruction
 * of a single session.
 *
 * Requirements: 16.5
 */

import type { ProductCard } from './chat';

export interface BriefContent {
  folioNumber: number;
  headline: string;
  filedTime: string;
  sections: BriefSection[];
  products: ProductCard[];
  confidence: {
    percentage: number;
    stats: { label: string; value: string }[];
  };
}

export interface BriefSection {
  numeral: string;
  title: string;
  paragraphs: string[];
  evidencePanel?: {
    sql: string;
    toolRanking: { name: string; distance: number }[];
  };
  memoryRows?: { tier: string; content: string }[];
  tracePills?: string[];
}
