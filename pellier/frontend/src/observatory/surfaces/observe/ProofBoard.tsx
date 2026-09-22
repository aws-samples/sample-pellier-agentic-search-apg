import { apiFetch, apiUrl } from '../../../services/apiBase'
/**
 * ProofBoard - system evidence surface.
 *
 * One route that maps the hands-on flow to concrete evidence:
 * readiness checks, evidence cards, and terminal fallbacks.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  ArrowLeft,
  Cpu,
  Database,
  ExternalLink,
  KeyRound,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { EditorialTitle, Eyebrow } from '../../components';
import {
  EvidenceCard,
  PolicyDecisionBadge,
  SectionEyebrow,
  StateBadge,
  type EvidenceCardTone,
  type PolicyDecision,
  type StateBadgeTone,
} from '../../../shared';

/* The tones a card and a badge can both wear. Provenance tones say where a
   number came from and are not states of a checkpoint, so they are excluded
   here rather than handled at each call site. */
type ProofTone = Extract<StateBadgeTone, EvidenceCardTone>;

type CheckState = 'pass' | 'warn' | 'fail';
type CardStatus = 'complete' | 'needs_build' | 'needs_run' | 'needs_data' | 'needs_config' | 'pending' | 'available';
type TraceStepState = 'pass' | 'warn' | 'pending';

interface ReadinessCheck {
  id: string;
  label: string;
  state: CheckState;
  detail: string;
  required: boolean;
  href?: string;
}

interface ManagedReceipt {
  present: boolean;
  traceKind: string;
  runtime: string;
  rail: string;
  jwtPassthrough: boolean;
  gatewayPassthrough: boolean;
  traceId?: string | null;
  runtimeRequestId?: string | null;
  sessionId?: string | null;
  evidenceProvenance?: string;
  /** Content digest of the sources packaged into the deployed runtime. */
  buildFingerprint?: string;
  /** The same digest computed over this checkout, for comparison. */
  localBuildFingerprint?: string;
  /**
   * 'current' when the deployed package was built from this checkout,
   * 'stale' when it was not, 'unknown' when the runtime reported no
   * fingerprint. Unknown is not a soft stale: a runtime deployed before the
   * mechanism existed cannot report one, and absence of evidence is not
   * evidence of stale code.
   */
  buildState?: 'current' | 'stale' | 'unknown';
  managedTrace?: {
    traceId?: string | null;
    runtimeRequestId?: string | null;
    sessionId?: string | null;
    xrayConsoleUrl?: string | null;
    logsConsoleUrl?: string | null;
    logsInsightsQuery?: string;
  };
  policyConfigured?: boolean;
  gatewayAuditPresent?: boolean;
  gatewayAuditAbsenceVerified?: boolean;
  latestGatewayAuditId?: number | null;
  latestGatewayAuditAt?: string;
  governedReceiptPresent?: boolean;
  latestGovernedReceiptId?: number | null;
  latestGovernedReceiptAt?: string;
  governedAuditId?: number | null;
  governedPrincipalId?: string;
  governedPrincipalLabel?: string;
  governedVerifiedSubject?: string;
  governedVerifiedUsername?: string;
  governedIdentitySource?: string;
  governedTokenFingerprint?: string;
  governedDecision?: string;
  governedTool?: string;
  governedPolicyName?: string;
  governedArgs?: Record<string, unknown>;
  writeOperationPresent?: boolean;
  writeOperationKey?: string;
  writeOperationName?: string;
  writeOperationCompletedAt?: string | null;
  absenceCheckDetail?: string;
}

interface ProofCard {
  id: string;
  lab?: string;
  group?: string;
  title: string;
  status: CardStatus;
  required: boolean;
  surface: string;
  summary: string;
  evidenceSource?: string;
  lastUpdated?: string | null;
  evidence: string[];
  fallback: {
    label: string;
    command: string;
  };
  links: Array<{ label: string; to: string }>;
}

interface ProofBoardPayload {
  status: 'ready' | 'attention' | 'not_ready';
  readiness: {
    status: 'ready' | 'attention' | 'not_ready';
    checks: ReadinessCheck[];
  };
  managedReceipt: ManagedReceipt;
  cards: ProofCard[];
}

interface ProofBoardProps {
  focusCardId?: string;
}

class ProofBoardApiError extends Error {
  constructor(
    readonly status: number,
    readonly code?: string,
  ) {
    super(`HTTP ${status}`);
  }
}

interface PersistedTurnReceipt {
  turn_id: string;
  rail: string;
  citations?: Array<{
    evidence_id: string;
    source_uri: string;
    revision: string | null;
    quote: string;
    entity_id: string;
  }>;
  tool_audit_ids?: Array<{
    audit_id: number;
    tool: string;
    caller: string;
    latency_ms: number | null;
  }>;
  policy_events?: Array<{
    decision: PolicyDecision;
    reason?: string | null;
  }>;
  terminal_status: string;
  latency_ms: number | null;
}

interface GovernanceReceipt {
  id: 'policy' | 'execution' | 'data';
  label: string;
  question: string;
  detail: string;
  evidence: string;
  state: TraceStepState;
}

const STATUS_LABEL: Record<CardStatus, string> = {
  complete: 'Observed',
  needs_build: 'Build',
  needs_run: 'Run',
  needs_data: 'Data',
  needs_config: 'Config',
  pending: 'Pending',
  available: 'Available',
};

// Status roles come from base.css (--obs-status-*), resolved by the shared
// StateBadge. The brand burgundy is not among them on purpose: a chip that
// borrows the accent reads as a button.
const STATUS_TONE: Record<CardStatus, ProofTone> = {
  complete: 'ok',
  needs_build: 'attention',
  needs_run: 'attention',
  needs_data: 'degraded',
  needs_config: 'degraded',
  pending: 'neutral',
  available: 'neutral',
};

const CHECK_TONE: Record<CheckState, { label: string; tone: ProofTone }> = {
  pass: { label: 'Pass', tone: 'ok' },
  warn: { label: 'Warn', tone: 'degraded' },
  fail: { label: 'Fix', tone: 'attention' },
};

/* Seen / Gap / Pending, as a badge tone and a card tone. The three states used
   to fill the whole card with their tint, so a board with one gap in it read
   as three differently coloured surfaces; the state now lives in the badge and
   in the card's top tick, and the paper stays one colour. */
