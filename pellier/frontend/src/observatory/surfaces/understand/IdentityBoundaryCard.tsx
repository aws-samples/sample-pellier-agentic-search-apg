/**
 * IdentityBoundaryCard — who asked, for whose data, and what stopped it.
 *
 * This is the visual reconstruction of Lab 4. It is NOT the proof. The proof is
 * `scripts/prove_identity_boundary.py` plus the SQL it runs; this card reads the
 * rows that proof left behind in `pellier.governed_receipts` and lays them out
 * so the chain is legible in one glance.
 *
 * The distinction the card exists to make visible:
 *
 *   the storefront persona chooses a scenario
 *   the Cognito access token names the security principal
 *   Cedar compares that principal against the requested customer
 *   Aurora Row-Level Security refuses the same crossing independently
 *
 * Every row carries its own provenance. A seeded forensic fixture and a live
 * provider decision live in the same table, so a page-level badge would let the
 * fixture borrow the credibility of the live rows beside it.
 *
 * Absence is only ever claimed when it was measured. `executionRow: 'unknown'`
 * renders as "not correlated", never as "no execution" — a receipt that predates
 * keyed correlation cannot prove non-execution, and saying otherwise would be
 * the same evidence theatre the surface is supposed to expose.
 */

import React from 'react';
import { ExpCard, Eyebrow } from '../../components';
import { useObservatoryData } from '../../hooks/useObservatoryData';
import { SourceBadge } from '../labs/LabShared';
import type { ProvenanceClass } from '../../labs/evidence';

type ExecutionRowState = 'present' | 'absent' | 'unknown';
type Ownership = 'own-customer' | 'other-customer' | 'unmapped' | 'ambiguous-mapping';

interface IdentityAttempt {
  receiptId: number;
  correlationKey: string;
  /** Receipt/session key for one Gateway invocation. */
  idempotencyKey: string;
  verifiedUsername: string | null;
  /** Already truncated by the backend; the full subject never reaches the browser. */
  verifiedSubject: string | null;
  requestedCustomerId: string | null;
  mappedCustomerId: string | null;
  /** A valid subject resolves to exactly one customer after migration 038. */
  mappingCardinality: number;
  ownership: Ownership;
  decision: string;
  policyName: string | null;
  policyEngineId: string | null;
  tokenFingerprint: string | null;
  identitySource: string | null;
  provenance: ProvenanceClass;
  tool: string | null;
  executionRow: ExecutionRowState;
  keyedAuditRows: number;
  durableWriteRows: number;
  auditId: number | null;
  createdAt: string | null;
}

interface IdentityRun {
  runId: string;
  startedAt: string | null;
  attempts: IdentityAttempt[];
  caseCount: number;
  denyCount: number;
  allowCount: number;
  provenance: ProvenanceClass;
  /** Two refusals with no execution plus at least one permit that executed. */
  complete: boolean;
  /** A DENY that executed, or an ALLOW that did not. Never hidden. */
  contradiction: string | null;
  decisions: string[];
}

interface IdentityBoundaryPayload {
  attempts: IdentityAttempt[];
  count: number;
  liveRuns: IdentityRun[];
  liveCount: number;
  selectedRunId: string | null;
  fixtures: IdentityAttempt[];
  fixtureCount: number;
  emptyReason: string | null;
}

const EXECUTION_LABEL: Record<ExecutionRowState, string> = {
  present: 'Keyed execution evidence present',
  absent: 'No row carries this key',
  unknown: 'Not correlated by key',
};

const OWNERSHIP_LABEL: Record<Ownership, string> = {
  'own-customer': 'own customer',
  'other-customer': "another customer's",
  unmapped: 'no mapped customer',
  'ambiguous-mapping': 'invalid ambiguous mapping',
};

const mono: React.CSSProperties = {
  fontFamily: 'var(--obs-mono)',
  fontSize: 'var(--obs-mono-size)',
  color: 'var(--obs-ink-1)',
};

const label: React.CSSProperties = {
  fontFamily: 'var(--obs-mono)',
  fontSize: 'var(--text-label)',
  letterSpacing: 'var(--obs-label-track)',
  textTransform: 'uppercase',
  color: 'var(--obs-ink-4)',
};

