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
  evidenceHref?: string;
  objective: string;
  participantTodo: string;
  buildConnection: {
    files: string[];
    requestPath: string;
    observableChange: string;
    counterexample: string;
  };
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
    customerNeed: "Marco needs reliable stock and dispatch facts before his trip.",
    nextBoundary: "You can check a product. Next, help Anna find the right product without changing her requirements.",
    summary: "Connect the inventory tool, then check that the agent answers from its returned facts. Keep an unknown product distinct from a known product with zero stock.",
    image: '/assets/personas/marco-720.webp',
    imageWidth: 720,
    imageHeight: 1080,
    proofCardIds: ['marco-floor-check'],
    objective:
      'Ground Marco’s warehouse answer in current Aurora rows. Reconcile the stock count and recorded ship window with the tool’s execution receipt.',
    participantTodo: "Task 1A: implement the inventory result contract. Task 1B: wire the specialist and prove a real Storefront turn.",
    buildConnection: {
      files: ['pellier/backend/agents/inventory_agent.py', 'pellier/backend/services/agent_tools.py'],
      requestPath: 'Storefront → chat API → Inventory Agent → check_inventory → Aurora',
      observableChange: 'After the Python edit and backend restart, Marco’s warehouse request should produce live stock rows and an execution receipt.',
      counterexample: 'An unknown product must not become a known product with zero stock. Check the direct tool result before judging the answer.',
    },
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
    shortTitle: 'PostgreSQL hybrid retrieval',
    customerNeed: "Anna needs a gift under $100. Alternatives may change her preferences, never her requirements.",
    nextBoundary: "You can find suitable products. Next, deploy Theo’s support capability and preserve the caller’s identity across the tool boundary.",
    summary: "Explain how search results are ranked, then keep budget, stock and exclusions unchanged when the agent retries with a different preference.",
    image: '/assets/personas/anna-720.webp',
    imageWidth: 720,
    imageHeight: 1080,
    proofCardIds: ['retrieval-comparison'],
    objective:
      'Explain Anna’s recorded ranking, then preserve her budget, stock requirements and exclusions when the agent relaxes a preference.',
    participantTodo: "Task 2A: reconstruct recorded RRF. Task 2B: preserve the original requirements in every fallback attempt.",
    buildConnection: {
      files: ['workshop/lab-2-rrf.sql', 'pellier/backend/services/search_plan.py'],
      requestPath: 'Storefront or comparison → shared retrieval executor → Aurora candidates → Cohere Rerank',
      observableChange: 'The SQL worksheet verifies saved fusion scores. The Python plan edit preserves original requirements when a preference is relaxed.',
      counterexample: 'A fallback must not admit an over-budget, unavailable or excluded product. Check both the original and relaxed plans.',
    },
    command:
      'psql -X -v ON_ERROR_STOP=1 -P pager=off -c "\nSELECT receipt_id, hard_constraints, retrieval_config,\n       latency_breakdown, modeled_cost_usd\n  FROM pellier.retrieval_receipts\n ORDER BY receipt_id DESC\n LIMIT 1;"',
    measurements: {
      before: {
        label: 'Before',
        value: 'The unfinished fallback refuses to relax a preference until its requirement-preservation contract is implemented.',
      },
      after: {
        label: 'Acceptance target',
        value: 'One receipt exposes branch ranks, RRF, rerank, observed latency, modeled cost, returned products, and enforced eligibility.',
      },
    },
    evidenceAssertion:
      'SQL recomputes the recorded RRF contribution and finds no price, stock, or archive violation in the exact returned IDs.',
    decisionPrompt:
      'Which preferences may change, which requirements must remain, and what evidence proves both?',
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
    shortTitle: 'Managed agents with AgentCore',
    customerNeed: "Theo wants remembered preferences and help with his own service history. Context must not become permission.",
    nextBoundary: "You can read under the right identity. Next, follow Jessica’s action through authorization, database effects and staff review.",
    summary: "Connect a tool that reads the signed-in customer’s support records, deploy it, and test access to their own records and another customer’s records.",
    image: '/assets/personas/theo-720.webp',
    imageWidth: 720,
    imageHeight: 1080,
    proofCardIds: ['managed-rail', 'audit-ledger'],
    objective:
      'Deploy Theo’s customer-scoped support path and use learned preferences in a new conversation. Verify the running build, Memory records, and current Aurora facts separately.',
    participantTodo: "Task 3A: reconcile publication, tool access and caller binding. Task 3B: deploy, challenge scope and identify the build that answered.",
    buildConnection: {
      files: ['scripts/deploy/gateway_tool_schemas.py', 'pellier/backend/services/agentcore_gateway.py'],
      requestPath: 'Storefront → AgentCore Runtime → Gateway and Policy → customer-scoped Aurora tool',
      observableChange: 'Deploy the edited package, then use a new session to verify ticket access and the executed build fingerprint. Saving locally does not update Runtime.',
      counterexample: 'Publication does not grant permission. The cross-session Memory experiment and regular Storefront history also use different actor scopes.',
    },
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
      'Retrieved record IDs, a new session ID, zero prior chat events, and catalog-tool results support the learned-preference check. The exact support turn must show ticket history bound to Theo. The Runtime receipt and Memory verifier establish the required managed checks; traces are optional diagnostics.',
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
    shortTitle: 'Governed actions with Cedar',
    customerNeed: "Jessica needs her service request resolved safely. Staff must establish what happened before choosing the next action.",
    nextBoundary: "Bring the four claims together: facts, requirements, caller and effect. Save your evidence and the next production question.",
    summary: "Write ownership checks in Cedar and PostgreSQL, then follow Jessica’s staff proposal through human confirmation to one recorded return.",
    image: '/assets/personas/jessica-720.webp',
    imageWidth: 720,
    imageHeight: 900,
    proofCardIds: ['runtime-gateway-policy'],
    evidenceHref: '/observatory/govern/verification',
    objective:
      'Prove five outcomes: authentication failure, Cedar denial, business refusal, commit, and output suppression. Verify replay and PostgreSQL RLS, then follow Jessica’s staff proposal through confirmation, execution and a matching return.',
    participantTodo: "Task 4A: author Cedar and distinguish five outcomes. Task 4B: test RLS and keyed evidence, then reconcile a human-reviewed return.",
    buildConnection: {
      files: ['policies/workshop_identity_match_forbid.cedar', 'workshop/lab-4-rls.sql', 'workshop/lab-4-absence.sql'],
      requestPath: 'Verified caller → Gateway and Cedar → tool → PostgreSQL transaction → response controls',
      observableChange: 'Deploy the identity rule, then correlate each decision with execution and durable effects using the exact operation key.',
      counterexample: 'A hidden or failed response can follow a commit. Inspect the saved operation before retrying; a new key can create another effect.',
    },
    command:
      'python3 scripts/prove_governance_outcomes.py \\\n  --json /tmp/pellier-evidence/lab-4-boundaries.json\npsql -X -v ON_ERROR_STOP=1 -P pager=off \\\n  -f workshop/lab-4-rls.sql',
    measurements: {
      before: {
        label: 'Before',
        value: 'The baseline policy does not bind the verified customer claim to the requested Aurora customer.',
      },
      after: {
        label: 'Acceptance target',
        value: 'All five outcomes have matched invocation and Aurora evidence. The suppressed credit remains committed and replays without a second credit. The rollback-only RLS test proves row scope; Jessica’s confirmed review links to one recorded return.',
      },
    },
    evidenceAssertion:
      'The boundary proof separates authentication, authorization, execution, durable effect, and response delivery. A suppressed response does not undo a committed credit. The rollback-only RLS test checks an independent boundary. The Operator review, confirmed terms and execution must match one return.',
    decisionPrompt:
      'Which control acted, did the tool execute, and did data change? What evidence is still needed when a response is missing or suppressed?',
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
        label: 'Inspect the five outcomes',
        to: '/observatory/govern/verification',
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
