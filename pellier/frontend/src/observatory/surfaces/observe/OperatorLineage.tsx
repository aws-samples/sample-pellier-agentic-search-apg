import React, { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  Check,
  CircleAlert,
  CircleDashed,
  Database,
  GitBranch,
  MessageSquareQuote,
  ShieldCheck,
  UserCheck,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import type {
  ConciergeGraphNode,
  ConciergeOrchestration,
  ShopperHandoff,
} from '../../../services/operatorConcierge'
import './OperatorLineage.css'

interface LineageReview {
  reviewId: number
  customerId: string
  customerName: string
  action: string
  status: 'pending' | 'approved' | 'rejected' | string
  sourceTurnId: string | null
  executionTurnId: string | null
  actionHash: string
}

interface LineageExecution {
  latestReceipt?: {
    policy_outcome?: string
    aurora_outcome?: string
    evidence_outcome?: string
    rail?: string
  }
  layers?: {
    key: string
    label: string
    present: boolean
    detail: string
  }[]
}

interface OperatorLineageResponse {
  customerId: string
  customerName?: string
  dataSource: string
  handoff: ShopperHandoff | null
  review: LineageReview | null
  orchestration: (ConciergeOrchestration & {
    sessionId?: string
    turnId?: string
  }) | null
  execution: LineageExecution | null
}

type StageState = 'complete' | 'waiting' | 'stopped'

interface Stage {
  id: string
  title: string
  owner: string
  state: StageState
  detail: string
  node?: ConciergeGraphNode
}

function stageIcon(stage: Stage): React.ReactNode {
  if (stage.state === 'complete') {
    return <Check size={16} strokeWidth={2} aria-hidden="true" />
  }
  if (stage.state === 'stopped') {
    return <CircleAlert size={16} strokeWidth={1.8} aria-hidden="true" />
  }
  return <CircleDashed size={16} strokeWidth={1.8} aria-hidden="true" />
}

function graphNodeState(
  node: ConciergeGraphNode | undefined,
  orchestrationStatus?: string,
): StageState {
  if (!node) {
    return ['failed', 'error', 'stopped', 'unavailable'].includes(
      String(orchestrationStatus ?? '').toLowerCase(),
    )
      ? 'stopped'
      : 'waiting'
  }
  const status = String(node.status ?? '').toLowerCase()
  if (['complete', 'completed', 'success', 'succeeded'].includes(status)) {
    return 'complete'
  }
  if (['failed', 'error', 'stopped', 'unavailable'].includes(status)) {
    return 'stopped'
  }
  return 'waiting'
}

function executionState(
  execution: LineageExecution['latestReceipt'] | undefined,
): StageState {
  if (!execution) return 'waiting'

  const policy = String(execution.policy_outcome ?? '').toUpperCase()
  const database = String(execution.aurora_outcome ?? '').toUpperCase()
  const evidence = String(execution.evidence_outcome ?? '').toUpperCase()

  if (
    policy === 'DENY' ||
    ['DENIED', 'NOT_ATTEMPTED', 'NOT_REACHED', 'FAILED', 'ERROR', 'REFUSED'].includes(
      database,
    ) ||
    ['FAILED', 'ERROR', 'INCOMPLETE'].includes(evidence)
  ) {
    return 'stopped'
  }

  const databaseComplete = [
    'APPLIED',
    'PERMITTED',
    'SUCCESS',
    'SUCCEEDED',
    'COMPLETED',
  ].includes(database)
  const evidenceComplete = ['COMPLETE', 'RECEIPTED', 'SUCCEEDED'].includes(evidence)
  const policyComplete = ['ALLOW', 'WOULD_DENY', 'LOG_ONLY'].includes(policy)
  return policyComplete && databaseComplete && evidenceComplete
    ? 'complete'
    : 'waiting'
}

function reviewCheckpoint(review: LineageReview | null): Stage {
  if (!review) {
    return {
      id: 'checkpoint',
      title: 'Pending review created',
      owner: 'Pellier application',
      state: 'waiting',
      detail: 'No durable review is linked to this handoff.',
    }
  }
  return {
    id: 'checkpoint',
    title: 'Pending review created',
    owner: 'PostgreSQL',
    state: 'complete',
    detail: `Review ${review.reviewId} binds ${review.action} to the stored action hash.`,
  }
}

function humanDecision(review: LineageReview | null): Stage {
  if (!review || review.status === 'pending') {
    return {
      id: 'human-decision',
      title: 'Human decision',
      owner: 'Pellier Operator',
      state: 'waiting',
      detail: review
        ? `Review ${review.reviewId} is waiting for a separate authenticated decision.`
        : 'No review is available for a person to decide.',
    }
  }
  return {
    id: 'human-decision',
    title: 'Human decision recorded',
    owner: 'Pellier Operator',
    state: review.status === 'approved' ? 'complete' : 'stopped',
    detail:
      review.status === 'approved'
        ? `Review ${review.reviewId} binds approval to the stored action hash.`
        : `Review ${review.reviewId} was declined; governed execution must stop.`,
  }
}

function graphStage(
  nodeId: string,
  title: string,
  orchestration: OperatorLineageResponse['orchestration'],
): Stage {
  const node = orchestration?.executedNodes?.find((item) => item.nodeId === nodeId)
  return {
    id: nodeId,
    title,
    owner: 'Strands Graph',
    state: graphNodeState(node, orchestration?.status),
    detail: node
      ? `${node.status}${node.durationMs != null ? ` in ${node.durationMs}ms` : ''}.`
      : 'No persisted execution for this graph node yet.',
    node,
  }
}

const OperatorLineage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const requestedCustomerId =
    searchParams.get('customer')?.trim() || 'CUST-THEO'
  const requestedReviewValue = searchParams.get('review')?.trim() || ''
  const requestedReviewId = /^[1-9]\d*$/.test(requestedReviewValue)
    ? Number(requestedReviewValue)
    : null
  const [data, setData] = useState<OperatorLineageResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setError(null)
    setData(null)
    const reviewQuery =
      requestedReviewId == null ? '' : `?review_id=${requestedReviewId}`
    fetch(
      `/api/observatory/operator-lineage/${encodeURIComponent(
        requestedCustomerId,
      )}${reviewQuery}`,
      {
      credentials: 'include',
      signal: controller.signal,
      },
    )
      .then(async (response) => {
        if (!response.ok) {
          const body = (await response.json().catch(() => ({}))) as {
            detail?: string
          }
          throw new Error(body.detail ?? `request_failed_${response.status}`)
        }
        return response.json() as Promise<OperatorLineageResponse>
      })
      .then((response) => {
        if (active) setData(response)
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        if (active) {
          setError(
            reason instanceof Error ? reason.message : 'operator_lineage_unavailable',
          )
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [requestedCustomerId, requestedReviewId])

  const stages = useMemo<Stage[]>(() => {
    if (!data?.handoff) return []
    const execution = data.execution?.latestReceipt
    return [
      {
        id: 'specialist',
        title: 'Storefront specialist',
        owner: data.handoff.routing.specialist || 'Customer Service Agent',
        state: 'complete',
        detail: `Captured the shopper request and observed ${
          data.handoff.routing.tools?.length ?? 0
        } tool call(s).`,
      },
      {
        id: 'handoff',
        title: 'Immutable shopper handoff',
        owner: 'Governed turn receipt',
        state: 'complete',
        detail: `Bound to ${data.handoff.source.turnId}; reported context, not authority.`,
      },
      reviewCheckpoint(data.review),
      graphStage('case-investigator', 'Case Investigator Agent', data.orchestration),
      graphStage('resolution-planner', 'Resolution Planner Agent', data.orchestration),
      humanDecision(data.review),
      {
        id: 'execution',
        title: 'Governed execution attempt',
        owner: execution?.rail || 'Gateway, Policy, and PostgreSQL',
        state: execution
          ? executionState(execution)
          : data.review?.status === 'rejected'
            ? 'stopped'
            : 'waiting',
        detail: execution
          ? `Policy ${execution.policy_outcome}; PostgreSQL ${execution.aurora_outcome}; evidence ${execution.evidence_outcome}.`
          : data.review?.status === 'rejected'
            ? 'The human declined the review, so execution correctly stopped.'
            : 'No execution receipt is visible for this operator.',
      },
    ]
  }, [data])

  return (
    <div className="observatory-lineage">
      <header className="observatory-lineage-head">
        <div>
          <h1 className="observatory-page-title font-display">Operator lineage</h1>
          <p>
            {data?.customerName ?? 'This client'}&rsquo;s live closed loop,
            reconstructed from PostgreSQL and persisted graph artifacts.
            Conversation explains the case; current rows decide what is true.
          </p>
        </div>
        {data?.dataSource ? (
          <span className="observatory-lineage-source">
            <Database size={15} strokeWidth={1.8} aria-hidden="true" />
            {data.dataSource}
          </span>
        ) : null}
      </header>

      {loading ? (
        <div className="observatory-lineage-state">Reading live lineage…</div>
      ) : error ? (
        <div className="observatory-lineage-state" data-state="error">
          <strong>
            {error === 'authentication_required' || error === 'invalid_credentials'
              ? 'Operator sign-in required'
              : error === 'operator_group_required'
                ? 'Operator access required'
                : 'The live lineage could not be read.'}
          </strong>
          <span>
            {error === 'authentication_required' || error === 'invalid_credentials'
              ? 'Sign in with the workshop operator account to inspect this principal-scoped lineage.'
              : error === 'operator_group_required'
                ? 'This signed-in account is not a member of the operator group.'
                : error}
          </span>
        </div>
      ) : !data?.handoff ? (
        <div className="observatory-lineage-state">
          <strong>
            No durable handoff is present for {requestedCustomerId} yet.
          </strong>
          <span>
            Apply migration 028, then run the client&rsquo;s governed storefront
            journey. This view does not substitute fixture data.
          </span>
        </div>
      ) : (
        <>
          <section className="observatory-lineage-context">
            <div>
              <MessageSquareQuote size={18} strokeWidth={1.8} aria-hidden="true" />
              <h2>Reported by {data.customerName ?? data.customerId}</h2>
              <blockquote>{data.handoff.shopperRequest}</blockquote>
              <p>Untrusted shopper context from the original append-only receipt.</p>
            </div>
            <ArrowRight size={19} strokeWidth={1.6} aria-hidden="true" />
            <div>
              <ShieldCheck size={18} strokeWidth={1.8} aria-hidden="true" />
              <h2>Bound proposal</h2>
              <strong>{data.handoff.proposal.action}</strong>
              <p>
                Review {data.handoff.proposal.reviewId}; current order, inventory,
                policy, and execution state are re-read independently.
              </p>
            </div>
          </section>

          <section className="observatory-lineage-flow">
            <div className="observatory-lineage-flow-head">
              <div>
                <GitBranch size={18} strokeWidth={1.8} aria-hidden="true" />
                <h2>Closed-loop execution</h2>
              </div>
              <span>
                {data.orchestration?.pattern ?? 'Strands graph not run'}
                {data.orchestration?.deploymentTarget
                  ? ` · ${data.orchestration.deploymentTarget} target`
                  : ''}
              </span>
            </div>
            {data.orchestration?.execution === 'agentcore-runtime' ? (
              <dl className="observatory-lineage-runtime" aria-label="Operator Runtime evidence">
                <dt>Executed build</dt>
                <dd><code>{data.orchestration.buildFingerprint ?? 'Not recorded'}</code></dd>
                <dt>Matches this checkout</dt>
                <dd>{data.orchestration.fingerprintMatches === true ? 'Verified' : 'Not established'}</dd>
                <dt>Runtime session</dt>
                <dd><code>{data.orchestration.runtimeSessionId ?? 'Not recorded'}</code></dd>
              </dl>
            ) : null}
            <ol>
              {stages.map((stage) => (
                <li
                  key={stage.id}
                  data-stage-state={stage.state}
                  data-testid={`operator-lineage-${stage.id}`}
                >
                  <span className="observatory-lineage-marker">
                    {stageIcon(stage)}
                  </span>
                  <div>
                    <h3>{stage.title}</h3>
                    <span>{stage.owner}</span>
                    <p>{stage.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <footer className="observatory-lineage-links">
            <Link to={`/operator/reviews/${data.review?.reviewId ?? data.handoff.proposal.reviewId}`}>
              <UserCheck size={16} strokeWidth={1.8} aria-hidden="true" />
              Open the human checkpoint
            </Link>
            <span>
              Source turn <code>{data.handoff.source.turnId}</code>
            </span>
          </footer>
        </>
      )}
    </div>
  )
}

export default OperatorLineage