function Field({ name, value }: { name: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 }}>
      <span style={label}>{name}</span>
      <span style={{ ...mono, wordBreak: 'break-word' }}>{value ?? '—'}</span>
    </div>
  );
}

function AttemptRow({ attempt }: { attempt: IdentityAttempt }) {
  const denied = attempt.decision === 'DENY';
  // Terracotta is "in flight or refused"; olive is verified. Burgundy is the
  // brand accent and is deliberately not used to encode a status here.
  const tone = denied ? 'var(--obs-terracotta)' : 'var(--obs-olive)';

  return (
    <article
      data-testid={`identity-attempt-${attempt.receiptId}`}
      data-decision={attempt.decision}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        padding: '16px 18px',
        border: '1px solid var(--obs-rule-1)',
        borderRadius: 'var(--obs-card-radius)',
        background: 'var(--obs-cream-2)',
      }}
    >
      <header
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '10px',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ ...mono, fontSize: '14px' }}>
          <strong>{attempt.verifiedUsername ?? 'unknown principal'}</strong>
          {' asked for '}
          <strong>{attempt.requestedCustomerId ?? 'no customer'}</strong>
          {' · '}
          {OWNERSHIP_LABEL[attempt.ownership]}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              ...label,
              color: tone,
              /* Decision is never encoded by colour alone — the word is the
                 signal and the colour only reinforces it. */
              fontWeight: 600,
            }}
          >
            {attempt.decision}
          </span>
          <SourceBadge provenance={attempt.provenance} compact />
        </span>
      </header>

      <div
        style={{
          display: 'grid',
          gap: '14px 22px',
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
        }}
      >
        <Field name="Verified subject" value={attempt.verifiedSubject} />
        <Field name="Mapped customer" value={attempt.mappedCustomerId} />
        <Field name="Action" value={attempt.tool} />
        <Field name="Policy" value={attempt.policyName} />
        <Field name="Policy engine" value={attempt.policyEngineId} />
        <Field name="Receipt key" value={attempt.correlationKey || null} />
        <Field name="Write key" value={attempt.idempotencyKey || null} />
        <Field
          name="Execution row"
          value={
            <span style={{ color: attempt.executionRow === 'present' ? 'var(--obs-olive)' : undefined }}>
              {EXECUTION_LABEL[attempt.executionRow]}
              {attempt.executionRow === 'present' && attempt.auditId
                ? ` (audit ${attempt.auditId})`
                : ''}
            </span>
          }
        />
        <Field
          name="Durable write"
          value={
            attempt.durableWriteRows > 0
              ? `${attempt.durableWriteRows} finalized write operation`
              : attempt.executionRow === 'absent'
                ? 'none, as expected for a refusal'
                : 'none recorded'
          }
        />
        <Field name="Token fingerprint" value={attempt.tokenFingerprint} />
      </div>
    </article>
  );
}

