import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  RotateCw,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import type { LabExercise } from '../../labs/labCatalog';
import {
  CLASSIFICATION_COPY,
  type EvidenceClassification,
  type EvidenceDatum,
  type LabStatus,
  type ProvenanceClass,
} from '../../labs/evidence';

const PROVENANCE_CLASS: Record<ProvenanceClass, string> = {
  Authoritative: 'authoritative',
  'Execution telemetry': 'telemetry',
  Derived: 'derived',
  Fixture: 'fixture',
  Unknown: 'unknown',
};

export function SourceBadge({
  provenance,
  compact = false,
}: {
  provenance: ProvenanceClass;
  compact?: boolean;
}) {
  return (
    <span
      className="lab-source-badge"
      data-provenance={PROVENANCE_CLASS[provenance]}
      data-compact={compact ? 'true' : undefined}
    >
      {provenance}
    </span>
  );
}

export function LabStatusMark({
  status,
  loading = false,
  discloseDetails = false,
}: {
  status: LabStatus;
  loading?: boolean;
  discloseDetails?: boolean;
}) {
  const Icon = loading
    ? CircleDashed
    : status.key === 'evidence_observed'
      ? CircleCheck
      : status.key === 'unknown' || status.key === 'evidence_missing'
        ? CircleAlert
        : CircleDashed;

  const metadata = (
    <span className="lab-status-mark-meta">
      <SourceBadge provenance={loading ? 'Unknown' : status.provenance} compact />
      <span>{loading ? 'Current response pending' : status.source}</span>
      <span>{loading ? 'Not observed' : status.freshness}</span>
    </span>
  );

  return (
    <div
      className="lab-status-mark"
      data-status={loading ? 'loading' : status.key}
    >
      <span className="lab-status-mark-main" role="status">
        <Icon size={15} strokeWidth={1.8} aria-hidden="true" />
        {discloseDetails ? <span>Environment:</span> : null}
        <strong>{loading ? 'Reading evidence' : status.label}</strong>
      </span>
      {discloseDetails ? (
        <details className="lab-evidence-disclosure">
          <summary>Evidence details</summary>
          {metadata}
        </details>
      ) : metadata}
    </div>
  );
}

export function EvidenceLoadNotice({
  error,
  onRetry,
}: {
  error: string;
  onRetry: () => void;
}) {
  return (
    <div className="lab-load-notice" role="alert">
      <div>
        <strong>Live evidence is unavailable</strong>
        <p>{error} No fixture or cached proof has been substituted.</p>
      </div>
      <button type="button" onClick={onRetry}>
        <RotateCw size={15} aria-hidden="true" />
        Retry
      </button>
    </div>
  );
}

export function ExerciseRail({
  exercises,
  activeExercise,
  statuses,
}: {
  exercises: readonly LabExercise[];
  activeExercise: LabExercise;
  statuses: Map<string, LabStatus>;
}) {
  return (
    <nav className="lab-exercise-rail" aria-label="Labs">
      <p className="lab-rail-title">Labs</p>
      <ol className="lab-exercise-rail-list">
        {exercises.map((exercise) => {
          const status = statuses.get(exercise.id);
          const active = exercise.id === activeExercise.id;
          return (
            <li key={exercise.id}>
              <Link
                to={`/observatory/labs/${exercise.id}`}
                className="lab-exercise-rail-link"
                data-active={active ? 'true' : undefined}
                aria-current={active ? 'page' : undefined}
              >
                <span className="lab-exercise-rail-number">
                  Lab {Number(exercise.number)}
                </span>
                <span className="lab-exercise-rail-copy">
                  <strong>{exercise.shortTitle}</strong>
                  <small>{status?.label ?? 'Unknown'}</small>
                </span>
                <ChevronRight size={15} strokeWidth={1.8} aria-hidden="true" />
              </Link>
            </li>
          );
        })}
      </ol>
      <Link
        to="/observatory/workbench#resources"
        className="lab-rail-reference"
      >
        <BookOpen size={15} strokeWidth={1.8} aria-hidden="true" />
        Evidence routes
      </Link>
    </nav>
  );
}

const WORKFLOW_STEPS = [
  'Baseline',
  'Build / operate',
  'Measure',
  'Prove',
  'Explain',
] as const;

export function WorkflowStepper() {
  return (
    <section className="lab-workflow" aria-labelledby="lab-workflow-title">
      <div className="lab-section-heading">
        <h2 id="lab-workflow-title">Lab contract</h2>
        <p>Focused two-hour stages, not inferred learner progress.</p>
      </div>
      <ol className="lab-workflow-list">
        {WORKFLOW_STEPS.map((step, index) => (
          <li key={step}>
            <span>{step}</span>
            {index < WORKFLOW_STEPS.length - 1 ? (
              <ArrowRight size={15} strokeWidth={1.7} aria-hidden="true" />
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function EvidenceDatumList({
  title,
  data,
  emptyMessage,
}: {
  title: string;
  data: EvidenceDatum[];
  emptyMessage?: string;
}) {
  return (
    <section className="lab-evidence-section">
      <h2>{title}</h2>
      {data.length > 0 ? (
        <dl className="lab-evidence-data">
          {data.map((datum) => (
            <div key={datum.id} className="lab-evidence-datum">
              <dt>{datum.label}</dt>
              <dd>
                <strong>{datum.value}</strong>
                <span className="lab-evidence-meta">
                  <SourceBadge provenance={datum.provenance} compact />
                  <span>{datum.source}</span>
                  <span>{datum.freshness}</span>
                </span>
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="lab-evidence-empty">
          {emptyMessage ?? 'No scoped evidence values were returned.'}
        </p>
      )}
    </section>
  );
}

export function EvidenceClassificationCard({
  classification,
}: {
  classification: EvidenceClassification;
}) {
  const copy = CLASSIFICATION_COPY[classification];
  return (
    <section
      className="lab-classification"
      data-contradiction={copy.contradiction ? 'true' : undefined}
      aria-labelledby="lab-classification-title"
    >
      <span className="lab-classification-code">{classification}</span>
      <h2 id="lab-classification-title">{copy.title}</h2>
      <p>{copy.detail}</p>
      <div className="lab-classification-source">
        <SourceBadge
          provenance={
            classification === 'UNKNOWN_NO_EXECUTION' ? 'Unknown' : 'Derived'
          }
          compact
        />
        <span>Classification rules</span>
      </div>
    </section>
  );
}

export function LabActionBar({ exercise }: { exercise: LabExercise }) {
  return (
    <div className="lab-action-bar" aria-label="Lab actions">
      {exercise.primaryAction ? (
        <Link to={exercise.primaryAction.to} className="lab-action-primary">
          {exercise.primaryAction.label}
        </Link>
      ) : (
        <span className="lab-action-unavailable" role="status">
          <CircleAlert size={16} strokeWidth={1.8} aria-hidden="true" />
          Bundle export unavailable
        </span>
      )}
      <div className="lab-action-secondary">
        {exercise.supportingActions.map((action) => (
          <Link key={action.to} to={action.to}>
            {action.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
