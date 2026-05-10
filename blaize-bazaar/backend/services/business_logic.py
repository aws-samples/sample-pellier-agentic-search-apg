"""
Business Logic Layer for Blaize Bazaar
Contains custom business logic for pricing, trending, inventory, and
category analysis.

Aligned to the boutique catalog schema:
    productId, name, brand, color, price, description, category, tags,
    rating, reviews (TEXT), "imgUrl", badge, tier, image_verified,
    quantity, embedding, created_at, updated_at

The ``quantity`` column was added by migration 004_add_quantity.sql
with realistic stock numbers seeded by tier + rating. Stock-level
functions (floor_check, running_low, restock_shelf) now issue
real SQL against this column.
"""
from typing import Dict, Any, List, Optional
from decimal import Decimal


def convert_decimals(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    return obj


class BusinessLogic:
    """Business logic layer for custom analytics and operations"""

    def __init__(self, db_service):
        self.db = db_service

    async def whats_trending(self, limit: int = 5, category: str = None) -> Dict[str, Any]:
        """Trending products by rating × reviews.

        The ``reviews::int`` cast is safe for today's catalog (numeric
        strings like "214"). If a future load introduces shorthand like
        "2.1k", swap the cast for a parse helper.
        """
        conditions = ['rating >= 4.0', "reviews::int > 50", '"imgUrl" IS NOT NULL']
        params: List[Any] = []

        if category:
            conditions.append("category ILIKE %s")
            params.append(f"%{category}%")

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
            FROM blaize_bazaar.product_catalog
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

    async def floor_check(self) -> Dict[str, Any]:
        """Overall inventory health — stock counts, low-stock alerts, health score."""
        stats = await self.db.fetch_one("""
            SELECT
                COUNT(*)                                  AS total_products,
                SUM(quantity)                             AS total_units,
                COUNT(*) FILTER (WHERE quantity <= 5)     AS running_low_count,
                COUNT(*) FILTER (WHERE quantity = 0)      AS out_of_stock_count,
                ROUND(AVG(quantity), 1)                   AS avg_quantity
            FROM blaize_bazaar.product_catalog
        """)
        stats = convert_decimals(dict(stats))

        critical = await self.db.fetch_all("""
            SELECT "productId", name, category, price, quantity
            FROM blaize_bazaar.product_catalog
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

    async def price_intelligence(self, category: str = None) -> Dict[str, Any]:
        """Per-category price statistics."""
        params: List[Any] = []
        if category:
            cat_condition = "category ILIKE %s"
            params.append(f"%{category}%")
            query = f"""
                SELECT
                    category,
                    COUNT(*) as product_count,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    AVG(price) as avg_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
                FROM blaize_bazaar.product_catalog
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
                FROM blaize_bazaar.product_catalog
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
            FROM blaize_bazaar.product_catalog
        """

        overall = await self.db.fetch_one(overall_query)
        overall_dict = convert_decimals(dict(overall))

        return {
            "status": "success",
            "overall": overall_dict,
            "by_category": categories,
            "filter": category if category else "all",
        }

    async def process_return(
        self,
        customer_id: str,
        product_id: int,
        reason: str,
    ) -> Dict[str, Any]:
        """Theo's anchor write. Atomic: ownership check → INSERT into
        ``returns`` → (if reason='damaged') decrement product_catalog.quantity.

        Cedar policy ``process-return-allowed-reasons`` (in
        agentcore_policy.py) gates the *reason value* before this method
        is ever called. We still validate inside the SQL CHECK and as
        a defense-in-depth guard here so a misbehaving agent that
        bypasses Cedar can't write garbage.

        Ownership is gated *here*, not in Cedar — the principal/resource
        relationship is a SQL JOIN (``orders ⋈ customer + product``),
        not a static policy. Cedar gates *what* the agent can do; SQL
        gates *whose* state the agent is allowed to mutate. Two
        separate enforcement layers, two separate teaching surfaces.

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

        # Single transaction so the ownership check, INSERT, and
        # conditional quantity decrement either all succeed or all fail.
        # If any step raises, psycopg's context manager rolls back.
        async with self.db.get_connection() as conn:
            async with conn.cursor() as cur:
                # 1. Ownership: customer must have ordered this product.
                #    LIMIT 1 because we only need existence, not count.
                await cur.execute(
                    "SELECT 1 FROM orders "
                    "WHERE customer_id = %s AND product_id = %s "
                    "LIMIT 1",
                    [customer_id, product_id],
                )
                owns = await cur.fetchone()
                if not owns:
                    return {
                        "status": "error",
                        "message": (
                            f"Customer {customer_id} did not order product "
                            f"{product_id}; cannot process return."
                        ),
                    }

                # 2. INSERT the return row, capture the id.
                await cur.execute(
                    "INSERT INTO returns (customer_id, product_id, reason) "
                    "VALUES (%s, %s, %s) "
                    "RETURNING id",
                    [customer_id, product_id, reason],
                )
                ins = await cur.fetchone()
                return_id = ins["id"] if ins else None

                # 3. If damaged, decrement product_catalog.quantity by 1
                #    (defloor at 0 — never go negative).
                new_quantity: Optional[int] = None
                product_name: Optional[str] = None
                if reason == "damaged":
                    await cur.execute(
                        'UPDATE blaize_bazaar.product_catalog '
                        'SET quantity = GREATEST(quantity - 1, 0), '
                        '    updated_at = NOW() '
                        'WHERE "productId" = %s '
                        'RETURNING "productId", name, quantity',
                        [product_id],
                    )
                    upd = await cur.fetchone()
                    if upd:
                        new_quantity = int(upd["quantity"])
                        product_name = upd["name"]
                else:
                    # Still fetch the product name for the success payload.
                    await cur.execute(
                        'SELECT "productId", name FROM blaize_bazaar.product_catalog '
                        'WHERE "productId" = %s',
                        [product_id],
                    )
                    sel = await cur.fetchone()
                    product_name = sel["name"] if sel else None

        return {
            "status": "success",
            "return_id": return_id,
            "product_id": product_id,
            "name": product_name,
            "reason": reason,
            "new_quantity": new_quantity,
        }

    async def restock_shelf(self, product_id: int, quantity: int) -> Dict[str, Any]:
        """Add `quantity` units to a product's stock. Returns the new total."""
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

        row = await self.db.fetch_one(
            'UPDATE blaize_bazaar.product_catalog '
            'SET quantity = quantity + %s, updated_at = NOW() '
            'WHERE "productId" = %s '
            'RETURNING "productId", name, quantity',
            quantity, product_id,
        )
        if not row:
            return {"status": "error", "message": f"Product {product_id} not found."}

        result = convert_decimals(dict(row))
        return {
            "status": "success",
            "product_id": result["productId"],
            "name": result["name"],
            "new_quantity": result["quantity"],
            "added": quantity,
        }

    async def find_pieces(
        self,
        query: str,
        max_price: float = None,
        min_rating: float = 0.0,
        category: str = None,
        min_similarity: float = 0.1,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Filtered semantic search with pgvector against the boutique schema."""
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
            conditions.append("category ILIKE %s")
            params.append(f"%{category}%")

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
            FROM blaize_bazaar.product_catalog
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
            "note": "⚠️ This is a Blaize Bazaar workshop tool for educational purposes",
        }

    async def get_products_by_category(
        self,
        category: str,
        min_rating: float = 4.0,
        max_price: float = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Browse products by category with rating and price filters."""
        conditions = ["category ILIKE %s", '"imgUrl" IS NOT NULL']
        params: List[Any] = [f"%{category}%"]

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
            FROM blaize_bazaar.product_catalog
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

    async def running_low(self, limit: int = 5) -> Dict[str, Any]:
        """Products running low on stock, sorted by quantity ascending."""
        rows = await self.db.fetch_all(
            """
            SELECT "productId", name, category, price, rating, quantity
            FROM blaize_bazaar.product_catalog
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

    async def personalized_search(
        self,
        query: str,
        preferences: Dict[str, Any] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Semantic search + preference-based boost re-ranking."""
        base_results = await self.find_pieces(query, limit=limit * 2)
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
