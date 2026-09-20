import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { motion, useReducedMotion } from 'motion/react';
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronsDownUp,
  ChevronsUpDown,
  CircleDashed,
  Copy,
  Database,
  Dot,
  GitBranch,
  Link2,
  LoaderCircle,
  Minus,
  RotateCcw,
  ShieldX,
  Sparkles,
  X,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { usePersona } from '../../../contexts/PersonaContext';
import {
  LAB_EXERCISES,
  findLabExercise,
} from '../../labs/labCatalog';
import { journeyForLab } from '../../../data/workshopJourneys';
import {
  Badge,
  ToggleGroup,
  ToggleGroupItem,
} from '../../../components/ui';
import ResponsiveImage from '../../../components/ResponsiveImage';
import MarkdownMessage from '../../../components/MarkdownMessage';
import {
  sendChatMessageStreaming,
  type ChatProduct,
  type ChatResponse,
  type ChatServiceError,
  type ResponseMode,
} from '../../../services/chat';
import type {
  EvidenceLedger,
  EvidenceLedgerEvent,
  EvidenceLedgerEventKind,
  EvidenceLedgerPhase,
  EvidenceLedgerProvenance,
  EvidenceReference,
  EvidenceSufficiencyCheck,
} from '../../../shared/evidenceLedger';
import ObservatoryCuratedTurns from './ObservatoryCuratedTurns';
import WorkbenchResources from '../../components/WorkbenchResources';
import LabHandoff from '../labs/LabHandoff';
import {
  canRunTurn,
  completeTurn,
  historyForTurn,
  type GuidedTurnEntry,
} from './guidedHistory';
import {
  FOCUS_INSPECT_STEP,
  FOCUS_PANELS,
  focusStepIndex,
  useCompactWorkbench,
} from './workbenchView';
import {
  readLabProgress,
  resumeHref,
  writeLabProgress,
  type LabProgress,
  type LabProgressStep,
} from '../../../shared/labProgress';
import './ObservatoryIndex.css';
import './ObservatoryWorkbench.css';

export type RunStatus = 'idle' | 'running' | 'complete' | 'error';

type StepKind =
  | 'routing'
  | 'memory'
  | 'guardrail'
  | 'agent'
  | 'tool'
  | 'sql'
  | 'observability';

import { RetrievalReceipt } from '../../components/RetrievalReceipt';
import {
  parseRetrievalReceipt,
  type RetrievalReceiptView,
} from '../../labs/retrievalReceipt';

interface JourneyStep {
  id: string;
  kind: StepKind;
  title: string;
  detail: string;
  status: string;
  source?: string;
  meta?: string;
  sql?: string;
  eventKind?: EvidenceLedgerEventKind;
  phase?: EvidenceLedgerPhase;
  provenance?: EvidenceLedgerProvenance;
  evidenceRef?: EvidenceReference;
  turnId?: string;
  traceId?: string | null;
  action?: {
    label: string;
    to: string;
  };
  /** Candidate ranks and scores behind a retrieval or rerank event. */
  retrieval?: RetrievalReceiptView;
  /** The receipt fields the projection attached to this event. */
  details?: Record<string, unknown>;
}

/**
 * Which receipt fields each event kind is worth reading verbatim, in the
 * order a reviewer asks about them. Everything else stays in `details` for
 * the JSON the row already links to. Policy comes first in spirit: a decision
 * without its principal, action and resource is not evidence of governance.
 */
const RECEIPT_FIELDS: Partial<
  Record<EvidenceLedgerEventKind, ReadonlyArray<[key: string, label: string]>>
> = {
  route: [
    ['rail', 'Rail'],
    ['model_config', 'Model config'],
  ],
  policy: [
    ['decision', 'Decision'],
    ['principal', 'Principal'],
    ['action', 'Action'],
    ['resource', 'Resource'],
    ['policy_name', 'Policy'],
    ['policy_engine_id', 'Policy engine'],
    ['enforcement_mode', 'Enforcement'],
    ['source', 'Source'],
  ],
  model: [
    ['model_id', 'Model'],
    ['inference_profile_id', 'Inference profile'],
    ['purpose', 'Purpose'],
    ['input_tokens', 'Input tokens'],
    ['output_tokens', 'Output tokens'],
    ['stop_reason', 'Stop reason'],
  ],
  aurora: [
    ['role_used', 'Database role'],
    ['statement_timeout', 'Statement timeout'],
    ['result_limit', 'Result limit'],
    ['row_count', 'Rows returned'],
    ['accepted', 'Accepted'],
    ['rejection_reason', 'Rejected because'],
    ['execution_outcome', 'Outcome'],
  ],
  tool: [
    ['tool', 'Tool'],
    ['caller', 'Caller'],
    ['args', 'Args'],
    ['result', 'Result'],
  ],
  retrieval: [
    ['embedding_model', 'Embedding model'],
    ['rerank_model', 'Rerank model'],
    ['candidate_count', 'Candidates'],
    ['hard_constraints', 'Hard constraints'],
    ['soft_preferences', 'Soft preferences'],
    ['relaxations', 'Relaxations'],
  ],
  response: [
    ['rail', 'Rail'],
    ['terminal_status', 'Terminal status'],
    ['citation_count', 'Citations'],
    ['tool_count', 'Tool calls'],
  ],
  operator_review: [
    ['lifecycle', 'Lifecycle'],
    ['review_id', 'Review'],
    ['action', 'Action'],
  ],
};

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value as object).length === 0;
  return false;
}

function formatReceiptValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

/** Labelled receipt fields for a step, or an empty list when it has none. */
function receiptFields(
  step: JourneyStep,
): Array<{ key: string; label: string; value: string }> {
  const details = step.details;
  if (!details) return [];
  const allowlist = step.eventKind ? RECEIPT_FIELDS[step.eventKind] : undefined;
  const pairs: Array<[string, string]> = allowlist
    ? [...allowlist]
    : Object.keys(details)
        .filter((key) => typeof details[key] !== 'object' || details[key] === null)
        .map((key) => [key, key.replace(/_/g, ' ')]);
  return pairs
    .filter(([key]) => !isEmptyValue(details[key]))
    .map(([key, label]) => ({ key, label, value: formatReceiptValue(details[key]) }));
}

type ReceiptStripSummary = {
  policy: string;
  execution: string;
  data: string;
  /**
   * Set only when two receipts for this turn cannot both be true.
   *
   * The strip exists so the three receipts can be read together; leaving a
   * reader to notice "DENY ×1" sitting beside "1 tool call audited" is how the
   * conflation the strip was built to prevent survives anyway.
   */
  conflict: string | null;
};

/**
 * The three receipts for one turn, from the ledger's own events. Policy is
 * the decision recorded, execution and data count their recorded receipts.
 * "Not recorded" is a finding, never hidden behind a neutral zero.
 */
function summarizeReceipts(steps: JourneyStep[]): ReceiptStripSummary {
  const decisions = steps
    .filter((step) => step.eventKind === 'policy')
    .map((step) => {
      const decision = String(step.details?.decision ?? step.status).toUpperCase();
      if (decision === 'ALLOW') return 'Allowed';
      if (decision === 'DENY') return 'Denied';
      if (decision === 'WOULD_DENY') return 'Would deny (not enforced)';
      if (decision === 'NOT_EVALUATED') return 'Not evaluated';
      return decision.toLowerCase().replace(/_/g, ' ');
    });
  // The exact audit-row link establishes the same attempt. A repeated tool
  // name, even on the same turn, is not enough to claim a contradiction.
  const denied = steps.filter((step) =>
    step.eventKind === 'policy' &&
    step.status === 'denied' &&
    step.turnId &&
    step.details?.audit_id !== null &&
    step.details?.audit_id !== undefined,
  );
  const conflicted = [
    ...new Set(
      steps
        .filter((step) =>
          step.eventKind === 'tool' &&
          step.evidenceRef?.kind === 'tool_audit' &&
          denied.some((policy) =>
            policy.turnId === step.turnId &&
            policy.details?.tool === step.details?.tool &&
            String(policy.details?.audit_id) === step.evidenceRef?.id,
          ),
        )
        .map((step) => String(step.details?.tool ?? ''))
        .filter(Boolean),
    ),
  ];
  const tools = steps.filter((step) => step.eventKind === 'tool');
  const aurora = steps.filter(
    (step) => step.eventKind === 'aurora' || step.eventKind === 'write',
  );
  const rejected = aurora.filter((step) => step.details?.accepted === false);
  const count = (list: string[]) =>
    [...new Set(list)]
      .map((value) => `${value} ×${list.filter((item) => item === value).length}`)
      .join(', ');
  return {
    policy: decisions.length ? count(decisions) : 'not recorded',
    execution: tools.length
      ? `${tools.length} tool ${tools.length === 1 ? 'call' : 'calls'} audited`
      : 'no tool receipt recorded',
    data: aurora.length
      ? `${aurora.length} Aurora ${aurora.length === 1 ? 'receipt' : 'receipts'}${
          rejected.length ? `, ${rejected.length} rejected` : ''
        }`
      : 'no Aurora query or write receipt recorded',
    conflict: conflicted.length
      ? `${conflicted.join(', ')} was denied and executed under the same audit-row link on this turn. ` +
        'tool_audit records only calls that ran, so these two receipts ' +
        'disagree; read both before drawing a conclusion.'
      : null,
  };
}

/**
 * Step kinds in the order a turn normally emits them. Used only for the empty
 * and pending skeleton, never presented as evidence that anything ran.
 */
const TRACE_SKELETON: StepKind[] = [
  'routing',
  'memory',
  'guardrail',
  'agent',
  'tool',
  'sql',
  'observability',
];

const TRACE_LINE_TOP = 28;

interface DbQuery {
  op?: string;
  table?: string;
  sql?: string;
  duration_ms?: number;
}

interface StreamEvent {
  type: string;
  content?: string;
  delta?: string;
  agent?: string;
  action?: string;
  status?: string;
  tool?: string;
  product?: unknown;
  queries?: DbQuery[];
  error?: string;
  message?: string;
  intent?: string;
  classifier?: string;
  response_mode?: ResponseMode;
  model_family?: 'opus' | 'sonnet' | 'haiku';
  model_id?: string;
  routing?: {
    loaded_skills?: string[];
    considered?: Array<{ name?: string; reason?: string }>;
    elapsed_ms?: number;
  };
  memory?: {
    source?: string;
    customer_id?: string;
    facts_loaded?: number;
    orders_loaded?: number;
    applied?: boolean;
    turns_loaded?: number;
    turns_persisted?: number;
    namespace_scope?: string;
    read_status?: string;
    write_status?: string;
    action_status?: string;
    retry_recommended?: boolean;
    error_code?: string;
  };
  profile?: {
    source?: string;
    customer_id?: string | null;
    facts_available?: number;
    orders_available?: number;
    available?: boolean;
  };
  guardrail?: {
    allowed?: boolean;
    action?: string;
    violations?: number;
    mode?: string;
    enforced?: boolean;
  };
  response?: {
    response?: string;
    products?: unknown[];
    rail?: string;
    orchestration?: {
      pattern?: string;
      route?: string;
      router?: string;
    };
    evidence_ledger?: EvidenceLedger;
  };
}