const IdentityBoundaryCard: React.FC = () => {
  const { data, loading, error, errorStatus } = useObservatoryData<IdentityBoundaryPayload>({
    key: 'identity-boundary',
  });
  const accessRestricted = errorStatus === 401 || errorStatus === 403;

  return (
    <ExpCard>
      <Eyebrow label="Govern · Identity boundary · verified principal vs requested customer" />
      <h3
        style={{
          fontFamily: 'var(--obs-heading)',
          fontSize: 'var(--obs-section-size)',
          fontWeight: 600,
          margin: '6px 0 10px',
          color: 'var(--obs-ink-1)',
        }}
      >
        Persona chooses the scenario. Cognito names the principal.
      </h3>
      <p
        style={{
          fontFamily: 'var(--obs-sans)',
          fontSize: '14px',
          lineHeight: 1.6,
          color: 'var(--obs-ink-2)',
          maxWidth: '68ch',
          margin: '0 0 16px',
        }}
      >
        Choosing Marco, Anna, or Theo selects a workshop scenario and authenticates
        nobody. Live proof records bind a validated Cognito principal to the requested
        <code> customer_id</code>, a policy decision, and keyed execution evidence.
        Lab 4 tests the ownership policy and Aurora Row-Level Security independently.
        Read each record’s provenance and measured result; this view does not
        establish that an untested control is active.
      </p>

      {loading && (
        <p style={{ ...mono, color: 'var(--obs-ink-3)' }}>Reading governed receipts…</p>
      )}

      {error && (
        <p style={{ ...mono, color: 'var(--obs-terracotta)' }}>
          {accessRestricted
            ? 'Sign in with an Operator account to inspect this cross-principal reconstruction. Shopper sign-in alone does not grant access.'
            : error}
        </p>
      )}

      {!loading && !error && data && (
        <>
          <section aria-labelledby="identity-live-heading">
            <h4
              id="identity-live-heading"
              style={{
                ...label,
                color: 'var(--obs-ink-2)',
                margin: '0 0 10px',
              }}
            >
              Live identity proof
            </h4>

            {data.liveRuns.length === 0 ? (
              <div
                data-testid="identity-boundary-empty"
                style={{
                  padding: '14px 16px',
                  border: '1px dashed var(--obs-rule-2)',
                  borderRadius: 'var(--obs-card-radius)',
                  background: 'var(--obs-cream-1)',
                }}
              >
                <p style={{ ...mono, color: 'var(--obs-ink-2)', marginBottom: '8px' }}>
                  {data.emptyReason}
                </p>
                <p style={{ ...mono, color: 'var(--obs-ink-3)' }}>
                  python3 scripts/prove_identity_boundary.py
                </p>
              </div>
            ) : (
              data.liveRuns.map((run) => (
                <div
                  key={run.runId}
                  data-testid={`identity-run-${run.runId}`}
                  data-selected={run.runId === data.selectedRunId ? 'true' : undefined}
                  style={{ marginBottom: '18px' }}
                >
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'baseline',
                      gap: '10px',
                      marginBottom: '10px',
                    }}
                  >
                    <span style={{ ...mono, color: 'var(--obs-ink-2)' }}>{run.runId}</span>
                    <span style={{ ...label }}>
                      {run.denyCount} refused · {run.allowCount} permitted
                    </span>
                    {/* Complete means the matrix held, not that a lab is done.
                        There is no honest completion signal for optional work. */}
                    <span
                      style={{
                        ...label,
                        color: run.complete ? 'var(--obs-olive)' : 'var(--obs-ink-4)',
                        fontWeight: 600,
                      }}
                    >
                      {run.complete ? 'matrix held' : 'matrix incomplete'}
                    </span>
                  </div>
                  {run.contradiction && (
                    <p
                      data-testid={`identity-contradiction-${run.runId}`}
                      style={{
                        ...mono,
                        color: 'var(--obs-terracotta)',
                        marginBottom: '10px',
                      }}
                    >
                      Contradiction: {run.contradiction}
                    </p>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {run.attempts.map((attempt) => (
                      <AttemptRow key={attempt.receiptId} attempt={attempt} />
                    ))}
                  </div>
                </div>
              ))
            )}
          </section>

          {data.fixtures.length > 0 && (
            <section
              aria-labelledby="identity-fixture-heading"
              data-testid="identity-boundary-fixtures"
              style={{ marginTop: '24px', paddingTop: '18px', borderTop: '1px solid var(--obs-rule-1)' }}
            >
              <h4
                id="identity-fixture-heading"
                style={{ ...label, color: 'var(--obs-ink-2)', margin: '0 0 6px' }}
              >
                Seeded reference fixture
              </h4>
              <p
                style={{
                  fontFamily: 'var(--obs-sans)',
                  fontSize: '13px',
                  lineHeight: 1.55,
                  color: 'var(--obs-ink-3)',
                  maxWidth: '68ch',
                  margin: '0 0 12px',
                }}
              >
                Shipped with the workshop so the forensic question has an answer before
                anyone runs anything. It is not a provider decision, it cannot satisfy
                Lab 4, and it never contributes to a live run&apos;s summary above. Its
                execution state reads &ldquo;not correlated&rdquo; because no key was
                ever recorded for it — that is different from proving nothing ran.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {data.fixtures.map((attempt) => (
                  <AttemptRow key={attempt.receiptId} attempt={attempt} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

    </ExpCard>
  );
};

export default IdentityBoundaryCard;
