"""Pellier's nine store tools: one bounded, parameterized query each.

Every tool's SQL and row shaping is stated once, here, and two rails call it:

* the in-process ``@tool`` wrappers in ``services/agent_tools.py``, through
  the psycopg pool;
* the Gateway Lambda ``scripts/deploy/pellier_store_tools.py``, through the
  RDS Data API adapter in ``scripts/deploy/common/dataapi.py``.

Each function takes ``run(sql, params) -> list[dict]``. SQL uses positional
``%s`` placeholders and ``params`` is a sequence in matching order, so psycopg
binds it directly and the Data API adapter rewrites it to named parameters (a
list parameter binds as ``text[]``). Every statement returns rows: a write ends
in ``RETURNING`` so both drivers can fetch its result the same way.

Values come back typed differently on the two rails. psycopg returns
``Decimal``, ``datetime`` and parsed JSON; the Data API returns numbers and
timestamps as strings and JSON columns as text. The shaping helpers below
accept both, so a tool answers identically whichever rail ran it.

This module imports only the standard library and the two pure retrieval
modules it plans and proves searches with, so the Lambda can package it.

| Tool                | Agent            | One bounded query                         |
|---------------------|------------------|-------------------------------------------|
| search_products     | Shopping         | planned hybrid search, writes a receipt   |
| browse_department   | Shopping         | products in one department, by rating     |
| compare_products    | Shopping         | two products side by side, by id          |
| check_stock         | Stock            | warehouse counts and ship windows         |
| get_orders          | Support          | the signed-in customer's orders           |
| get_return_policy   | Support          | return window and care for a department   |
| get_tickets         | Support          | the signed-in customer's support tickets  |
| give_store_credit   | Operator only    | one store credit per idempotency key      |
| ask_a_person        | Shopping, Support| a handoff; a credit request opens a review|
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from services.retrieval_receipt import INSERT_SQL as RECEIPT_INSERT_SQL
from services.retrieval_receipt import build_receipt, receipt_params
from services.search_plan import (
    STRATEGY_HYBRID,
    STRATEGY_VECTOR,
    PreferenceRelaxationUnavailable,
    build_plan,
)

logger = logging.getLogger(__name__)

Run = Callable[[str, Sequence[Any]], List[Dict[str, Any]]]
EmbedFn = Callable[[str], Sequence[float]]
RerankFn = Callable[..., List[Dict[str, Any]]]

# The nine tools, in the order the Gateway publishes them.
TOOL_NAMES: Tuple[str, ...] = (
    "search_products",
    "browse_department",
    "compare_products",
    "check_stock",
    "get_orders",
    "get_return_policy",
    "get_tickets",
    "give_store_credit",
    "ask_a_person",
)

# Results a shopper-facing read may return. The bound is part of the contract:
# no tool hands a model an unbounded table.
MAX_ROWS = 20

# The goodwill ceiling. A CHECK constraint on pellier.store_credits enforces it
# again in the database; this only returns a readable envelope first.
MAX_CREDIT_CENTS = 50000

_LIKE_METACHARACTERS = re.compile(r"([\\%_])")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def prepare_like_pattern(term: str) -> str:
    """Wrap literal shopper text in a contains-match LIKE pattern.

    Bound parameters prevent injection, but PostgreSQL still reads ``%``,
    ``_`` and ``\\`` inside a LIKE value. Escaping them keeps the shopper's
    text literal; the surrounding wildcards make it a contains-match.
    """
    escaped = _LIKE_METACHARACTERS.sub(r"\\\1", str(term).lower())
    return f"%{escaped}%"


def write_request_hash(operation: str, **arguments: Any) -> str:
    """Canonical fingerprint of a write request: sorted-key JSON, SHA-256 hex.

    An operator review stores it as ``approvals.action_hash`` and the credit
    write stores the same value, so a human confirmation binds to the exact
    parameters it was shown and the write it authorises compares by value.
    """
    payload = json.dumps(
        {"operation": operation, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clamp(limit: Any, default: int, ceiling: int = MAX_ROWS) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(1, min(value, ceiling))


def as_number(value: Any) -> Optional[float]:
    """A row value as a float, or ``None`` when it is absent or not a number.

    A bare ``bool`` is absent too: ``float(True)`` is a coincidence of the
    type system, not a price.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    number = as_number(value)
    return int(number) if number is not None else 0


def _as_list(value: Any) -> List[Any]:
    """A JSON array column as a list, whether the driver parsed it or not."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return list(value) if isinstance(value, (list, tuple)) else []


def _as_object(value: Any) -> Any:
    """A JSON object column as a dict, whether the driver parsed it or not."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _plain(value: Any) -> Any:
    """JSON-safe copy of a driver value."""
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _product(row: Dict[str, Any]) -> Dict[str, Any]:
    """The product card every catalog tool returns."""
    return {
        "productId": str(row.get("productId") or row.get("product_id") or ""),
        "name": row.get("name") or "",
        "brand": row.get("brand") or "",
        "color": row.get("color") or "",
        "price": as_number(row.get("price")) or 0.0,
        "rating": as_number(row.get("rating")) or 0.0,
        "reviews": _integer(row.get("reviews")),
        "category": row.get("category") or "",
        "imgUrl": row.get("imgUrl") or row.get("img_url") or "",
        "badge": row.get("badge"),
        "tags": [str(tag) for tag in _as_list(row.get("tags"))],
    }


# ---------------------------------------------------------------------------
# browse_department
# ---------------------------------------------------------------------------

_BROWSE_SQL = """
    SELECT "productId", name, brand, color, price, rating, reviews,
           category, "imgUrl", badge, tags
      FROM pellier.product_catalog
     WHERE lower(category) LIKE %s ESCAPE '\\'
       AND "imgUrl" IS NOT NULL
     ORDER BY rating DESC, reviews DESC, "productId"
     LIMIT %s
"""