const TRACE_TONE: Record<TraceStepState, { label: string; card: ProofTone }> = {
  pass: { label: 'Seen', card: 'ok' },
  warn: { label: 'Gap', card: 'degraded' },
  pending: { label: 'Pending', card: 'neutral' },
};

// Four-lab workshop spine.
const LAB_BY_CARD_ID: Record<string, string> = {
  'marco-floor-check': 'Lab 1: Build a PostgreSQL-Grounded Agent',
  'retrieval-comparison': 'Lab 2: Build and Measure PostgreSQL Hybrid Retrieval',
  'managed-rail': 'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore',
  'audit-ledger': 'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore',
  'runtime-gateway-policy': 'Lab 4: Build Governed Agent Actions with Cedar',
};

interface GovernedProofStage {
  id: 'ground' | 'retrieval' | 'managed' | 'governed';
  number: string;
  title: string;
  question: string;
  description: string;
  cardIds: string[];
  icon: LucideIcon;
}

const GOVERNED_PROOF_STAGES: GovernedProofStage[] = [
  {
    id: 'ground',
    number: '01',
    title: 'Ground answers',
    question: 'Can Pellier answer from a verified operational fact?',
    description: 'Start with the Aurora-backed tool result that makes the answer inspectable.',
    cardIds: ['marco-floor-check'],
    icon: Database,
  },
  {
    id: 'retrieval',
    number: '02',
    title: 'Retrieval',
    question: 'Can the answer show why these records were selected?',
    description: 'Inspect the retrieval comparison before any model explanation is accepted.',
    cardIds: ['retrieval-comparison'],
    icon: Search,
  },
  {
    id: 'managed',
    number: '03',
    title: 'Runtime & memory',
    question: 'Can managed execution and state be correlated to a receipt?',
    description: 'The managed Runtime boundary carries the session and trace evidence forward.',
    cardIds: ['managed-rail', 'audit-ledger'],
    icon: Cpu,
  },
  {
    id: 'governed',
    number: '04',
    title: 'Policy & receipt',
    question: 'Was the action allowed, stopped, or recorded with evidence?',
    description: 'Finish at the Gateway, Cedar decision, and linked Aurora audit evidence.',
    cardIds: ['runtime-gateway-policy'],
    icon: ShieldCheck,
  },
];

function cardLab(card: ProofCard): string {
  return LAB_BY_CARD_ID[card.id] ?? card.lab ?? 'Lab checkpoint';
}

