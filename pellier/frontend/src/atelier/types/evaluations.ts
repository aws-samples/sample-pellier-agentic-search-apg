/**
 * Atelier Observatory — Evaluations types
 *
 * Agent evaluation scorecards with accuracy, latency, and citation metrics.
 *
 * Requirements: 16.5
 */

export interface EvaluationScorecard {
  agentName: string;
  accuracy: number;
  latencyP50: number;
  latencyP95: number;
  citationRate: number;
  versionTrend: { version: string; score: number }[];
}