def browse_department(run: Run, *, department: str, limit: int = 5) -> Dict[str, Any]:
    """The highest-rated products in one store department."""
    name = " ".join(str(department or "").split())
    if not name:
        return {"status": "error", "message": "A department is required."}
    rows = run(_BROWSE_SQL, (prepare_like_pattern(name), _clamp(limit, 5)))
    products = [_product(row) for row in rows]
    return {
        "status": "success",
        "department": name,
        "count": len(products),
        "products": products,
    }


# ---------------------------------------------------------------------------
# compare_products
# ---------------------------------------------------------------------------

_COMPARE_SQL = """
    SELECT "productId", name, brand, color, description, price, rating,
           reviews, category, "imgUrl", badge, tags
      FROM pellier.product_catalog
     WHERE "productId" IN (%s, %s)
"""


def compare_products(run: Run, *, product_id_1: Any, product_id_2: Any) -> Dict[str, Any]:
    """Two named products side by side: price, rating and reviews."""
    first, second = str(product_id_1).strip(), str(product_id_2).strip()
    rows = {str(row.get("productId")): row for row in run(_COMPARE_SQL, (first, second))}
    missing = [pid for pid in (first, second) if pid not in rows]
    if missing:
        return {"status": "not_found", "error": f"Product(s) not found: {', '.join(missing)}"}

    product_1, product_2 = _product(rows[first]), _product(rows[second])
    return {
        "status": "success",
        "product_1": product_1,
        "product_2": product_2,
        "comparison": {
            "price_winner": product_1["productId"]
            if product_1["price"] <= product_2["price"]
            else product_2["productId"],
            "rating_winner": product_1["productId"]
            if product_1["rating"] >= product_2["rating"]
            else product_2["productId"],
            "reviews_winner": product_1["productId"]
            if product_1["reviews"] >= product_2["reviews"]
            else product_2["productId"],
            "price_difference": round(abs(product_1["price"] - product_2["price"]), 2),
        },
    }


# ---------------------------------------------------------------------------
# check_stock
# ---------------------------------------------------------------------------

_STOCK_PRODUCT_SQL = """
    SELECT "productId", name, brand, color, price
      FROM pellier.product_catalog
     WHERE {clause}
     ORDER BY rating DESC NULLS LAST, "productId"
     LIMIT 5
"""

_STOCK_WAREHOUSE_SQL = """
    SELECT w.id              AS warehouse_id,
           w.display_name    AS warehouse_name,
           w.city,
           w.ship_window_min,
           w.ship_window_max,
           wi.quantity
      FROM pellier.warehouse_inventory wi
      JOIN pellier.warehouses w ON w.id = wi.warehouse_id
     WHERE wi.product_id = %s
     ORDER BY wi.quantity DESC, w.id ASC
"""


def check_stock(run: Run, *, product_query: str) -> Dict[str, Any]:
    """Warehouse, quantity and ship window for one named product.

    Unknown and zero are different answers. A piece the catalog does not
    carry is ``not_found``; a piece it carries with no units is ``success``
    with ``total_units`` 0 and its warehouse rows. More than one match is
    ``ambiguous`` with the candidates, so the agent asks which one is meant.
    """
    tokens = [token for token in str(product_query or "").split() if token]
    if not tokens:
        return {"status": "not_found", "query": product_query, "message": "Empty product query."}

    # One LIKE per word, so "Hadley shirt" matches "Hadley ... Linen Shirt".
    clause = " AND ".join(["lower(name) LIKE %s ESCAPE '\\'"] * len(tokens))
    candidates = run(
        _STOCK_PRODUCT_SQL.format(clause=clause),
        tuple(prepare_like_pattern(token) for token in tokens),
    )
    if not candidates:
        return {
            "status": "not_found",
            "query": product_query,
            "message": (
                f"No product matched '{product_query}'. "
                "Stock can only be reported for products in the catalog."
            ),
        }
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "query": product_query,
            "candidates": [
                {
                    "productId": str(row.get("productId")),
                    "name": row.get("name"),
                    "brand": row.get("brand"),
                    "color": row.get("color"),
                }
                for row in candidates
            ],
            "message": (
                f"Multiple products match '{product_query}'. "
                "Ask the customer which one they mean before reporting stock."
            ),
        }

    product = candidates[0]
    product_id = str(product.get("productId"))
    warehouses = [
        {
            "warehouse_id": row.get("warehouse_id"),
            "warehouse_name": row.get("warehouse_name"),
            "city": row.get("city"),
            "ship_window_min": _integer(row.get("ship_window_min")),
            "ship_window_max": _integer(row.get("ship_window_max")),
            "quantity": _integer(row.get("quantity")),
        }
        for row in run(_STOCK_WAREHOUSE_SQL, (product_id,))
    ]
    return {
        "status": "success",
        "product": {
            "productId": product_id,
            "name": product.get("name"),
            "brand": product.get("brand"),
            "color": product.get("color"),
            "price": as_number(product.get("price")),
        },
        "total_units": sum(row["quantity"] for row in warehouses),
        "warehouses": warehouses,
    }


# ---------------------------------------------------------------------------
# get_orders
# ---------------------------------------------------------------------------

_ORDERS_SQL = """
    SELECT o.id AS order_id, o.product_id, p.name, p.brand, p.category,
           o.quantity, o.amount_paid_cents, o.placed_at
      FROM pellier.orders o
      JOIN pellier.product_catalog p ON p."productId" = o.product_id
     WHERE o.customer_id = %s
     ORDER BY o.placed_at DESC, o.id DESC
     LIMIT %s
"""


def get_orders(run: Run, *, customer_id: str, limit: int = 10) -> Dict[str, Any]:
    """One customer's orders, newest first, with the amount paid.

    The caller binds ``customer_id`` to the signed-in shopper; this function
    never chooses whose orders to read.
    """
    orders = [
        {
            "order_id": _integer(row.get("order_id")),
            "product_id": str(row.get("product_id")),
            "name": row.get("name"),
            "brand": row.get("brand"),
            "category": row.get("category"),
            "quantity": _integer(row.get("quantity")),
            "amount_paid_cents": _integer(row.get("amount_paid_cents")),
            "amount_paid": round(_integer(row.get("amount_paid_cents")) / 100.0, 2),
            "placed_at": _timestamp(row.get("placed_at")),
        }
        for row in run(_ORDERS_SQL, (str(customer_id), _clamp(limit, 10)))
    ]
    return {
        "status": "success",
        "customer_id": str(customer_id),
        "count": len(orders),
        "orders": orders,
    }