interface ProfileContextReceipt {
  source?: string;
  customer_id?: string | null;
  facts_available?: number;
  facts_loaded?: number;
  orders_available?: number;
  orders_loaded?: number;
  available?: boolean;
  applied?: boolean;
}

interface IntentSignal {
  intent: string;
  classifier: string;
  responseMode: ResponseMode;
  modelFamily: 'opus' | 'sonnet' | 'haiku';
  modelId: string;
}

interface VerifiedClaim {
  id: string;
  title: string;
  detail: string;
  /**
   * Ledger event this claim rests on. Present only when an emitted step
   * actually backs the claim, so a claim never advertises evidence that
   * cannot be opened.
   */
  stepId?: string;
}

function reconcileAgentResponse(current: string, candidate?: string): string {
  if (!candidate) return current;
  if (current && candidate.length < current.length * 0.5) return current;
  return candidate;
}

function mapProduct(value: unknown): ChatProduct {
  const product = (value ?? {}) as Record<string, any>;
  return {
    id: product.id ?? product.productId ?? 0,
    name: product.name ?? product.product_description ?? 'Catalog product',
    price: Number(product.price ?? 0),
    image:
      product.image ??
      product.imgUrl ??
      product.imgurl ??
      product.image_url ??
      '',
    category: product.category ?? product.category_name ?? '',
    rating: product.stars ?? product.rating,
    reviews: product.reviews,
    url: product.url ?? product.producturl,
    similarityScore:
      product.similarityScore ??
      product.similarity_score ??
      product.similarity ??
      product.relevance_score,
  };
}

function mergeProducts(current: ChatProduct[], incoming: unknown[]): ChatProduct[] {
  const next = [...current];
  incoming.map(mapProduct).forEach((product) => {
    const existingIndex = next.findIndex(
      (item) =>
        (product.id > 0 && item.id === product.id) ||
        (product.name && item.name === product.name),
    );
    if (existingIndex >= 0) next[existingIndex] = product;
    else next.push(product);
  });
  return next;
}

function productsForResponse(
  products: ChatProduct[],
  response: string,
): ChatProduct[] {
  const normalizedResponse = response.toLocaleLowerCase();
  const ranked = products.map((product, index) => ({
    product,
    index,
    mentionIndex: product.name
      ? normalizedResponse.indexOf(product.name.toLocaleLowerCase())
      : -1,
  }));
  const mentioned = ranked
    .filter((item) => item.mentionIndex >= 0)
    .sort((a, b) =>
      a.mentionIndex === b.mentionIndex
        ? a.index - b.index
        : a.mentionIndex - b.mentionIndex,
    )
    .map((item) => item.product);

  if (!mentioned.length) return products;

  return mentioned;
}

function LabsProductCard({
  product,
  role,
}: {
  product: ChatProduct;
  role: 'best-match' | 'pairing';
}) {
  return (
    <article className="observatory-product" data-product-role={role}>
      <div className="observatory-product-media">
        {product.image ? (
          <ResponsiveImage
            src={product.image}
            alt={product.name}
            loading="lazy"
            decoding="async"
            sizes="(max-width: 560px) 112px, (max-width: 959px) 44vw, 220px"
          />
        ) : (
          <span aria-hidden="true">
            {product.name.charAt(0).toUpperCase()}
          </span>
        )}
      </div>
      <div className="observatory-product-copy">
        <small>{product.category || 'Catalog result'}</small>
        <h4>{product.name}</h4>
        <strong className="observatory-product-price">
          ${product.price.toFixed(2)}
        </strong>
        <dl className="observatory-product-evidence">
          {product.similarityScore !== undefined ? (
            <div>
              <dt>Similarity</dt>
              <dd>{product.similarityScore.toFixed(3)}</dd>
            </div>
          ) : null}
          {product.rating ? (
            <div>
              <dt>Rating</dt>
              <dd>
                {product.rating.toFixed(1)}
                {product.reviews ? ` (${product.reviews})` : ''}
              </dd>
            </div>
          ) : null}
        </dl>
      </div>
    </article>
  );
}

function formatElapsed(elapsedMs: number): string {
  if (elapsedMs < 1000) return `${Math.max(0, Math.round(elapsedMs))} ms`;
  return `${(elapsedMs / 1000).toFixed(1)} s`;
}

function statusLabel(status: RunStatus): string {
  if (status === 'running') return 'Running';
  if (status === 'complete') return 'Completed';
  if (status === 'error') return 'Run failed';
  return 'Ready';
}

function runProofSummary(
  runStatus: RunStatus,
  activeTurn: number | null,
  activeQuery: string | null,
  eventCount: number,
  agentCount: number,
  sqlCount: number,
  productCount: number,
): { label: string; summary: string } {
  const turnLabel = activeTurn === null ? 'This turn' : `Turn ${activeTurn + 1}`;

  if (runStatus === 'running') {
    return {
      label: `Following ${turnLabel.toLowerCase()}`,
      summary: activeQuery ?? 'Waiting for the first emitted event.',
    };
  }
  if (runStatus === 'complete') {
    return {
      label: eventCount ? 'Evidence captured' : 'Turn complete',
      summary: `${eventCount} ${eventCount === 1 ? 'event' : 'events'}. ${agentCount} ${agentCount === 1 ? 'agent' : 'agents'}. ${sqlCount} SQL ${sqlCount === 1 ? 'query' : 'queries'}. ${productCount} ${productCount === 1 ? 'product' : 'products'}.`,
    };
  }
  if (runStatus === 'error') {
    return {
      label: `${turnLabel} needs attention`,
      summary: 'The stream stopped before the evidence trail completed.',
    };
  }
  return {
    label: 'Ready to inspect',
    summary: 'Choose an Aurora-backed guided shopper request.',
  };
}

/** Metrics read "-" before a run so an untouched page shows no false zeroes. */
function metricValue(status: RunStatus, value: number | string): string {
  if (status === 'idle') return '-';
  return String(value);
}

/**
 * Status describes the recorded operation, not whether reading its receipt
 * worked. The projection also uses unavailable for an empty retrieval or a
 * tool's null result, and not_enforced for a recorded WOULD_DENY evaluation.
 */
function evidenceStateLabel(step: JourneyStep): string {
  const { status, eventKind, details } = step;
  if (status === 'succeeded') return 'Evidence available';
  if (status === 'denied') return 'Denied';
  if (status === 'not_reached') return 'Not reached';
  if (status === 'not_enforced') {
    const decision = String(details?.decision ?? '').toUpperCase();
    if (decision === 'WOULD_DENY') return 'Would deny (not enforced)';
    if (decision === 'NOT_EVALUATED') return 'Not evaluated';
    return 'Not enforced';
  }
  if (status === 'failed' || status === 'error') {
    if (eventKind === 'aurora') return 'Query execution failed';
    if (eventKind === 'model') return 'Model invocation failed';
    if (eventKind === 'policy') return 'Policy evaluation failed';
    if (eventKind === 'memory') return 'Memory operation failed';
    if (eventKind === 'response') return 'Turn failed';
    return 'Execution failed';
  }
  if (status === 'unavailable') {
    if (
      eventKind === 'retrieval' &&
      Array.isArray(details?.citation_ids) &&
      details.citation_ids.length === 0
    ) {
      return 'No citations returned';
    }
    if (eventKind === 'tool' && step.evidenceRef?.kind === 'tool_audit') {
      return 'No result recorded';
    }
    if (eventKind === 'response' && details?.terminal_status === 'trace-pending') {
      return 'Trace pending';
    }
    if (eventKind === 'memory') return 'Memory unavailable';
    return 'Evidence unavailable';
  }
  if (['running', 'in_progress', 'executing'].includes(status)) return 'Running';
  if (status === 'completed' || status === 'complete') return 'Completed';
  if (status === 'pending') return 'Waiting';
  if (status === 'planned') return 'Planned';
  return status.replace(/_/g, ' ');
}

/** The glyph reinforces the status label; it never replaces it. */
function glyphForStatus(status: string) {
  if (status === 'succeeded' || status === 'completed' || status === 'complete') {
    return <Check size={14} strokeWidth={2.2} aria-hidden="true" />;
  }
  if (status === 'denied') return <ShieldX size={14} aria-hidden="true" />;
  if (status === 'failed' || status === 'error') {
    return <X size={14} strokeWidth={2.2} aria-hidden="true" />;
  }
  if (status === 'in_progress' || status === 'executing' || status === 'running') {
    return <LoaderCircle size={14} aria-hidden="true" />;
  }
  if (status === 'pending' || status === 'planned') {
    return <CircleDashed size={14} aria-hidden="true" />;
  }
  if (status === 'not_reached' || status === 'not_enforced' || status === 'unavailable') {
    return <Minus size={14} aria-hidden="true" />;
  }
  return <Dot size={22} aria-hidden="true" />;
}

function observabilityStep(
  response: ChatResponse,
  id: string,
): JourneyStep | null {
  const execution = response.agent_execution;
  const traceIds = Array.from(
    new Set(
      [
        execution?.trace_id,
        ...(Array.isArray(execution?.traceIds) ? execution.traceIds : []),
      ].filter(
        (traceId): traceId is string =>
          typeof traceId === 'string' && traceId.trim().length > 0,
      ),
    ),
  );
  if (!traceIds.length) return null;

  const sessionPath = response.session_id
    ? `/observatory/sessions/${encodeURIComponent(response.session_id)}/telemetry`
    : '/observatory/sessions';

  return {
    id,
    kind: 'observability',
    title: 'OpenTelemetry export',
    detail: `${traceIds.length} ${traceIds.length === 1 ? 'trace identifier' : 'trace identifiers'} emitted for this completed turn`,
    status: 'completed',
    source: 'agent_execution',
    meta: [
      execution?.otel_enabled === true ? 'SDK-backed OTEL' : 'Trace context',
      'agent / model / tool spans',
      traceIds[0],
    ].join(' / '),
    action: {
      label: response.session_id ? 'Open session telemetry' : 'Open sessions',
      to: sessionPath,
    },
  };
}

function stepKindForLedgerEvent(
  eventKind: EvidenceLedgerEventKind,
): StepKind {
  if (eventKind === 'route' || eventKind === 'plan') return 'routing';
  if (eventKind === 'memory') return 'memory';
  if (eventKind === 'policy' || eventKind === 'operator_review') {
    return 'guardrail';
  }
  if (eventKind === 'tool' || eventKind === 'write') return 'tool';
  if (
    eventKind === 'retrieval' ||
    eventKind === 'rerank' ||
    eventKind === 'aurora'
  ) {
    return 'sql';
  }
  if (eventKind === 'response') return 'observability';
  return 'agent';
}

