"""
Business Logic Layer for Pellier
Contains custom business logic for pricing, trending, inventory, and
category analysis.

Aligned to the Pellier catalog schema:
    productId, name, brand, color, price, description, category, tags,
    rating, reviews (TEXT), "imgUrl", badge, tier, image_verified,
    quantity, embedding, created_at, updated_at

The ``quantity`` column is created by ``001_schema.sql`` and seeded by
``seed_pellier_catalog.py``. Stock-level
functions (check_inventory, get_low_stock, restock_inventory) now issue
real SQL against this column.
"""
import hashlib
import json
import re
from typing import Dict, Any, List, Optional
from decimal import Decimal


_LIKE_METACHARACTERS = re.compile(r"([\\%_])")


def prepare_like_pattern(term: str) -> str:
    """Wrap literal shopper text in a PostgreSQL LIKE pattern.

    Bound parameters prevent SQL injection, but PostgreSQL still interprets
    ``%``, ``_``, and ``\\`` inside a LIKE value. Escape those metacharacters
    so a shopper's query remains literal, then let the surrounding wildcards
    implement the intended contains-match.
    """
    escaped = _LIKE_METACHARACTERS.sub(r"\\\1", str(term).lower())
    return f"%{escaped}%"


def convert_decimals(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    return obj


def write_request_hash(operation: str, **arguments: Any) -> str:
    """Canonical fingerprint of a write request: sorted-key JSON, SHA-256 hex.

    Public because two callers depend on producing the *same* value:

      * every governed mutation stores it as ``write_operations.request_hash``,
        so replaying a key with different arguments is a conflict rather than a
        silent second write;
      * an operator review stores it as ``approvals.action_hash``, so a human
        confirmation binds to the exact parameters it was shown.

    Because both come from this one function, a confirmed review and the write
    it authorises can be compared by hash. A second implementation of the same
    scheme would make that comparison a coincidence rather than a guarantee.
    """
    payload = json.dumps(
        {"operation": operation, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BusinessLogic:
    """Business logic layer for custom analytics and operations"""

    def __init__(self, db_service):
        self.db = db_service

    async def get_trending_products(self, limit: int = 5, category: str = None) -> Dict[str, Any]:
        """Trending products by rating × reviews.

        The ``reviews::int`` cast is safe for today's catalog (numeric
        strings like "214"). If a future load introduces shorthand like
        "2.1k", swap the cast for a parse helper.
        """
        conditions = [
            'rating >= 4.0',
            "reviews::int > 50",
            '"imgUrl" IS NOT NULL',
        ]
        params: List[Any] = []

        if category:
            conditions.append("lower(category) LIKE %s ESCAPE '\\'")
            params.append(prepare_like_pattern(category))

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                "productId",
                name,
                brand,
                color,
                "imgUrl",
                price,
                rating,
                reviews,
                category,
                badge,
                tags,
                (reviews::int * rating) as trending_score
            FROM pellier.product_catalog
            WHERE {where_clause}
            ORDER BY trending_score DESC, rating DESC
            LIMIT %s
        """

        params.append(limit)
        results = await self.db.fetch_all(query, *params)

        products = [convert_decimals(dict(row)) for row in results]

        return {
            "status": "success",
            "count": len(products),
            "products": products,
            "metadata": {
                "criteria": "reviews * rating, min 4.0 rating, min 50 reviews",
                "limit": limit,
                "category_filter": category,
            },
        }

    async def check_inventory(self, product_query: Optional[str] = None) -> Dict[str, Any]:
        """Inventory check.

        Two modes:
          * ``product_query=None`` (default) — overall inventory health:
            stock counts, low-stock alerts, health score. Used for
            "what's running low" / "give me a stock overview" questions.
          * ``product_query="Hadley shirt"`` (or `"Pellier Linen Shirt"`) —
            per-warehouse breakdown for a single product. Resolves the query
            against ``product_catalog.name`` (ILIKE) and joins
            ``warehouse_inventory`` so Inventory Agent can answer "is the Hadley shirt
            (Pellier Linen Shirt in ecru) at the Brooklyn warehouse?" with concrete
            counts. Returns ambiguity error when more than one product
            matches; not_found when zero match.
        """
        if product_query:
            return await self._check_inventory_by_product(product_query)

        stats = await self.db.fetch_one("""
            SELECT
                COUNT(*)                                  AS total_products,
                SUM(quantity)                             AS total_units,
                COUNT(*) FILTER (WHERE quantity <= 5)     AS running_low_count,
                COUNT(*) FILTER (WHERE quantity = 0)      AS out_of_stock_count,
                ROUND(AVG(quantity), 1)                   AS avg_quantity
            FROM pellier.product_catalog
        """)
        stats = convert_decimals(dict(stats))

        critical = await self.db.fetch_all("""
            SELECT "productId", name, category, price, quantity
            FROM pellier.product_catalog
            WHERE quantity <= 5
            ORDER BY quantity ASC, rating DESC
            LIMIT 5
        """)
        critical_items = [convert_decimals(dict(r)) for r in critical]

        alerts = []
        for r in critical_items[:3]:
            qty = r.get("quantity", 0)
            label = "OUT OF STOCK" if qty == 0 else f"only {qty} left"
            alerts.append(f"{r['name']} — {label}")

        total = stats.get("total_products", 1) or 1
        low = stats.get("running_low_count", 0)
        oos = stats.get("out_of_stock_count", 0)
        health_score = round(max(0, 100 - oos * 10 - low * 3), 1)

        return {
            "status": "success",
            "health_score": health_score,
            "statistics": stats,
            "critical_items": critical_items,
            "alerts": alerts,
        }

    async def _check_inventory_by_product(self, product_query: str) -> Dict[str, Any]:
        """Per-warehouse breakdown for a named product.

        Implementation note: takes up to 5 ILIKE matches; if exactly one,
        returns the breakdown. If more than one, returns an ambiguity
        envelope with candidate names so the agent can ask the customer
        to disambiguate. If zero, returns not_found.
        """
        # Per-token ILIKE match on whitespace-split tokens — e.g. "Hadley shirt"
        # → `%Hadley%` AND `%shirt%` on catalog `name`. A single wrapped substring
        # would miss compounds like "Pellier Linen Shirt" when the shopper writes
        # "Pellier shirt".
        tokens = [t for t in product_query.strip().split() if t]
        if not tokens:
            return {
                "status": "not_found",
                "query": product_query,
                "message": "Empty product query.",
            }

        # Build "lower(name) LIKE %s ESCAPE '\' AND ..." with one
        # param per token so the trigram index on lower(name) can accelerate
        # fuzzy lookups at larger catalog sizes.
        clause = " AND ".join(["lower(name) LIKE %s ESCAPE '\\'"] * len(tokens))
        params = tuple(prepare_like_pattern(t) for t in tokens)

        rows = await self.db.fetch_all(
            f"""
            SELECT "productId", name, brand, color, price
              FROM pellier.product_catalog
             WHERE {clause}
             ORDER BY rating DESC NULLS LAST
             LIMIT 5
            """,
            *params,
        )
        candidates = [convert_decimals(dict(r)) for r in rows]

        if not candidates:
            return {
                "status": "not_found",
                "query": product_query,
                "message": (
                    f"No product matched '{product_query}'. "
                    "Inventory Agent can only break down inventory for products in the catalog."
                ),
            }

        if len(candidates) > 1:
            return {
                "status": "ambiguous",
                "query": product_query,
                "candidates": [
                    {
                        "productId": c["productId"],
                        "name": c["name"],
                        "brand": c.get("brand"),
                        "color": c.get("color"),
                    }
                    for c in candidates
                ],
                "message": (
                    f"Multiple products match '{product_query}'. "
                    "Ask the customer which one they mean before reporting stock."
                ),
            }

        product = candidates[0]
        product_id = product["productId"]

        # Per-warehouse breakdown
        wh_rows = await self.db.fetch_all(
            """
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
            """,
            product_id,
        )
        warehouses = [convert_decimals(dict(r)) for r in wh_rows]
        total_units = sum(w.get("quantity", 0) or 0 for w in warehouses)

        return {
            "status": "success",
            "product": {
                "productId": product_id,
                "name": product["name"],
                "brand": product.get("brand"),
                "color": product.get("color"),
                "price": product.get("price"),
            },
            "total_units": total_units,
            "warehouses": warehouses,
        }

    async def get_price_analysis(self, category: str = None) -> Dict[str, Any]:
        """Per-category price statistics."""
        params: List[Any] = []
        if category:
            cat_condition = "lower(category) LIKE %s ESCAPE '\\'"
            params.append(prepare_like_pattern(category))
            query = f"""
                SELECT
                    category,
                    COUNT(*) as product_count,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    AVG(price) as avg_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
                FROM pellier.product_catalog
                WHERE {cat_condition}
                GROUP BY category
            """
            results = await self.db.fetch_all(query, *params)
        else:
            query = """
                SELECT
                    category,
                    COUNT(*) as product_count,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    AVG(price) as avg_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
                FROM pellier.product_catalog
                GROUP BY category
                ORDER BY product_count DESC
                LIMIT 10
            """
            results = await self.db.fetch_all(query)

        categories = [convert_decimals(dict(row)) for row in results]

        overall_query = """
            SELECT
                COUNT(*) as total_products,
                MIN(price) as min_price,
                MAX(price) as max_price,
                AVG(price) as avg_price,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
            FROM pellier.product_catalog
        """

        overall = await self.db.fetch_one(overall_query)
        overall_dict = convert_decimals(dict(overall))

        return {
            "status": "success",
            "overall": overall_dict,
            "by_category": categories,
            "filter": category if category else "all",
        }

    async def initiate_return(
        self,
        customer_id: str,
        product_id: int,
        reason: str,
        idempotency_key: str,
        principal_sub: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Theo's idempotent return write, executed atomically in Aurora.

        The AgentCore CLI project attaches the managed Cedar engine to the
        Gateway in ENFORCE mode, so it can gate a managed call before the
        tool's Lambda ever runs.
        Governed requests execute this transaction through that Lambda;
        the builders format can execute it in-process. Both validate the
        canonical reason set here as a defense-in-depth guard.

        Ownership is gated *here*, not in Cedar — the principal/resource
        relationship is a SQL JOIN (``orders ⋈ customer + product``),
        not a static policy. Cedar gates *what* the agent can do; SQL
        gates *whose* state the agent is allowed to mutate. Two
        separate enforcement layers, two separate teaching surfaces.

        Two rails, chosen by ``principal_sub``:

        * **No principal** — the write runs on the ordinary connection, which
          belongs to the table owner and therefore bypasses Row-Level
          Security. This is the anonymous and simulated-persona path the
          storefront uses today, and it is why an agent on this rail can
          process *another* customer's return: the only gate is the
          ``customer_id`` argument, and the caller supplies that.
        * **Verified principal** — the write runs inside
          ``principal_session``, as a non-owner role with the principal bound
          transaction-locally, so RLS binds. The same request for another
          customer's return is refused by the database.

        Args:
            customer_id: Customer whose return is being processed.
            product_id: Product being returned.
            reason: Must be one of the canonical reasons.
            idempotency_key: Caller-supplied key; a repeat returns the first
                result rather than writing twice.
            principal_sub: Verified Cognito subject, or ``None`` for the
                owner rail. Never a persona id — a UI selection must not
                choose which rows are writable.

        Returns one of:
          {"status": "success",
           "return_id": int, "product_id": int, "name": str,
           "reason": str, "new_quantity": int | None}
          {"status": "error", "message": str}
          {"status": "policy_blocked", "message": str}  (defense-in-depth)
        """
        ALLOWED = {"damaged", "wrong_size", "not_as_described",
                   "changed_mind", "other"}
        if reason not in ALLOWED:
            return {
                "status": "policy_blocked",
                "message": (
                    f"Reason '{reason}' is not an allowed return reason. "
                    f"Allowed: {sorted(ALLOWED)}."
                ),
            }
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            return {"status": "error", "message": "idempotency_key is required."}
        request_hash = write_request_hash(
            "initiate_return",
            customer_id=str(customer_id),
            product_id=int(product_id),
            reason=str(reason),
        )
        sql = (
            "SELECT pellier.process_return_idempotent(%s, %s, %s, %s, %s) "
            "AS result"
        )
        params = (
            clean_key,
            request_hash,
            str(customer_id),
            str(product_id),
            str(reason),
        )

        if principal_sub is None:
            row = await self.db.fetch_one(sql, *params)
            result = row.get("result") if row else None
            if isinstance(result, str):
                result = json.loads(result)
        else:
            result = await self._initiate_return_governed(
                sql, params, customer_id=str(customer_id), principal_sub=principal_sub
            )

        return convert_decimals(result or {
            "status": "error",
            "message": "Return operation produced no result.",
        })

    async def _initiate_return_governed(
        self,
        sql: str,
        params: tuple,
        *,
        customer_id: str,
        principal_sub: str,
    ) -> Optional[Dict[str, Any]]:
        """Run the return write with RLS bound, and report denials honestly.

        The database stays the enforcer. This only translates one outcome that
        would otherwise be a false statement.

        ``process_return_idempotent`` establishes ownership by selecting the
        matching row from ``pellier.orders``. Under RLS that select is scoped
        to the principal, so a request for a customer outside that scope finds
        nothing and the function reports "Customer X did not order product Y".
        That message is wrong: the order may well exist. Reporting it would
        state a falsehood about Aurora's contents and would disguise an
        authorization boundary as a data fact — the conflation the denial
        taxonomy exists to prevent.

        So when the function reports not-ordered, we ask the database, inside
        the same transaction, whether that customer is in scope at all. If it
        is not, the outcome is an authorization denial and says so. If it is,
        the original message was true and stands.
        """
        async with self.db.principal_session(principal_sub) as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
                result = row.get("result") if row else None
                if isinstance(result, str):
                    result = json.loads(result)

                if not self._reports_not_ordered(result):
                    return result

                await cur.execute(
                    "SELECT count(*) AS in_scope FROM"
                    " pellier.current_principal_customers()"
                    " WHERE customer_id = %s",
                    (customer_id,),
                )
                scope_row = await cur.fetchone()
                in_scope = bool(scope_row and scope_row.get("in_scope"))

        if in_scope:
            return result

        return {
            "status": "policy_blocked",
            "message": (
                f"This session is not authorized to act on {customer_id}'s "
                "orders. The database refused the read the return depends on, "
                "so nothing was changed."
            ),
            "denied_by": "database_row_level_security",
        }

    @staticmethod
    def _reports_not_ordered(result: Optional[Dict[str, Any]]) -> bool:
        """True when the write function concluded the customer never ordered.

        Matches on the function's own phrasing rather than a status code
        because ``status: error`` covers several unrelated outcomes.
        """
        if not isinstance(result, dict) or result.get("status") != "error":
            return False
        return "did not order" in str(result.get("message", ""))

    async def restock_inventory(
        self,
        product_id: int,
        quantity: int,
        idempotency_key: str,
        warehouse_id: str = "BK-01",
    ) -> Dict[str, Any]:
        """Add inventory to one warehouse and recompute the catalog total."""
        if quantity <= 0:
            return {"status": "error", "message": "Quantity must be positive."}
        if quantity > 500:
            return {
                "status": "policy_blocked",
                "message": (
                    f"Restock of {quantity} units exceeds the 500-unit policy "
                    "limit. Split the order or get manager approval."
                ),
                "product_id": product_id,
            }
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            return {"status": "error", "message": "idempotency_key is required."}
        clean_warehouse = str(warehouse_id or "BK-01").strip() or "BK-01"
        request_hash = write_request_hash(
            "restock_inventory",
            product_id=int(product_id),
            quantity=int(quantity),
            warehouse_id=clean_warehouse,
        )
        row = await self.db.fetch_one(
            "SELECT pellier.restock_shelf_idempotent(%s, %s, %s, %s, %s) "
            "AS result",
            clean_key,
            request_hash,
            str(product_id),
            int(quantity),
            clean_warehouse,
        )
        result = row.get("result") if row else None
        if isinstance(result, str):
            result = json.loads(result)
        return convert_decimals(result or {
            "status": "error",
            "message": "Restock operation produced no result.",
        })

    async def search_products(
        self,
        query: str,
        max_price: float = None,
        min_rating: float = 0.0,
        category: str = None,
        min_similarity: float = 0.1,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Filtered semantic search with pgvector against the Pellier catalog schema."""
        from services.embeddings import EmbeddingService
        import time

        start_time = time.time()
        if not hasattr(self, "_embedding_service"):
            self._embedding_service = EmbeddingService()
        query_embedding = self._embedding_service.embed_query(query)
        embedding_time_ms = (time.time() - start_time) * 1000

        conditions = ['"imgUrl" IS NOT NULL']
        params: List[Any] = [str(query_embedding)]

        if max_price:
            conditions.append("price <= %s")
            params.append(max_price)

        if min_rating:
            conditions.append("rating >= %s")
            params.append(min_rating)

        if category:
            conditions.append("lower(category) LIKE %s ESCAPE '\\'")
            params.append(prepare_like_pattern(category))

        params.append(limit)
        where_clause = " AND ".join(conditions)

        search_query = f"""
            WITH query_embedding AS (SELECT %s::vector as emb)
            SELECT
                "productId",
                name,
                brand,
                color,
                description,
                price,
                rating,
                reviews,
                category,
                "imgUrl",
                badge,
                tags,
                1 - (embedding <=> (SELECT emb FROM query_embedding)) as similarity
            FROM pellier.product_catalog
            WHERE {where_clause}
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """

        db_start = time.time()
        results = await self.db.fetch_all(search_query, *params)
        db_time_ms = (time.time() - db_start) * 1000

        products = [convert_decimals(dict(row)) for row in results]

        if min_similarity > 0:
            products = [p for p in products if p.get("similarity", 0) >= min_similarity]

        return {
            "status": "success",
            "query": query,
            "count": len(products),
            "products": products,
            "filters": {
                "max_price": max_price,
                "min_rating": min_rating,
                "category": category,
                "min_similarity": min_similarity,
            },
            "performance": {
                "bedrock_embedding_ms": round(embedding_time_ms, 2),
                "database_query_ms": round(db_time_ms, 2),
                "total_ms": round(embedding_time_ms + db_time_ms, 2),
            },
            "sql_query": search_query.replace("%s", "?"),
            "note": "⚠️ This is a Pellier workshop tool for educational purposes",
        }

    async def get_products_by_category(
        self,
        category: str,
        min_rating: float = 4.0,
        max_price: float = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Browse products by category with rating and price filters."""
        conditions = [
            "lower(category) LIKE %s ESCAPE '\\'",
            '"imgUrl" IS NOT NULL',
        ]
        params: List[Any] = [prepare_like_pattern(category)]

        if min_rating:
            conditions.append("rating >= %s")
            params.append(min_rating)

        if max_price:
            conditions.append("price <= %s")
            params.append(max_price)

        params.append(limit)
        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                "productId",
                name,
                brand,
                color,
                price,
                rating,
                reviews,
                category,
                "imgUrl",
                badge,
                tags
            FROM pellier.product_catalog
            WHERE {where_clause}
            ORDER BY rating DESC, reviews::int DESC
            LIMIT %s
        """

        results = await self.db.fetch_all(query, *params)
        products = [convert_decimals(dict(row)) for row in results]

        return {
            "status": "success",
            "category": category,
            "count": len(products),
            "products": products,
            "filters": {
                "min_rating": min_rating,
                "max_price": max_price,
            },
        }

    async def get_low_stock(self, limit: int = 5) -> Dict[str, Any]:
        """Products running low on stock, sorted by quantity ascending."""
        rows = await self.db.fetch_all(
            """
            SELECT "productId", name, category, price, rating, quantity
            FROM pellier.product_catalog
            WHERE quantity <= 10
            ORDER BY quantity ASC, rating DESC
            LIMIT %s
            """,
            limit,
        )
        products = [convert_decimals(dict(r)) for r in rows]
        for p in products:
            qty = p.get("quantity", 0)
            p["restock_urgency"] = (
                "critical" if qty <= 2
                else "low" if qty <= 5
                else "watch"
            )
        return {
            "status": "success",
            "count": len(products),
            "products": products,
        }

    async def issue_credit(
        self,
        customer_id: str,
        amount_cents: int,
        reason: str,
        idempotency_key: str,
        issued_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue a goodwill store credit, applied exactly once.

        Service recovery is a money movement, so it gets its own durable row
        rather than being recorded as a note on a return. A return is not a
        credit, and an auditor asking "what did we pay out this quarter?"
        cannot answer it from the returns table.

        The write is delegated to ``pellier.apply_store_credit``, which claims
        the idempotency key in ``pellier.write_operations`` before touching
        ``pellier.store_credits``. So the evidence a credit produces is the
        same shape every other governed write produces.

        The $500 ceiling is enforced in two places on purpose: this function
        returns a readable ``policy_blocked`` envelope, and a CHECK constraint
        on the table refuses the row regardless of who is calling. A limit that
        lives only in a prompt or a tool schema is a suggestion.

        Args:
            customer_id: Customer receiving the credit, e.g. ``CUST-JESSICA``.
            amount_cents: Integer cents. Money in a float is a defect waiting
                for a rounding report to disagree with the ledger.
            reason: Why the credit was issued. Required; it lands in the audit.
            idempotency_key: Stable key for this intended write.
            issued_by: Verified operator ``sub``, when one is available.

        Returns:
            ``{"status": "success", ...}`` with the credit id, the new balance,
            and ``idempotent_replay``; or an ``error`` / ``policy_blocked`` /
            ``idempotency_conflict`` envelope.
        """
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            return {"status": "error", "message": "idempotency_key is required."}
        try:
            cents = int(amount_cents)
        except (TypeError, ValueError):
            return {
                "status": "error",
                "message": f"amount_cents must be an integer, got {amount_cents!r}.",
            }
        clean_reason = str(reason or "").strip()
        if not clean_reason:
            return {"status": "error", "message": "A reason is required for a credit."}

        request_hash = write_request_hash(
            "issue_credit",
            customer_id=str(customer_id),
            amount_cents=cents,
            reason=clean_reason,
        )
        row = await self.db.fetch_one(
            "SELECT pellier.apply_store_credit(%s, %s, %s, %s, %s, %s) AS result",
            clean_key,
            request_hash,
            str(customer_id),
            cents,
            clean_reason,
            str(issued_by or "") or None,
        )
        result = row.get("result") if row else None
        if isinstance(result, str):
            result = json.loads(result)
        return convert_decimals(result or {
            "status": "error",
            "message": "Credit operation produced no result.",
        })

    async def get_ticket_history(
        self,
        customer_id: str,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Past support interactions for one customer, newest first.

        Read-only context so the concierge can reason over what already
        happened instead of asking a client to repeat it.
        """
        rows = await self.db.fetch_all(
            """
            SELECT ticket_id, subject, status, channel, last_note,
                   opened_at, resolved_at
              FROM pellier.support_tickets
             WHERE customer_id = %s
             ORDER BY opened_at DESC
             LIMIT %s
            """,
            str(customer_id),
            int(limit),
        )
        tickets = [convert_decimals(dict(r)) for r in (rows or [])]
        for t in tickets:
            for field in ("opened_at", "resolved_at"):
                value = t.get(field)
                if value is not None and hasattr(value, "isoformat"):
                    t[field] = value.isoformat()
        return {
            "status": "success",
            "customer_id": str(customer_id),
            "count": len(tickets),
            "open_count": sum(
                1 for t in tickets if t.get("status") in ("open", "pending")
            ),
            "tickets": tickets,
        }

    async def personalized_search(
        self,
        query: str,
        preferences: Dict[str, Any] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Semantic search + preference-based boost re-ranking."""
        base_results = await self.search_products(query, limit=limit * 2)
        products = base_results.get("products", [])
        preferences = preferences or {}

        preferred_categories = [c.lower() for c in preferences.get("categories", [])]
        price_range = preferences.get("price_range", {})
        min_price = price_range.get("min")
        max_price = price_range.get("max")

        for product in products:
            reasons: List[str] = []
            boost = 0.0
            category = (product.get("category") or "").lower()

            if preferred_categories and any(pc in category for pc in preferred_categories):
                boost += 0.1
                reasons.append(
                    f"Matches your interest in {product.get('category', 'this category')}"
                )

            price = float(product.get("price", 0))
            if min_price is not None and max_price is not None:
                if min_price <= price <= max_price:
                    boost += 0.05
                    reasons.append(f"Within your ${min_price}–${max_price} budget")
            elif max_price is not None and price <= max_price:
                boost += 0.05
                reasons.append(f"Under your ${max_price} budget")

            rating = float(product.get("rating", 0))
            if rating >= 4.5:
                boost += 0.03
                reasons.append("Highly rated by customers")

            product["personalization_boost"] = round(boost, 3)
            product["recommendation_reasons"] = reasons
            original_sim = product.get("similarity", 0)
            product["personalized_score"] = round(original_sim + boost, 4)

        products.sort(key=lambda p: p.get("personalized_score", 0), reverse=True)
        products = products[:limit]

        return {
            "status": "success",
            "query": query,
            "count": len(products),
            "products": products,
            "preferences_applied": preferences,
            "personalization": True,
        }