const CODE_STYLE: React.CSSProperties = {
  margin: 0,
  padding: '12px 14px',
  borderRadius: 'var(--gov-radius-md)',
  background: 'var(--dl-ink)',
  color: 'var(--dl-accent-soft)',
  border: '1px solid color-mix(in srgb, var(--dl-accent-soft) 18%, transparent)',
  fontFamily: 'var(--obs-mono)',
  fontSize: '12px',
  lineHeight: 1.55,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

function formatTimestamp(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

function statusPill(status: CardStatus) {
  // No glyph here, unlike CheckPill. Seven checkpoint statuses share four
  // tones -- Build and Run are both `attention`, Data and Config both
  // `degraded` -- so a glyph would repeat rather than distinguish, and this
  // badge sits inside a tab and a card head where width is scarce. CheckPill
  // has one glyph per state, so there it earns its place.
  return (
    <StateBadge tone={STATUS_TONE[status]} icon={false}>
      {STATUS_LABEL[status]}
    </StateBadge>
  );
}

function stageReceiptDetail(
  stage: GovernedProofStage,
  card: ProofCard | undefined,
  receipt: ManagedReceipt,
) {
  if (stage.id === 'managed' && receipt.present) {
    const memoryEvidence = card?.evidence.find((item) => /memory/i.test(item));
    const detail = [
      memoryEvidence,
      receipt.runtime || 'Managed Runtime',
      receipt.rail || 'managed rail',
      receipt.sessionId ? `session ${receipt.sessionId}` : undefined,
      receipt.traceId || receipt.managedTrace?.traceId,
    ].filter(Boolean).join(' · ');
    return {
      label: memoryEvidence ? 'Memory and managed receipt' : 'Managed receipt',
      detail,
    };
  }

  if (stage.id === 'governed' && receipt.governedReceiptPresent) {
    const detail = [
      receipt.governedDecision,
      receipt.governedPolicyName,
      receipt.gatewayAuditPresent
        ? `tool_audit ${receipt.latestGatewayAuditId ?? 'recorded'}`
        : receipt.gatewayAuditAbsenceVerified
          ? 'no execution row after DENY'
          : undefined,
    ].filter(Boolean).join(' · ');
    return {
      label: 'Governed receipt',
      detail,
    };
  }

  if (card) {
    return {
      label: card.evidenceSource ? 'Evidence source' : 'Latest checkpoint',
      detail: card.evidenceSource ?? card.evidence[0] ?? card.summary,
    };
  }

  return {
    label: 'Evidence unavailable',
    detail: 'This Proof Board response does not include the checkpoint required for this stage.',
  };
}

const GovernedProofRail: React.FC<{ cards: ProofCard[]; receipt: ManagedReceipt }> = ({
  cards,
  receipt,
}) => {
  const [activeStageId, setActiveStageId] = useState<GovernedProofStage['id']>('ground');
  const selectStage = (index: number) => {
    const stage = GOVERNED_PROOF_STAGES[index];
    if (!stage) return;
    setActiveStageId(stage.id);
    requestAnimationFrame(() => {
      document.getElementById(`governed-proof-tab-${stage.id}`)?.focus();
    });
  };
  const activeStage = GOVERNED_PROOF_STAGES.find((stage) => stage.id === activeStageId)
    ?? GOVERNED_PROOF_STAGES[0];
  const activeCard = activeStage.cardIds
    .map((cardId) => cards.find((card) => card.id === cardId))
    .find((card): card is ProofCard => Boolean(card));
  const evidence = stageReceiptDetail(activeStage, activeCard, receipt);

  return (
    <section
      aria-label="Governed proof journey"
      className="pellier-governed-proof-rail"
      data-testid="governed-proof-rail"
    >
      <div
        aria-label="Governed proof stages"
        className="pellier-governed-proof-tabs"
        role="tablist"
      >
        {GOVERNED_PROOF_STAGES.map((stage, index) => {
          const isActive = stage.id === activeStage.id;
          const stageCard = stage.cardIds
            .map((cardId) => cards.find((card) => card.id === cardId))
            .find((card): card is ProofCard => Boolean(card));
          const StageIcon = stage.icon;
          return (
            <button
              aria-controls={`governed-proof-panel-${stage.id}`}
              aria-selected={isActive}
              className="pellier-governed-proof-tab"
              data-active={isActive ? 'true' : 'false'}
              data-testid={`governed-proof-stage-${stage.id}`}
              id={`governed-proof-tab-${stage.id}`}
              key={stage.id}
              onClick={() => setActiveStageId(stage.id)}
              onKeyDown={(event) => {
                const lastIndex = GOVERNED_PROOF_STAGES.length - 1;
                if (event.key === 'ArrowRight') {
                  event.preventDefault();
                  selectStage(index === lastIndex ? 0 : index + 1);
                } else if (event.key === 'ArrowLeft') {
                  event.preventDefault();
                  selectStage(index === 0 ? lastIndex : index - 1);
                } else if (event.key === 'Home') {
                  event.preventDefault();
                  selectStage(0);
                } else if (event.key === 'End') {
                  event.preventDefault();
                  selectStage(lastIndex);
                }
              }}
              role="tab"
              tabIndex={isActive ? 0 : -1}
              type="button"
            >
              <span className="pellier-governed-proof-tab-icon" aria-hidden="true">
                <StageIcon size={17} strokeWidth={1.7} />
              </span>
              <span className="pellier-governed-proof-tab-copy">
                <span>{stage.number}</span>
                <strong>{stage.title}</strong>
              </span>
              <small>
                {stageCard ? (
                  statusPill(stageCard.status)
                ) : (
                  <StateBadge tone="neutral" icon={false}>
                    Unavailable
                  </StateBadge>
                )}
              </small>
            </button>
          );
        })}
      </div>

      <div
        aria-labelledby={`governed-proof-tab-${activeStage.id}`}
        className="pellier-governed-proof-panel"
        id={`governed-proof-panel-${activeStage.id}`}
        role="tabpanel"
      >
        <div className="pellier-governed-proof-question">
          <div className="pellier-governed-proof-stage-label">
            <span>{activeStage.number}</span>
            <SectionEyebrow tone="muted" dot={false}>
              {activeStage.title}
            </SectionEyebrow>
          </div>
          <h2 className="font-display">{activeStage.question}</h2>
          <p>{activeStage.description}</p>
        </div>
        <div className="pellier-governed-proof-evidence">
          <div className="pellier-governed-proof-evidence-label">
            <SectionEyebrow dot={false}>{evidence.label}</SectionEyebrow>
            {activeCard ? statusPill(activeCard.status) : null}
          </div>
          <p className="font-mono">{evidence.detail}</p>
          {activeCard ? (
            <a href={`#${activeCard.id}`}>
              Open checkpoint
            </a>
          ) : (
            <p className="pellier-governed-proof-unavailable" role="status">
              Run that lab or update the governed backend before using this stage as proof.
            </p>
          )}
        </div>
      </div>
    </section>
  );
};

const CheckPill: React.FC<{ state: CheckState }> = ({ state }) => (
  <StateBadge tone={CHECK_TONE[state].tone}>{CHECK_TONE[state].label}</StateBadge>
);

const ReadinessPanel: React.FC<{ checks: ReadinessCheck[] }> = ({ checks }) => {
  return (
    <section aria-label="Environment readiness" style={{ marginBottom: '32px' }}>
      <div
        className="proof-board-section-heading"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          marginBottom: '14px',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 'inherit', lineHeight: 1 }}>
          <Eyebrow label="Readiness" />
        </h2>
        <SectionEyebrow tone="muted" dot={false}>
          Read only
        </SectionEyebrow>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '12px',
        }}
      >
        {checks.map((check) => (
          <EvidenceCard
            key={check.id}
            padding="compact"
            style={{
              minHeight: '126px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                flexWrap: 'wrap',
              }}
            >
              <CheckPill state={check.state} />
              <SectionEyebrow tone="muted" dot={false}>
                {check.required ? 'Baseline' : 'Managed'}
              </SectionEyebrow>
            </div>
            <h3
              style={{
                margin: 0,
                color: 'var(--obs-ink-1)',
                fontFamily: 'var(--obs-heading)',
                fontSize: '20px',
                fontWeight: 600,
              }}
            >
              {check.label}
            </h3>
            <p
              style={{
                margin: 0,
                color: 'var(--obs-ink-2)',
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                lineHeight: 1.5,
              }}
            >
              {check.detail}
            </p>
          </EvidenceCard>
        ))}
      </div>
    </section>
  );
};

