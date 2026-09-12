"""Order-bound replacement proposals and current Aurora recovery evidence.

Preparation writes only an existing operator review. Execution goes through the
existing managed Gateway rail, never from this read/preparation service.
"""
from __future__ import annotations

from typing import Any

from services import operator_review as review

ACTION = "replace_damaged_item"
DISPOSITION = "inspection_required"


async def prepare(
    db: Any, *, customer_id: str, order_id: int, quantity: int,
    issue: str, operator_sub: str,
) -> int:
    issue = issue.strip()
    if not issue:
        raise review.ReviewError("replacement_issue_required", 422)
    # Presence is capability evidence for this additive migration, not permission
    # to execute the Gateway tool.
    ready = await db.fetch_one(
        "SELECT to_regclass('pellier.replacements') IS NOT NULL AS available"
    )
    if not ready or not ready["available"]:
        raise review.ReviewError("replacement_not_installed", 503)
    order = await db.fetch_one(
        """SELECT o.id, o.product_id, o.quantity, p.name,
                  COALESCE((SELECT sum(r.quantity) FROM pellier.returns r
                     WHERE r.customer_id = o.customer_id AND r.product_id = o.product_id
                       AND (r.order_id = o.id OR r.order_id IS NULL)
                       AND r.status <> 'rejected'), 0) AS returned
             FROM pellier.orders o JOIN pellier.product_catalog p ON p."productId" = o.product_id
            WHERE o.id = %s AND o.customer_id = %s""",
        order_id, customer_id,
    )
    if not order:
        raise review.ReviewError("replacement_order_not_found", 404)
    if quantity < 1 or quantity + int(order["returned"]) > int(order["quantity"]):
        raise review.ReviewError("replacement_quantity_exceeds_order", 409)
    material = {
        "customer_id": customer_id, "order_id": order_id,
        "product_id": int(order["product_id"]), "quantity": quantity,
        "reason": "damaged", "disposition": DISPOSITION,
    }
    review_id = await review.propose_review(
        db, action=ACTION, args=material, source_turn_id=None, issue=issue,
        requested_by_sub=operator_sub, requester_kind=review.REQUESTER_OPERATOR,
        recommendation={
            "primaryAction": ACTION,
            "rationale": (
                f"The operator proposes replacing {quantity} unit(s) of {order['name']} "
                f"from order #{order_id} after reported damage. Stock is checked again "
                "when the approved action executes. The damaged piece requires inspection."
            ),
        },
    )
    if review_id is None:
        raise review.ReviewError("replacement_prepare_failed", 503)
    return review_id


async def read_replacements(db: Any, customer_id: str, replacement_id: str | None = None) -> dict[str, Any]:
    ready = await db.fetch_one(
        "SELECT to_regclass('pellier.replacements') IS NOT NULL AS available"
    )
    if not ready or not ready["available"]:
        return {"available": False, "replacements": []}
    rows = await db.fetch_all(
        """SELECT r.*, p.name AS product_name, o.event_id AS outbox_id,
                  o.attempts AS outbox_attempts, o.published_at AS outbox_published,
                  COALESCE((SELECT jsonb_agg(jsonb_build_object(
                      'type', e.event_type, 'at', e.created_at, 'details', e.details)
                      ORDER BY e.event_id)
                    FROM pellier.replacement_events e
                    WHERE e.replacement_id = r.replacement_id), '[]'::jsonb) AS events
             FROM pellier.replacements r
             JOIN pellier.product_catalog p ON p."productId" = r.product_id
             LEFT JOIN pellier.replacement_outbox o USING (replacement_id)
            WHERE r.customer_id = %s AND (%s::uuid IS NULL OR r.replacement_id = %s::uuid)
            ORDER BY r.created_at DESC LIMIT 50""",
        customer_id, replacement_id, replacement_id,
    )
    def iso(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else str(value) if value else None

    return {
        "available": True,
        "replacements": [{
            "replacementId": str(r["replacement_id"]), "reviewId": int(r["review_id"]),
            "orderId": int(r["order_id"]), "productId": str(r["product_id"]),
            "productName": r["product_name"], "quantity": int(r["quantity"]),
            "disposition": r["disposition"], "state": r["status"],
            "providerOperationId": r["provider_operation_id"],
            "executionArn": r["workflow_execution_arn"],
            "idempotencyKey": r["idempotency_key"], "approvalHash": r["request_hash"],
            "outbox": {
                "eventId": str(r["outbox_id"]), "attempts": int(r["outbox_attempts"]),
                "publishedAt": iso(r["outbox_published"]),
            } if r["outbox_id"] else None,
            "createdAt": iso(r["created_at"]), "updatedAt": iso(r["updated_at"]),
            "events": r["events"], "provider": "workshop-simulator",
        } for r in rows],
    }
