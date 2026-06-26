/**
 * Search-explain types — the wire shape of GET /api/atelier/search/explain.
 *
 * The endpoint runs ONE hybrid query and returns each intermediate stage
 * of the retrieval pipeline (EMBED → VECTOR → LEXICAL → FUSION → RERANK)
 * shaped as a telemetry-style panel so the Atelier "Search" surface can
 * render the mechanism, not just the outcome. Rows arrive pre-stringified
 * (string[][]) — the backend has already formatted numbers for display.
 */

export type SearchStageName =
  | 'embed'
  | 'vector'
  | 'lexical'
  | 'fusion'
  | 'rerank';

export type SearchTagClass = 'cyan' | 'amber' | 'green';

export interface SearchStage {
  /** Machine name of the pipeline stage. */
  stage: SearchStageName;
  /** Uppercase eyebrow tag, e.g. "SEARCH · VECTOR". */
  tag: string;
  /** Human-readable stage title. */
  title: string;
  /** Literal SQL for the stage (VECTOR/LEXICAL); empty for non-SQL stages. */
  sql: string;
  /** Column headers for the rows table. */
  columns: string[];
  /** Pre-stringified table rows. */
  rows: string[][];
  /** One-line teaching note shown under the table. */
  meta: string;
  /** Panel accent class: cyan = data op, amber = LLM/Bedrock. */
  tagClass: SearchTagClass;
  /** Optional stage latency in ms. */
  durationMs?: number;
}

export interface SearchExplainParams {
  k_vector: number;
  k_bm25: number;
  rrf_k: number;
  top_n: number;
}

export interface SearchExplainResponse {
  query: string;
  params: SearchExplainParams;
  stages: SearchStage[];
}