function ledgerStep(event: EvidenceLedgerEvent): JourneyStep {
  const details = event.details ?? {};
  // The projection merges the retrieval receipt into these two events. The
  // Search pipeline page shows the same tables for a typed query; here they
  // belong to the query the shopper sent, and the action opens that page on it.
  const retrieval =
    event.eventKind === 'retrieval' || event.eventKind === 'rerank'
      ? (parseRetrievalReceipt(details) ?? undefined)
      : undefined;
  const compactMeta = [
    event.provenance,
    event.durationMs !== null && event.durationMs !== undefined
      ? `${event.durationMs} ms`
      : '',
    event.traceId ? `trace ${event.traceId}` : '',
    `${event.evidenceRef.kind}:${event.evidenceRef.id}`,
  ]
    .filter(Boolean)
    .join(' / ');
  return {
    id: `ledger-${event.sequence}-${event.evidenceRef.kind}-${event.evidenceRef.id}`,
    kind: stepKindForLedgerEvent(event.eventKind),
    eventKind: event.eventKind,
    phase: event.phase,
    title: event.title,
    detail: event.summary,
    status: event.status,
    source:
      typeof details.caller === 'string'
        ? details.caller
        : typeof details.purpose === 'string'
          ? details.purpose
          : event.evidenceRef.kind,
    meta: compactMeta,
    sql: event.sql ?? undefined,
    provenance: event.provenance,
    evidenceRef: event.evidenceRef,
    turnId: event.turnId,
    traceId: event.traceId,
    retrieval,
    details,
    action:
      event.eventKind === 'retrieval' && retrieval?.queryPreview
        ? {
            label: 'Trace this retrieval',
            to: `/observatory/search?q=${encodeURIComponent(retrieval.queryPreview)}`,
          }
        : undefined,
  };
}

function ledgerSteps(ledger: EvidenceLedger): JourneyStep[] {
  return ledger.events.map(ledgerStep);
}

function patternLabel(pattern: string): string {
  if (pattern === 'dispatcher') return 'Dispatcher';
  if (pattern === 'graph') return 'Graph';
  return pattern ? 'Unexpected pattern' : 'Server selected';
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'The live agent run failed before completion.';
}

function failureTitle(code: string | null): string {
  if (code === 'authentication_required') return 'Sign-in required';
  if (code === 'policy_denied') return 'Policy denied';
  if (code === 'workshop_build_required') return 'Complete the workshop build';
  if (code === 'invalid_request') return 'Request not accepted';
  if (code === 'service_unavailable') return 'Service unavailable';
  return 'Agent run did not complete';
}

function labelIntent(intent: string): string {
  return intent
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

const RESPONSE_MODE_META: Record<
  ResponseMode,
  { label: string; note: string }
> = {
  balanced: {
    label: 'Balanced',
    note: 'Configured Opus for editorial specialists; Sonnet for reporting.',
  },
  editorial: {
    label: 'Editorial',
    note: 'Configured Opus profile composes the specialist response.',
  },
  fast: {
    label: 'Fast',
    note: 'Configured Haiku profile composes a concise specialist response.',
  },
};

function responseModeLabel(mode: ResponseMode): string {
  return RESPONSE_MODE_META[mode].label;
}

/** "Lab 3: AgentCore managed path, Inspect evidence" for a stored position. */
function resumeLabel(progress: LabProgress): string {
  const exercise = findLabExercise(progress.lab);
  const panel = FOCUS_PANELS.find((item) => item.id === progress.step);
  const lab = exercise
    ? `Lab ${Number(exercise.number)}: ${exercise.shortTitle}`
    : 'the workbench';
  return panel ? `${lab}, ${panel.label}` : lab;
}

function labelRail(rail: string): string {
  if (rail === 'gateway-mcp') return 'Gateway MCP';
  if (rail === 'in-process') return 'In process';
  if (rail === 'runtime') return 'AgentCore Runtime';
  return rail || 'Server selected';
}

function modelDisplayName(
  family: IntentSignal['modelFamily'],
  modelId: string,
): string {
  const familyLabel =
    family === 'opus' ? 'Opus' : family === 'haiku' ? 'Haiku' : 'Sonnet';
  const version = modelId
    .match(/claude-(?:opus|sonnet|haiku)-([0-9]+(?:-[0-9]+)?)/i)?.[1]
    ?.replace('-', '.');
  return `Claude ${familyLabel}${version ? ` ${version}` : ''}`;
}

/** Format only the displayed receipt; the captured SQL remains untouched. */
function formatSqlForDisplay(sql: string): string {
  return sql
    .trim()
    .replace(
      /\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|RETURNING)\s+/gi,
      '\n$1 ',
    )
    .replace(/\s+(AND|OR)\s+/gi, '\n  $1 ');
}

function sqlBindingCount(sql: string): number {
  return sql.match(/%s|\$\d+/g)?.length ?? 0;
}

/**
 * Assemble the "Why this answer" lines.
 *
 * Every clause restates a value the turn emitted: the routing decision, the
 * tools that ran, the number of Aurora receipts captured, and the rail that
 * served it. Nothing here is the model's own account of its reasoning, which
 * the backend does not expose and which would not be evidence if it did. A
 * clause is omitted rather than guessed when its signal is absent.
 */
interface RationaleInput {
  intentSignal: IntentSignal | null;
  toolNames: string[];
  sqlCount: number;
  executionRail: string;
  executionPattern: string | null;
  executionRoute: string | null;
}

function whyThisAnswer({
  intentSignal,
  toolNames,
  sqlCount,
  executionRail,
  executionPattern,
  executionRoute,
}: RationaleInput): string[] {
  const lines: string[] = [];

  if (intentSignal) {
    lines.push(
      `Classified as a ${labelIntent(intentSignal.intent)} request by the ${intentSignal.classifier} router, then composed by ${modelDisplayName(intentSignal.modelFamily, intentSignal.modelId)}.`,
    );
  }

  if (executionPattern) {
    lines.push(
      executionRoute
        ? `Dispatched through the ${patternLabel(executionPattern)} pattern to ${labelIntent(executionRoute)}.`
        : `Dispatched through the ${patternLabel(executionPattern)} pattern.`,
    );
  }

  if (toolNames.length) {
    lines.push(
      `Grounded by ${toolNames.length === 1 ? 'the tool' : 'the tools'} ${toolNames.join(', ')}.`,
    );
  }

  if (sqlCount) {
    lines.push(
      `Aurora returned ${sqlCount} query ${sqlCount === 1 ? 'receipt' : 'receipts'} on the ${executionRail} rail.`,
    );
  }

  return lines;
}