# ---------------------------------------------------------------------------
# get_return_policy
# ---------------------------------------------------------------------------

# One row: the department's own policy when it has one, else the default.
_RETURN_POLICY_SQL = """
    SELECT category_name, return_window_days, conditions, refund_method
      FROM pellier.return_policies
     WHERE category_name IN (%s, 'default')
     ORDER BY (category_name = 'default'), category_name
     LIMIT 1
"""


def get_return_policy(run: Run, *, department: str = "default") -> Dict[str, Any]:
    """The return window, condition rules and refund method for a department."""
    name = " ".join(str(department or "").split()) or "default"
    rows = run(_RETURN_POLICY_SQL, (name,))
    if not rows:
        return {"status": "not_found", "error": f"No return policy found for {name}."}
    row = rows[0]
    return {
        "status": "success",
        "department": row.get("category_name"),
        "return_window_days": _integer(row.get("return_window_days")),
        "conditions": row.get("conditions"),
        "refund_method": row.get("refund_method"),
    }


# ---------------------------------------------------------------------------
# get_tickets
# ---------------------------------------------------------------------------

_TICKETS_SQL = """
    SELECT ticket_id, subject, status, channel, last_note, opened_at, resolved_at
      FROM pellier.support_tickets
     WHERE customer_id = %s
     ORDER BY opened_at DESC
     LIMIT %s
"""


def get_tickets(run: Run, *, customer_id: str, limit: int = 5) -> Dict[str, Any]:
    """One customer's support tickets, newest first.

    Like ``get_orders``, the caller binds ``customer_id`` to the signed-in
    shopper; on the Gateway that binding is the Lab 3 build.
    """
    tickets = [
        {
            "ticket_id": row.get("ticket_id"),
            "subject": row.get("subject"),
            "status": row.get("status"),
            "channel": row.get("channel"),
            "last_note": row.get("last_note"),
            "opened_at": _timestamp(row.get("opened_at")),
            "resolved_at": _timestamp(row.get("resolved_at")),
        }
        for row in run(_TICKETS_SQL, (str(customer_id), _clamp(limit, 5)))
    ]
    return {
        "status": "success",
        "customer_id": str(customer_id),
        "count": len(tickets),
        "open_count": sum(1 for ticket in tickets if ticket["status"] in ("open", "pending")),
        "tickets": tickets,
    }


# ---------------------------------------------------------------------------
# give_store_credit
# ---------------------------------------------------------------------------

# Every argument is cast at the call site. The Data API sends an integer as a
# bigint, and PostgreSQL does not narrow bigint to the function's ``integer``
# parameter when resolving the overload (live, 2026-09-10: Cedar allowed the
# call, the Lambda ran, and no credit row was written).
_CREDIT_SQL = (
    "SELECT pellier.apply_store_credit("
    "%s::text, %s::text, %s::text, %s::integer, %s::text, %s::text) AS result"
)


