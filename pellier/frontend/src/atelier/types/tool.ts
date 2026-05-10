/**
 * Atelier Observatory — Tool types
 *
 * Represents a registered tool function and pgvector discovery results.
 *
 * Requirements: 16.5
 */

export interface Tool {
  numeral: number;
  functionName: string;
  description: string;
  status: 'shipped' | 'exercise';
  /**
   * 'read'  — tool only queries Aurora (or Bedrock); does not change
   *           any persistent state.
   * 'write' — tool mutates Aurora rows. Mutating tools always pass
   *           through the Cedar policy hook AND get a row in
   *           tool_audit (Theo's anchor capability — every mutation
   *           leaves a paper trail). Surfaced in the Atelier with
   *           a burgundy WRITE pill so the read/write split is
   *           obvious at a glance.
   */
  mutationType: 'read' | 'write';
  signature: string;
  usedBy: string[];
  invocationCount: number;
  version: string;
}

export interface ToolDiscoveryResult {
  rank: number;
  toolId: string;
  name: string;
  description: string;
  similarity: number;
  status: 'shipped' | 'exercise';
}
