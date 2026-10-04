#!/usr/bin/env python3
"""Prepare the local-only workflow state used by the golden retail journeys.

This helper exists for a local PostgreSQL rehearsal, where AgentCore is
deliberately absent. It prepares one exact Theo review plus its append-only
shopper handoff receipt, and verifies Jessica's ticket-versus-return
discrepancy. It never updates or decides an existing review, executes a
business action, or writes a policy verdict, return, credit, audit row, or
execution receipt.

Dry run by default::

    python3 scripts/seed_local_golden_journeys.py
    python3 scripts/seed_local_golden_journeys.py --apply

The target is restricted to a loopback PostgreSQL host and a database whose
name ends in ``_dev``. This script cannot be pointed at Aurora.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from typing import Any, Dict, List

LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})
SOURCE_TURN_ID = "turn-10ca1a5eed8d4a84a1d0cce58a9beef1"
THEO_ARGS: Dict[str, Any] = {
    "customer_id": "CUST-THEO",
    "product_id": 37,
    "reason": "damaged",
}


def write_request_hash(operation: str, arguments: Dict[str, Any]) -> str:
    """Mirror the canonical business-logic hash without importing app config."""
    payload = json.dumps(
        {"operation": operation, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_local_target(host: str, database: str) -> None:
    """Refuse every remote host and every non-development database name."""
    if host not in LOCAL_HOSTS:
        raise SystemExit(
            f"Refusing non-loopback PostgreSQL host {host!r}; "
            "this helper is local-only."
        )
    if not re.fullmatch(r"[A-Za-z0-9_]+_dev", database):
        raise SystemExit(
            f"Refusing database {database!r}; local journey databases must end in _dev."
        )


def _psql_command(args: argparse.Namespace, sql: str) -> List[str]:
    command = [
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
        "-d",
        args.database,
    ]
    if args.host:
        command.extend(["-h", args.host])
    if args.port:
        command.extend(["-p", str(args.port)])
    if args.user:
        command.extend(["-U", args.user])
    command.extend(["-c", sql])
    return command


def _run(args: argparse.Namespace, sql: str) -> int:
    completed = subprocess.run(_psql_command(args, sql), check=False)
    return completed.returncode


def survey_sql() -> str:
    return f"""
SELECT
    'theo_order' AS check_name,
    COUNT(*)::text AS value
  FROM pellier.orders
 WHERE customer_id = 'CUST-THEO' AND product_id = '37'
UNION ALL
SELECT
    'theo_pending_review',
    COUNT(*)::text
  FROM pellier.approvals
 WHERE source_turn_id = '{SOURCE_TURN_ID}' AND status = 'pending'
UNION ALL
SELECT
    'theo_handoff_receipt',
    COUNT(*)::text
  FROM pellier.governed_turn_receipts gtr
  JOIN pellier.approvals a ON a.source_turn_id = gtr.turn_id
 WHERE a.source_turn_id = '{SOURCE_TURN_ID}'
   AND gtr.handoff_context->>'customerId' = 'CUST-THEO'
   AND (gtr.handoff_context->'proposal'->>'reviewId')::bigint = a.id
   AND gtr.handoff_context->'proposal'->>'actionHash' = a.action_hash
UNION ALL
SELECT
    'jessica_support_assertions',
    COUNT(*)::text
  FROM pellier.support_tickets
 WHERE customer_id = 'CUST-JESSICA'
   AND lower(subject || ' ' || last_note) LIKE '%return%'
UNION ALL
SELECT
    'jessica_authoritative_returns',
    COUNT(*)::text
  FROM pellier.returns
 WHERE customer_id = 'CUST-JESSICA'
ORDER BY check_name;
"""


def seed_sql() -> str:
    action_hash = write_request_hash("initiate_return", THEO_ARGS)
    arguments = json.dumps(THEO_ARGS, sort_keys=True, separators=(",", ":"))
    recommendation = json.dumps(
        {
            "primaryAction": "initiate_return",
            "rationale": (
                "Theo owns the Wabi-Sabi Bowl and stated that it arrived damaged. "
                "A person must confirm these exact terms before managed execution."
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"""
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pellier.orders o
          JOIN pellier.product_catalog p ON p."productId" = o.product_id
         WHERE o.customer_id = 'CUST-THEO'
           AND o.product_id = '37'
           AND p.name = 'Wabi-Sabi Bowl'
    ) THEN
        RAISE EXCEPTION 'Canonical Theo Wabi-Sabi Bowl order is missing';
    END IF;
END $$;

INSERT INTO pellier.approvals
    (customer_id, tool, args, status, source_turn_id, order_id,
     issue, recommendation, action_hash)
SELECT
    'CUST-THEO',
    'initiate_return',
    '{arguments}'::jsonb,
    'pending',
    '{SOURCE_TURN_ID}',
    o.id,
    'Wabi-Sabi Bowl arrived chipped',
    '{recommendation}'::jsonb,
    '{action_hash}'
  FROM pellier.orders o
 WHERE o.customer_id = 'CUST-THEO'
   AND o.product_id = '37'
   -- Idempotent across the whole lifecycle, not just while the row is live.
   -- `approvals_open_per_action_idx` is a PARTIAL unique index scoped to
   -- live reviews (`status IN ('pending', 'approved')`), so the ON CONFLICT
   -- below stops a second row only until the first one is declined. After that
   -- the seeded review leaves the index, and the next seed run would insert
   -- another copy: a workshop box that had been reseeded twice showed two
   -- identical decided Theo returns in the Action Queue's history, back when
   -- the index covered pending rows only. The source turn is this row's identity anyway --
   -- the block directly below calls it "the canonical Theo review" and reads
   -- it back by exactly this value.
   AND NOT EXISTS (
         SELECT 1
           FROM pellier.approvals a
          WHERE a.source_turn_id = '{SOURCE_TURN_ID}'
       )
 ORDER BY o.placed_at DESC, o.id DESC
 LIMIT 1
