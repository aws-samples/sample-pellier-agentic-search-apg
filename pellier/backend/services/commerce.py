"""Proof-carrying storefront commerce.

The agent or UI may prepare a cart, but this service owns the execution
boundary: Cognito principal, server-priced quote, explicit consent grant,
inventory reservation, payment state, and an immutable Aurora receipt.

The included payment adapter is deliberately a sandbox. It models provider
state transitions without claiming to process cards or move money.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence


MONEY = Decimal("0.01")
TAX_RATE = Decimal("0.0825")
FREE_SHIPPING_THRESHOLD = Decimal("150.00")
STANDARD_SHIPPING = Decimal("12.00")
QUOTE_TTL = timedelta(minutes=10)
CONSENT_TTL = timedelta(minutes=5)
TERMINAL_ORDER_STATUSES = {"paid", "payment_declined", "payment_failed"}


class CommerceError(Exception):
    """A stable commerce failure code plus its intended HTTP status."""

    def __init__(self, code: str, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PaymentResult:
    status: str
    event_type: str
    provider_ref: str
    failure_code: str | None = None


class SandboxPaymentAdapter:
    """Deterministic payment-state adapter that never moves real money."""

    provider = "pellier-sandbox"
    mode = "sandbox"

    async def settle(
        self,
        *,
        order_id: uuid.UUID,
        amount: Decimal,
        currency: str,
    ) -> PaymentResult:
        configured = os.environ.get(
            "PELLIER_SANDBOX_PAYMENT_OUTCOME", "settled"
        ).strip().lower()
        provider_ref = "sbx_" + hashlib.sha256(
            f"{order_id}:{amount}:{currency}".encode("utf-8")
        ).hexdigest()[:20]
        if configured == "settled":
            return PaymentResult("settled", "payment.settled", provider_ref)
        if configured == "declined":
            return PaymentResult(
                "declined",
                "payment.declined",
                provider_ref,
                "sandbox_declined",
            )
        return PaymentResult(
            "failed",
            "payment.failed",
            provider_ref,
            "sandbox_adapter_misconfigured",
        )


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_value(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class CommerceService:
    def __init__(
        self,
        db_service: Any,
        payment_adapter: SandboxPaymentAdapter | None = None,
    ) -> None:
        self.db = db_service
        self.payment = payment_adapter or SandboxPaymentAdapter()

    async def create_quote(
        self,
        *,
        principal_sub: str,
        lines: Sequence[Mapping[str, int]],
        session_id: str | None = None,
        turn_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        created_at = now or datetime.now(timezone.utc)
        quantities: dict[int, int] = {}
        for line in lines:
            product_id = int(line["product_id"])
            quantity = int(line["quantity"])
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        if not quantities:
            raise CommerceError("invalid_request", 422)
        if len(quantities) > 10 or any(q < 1 or q > 20 for q in quantities.values()):
            raise CommerceError("invalid_request", 422)

        product_ids = [str(product_id) for product_id in sorted(quantities)]
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT pc."productId" AS product_id,
                           pc.name,
                           pc."imgUrl" AS image_url,
                           pc.price,
                           pc.quantity AS catalog_quantity,
                           COALESCE(sum(wi.quantity), 0)::int
                               AS available_quantity
                      FROM pellier.product_catalog pc
                      LEFT JOIN pellier.warehouse_inventory wi
                        ON wi.product_id = pc."productId"
                     WHERE pc."productId" = ANY(%s)
                     GROUP BY pc."productId", pc.name, pc."imgUrl",
                              pc.price, pc.quantity
                     ORDER BY pc."productId"
                    """,
                    (product_ids,),
                )
                rows = list(await cur.fetchall())
                by_id = {str(row["product_id"]): row for row in rows}
                if set(by_id) != set(product_ids):
                    raise CommerceError("product_unavailable")

                quote_lines: list[dict[str, Any]] = []
                for product_id in product_ids:
                    row = by_id[product_id]
                    quantity = quantities[int(product_id)]
                    available = min(
                        int(row["catalog_quantity"]),
                        int(row["available_quantity"]),
                    )
                    if available < quantity:
                        raise CommerceError("inventory_unavailable")
                    unit_price = _money(row["price"])
                    quote_lines.append(
                        {
                            "product_id": product_id,
                            "product_name": str(row["name"]),
                            "image_url": row.get("image_url"),
                            "unit_price": unit_price,
                            "quantity": quantity,
                            "available_quantity": available,
                            "line_total": _money(unit_price * quantity),
                        }
                    )

                subtotal = _money(sum(line["line_total"] for line in quote_lines))
                shipping = (
                    Decimal("0.00")
                    if subtotal >= FREE_SHIPPING_THRESHOLD
                    else STANDARD_SHIPPING
                )
                tax = _money(subtotal * TAX_RATE)
                total = _money(subtotal + shipping + tax)
                quote_id = uuid.uuid4()
                expires_at = created_at + QUOTE_TTL
                rules = {
                    "policy": "pellier-commerce-v1",
                    "currency": "USD",
                    "taxRate": str(TAX_RATE),
                    "freeShippingThreshold": f"{FREE_SHIPPING_THRESHOLD:.2f}",
                    "standardShipping": f"{STANDARD_SHIPPING:.2f}",
                    "paymentProvider": self.payment.provider,
                    "paymentMode": self.payment.mode,
                }
                hash_payload = {
                    "quoteId": quote_id,
                    "principalSub": principal_sub,
                    "currency": "USD",
                    "lines": quote_lines,
                    "subtotal": subtotal,
                    "shipping": shipping,
                    "tax": tax,
                    "total": total,
                    "rules": rules,
                    "expiresAt": expires_at,
                }
                quote_hash = _canonical_hash(hash_payload)

                await cur.execute(
                    """
                    INSERT INTO pellier.commerce_quotes (
                        quote_id, principal_sub, session_id, turn_id,
                        currency, subtotal, shipping, tax, total,
                        rule_snapshot, quote_hash, expires_at, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, 'USD', %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s
                    )
                    """,
                    (
                        quote_id,
                        principal_sub,
                        session_id,
                        turn_id,
                        subtotal,
                        shipping,
                        tax,
                        total,
                        json.dumps(rules),
                        quote_hash,
                        expires_at,
                        created_at,
                    ),
                )
                for line in quote_lines:
                    await cur.execute(
                        """
                        INSERT INTO pellier.commerce_quote_lines (
                            quote_id, product_id, product_name, image_url,
                            unit_price, quantity, available_quantity, line_total
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            quote_id,
                            line["product_id"],
                            line["product_name"],
                            line["image_url"],
                            line["unit_price"],
                            line["quantity"],
                            line["available_quantity"],
                            line["line_total"],
                        ),
                    )
                await conn.commit()

        return {
            "quoteId": str(quote_id),
            "quoteHash": quote_hash,
            "status": "open",
            "currency": "USD",
            "lines": [
                {
                    "productId": int(line["product_id"]),
                    "name": line["product_name"],
                    "imageUrl": line["image_url"],
                    "unitPrice": f"{line['unit_price']:.2f}",
                    "quantity": line["quantity"],
                    "lineTotal": f"{line['line_total']:.2f}",
                }
                for line in quote_lines
            ],
            "amounts": {
                "subtotal": f"{subtotal:.2f}",
                "shipping": f"{shipping:.2f}",
                "tax": f"{tax:.2f}",
                "total": f"{total:.2f}",
            },
            "rules": rules,
            "expiresAt": expires_at.isoformat(),
        }

    async def confirm_quote(
        self,
        *,
        principal_sub: str,
        quote_id: uuid.UUID,
        quote_hash: str,
        acknowledged: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not acknowledged:
            raise CommerceError("confirmation_required", 422)
        confirmed_at = now or datetime.now(timezone.utc)
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT *
                      FROM pellier.commerce_quotes
                     WHERE quote_id = %s
                     FOR UPDATE
                    """,
                    (quote_id,),
                )
                quote = await cur.fetchone()
                if not quote or quote["principal_sub"] != principal_sub:
                    raise CommerceError("quote_not_found", 404)
                if quote["status"] != "open":
                    raise CommerceError("quote_unavailable")
                if quote["expires_at"] <= confirmed_at:
                    raise CommerceError("quote_expired")
                if not hmac.compare_digest(
                    str(quote["quote_hash"]).strip(), quote_hash
                ):
                    raise CommerceError("quote_changed")

                await cur.execute(
                    """
                    SELECT *
                      FROM pellier.commerce_confirmation_grants
                     WHERE quote_id = %s
                       AND principal_sub = %s
                    """,
                    (quote_id, principal_sub),
                )
                grant = await cur.fetchone()
                if grant:
                    if grant["used_at"] is not None:
                        raise CommerceError("confirmation_already_used")
                    if grant["expires_at"] <= confirmed_at:
                        raise CommerceError("confirmation_expired")
                else:
                    grant_id = uuid.uuid4()
                    expires_at = min(
                        quote["expires_at"],
                        confirmed_at + CONSENT_TTL,
                    )
                    await cur.execute(
                        """
                        INSERT INTO pellier.commerce_confirmation_grants (
                            grant_id, quote_id, principal_sub, quote_hash,
                            confirmed_total, currency, acknowledged_at,
                            expires_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            grant_id,
                            quote_id,
                            principal_sub,
                            quote["quote_hash"],
                            quote["total"],
                            quote["currency"],
                            confirmed_at,
                            expires_at,
                        ),
                    )
                    grant = await cur.fetchone()
                await conn.commit()

        return {
            "confirmationGrantId": str(grant["grant_id"]),
            "quoteId": str(grant["quote_id"]),
            "quoteHash": str(grant["quote_hash"]).strip(),
            "confirmedTotal": f"{_money(grant['confirmed_total']):.2f}",
            "currency": grant["currency"],
            "status": "granted",
            "expiresAt": _iso(grant["expires_at"]),
        }

    async def execute_order(
        self,
        *,
        principal_sub: str,
        confirmation_grant_id: uuid.UUID,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        started_at = now or datetime.now(timezone.utc)
        order = await self._existing_order(principal_sub, idempotency_key)
        if order and str(order["confirmation_grant_id"]) != str(
            confirmation_grant_id
        ):
            raise CommerceError("idempotency_key_reused")
        if order and order["status"] in TERMINAL_ORDER_STATUSES:
            return await self.get_receipt(
                principal_sub=principal_sub,
                order_id=order["order_id"],
            )

        if order is None:
            order = await self._prepare_order(
                principal_sub=principal_sub,
                confirmation_grant_id=confirmation_grant_id,
                idempotency_key=idempotency_key,
                now=started_at,
            )

        payment_result = await self.payment.settle(
            order_id=order["order_id"],
            amount=_money(order["total"]),
            currency=order["currency"],
        )
        await self._finalize_order(
            principal_sub=principal_sub,
            order_id=order["order_id"],
            result=payment_result,
            now=started_at,
        )
        return await self.get_receipt(
            principal_sub=principal_sub,
            order_id=order["order_id"],
        )

    async def _existing_order(
        self,
        principal_sub: str,
        idempotency_key: str,
    ) -> Mapping[str, Any] | None:
        return await self.db.fetch_one(
            """
            SELECT *
              FROM pellier.commerce_orders
             WHERE principal_sub = %s
               AND idempotency_key = %s
            """,
            principal_sub,
            idempotency_key,
        )

    async def _prepare_order(
        self,
        *,
        principal_sub: str,
        confirmation_grant_id: uuid.UUID,
        idempotency_key: str,
        now: datetime,
    ) -> Mapping[str, Any]:
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT g.*, q.session_id, q.turn_id, q.subtotal,
                           q.shipping, q.tax, q.total, q.currency,
                           q.status AS quote_status, q.expires_at AS quote_expires_at,
                           q.rule_snapshot
                      FROM pellier.commerce_confirmation_grants g
                      JOIN pellier.commerce_quotes q ON q.quote_id = g.quote_id
                     WHERE g.grant_id = %s
                     FOR UPDATE OF g, q
                    """,
                    (confirmation_grant_id,),
                )
                grant = await cur.fetchone()
                if not grant or grant["principal_sub"] != principal_sub:
                    raise CommerceError("confirmation_not_found", 404)
                if grant["used_at"] is not None:
                    if grant["used_order_id"]:
                        await cur.execute(
                            """
                            SELECT *
                              FROM pellier.commerce_orders
                             WHERE order_id = %s
                               AND principal_sub = %s
                               AND idempotency_key = %s
                            """,
                            (
                                grant["used_order_id"],
                                principal_sub,
                                idempotency_key,
                            ),
                        )
                        replay = await cur.fetchone()
                        if replay:
                            return replay
                    raise CommerceError("confirmation_already_used")
                if grant["expires_at"] <= now:
                    raise CommerceError("confirmation_expired")
                if grant["quote_status"] != "open":
                    raise CommerceError("quote_unavailable")
                if grant["quote_expires_at"] <= now:
                    raise CommerceError("quote_expired")

                await cur.execute(
                    """
                    SELECT *
                      FROM pellier.commerce_quote_lines
                     WHERE quote_id = %s
                     ORDER BY product_id
                    """,
                    (grant["quote_id"],),
                )
                lines = list(await cur.fetchall())
                product_ids = [line["product_id"] for line in lines]

                await cur.execute(
                    """
                    SELECT "productId" AS product_id, price, quantity
                      FROM pellier.product_catalog
                     WHERE "productId" = ANY(%s)
                     FOR UPDATE
                    """,
                    (product_ids,),
                )
                catalog = {
                    row["product_id"]: row for row in await cur.fetchall()
                }
                for line in lines:
                    current = catalog.get(line["product_id"])
                    if current is None:
                        raise CommerceError("product_unavailable")
                    if _money(current["price"]) != _money(line["unit_price"]):
                        raise CommerceError("quote_changed")
                    if int(current["quantity"]) < int(line["quantity"]):
                        raise CommerceError("inventory_unavailable")

                await cur.execute(
                    """
                    SELECT product_id, warehouse_id, quantity
                      FROM pellier.warehouse_inventory
                     WHERE product_id = ANY(%s)
                     ORDER BY product_id, warehouse_id
                     FOR UPDATE
                    """,
                    (product_ids,),
                )
                warehouse_rows = list(await cur.fetchall())
                by_product: dict[str, list[Mapping[str, Any]]] = {}
                for row in warehouse_rows:
                    by_product.setdefault(row["product_id"], []).append(row)
                for line in lines:
                    available = sum(
                        int(row["quantity"])
                        for row in by_product.get(line["product_id"], [])
                    )
                    if available < int(line["quantity"]):
                        raise CommerceError("inventory_unavailable")

                order_id = uuid.uuid4()
                order_number = f"PEL-{str(order_id).split('-')[0].upper()}"
                attempt_id = uuid.uuid4()
                await cur.execute(
                    """
                    INSERT INTO pellier.commerce_orders (
                        order_id, order_number, principal_sub, quote_id,
                        confirmation_grant_id, idempotency_key, session_id,
                        turn_id, currency, subtotal, shipping, tax, total,
                        status, payment_status, created_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, 'payment_pending', 'pending', %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        order_id,
                        order_number,
                        principal_sub,
                        grant["quote_id"],
                        confirmation_grant_id,
                        idempotency_key,
                        grant["session_id"],
                        grant["turn_id"],
                        grant["currency"],
                        grant["subtotal"],
                        grant["shipping"],
                        grant["tax"],
                        grant["total"],
                        now,
                        now,
                    ),
                )
                order = await cur.fetchone()

                for line in lines:
                    await cur.execute(
                        """
                        INSERT INTO pellier.commerce_order_lines (
                            order_id, product_id, product_name, image_url,
                            unit_price, quantity, line_total
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            line["product_id"],
                            line["product_name"],
                            line["image_url"],
                            line["unit_price"],
                            line["quantity"],
                            line["line_total"],
                        ),
                    )
                    remaining = int(line["quantity"])
                    for warehouse in by_product[line["product_id"]]:
                        allocation = min(remaining, int(warehouse["quantity"]))
                        if allocation == 0:
                            continue
                        movement_key = (
                            f"commerce:{order_id}:reserve:"
                            f"{line['product_id']}:{warehouse['warehouse_id']}"
                        )
                        await self._set_inventory_context(
                            cur,
                            reason="reservation",
                            idempotency_key=movement_key,
                            principal_sub=principal_sub,
                        )
                        await cur.execute(
                            """
                            UPDATE pellier.warehouse_inventory
                               SET quantity = quantity - %s,
                                   updated_at = %s
                             WHERE warehouse_id = %s
                               AND product_id = %s
                               AND quantity >= %s
                            """,
                            (
                                allocation,
                                now,
                                warehouse["warehouse_id"],
                                line["product_id"],
                                allocation,
                            ),
                        )
                        reservation_id = uuid.uuid4()
                        await cur.execute(
                            """
                            INSERT INTO pellier.commerce_inventory_reservations (
                                reservation_id, order_id, product_id,
                                warehouse_id, quantity, status,
                                created_at, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, 'reserved', %s, %s)
                            """,
                            (
                                reservation_id,
                                order_id,
                                line["product_id"],
                                warehouse["warehouse_id"],
                                allocation,
                                now,
                                now,
                            ),
                        )
                        remaining -= allocation
                        if remaining == 0:
                            break
                    await cur.execute(
                        """
                        UPDATE pellier.product_catalog
                           SET quantity = quantity - %s
                         WHERE "productId" = %s
                           AND quantity >= %s
                        """,
                        (
                            line["quantity"],
                            line["product_id"],
                            line["quantity"],
                        ),
                    )

                await cur.execute(
                    """
                    INSERT INTO pellier.commerce_payment_attempts (
                        attempt_id, order_id, provider, mode, amount,
                        currency, status, created_at, updated_at
                    )
                    VALUES (
                        %s, %s, 'pellier-sandbox', 'sandbox',
                        %s, %s, 'pending', %s, %s
                    )
                    """,
                    (
                        attempt_id,
                        order_id,
                        grant["total"],
                        grant["currency"],
                        now,
                        now,
                    ),
                )
                await cur.execute(
                    """
                    UPDATE pellier.commerce_confirmation_grants
                       SET used_at = %s, used_order_id = %s
                     WHERE grant_id = %s
                    """,
                    (now, order_id, confirmation_grant_id),
                )
                await cur.execute(
                    """
                    UPDATE pellier.commerce_quotes
                       SET status = 'consumed'
                     WHERE quote_id = %s
                    """,
                    (grant["quote_id"],),
                )
                await self._insert_outbox(
                    cur,
                    order_id=order_id,
                    event_type="commerce.payment.requested",
                    payload={
                        "orderId": str(order_id),
                        "paymentAttemptId": str(attempt_id),
                        "amount": f"{_money(grant['total']):.2f}",
                        "currency": grant["currency"],
                        "provider": self.payment.provider,
                        "mode": self.payment.mode,
                    },
                )
                await conn.commit()
                return order

    async def _finalize_order(
        self,
        *,
        principal_sub: str,
        order_id: uuid.UUID,
        result: PaymentResult,
        now: datetime,
    ) -> None:
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT o.*, p.attempt_id
                      FROM pellier.commerce_orders o
                      JOIN pellier.commerce_payment_attempts p
                        ON p.order_id = o.order_id
                     WHERE o.order_id = %s
                       AND o.principal_sub = %s
                     FOR UPDATE OF o, p
                    """,
                    (order_id, principal_sub),
                )
                order = await cur.fetchone()
                if not order:
                    raise CommerceError("order_not_found", 404)
                if order["status"] in TERMINAL_ORDER_STATUSES:
                    return

                event_key = f"{order_id}:{result.event_type}"
                await cur.execute(
                    """
                    INSERT INTO pellier.commerce_payment_events (
                        attempt_id, event_key, event_type, payload, occurred_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (event_key) DO NOTHING
                    """,
                    (
                        order["attempt_id"],
                        event_key,
                        result.event_type,
                        json.dumps(
                            {
                                "providerRef": result.provider_ref,
                                "status": result.status,
                                "failureCode": result.failure_code,
                                "mode": self.payment.mode,
                            }
                        ),
                        now,
                    ),
                )
                await cur.execute(
                    """
                    UPDATE pellier.commerce_payment_attempts
                       SET status = %s,
                           provider_ref = %s,
                           failure_code = %s,
                           updated_at = %s
                     WHERE attempt_id = %s
                    """,
                    (
                        result.status,
                        result.provider_ref,
                        result.failure_code,
                        now,
                        order["attempt_id"],
                    ),
                )

                if result.status == "settled":
                    order_status = "paid"
                    await cur.execute(
                        """
                        UPDATE pellier.commerce_inventory_reservations
                           SET status = 'captured', updated_at = %s
                         WHERE order_id = %s
                           AND status = 'reserved'
                        """,
                        (now, order_id),
                    )
                else:
                    order_status = (
                        "payment_declined"
                        if result.status == "declined"
                        else "payment_failed"
                    )
                    await self._release_reservations(
                        cur,
                        order_id=order_id,
                        principal_sub=principal_sub,
                        now=now,
                    )

                await cur.execute(
                    """
                    UPDATE pellier.commerce_orders
                       SET status = %s, payment_status = %s, updated_at = %s
                     WHERE order_id = %s
                    """,
                    (order_status, result.status, now, order_id),
                )
                await self._insert_outbox(
                    cur,
                    order_id=order_id,
                    event_type=f"commerce.{result.event_type}",
                    payload={
                        "orderId": str(order_id),
                        "paymentAttemptId": str(order["attempt_id"]),
                        "status": result.status,
                        "providerRef": result.provider_ref,
                        "mode": self.payment.mode,
                    },
                )
                await self._persist_receipt(
                    cur,
                    order_id=order_id,
                    principal_sub=principal_sub,
                    order_status=order_status,
                    now=now,
                )
                await conn.commit()

    async def _release_reservations(
        self,
        cur: Any,
        *,
        order_id: uuid.UUID,
        principal_sub: str,
        now: datetime,
    ) -> None:
        await cur.execute(
            """
            SELECT *
              FROM pellier.commerce_inventory_reservations
             WHERE order_id = %s
               AND status = 'reserved'
             ORDER BY product_id, warehouse_id
             FOR UPDATE
            """,
            (order_id,),
        )
        reservations = list(await cur.fetchall())
        released_by_product: dict[str, int] = {}
        for reservation in reservations:
            movement_key = (
                f"commerce:{order_id}:release:"
                f"{reservation['product_id']}:{reservation['warehouse_id']}"
            )
            await self._set_inventory_context(
                cur,
                reason="release",
                idempotency_key=movement_key,
                principal_sub=principal_sub,
            )
            await cur.execute(
                """
                UPDATE pellier.warehouse_inventory
                   SET quantity = quantity + %s, updated_at = %s
                 WHERE warehouse_id = %s
                   AND product_id = %s
                """,
                (
                    reservation["quantity"],
                    now,
                    reservation["warehouse_id"],
                    reservation["product_id"],
                ),
            )
            released_by_product[reservation["product_id"]] = (
                released_by_product.get(reservation["product_id"], 0)
                + int(reservation["quantity"])
            )
        for product_id, quantity in released_by_product.items():
            await cur.execute(
                """
                UPDATE pellier.product_catalog
                   SET quantity = quantity + %s
                 WHERE "productId" = %s
                """,
                (quantity, product_id),
            )
        await cur.execute(
            """
            UPDATE pellier.commerce_inventory_reservations
               SET status = 'released', updated_at = %s
             WHERE order_id = %s
               AND status = 'reserved'
            """,
            (now, order_id),
        )

    async def _persist_receipt(
        self,
        cur: Any,
        *,
        order_id: uuid.UUID,
        principal_sub: str,
        order_status: str,
        now: datetime,
    ) -> None:
        await cur.execute(
            """
            SELECT o.*, q.quote_hash, q.rule_snapshot,
                   g.acknowledged_at, p.attempt_id, p.provider,
                   p.mode, p.status AS provider_status, p.provider_ref,
                   p.failure_code
              FROM pellier.commerce_orders o
              JOIN pellier.commerce_quotes q ON q.quote_id = o.quote_id
              JOIN pellier.commerce_confirmation_grants g
                ON g.grant_id = o.confirmation_grant_id
              JOIN pellier.commerce_payment_attempts p
                ON p.order_id = o.order_id
             WHERE o.order_id = %s
            """,
            (order_id,),
        )
        row = await cur.fetchone()
        await cur.execute(
            """
            SELECT product_id, product_name, unit_price, quantity, line_total
              FROM pellier.commerce_order_lines
             WHERE order_id = %s
             ORDER BY product_id
            """,
            (order_id,),
        )
        order_lines = list(await cur.fetchall())
        await cur.execute(
            """
            SELECT reservation_id, product_id, warehouse_id, quantity, status
              FROM pellier.commerce_inventory_reservations
             WHERE order_id = %s
             ORDER BY product_id, warehouse_id
            """,
            (order_id,),
        )
        reservations = list(await cur.fetchall())
        await cur.execute(
            """
            SELECT entry_id
              FROM pellier.inventory_ledger
             WHERE idempotency_key LIKE %s
             ORDER BY entry_id
            """,
            (f"commerce:{order_id}:%",),
        )
        ledger_ids = [item["entry_id"] for item in await cur.fetchall()]
        await cur.execute(
            """
            SELECT event_id
              FROM pellier.commerce_payment_events
             WHERE attempt_id = %s
             ORDER BY event_id
            """,
            (row["attempt_id"],),
        )
        payment_event_ids = [item["event_id"] for item in await cur.fetchall()]
        await cur.execute(
            """
            SELECT event_id
              FROM pellier.commerce_outbox
             WHERE aggregate_id = %s
             ORDER BY created_at, event_id
            """,
            (order_id,),
        )
        outbox_ids = [str(item["event_id"]) for item in await cur.fetchall()]
        evidence = {
            "identity": {
                "principalSub": principal_sub,
                "verified": True,
            },
            "context": {
                "sessionId": row["session_id"],
                "turnId": row["turn_id"],
            },
            "quote": {
                "quoteId": str(row["quote_id"]),
                "quoteHash": str(row["quote_hash"]).strip(),
                "rules": _parse_json(row["rule_snapshot"]),
                "total": f"{_money(row['total']):.2f}",
                "currency": row["currency"],
            },
            "order": {
                "orderId": str(row["order_id"]),
                "orderNumber": row["order_number"],
                "lines": [
                    {
                        "productId": int(line["product_id"]),
                        "name": line["product_name"],
                        "unitPrice": f"{_money(line['unit_price']):.2f}",
                        "quantity": int(line["quantity"]),
                        "lineTotal": f"{_money(line['line_total']):.2f}",
                    }
                    for line in order_lines
                ],
            },
            "consent": {
                "confirmationGrantId": str(row["confirmation_grant_id"]),
                "acknowledgedAt": _iso(row["acknowledged_at"]),
            },
            "inventory": {
                "reservationIds": [
                    str(item["reservation_id"]) for item in reservations
                ],
                "ledgerEntryIds": ledger_ids,
                "status": (
                    "captured" if order_status == "paid" else "released"
                ),
            },
            "payment": {
                "attemptId": str(row["attempt_id"]),
                "eventIds": payment_event_ids,
                "provider": row["provider"],
                "mode": row["mode"],
                "status": row["provider_status"],
                "providerRef": row["provider_ref"],
                "failureCode": row["failure_code"],
            },
            "outboxEventIds": outbox_ids,
            "outcome": order_status,
        }
        receipt_id = uuid.uuid4()
        receipt_hash = _canonical_hash(evidence)
        await cur.execute(
            """
            INSERT INTO pellier.commerce_receipts (
                receipt_id, order_id, principal_sub, quote_id,
                confirmation_grant_id, payment_attempt_id, outcome,
                evidence, receipt_hash, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (order_id) DO NOTHING
            """,
            (
                receipt_id,
                order_id,
                principal_sub,
                row["quote_id"],
                row["confirmation_grant_id"],
                row["attempt_id"],
                order_status,
                json.dumps(_json_value(evidence)),
                receipt_hash,
                now,
            ),
        )

    async def get_receipt(
        self,
        *,
        principal_sub: str,
        order_id: uuid.UUID,
    ) -> dict[str, Any]:
        row = await self.db.fetch_one(
            """
            SELECT o.order_id, o.order_number, o.status, o.payment_status,
                   o.currency, o.subtotal, o.shipping, o.tax, o.total,
                   o.created_at, r.receipt_id, r.receipt_hash,
                   r.evidence, r.created_at AS receipt_created_at
              FROM pellier.commerce_orders o
              JOIN pellier.commerce_receipts r ON r.order_id = o.order_id
             WHERE o.order_id = %s
               AND o.principal_sub = %s
               AND r.principal_sub = %s
            """,
            order_id,
            principal_sub,
            principal_sub,
        )
        if not row:
            raise CommerceError("receipt_not_found", 404)
        evidence = _parse_json(row["evidence"])
        receipt_hash = str(row["receipt_hash"]).strip()
        return {
            "orderId": str(row["order_id"]),
            "orderNumber": row["order_number"],
            "status": row["status"],
            "paymentStatus": row["payment_status"],
            "currency": row["currency"],
            "amounts": {
                "subtotal": f"{_money(row['subtotal']):.2f}",
                "shipping": f"{_money(row['shipping']):.2f}",
                "tax": f"{_money(row['tax']):.2f}",
                "total": f"{_money(row['total']):.2f}",
            },
            "payment": evidence["payment"],
            "evidence": evidence,
            "receipt": {
                "receiptId": str(row["receipt_id"]),
                "receiptHash": receipt_hash,
                "verified": hmac.compare_digest(
                    receipt_hash,
                    _canonical_hash(evidence),
                ),
                "createdAt": _iso(row["receipt_created_at"]),
            },
            "createdAt": _iso(row["created_at"]),
        }

    @staticmethod
    async def _set_inventory_context(
        cur: Any,
        *,
        reason: str,
        idempotency_key: str,
        principal_sub: str,
    ) -> None:
        await cur.execute(
            "SELECT set_config('pellier.inventory_reason', %s, true)",
            (reason,),
        )
        await cur.execute(
            "SELECT set_config('pellier.inventory_idempotency_key', %s, true)",
            (idempotency_key,),
        )
        await cur.execute(
            "SELECT set_config('pellier.principal_sub', %s, true)",
            (principal_sub,),
        )

    @staticmethod
    async def _insert_outbox(
        cur: Any,
        *,
        order_id: uuid.UUID,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> uuid.UUID:
        event_id = uuid.uuid4()
        await cur.execute(
            """
            INSERT INTO pellier.commerce_outbox (
                event_id, aggregate_type, aggregate_id,
                event_type, payload
            )
            VALUES (%s, 'commerce_order', %s, %s, %s::jsonb)
            """,
            (event_id, order_id, event_type, json.dumps(_json_value(payload))),
        )
        return event_id


__all__ = [
    "CommerceError",
    "CommerceService",
    "PaymentResult",
    "SandboxPaymentAdapter",
]