def give_store_credit(
    run: Run,
    *,
    customer_id: str,
    amount_cents: Any,
    reason: str,
    idempotency_key: str,
    issued_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Write one store credit, exactly once per idempotency key.

    Staff only, and only for a review a person approved: Cedar admits the
    staff scope at the Gateway, and the Operator executes nothing it has not
    confirmed. A replay returns the first result instead of a second credit.

    Args:
        run: Statement runner for the calling rail.
        customer_id: Customer receiving the credit, e.g. ``CUST-JESSICA``.
        amount_cents: Integer cents, at most ``MAX_CREDIT_CENTS``.
        reason: Why the credit is given. Required, and audited.
        idempotency_key: The review's key for this one intended write.
        issued_by: Verified staff subject, when the rail has one.
    """
    key = str(idempotency_key or "").strip()
    if not key:
        return {"status": "error", "message": "idempotency_key is required."}
    try:
        cents = int(amount_cents)
    except (TypeError, ValueError):
        return {"status": "error", "message": f"amount_cents must be an integer, got {amount_cents!r}."}
    clean_reason = str(reason or "").strip()
    if not clean_reason:
        return {"status": "error", "message": "A reason is required for a credit."}

    request_hash = write_request_hash(
        "give_store_credit",
        customer_id=str(customer_id),
        amount_cents=cents,
        reason=clean_reason,
    )
    rows = run(
        _CREDIT_SQL,
        (key, request_hash, str(customer_id), cents, clean_reason, str(issued_by or "") or None),
    )
    result = _as_object(rows[0].get("result")) if rows else None
    if not isinstance(result, dict):
        return {"status": "error", "message": "Credit operation produced no result."}
    return {name: _plain(value) for name, value in result.items()}


# ---------------------------------------------------------------------------
# ask_a_person
# ---------------------------------------------------------------------------

# A credit request becomes a pending review for staff: the same row shape the
# Operator review queue reads, keyed so a repeated ask resolves to one card.
_CREDIT_REVIEW_SQL = """
    INSERT INTO pellier.approvals
        (customer_id, tool, args, status, source_turn_id, issue,
         recommendation, action_hash, requested_by_sub, requester_kind)
    VALUES (%s, 'give_store_credit', %s::jsonb, 'pending', %s, %s,
            %s::jsonb, %s, %s, %s)
    ON CONFLICT (customer_id, tool, action_hash) WHERE status = 'pending'
    DO NOTHING
    RETURNING id
"""

_OPEN_CREDIT_REVIEW_SQL = """
    SELECT id
      FROM pellier.approvals
     WHERE customer_id = %s
       AND tool = 'give_store_credit'
       AND action_hash = %s
       AND status = 'pending'
     LIMIT 1
"""


def _open_credit_review(
    run: Run,
    *,
    customer_id: str,
    amount_cents: int,
    reason: str,
    source_turn_id: Optional[str],
    requested_by_sub: Optional[str],
    requester_kind: str,
) -> Optional[int]:
    material = {"customer_id": customer_id, "amount_cents": amount_cents, "reason": reason}
    action_hash = write_request_hash("give_store_credit", **material)
    recommendation = {
        "primaryAction": "give_store_credit",
        "rationale": "Requested by the client in conversation.",
    }
    rows = run(
        _CREDIT_REVIEW_SQL,
        (
            customer_id,
            json.dumps(material, sort_keys=True),
            source_turn_id,
            reason,
            json.dumps(recommendation, sort_keys=True),
            action_hash,
            (requested_by_sub or "").strip() or None,
            requester_kind,
        ),
    )
    if not rows:
        rows = run(_OPEN_CREDIT_REVIEW_SQL, (customer_id, action_hash))
    return _integer(rows[0].get("id")) if rows else None


def ask_a_person(
    run: Run,
    *,
    reason: str,
    customer_id: Optional[str] = None,
    store_credit_cents: Any = 0,
    source_turn_id: Optional[str] = None,
    requested_by_sub: Optional[str] = None,
    requester_kind: str = "unverified",
) -> Dict[str, Any]:
    """Hand the conversation to a person at Pellier.

    The handoff changes no business data. When the shopper asks for store
    credit, it also opens one pending review for staff to decide; the credit
    itself is written only by ``give_store_credit`` after a person approves.

    Args:
        run: Statement runner for the calling rail.
        reason: One sentence on what is being handed over and why.
        customer_id: The caller-bound customer, or ``None`` when unknown.
        store_credit_cents: The credit the shopper asked for, in cents; zero
            when the handoff is not a credit request.
        source_turn_id: The shopper turn that asked, for the review record.
        requested_by_sub: Verified subject that asked, when the rail has one.
        requester_kind: ``shopper`` for a verified caller, else ``unverified``.
    """
    clean_reason = " ".join(str(reason or "").split()) or "The shopper asked to talk to a person."
    customer = str(customer_id or "").strip() or None
    payload: Dict[str, Any] = {
        "type": "escalation",
        "channel": "person",
        "status": "handed_off",
        "reason": clean_reason,
        "customer_id": customer,
        "contact": {
            "label": "Talk to a person",
            "mailto": "help@pellier.example",
            "response_window": "Within 1 business day",
        },
        "next_steps": [
            "A person at Pellier receives your note with the full context.",
            "They reply within one business day.",
            "You can keep browsing. We'll pick up where you left off.",
        ],
    }

    cents = _integer(store_credit_cents)
    if cents <= 0:
        return payload
    if customer is None:
        payload["credit_request"] = "sign_in_required"
        return payload
    if cents > MAX_CREDIT_CENTS:
        payload["credit_request"] = "over_ceiling"
        return payload

    try:
        review_id = _open_credit_review(
            run,
            customer_id=customer,
            amount_cents=cents,
            reason=clean_reason,
            source_turn_id=source_turn_id,
            requested_by_sub=requested_by_sub,
            requester_kind=requester_kind if requester_kind in ("shopper", "unverified") else "unverified",
        )
    except Exception as exc:  # noqa: BLE001 - the handoff stands without the review
        logger.warning("credit review not opened for %s: %s", customer, exc)
        review_id = None
    if review_id is None:
        payload["credit_request"] = "not_recorded"
        return payload
    payload["credit_request"] = "review_opened"
    payload["review_id"] = review_id
    return payload


# ---------------------------------------------------------------------------
# search_products: the planned hybrid pipeline
# ---------------------------------------------------------------------------
#
# typed plan -> hard SQL predicates on both branches -> vector + full text
# -> RRF -> rerank over a bounded pool -> eligibility recheck -> rows shown
#
# Hard constraints are enforced twice on purpose. They enter candidate
# generation as SQL so an invalid row never consumes reranker capacity, and
# they are rechecked after the reranker so a row that slipped past the SQL is
# still refused before it becomes evidence.

STAGE_EMBED = "embed"
STAGE_VECTOR = "vector"
STAGE_HYBRID = "hybrid"
STAGE_RERANK = "rerank"
STAGE_ELIGIBILITY = "eligibility"

SEARCH_METHOD_VECTOR = "vector"
SEARCH_METHOD_HYBRID = "hybrid"
SEARCH_METHOD_HYBRID_RERANK = "hybrid+rerank"
SEARCH_METHOD_RERANK_FALLBACK = "hybrid (rerank fallback to RRF order)"

# Below three documents the reranker has nothing to reorder.
RERANK_POOL_MIN = 3
# The provided candidate budget. Tune only in the optional retrieval extension.
DEFAULT_RERANK_POOL_K = 15

# Executor knobs when a caller supplies none. The backend passes its settings;
# the Lambda, which has no settings module, runs on these.
DEFAULT_RETRIEVAL_CONFIG: Dict[str, int] = {
    "k_vector": 20,
    "k_fts": 20,
    "rrf_k": 60,
    "top_n": 30,
    "rerank_max_documents": 30,
}

# Stop words and US spellings for the full-text branch. Conversational queries
# OR-join their meaningful tokens: plainto_tsquery ANDs every stem, so "a
# thoughtful gift for someone who loves morning rituals" would match nothing.
FTS_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "have", "has",
    "are", "was", "were", "from", "into", "out", "but", "not",
    "any", "all", "some", "one", "two", "three", "what", "where",
    "when", "how", "who", "why", "you", "your", "yours", "our",
    "their", "they", "them", "his", "her", "him", "she",
    "let", "lets", "just", "really", "also", "more", "most",
    "much", "many", "very",
    # Conversational filler that never adds retrieval signal.
    "something", "someone", "somebody", "anything", "anyone",
    "thing", "things", "stuff", "kind", "sort", "type",
    "good", "great", "nice", "would", "could", "should",
    "want", "need", "like", "love", "loves", "loving",
    # Generic shopping verbs.
    "find", "show", "give", "get", "browse", "recommend",
    "suggest", "help", "tell", "look", "looking",
})
# The catalog spells colors the US way, and the english stemmer keeps "grey"
# and "gray" apart.
US_SPELLINGS = {"grey": "gray"}

_CATALOG_COLUMNS = """
                "productId" AS product_id,
                name,
                brand,
                color,
                description,
                "imgUrl"   AS img_url,
                category,
                price,
                rating,
                reviews,
                badge,
                tags,
                materials,
                quantity,
                updated_at"""


def _indent_clauses(extra_clauses: Sequence[str]) -> str:
    """Render extra predicates as trailing ``AND`` lines for the branch SQL."""
    return "".join(f"\n              AND {clause}" for clause in extra_clauses)


def vector_branch_sql(extra_clauses: Sequence[str] = ()) -> str:
    """The pgvector branch, with a plan's hard predicates applied.

    Parameters, in order: the query embedding as a vector literal, the
    predicate parameters, and the branch size.
    """
    return f"""
            WITH query_embedding AS (
                SELECT %s::vector AS emb
            )
            SELECT{_CATALOG_COLUMNS},
                1 - (embedding <=> (SELECT emb FROM query_embedding)) AS similarity
            FROM pellier.product_catalog
            WHERE "imgUrl" IS NOT NULL{_indent_clauses(extra_clauses)}
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """


def fts_branch_sql(extra_clauses: Sequence[str] = ()) -> str:
    """The full-text branch, with a plan's hard predicates applied.

    Parameters, in order: the OR-joined ``to_tsquery`` text, the predicate
    parameters, and the branch size. ``ts_rank_cd`` is cover-density ranking,
    not BM25.
    """
    return f"""
            WITH q AS (
                SELECT to_tsquery('english', %s) AS ts_q
            )
            SELECT{_CATALOG_COLUMNS},
                ts_rank_cd(description_tsv, q.ts_q) AS fts_rank_score
            FROM pellier.product_catalog
            CROSS JOIN q
            WHERE "imgUrl" IS NOT NULL
              AND description_tsv @@ q.ts_q{_indent_clauses(extra_clauses)}
            ORDER BY fts_rank_score DESC
            LIMIT %s
        """


def or_tsquery(query: str) -> str:
    """OR-of-tokens text for ``to_tsquery``; empty when no token survives."""
    if not query:
        return ""
    cleaned = re.sub(r"[^\w\s-]", " ", query.lower())
    tokens = [token.strip("-") for token in cleaned.split() if len(token) > 2]
    tokens = [US_SPELLINGS.get(token, token) for token in tokens if token not in FTS_STOP_WORDS]
    unique: List[str] = []
    for token in tokens:
        if token and token not in unique:
            unique.append(token)
    return " | ".join(unique)


def vector_literal(embedding: Sequence[float]) -> str:
    """pgvector's text form, which both drivers bind as a plain string."""
    return "[" + ",".join(repr(float(value)) for value in embedding) + "]"


def rrf_merge(
    vector_rows: List[Dict[str, Any]],
    fts_rows: List[Dict[str, Any]],
    rrf_k: int,
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion: sum ``1 / (rrf_k + rank)`` over both lists.

    Every merged row keeps its branch ranks (``vec_rank``, ``fts_rank``,
    ``None`` when absent from a branch) and gains ``rrf_score``. When a
    product appears in both branches the vector row is kept, so its cosine
    similarity survives for the receipt.
    """
    scores: Dict[Any, float] = {}
    rows_by_id: Dict[Any, Dict[str, Any]] = {}
    for rank_zero, row in enumerate(vector_rows):
        pid = row["product_id"]
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (rrf_k + rank_zero + 1)
        if pid not in rows_by_id:
            rows_by_id[pid] = dict(row)
            rows_by_id[pid]["fts_rank"] = None
        rows_by_id[pid]["vec_rank"] = rank_zero + 1
    for rank_zero, row in enumerate(fts_rows):
        pid = row["product_id"]
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (rrf_k + rank_zero + 1)
        if pid not in rows_by_id:
            rows_by_id[pid] = dict(row)
            rows_by_id[pid]["vec_rank"] = None
        elif "fts_rank_score" in row and "fts_rank_score" not in rows_by_id[pid]:
            rows_by_id[pid]["fts_rank_score"] = row["fts_rank_score"]
        rows_by_id[pid]["fts_rank"] = rank_zero + 1
    for pid, row in rows_by_id.items():
        row["rrf_score"] = scores[pid]
    merged = list(rows_by_id.values())
    merged.sort(key=lambda row: row["rrf_score"], reverse=True)
    return merged


def catalog_document(row: Dict[str, Any]) -> str:
    """The bounded catalog text the reranker scores."""
    name = " ".join(str(row.get("name") or "").split())
    description = " ".join(str(row.get("description") or "").split())
    category = " ".join(str(row.get("category") or "").split())
    if len(description) > 240:
        description = description[:237] + "…"
    return f"{name} — {description} ({category})"


def resolve_rerank_pool_k(config: Dict[str, Any]) -> int:
    """Bound the rerank pool between the floor and the reranker's own cap."""
    requested = config.get("rerank_pool_k") or DEFAULT_RERANK_POOL_K
    ceiling = max(RERANK_POOL_MIN, int(config.get("rerank_max_documents") or 30))
    return max(RERANK_POOL_MIN, min(int(requested), ceiling))


@dataclass
class SearchStage:
    """One pipeline stage: how many rows left it and how long it took."""

    name: str
    count: int
    latency_ms: int


@dataclass
class SearchExecution:
    """Everything one search run produced, ready to show and to prove.

    Attributes:
        plan: The plan rung that produced ``returned``; a widened rung lists
            its ``relaxations``.
        query: The text that was embedded and lexically matched.
        candidates: The fused pool, in RRF order, with branch ranks.
        ordered: The eligible rows in final order, with ``rerank_score``.
        returned: ``ordered[:limit]``, the rows the caller will show.
        stages: Per-stage counts and latencies, every pass in order.
        rerank_pool_k: The bound on documents sent to the reranker.
        relaxation_steps: Names of the ladder steps applied.
        search_method: The label the payload reports.
        attempts: One entry per pass: required tags, relaxations, eligible.
        relaxation_unavailable: Only the first pass ran because the starter
            cannot widen preferences yet; an empty result proves nothing.
    """

    plan: Any
    query: str
    candidates: List[Dict[str, Any]]
    ordered: List[Dict[str, Any]]
    returned: List[Dict[str, Any]]
    stages: List[SearchStage]
    rerank_pool_k: int
    relaxation_steps: List[str] = field(default_factory=list)
    search_method: str = SEARCH_METHOD_HYBRID_RERANK
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    relaxation_unavailable: bool = False

    @property
    def rerank_pool(self) -> List[Dict[str, Any]]:
        """The candidates the reranker was allowed to see."""
        return self.candidates[: self.rerank_pool_k]

    def stage(self, name: str) -> Optional[SearchStage]:
        """Return the last recorded stage with this name, if it ran."""
        for recorded in reversed(self.stages):
            if recorded.name == name:
                return recorded
        return None

    def latency_breakdown(self) -> Dict[str, int]:
        """Sum stage latencies by name for the retrieval receipt."""
        breakdown: Dict[str, int] = {}
        for recorded in self.stages:
            breakdown[recorded.name] = breakdown.get(recorded.name, 0) + recorded.latency_ms
        return breakdown


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _catalog_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one branch row: JSON columns as lists on either rail."""
    normalized = dict(row)
    for name in ("tags", "materials"):
        if name in normalized and not isinstance(normalized[name], list):
            normalized[name] = _as_list(normalized[name])
    return normalized


def violates_hard_constraints(row: Dict[str, Any], plan: Any) -> bool:
    """True when a row breaks a hard predicate the plan declared.

    A field the row does not carry, or carries as something that will not
    coerce, cannot be judged and is not a violation; the SQL predicate stays
    the enforcement point for it.
    """
    hard = plan.hard
    price = as_number(row.get("price"))
    ceiling = as_number(hard.price_max_usd)
    if ceiling is not None and price is not None and price > ceiling + 1e-9:
        return True
    category = row.get("category")
    if hard.categories and category is not None:
        if str(category).lower() not in {value.lower() for value in hard.categories}:
            return True
    quantity = as_number(row.get("quantity"))
    if hard.in_stock_only and quantity is not None and quantity <= 0:
        return True
    excluded = {value.lower() for value in plan.exclusions}
    for listed in (row.get("tags"), row.get("materials")):
        if excluded and listed is not None and {str(v).lower() for v in listed} & excluded:
            return True
    return False


def _project_rerank(pool: List[Dict[str, Any]], results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Project reranker indices back onto the pool, skipping invalid ones."""
    ordered: List[Dict[str, Any]] = []
    for result in results:
        try:
            index = int(result["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if index < 0 or index >= len(pool):
            continue
        try:
            score = float(result.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        ordered.append({**pool[index], "rerank_score": score})
    return ordered


def _bounded(value: Any, default: int) -> int:
    return max(5, min(int(value or default), 100))


def _retrieve_candidates(
    run: Run,
    *,
    plan: Any,
    query: str,
    embedding: str,
    config: Dict[str, Any],
    stages: List[SearchStage],
) -> List[Dict[str, Any]]:
    """Candidate generation for the plan's declared strategy."""
    clauses, params = plan.compile_predicates()
    k_vector = _bounded(config.get("k_vector"), DEFAULT_RETRIEVAL_CONFIG["k_vector"])
    started = time.perf_counter()
    vector_rows = [
        _catalog_row(row)
        for row in run(vector_branch_sql(clauses), (embedding, *params, k_vector))
    ]
    if plan.retrieval_strategy == STRATEGY_VECTOR:
        for rank_zero, row in enumerate(vector_rows):
            row["vec_rank"] = rank_zero + 1
            row["fts_rank"] = None
            row["rrf_score"] = None
        stages.append(SearchStage(STAGE_VECTOR, len(vector_rows), _elapsed_ms(started)))
        return vector_rows

    lexical = or_tsquery(query)
    k_fts = _bounded(config.get("k_fts"), DEFAULT_RETRIEVAL_CONFIG["k_fts"])
    fts_rows = (
        [_catalog_row(row) for row in run(fts_branch_sql(clauses), (lexical, *params, k_fts))]
        if lexical
        else []
    )
    rrf_k = int(config.get("rrf_k") or DEFAULT_RETRIEVAL_CONFIG["rrf_k"])
    top_n = _bounded(config.get("top_n"), DEFAULT_RETRIEVAL_CONFIG["top_n"])
    candidates = rrf_merge(vector_rows, fts_rows, rrf_k)[:top_n]
    stages.append(SearchStage(STAGE_HYBRID, len(candidates), _elapsed_ms(started)))
    return candidates


def _rank_candidates(
    candidates: List[Dict[str, Any]],
    *,
    plan: Any,
    query: str,
    rerank: RerankFn,
    pool_k: int,
    stages: List[SearchStage],
) -> Tuple[List[Dict[str, Any]], str]:
    """Order the pool: rerank for ``hybrid+rerank``, RRF order otherwise."""
    if plan.retrieval_strategy == STRATEGY_VECTOR:
        return [dict(row) for row in candidates], SEARCH_METHOD_VECTOR
    if plan.retrieval_strategy == STRATEGY_HYBRID:
        return [{**row, "rerank_score": None} for row in candidates], SEARCH_METHOD_HYBRID

    pool = [dict(row) for row in candidates[:pool_k]]
    rerank_query = (getattr(plan.soft, "soft_signal", "") or "").strip() or query
    started = time.perf_counter()
    results: List[Dict[str, Any]] = []
    if pool:
        results = rerank(
            query=rerank_query,
            documents=[catalog_document(row) for row in pool],
            top_n=len(pool),
        ) or []
    ordered = _project_rerank(pool, results)
    stages.append(SearchStage(STAGE_RERANK, len(ordered), _elapsed_ms(started)))
    if not ordered:
        return [{**row, "rerank_score": None} for row in pool], SEARCH_METHOD_RERANK_FALLBACK
    return ordered, SEARCH_METHOD_HYBRID_RERANK


def _run_pass(
    run: Run,
    *,
    plan: Any,
    query: str,
    embedding: str,
    limit: int,
    rerank: RerankFn,
    config: Dict[str, Any],
    pool_k: int,
    stages: List[SearchStage],
) -> SearchExecution:
    """Execute one plan rung end to end and record its stages."""
    candidates = _retrieve_candidates(
        run, plan=plan, query=query, embedding=embedding, config=config, stages=stages
    )
    ranked, search_method = _rank_candidates(
        candidates, plan=plan, query=query, rerank=rerank, pool_k=pool_k, stages=stages
    )
    started = time.perf_counter()
    ordered = [row for row in ranked if not violates_hard_constraints(row, plan)]
    stages.append(SearchStage(STAGE_ELIGIBILITY, len(ordered), _elapsed_ms(started)))
    return SearchExecution(
        plan=plan,
        query=query,
        candidates=candidates,
        ordered=ordered,
        returned=ordered[:limit],
        stages=stages,
        rerank_pool_k=pool_k,
        relaxation_steps=[relaxation.step for relaxation in plan.relaxations],
        search_method=search_method,
    )


def run_search_plan(
    run: Run,
    *,
    plan: Any,
    query: str,
    limit: int,
    embed: EmbedFn,
    rerank: RerankFn,
    config: Dict[str, Any],
    relax: bool = True,
    return_strict_on_unavailable: bool = False,
) -> SearchExecution:
    """Run a typed plan through the planned hybrid pipeline.

    Args:
        run: Statement runner for the calling rail.
        plan: A :class:`~services.search_plan.SearchPlan`. Its hard
            constraints and exclusions compile into both branch queries; its
            strategy selects vector, hybrid or hybrid+rerank; its
            ``soft_signal`` is what the reranker scores.
        query: The text embedded once and matched lexically.
        limit: How many rows the caller will show, at least one.
        embed: Returns the query embedding.
        rerank: ``rerank(query=, documents=, top_n=)`` returning
            ``[{"index", "relevance_score"}]``; empty means unavailable.
        config: ``k_vector``, ``k_fts``, ``rrf_k``, ``top_n``,
            ``rerank_pool_k`` and ``rerank_max_documents``.
        relax: When the strict pass is short, walk the plan's relaxation
            ladder. Hard constraints never widen.
        return_strict_on_unavailable: Keep an honest first pass when the
            starter cannot widen preferences yet, and mark it; otherwise the
            unfinished fallback raises.

    Returns:
        The :class:`SearchExecution` of the pass that produced the rows, with
        every pass's stages recorded in order.
    """
    limit = max(1, int(limit))
    pool_k = resolve_rerank_pool_k(config)
    stages: List[SearchStage] = []

    started = time.perf_counter()
    vector = list(embed(query))
    stages.append(SearchStage(STAGE_EMBED, len(vector), _elapsed_ms(started)))
    embedding = vector_literal(vector)
    attempts: List[Dict[str, Any]] = []

    def run_rung(rung: Any) -> SearchExecution:
        result = _run_pass(
            run,
            plan=rung,
            query=query,
            embedding=embedding,
            limit=limit,
            rerank=rerank,
            config=config,
            pool_k=pool_k,
            stages=stages,
        )
        attempts.append({
            "preferences": list(rung.soft.tags),
            "relaxations": [relaxation.step for relaxation in rung.relaxations],
            "eligible": len(result.ordered),
        })
        return result

    # A complete strict result needs no fallback, so the unfinished Lab 1
    # fallback never runs for a request the first pass already satisfies.
    execution = run_rung(plan)
    if relax and len(execution.returned) < limit:
        try:
            remaining_rungs = plan.relaxation_ladder()[1:]
        except PreferenceRelaxationUnavailable:
            if not return_strict_on_unavailable:
                raise
            # Keep the validated first pass. Never drop a predicate or claim
            # that a broader search found nothing.
            execution.relaxation_unavailable = True
            remaining_rungs = []
        for rung in remaining_rungs:
            if len(execution.returned) >= limit:
                break
            execution = run_rung(rung)
    execution.attempts = attempts
    return execution


# Merchandising rules are versioned and disclosed, never hidden. A declared
# rule may reorder candidates retrieval already surfaced; it never injects a
# product and never overrides a hard constraint. This one is Anna's
# housewarming hero.
MERCHANDISING_RULE_ID = "merch.milestone-home-gift.v1"
_MILESTONE_HOME_GIFT_PATTERN = re.compile(
    r"\b(milestone|housewarming|new homeowner|homeowner|new home|first home)\b",
    re.IGNORECASE,
)


def apply_merchandising_rules(
    query: str, products: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Apply declared merchandising rules and report which ones fired."""
    if not _MILESTONE_HOME_GIFT_PATTERN.search(query or ""):
        return products, []
    for index, product in enumerate(products):
        if product.get("name") != "Tall Stoneware Vase":
            continue
        if index == 0:
            return products, []
        promoted = [product, *products[:index], *products[index + 1:]]
        return promoted, [
            {
                "ruleId": MERCHANDISING_RULE_ID,
                "signal": "curated_hero",
                "product": product.get("name"),
                "fromRank": index + 1,
                "toRank": 1,
                "reason": (
                    "Declared merchandising rule: curated housewarming hero "
                    "promoted above pure relevance order."
                ),
            }
        ]
    return products, []


def _search_product(row: Dict[str, Any]) -> Dict[str, Any]:
    """The card for one retrieved row, with its ranking scores."""
    return {
        **_product(row),
        "description": row.get("description") or "",
        "rrf_score": row.get("rrf_score"),
        "rerank_score": row.get("rerank_score"),
    }


def select_shown_products(
    ordered: List[Dict[str, Any]],
    *,
    limit: int,
    max_price: Optional[float],
    min_rating: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Walk the eligible list in rank order and keep what the shopper sees.

    Price already ran in SQL and in the recheck; repeating it here is a last
    defence. ``min_rating`` is a genuine post-rerank preference. Returns the
    raw rows and their cards, index-aligned, so the receipt cites exactly the
    rows behind the cards.
    """
    rows: List[Dict[str, Any]] = []
    products: List[Dict[str, Any]] = []
    for row in ordered:
        product = _search_product(row)
        if max_price and product["price"] > max_price:
            continue
        if min_rating and product["rating"] < min_rating:
            continue
        rows.append(row)
        products.append(product)
        if len(products) >= limit:
            break
    return rows, products


def _write_search_receipt(
    run: Run,
    *,
    query: str,
    execution: SearchExecution,
    shown_rows: List[Dict[str, Any]],
    merchandising: List[Dict[str, Any]],
    config: Dict[str, Any],
    receipt: Dict[str, Any],
) -> None:
    """Persist the plan, per-stage ranks and the rows cited. Never raises.

    A receipt is evidence about a turn, not part of serving it: a lost receipt
    is a gap in evidence, a raised exception would be a gap in the product.
    """
    try:
        built = build_receipt(
            query=query,
            plan=execution.plan,
            candidates=execution.candidates,
            ordered=execution.ordered,
            citation_rows=shown_rows,
            merchandising_rules=merchandising,
            embedding_model=receipt.get("embedding_model"),
            rerank_model=receipt.get("rerank_model"),
            retrieval_config={
                **{key: value for key, value in config.items() if key != "rerank_max_documents"},
                "rerank_pool_k": execution.rerank_pool_k,
                "search_method": execution.search_method,
                "relaxation_steps": execution.relaxation_steps,
                "attempts": execution.attempts,
                "relaxation_unavailable": execution.relaxation_unavailable,
            },
            latency_breakdown=execution.latency_breakdown(),
            turn_id=receipt.get("turn_id"),
            session_id=receipt.get("session_id"),
            principal_sub=receipt.get("principal_sub"),
            rail=receipt.get("rail"),
        )
        run(RECEIPT_INSERT_SQL, receipt_params(built))
    except Exception as exc:  # noqa: BLE001 - evidence must not break the turn
        logger.warning("retrieval receipt write skipped: %s", exc)


def search_products(
    run: Run,
    *,
    query: str,
    embed: EmbedFn,
    rerank: RerankFn,
    extracted: Optional[Dict[str, Any]] = None,
    max_price: Optional[float] = None,
    min_rating: float = 0.0,
    category: Optional[str] = None,
    limit: int = 5,
    config: Optional[Dict[str, Any]] = None,
    receipt: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Planned hybrid search: the shopper's requirements as SQL, then rank.

    Args:
        run: Statement runner for the calling rail.
        query: Search words for what to find.
        embed: Returns the query embedding (Cohere Embed v4).
        rerank: Cohere Rerank 3.5, ``[]`` when unavailable.
        extracted: The structured reading of what the shopper typed, or
            ``None`` when no extractor ran. It is the only way a stated
            exclusion, stock requirement or implied budget reaches SQL.
        max_price: An explicit ceiling, a hard SQL predicate.
        min_rating: A post-rerank preference.
        category: A department the agent thinks fits. Recorded on the plan,
            never a filter.
        limit: Number of products to return.
        config: Executor knobs; defaults to ``DEFAULT_RETRIEVAL_CONFIG``.
        receipt: Turn context for the retrieval receipt (``turn_id``,
            ``session_id``, ``principal_sub``, ``rail``, model ids), or
            ``None`` to write none.

    Returns:
        The payload the agent reads. ``constraint_notice`` and
        ``search_notice`` are sentences the answer must relay.
    """
    limit = _clamp(limit, 5)
    knobs = {**DEFAULT_RETRIEVAL_CONFIG, **(config or {})}
    plan = build_plan(
        query,
        extracted,
        price_max_usd=max_price,
        inferred_category=category or None,
        top_k=limit,
    )
    execution = run_search_plan(
        run,
        plan=plan,
        query=query,
        limit=limit,
        embed=embed,
        rerank=rerank,
        config=knobs,
        return_strict_on_unavailable=True,
    )
    ordered, merchandising = apply_merchandising_rules(query, execution.ordered)
    shown_rows, products = select_shown_products(
        ordered, limit=limit, max_price=max_price, min_rating=min_rating
    )

    payload: Dict[str, Any] = {
        "status": "success",
        "query": query,
        "count": len(products),
        "products": products,
        "search_method": execution.search_method,
        "pool_size": len(execution.candidates),
        "rerank_pool_k": execution.rerank_pool_k,
        "hard_constraints_enforced": execution.plan.hard.describe(),
        "constraints_applied_before_rerank": True,
        "search_plan": execution.plan.to_dict(),
        "relaxation_unavailable": execution.relaxation_unavailable,
    }
    if execution.relaxation_unavailable:
        payload["search_notice"] = (
            "These are the matches from the first attempt. "
            "Alternatives with fewer preferences have not been checked."
            if products
            else "No matches were returned on the first attempt. "
            "Alternatives with fewer preferences have not been checked."
        )
    notice = execution.plan.constraint_notice()
    if notice:
        payload["constraint_notice"] = notice
    if merchandising:
        payload["merchandising_rules_applied"] = merchandising

    if receipt is not None:
        _write_search_receipt(
            run,
            query=query,
            execution=execution,
            shown_rows=shown_rows,
            merchandising=merchandising,
            config=knobs,
            receipt=receipt,
        )
    return payload