ON CONFLICT (customer_id, tool, action_hash) WHERE status IN ('pending', 'approved')
DO NOTHING;

DO $$
DECLARE
    v_review RECORD;
    v_existing JSONB;
    v_handoff JSONB;
BEGIN
    SELECT id, customer_id, tool, args, status, source_turn_id,
           execution_turn_id, action_hash
      INTO v_review
      FROM pellier.approvals
     WHERE source_turn_id = '{SOURCE_TURN_ID}';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Canonical Theo review is missing';
    END IF;
    IF v_review.status <> 'pending' OR v_review.execution_turn_id IS NOT NULL THEN
        RAISE EXCEPTION
            'Canonical Theo review was decided or executed; refusing to alter lineage';
    END IF;
    IF v_review.customer_id <> 'CUST-THEO'
       OR v_review.tool <> 'initiate_return'
       OR v_review.args <> '{arguments}'::jsonb
       OR v_review.action_hash <> '{action_hash}' THEN
        RAISE EXCEPTION 'Canonical Theo review does not match the golden journey';
    END IF;

    SELECT handoff_context
      INTO v_existing
      FROM pellier.governed_turn_receipts
     WHERE turn_id = v_review.source_turn_id;

    IF FOUND THEN
        IF v_existing = '{{}}'::jsonb THEN
            RAISE EXCEPTION
                'Existing immutable turn receipt has no handoff; reset local development data instead of rewriting it';
        END IF;
        IF v_existing->>'customerId' <> v_review.customer_id
           OR (v_existing->'proposal'->>'reviewId')::bigint <> v_review.id
           OR v_existing->'proposal'->>'actionHash' <> v_review.action_hash THEN
            RAISE EXCEPTION 'Existing shopper handoff does not match the review';
        END IF;
        RETURN;
    END IF;

    v_handoff := jsonb_build_object(
        'schemaVersion', '1',
        'trust', 'UNTRUSTED_SHOPPER_CONTEXT',
        'checkpoint', 'WAITING_FOR_HUMAN',
        'customerId', v_review.customer_id,
        'source', jsonb_build_object(
            'sessionId', 'local-golden-theo',
            'turnId', v_review.source_turn_id
        ),
        'shopperRequest',
            'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
        'transcriptExcerpt', jsonb_build_array(
            jsonb_build_object(
                'role', 'user',
                'content',
                    'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
                'truncated', 'false'
            )
        ),
        'assistantResponseExcerpt',
            'I prepared the exact return request for a person to review.',
        'routing', jsonb_build_object(
            'specialist', 'customer_service',
            'tools', jsonb_build_array('get_return_policy', 'initiate_return')
        ),
        'proposal', jsonb_build_object(
            'reviewId', v_review.id,
            'action', v_review.tool,
            'actionHash', v_review.action_hash
        ),
        'evidenceRefs', jsonb_build_array(
            jsonb_build_object(
                'kind', 'governed_turn_receipt',
                'id', v_review.source_turn_id
            ),
            jsonb_build_object('kind', 'approval', 'id', v_review.id)
        )
    );

    INSERT INTO pellier.governed_turn_receipts (
        turn_id, session_id, principal_sub, principal_verified, rail,
        model_config, retrieval_receipt_id, citations, tool_audit_ids,
        policy_events, trace, handoff_context, terminal_outcome,
        terminal_status, latency_ms
    ) VALUES (
        v_review.source_turn_id,
        'local-golden-theo',
        NULL,
        FALSE,
        'local-postgresql',
        '{{}}'::jsonb,
        NULL,
        '[]'::jsonb,
        '[]'::jsonb,
        '[]'::jsonb,
        '{{"source":"local-golden-journey","managed":false}}'::jsonb,
        v_handoff,
        '{{"kind":"local-rehearsal","managedProof":false}}'::jsonb,
        'complete',
        0
    );
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pellier.approvals
         WHERE source_turn_id = '{SOURCE_TURN_ID}'
           AND (status <> 'pending' OR execution_turn_id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION
            'Local golden journey changed the review state';
    END IF;
END $$;

COMMIT;
{survey_sql()}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="", help="Loopback host; empty uses local socket")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="pellier_dev")
    parser.add_argument("--user", default="")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Prepare the pending review and immutable handoff. Without this flag, only survey.",
    )
    args = parser.parse_args()

    require_local_target(args.host, args.database)

    if args.apply:
        print(
            "Preparing local Theo review and immutable handoff. "
            "No business action will execute."
        )
        return _run(args, seed_sql())

    print("Dry run. Current local journey state:")
    rc = _run(args, survey_sql())
    if rc == 0:
        print("\nRe-run with --apply to prepare Theo's review and handoff.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