const TraceStep: React.FC<{ label: string; detail: string; state: TraceStepState }> = ({
  label,
  detail,
  state,
}) => {
  const tone = TRACE_TONE[state];
  return (
    <EvidenceCard
      tone={tone.card}
      padding="compact"
      style={{
        minHeight: '96px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      <div style={{ marginBottom: '10px' }}>
        <StateBadge tone={tone.card}>{tone.label}</StateBadge>
      </div>
      <div
        style={{
          color: 'var(--obs-ink-1)',
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          fontWeight: 600,
          lineHeight: 1.25,
          marginBottom: '6px',
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: 'var(--obs-ink-2)',
          fontFamily: 'var(--obs-sans)',
          fontSize: '12px',
          lineHeight: 1.35,
        }}
      >
        {detail}
      </div>
    </EvidenceCard>
  );
};

const GovernanceReceiptCard: React.FC<React.PropsWithChildren<{ receipt: GovernanceReceipt }>> = ({
  receipt,
  children,
}) => {
  const tone = TRACE_TONE[receipt.state];
  return (
    <EvidenceCard
      as="article"
      tone={tone.card}
      padding="compact"
      data-testid={`governance-receipt-${receipt.id}`}
      style={{
        minHeight: '218px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          marginBottom: '18px',
        }}
      >
        <SectionEyebrow dot={false}>{receipt.label}</SectionEyebrow>
        <StateBadge tone={tone.card}>{tone.label}</StateBadge>
      </div>
      <h3
        style={{
          margin: '0 0 12px',
          color: 'var(--obs-ink-1)',
          fontFamily: 'var(--obs-heading)',
          fontSize: '20px',
          fontWeight: 600,
          lineHeight: 1.2,
        }}
      >
        {receipt.question}
      </h3>
      <p
        style={{
          margin: '0 0 14px',
          color: 'var(--obs-ink-2)',
          fontFamily: 'var(--obs-sans)',
          fontSize: '13px',
          lineHeight: 1.5,
        }}
      >
        {receipt.detail}
      </p>
      <p
        className="font-mono"
        style={{
          margin: 'auto 0 0',
          color: 'var(--obs-ink-3)',
          fontSize: '11px',
          lineHeight: 1.45,
          overflowWrap: 'anywhere',
        }}
      >
        {receipt.evidence}
      </p>
      {children}
    </EvidenceCard>
  );
};

const ManagedTraceCorrelation: React.FC<{ receipt: ManagedReceipt }> = ({ receipt }) => {
  const trace = receipt.managedTrace || {};
  const traceId = receipt.traceId || trace.traceId;
  const requestId = receipt.runtimeRequestId || trace.runtimeRequestId;
  const sessionId = receipt.sessionId || trace.sessionId;
  const rows = [
    ['Trace', traceId],
    ['Runtime request', requestId],
    ['Session', sessionId],
    ['Evidence from', receipt.evidenceProvenance],
  ].filter((row): row is [string, string] => Boolean(row[1]));
  const buildState = receipt.buildState ?? 'unknown';
  const deployedBuild = (receipt.buildFingerprint || '').slice(0, 12);
  const localBuild = (receipt.localBuildFingerprint || '').slice(0, 12);
  // Which revision answered. Rendered as its own row rather than folded into
  // the list above because it is the one line that answers "did Runtime run
  // the code I just packaged?" -- and because a stale build has to read as a
  // finding, not as another correlation id.
  //
  // Both digests are printed in every state, including a match. "This checkout"
  // is a conclusion; the two hashes are the reading it was drawn from, and a
  // participant who cannot see them has to take the badge on trust.
  const buildTone: { tone: ProofTone; label: string } =
    buildState === 'current'
      ? { tone: 'ok', label: 'This checkout' }
      : buildState === 'stale'
        ? { tone: 'attention', label: 'Older deployment' }
        : { tone: 'neutral', label: 'Not reported' };

  return (
    <div
      data-testid="managed-trace-correlation"
      style={{
        borderTop: '1px solid var(--obs-card-border)',
        marginTop: '16px',
        paddingTop: '14px',
      }}
    >
      <div style={{ marginBottom: '10px' }}>
        <SectionEyebrow tone="muted" dot={false}>
          Managed trace correlation
        </SectionEyebrow>
      </div>
      <div
        data-testid="managed-build-fingerprint"
        data-build-state={buildState}
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '8px',
          marginBottom: '10px',
          paddingBottom: '10px',
          borderBottom: '1px solid var(--obs-rule-1)',
        }}
      >
        <span style={{ color: 'var(--obs-ink-3)', fontSize: '11px' }}>
          Executed revision
        </span>
        <StateBadge tone={buildTone.tone}>{buildTone.label}</StateBadge>
        <span
          className="font-mono"
          style={{ color: 'var(--obs-ink-2)', fontSize: '11px', overflowWrap: 'anywhere' }}
        >
          {buildState === 'unknown'
            ? localBuild
              ? `executed not reported · expected ${localBuild}`
              : 'Runtime reported no build fingerprint'
            : `executed ${deployedBuild} · expected ${localBuild}`}
        </span>
      </div>
      {rows.length > 0 ? (
        rows.map(([label, value]) => (
          <div
            key={label}
            style={{
              display: 'grid',
              gridTemplateColumns: '88px minmax(0, 1fr)',
              gap: '8px',
              marginTop: '5px',
            }}
          >
            <span style={{ color: 'var(--obs-ink-3)', fontSize: '11px' }}>{label}</span>
            <span
              className="font-mono"
              style={{
                color: 'var(--obs-ink-2)',
                fontSize: '11px',
                overflowWrap: 'anywhere',
              }}
            >
              {value}
            </span>
          </div>
        ))
      ) : (
        <p style={{ color: 'var(--obs-ink-3)', fontSize: '11px', margin: 0 }}>
          Correlation IDs were not reported on the latest Runtime response.
        </p>
      )}
      {(trace.xrayConsoleUrl || trace.logsConsoleUrl) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '12px' }}>
          {trace.xrayConsoleUrl && (
            <a
              href={trace.xrayConsoleUrl}
              target="_blank"
              rel="noreferrer"
              className="proof-board-trace-link"
              style={{ alignItems: 'center', color: 'var(--obs-red-1)', display: 'inline-flex', fontSize: '11px', gap: '4px' }}
            >
              Trace in CloudWatch <ExternalLink size={12} aria-hidden="true" />
            </a>
          )}
          {trace.logsConsoleUrl && (
            <a
              href={trace.logsConsoleUrl}
              target="_blank"
              rel="noreferrer"
              className="proof-board-trace-link"
              style={{ alignItems: 'center', color: 'var(--obs-red-1)', display: 'inline-flex', fontSize: '11px', gap: '4px' }}
            >
              Runtime logs <ExternalLink size={12} aria-hidden="true" />
            </a>
          )}
        </div>
      )}
    </div>
  );
};

