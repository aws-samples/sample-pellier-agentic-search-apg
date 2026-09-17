import type { ReferenceId } from './referenceCatalog';

interface DiagnosticCase {
  observation: string;
  mechanism: string;
  evidence: string;
}

/** Explanations for interpreting lab evidence, never observations of this deployment. */
export const REFERENCE_DIAGNOSTICS: Record<ReferenceId, DiagnosticCase[]> = {
  sessions: [
    {
      observation: 'The answer looks right, but the tool receipt is missing.',
      mechanism: 'Plausible text cannot establish a database read. A missing span can also mean incomplete telemetry, so it cannot establish that the tool was skipped.',
      evidence: 'Match the exact session, turn, tool arguments, and tool_audit row. Reconcile the returned warehouse values with the answer; an unrelated recent row is insufficient.',
    },
    {
      observation: 'Two turns mention the same product.',
      mechanism: 'A product ID identifies the subject, not the execution. A later request may have different inventory, identity, or tool results.',
      evidence: 'Keep the turn and execution identifiers together. Compare the recorded result for that turn with current Aurora state without treating a later read as the original snapshot.',
    },
  ],
  proof: [
    {
      observation: 'The environment is ready, but the lab result is unproven.',
      mechanism: 'A healthy service and available records establish prerequisites. They do not identify your edited build or prove that your request met the acceptance contract.',
      evidence: 'Keep the build revision, run or session ID, receipt, and matching SQL output. Use the Workshop Studio acceptance checks to connect them.',
    },
    {
      observation: 'A denial has no matching execution row.',
      mechanism: 'Absence is useful only when the lookup is scoped correctly and the audit path is known to work. An empty table or wrong request key can produce the same result.',
      evidence: 'Use the denied invocation key and the successful positive control from the same proof run. Verify both the decision evidence and the independent database counts.',
    },
  ],
  search: [
    {
      observation: 'A product rises after fusion despite a weaker vector rank.',
      mechanism: 'RRF combines ranks rather than incomparable raw scores. With k = 60, an illustrative product ranked 1 and 8 contributes 1/61 + 1/68; an absent branch contributes nothing.',
      evidence: 'Read the recorded k and both one-based ranks, recompute each contribution, and compare the fused ordering before considering rerank scores.',
    },
    {
      observation: 'Reranking never returns the expected product.',
      mechanism: 'The reranker only sees the supplied candidate pool. A product removed by branch limits, eligibility, or the fused candidate budget cannot be restored by changing its rerank position.',
      evidence: 'Locate the product ID in each branch, the fused pool, and the rerank input. Use the constrained Lab 2 receipt to determine where eligibility or truncation removed it.',
    },
  ],
  performance: [
    {
      observation: 'A wider candidate budget changes the top result.',
      mechanism: 'More candidates can improve coverage while increasing rerank work. One better-looking answer does not establish recall, and a budget change must preserve price, stock, and archive constraints.',
      evidence: 'Hold the query, constraints, strategy, and data snapshot fixed. Compare exact candidate IDs, returned IDs, observed stage times, and modeled cost. Use relevance labels for a quality claim.',
    },
    {
      observation: 'One strategy is much faster in this comparison.',
      mechanism: 'The comparison shares an embedding and runs each strategy once. Cache state, provider latency, and database work can vary; a single duration is not a latency percentile.',
      evidence: 'Retain the receipt and its timing breakdown. For a broader claim, repeat a held-out query set with a fixed build and record failures as well as successful runs.',
    },
  ],
  tools: [
    {
      observation: 'The source contains a tool, but the managed agent cannot call it.',
      mechanism: 'Implementation, Gateway publication, caller-visible discovery, and the Runtime tool binding are separate contracts. A correct function can still be absent from the running package.',
      evidence: 'Compare the canonical schema and tool name with Gateway discovery for that caller and the deployed Runtime fingerprint. Then inspect the exact invocation and target receipt.',
    },
    {
      observation: 'An owned read works, but another customer’s read fails.',
      mechanism: 'Discovering a tool does not grant access to every argument. The verified principal and requested customer scope must still pass authorization and ownership checks.',
      evidence: 'Compare the owned and foreign attempts using the same authenticated caller. Identify the rejecting boundary and verify the result without substituting scenario selection for identity.',
    },
  ],
  memory: [
    {
      observation: 'The agent remembers something in the same conversation.',
      mechanism: 'Prior chat events can explain that answer without long-term extraction. Seeded customer history can also look like learned memory.',
      evidence: 'Use the isolated experiment’s stable actor with a new session and zero prior chat events. Match the extracted record IDs to the preference supplied during recall.',
    },
    {
      observation: 'The write succeeded, but no preference is recalled yet.',
      mechanism: 'Event persistence, asynchronous extraction, and retrieval are different stages. A successful event write does not establish that an extracted record is available in the expected scope.',
      evidence: 'Inspect the event, extraction state, actor scope, namespace, and retrieved record IDs. Report pending extraction explicitly; re-read current product and order facts from Aurora.',
    },
  ],
  govern: [
    {
      observation: 'The request failed. Did Cedar deny it?',
      mechanism: 'An unauthenticated request can fail before policy evaluation. An authorized request can reach the tool and then fail a business condition. The visible failure alone cannot distinguish those paths.',
      evidence: 'Correlate authentication, authorization, tool execution, and database counts for the same operation key. Use the five-outcome proof and its positive controls.',
    },
    {
      observation: 'The response was suppressed after a credit committed.',
      mechanism: 'Output inspection acts on the response. It does not reverse an earlier database commit, and a new operation key can describe a second operation.',
      evidence: 'Reconcile the existing operation key with the finalized record and audit rows. Inspect the authorized same-key replay and verify that the durable business effect remains singular.',
    },
  ],
  architecture: [
    {
      observation: 'A trace names AgentCore, but the execution boundary is unclear.',
      mechanism: 'The in-process shopper path, managed shopper Runtime, and separate Operator Runtime are distinct. A diagram or configured endpoint cannot establish which one executed a particular request.',
      evidence: 'Match the exact turn or investigation to the Runtime fingerprint and execution metadata. Name the caller, tool target, owning store, and observed failure behavior at each boundary.',
    },
    {
      observation: 'An investigation produced a proposal. Has an action happened?',
      mechanism: 'The Operator graph, durable review checkpoint, human decision, and governed execution have separate responsibilities. A proposal alone is not approval or a committed remedy.',
      evidence: 'Follow the investigation ID to the review, decision, action receipt, and business record where present. Preserve an unapproved proposal as pending human review.',
    },
  ],
  evaluations: [
    {
      observation: 'The workshop cases pass. Is quality established?',
      mechanism: 'Bounded acceptance cases establish specific contracts. Broader quality requires held-out cases, explicit relevance or correctness criteria, and repeatable conditions.',
      evidence: 'Fix the build, model, query set, labels, permissions, and candidate budget. Report quality separately from latency, token usage, and cost; retain contradictory and failed runs.',
    },
    {
      observation: 'An evaluator is configured, but no scorecard exists.',
      mechanism: 'Configuration describes an intended measurement. It does not establish that requests were evaluated or that the reported sample represents the workload.',
      evidence: 'Identify the evaluated run IDs, sample size, metric definition, and result records. Keep an unavailable measurement distinct from a measured zero.',
    },
  ],
  production: [
    {
      observation: 'Sequential replay works. What about simultaneous duplicates?',
      mechanism: 'The workshop replay covers a bounded sequence. Concurrent requests can contend for the operation claim and transaction, while retries can arrive after authorization has changed.',
      evidence: 'In a separate fault rehearsal, retain overlapping invocation IDs, the shared key, action hash, current authorization, and committed business counts. Require one durable effect and explicit outcomes for every attempt.',
    },
    {
      observation: 'The connection closes while the write is completing.',
      mechanism: 'Transport failure does not establish rollback. The operation may have committed before its response was lost; assuming failure and issuing a new key risks another effect.',
      evidence: 'Define the invariant before the fault test. Inspect the original key, transaction state, receipt, and business rows, then exercise authorized recovery without assuming a successful response.',
    },
  ],
  replacement: [
    {
      observation: 'A replacement is approved, but fulfillment is pending.',
      mechanism: 'Approval, reservation, outbox delivery, and provider completion are separate states. An approved remedy does not establish that fulfillment completed.',
      evidence: 'Follow the exact replacement through its review, reservation, outbox, provider operation, and event history. Identify the pending boundary before choosing recovery.',
    },
    {
      observation: 'The fulfillment request timed out.',
      mechanism: 'The workshop simulator may have recorded the operation even when the caller did not receive its response. A timeout alone cannot establish whether retry is needed.',
      evidence: 'Reconcile the existing provider operation and outbox state before retrying. Keep simulator evidence explicitly separate from any claim about a real carrier.',
    },
  ],
};
