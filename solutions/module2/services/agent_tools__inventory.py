"""
Strands SDK Tools for Agents
Provides @tool decorated functions for agent use with live database access.
Uses pgvector semantic search (Module 1 teaching surface) — the hybrid +
Cohere Rerank pipeline was removed when the concierge switched to pure
semantic retrieval.
"""
from strands import tool
import contextvars
import json
import asyncio
import re

# Global service references
_db_service = None
_main_loop = None

def set_db_service(db_service):
    """Set the database service instance"""
    global _db_service
    _db_service = db_service

def set_main_loop(loop):
    """Store reference to the main uvicorn event loop for cross-thread dispatch"""
    global _main_loop
    _main_loop = loop

def _run_async(coro):
    """Run async coroutine from a sync context (e.g. Strands @tool in a background thread).

    Dispatches to the main uvicorn event loop via run_coroutine_threadsafe so that
    the AsyncConnectionPool (bound to the main loop) works correctly. Propagates
    the caller's ContextVars (e.g. ``db_query_log_var``) into the coroutine so
    per-turn telemetry buffers catch tool-initiated DB calls.
    """
    # Capture the current ContextVars (e.g. db_query_log_var) so the
    # coroutine runs with the same context even when dispatched to a
    # different event loop.
    ctx = contextvars.copy_context()

    async def _run_in_ctx():
        # Create a Task in the captured context; this ensures ContextVars
        # set by the caller (like db_query_log_var) are visible inside
        # the coroutine even though we crossed threads.
        return await asyncio.get_running_loop().create_task(coro, context=ctx)

    if _main_loop and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_run_in_ctx(), _main_loop)
        return future.result(timeout=30)
    # Fallback for standalone / test contexts where no main loop is set
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_run_in_ctx(), loop)
            return future.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

@tool
def floor_check() -> str:
    """Get current inventory health statistics including stock levels and alerts. Use for warehouse, stock status, or inventory overview questions."""
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.floor_check())
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def whats_trending(limit: int = 5, category: str = None) -> str:
    """Get the most popular and trending products, optionally filtered by category. Use when customers ask about bestsellers, what's hot, or popular items.

    Args:
        limit: Maximum number of products to return (default: 5)
        category: Optional category filter (e.g. "Electronics", "Shoes")

    Returns:
        JSON string with trending products

    ⏩ SHORT ON TIME? Run:
       cp solutions/module2/services/agent_tools.py blaize-bazaar/backend/services/agent_tools.py
    """
    # === CHALLENGE 2: START ===
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.whats_trending(limit, category))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
    # === CHALLENGE 2: END ===