const ReceiptStrip: React.FC<{ receipt: ManagedReceipt }> = ({ receipt }) => {
  const gatewayAuditAt = formatTimestamp(receipt.latestGatewayAuditAt);
  const governedAt = formatTimestamp(receipt.latestGovernedReceiptAt);
  const customerId = typeof receipt.governedArgs?.customer_id === 'string'
    ? receipt.governedArgs.customer_id
    : '';
  const isDeny = receipt.governedDecision === 'DENY';
  const absenceVerified = Boolean(receipt.gatewayAuditAbsenceVerified);
  const writeOperationCompleted = Boolean(
    receipt.writeOperationPresent && receipt.writeOperationCompletedAt,
  );
  const receiptSeen = Boolean(receipt.present || receipt.governedReceiptPresent);
  const tokenFingerprint = receipt.governedTokenFingerprint
    ? `${receipt.governedTokenFingerprint.slice(0, 12)}...`
    : '';
  const traceSteps: Array<{ label: string; detail: string; state: TraceStepState }> = [
    {
      label: 'Verified identity',
      detail: receipt.governedVerifiedUsername
        ? `${receipt.governedVerifiedUsername} via ${receipt.governedIdentitySource || 'Cognito JWT'}`
        : receipt.governedPrincipalLabel
          ? receipt.governedPrincipalLabel
          : receipt.jwtPassthrough
            ? 'Caller JWT forwarded'
            : 'Signed-in JWT not observed',
      state: receipt.governedReceiptPresent || receipt.jwtPassthrough ? 'pass' : 'pending',
    },
    {
      label: 'JWT binding',
      detail: tokenFingerprint && receipt.governedVerifiedSubject
        ? `sha256 ${tokenFingerprint} · subject ${receipt.governedVerifiedSubject}`
        : 'No verified token fingerprint on receipt',
      state: tokenFingerprint && receipt.governedVerifiedSubject
        ? 'pass'
        : receipt.governedReceiptPresent ? 'warn' : 'pending',
    },
    {
      label: 'Runtime',
      detail: receipt.present ? receipt.runtime || 'Managed receipt present' : 'No managed receipt',
      state: receipt.present ? 'pass' : 'pending',
    },
    {
      label: 'Gateway',
      detail: receipt.gatewayPassthrough ? receipt.rail || 'Gateway MCP rail' : 'Gateway hop not observed',
      state: receipt.gatewayPassthrough ? 'pass' : 'pending',
    },
    {
      label: 'Cedar decision',
      detail: receipt.governedDecision
        ? `${receipt.governedDecision}${receipt.governedPolicyName ? ` via ${receipt.governedPolicyName}` : ''}${governedAt ? ` at ${governedAt}` : ''}`
        : receipt.policyConfigured ? 'Policy engine configured' : 'Policy engine id missing',
      state: receipt.governedReceiptPresent
        ? 'pass'
        : receipt.policyConfigured ? (receipt.present ? 'pass' : 'pending') : 'warn',
    },
    {
      label: 'Tool result',
      detail: receipt.gatewayAuditPresent
        ? `${receipt.governedTool || 'Gateway tool'} audit ${receipt.latestGatewayAuditId}`
        : isDeny && absenceVerified
          ? 'Cedar DENY: tool target did not execute'
          : isDeny
            ? receipt.absenceCheckDetail || 'DENY receipt present; absence not verified'
            : 'No Gateway ALLOW row',
      state: receipt.gatewayAuditPresent || (isDeny && absenceVerified)
        ? 'pass'
        : receiptSeen ? 'warn' : 'pending',
    },
    {
      label: 'Aurora audit',
      detail: gatewayAuditAt
        ? `tool_audit at ${gatewayAuditAt}${customerId ? ` for ${customerId}` : ''}`
        : absenceVerified
          ? 'Gateway/Cedar DENY left no tool_audit row'
          : 'No Gateway audit row for this receipt',
      state: receipt.gatewayAuditPresent || absenceVerified ? 'pass' : receiptSeen ? 'warn' : 'pending',
    },
  ];
  const governanceReceipts: GovernanceReceipt[] = [
    {
      id: 'policy',
      label: 'Policy receipt',
      question: 'Was the action permitted?',
      detail: receipt.governedDecision
        ? `${receipt.governedDecision}${receipt.governedPolicyName ? ` via ${receipt.governedPolicyName}` : ''}${governedAt ? ` at ${governedAt}` : ''}`
        : receipt.policyConfigured
          ? 'Policy is configured; run the governed turn to capture a decision.'
          : 'No policy decision is available yet.',
      evidence: receipt.governedVerifiedUsername
        ? `${receipt.governedVerifiedUsername} via ${receipt.governedIdentitySource || 'Cognito JWT'}`
        : receipt.governedPrincipalLabel || 'No verified principal on the latest receipt',
      state: receipt.governedReceiptPresent
        ? 'pass'
        : receipt.policyConfigured ? 'warn' : 'pending',
    },
    {
      id: 'execution',
      label: 'Execution receipt',
      question: 'What actually ran?',
      detail: isDeny && receipt.governedReceiptPresent
        ? `${receipt.governedTool || 'The governed tool'} was stopped before target execution.`
        : receipt.gatewayAuditPresent
          ? `${receipt.governedTool || 'The governed tool'} ran through ${receipt.rail || 'the Gateway MCP rail'}.`
          : receipt.present
            ? `${receipt.runtime || 'AgentCore Runtime'} returned on ${receipt.rail || 'the managed rail'}; tool evidence is pending.`
            : 'No managed Runtime execution receipt is available yet.',
      evidence: receipt.present
        ? `${receipt.runtime || 'AgentCore Runtime'} · ${receipt.rail || 'managed rail'}`
        : 'Runtime and Gateway correlation not observed',
      state: receipt.gatewayAuditPresent || (isDeny && receipt.governedReceiptPresent)
        ? 'pass'
        : receipt.present ? 'warn' : 'pending',
    },
    {
      id: 'data',
      label: 'Data receipt',
      question: 'What reached the system of record?',
      detail: writeOperationCompleted
        ? `Aurora recorded ${receipt.writeOperationName || 'the governed write'} as complete in pellier.write_operations.`
        : receipt.writeOperationPresent
          ? 'Aurora contains the idempotency claim, but completion is not proven.'
        : absenceVerified
          ? 'No system-of-record write was attempted because Cedar denied the action before target execution.'
          : receipt.gatewayAuditPresent
            ? 'Tool execution is visible, but no idempotent write ledger row is linked.'
            : 'No linked system-of-record write or verified DENY absence is available yet.',
      evidence: receipt.writeOperationPresent
        ? `write_operations.idempotency_key=${receipt.writeOperationKey || 'unknown'}`
        : absenceVerified
          ? 'governed receipt present · target execution absent'
          : 'System-of-record evidence pending',
      state: writeOperationCompleted || absenceVerified
        ? 'pass'
        : receiptSeen ? 'warn' : 'pending',
    },
  ];

  return (
    <section
      aria-label="Three governance receipts"
      style={{
        marginBottom: '30px',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: '14px',
          flexWrap: 'wrap',
          marginBottom: '14px',
        }}
      >
        <div>
          <Eyebrow label="Three receipts" />
          <h2
            className="font-display"
            style={{
              margin: '7px 0 0',
              color: 'var(--obs-ink-1)',
              fontSize: 'var(--text-sub)',
              fontWeight: 400,
              lineHeight: 1.15,
              letterSpacing: 'var(--tracking-display)',
            }}
          >
            Reconstruct one governed action.
          </h2>
        </div>
        <SectionEyebrow tone="muted" dot={false}>
          {receipt.present ? receipt.traceKind || 'managed receipt' : 'after SQL proof'}
        </SectionEyebrow>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '14px',
        }}
      >
        {governanceReceipts.map((item) => (
          <GovernanceReceiptCard key={item.id} receipt={item}>
            {item.id === 'execution' ? <ManagedTraceCorrelation receipt={receipt} /> : null}
          </GovernanceReceiptCard>
        ))}
      </div>
      <details style={{ marginTop: '16px' }}>
        <summary
          style={{
            cursor: 'pointer',
            color: 'var(--obs-red-1)',
            fontFamily: 'var(--obs-heading)',
            fontSize: '13px',
            fontWeight: 600,
          }}
        >
          Inspect end-to-end correlation
        </summary>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '10px',
            marginTop: '12px',
          }}
        >
          {traceSteps.map((step) => (
            <TraceStep key={step.label} {...step} />
          ))}
        </div>
      </details>
      <p
        style={{
          margin: '12px 0 0',
          color: 'var(--obs-ink-3)',
          fontFamily: 'var(--obs-sans)',
          fontSize: '12px',
          lineHeight: 1.5,
        }}
      >
        No-row DENY is scoped to the Gateway/Cedar rail. In-process tool calls can still write audit rows
        because they execute before local return handling completes.
      </p>
    </section>
  );
};

