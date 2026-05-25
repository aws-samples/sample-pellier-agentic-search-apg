/**
 * Evaluation metrics catalog — workshop teaching reference for
 * retrieval, grounding, and agent-quality measurement.
 */

export type EvalMetricTier = 'retrieval' | 'generation' | 'agent';

export interface EvaluationMetric {
  id: string;
  name: string;
  shorthand: string;
  tier: EvalMetricTier;
  definition: string;
  /** Plain-language formula — no LaTeX required in UI */
  formula: string;
  /** What regression or failure mode this metric surfaces */
  catches: string;
  pellierExample: string;
  /** Tools or approaches that commonly compute this */
  measuredVia: string[];
}

export const EVAL_METRIC_TIER_LABEL: Record<EvalMetricTier, string> = {
  retrieval: 'Retrieval',
  generation: 'Generation',
  agent: 'Agent / end-to-end',
};

export const RETRIEVAL_EVAL_PIPELINE_NOTE =
  'Split the problem in three layers: (1) did search return the right catalog rows? — Recall@K, Precision@K, MRR; (2) were those rows actually useful context? — context relevance / precision; (3) did the specialist cite them honestly? — faithfulness, citation rate, answer relevance. Anna\'s hybrid+rerank work mostly moves layer 1; the scorecards on this page mostly reflect layer 3.';

export const EVALUATION_METRICS: EvaluationMetric[] = [
  {
    id: 'recall-at-k',
    name: 'Recall@K',
    shorthand: 'Recall@5',
    tier: 'retrieval',
    definition:
      'Of all queries where a relevant product exists, what fraction had at least one relevant hit in the top K results?',
    formula: 'relevant found in top-K ÷ queries with a known relevant item',
    catches:
      'Missed recall — vector-only search that never surfaces literal SKUs (e.g. "Gift Wrapping Kit" under a gift query).',
    pellierExample:
      'Marco Turn 2: is the Hadley Camp Shirt in the top 5 after find_pieces? Workshop often tracks Recall@5 before and after hybrid+rerank.',
    measuredVia: ['Golden-set regression', 'RAGAS', 'Custom Aurora benchmark'],
  },
  {
    id: 'precision-at-k',
    name: 'Precision@K',
    shorthand: 'P@5',
    tier: 'retrieval',
    definition:
      'Of the K products returned, what fraction are actually relevant to the query?',
    formula: 'relevant in top-K ÷ K',
    catches:
      'Noisy retrieval — too many plausible-but-wrong items crowding the reranker or the agent context window.',
    pellierExample:
      'Anna gift query: if 3 of 5 hits are wrap-ready but 2 are random apparel, P@5 = 0.6 even when Recall@5 = 1.0.',
    measuredVia: ['Golden-set labels', 'RAGAS context precision'],
  },
  {
    id: 'mrr',
    name: 'Mean Reciprocal Rank',
    shorthand: 'MRR',
    tier: 'retrieval',
    definition:
      'How high does the first relevant product appear? Averaged as 1/rank across queries (1.0 = always rank 1).',
    formula: 'mean(1 ÷ rank of first relevant hit)',
    catches:
      'Right answer buried on page two — common when Postgres FTS and vector disagree and rerank is off.',
    pellierExample:
      'Compare MRR for vector-only vs hybrid+rerank on the same 50 boutique queries; a +0.15 MRR often matters more than a prettier prose answer.',
    measuredVia: ['Labeled search benchmarks', 'Performance search-strategy compare'],
  },
  {
    id: 'context-relevance',
    name: 'Context relevance',
    shorthand: 'Ctx rel.',
    tier: 'retrieval',
    definition:
      'Are the retrieved chunks or product cards on-topic for the user message — not just keyword overlap?',
    formula: 'LLM or human judges whether each retrieved unit supports the query intent',
    catches:
      'Retrieval that looks good in embedding space but sends wrong category or persona context to the agent.',
    pellierExample:
      'Theo ceramics query should not pull apparel STM; context relevance drops when LTM recall returns the wrong episodic seed.',
    measuredVia: ['RAGAS context relevancy', 'Agent-as-judge on retrieved set'],
  },
  {
    id: 'context-precision',
    name: 'Context precision',
    shorthand: 'Ctx prec.',
    tier: 'retrieval',
    definition:
      'What proportion of retrieved context is actually needed to answer — penalizes stuffing the prompt with marginally related SKUs.',
    formula: 'useful context pieces ÷ total pieces passed to the model',
    catches:
      'Over-fetching — hybrid search that widens recall but floods the specialist with noise.',
    pellierExample:
      'After raising K from 10→30 for Recall@10, context precision may fall; the teaching beat is trading cost vs signal.',
    measuredVia: ['RAGAS context precision', 'Manual chunk audit'],
  },
  {
    id: 'faithfulness',
    name: 'Faithfulness / groundedness',
    shorthand: 'Faith.',
    tier: 'generation',
    definition:
      'Is every factual claim in the assistant reply supported by the retrieved catalog context?',
    formula: 'supported claims ÷ total factual claims (often LLM-judged)',
    catches:
      'Hallucinated price, fabric, or availability — the failure mode that erodes trust even when retrieval was perfect.',
    pellierExample:
      'Style Advisor must not invent "linen" when the hit was cotton; faithfulness is the guardrail on top of Recall@5.',
    measuredVia: ['RAGAS faithfulness', 'Agent-as-judge with citation rubric'],
  },
  {
    id: 'answer-relevance',
    name: 'Answer relevance',
    shorthand: 'Ans rel.',
    tier: 'generation',
    definition:
      'Does the final reply actually address what the shopper asked — independent of whether citations were faithful?',
    formula: 'LLM or human: does the answer satisfy the user intent?',
    catches:
      'On-topic but unhelpful — polished prose that ignores budget, persona, or the gift-table skill.',
    pellierExample:
      'Anna asks for wrap-ready gifts under $80; a faithful list of $200 scarves fails answer relevance even with perfect citations.',
    measuredVia: ['RAGAS answer relevancy', 'Human rubric', 'Agent-as-judge'],
  },
  {
    id: 'accuracy',
    name: 'Recommendation accuracy',
    shorthand: 'Acc.',
    tier: 'agent',
    definition:
      'Did the agent recommend the expected product (or set) for a labeled session turn?',
    formula: 'correct top pick ÷ labeled turns',
    catches:
      'End-to-end regressions across routing, tools, retrieval, and prompt — what the scorecards summarize.',
    pellierExample:
      'Fixture sessions encode expected picks (e.g. Hadley Camp Shirt on Marco opening); accuracy is the golden-set view of "did we ship the right answer?"',
    measuredVia: ['Golden-set regression', 'AgentCore Evals datasets'],
  },
  {
    id: 'citation-rate',
    name: 'Citation rate',
    shorthand: 'Cite %',
    tier: 'agent',
    definition:
      'How often does the agent attach traceable product or tool evidence to its recommendation?',
    formula: 'turns with valid citations ÷ turns evaluated',
    catches:
      'Confident answers with no grounding — hard to debug in production without telemetry.',
    pellierExample:
      'Shown on each scorecard below; low citation rate with high accuracy suggests lucky guessing or stale fixtures.',
    measuredVia: ['Telemetry inspection', 'Automated citation parser', 'Human audit'],
  },
];

export function filterMetricsByTier(
  metrics: EvaluationMetric[],
  tier: EvalMetricTier | 'all',
): EvaluationMetric[] {
  if (tier === 'all') return metrics;
  return metrics.filter((m) => m.tier === tier);
}
