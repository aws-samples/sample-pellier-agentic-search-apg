#!/usr/bin/env python3
"""Read-only Lab 4 proof of one human-reviewed return, across three phases.

This script never proposes, confirms or executes an action. The participant does
that in Operator. It reads exact review/turn/key evidence through psql and compares
it with the proposed-phase snapshot. Do not reuse snapshots from another run.

Lineage is derived, not copied. The review row names the turn that created it,
and that turn's saved Operator Concierge artifact must list this exact review ID
and action hash among its proposed actions. A later turn that merely resolved to
the same open review carries a different turn ID, so it cannot stand in.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import subprocess

SQL = """
WITH review AS (
 SELECT a.*, 'operator-review:' || a.id || ':' || left(a.action_hash, 32) AS write_key
 FROM pellier.approvals a WHERE a.id = :'review_id'::bigint
), proposal AS (
 SELECT m.session_id, m.metadata->>'turn_id' AS turn_id, item AS proposed_action
   FROM review a
   JOIN pellier.messages m ON m.metadata->>'turn_id' = a.source_turn_id
   JOIN pellier.conversations c ON c.session_id = m.session_id
  CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(m.metadata->'artifact'->'proposedActions') = 'array'
         THEN m.metadata->'artifact'->'proposedActions' ELSE '[]'::jsonb END
  ) AS item
  WHERE m.role = 'assistant' AND c.agent_name = 'operator_concierge'
    AND c.metadata->>'customer_id' = 'CUST-JESSICA'
    AND item->>'reviewId' = a.id::text
    AND item->>'actionHash' = a.action_hash
), writes AS (
 SELECT w.* FROM pellier.write_operations w JOIN review a ON w.idempotency_key=a.write_key
)
SELECT jsonb_build_object(
 'review', (SELECT to_jsonb(a) FROM review a),
 'proposals', (SELECT coalesce(jsonb_agg(to_jsonb(p)), '[]'::jsonb) FROM proposal p),
 'receipts', (SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.receipt_id),'[]'::jsonb)
   FROM pellier.execution_receipts e JOIN review a ON e.review_id=a.id),
 'toolCalls', (SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb)
   FROM pellier.tool_audit t JOIN review a ON t.args->>'idempotency_key'=a.write_key),
 'writes', (SELECT coalesce(jsonb_agg(to_jsonb(w)),'[]'::jsonb) FROM writes w),
 'returns', (SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb)
   FROM pellier.returns r JOIN writes w ON r.id::text=w.result->>'return_id')
);
"""


def _proposal_lineage(review: dict, proposals: list, source_turn: str) -> bool:
    """The review's own source turn saved an artifact proposing this review."""
    stored = str(review.get('source_turn_id') or '')
    if not stored.startswith('turn-') or len(proposals) != 1:
        return False
    if source_turn and source_turn != stored:
        return False
    proposal = proposals[0]
    action = proposal.get('proposed_action') or {}
    return (proposal.get('turn_id') == stored
            and str(action.get('reviewId')) == str(review.get('id'))
            and action.get('actionHash') == review.get('action_hash'))