const ProofCardView: React.FC<{
  card: ProofCard;
  highlighted?: boolean;
  /** h3 under a rail heading; h2 when the card is the page's only section. */
  titleAs?: 'h2' | 'h3';
}> = ({
  card,
  highlighted = false,
  titleAs: TitleTag = 'h3',
}) => {
  const lastUpdated = formatTimestamp(card.lastUpdated);
  return (
  <EvidenceCard
    as="article"
    id={card.id}
    data-testid={`proof-card-${card.id}`}
    style={{
      scrollMarginTop: '80px',
      /* The highlighted card is the one a deep link landed on. It keeps the
         card's own paper and gains a burgundy edge plus a ring, so "you are
         here" is an outline rather than a different surface. */
      ...(highlighted
        ? {
            borderColor: 'var(--obs-red-1)',
            boxShadow:
              '0 0 0 3px color-mix(in srgb, var(--obs-red-1) 14%, transparent), var(--gov-shadow-card)',
          }
        : null),
    }}
  >
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        flexWrap: 'wrap',
        marginBottom: '12px',
      }}
    >
      <SectionEyebrow dot={false}>{cardLab(card)}</SectionEyebrow>
      {statusPill(card.status)}
      <SectionEyebrow tone="muted" dot={false}>
        {card.required ? 'Baseline evidence' : 'Extension evidence'}
      </SectionEyebrow>
    </div>
    <TitleTag
      style={{
        margin: '0 0 6px',
        color: 'var(--obs-ink-1)',
        fontFamily: 'var(--obs-heading)',
        fontSize: '26px',
        lineHeight: 1.15,
        fontWeight: 600,
      }}
    >
      {card.title}
    </TitleTag>
    <p style={{ margin: '0 0 12px' }}>
      <SectionEyebrow tone="muted" dot={false}>
        {card.surface}
      </SectionEyebrow>
    </p>
    <p
      style={{
        margin: '0 0 16px',
        color: 'var(--obs-ink-2)',
        fontFamily: 'var(--obs-sans)',
        fontSize: '14px',
        lineHeight: 1.55,
      }}
    >
      {card.summary}
    </p>
    {(card.evidenceSource || lastUpdated) && (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: '8px',
          margin: '0 0 14px',
        }}
      >
        {card.evidenceSource && (
          <div>
            <div style={{ marginBottom: '5px' }}>
              <SectionEyebrow tone="muted" dot={false}>
                Evidence source
              </SectionEyebrow>
            </div>
            <div
              style={{
                color: 'var(--obs-ink-2)',
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                lineHeight: 1.45,
                wordBreak: 'break-word',
              }}
            >
              {card.evidenceSource}
            </div>
          </div>
        )}
        {lastUpdated && (
          <div>
            <div style={{ marginBottom: '5px' }}>
              <SectionEyebrow tone="muted" dot={false}>
                Last updated
              </SectionEyebrow>
            </div>
            <div
              style={{
                color: 'var(--obs-ink-2)',
                fontFamily: 'var(--obs-mono)',
                fontSize: '11px',
                lineHeight: 1.45,
              }}
            >
              {lastUpdated}
            </div>
          </div>
        )}
      </div>
    )}
    <ul
      style={{
        margin: '0 0 16px',
        paddingLeft: '18px',
        color: 'var(--obs-ink-2)',
        fontFamily: 'var(--obs-sans)',
        fontSize: '13px',
        lineHeight: 1.55,
      }}
    >
      {card.evidence.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
    <div style={{ marginBottom: '16px' }}>
      <div style={{ marginBottom: '8px' }}>
        <SectionEyebrow tone="muted" dot={false}>
          {card.fallback.label}
        </SectionEyebrow>
      </div>
      <pre style={CODE_STYLE}>{card.fallback.command}</pre>
    </div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
      {card.links.map((link) => (
        <Link
          key={`${card.id}-${link.to}`}
          to={link.to}
          className="proof-board-link-chip"
          style={{
            color: 'var(--obs-red-1)',
            border: '1px solid var(--obs-card-border)',
            borderRadius: '4px',
            padding: '5px 10px',
            textDecoration: 'none',
            fontFamily: 'var(--obs-heading)',
            fontSize: '12px',
            fontWeight: 600,
          }}
        >
          {link.label}
        </Link>
      ))}
    </div>
  </EvidenceCard>
  );
};

