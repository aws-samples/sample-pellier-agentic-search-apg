import type { LabExerciseId } from '../labs/labCatalog';

/** One directory and one teaching contract per reference, shared with its page. */
export interface WorkshopReference {
  label: string;
  path: string;
  lab: LabExerciseId;
  role: string;
  question: string;
  inspect: string;
  limit: string;
  sources: string[];
}

export const GOVERNED_SOURCE = 'https://github.com/aws-samples/sample-pellier-agentic-search-apg/tree/governed';
export const REFERENCES = {
  sessions: {
    label: 'Sessions & traces', path: '/observatory/sessions', lab: 'grounded-inventory',
    role: 'Recorded evidence · Labs 1–4',
    question: 'Which recorded tool result supports this answer?',
    inspect: 'Choose the exact session and turn. Match the inventory tool arguments and returned warehouse row to the answer, then reconcile the execution with tool_audit in Aurora.',
    limit: 'A trace shows recorded activity. It does not establish that the answer used the result correctly. Missing telemetry is unknown, not proof of non-execution.',
    sources: ['pellier/backend/services/governed_turn_receipt.py', 'pellier/backend/routes/observatory.py'],
  },
  proof: {
    label: 'Proof Board', path: '/observatory/proof-board', lab: 'grounded-inventory',
    role: 'Evidence reconciliation · Labs 1–4',
    question: 'Can the claim be reconstructed from independent records?',
    inspect: 'Follow grounding, retrieval, the managed path, and governance in lab order. Retain the receipt identifiers and reconcile each checkpoint with the SQL result from the same run.',
    limit: 'Readiness and recent records are orientation. They do not replace a turn-scoped receipt or establish that your current build passed the Studio acceptance checks.',
    sources: ['pellier/backend/routes/observatory.py', 'pellier/backend/services/retrieval_receipt.py'],
  },
  search: {
    label: 'Search pipeline', path: '/observatory/search', lab: 'retrieval-acceptance',
    role: 'Mechanism experiment · Lab 2',
    question: 'Why did a candidate move between retrieval and reranking?',
    inspect: 'Compare vector and lexical ranks, recompute a fused score, and inspect the rerank position change. RRF adds reciprocal ranks; a candidate absent from the pool cannot be recovered by reranking.',
    limit: 'This is a new, unconstrained query. It does not replay a shopper turn, enforce Anna’s typed price and stock constraints, or persist a retrieval receipt. Use Retrieval comparison and the Lab 2 receipt for those checks.',
    sources: ['pellier/backend/app.py', 'pellier/backend/services/hybrid_search.py', 'pellier/backend/services/planned_hybrid_retrieval.py'],
  },
  performance: {
    label: 'Retrieval comparison', path: '/observatory/performance', lab: 'retrieval-acceptance',
    role: 'Controlled comparison · Lab 2',
    question: 'What does each retrieval strategy buy for this query?',
    inspect: 'Compare returned products, constraint enforcement, observed time, and modeled request cost. Read the agentic row’s typed plan and retain its comparison receipt before defending the candidate budget.',
    limit: 'Each strategy runs once after a shared embedding. These times are not percentiles and the costs are not a bill. Product order alone does not measure recall; the separate pool experiment uses a bounded labelled query set.',
    sources: ['pellier/backend/app.py', 'pellier/backend/services/planned_hybrid_retrieval.py', 'scripts/eval_retrieval_harness.py'],
  },
  tools: {
    label: 'Tool Registry', path: '/observatory/tools', lab: 'managed-agent-path',
    role: 'Contract inspection · Labs 1 & 3',
    question: 'Is this tool implemented, published, visible, and permitted?',
    inspect: 'Inspect check_inventory’s input contract, then get_ticket_history’s canonical schema. Lab 3 separately checks Gateway publication, the Runtime catalogue, and owned versus foreign customer reads.',
    limit: 'A source build count or pgvector discovery match is not the caller-visible Gateway catalogue. Neither establishes invocation permission. Match the managed invocation to its build fingerprint and execution receipt.',
    sources: ['pellier/backend/services/agent_tools.py', 'scripts/deploy/gateway_tool_schemas.py', 'pellier/backend/services/agentcore_runtime.py'],
  },
  memory: {
    label: 'Memory', path: '/observatory/memory', lab: 'managed-agent-path',
    role: 'Continuity evidence · Lab 3',
    question: 'Did a new conversation use an extracted preference?',
    inspect: 'Keep the verified actor stable within the isolated memory experiment. Compare the written event, extracted preference record, and recall in a new conversation with zero prior chat events.',
    limit: 'Extraction is asynchronous. Seeded customer history is not learned memory, and a remembered preference is not current inventory or order truth. Re-read those facts from Aurora.',
    sources: ['pellier/backend/services/memory_showcase.py', 'pellier/backend/services/agentcore_memory.py'],
  },
  govern: {
    label: 'Govern', path: '/observatory/govern', lab: 'fail-closed-policy',
    role: 'Authorization and effects · Lab 4',
    question: 'Which boundary allowed or stopped Jessica’s action?',
    inspect: 'Separate verified identity, Cedar authorization, database ownership and business checks, then committed effects. Reconcile DENY, business refusal, commit, and replay using the same request identifiers.',
    limit: 'An ALLOW is permission to attempt the tool, not a committed return. A DENY needs a policy receipt and a keyed absence check. Operator human review belongs to the separately authenticated staff path.',
    sources: ['pellier/backend/services/governed_turn_receipt.py', 'pellier/backend/routes/observatory.py'],
  },
  architecture: {
    label: 'Architecture', path: '/observatory/architecture', lab: 'fail-closed-policy',
    role: 'Architecture defence · Labs 1–4',
    question: 'Where does each piece of state live, and who enforces the boundary?',
    inspect: 'Trace Aurora facts → retrieval candidates → managed tool invocation → authorized database effect. For each hop, name the caller, owning store, failure behavior, and evidence you retained in the lab.',
    limit: 'These diagrams and code references explain the design. They do not establish that this deployment exercised every path. Use your four lab records to support the final architecture defence.',
    sources: ['pellier/backend/services/observatory_copy.py', 'pellier/backend/services/agentcore_runtime.py'],
  },
  evaluations: {
    label: 'Evaluations', path: '/observatory/evaluations', lab: 'retrieval-acceptance',
    role: 'After the labs · Evaluation design',
    question: 'What evidence would justify a broader quality claim?',
    inspect: 'Start with Lab 2’s candidate-budget result and Lab 4’s outcome matrix. Define held-out queries, relevance labels, failure cases, and a fixed build before comparing repeated runs.',
    limit: 'Configured evaluators and local test definitions are not measured scorecards. Workshop acceptance covers bounded cases; it does not establish production accuracy or P95 latency.',
    sources: ['pellier/backend/services/agentcore_evals.py', 'scripts/eval_retrieval_harness.py', 'pellier/backend/tests/test_golden_journeys.py'],
  },
  production: {
    label: 'Production patterns', path: '/observatory/production-patterns', lab: 'fail-closed-policy',
    role: 'After the labs · Failure analysis',
    question: 'What remains to test before this design can serve production traffic?',
    inspect: 'Extend the four lab contracts with concurrent duplicates, lost responses, expired identity, stale memory, and transaction rollback. Define the expected database effect before inducing a failure.',
    limit: 'These are design and test considerations. The sequential workshop replay is bounded evidence, not a guarantee for every concurrent or retried request.',
    sources: ['pellier/backend/services/agentcore_runtime.py', 'pellier/backend/services/governed_turn_receipt.py'],
  },
  replacement: {
    label: 'Replacement recovery', path: '/observatory/replacement', lab: 'fail-closed-policy',
    role: 'After the labs · Operator recovery extension',
    question: 'Can an approved remedy recover without creating a second operation?',
    inspect: 'Open an exact replacement from the Operator client record. Correlate approval, reservation, outbox, provider operation, and recorded events before deciding whether to retry.',
    limit: 'This extension needs an existing replacement and Operator sign-in. It is outside the four required labs. Fulfillment uses a workshop simulator, not a real carrier.',
    sources: ['pellier/backend/services/replacement_recovery.py', 'scripts/deploy/replacement_worker.py'],
  },
} satisfies Record<string, WorkshopReference>;
export type ReferenceId = keyof typeof REFERENCES;

export const LAB_REFERENCE_GROUPS: { lab: LabExerciseId; title: string; question: string; refs: ReferenceId[] }[] = [
  { lab: 'grounded-inventory', title: 'Lab 1 · Marco · Ground the answer', question: 'Which database fact supports the answer?', refs: ['sessions', 'proof'] },
  { lab: 'retrieval-acceptance', title: 'Lab 2 · Anna · Explain retrieval', question: 'Which candidates survive, and why?', refs: ['search', 'performance'] },
  { lab: 'managed-agent-path', title: 'Lab 3 · Theo · Prove the managed path', question: 'What crossed the tool and memory boundaries?', refs: ['tools', 'memory'] },
  { lab: 'fail-closed-policy', title: 'Lab 4 · Jessica · Defend the outcome', question: 'What was authorized, executed, and committed?', refs: ['govern', 'architecture'] },
];
export const EXTENSION_REFERENCES: ReferenceId[] = ['evaluations', 'production', 'replacement'];
