/**
 * Evaluation methods catalog for the Evaluations surface —
 * workshop-oriented comparison of common agent/RAG eval approaches.
 */

export type EvalMethodFit = 'strong' | 'partial' | 'workshop';

export interface EvaluationMethod {
  id: string;
  name: string;
  vendor: string;
  tagline: string;
  bestFor: string[];
  watchOuts: string[];
  pellierFit: EvalMethodFit;
  /** When this method shines in the Pellier boutique arc */
  workshopNote: string;
}

export const EVALUATION_METHODS: EvaluationMethod[] = [
  {
    id: 'agent-judge',
    name: 'Agent as a Judge',
    vendor: 'LLM rubric (any model)',
    tagline: 'A second model scores turns against a rubric you define.',
    bestFor: [
      'Subjective quality — tone, helpfulness, gift-wrap guidance',
      'Per-turn pass/fail with natural-language criteria',
      'Fast iteration before you have labeled golden sets',
    ],
    watchOuts: [
      'Judge bias and position bias — calibrate against human samples',
      'Cost scales with eval volume (every turn = extra model call)',
    ],
    pellierFit: 'strong',
    workshopNote:
      'Strong fit for Style Advisor and Experience Guide — score whether the agent cited inventory, respected budget, and stayed on-brand without building a full harness first.',
  },
  {
    id: 'agentcore-evals',
    name: 'Amazon Bedrock AgentCore Evals',
    vendor: 'AWS',
    tagline: 'Managed eval runs tied to agents deployed on AgentCore Runtime.',
    bestFor: [
      'Regression gates before promoting agent versions',
      'Built-in trajectories when you already run on AgentCore',
      'Operational evals in the same account as production',
    ],
    watchOuts: [
      'Most valuable once agents are on AgentCore — less about local FastAPI dev',
      'Define datasets and success metrics up front',
    ],
    pellierFit: 'workshop',
    workshopNote:
      'The production-shaped path: after the Builder\'s Session exercise (floor_check) is live, wire eval datasets to the same Runtime ARNs you use in the boutique.',
  },
  {
    id: 'ragas',
    name: 'RAGAS',
    vendor: 'Open source',
    tagline: 'RAG-focused metrics — faithfulness, answer relevance, context precision.',
    bestFor: [
      'Retrieval + generation pipelines (hybrid search, rerank)',
      'Quantifying whether answers stay grounded in catalog hits',
      'Comparing vector-only vs hybrid vs hybrid+rerank objectively',
    ],
    watchOuts: [
      'Needs reference contexts or synthetic test sets',
      'Less opinionated about tool-use or multi-agent routing',
    ],
    pellierFit: 'strong',
    workshopNote:
      'Ideal for Anna\'s anchor capability — measure whether hybrid+rerank actually improves grounded recommendations vs vector-only.',
  },
  {
    id: 'langsmith',
    name: 'LangSmith',
    vendor: 'LangChain',
    tagline: 'Trace collection, datasets, online/offline evals, human review queues.',
    bestFor: [
      'End-to-end tracing across chains, tools, and retrievers',
      'Human-in-the-loop review of bad sessions',
      'A/B comparing prompts and retrieval configs',
    ],
    watchOuts: [
      'Another SaaS dependency — export and retention policies matter',
      'Instrument your stack early or migration is painful',
    ],
    pellierFit: 'partial',
    workshopNote:
      'Useful if you already standardize on LangGraph/LangChain; Pellier\'s Atelier telemetry is the in-workshop substitute for trace inspection.',
  },
  {
    id: 'golden-set',
    name: 'Golden-set regression',
    vendor: 'Your CI pipeline',
    tagline: 'Fixed queries with expected products, tools, or JSON shapes.',
    bestFor: [
      'Non-negotiable regressions — "Marco Turn 2 must surface Hadley Camp Shirt"',
      'Tool routing and pgvector discover smoke tests',
      'Cheap, deterministic gates on every PR',
    ],
    watchOuts: [
      'Brittle if overfit to fixture SKUs — refresh when catalog changes',
      'Does not catch novel failure modes',
    ],
    pellierFit: 'strong',
    workshopNote:
      'What the repo already leans on — pytest + fixture sessions. Extend with labeled picks per persona journey.',
  },
  {
    id: 'human-eval',
    name: 'Human evaluation',
    vendor: 'Operators / merchandisers',
    tagline: 'People score sessions in a rubric spreadsheet or review UI.',
    bestFor: [
      'Ground truth for calibrating LLM judges',
      'Brand voice and merchandising judgment calls',
      'Small-N deep dives on capstone demos',
    ],
    watchOuts: [
      'Slow and expensive at scale',
      'Inter-rater agreement needs a clear rubric',
    ],
    pellierFit: 'strong',
    workshopNote:
      'Capstone sessions (Marco capstone, Theo return) are designed for live human scoring alongside the scorecards on this page.',
  },
];

export const PELLIER_EVAL_STACK_NOTE =
  'For Pellier: measure retrieval first (Recall@K, MRR, context relevance), then generation faithfulness, then end-to-end accuracy and citation rate on fixture journeys. Golden-set regression guards CI; RAGAS quantifies retrieval+grounding; an LLM judge covers tone; AgentCore Evals promotes winners on Runtime. LangSmith is optional if you already live there.';