function groupCardsByLab(cards: ProofCard[]) {
  const groups = new Map<string, ProofCard[]>();
  for (const card of cards) {
    const lab = cardLab(card);
    const items = groups.get(lab) ?? [];
    items.push(card);
    groups.set(lab, items);
  }
  return Array.from(groups.entries());
}

const ProofRail: React.FC<{
  eyebrow: string;
  title: string;
  summary: string;
  cards: ProofCard[];
  activeAnchor: string;
}> = ({ eyebrow, title, summary, cards, activeAnchor }) => {
  if (!cards.length) return null;
  const groupedCards = groupCardsByLab(cards);
  return (
    <section aria-label={title} style={{ marginBottom: '36px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '14px',
          flexWrap: 'wrap',
          marginBottom: '10px',
        }}
      >
        <div>
          <Eyebrow label={eyebrow} />
          <h2
            className="font-display"
            style={{
              margin: '6px 0 0',
              color: 'var(--obs-ink-1)',
              fontSize: 'var(--text-sub)',
              fontWeight: 400,
              lineHeight: 1.15,
              letterSpacing: 'var(--tracking-display)',
            }}
          >
            {title}
          </h2>
        </div>
        <SectionEyebrow tone="muted" dot={false}>
          {cards.length} {cards.length === 1 ? 'card' : 'cards'}
        </SectionEyebrow>
      </div>
      <p
        style={{
          color: 'var(--obs-ink-2)',
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          lineHeight: 1.55,
          margin: '0 0 16px',
          maxWidth: '760px',
        }}
      >
        {summary}
      </p>
      {groupedCards.map(([lab, labCards]) => (
        <div key={lab} style={{ marginBottom: '20px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '12px',
            }}
          >
            <Eyebrow label={lab} />
            <SectionEyebrow tone="muted" dot={false}>
              {labCards.length} {labCards.length === 1 ? 'card' : 'cards'}
            </SectionEyebrow>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: '16px',
            }}
          >
            {labCards.map((card) => (
              <ProofCardView
                key={card.id}
                card={card}
                highlighted={activeAnchor === card.id}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
};

const PersistedTurnReceiptPanel: React.FC<{ receipt: PersistedTurnReceipt }> = ({
  receipt,
}) => {
  // A receipt may represent a failed turn before policy or retrieval emitted
  // their respective arrays. Show absent evidence honestly rather than
  // crashing the proof surface while a participant inspects that failure.
  const citations = receipt.citations ?? [];
  const toolAuditIds = receipt.tool_audit_ids ?? [];
  const policy = receipt.policy_events?.[0];
  return (
    <EvidenceCard
      as="section"
      quiet
      padding="compact"
      aria-label="Persisted turn receipt"
      data-testid="persisted-turn-receipt"
      style={{ marginBottom: '28px' }}
    >
      <Eyebrow label="Persisted turn receipt" />
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          gap: '12px',
          alignItems: 'center',
          marginTop: '8px',
        }}
      >
        <div>
          <h2
            style={{
              fontFamily: 'var(--obs-heading)',
              fontSize: '22px',
              fontWeight: 600,
              margin: 0,
              color: 'var(--obs-ink-1)',
            }}
          >
            {receipt.turn_id}
          </h2>
          <p
            style={{
              fontFamily: 'var(--obs-sans)',
              fontSize: '13px',
              margin: '4px 0 0',
              color: 'var(--obs-ink-3)',
            }}
          >
            {receipt.terminal_status} on {receipt.rail}
          </p>
        </div>
        {policy && (
          <PolicyDecisionBadge
            decision={policy.decision}
            reason={policy.reason}
            size="md"
          />
        )}
      </div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '16px',
          marginTop: '16px',
          fontFamily: 'var(--obs-mono)',
          fontSize: '12px',
          color: 'var(--obs-ink-2)',
        }}
      >
        <span>{citations.length} catalog citations</span>
        <span>{toolAuditIds.length} executed tools</span>
        {typeof receipt.latency_ms === 'number' && (
          <span>{Math.round(receipt.latency_ms)}ms</span>
        )}
      </div>
      {citations.length > 0 && (
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: '16px 0 0',
            display: 'grid',
            gap: '7px',
          }}
        >
          {citations.map((citation) => (
            <li
              key={citation.evidence_id}
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                color: 'var(--obs-ink-2)',
              }}
            >
              <code style={{ fontFamily: 'var(--obs-mono)', fontSize: '11px' }}>
                {citation.entity_id}
              </code>{' '}
              {citation.quote}
            </li>
          ))}
        </ul>
      )}
    </EvidenceCard>
  );
};

