export const LAB_EXERCISE_IDS = [
  'grounded-inventory',
  'retrieval-acceptance',
  'managed-agent-path',
  'fail-closed-policy',
] as const;

export type LabExerciseId = (typeof LAB_EXERCISE_IDS)[number];

export interface LabAction {
  label: string;
  to: string;
}

export interface LabMeasurement {
  label: string;
  value: string;
}

export interface LabExercise {
  id: LabExerciseId;
  number: string;
  anchorName: 'Marco' | 'Anna' | 'Theo' | 'Jessica';
  title: string;
  shortTitle: string;
  summary: string;
  customerNeed: string;
  nextBoundary: string;
  image: string;
  imageWidth: number;
  imageHeight: number;
  proofCardIds: string[];
  objective: string;
  participantTodo: string;
  command: string;
  measurements: {
    before: LabMeasurement;
    after: LabMeasurement;
  };
  evidenceAssertion: string;
  decisionPrompt: string;
  primaryAction?: LabAction;
  supportingActions: LabAction[];
  unavailableReason?: string;
}

export const LAB_EXERCISES: readonly LabExercise[] = [
  {
    id: 'grounded-inventory',
    number: '01',
    anchorName: 'Marco',
    title: 'Build a PostgreSQL-Grounded Agent',
    shortTitle: 'PostgreSQL-grounded agent',
    customerNeed: 'Marco needs a warehouse answer he can trust before his trip.',
    nextBoundary: 'A correct stock answer is only the start. Next, help Anna find an eligible gift and measure how retrieval changes her options.',
    summary:
      'Complete the Inventory Agent and its Aurora tool, then prove the answer against the exact warehouse rows and execution receipt.',
    image: '/assets/personas/marco-720.webp',
    imageWidth: 720,
    imageHeight: 1080,
    proofCardIds: ['marco-floor-check'],
    objective:
      'Ground Marco’s warehouse answer in current Aurora rows. Reconcile the stock count and recorded ship window with the tool’s execution receipt.',
    participantTodo:
      'Complete the two marked source regions, verify both build markers, and replay Marco\'s warehouse request under a unique session.',
    command:
      'psql -X -v ON_ERROR_STOP=1 -P pager=off -c "\nSELECT p.product_id, p.quantity AS catalog_units,\n       sum(wi.quantity)::int AS warehouse_units,\n       p.quantity = sum(wi.quantity) AS reconciled\n  FROM pellier.product_catalog p\n  JOIN pellier.warehouse_inventory wi USING (product_id)\n WHERE p.product_id = \'2\'\n GROUP BY p.product_id, p.quantity;"',
    measurements: {
      before: {
        label: 'Before',
        value: 'The answer is bounded or the catalog and warehouse totals are not reconciled.',
      },
      after: {
        label: 'Acceptance target',
        value: 'Both markers are shipped, Marco receives live warehouse facts, and one session-scoped audit row exists.',
      },
    },
    evidenceAssertion:
      'The selected Marco turn and run identify the requested product, report live Aurora values, and link a new check_inventory execution row. Unknown product and zero stock remain distinct.',
    decisionPrompt:
      'Which table owns inventory truth, and what invariant keeps the aggregate and the per-warehouse rows from drifting apart?',
    primaryAction: {
      label: 'Open live workbench',
      to: '/observatory/workbench',
    },
    supportingActions: [
      {
        label: 'Inspect inventory proof',
        to: '/observatory/proof-board#marco-floor-check',
      },
      {
        label: 'Open tool reference',
        to: '/observatory/tools',
      },
    ],
  },
  {
    id: 'retrieval-acceptance',
    number: '02',
    anchorName: 'Anna',
    title: 'Build and Measure PostgreSQL Hybrid Retrieval',
    shortTitle: 'PostgreSQL retrieval',
    customerNeed: 'Anna needs a gift under $100, with availability treated as a constraint.',
    nextBoundary: 'Now that retrieval is inspectable, take Theo’s support journey to a managed runtime and separate remembered preferences from current facts.',
    summary:
      'Inspect a PostgreSQL query plan, verify RRF in SQL, and repair a narrow candidate budget without relaxing eligibility.',
    image: '/assets/personas/anna-720.webp',
    imageWidth: 720,
    imageHeight: 1080,
    proofCardIds: ['retrieval-comparison'],
    objective:
      'Keep Anna’s gift under $100 and in stock. Trace eligible candidates through lexical search, vector retrieval, fusion, and reranking.',
    participantTodo:
      'Complete the RRF worksheet and candidate-budget build. Compare the same request before and after, then verify exact product IDs against Aurora.',
    command:
      'psql -X -v ON_ERROR_STOP=1 -P pager=off -c "\nSELECT receipt_id, hard_constraints, retrieval_config,\n       latency_breakdown, modeled_cost_usd\n  FROM pellier.retrieval_receipts\n ORDER BY receipt_id DESC\n LIMIT 1;"',
    measurements: {
      before: {
        label: 'Before',
        value: 'The live rerank stage receives only three fused candidates, even when more eligible products were retrieved.',
      },
      after: {
        label: 'Acceptance target',
        value: 'One receipt exposes branch ranks, RRF, rerank, observed latency, modeled cost, returned products, and enforced eligibility.',
      },
    },
    evidenceAssertion:
      'SQL recomputes the recorded RRF contribution and finds no price, stock, or archive violation in the exact returned IDs.',
    decisionPrompt:
      'Which measured tradeoff justifies the selected strategy for this query class?',
    primaryAction: {
      label: 'Open retrieval comparison',
      to: '/observatory/performance',
    },
    supportingActions: [
      {
        label: 'Inspect retrieval proof',
        to: '/observatory/proof-board#retrieval-comparison',
      },
      {
        label: 'Open search reference',
        to: '/observatory/search',
      },
    ],
  },
  {
    id: 'managed-agent-path',
    number: '03',
    anchorName: 'Theo',
    title: 'Deploy and Operate Agents with Amazon Bedrock AgentCore',
    shortTitle: 'AgentCore managed path',
    customerNeed: 'Theo needs continuity across conversations without crossing into another customer’s records.',
    nextBoundary: 'A deployed agent still needs a boundary on what it may do. Next, prove authorization, database scope, and the human review checkpoint.',
    summary:
      'Publish Theo\'s customer-scoped read, reconcile the Runtime tool list, and deploy. Use learned preferences in a new conversation and verify the running build.',
    image: '/assets/personas/theo-720.webp',
    imageWidth: 720,
    imageHeight: 1080,
    proofCardIds: ['managed-rail', 'audit-ledger'],
    objective:
      'Deploy Theo’s customer-scoped support path and use learned preferences in a new conversation. Verify the running build, Memory records, and current Aurora facts separately.',
    participantTodo:
      'Publish get_ticket_history, bind the support read to the caller, and deploy. Complete the learned-preference check, then run Theo\'s three-turn thread and read its Memory events from a separate process.',
    command:
      'cd .agentcore-project/pellier\nnpx -y @aws/agentcore@0.29.0 invoke \\\n  --runtime pellier_orchestrator \\\n  --session-id "$RUNTIME_SESSION" \\\n  --bearer-token "$PELLIER_TOKEN" \\\n  --prompt "Hand-thrown ceramics for a slower morning routine" \\\n  --json',
    measurements: {
      before: {
        label: 'Before',
        value: 'The Gateway publishes 16 tools. The support specialist requests tools outside the shopper\'s available tool list. Discovery is filtered by the caller\'s policy.',
      },
      after: {
        label: 'Acceptance target',
        value: 'The Gateway publishes 17 tools, the executed build matches this checkout, and Theo\'s new experiment conversation uses an extracted preference with current product data.',
      },
    },
    evidenceAssertion:
      'Retrieved record IDs, a new session ID, zero prior chat events, and catalog-tool results support the learned-preference check. The Runtime receipt, Memory verifier, and trace contract establish the other managed checks.',
    decisionPrompt:
      'Which artifact proves each managed boundary, and which claims remain unproven when one artifact is missing?',
    primaryAction: {
      label: 'Open live workbench',
      to: '/observatory/workbench',
    },
    supportingActions: [
      {
        label: 'Inspect managed evidence',
        to: '/observatory/proof-board#managed-rail',
      },
      {
        label: 'Inspect live sessions',
        to: '/observatory/sessions',
      },
    ],
  },
  {
    id: 'fail-closed-policy',
    number: '04',
    anchorName: 'Jessica',
    title: 'Build Governed Agent Actions with Cedar',
    shortTitle: 'Cedar and governed actions',
    customerNeed: 'Jessica needs a fair resolution, with account access and consequential actions controlled.',
    nextBoundary: 'Bring the four evidence sets together: defend which layer enforces each boundary, then restore the workshop baseline and follow cleanup.',
    summary:
      'Bind verified identity in Cedar, prove the four-case execution matrix and Aurora RLS backstop, then investigate Jessica\'s case as separately authorized staff.',
    image: '/assets/personas/jessica-720.webp',
    imageWidth: 720,
    imageHeight: 900,
    proofCardIds: ['runtime-gateway-policy'],
    objective:
      'Use Marco and Jessica to prove the customer boundary with the identity matrix and PostgreSQL RLS checks. Then investigate Jessica’s service issue as separately authorized staff, stopping at human review.',
    participantTodo:
      'Complete the Cedar rule and keyed absence query. Run the four-case identity matrix and RLS read and write checks, then complete one Operator investigation for Jessica. Stop before a consequential action and reset the policy in Summary.',
    command:
      'python3 scripts/prove_identity_boundary.py \\\n  --json /tmp/pellier-evidence/lab-4.json\npsql -X -v ON_ERROR_STOP=1 -P pager=off \\\n  -f workshop/lab-4-rls.sql',
    measurements: {
      before: {
        label: 'Before',
        value: 'The baseline policy does not bind the verified customer claim to the requested Aurora customer.',
      },
      after: {
        label: 'Acceptance target',
        value: 'Marco is denied, Jessica\'s invalid return is refused, and her valid return commits once and replays safely. RLS enforces row scope; Operator stops before execution.',
      },
    },
    evidenceAssertion:
      'The keyed matrix distinguishes policy, execution, write, and durable effect. RLS verifies an independent database boundary. The Operator investigation stops at the human checkpoint before a consequential action.',
    decisionPrompt:
      'Which layer proves identity, authorization, execution, database scope, and human approval, and what remains unproven if any layer is missing?',
    primaryAction: {
      label: 'Open Jessica in Operator',
      to: '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title',
    },
    supportingActions: [
      {
        label: 'Open Cedar policies',
        to: '/observatory/govern/policies',
      },
      {
        label: 'Inspect policy checkpoint',
        to: '/observatory/proof-board#runtime-gateway-policy',
      },
    ],
  },
] as const;

const LAB_BY_ID = new Map(LAB_EXERCISES.map((exercise) => [exercise.id, exercise]));
const LEGACY_LAB_ALIASES = new Map<string, LabExerciseId>([
  ['exactly-once-return', 'managed-agent-path'],
]);

export function findLabExercise(id: string | undefined): LabExercise | undefined {
  if (!id) return undefined;
  const canonicalId = LEGACY_LAB_ALIASES.get(id) ?? (id as LabExerciseId);
  return LAB_BY_ID.get(canonicalId);
}