def assess(observed: dict, *, phase: str, source_turn: str = '', baseline: dict | None = None) -> dict:
    review = observed.get('review') or {}
    writes, receipts = observed.get('writes') or [], observed.get('receipts') or []
    calls, returns = observed.get('toolCalls') or [], observed.get('returns') or []
    checks = {
        'jessicaReturn': review.get('customer_id') == 'CUST-JESSICA'
            and review.get('tool') == 'initiate_return'
            and (review.get('args') or {}).get('customer_id') == 'CUST-JESSICA',
        'proposalLineage': _proposal_lineage(review, observed.get('proposals') or [], source_turn),
        'hasActionHash': bool(re.fullmatch(r'[0-9a-f]{64}', str(review.get('action_hash') or ''))),
    }
    if phase == 'proposed':
        checks['pendingWithoutEffects'] = (review.get('status') == 'pending'
            and not review.get('decided_by') and not review.get('execution_turn_id')
            and not writes and not receipts and not calls and not returns)
    else:
        prior = (baseline or {}).get('observed', {}).get('review') or {}
        checks['sameReviewedTerms'] = bool(baseline and baseline.get('passed') is True
            and baseline.get('phase') == 'proposed') and all(
                review.get(key) == prior.get(key) for key in
                ('id', 'source_turn_id', 'action_hash', 'args', 'write_key'))
        checks['humanConfirmed'] = review.get('status') == 'approved' and bool(review.get('decided_by'))
        if phase == 'confirmed':
            checks['confirmationIsNotExecution'] = not (writes or receipts or calls or returns or review.get('execution_turn_id'))
        else:
            key = review.get('write_key')
            checks['governedExecution'] = bool(review.get('execution_turn_id')) and bool(receipts) and all(
                e.get('review_id') == review.get('id') and e.get('tool') == 'initiate_return'
                and bool(e.get('customer_subject'))
                and e.get('execution_turn_id') == review.get('execution_turn_id')
                and e.get('actor_principal') == review.get('decided_by')
                and e.get('idempotency_key') == key and e.get('rail') == 'gateway-mcp'
                for e in receipts)
            # Keep failed attempts visible. A later retry may succeed with the
            # same review/key; only the final recorded attempt claims success.
            latest = receipts[-1] if receipts else {}
            checks['latestAttemptSucceeded'] = (latest.get('gateway_mode') == 'ENFORCE'
                and latest.get('policy_outcome') == 'ALLOW'
                and latest.get('aurora_outcome') == 'PERMITTED')
            checks['toolExecuted'] = bool(calls) and all(
                c.get('tool') == 'initiate_return' and c.get('caller') == 'gateway'
                and c.get('args', {}).get('idempotency_key') == key
                and c.get('args', {}).get('customer_id') == 'CUST-JESSICA'
                and str(c.get('args', {}).get('product_id')) == str(review.get('args', {}).get('product_id'))
                and c.get('args', {}).get('reason') == review.get('args', {}).get('reason')
                for c in calls)
            checks['oneMatchingEffect'] = (len(writes) == len(returns) == 1
                and writes[0].get('completed_at') is not None
                and writes[0].get('idempotency_key') == key
                and writes[0].get('operation') == 'initiate_return'
                and writes[0].get('result', {}).get('status') == 'success'
                and str(writes[0].get('result', {}).get('return_id')) == str(returns[0].get('id'))
                and returns[0].get('customer_id') == 'CUST-JESSICA'
                and str(returns[0].get('product_id')) == str(review.get('args', {}).get('product_id'))
                and returns[0].get('reason') == review.get('args', {}).get('reason'))
    return {'phase': phase, 'sourceTurnId': review.get('source_turn_id'), 'observed': observed,
            'assertions': checks, 'passed': all(value is True for value in checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-id', required=True, type=int)
    parser.add_argument('--source-turn', default='',
                        help='Optional cross-check; the checker derives the turn from the review')
    parser.add_argument('--phase', required=True, choices=('proposed', 'confirmed', 'executed'))
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--json', required=True, type=Path)
    args = parser.parse_args()
    if args.review_id < 1:
        parser.error('Copy the review ID from the review page address: /operator/reviews/<id>')
    if args.source_turn and not args.source_turn.startswith('turn-'):
        parser.error('--source-turn must be the originating turn-... ID, or omitted')
    if args.phase != 'proposed' and args.baseline is None:
        parser.error('Use the successful proposed-phase snapshot as --baseline')
    result = subprocess.run(['psql', '-X', '-At', '-v', 'ON_ERROR_STOP=1',
        '-v', f'review_id={args.review_id}'], input=SQL, text=True, capture_output=True, check=True)
    observed = json.loads(result.stdout)
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    report = assess(observed, phase=args.phase, source_turn=args.source_turn, baseline=baseline)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps({'phase': args.phase, 'sourceTurnId': report['sourceTurnId'],
                      'passed': report['passed'], 'assertions': report['assertions']}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