const ProofBoard: React.FC<ProofBoardProps> = ({ focusCardId }) => {
  const location = useLocation();
  const [data, setData] = useState<ProofBoardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [turnReceipt, setTurnReceipt] = useState<PersistedTurnReceipt | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    apiFetch('/api/observatory/proof-board', { credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) {
          let code: string | undefined;
          try {
            const body = await response.json() as { detail?: string; error?: string };
            code = body.detail ?? body.error;
          } catch {
            // The HTTP status still identifies the failure without a JSON body.
          }
          throw new ProofBoardApiError(response.status, code);
        }
        return response.json();
      })
      .then((json: ProofBoardPayload) => {
        if (active) {
          setData(json);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedTurnId = useMemo(
    () => new URLSearchParams(location.search).get('turn'),
    [location.search],
  );
  const authenticationRequired =
    error instanceof ProofBoardApiError &&
    error.status === 401 &&
    (!error.code ||
      error.code === 'authentication_required' ||
      error.code === 'invalid_credentials');
  const credentialsRejected =
    error instanceof ProofBoardApiError && error.code === 'invalid_credentials';
  const cognitoBrowserAuthConfigured = Boolean(
    import.meta.env.VITE_COGNITO_DOMAIN &&
      import.meta.env.VITE_COGNITO_CLIENT_ID,
  );

  useEffect(() => {
    if (!selectedTurnId) {
      setTurnReceipt(null);
      return;
    }
    let active = true;
    apiFetch(`/api/governed-receipts/${encodeURIComponent(selectedTurnId)}`, {
      credentials: 'include',
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((receipt: PersistedTurnReceipt | null) => {
        if (active) setTurnReceipt(receipt);
      })
      .catch(() => {
        if (active) setTurnReceipt(null);
      });
    return () => {
      active = false;
    };
  }, [selectedTurnId]);

  const activeAnchor = useMemo(() => {
    if (!location.hash) return '';
    return decodeURIComponent(location.hash.replace(/^#/, ''));
  }, [location.hash]);
  const focusedCardId = focusCardId ?? activeAnchor;
  const isAuditFocus = focusedCardId === 'audit-ledger';

  const rails = useMemo(() => {
    const cards = data?.cards ?? [];
    return {
      required: cards.filter((card) => card.required),
      optional: cards.filter((card) => !card.required),
    };
  }, [data]);
  const focusedCard = useMemo(
    () => data?.cards.find((card) => card.id === focusedCardId) ?? null,
    [data, focusedCardId],
  );

  return (
    <div className="observatory-reading-page observatory-proof-board-page">
      {isAuditFocus && (
        <Link
          to="/observatory/proof-board"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '7px',
            marginBottom: '24px',
            color: 'var(--obs-ink-2)',
            fontFamily: 'var(--obs-heading)',
            fontSize: '13px',
            fontWeight: 600,
            textDecoration: 'none',
          }}
        >
          <ArrowLeft size={15} aria-hidden="true" />
          All checkpoints
        </Link>
      )}
      <EditorialTitle referenceId="proof"
        backToReferences={!isAuditFocus}
        eyebrow={
          isAuditFocus
            ? 'Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore'
            : 'Observe · Evidence'
        }
        title="Proof Board"
        summary={
          isAuditFocus
            ? 'A focused read of the live Aurora rows and governed receipt. The SQL result is the proof; this view confirms that the expected evidence is present.'
            : 'Read the durable runtime, policy, execution, and Aurora evidence recorded by the workshop. Run the SQL yourself when you need the proof rather than a summary.'
        }
      />

      {turnReceipt && <PersistedTurnReceiptPanel receipt={turnReceipt} />}

      {loading && (
        <p className="font-mono" style={{ color: 'var(--obs-ink-3)' }}>
          {isAuditFocus ? 'Loading audit proof...' : 'Loading proof board...'}
        </p>
      )}
      {authenticationRequired && (
        <div
          role="alert"
          style={{
            border: '1px solid var(--obs-status-degraded-line)',
            background: 'var(--obs-status-degraded-bg)',
            borderRadius: 'var(--gov-radius-lg)',
            padding: '18px 20px',
            color: 'var(--obs-ink-1)',
            fontFamily: 'var(--obs-sans)',
            marginBottom: '24px',
            maxWidth: '760px',
          }}
        >
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
            <KeyRound
              size={20}
              strokeWidth={1.8}
              aria-hidden="true"
              style={{ flex: '0 0 auto', marginTop: '2px', color: 'var(--obs-status-degraded-fg)' }}
            />
            <div>
              <h2
                style={{
                  margin: 0,
                  fontFamily: 'var(--obs-heading)',
                  fontSize: '17px',
                  fontWeight: 600,
                }}
              >
                {credentialsRejected
                  ? 'Cognito session expired'
                  : 'Cognito identity required'}
              </h2>
              <p
                style={{
                  margin: '6px 0 14px',
                  color: 'var(--obs-ink-2)',
                  fontSize: '14px',
                  lineHeight: 1.55,
                }}
              >
                {credentialsRejected
                  ? 'Your saved proof remains unchanged. Authenticate again to load receipts tied to your verified Cognito subject.'
                  : 'Proof Board evidence is scoped to the verified caller. Authenticate before loading receipts tied to a Cognito subject.'}
              </p>
              {cognitoBrowserAuthConfigured ? (
                <a
                  href={apiUrl('/api/auth/signin?provider=email')}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '7px',
                    color: 'var(--obs-ink-1)',
                    fontSize: '13px',
                    fontWeight: 600,
                    textDecoration: 'underline',
                    textUnderlineOffset: '3px',
                  }}
                >
                  <KeyRound size={15} strokeWidth={1.9} aria-hidden="true" />
                  Authenticate with Cognito
                </a>
              ) : (
                <p
                  style={{
                    margin: 0,
                    color: 'var(--obs-ink-2)',
                    fontSize: '13px',
                    fontWeight: 600,
                  }}
                >
                  Browser authentication is not configured for this preview.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
      {error && !authenticationRequired && (
        <div
          role="alert"
          style={{
            border: '1px solid var(--obs-status-attention-line)',
            background: 'var(--obs-status-attention-bg)',
            borderRadius: 'var(--gov-radius-lg)',
            padding: '14px 16px',
            color: 'var(--obs-status-attention-fg)',
            fontFamily: 'var(--obs-sans)',
            marginBottom: '24px',
          }}
        >
          Proof board API unavailable: {error.message}
        </div>
      )}

      {data && (
        isAuditFocus ? (
          focusedCard ? (
            <section
              aria-label="Lab 3 audit evidence"
              style={{ maxWidth: '860px' }}
            >
              <ProofCardView card={focusedCard} highlighted titleAs="h2" />
            </section>
          ) : (
            <div
              role="alert"
              style={{
                border: '1px solid var(--obs-card-border)',
                borderRadius: 'var(--gov-radius-lg)',
                padding: '18px 20px',
                color: 'var(--obs-ink-2)',
                fontFamily: 'var(--obs-sans)',
              }}
            >
              The audit-ledger checkpoint is not available from this backend.
            </div>
          )
        ) : (
          <>
            <GovernedProofRail cards={data.cards} receipt={data.managedReceipt} />
            <ReadinessPanel checks={data.readiness.checks} />

            <ProofRail
              eyebrow="Baseline evidence"
              title="Lab checkpoints"
              summary="These cards summarize the evidence each lab leaves behind. Use their terminal or SQL fallbacks when you need canonical proof."
              cards={rails.required}
              activeAnchor={activeAnchor}
            />
            <ReceiptStrip receipt={data.managedReceipt} />
            <ProofRail
              eyebrow="Extension evidence"
              title="Managed boundary"
              summary="These cards remain optional only in the separate builders format."
              cards={rails.optional}
              activeAnchor={activeAnchor}
            />
          </>
        )
      )}
    </div>
  );
};

export default ProofBoard;