export default function ObservatoryWorkbench() {
  const { persona, switchPersona, switching, switchError } = usePersona();
  const reduceMotion = useReducedMotion() !== false;
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedLab =
    findLabExercise(searchParams.get('lab') ?? undefined) ?? LAB_EXERCISES[0];
  const selectedJourney = journeyForLab(selectedLab.id)!;
  const selectedPersona =
    persona?.id === selectedJourney.anchorId ? persona : null;
  const storefrontJourney = selectedJourney.surface === 'storefront';
  const profileReady = !storefrontJourney || (Boolean(selectedPersona) && !switching);
  const [activeTurn, setActiveTurn] = useState<number | null>(null);
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus>('idle');
  const [steps, setSteps] = useState<JourneyStep[]>([]);
  const [products, setProducts] = useState<ChatProduct[]>([]);
  const [agentResponse, setAgentResponse] = useState('');
  const [elapsedMs, setElapsedMs] = useState(0);
  const [runError, setRunError] = useState<string | null>(null);
  const [runErrorCode, setRunErrorCode] = useState<string | null>(null);
  const [retryAllowed, setRetryAllowed] = useState(true);
  const [ledgerPending, setLedgerPending] = useState(false);
  const [responseMode, setResponseMode] =
    useState<ResponseMode>('balanced');
  const [setupOpen, setSetupOpen] = useState(false);
  const [intentSignal, setIntentSignal] = useState<IntentSignal | null>(null);
  const [executionRail, setExecutionRail] = useState('Server selected');
  const [executionPattern, setExecutionPattern] = useState<string | null>(null);
  const [executionRoute, setExecutionRoute] = useState<string | null>(null);
  const [evidenceSufficiency, setEvidenceSufficiency] = useState<
    EvidenceSufficiencyCheck[]
  >([]);
  const [durableLedger, setDurableLedger] = useState(false);
  const [copiedSqlId, setCopiedSqlId] = useState<string | null>(null);
  /**
   * Per-receipt disclosure. Absent means "use the default", which opens the
   * newest Aurora receipt so a completed run shows its proof without a click.
   * A present value is an explicit participant choice and always wins.
   */
  const [receiptOverrides, setReceiptOverrides] = useState<
    Record<string, boolean>
  >({});
  const [linkedStepId, setLinkedStepId] = useState<string | null>(null);
  // One workspace adapts to the available width; there is no expertise setting.
  const compact = useCompactWorkbench();
  // The step is addressable: Resume and a shared link both carry `?step=`.
  const focusStep = focusStepIndex(searchParams.get('step'));
  const showFocusStep = (index: number, replace = false) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set('step', FOCUS_PANELS[index].id);
      return next;
    }, { replace, preventScrollReset: true });
  };
  /**
   * Where this browser left off, read once on mount. Read once on purpose:
   * the control is a way back to a previous session, and repointing it at the
   * position the participant is currently in would make it a no-op link.
   */
  const [resumePoint] = useState<LabProgress | null>(() => readLabProgress());
  /**
   * Completed guided turns, indexed by turn. This is the conversation the
   * next turn is sent with: the journey promises each turn keeps the previous
   * one, and turn N stays disabled until turn N-1 has an entry here.
   */
  const [turnEntries, setTurnEntries] = useState<
    Array<GuidedTurnEntry | undefined>
  >([]);
  const startedAtRef = useRef<number | null>(null);
  const eventSequenceRef = useRef(0);
  const runGenerationRef = useRef(0);
  const traceListRef = useRef<HTMLOListElement | null>(null);
  const currentTraceStepRef = useRef<HTMLLIElement | null>(null);
  const stepNodesRef = useRef(new Map<string, HTMLLIElement>());
  const linkTimerRef = useRef<number | null>(null);
  const [traceLineHeight, setTraceLineHeight] = useState(0);

  /**
   * A different lab or a different shopper is a different run, so nothing
   * from the previous one survives it.
   *
   * Keyed on `customer_id` rather than the persona object because that is the
   * identity the run actually sends. A provider that rebuilds the object for
   * the same shopper would otherwise wipe a live run, and since this effect
   * assigns fresh arrays and objects React can never bail out on an unchanged
   * value: every pass would schedule the next one.
   */
  useEffect(() => {
    // A late stream must never populate another lab or shopper's evidence.
    runGenerationRef.current += 1;
    startedAtRef.current = null;
    setActiveTurn(null);
    setActiveQuery(null);
    setRunStatus('idle');
    setSteps([]);
    setProducts([]);
    setAgentResponse('');
    setElapsedMs(0);
    setRunError(null);
    setRunErrorCode(null);
    setRetryAllowed(true);
    setLedgerPending(false);
    setIntentSignal(null);
    setExecutionRail('Server selected');
    setExecutionPattern(null);
    setExecutionRoute(null);
    setEvidenceSufficiency([]);
    setDurableLedger(false);
    setCopiedSqlId(null);
    setReceiptOverrides({});
    setLinkedStepId(null);
    setTurnEntries([]);
    return () => {
      runGenerationRef.current += 1;
      startedAtRef.current = null;
    };
  }, [selectedJourney.anchorId, selectedPersona?.customer_id]);

  // A highlight timer that outlives its node would fire against a step from a
  // previous run, so it is cancelled on unmount.
  useEffect(
    () => () => {
      if (linkTimerRef.current !== null) {
        window.clearTimeout(linkTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (runStatus !== 'running') return undefined;
    const interval = window.setInterval(() => {
      if (startedAtRef.current !== null) {
        setElapsedMs(Date.now() - startedAtRef.current);
      }
    }, 100);
    return () => window.clearInterval(interval);
  }, [runStatus]);

  const updateAgentStep = (event: StreamEvent) => {
    const agent = event.agent || 'Agent';
    setSteps((current) => {
      const existingIndex = current.findIndex(
        (step) => step.kind === 'agent' && step.source === agent,
      );
      const next: JourneyStep = {
        id:
          existingIndex >= 0
            ? current[existingIndex].id
            : `agent-${eventSequenceRef.current++}`,
        kind: 'agent',
        title: agent,
        detail: event.action || 'Agent lifecycle update',
        status: event.status || 'in_progress',
        source: agent,
        eventKind: 'model',
        phase: 'reasoning',
        provenance: 'live-emitted-event',
      };
      if (existingIndex < 0) return [...current, next];
      return current.map((step, index) => (index === existingIndex ? next : step));
    });
  };

  const addToolStep = (event: StreamEvent) => {
    const tool = event.tool || 'Tool';
    setSteps((current) => [
      ...current,
      {
        id: `tool-${eventSequenceRef.current++}`,
        kind: 'tool',
        title: tool,
        detail: 'Tool invocation emitted by the live agent',
        status: event.status || 'executing',
        source: tool,
        eventKind: 'tool',
        phase: 'execution',
        provenance: 'live-emitted-event',
      },
    ]);
  };

  const addRoutingStep = (event: StreamEvent) => {
    const loaded = event.routing?.loaded_skills ?? [];
    const considered = event.routing?.considered?.length ?? 0;
    setSteps((current) => [
      ...current,
      {
        id: `routing-${eventSequenceRef.current++}`,
        kind: 'routing',
        title: 'Skill routing',
        detail: loaded.length
          ? `Loaded ${loaded.join(', ')}`
          : 'No optional skills loaded for this turn',
        status: 'completed',
        eventKind: 'route',
        phase: 'routing',
        provenance: 'live-emitted-event',
        meta: [
          considered ? `${considered} considered` : '',
          event.routing?.elapsed_ms !== undefined
            ? `${Math.round(event.routing.elapsed_ms)} ms`
            : '',
        ]
          .filter(Boolean)
          .join(' / '),
      },
    ]);
  };

  const addAuroraProfileStep = (event: StreamEvent) => {
    const profile: ProfileContextReceipt = event.profile ?? event.memory ?? {};
    const facts = profile.facts_available ?? profile.facts_loaded ?? 0;
    const orders = profile.orders_available ?? profile.orders_loaded ?? 0;
    const live = profile.source === 'aurora';
    const available =
      profile.available ?? (live && profile.applied !== false);
    const legacyMemoryEvent = !event.profile;
    setSteps((current) => [
      ...current,
      {
        id: `memory-${eventSequenceRef.current++}`,
        kind: 'memory',
        title: 'Aurora profile context',
        detail: live && available
          ? `${facts} profile ${facts === 1 ? 'fact' : 'facts'} and ${orders} past ${orders === 1 ? 'order' : 'orders'} ${legacyMemoryEvent ? 'loaded' : 'available'}`
          : 'No live Aurora profile context was available for this turn',
        status: live && available ? 'completed' : 'unavailable',
        eventKind: 'memory',
        phase: 'context',
        provenance: 'live-emitted-event',
        meta: [profile.source || 'unavailable', profile.customer_id || '']
          .filter(Boolean)
          .join(' / '),
      },
    ]);
  };

  const addAgentCoreMemoryStep = (event: StreamEvent) => {
    const memory = event.memory ?? {};
    const loaded = memory.turns_loaded ?? 0;
    const persisted = memory.turns_persisted ?? 0;
    const readFailed = memory.read_status === 'failed';
    const writeFailed = memory.write_status === 'failed';
    const memoryFailed = readFailed || writeFailed;
    setSteps((current) => [
      ...current,
      {
        id: `agentcore-memory-${eventSequenceRef.current++}`,
        kind: 'memory',
        title: 'AgentCore Memory',
        detail: readFailed
          ? 'Prior managed-memory context was unavailable; this action ran without it'
          : writeFailed
          ? `${loaded} prior ${loaded === 1 ? 'turn' : 'turns'} read; the completed action was not appended`
          : `${loaded} prior ${loaded === 1 ? 'turn' : 'turns'} read; ${persisted} new turns persisted`,
        status:
          memory.source === 'agentcore-memory' && !memoryFailed
            ? 'completed'
            : 'unavailable',
        eventKind: 'memory',
        phase: 'context',
        provenance: 'agentcore-service-telemetry',
        meta: [
          memory.source,
          memory.namespace_scope,
          readFailed ? 'prior context unavailable' : '',
          writeFailed ? 'do not repeat the action' : '',
        ]
          .filter(Boolean)
          .join(' / '),
      },
    ]);
  };

  const addGuardrailStep = (event: StreamEvent) => {
    const guardrail = event.guardrail ?? {};
    const allowed = guardrail.allowed !== false;
    setSteps((current) => [
      ...current,
      {
        id: `guardrail-${eventSequenceRef.current++}`,
        kind: 'guardrail',
        title: 'Input safety inspection',
        detail: allowed
          ? 'Request evaluated before agent execution'
          : 'Request flagged by the input evaluation',
        status: guardrail.action === 'ERROR' ? 'error' : 'completed',
        eventKind: 'policy',
        phase: 'governance',
        provenance: 'live-emitted-event',
        meta: [
          guardrail.mode || 'configured',
          guardrail.action || 'NONE',
          guardrail.enforced ? 'enforced' : 'inspect only',
        ].join(' / '),
      },
    ]);
  };

  const addSqlSteps = (queries: DbQuery[]) => {
    const captured = queries.filter(
      (queryItem): queryItem is DbQuery & { sql: string } =>
        typeof queryItem.sql === 'string' && queryItem.sql.trim().length > 0,
    );
    if (!captured.length) return;
    setSteps((current) => [
      ...current,
      ...captured.map((queryItem) => ({
        id: `sql-${eventSequenceRef.current++}`,
        kind: 'sql' as const,
        title: [queryItem.op?.toUpperCase(), queryItem.table]
          .filter(Boolean)
          .join(' / ') || 'Database query',
        detail: 'Aurora emitted a query receipt with source and timing metadata',
        status: 'completed',
        eventKind: 'aurora' as const,
        phase: 'execution' as const,
        provenance: 'live-emitted-event' as const,
        meta:
          queryItem.duration_ms !== undefined
            ? `${queryItem.duration_ms} ms`
            : undefined,
        sql: queryItem.sql,
      })),
    ]);
  };

  const handleStreamEvent = (rawEvent: unknown) => {
    const event = rawEvent as StreamEvent;

    if (event.type === 'content_reset') {
      setAgentResponse('');
    } else if (event.type === 'content_delta' && event.delta) {
      setAgentResponse((current) => current + event.delta);
    } else if (event.type === 'content' && event.content !== undefined) {
      setAgentResponse((current) =>
        reconcileAgentResponse(current, event.content),
      );
    } else if (event.type === 'product' && event.product) {
      setProducts((current) => mergeProducts(current, [event.product]));
    } else if (
      event.type === 'intent_signal' &&
      event.intent &&
      event.response_mode &&
      event.model_family
    ) {
      setIntentSignal({
        intent: event.intent,
        classifier: event.classifier || 'deterministic',
        responseMode: event.response_mode,
        modelFamily: event.model_family,
        modelId: event.model_id || '',
      });
    } else if (event.type === 'skill_routing') {
      addRoutingStep(event);
    } else if (
      event.type === 'memory_context' ||
      event.type === 'aurora_profile_context'
    ) {
      addAuroraProfileStep(event);
    } else if (event.type === 'agentcore_memory') {
      addAgentCoreMemoryStep(event);
    } else if (event.type === 'guardrail_decision') {
      addGuardrailStep(event);
    } else if (event.type === 'agent_step') {
      updateAgentStep(event);
    } else if (event.type === 'tool_call') {
      addToolStep(event);
    } else if (event.type === 'db_queries') {
      addSqlSteps(Array.isArray(event.queries) ? event.queries : []);
    } else if (event.type === 'complete') {
      if (event.response?.response) {
        setAgentResponse((current) =>
          reconcileAgentResponse(current, event.response?.response),
        );
      }
      if (event.response?.rail) {
        setExecutionRail(labelRail(event.response.rail));
      }
      if (event.response?.orchestration?.pattern) {
        setExecutionPattern(event.response.orchestration.pattern);
        setExecutionRoute(event.response.orchestration.route || null);
      }
      if (Array.isArray(event.response?.products)) {
        setProducts((current) =>
          mergeProducts(current, event.response?.products ?? []),
        );
      }
      if (event.response?.evidence_ledger) {
        setSteps(ledgerSteps(event.response.evidence_ledger));
        setEvidenceSufficiency(
          event.response.evidence_ledger.evidenceSufficiency,
        );
        setDurableLedger(true);
      }
    } else if (event.type === 'error') {
      setRunError(
        event.error || event.message || 'The agent reported an execution error.',
      );
    }
  };

  /** Run one Aurora-backed guided shopper request through the live stream. */
  const runAgent = async (
    curatedQuery: string,
    turnIndex: number | null,
  ) => {
    const request = curatedQuery.trim();
    if (!request || runStatus === 'running' || !profileReady) return;
    // Turn N is not a fresh conversation: it may only run once turn N-1 has
    // completed, because it is sent with that turn's exchange behind it.
    // Explore prompts are exempt, which is the predicate's business, not
    // this call site's: the request rail disables exactly what this refuses.
    if (turnIndex !== null && !canRunTurn(turnEntries, turnIndex)) return;

    const conversationHistory =
      turnIndex === null ? [] : historyForTurn(turnEntries, turnIndex);
    const generation = ++runGenerationRef.current;
    const isCurrentRun = () => generation === runGenerationRef.current;
    let turnId: string | null = null;

    setActiveTurn(turnIndex);
    setActiveQuery(request);
    eventSequenceRef.current = 0;
    startedAtRef.current = Date.now();
    setRunStatus('running');
    setRunError(null);
    setRunErrorCode(null);
    setRetryAllowed(true);
    setLedgerPending(false);
    setSteps([]);
    setProducts([]);
    setAgentResponse('');
    setElapsedMs(0);
    setIntentSignal(null);
    setExecutionRail('Server selected');
    setExecutionPattern(null);
    setExecutionRoute(null);
    setEvidenceSufficiency([]);
    setDurableLedger(false);
    setCopiedSqlId(null);
    setReceiptOverrides({});
    setLinkedStepId(null);

    try {
      const response: ChatResponse = await sendChatMessageStreaming(
        request,
        conversationHistory,
        (event) => {
          if (!isCurrentRun()) return;
          if (event.type === 'turn_start' && typeof event.turn_id === 'string') {
            turnId = event.turn_id;
          }
          handleStreamEvent(event);
        },
        undefined,
        false,
        selectedPersona?.customer_id ?? null,
        'dispatcher',
        responseMode,
      );
      if (!isCurrentRun()) return;
      if (response.response) {
        setAgentResponse((current) =>
          reconcileAgentResponse(current, response.response),
        );
      }
      if (response.products?.length) {
        setProducts((current) => mergeProducts(current, response.products));
      }
      if (response.evidence_ledger) {
        setSteps(ledgerSteps(response.evidence_ledger));
        setEvidenceSufficiency(
          response.evidence_ledger.evidenceSufficiency,
        );
        setDurableLedger(true);
      } else {
        const emittedObservability = observabilityStep(
          response,
          `observability-${eventSequenceRef.current++}`,
        );
        setSteps((current) => {
          const completed = current.map((step) => ({
            ...step,
            status:
              step.status === 'in_progress' || step.status === 'executing'
                ? 'completed'
                : step.status,
          }));
          return emittedObservability
            ? [...completed, emittedObservability]
            : completed;
        });
      }
      if (turnIndex !== null) {
        const answer = response.response ?? '';
        setTurnEntries((current) =>
          completeTurn(current, turnIndex, {
            query: request,
            answer,
            products: response.products ?? [],
          }),
        );
      }
      setRunStatus('complete');
      // The evidence panel is only worth reading once there is evidence in
      // it. While the turn streams, the request rail is the useful view, so
      // focus mode moves to Inspect on completion rather than on dispatch.
      showFocusStep(FOCUS_INSPECT_STEP, true);
    } catch (error) {
      if (!isCurrentRun()) return;
      const failure = error as Partial<ChatServiceError> | null;
      setRunError(errorMessage(error));
      setRunErrorCode(failure?.code ?? null);
      setRetryAllowed(failure?.retryable !== false);
      setRunStatus('error');
      setSteps((current) => current.map((step) =>
        ['running', 'in_progress', 'executing'].includes(step.status)
          ? { ...step, status: 'unavailable' }
          : step,
      ));
      if (startedAtRef.current !== null) {
        setElapsedMs(Date.now() - startedAtRef.current);
        startedAtRef.current = null;
      }
      showFocusStep(FOCUS_INSPECT_STEP, true);
      // The server persists a failed or denied turn before emitting its error.
      // Read that exact principal-scoped ledger; never replay the action to
      // obtain evidence. HTTP failures without a turn id have nothing to read.
      if (turnId) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 8000);
        setLedgerPending(true);
        try {
          const result = await fetch(
            `/api/observatory/turns/${encodeURIComponent(turnId)}/ledger`,
            { credentials: 'include', signal: controller.signal },
          );
          if (result.ok && isCurrentRun()) {
            const ledger = await result.json() as EvidenceLedger;
            if (
              isCurrentRun() &&
              ledger.authority === 'canonical-receipt-projection' &&
              ledger.principalScoped === true &&
              ledger.turnId === turnId &&
              Array.isArray(ledger.events) &&
              Array.isArray(ledger.evidenceSufficiency)
            ) {
              setSteps(ledgerSteps(ledger));
              setEvidenceSufficiency(ledger.evidenceSufficiency);
              setDurableLedger(true);
            }
          }
        } catch {
          // Keep received live events; an unreadable ledger is not an empty one.
        } finally {
          window.clearTimeout(timeout);
          if (isCurrentRun()) setLedgerPending(false);
        }
      }
    } finally {
      if (isCurrentRun()) {
        if (startedAtRef.current !== null) {
          setElapsedMs(Date.now() - startedAtRef.current);
        }
        startedAtRef.current = null;
      }
    }
  };

  const agentCount = new Set(
    steps
      .filter((step) => step.kind === 'agent' && step.source)
      .map((step) => step.source),
  ).size;
  const sqlCount = steps.filter((step) => Boolean(step.sql)).length;
  const orderedProducts = productsForResponse(products, agentResponse);
  const bestMatch = orderedProducts[0];
  const supportingProducts = orderedProducts.slice(1);
  const currentStepId =
    runStatus === 'running' && steps.length
      ? steps[steps.length - 1].id
      : null;

  useEffect(() => {
    const currentStep = currentTraceStepRef.current;
    if (!currentStepId || !currentStep?.scrollIntoView) return;
    currentStep.scrollIntoView({
      block: 'nearest',
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }, [currentStepId, reduceMotion]);

  useLayoutEffect(() => {
    const list = traceListRef.current;
    const latestStep = currentTraceStepRef.current;

    if (!steps.length || !list || !latestStep) {
      setTraceLineHeight(0);
      return undefined;
    }

    const measure = () => {
      const listRect = list.getBoundingClientRect();
      const stepRect = latestStep.getBoundingClientRect();
      const nextHeight =
        stepRect.bottom - listRect.top - TRACE_LINE_TOP - 10;
      setTraceLineHeight(Math.max(0, nextHeight));
    };

    measure();

    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    return () => observer.disconnect();
  }, [currentStepId, steps.length]);

  const verifiedClaims: VerifiedClaim[] = [];
  const latestSqlStep = [...steps]
    .reverse()
    .find((step) => step.kind === 'sql');
  const firstToolStep = steps.find((step) => step.kind === 'tool');
  const routingStep = steps.find((step) => step.kind === 'routing');
  const toolNames = Array.from(
    new Set(
      steps
        .filter((step) => step.kind === 'tool' && step.source)
        .map((step) => step.source as string),
    ),
  );
  if (sqlCount) {
    verifiedClaims.push({
      id: 'sql',
      title: `${sqlCount} database ${sqlCount === 1 ? 'lookup' : 'lookups'} captured`,
      detail: [latestSqlStep?.title, latestSqlStep?.meta]
        .filter(Boolean)
        .join(' / '),
      stepId: latestSqlStep?.id,
    });
  }
  if (bestMatch) {
    const productContext = [
      bestMatch.category,
      bestMatch.price > 0 ? `$${bestMatch.price.toFixed(2)}` : '',
    ]
      .filter(Boolean)
      .join(' / ');
    verifiedClaims.push({
      id: 'products',
      title:
        products.length === 1
          ? `${bestMatch.name} returned by the live turn`
          : `${bestMatch.name} and ${products.length - 1} more returned`,
      detail: productContext || 'Grounded catalog evidence from this turn.',
      // The tool call is the step that produced the products. Absent a tool
      // event the claim stands on its own without a link to open.
      stepId: firstToolStep?.id,
    });
  }
  if (executionPattern) {
    verifiedClaims.push({
      id: 'route',
      title: `${patternLabel(executionPattern)} route`,
      detail: executionRoute
        ? `Completed through ${labelIntent(executionRoute)}.`
        : `Completed through ${executionRail}.`,
      stepId: routingStep?.id,
    });
  }

  const linkedClaimCount = verifiedClaims.filter((claim) =>
    Boolean(claim.stepId),
  ).length;

  const rationale = whyThisAnswer({
    intentSignal,
    toolNames,
    sqlCount,
    executionRail,
    executionPattern,
    executionRoute,
  });

  const receiptSteps = steps.filter((step) => Boolean(step.sql));
  const receiptStepCount = receiptSteps.length;

  /** Explicit choice beats the default, which opens the newest receipt. */
  const isReceiptOpen = (step: JourneyStep): boolean => {
    if (!step.sql && !step.retrieval && receiptFields(step).length === 0) {
      return false;
    }
    const override = receiptOverrides[step.id];
    if (override !== undefined) return override;
    return step.id === latestSqlStep?.id;
  };

  const toggleReceipt = (step: JourneyStep) => {
    const next = !isReceiptOpen(step);
    setReceiptOverrides((current) => ({ ...current, [step.id]: next }));
  };

  const allReceiptsOpen =
    receiptStepCount > 0 && receiptSteps.every(isReceiptOpen);

  /**
   * Bulk disclosure writes an explicit state for every receipt rather than
   * clearing the overrides. Clearing would fall back to the default, which
   * opens the newest receipt, so "Collapse all" would leave one open.
   */
  const toggleAllReceipts = () => {
    const next = !allReceiptsOpen;
    setReceiptOverrides(
      Object.fromEntries(receiptSteps.map((step) => [step.id, next])),
    );
  };

  /**
   * Open a claim's supporting event: scroll it into the ledger's viewport and
   * mark it so the relationship is visible rather than asserted.
   */
  const openLinkedStep = (stepId: string) => {
    setLinkedStepId(stepId);
    const step = steps.find((item) => item.id === stepId);
    if (step) {
      setReceiptOverrides((current) => ({ ...current, [stepId]: true }));
    }
    if (compact) showFocusStep(FOCUS_INSPECT_STEP);
    if (linkTimerRef.current !== null) {
      window.clearTimeout(linkTimerRef.current);
    }
    linkTimerRef.current = window.setTimeout(() => {
      setLinkedStepId(null);
      linkTimerRef.current = null;
    }, 2200);
  };

  // Navigation must reveal the ledger before a claim can scroll to its event.
  useEffect(() => {
    if (!linkedStepId || (compact && focusStep !== FOCUS_INSPECT_STEP)) return;
    stepNodesRef.current.get(linkedStepId)?.scrollIntoView?.({
      block: 'center',
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }, [linkedStepId, compact, focusStep, reduceMotion]);

  const proofSummary = runProofSummary(
    runStatus,
    activeTurn,
    activeQuery,
    steps.length,
    agentCount,
    sqlCount,
    products.length,
  );

  const focusMode = storefrontJourney && compact;
  const currentStep = (FOCUS_PANELS[focusStep] ?? FOCUS_PANELS[0]).id;

  // Record the position as it changes so a closed tab is recoverable. The
  // next action is the lab's own participant TODO, not an invented instruction.
  useEffect(() => {
    writeLabProgress({
      lab: selectedLab.id,
      step: currentStep as LabProgressStep,
      nextAction: selectedLab.participantTodo,
    });
  }, [selectedLab.id, selectedLab.participantTodo, currentStep]);

  const activeFocusPanel = FOCUS_PANELS[focusStep] ?? FOCUS_PANELS[0];
  /** In focus mode only the current step's panel is mounted-visible. */
  const focusProps = (panel: 'requests' | 'trace' | 'results') =>
    focusMode
      ? {
          'data-focus-active': activeFocusPanel.panel === panel ? 'true' : 'false',
          hidden: activeFocusPanel.panel !== panel,
        }
      : {};

  const copySql = async (step: JourneyStep) => {
    if (!step.sql || !navigator.clipboard?.writeText) return;
    try {
      await navigator.clipboard.writeText(step.sql);
      setCopiedSqlId(step.id);
    } catch {
      setCopiedSqlId(null);
    }
  };

  /*
   * Resume only when it leads somewhere other than what is already on screen.
   * It carries a lab AND a step, so it is a real shortcut when either differs;
   * pointing at the lab you are looking at, it was a button that did nothing.
   */
  const shownPanelId = FOCUS_PANELS[focusStep]?.id;
  const resumeElsewhere =
    resumePoint !== null &&
    (resumePoint.lab !== selectedLab.id ||
      (focusMode && resumePoint.step !== shownPanelId));

  /*
   * Sufficiency and claims are a result, not a promise. Before the first turn
   * the column says one thing; once a turn has settled they appear even when
   * they are empty. Only a received ledger can establish an empty result;
   * without one, the result is unavailable.
   */
  const turnSettled =
    runStatus === 'complete' ||
    runStatus === 'error';

  // One visible run summary in either mode. Focus mode keeps it above the
  // panels so status remains available while Run or Reconcile is selected.
  const runSummary = (
    <div
      className="observatory-run-summary"
      role="status"
      aria-label="Run proof summary"
      aria-live="polite"
    >
      <span className="observatory-run-summary-copy">
        {proofSummary.label}. {proofSummary.summary}
      </span>
      <Badge
        variant={
          runStatus === 'complete'
            ? 'success'
            : runStatus === 'error'
              ? 'destructive'
              : runStatus === 'running'
                ? 'warning'
                : 'neutral'
        }
        className="observatory-live-state"
        data-status={runStatus}
      >
        {runStatus === 'error' && runErrorCode === 'policy_denied'
          ? 'Denied'
          : runStatus === 'error' && runErrorCode === 'authentication_required'
            ? 'Sign-in required'
            : statusLabel(runStatus)}
      </Badge>
    </div>
  );

  return (
    <div className="observatory-workbench labs-index">
      <div className="labs-index-inner">
        <header className="observatory-workbench-intro">
          <div className="observatory-workbench-intro-copy">
            <h1 className="observatory-page-title font-display">
              Workbench
            </h1>
          </div>
          {resumeElsewhere ? <div className="observatory-workbench-intro-aside">
            {resumeElsewhere ? (
              <Link
                className="observatory-resume"
                to={resumeHref(resumePoint as LabProgress)}
                aria-label={`Resume ${resumeLabel(resumePoint as LabProgress)}`}
              >
                <RotateCcw size={14} aria-hidden="true" />
                <span>
                  Resume
                  <small>{resumeLabel(resumePoint as LabProgress)}</small>
                </span>
              </Link>
            ) : null}
          </div> : null}
        </header>
        {focusMode ? (
          <nav
            className="observatory-focus-steps"
            aria-label="Workbench steps"
          >
            {FOCUS_PANELS.map((panel, index) => (
              <button
                key={panel.id}
                type="button"
                data-state={
                  index === focusStep
                    ? 'current'
                    : index < focusStep
                      ? 'done'
                      : 'ahead'
                }
                aria-current={index === focusStep ? 'step' : undefined}
                onClick={() => showFocusStep(index)}
              >
                <span aria-hidden="true">{index + 1}</span>
                {panel.label}
              </button>
            ))}
          </nav>
        ) : null}
        {/* The portraits introduce the scenarios on the Lab Collection. Here the
            same four destinations are a switcher, so the Workbench does not
            open with a second copy of that gallery. Still links: deep links,
            Back/Forward and keyboard focus behave exactly as before. */}
        <nav className="observatory-lab-switch" aria-label="Select a lab">
          {LAB_EXERCISES.map((exercise) => {
            const selected = exercise.id === selectedLab.id;
            return (
              <Link
                key={exercise.id}
                to={`/observatory/workbench?lab=${exercise.id}`}
                className="observatory-lab-switch-option"
                data-selected={selected ? 'true' : undefined}
                aria-current={selected ? 'step' : undefined}
                aria-label={`Lab ${Number(exercise.number)} ${exercise.anchorName}: ${exercise.title}`}
              >
                <span aria-hidden="true">{Number(exercise.number)}</span>
                {exercise.anchorName}
              </Link>
            );
          })}
        </nav>
        <div className="observatory-workbench-task">
          <h2>Lab {Number(selectedLab.number)}: {selectedLab.title}</h2>
          <p className="observatory-workbench-purpose">{selectedLab.objective}</p>
          <p className="observatory-workbench-studio-note">Follow Lab {Number(selectedLab.number)} in Workshop Studio. Use this workspace to run the scenario and inspect its evidence.</p>
        </div>
        {focusMode ? (
          <div className="observatory-workbench-status">{runSummary}</div>
        ) : null}
        <div
          className="observatory-workbench-grid"
          data-view={storefrontJourney ? (compact ? 'focus' : 'wide') : 'operator'}
          aria-label={storefrontJourney ? 'Live agent run' : 'Operator investigation handoff'}
        >
          <motion.aside
            className="observatory-input-panel"
            data-motion-panel="requests"
            aria-label="Guided requests and run settings"
            {...focusProps('requests')}
            initial={
              reduceMotion
                ? false
                : {
                    opacity: 0,
                    clipPath: 'inset(0 100% 0 0 round 14px)',
                  }
            }
            animate={{ opacity: 1, clipPath: 'inset(0 0 0 0 round 14px)' }}
            transition={{
              duration: reduceMotion ? 0 : 0.46,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            <ObservatoryCuratedTurns
              journey={selectedJourney}
              running={runStatus === 'running'}
              activeIndex={activeTurn}
              ready={profileReady}
              canRunTurn={(index) => canRunTurn(turnEntries, index)}
              anchorError={switchError}
              selectingScenario={switching}
              onSelectScenario={() => { void switchPersona(selectedJourney.anchorId); }}
              onInspect={(curatedQuery, index) => {
                void runAgent(curatedQuery, index);
              }}
            />

            {storefrontJourney ? <section
              className="observatory-run-controls"
              aria-label="Run setup"
            >
              <header className="observatory-run-controls-heading">
                <button
                  type="button"
                  className="observatory-run-setup-toggle"
                  aria-expanded={setupOpen}
                  aria-controls="observatory-run-setup-options"
                  aria-label={setupOpen ? 'Hide run setup' : 'Show run setup'}
                  onClick={() => setSetupOpen((open) => !open)}
                >
                  <span>
                    <GitBranch size={14} aria-hidden="true" />
                    Run setup
                  </span>
                  <span className="observatory-run-setup-toggle-action">
                    {setupOpen ? 'Hide' : 'Tune'}
                    <ChevronDown
                      size={15}
                      aria-hidden="true"
                      data-open={setupOpen ? 'true' : 'false'}
                    />
                  </span>
                </button>
                <Badge variant="neutral">
                  {selectedJourney.surface === 'operator'
                    ? 'Operator handoff'
                    : 'Storefront Dispatcher'}
                </Badge>
              </header>

              {setupOpen ? (
                <div
                  id="observatory-run-setup-options"
                  className="observatory-compact-controls"
                >
                  <fieldset>
                    <legend>Response mode</legend>
                    <ToggleGroup
                      type="single"
                      value={responseMode}
                      aria-label="Response mode"
                      className="observatory-segmented"
                      data-columns="3"
                      onValueChange={(value) => {
                        if (value) setResponseMode(value as ResponseMode);
                      }}
                    >
                      {(['editorial', 'balanced', 'fast'] as ResponseMode[]).map(
                        (mode) => (
                          <ToggleGroupItem
                            key={mode}
                            value={mode}
                            aria-label={responseModeLabel(mode)}
                            disabled={runStatus === 'running'}
                          >
                            {responseModeLabel(mode)}
                          </ToggleGroupItem>
                        ),
                      )}
                    </ToggleGroup>
                    <p className="observatory-mode-note">
                      {RESPONSE_MODE_META[responseMode].note}
                    </p>
                  </fieldset>

                  {storefrontJourney ? (
                    profileReady && selectedPersona ? (
                      <div className="observatory-profile-control">
                        <div>
                          <strong>Aurora profile context</strong>
                          <small>
                            Bound to {selectedPersona.display_name}&rsquo;s
                            current facts and order history for this lab
                          </small>
                        </div>
                      </div>
                    ) : (
                      <p className="observatory-profile-unavailable">
                        {switchError
                          ? `Unable to open ${selectedJourney.anchorName}'s guided session: ${switchError}`
                          : `Choose ${selectedJourney.anchorName} above before running these Aurora-backed turns. Scenario selection does not authenticate the caller.`}
                      </p>
                    )
                  ) : (
                    <p className="observatory-profile-unavailable">
                      Jessica&rsquo;s case continues in the separately
                      authenticated Operator surface.
                    </p>
                  )}
                </div>
              ) : null}

              <div className="observatory-run-foot">
                <p className="observatory-provenance">
                  Live SSE from <code>/api/chat/stream</code>, reconciled to
                  principal-scoped Aurora receipts when the turn completes.
                </p>
              </div>
            </section> : (
              <section className="observatory-operator-next" aria-labelledby="operator-next-title">
                <h3 id="operator-next-title">Carry the proof into the decision</h3>
                <p>
                  Lab 4 separates authentication failure, Cedar denial, business
                  refusal, commit, and output suppression. Its replay controls
                  check that one operation key retains one effect. Jessica’s Operator investigation uses those
                  distinctions to prepare a decision for human review.
                </p>
                <p>
                  Open the staff desk with an Operator account, then inspect
                  its recorded evidence. Preparing a review does not execute
                  the proposed action.
                </p>
                <Link to="/observatory/govern/verification">Review the Lab 4 proof</Link>
                <Link to="/observatory/operator-lineage">Inspect recorded Operator evidence</Link>
              </section>
            )}

          </motion.aside>

          {storefrontJourney ? <>
          <motion.section
            className="observatory-trace-panel"
            data-motion-panel="trace"
            aria-labelledby="live-journey-title"
            {...focusProps('trace')}
            initial={
              reduceMotion
                ? false
                : {
                    opacity: 0,
                    clipPath: 'inset(0 0 100% 0 round 14px)',
                  }
            }
            animate={{ opacity: 1, clipPath: 'inset(0 0 0 0 round 14px)' }}
            transition={{
              duration: reduceMotion ? 0 : 0.46,
              delay: reduceMotion ? 0 : 0.07,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            <div className="observatory-section-heading">
              <div>
                <h2 id="live-journey-title">Evidence ledger</h2>
                <p>
                  {activeQuery ??
                    'A live timeline of emitted decisions and evidence.'}
                </p>
                {steps.length && durableLedger ? (
                  <dl
                    className="observatory-receipt-strip"
                    data-testid="observatory-receipt-strip"
                    aria-label="The three receipts for this turn"
                  >
                    {(() => {
                      const receipts = summarizeReceipts(steps);
                      return (
                        <>
                          <div>
                            <dt>Policy</dt>
                            <dd>{receipts.policy}</dd>
                          </div>
                          <div>
                            <dt>Execution</dt>
                            <dd>{receipts.execution}</dd>
                          </div>
                          <div>
                            <dt>Data</dt>
                            <dd>{receipts.data}</dd>
                          </div>
                          {receipts.conflict ? (
                            <div
                              className="observatory-receipt-conflict"
                              data-testid="observatory-receipt-conflict"
                            >
                              <dt>Conflict</dt>
                              <dd>{receipts.conflict}</dd>
                            </div>
                          ) : null}
                        </>
                      );
                    })()}
                  </dl>
                ) : null}
              </div>
              {/* Only offered when there is more than one receipt to act on;
                  a control that cannot change anything is not an affordance. */}
              {receiptStepCount > 1 ? (
                <button
                  type="button"
                  className="observatory-ledger-action"
                  aria-pressed={allReceiptsOpen}
                  onClick={toggleAllReceipts}
                >
                  {allReceiptsOpen ? (
                    <ChevronsDownUp size={14} aria-hidden="true" />
                  ) : (
                    <ChevronsUpDown size={14} aria-hidden="true" />
                  )}
                  {allReceiptsOpen ? 'Collapse all' : 'Expand all'}
                </button>
              ) : null}
              {!focusMode ? runSummary : null}
            </div>

            <div
              className="observatory-panel-scroll observatory-ledger-scroll"
              data-idle={
                !intentSignal &&
                !runError &&
                steps.length === 0 &&
                runStatus === 'idle'
                  ? 'true'
                  : undefined
              }
            >
              {intentSignal ? (
                <section
                  className="observatory-run-contract"
                  role="status"
                  aria-label="Execution context"
                >
                  <header>
                    <div>
                      <span>Routing decision</span>
                      <strong>
                        {labelIntent(intentSignal.intent)} request
                      </strong>
                    </div>
                    <Badge
                      variant="neutral"
                      className="observatory-run-mode"
                    >
                      {responseModeLabel(intentSignal.responseMode)} mode
                    </Badge>
                  </header>
                  <dl>
                    <div>
                      <dt>Intent</dt>
                      <dd>{labelIntent(intentSignal.intent)}</dd>
                    </div>
                    <div>
                      <dt>Classifier</dt>
                      <dd>{labelIntent(intentSignal.classifier)}</dd>
                    </div>
                    <div className="observatory-run-contract-model">
                      <dt>Response model</dt>
                      <dd>
                        {modelDisplayName(
                          intentSignal.modelFamily,
                          intentSignal.modelId,
                        )}
                      </dd>
                      <code title={intentSignal.modelId}>
                        {intentSignal.modelId || 'Server default'}
                      </code>
                    </div>
                    {executionPattern ? (
                      <div>
                        <dt>Path</dt>
                        <dd>
                          {patternLabel(executionPattern)}
                          {executionRoute
                            ? ` / ${labelIntent(executionRoute)}`
                            : ''}
                        </dd>
                      </div>
                    ) : null}
                    {executionRail !== 'Server selected' ? (
                      <div>
                        <dt>Rail</dt>
                        <dd>{executionRail}</dd>
                      </div>
                    ) : null}
                  </dl>
                </section>
              ) : null}

              {!intentSignal && executionPattern ? (
                <section
                  className="observatory-run-contract observatory-run-contract--compact"
                  role="status"
                  aria-label="Execution context"
                >
                  <dl>
                    <div>
                      <dt>Path</dt>
                      <dd>
                        {patternLabel(executionPattern)}
                        {executionRoute
                          ? ` / ${labelIntent(executionRoute)}`
                          : ''}
                      </dd>
                    </div>
                    <div>
                      <dt>Rail</dt>
                      <dd>{executionRail}</dd>
                    </div>
                  </dl>
                </section>
              ) : null}

              {runError ? (
                <div className="observatory-error" role="alert">
                  <strong>{failureTitle(runErrorCode)}</strong>
                  <p>{runError}</p>
                  {runErrorCode === 'authentication_required' ? (
                    <Link to={`/signin?returnTo=${encodeURIComponent(
                      `/observatory/workbench?lab=${selectedLab.id}&step=inspect`,
                    )}`}>
                      Sign in to continue
                    </Link>
                  ) : null}
                  {activeQuery !== null && retryAllowed ? (
                    <button
                      type="button"
                      disabled={ledgerPending}
                      onClick={() => {
                        void runAgent(activeQuery, activeTurn);
                      }}
                    >
                      <RotateCcw size={13} aria-hidden="true" />
                      Retry turn
                    </button>
                  ) : null}
                </div>
              ) : null}

              {steps.length ? (
                <ol
                  ref={traceListRef}
                  className="observatory-trace-list"
                >
                  <motion.li
                    key={`${steps[steps.length - 1]?.id ?? 'trace'}-${Math.round(traceLineHeight)}`}
                    className="observatory-trace-progress"
                    role="presentation"
                    aria-hidden="true"
                    style={{ height: traceLineHeight }}
                    initial={reduceMotion ? false : {
                      clipPath: 'inset(0 0 100% 0)',
                      opacity: 0.8,
                    }}
                    animate={{
                      clipPath: 'inset(0 0 0% 0)',
                      opacity: traceLineHeight > 0 ? 1 : 0,
                    }}
                    transition={{
                      duration: reduceMotion ? 0 : 0.74,
                      ease: [0.16, 1, 0.3, 1],
                    }}
                  />
                  {steps.map((step, index) => (
                    <motion.li
                      key={step.id}
                      ref={(node) => {
                        if (node) stepNodesRef.current.set(step.id, node);
                        else stepNodesRef.current.delete(step.id);
                        if (index === steps.length - 1) {
                          currentTraceStepRef.current = node;
                        }
                      }}
                      className="observatory-trace-step"
                      data-kind={step.kind}
                      data-status={step.status}
                      data-current={
                        step.id === currentStepId ? 'true' : undefined
                      }
                      data-expanded={isReceiptOpen(step) ? 'true' : undefined}
                      data-linked={
                        step.id === linkedStepId ? 'true' : undefined
                      }
                      initial={
                        reduceMotion
                          ? false
                          : { opacity: 0.72, transform: 'translateY(6px)' }
                      }
                      animate={{ opacity: 1, transform: 'translateY(0)' }}
                      transition={{
                        duration: reduceMotion ? 0 : 0.28,
                        ease: [0.16, 1, 0.3, 1],
                      }}
                    >
                      <span className="observatory-trace-index">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="observatory-trace-node" aria-hidden="true">
                        {glyphForStatus(step.status)}
                      </span>
                      <div className="observatory-trace-content">
                        <div className="observatory-trace-kicker">
                          <span>{step.eventKind ?? step.kind}</span>
                          <em>{evidenceStateLabel(step)}</em>
                        </div>
                        <h3 aria-label={step.title}>{step.title}</h3>
                        <p>{step.detail}</p>
                        {step.meta ? <small>{step.meta}</small> : null}
                        {step.action ? (
                          <Link
                            to={step.action.to}
                            className="observatory-trace-action"
                          >
                            {step.action.label}
                            <Link2 size={12} aria-hidden="true" />
                          </Link>
                        ) : null}
                        {step.sql && isReceiptOpen(step) ? (
                          <div className="observatory-proof-block">
                            <div className="observatory-proof-block-heading">
                              <div>
                                <span>
                                  <Database size={14} aria-hidden="true" />
                                  Aurora SQL receipt
                                </span>
                                <strong>{step.title}</strong>
                              </div>
                              <button
                                type="button"
                                className="observatory-copy-sql"
                                title={
                                  copiedSqlId === step.id
                                    ? 'SQL copied'
                                    : 'Copy captured SQL'
                                }
                                aria-label={
                                  copiedSqlId === step.id
                                    ? 'SQL copied'
                                    : 'Copy captured SQL'
                                }
                                onClick={() => {
                                  void copySql(step);
                                }}
                              >
                                {copiedSqlId === step.id ? (
                                  <Check size={14} aria-hidden="true" />
                                ) : (
                                  <Copy size={14} aria-hidden="true" />
                                )}
                              </button>
                            </div>
                            <pre
                              className="observatory-sql"
                              aria-label="Captured SQL"
                            >
                              <code>{formatSqlForDisplay(step.sql)}</code>
                            </pre>
                            <dl className="observatory-proof-receipt">
                              <div>
                                <dt>Source</dt>
                                <dd>
                                  <code>db_queries</code> event
                                </dd>
                              </div>
                              <div>
                                <dt>Duration</dt>
                                <dd>{step.meta ?? 'Not reported'}</dd>
                              </div>
                              <div>
                                <dt>Bindings</dt>
                                <dd>
                                  {sqlBindingCount(step.sql)
                                    ? `${sqlBindingCount(step.sql)} positional`
                                    : 'None'}
                                </dd>
                              </div>
                              <div>
                                <dt>Status</dt>
                                <dd data-status={step.status}>
                                  <CheckCircle2
                                    size={12}
                                    aria-hidden="true"
                                  />
                                  {labelIntent(step.status)}
                                </dd>
                              </div>
                            </dl>
                          </div>
                        ) : null}
                        {step.retrieval && isReceiptOpen(step) ? (
                          <div className="observatory-proof-block">
                            <div className="observatory-proof-block-heading">
                              <div>
                                <span>
                                  <Database size={14} aria-hidden="true" />
                                  Retrieval receipt
                                </span>
                                <strong>{step.title}</strong>
                              </div>
                            </div>
                            <RetrievalReceipt view={step.retrieval} />
                          </div>
                        ) : null}
                        {isReceiptOpen(step) && receiptFields(step).length ? (
                          <dl
                            className="observatory-proof-receipt observatory-receipt-fields"
                            data-testid="observatory-receipt-fields"
                          >
                            {receiptFields(step).map((field) => (
                              <div key={field.key}>
                                <dt>{field.label}</dt>
                                <dd>
                                  <code title={field.value}>{field.value}</code>
                                </dd>
                              </div>
                            ))}
                          </dl>
                        ) : null}
                      </div>
                      {/* The receipt control belongs to the row, not the
                          sentence. Keeping it in its own grid column prevents
                          the hit area from covering a long evidence detail. */}
                      {step.sql || step.retrieval || receiptFields(step).length ? (
                        <button
                          type="button"
                          className="observatory-receipt-toggle"
                          aria-expanded={isReceiptOpen(step)}
                          aria-label={`${isReceiptOpen(step) ? 'Hide' : 'Show'} the Aurora receipt for ${step.title}`}
                          title={`${isReceiptOpen(step) ? 'Hide' : 'Show'} Aurora receipt`}
                          onClick={() => toggleReceipt(step)}
                        >
                          <span
                            className="observatory-receipt-toggle-label"
                            aria-hidden="true"
                          >
                            Receipt
                          </span>
                          <ChevronDown size={14} aria-hidden="true" />
                        </button>
                      ) : null}
                    </motion.li>
                  ))}
                </ol>
              ) : turnSettled ? (
                <p className="observatory-trace-skeleton-note">
                  {ledgerPending
                    ? "Reading this turn's durable ledger."
                    : durableLedger
                      ? 'The recorded ledger contains no events for this turn.'
                      : 'No evidence events were received. The execution outcome is not established by this view.'}
                </p>
              ) : (
                <div className="observatory-trace-skeleton">
                  <p className="observatory-trace-skeleton-note">
                    {runStatus === 'running'
                      ? 'Waiting for the first emitted event.'
                      : 'The seven categories of evidence this turn can emit. A turn does not visit them in order, and does not have to reach all of them.'}
                  </p>
                  <ol
                    className="observatory-trace-list"
                    data-skeleton="true"
                    aria-label="Evidence categories"
                  >
                    {TRACE_SKELETON.map((kind) => (
                      <li
                        key={kind}
                        className="observatory-trace-step"
                        data-kind={kind}
                        data-status="not-run"
                      >
                        <div className="observatory-trace-content">
                          <div className="observatory-trace-kicker">
                            <span>{kind}</span>
                            <em>{runStatus === 'running' ? 'Waiting' : 'Not run'}</em>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>

            <div className="observatory-ledger-footer">
              <dl className="observatory-session-metrics">
                <div>
                  <dt>Elapsed</dt>
                  <dd>
                    {runStatus === 'idle' ? '-' : formatElapsed(elapsedMs)}
                  </dd>
                </div>
                <div>
                  <dt>Steps</dt>
                  <dd>{metricValue(runStatus, steps.length)}</dd>
                </div>
                <div>
                  <dt>Agents</dt>
                  <dd>{metricValue(runStatus, agentCount)}</dd>
                </div>
                <div>
                  <dt>SQL</dt>
                  <dd>{metricValue(runStatus, sqlCount)}</dd>
                </div>
              </dl>

              {/* Counts come from the events actually held in state. The line
                  is absent before a run rather than reading a hopeful zero. */}
              {steps.length ? (
                <p className="observatory-append-only">
                  {durableLedger ? 'Durable receipt projection' : 'Live run timeline'}.
                  {' '}{steps.length} {steps.length === 1 ? 'event' : 'events'},{' '}
                  {receiptStepCount} SQL{' '}
                  {receiptStepCount === 1 ? 'receipt' : 'receipts'}.
                </p>
              ) : null}
            </div>
          </motion.section>

          <motion.section
            className="observatory-results-panel"
            data-motion-panel="results"
            {...focusProps('results')}
            aria-labelledby="live-result-title"
            initial={
              reduceMotion
                ? false
                : {
                    opacity: 0,
                    clipPath: 'inset(0 0 0 100% round 14px)',
                  }
            }
            animate={{ opacity: 1, clipPath: 'inset(0 0 0 0 round 14px)' }}
            transition={{
              duration: reduceMotion ? 0 : 0.46,
              delay: reduceMotion ? 0 : 0.14,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            <div className="observatory-section-heading">
              <div>
                <h2 id="live-result-title">Grounded answer</h2>
                <p>The shopper reply and its supporting evidence.</p>
              </div>
            </div>

            <div className="observatory-panel-scroll observatory-results-scroll">
              <section
                className="observatory-agent-response"
                aria-label={
                  products.length ? 'Recommended result' : 'Shopper answer'
                }
                data-empty={agentResponse ? undefined : 'true'}
              >
                <div className="observatory-agent-response-label">
                  {products.length ? (
                    <Sparkles size={14} aria-hidden="true" />
                  ) : (
                    <Sparkles
                      className="observatory-agent-sparkle"
                      data-testid="shopper-answer-sparkle"
                      size={15}
                      strokeWidth={2.2}
                      aria-hidden="true"
                    />
                  )}
                  {products.length ? 'Recommended result' : 'Shopper answer'}
                </div>
                {agentResponse ? (
                  <div className="observatory-agent-prose">
                    <MarkdownMessage
                      content={agentResponse}
                      streaming={runStatus === 'running'}
                    />
                  </div>
                ) : (
                  <p>
                    {runStatus === 'running'
                      ? 'The answer will appear here as the agent streams.'
                      : runStatus === 'error'
                        ? 'No shopper answer was received before the request stopped.'
                        : runStatus === 'complete'
                          ? 'This turn completed without a shopper answer.'
                      : 'Choose a shopper turn to inspect its answer and evidence.'}
                  </p>
                )}
              </section>

              {bestMatch ? (
                <div className="observatory-catalog-edit">
                  <section aria-labelledby="best-match-title">
                    <div className="observatory-catalog-heading">
                      <div>
                        <h3 id="best-match-title">Best match</h3>
                        <span>First recommendation from this turn</span>
                      </div>
                    </div>
                    <div
                      className="observatory-products"
                      data-layout="feature"
                    >
                      <LabsProductCard
                        product={bestMatch}
                        role="best-match"
                      />
                    </div>
                  </section>

                  {supportingProducts.length ? (
                    <section
                      className="observatory-pairings"
                      aria-labelledby="grounded-results-title"
                    >
                      <div className="observatory-catalog-heading">
                        <div>
                          <h3 id="grounded-results-title">Grounded results</h3>
                          <span>
                            {supportingProducts.length}{' '}
                            {supportingProducts.length === 1
                              ? 'additional product returned by this turn'
                              : 'additional products returned by this turn'}
                          </span>
                        </div>
                      </div>
                      <div
                        className="observatory-products"
                        data-layout="feature"
                      >
                        {supportingProducts.map((product, index) => (
                          <LabsProductCard
                            key={`${product.id || product.name}-${index}`}
                            product={product}
                            role="pairing"
                          />
                        ))}
                      </div>
                    </section>
                  ) : null}

                </div>
              ) : runStatus === 'complete' ? (
                <p
                  className="observatory-products-empty"
                  data-status={runStatus}
                >
                  This turn completed without a product result.
                </p>
              ) : null}

              {turnSettled ? (
              <section
                className="observatory-evidence-sufficiency"
                aria-labelledby="evidence-sufficiency-title"
              >
                <div className="observatory-results-subheading">
                  <h3 id="evidence-sufficiency-title">Evidence sufficiency</h3>
                  <span>{evidenceSufficiency.length || '-'}</span>
                </div>
                {evidenceSufficiency.length ? (
                  <ul>
                    {evidenceSufficiency.map((check) => (
                      <li key={check.id} data-status={check.status}>
                        <span aria-hidden="true" />
                        <div>
                          <strong>{check.label}</strong>
                          <small>{check.detail}</small>
                        </div>
                        <em>{check.status.replace(/_/g, ' ')}</em>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="observatory-results-placeholder">
                    {ledgerPending
                      ? "Reading this turn's durable ledger."
                      : durableLedger
                      ? 'The recorded ledger contains no sufficiency checks for this turn.'
                      : 'Evidence sufficiency is unavailable because no durable ledger was received for this turn.'}
                  </p>
                )}
              </section>
              ) : null}

              {turnSettled ? (
              <section
                className="observatory-verified-claims"
                aria-labelledby="verified-claims-title"
              >
                <div className="observatory-results-subheading">
                  <h3 id="verified-claims-title">Evidence-linked claims</h3>
                  <span>{verifiedClaims.length || '-'}</span>
                </div>
                {verifiedClaims.length ? (
                  <ul>
                    {verifiedClaims.map((claim) => (
                      <li key={claim.id} data-linkable={claim.stepId ? 'true' : undefined}>
                        <CheckCircle2 size={15} aria-hidden="true" />
                        <span>
                          <strong>{claim.title}</strong>
                          <small>{claim.detail}</small>
                        </span>
                        {/* Only a claim with an emitted event behind it gets
                            an open affordance. */}
                        {claim.stepId ? (
                          <button
                            type="button"
                            className="observatory-claim-link"
                            onClick={() => openLinkedStep(claim.stepId as string)}
                          >
                            <Link2 size={13} aria-hidden="true" />
                            Open event
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="observatory-results-placeholder">
                    {ledgerPending
                      ? "Reading this turn's durable ledger."
                      : durableLedger
                      ? 'This turn linked no claim to an emitted event.'
                      : 'Linked claims are unavailable because no durable ledger was received for this turn.'}
                  </p>
                )}
                {linkedClaimCount ? (
                  <p className="observatory-claims-linked">
                    <Link2 size={12} aria-hidden="true" />
                    {linkedClaimCount} of {verifiedClaims.length} linked to a
                    ledger event
                  </p>
                ) : null}
                {!durableLedger && verifiedClaims.length > 0 ? (
                  <p className="observatory-results-placeholder">
                    These links use live events only. No durable ledger was
                    received to verify this turn.
                  </p>
                ) : null}
              </section>
              ) : null}

              {rationale.length ? (
                <section
                  className="observatory-rationale"
                  aria-labelledby="why-this-answer-title"
                >
                  <div className="observatory-results-subheading">
                    <h3 id="why-this-answer-title">Why this answer</h3>
                  </div>
                  <ul>
                    {rationale.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                  {/* Naming the source keeps this from reading as the model's
                      account of its own reasoning, which the runtime does not
                      expose. */}
                  <p className="observatory-rationale-source">
                    Assembled from this turn's emitted events.
                  </p>
                </section>
              ) : null}
            </div>
          </motion.section>
          </> : null}
        </div>
        {(!storefrontJourney || (runStatus === 'complete' && turnEntries.slice(0, 3).filter(Boolean).length === 3)) && <LabHandoff exercise={selectedLab} />}
        <WorkbenchResources compact collapsible defaultExpanded={false} labId={selectedLab.id} />
      </div>
    </div>
  );
}