@tool
def price_intelligence(category: str = None) -> str:
    """Get pricing statistics and price distribution analysis for a product category. Use for price comparisons, budget analysis, or average price questions."""
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.price_intelligence(category))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def restock_shelf(product_id: int, quantity: int) -> str:
    """Restock a specific product by adding inventory quantity. Use when an inventory manager needs to replenish stock for a product ID.

    Args:
        product_id: Integer productId (1-92 in the boutique catalog).
        quantity: Units to add to current stock.
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.restock_shelf(product_id, quantity))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

_CATEGORY_MAP = {
    # Boutique catalog categories (92 products, 9 categories)
    'linen': 'Linen', 'camp shirt': 'Linen', 'oxford': 'Linen',
    'dress': 'Dresses', 'gown': 'Dresses', 'sundress': 'Dresses', 'maxi': 'Dresses',
    'slip dress': 'Dresses', 'kaftan': 'Dresses', 'shirtdress': 'Dresses',
    'outerwear': 'Outerwear', 'jacket': 'Outerwear', 'cardigan': 'Outerwear',
    'vest': 'Outerwear', 'sweater': 'Outerwear', 'blazer': 'Outerwear',
    'trench': 'Outerwear', 'anorak': 'Outerwear', 'puffer': 'Outerwear',
    'shoe': 'Footwear', 'sneaker': 'Footwear', 'sandal': 'Footwear',
    'boot': 'Footwear', 'loafer': 'Footwear', 'runner': 'Footwear',
    'espadrille': 'Footwear', 'mule': 'Footwear', 'derby': 'Footwear',
    'footwear': 'Footwear', 'trail runner': 'Footwear',
    'accessory': 'Accessories', 'accessories': 'Accessories', 'hat': 'Accessories',
    'bracelet': 'Accessories', 'cuff': 'Accessories', 'earring': 'Accessories',
    'scarf': 'Accessories', 'pocket square': 'Accessories',
    'bag': 'Bags', 'tote': 'Bags', 'backpack': 'Bags', 'crossbody': 'Bags',
    'clutch': 'Bags', 'duffle': 'Bags', 'weekender': 'Bags', 'pouch': 'Bags',
    'handbag': 'Bags', 'purse': 'Bags',
    'home': 'Home', 'candle': 'Home', 'throw': 'Home', 'blanket': 'Home',
    'towel': 'Home', 'rug': 'Home', 'vase': 'Home', 'pillow': 'Home',
    'incense': 'Home', 'tumbler': 'Home', 'napkin': 'Home', 'duvet': 'Home',
    'pitcher': 'Home',
    'top': 'Tops', 'tee': 'Tops', 'blouse': 'Tops', 'camisole': 'Tops',
    'henley': 'Tops', 'polo': 'Tops', 'tank': 'Tops', 'shell': 'Tops',
    'button-down': 'Tops',
    'bottom': 'Bottoms', 'bottoms': 'Bottoms', 'trouser': 'Bottoms',
    'pant': 'Bottoms', 'skirt': 'Bottoms', 'denim': 'Bottoms',
    'palazzo': 'Bottoms', 'chino': 'Bottoms', 'corduroy': 'Bottoms',
}

def _detect_category(query: str) -> str | None:
    """Auto-detect product category from query keywords.
    
    Uses word-boundary matching so "what" doesn't match "hat".
    Prefers longer (more specific) keyword matches so "linen shirt"
    maps to Linen, not Tops. Handles common plural forms (s, es).
    """
    query_lower = query.lower()
    for keyword, cat_name in sorted(_CATEGORY_MAP.items(), key=lambda x: -len(x[0])):
        # Match keyword with optional trailing s/es for plurals
        pattern = r'(?<![a-z])' + re.escape(keyword) + r'(?:e?s)?(?![a-z])'
        if re.search(pattern, query_lower):
            return cat_name
    return None

@tool
def find_pieces(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5
) -> str:
    """Search for products by natural language query with optional price and rating filters. Use for descriptive or intent-based product searches.

    Args:
        query: Natural language search query
        max_price: Maximum price filter (optional)
        min_rating: Minimum star rating (default: 0.0)
        category: Category filter (optional — auto-detected from query if not set)
        limit: Number of results (default: 5)
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.vector_search import VectorSearch
        from services.embeddings import EmbeddingService

        # Auto-detect category from query if not provided
        if not category:
            category = _detect_category(query)

        embedding_service = EmbeddingService()
        query_embedding = embedding_service.embed_query(query)

        vector = VectorSearch(_db_service)

        # Concierge uses pure pgvector semantic search — the Module 1
        # teaching surface. The hybrid + rerank pipeline was removed
        # when the concierge switched to semantic-only retrieval.
        pool_size = 30 if category else 20
        rows = _run_async(
            vector.vector_search(query_embedding, pool_size, ef_search=40)
        )
        result = {"results": rows, "method": "semantic"}

        # Normalize field names and apply filters.
        products = result.get("results", [])
        normalized = []
        for p in products:
            reviews_raw = p.get("reviews")
            try:
                reviews_int = int(reviews_raw) if reviews_raw is not None else 0
            except (TypeError, ValueError):
                reviews_int = 0
            product = {
                "productId": p.get("product_id"),
                "name": p.get("name", ""),
                "brand": p.get("brand", ""),
                "color": p.get("color", ""),
                "description": p.get("description", ""),
                "price": float(p["price"]) if hasattr(p.get("price"), '__float__') else p.get("price", 0),
                "rating": float(p["rating"]) if hasattr(p.get("rating"), '__float__') else p.get("rating", 0),
                "reviews": reviews_int,
                "category": p.get("category", ""),
                "imgUrl": p.get("img_url", ""),
                "badge": p.get("badge"),
                "tags": list(p.get("tags") or []),
            }
            if max_price and product["price"] > max_price:
                continue
            if min_rating and product["rating"] < min_rating:
                continue
            if category and category.lower() not in product["category"].lower():
                continue
            normalized.append(product)

        # Trim to requested limit after filtering
        normalized = normalized[:limit]

        return json.dumps({
            "status": "success",
            "query": query,
            "count": len(normalized),
            "products": normalized,
            "search_method": result.get("method", "hybrid"),
            "category_detected": category,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def explore_collection(
    category: str,
    min_rating: float = 0.0,
    max_price: float = None,
    limit: int = 5
) -> str:
    """Browse products within a specific category with rating and price filters. Use when customers want to browse a known category.
    
    Args:
        category: Product category name
        min_rating: Minimum star rating (default: 4.0)
        max_price: Maximum price filter (optional)
        limit: Number of results (default: 10)
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.get_products_by_category(
            category, min_rating, max_price, limit
        ))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def running_low(limit: int = 5) -> str:
    """Get products that are running low on stock, prioritized by demand. Use to identify items that need restocking soon.

    Args:
        limit: Number of results (default: 5)
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.running_low(limit))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# === WIRE IT LIVE (Lab 2) ===
@tool
def side_by_side(product_id_1: int, product_id_2: int) -> str:
    """Compare two products side by side by their product IDs. Use when customers want to see differences in price, rating, and features.

    Args:
        product_id_1: First integer productId to compare (1-92 in the boutique catalog).
        product_id_2: Second integer productId to compare (1-92 in the boutique catalog).
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        query = """
            SELECT "productId", name, brand, color, description, price,
                   rating, reviews, category, "imgUrl", badge, tags
            FROM blaize_bazaar.product_catalog
            WHERE "productId" = %s
        """
        p1 = _run_async(_db_service.fetch_one(query, product_id_1))
        p2 = _run_async(_db_service.fetch_one(query, product_id_2))

        if not p1 or not p2:
            missing = []
            if not p1: missing.append(product_id_1)
            if not p2: missing.append(product_id_2)
            return json.dumps({"error": f"Product(s) not found: {', '.join(missing)}"})

        def fmt(row):
            reviews_raw = row.get("reviews")
            try:
                reviews_int = int(reviews_raw) if reviews_raw is not None else 0
            except (TypeError, ValueError):
                reviews_int = 0
            return {
                "productId": row.get("productId"),
                "name": row.get("name", ""),
                "brand": row.get("brand", ""),
                "color": row.get("color", ""),
                "price": float(row.get("price", 0)),
                "rating": float(row.get("rating", 0)),
                "reviews": reviews_int,
                "category": row.get("category", ""),
                "badge": row.get("badge"),
                "tags": list(row.get("tags") or []),
            }

        product_1 = fmt(p1)
        product_2 = fmt(p2)

        # Determine winner for each metric
        comparison = {
            "price_winner": product_1["productId"] if product_1["price"] <= product_2["price"] else product_2["productId"],
            "rating_winner": product_1["productId"] if product_1["rating"] >= product_2["rating"] else product_2["productId"],
            "reviews_winner": product_1["productId"] if product_1["reviews"] >= product_2["reviews"] else product_2["productId"],
            "price_difference": abs(product_1["price"] - product_2["price"]),
        }

        return json.dumps({
            "status": "success",
            "product_1": product_1,
            "product_2": product_2,
            "comparison": comparison,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
# === END WIRE IT LIVE ===


# === RETURN POLICY TOOL (backed by blaize_bazaar.return_policies table) ===

@tool
def returns_and_care(category: str = "default") -> str:
    """Look up the return and refund policy for a specific product category. Use when customers ask about returns, refunds, warranties, or return windows.

    Args:
        category: Product category name (e.g., "Electronics", "Shoes")

    Returns:
        JSON string with return policy details
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        query = """
            SELECT category_name, return_window_days, conditions, refund_method
            FROM blaize_bazaar.return_policies
            WHERE category_name = %s
        """
        row = _run_async(_db_service.fetch_one(query, category))

        if not row:
            row = _run_async(_db_service.fetch_one(query, "default"))

        if not row:
            return json.dumps({"error": f"No return policy found for category: {category}"})

        return json.dumps({
            "category": row["category_name"],
            "return_window_days": row["return_window_days"],
            "conditions": row["conditions"],
            "refund_method": row["refund_method"],
        })
    except Exception as e:
        return json.dumps({"error": f"Return policy lookup error: {str(e)}"})


@tool
def style_match(product_id: int, limit: int = 5) -> str:
    """Find complementary pieces that pair well with a given product.

    Uses pgvector cosine similarity to find products whose embeddings
    are closest to the given product's embedding — semantic style
    matching, not keyword overlap. Great for "what goes with this?"

    Args:
        product_id: The product to match against (1-40 in the curated catalog)
        limit: Number of matches to return (default: 5)

    Returns:
        JSON with the source product and its closest style matches,
        including cosine similarity scores.
    """
    try:
        source = _run_async(db_service.fetch_one(
            'SELECT "productId", name, brand, price, category_name, embedding '
            'FROM blaize_bazaar.product_catalog WHERE "productId" = %s',
            str(product_id).ljust(10),
        ))
        if not source:
            return json.dumps({"error": f"Product {product_id} not found"})
        if not source.get("embedding"):
            return json.dumps({"error": f"Product {product_id} has no embedding"})

        matches = _run_async(db_service.fetch_all(
            'SELECT "productId", name, brand, color, price, rating, reviews, '
            'category_name, "imgUrl", '
            '1 - (embedding <=> %s::vector) AS similarity_score '
            'FROM blaize_bazaar.product_catalog '
            'WHERE "productId" != %s '
            'ORDER BY embedding <=> %s::vector '
            'LIMIT %s',
            str(source["embedding"]), str(product_id).ljust(10),
            str(source["embedding"]), limit,
        ))

        return json.dumps({
            "source": {
                "productId": str(source["productId"]).strip(),
                "name": source["name"],
                "brand": source["brand"],
                "price": float(source["price"]),
            },
            "matches": [
                {
                    "productId": str(m["productId"]).strip(),
                    "name": m["name"],
                    "brand": m["brand"],
                    "color": m.get("color", ""),
                    "price": float(m["price"]),
                    "rating": float(m.get("rating", 0)),
                    "reviews": int(m.get("reviews", 0)),
                    "category": m.get("category_name", ""),
                    "imgUrl": m.get("imgUrl", ""),
                    "similarity_score": round(float(m.get("similarity_score", 0)), 4),
                }
                for m in matches
            ],
            "query_type": "pgvector_cosine_similarity",
            "index": "hnsw",
        })
    except Exception as e:
        logger.error(f"style_match error: {e}")
        return json.dumps({"error": str(e)})
