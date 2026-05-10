"""
Strands SDK Tools for Agents
Provides @tool decorated functions for agent use with live database access.

Two retrieval entry points:

  - ``find_pieces`` — Marco's foundation. Pure pgvector cosine
    similarity over the product catalog. Module 1 teaching surface.

  - ``find_pieces_hybrid`` — Anna's anchor capability. Hybrid
    pgvector + Postgres BM25 with RRF merge, then Cohere Rerank v3.5
    on the top 30. Module 1 hybrid teaching surface; granted only to
    the Curator agent (recommendation_agent.py).
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
    """Get current inventory health statistics including stock levels and alerts. Use for warehouse, stock status, or inventory overview questions.

    ⏩ SHORT ON TIME? Run:
       cp solutions/module2/services/agent_tools__inventory.py pellier/backend/services/agent_tools.py
    """
    # === CHALLENGE · Stock Keeper · floor_check: START ===
    # WORKSHOP_EXERCISE_STUB
    #
    # Wire this tool to BusinessLogic.floor_check() so Stock Keeper
    # can answer Marco's Turn 4: "Is the Pellier shirt at the
    # Brooklyn warehouse?"
    #
    # Steps:
    #   1. Guard on _db_service being initialized (return a JSON error
    #      if not).
    #   2. Import BusinessLogic from services.business_logic.
    #   3. Call logic.floor_check() via _run_async() — it's an async
    #      method.
    #   4. Return the result as a JSON string (use json.dumps with
    #      indent=2).
    #   5. Catch exceptions and return a JSON error envelope.
    #
    # Verify locally:
    #   cd pellier/backend
    #   pytest tests/test_agent_tools.py::test_floor_check -v
    #
    # Verify live:
    #   Click Marco Turn 4 pill in the Boutique — Stock Keeper answers
    #   with the Brooklyn warehouse breakdown.
    return json.dumps({
        "error": "floor_check is in stub state",
        "hint": "This is the workshop build. Implement the tool body or run the cp command above.",
    })
    # === CHALLENGE · Stock Keeper · floor_check: END ===

@tool
def whats_trending(limit: int = 5, category: str = None) -> str:
    """Get the most popular and trending products, optionally filtered by category. Use when customers ask about bestsellers, what's hot, or popular items.

    Args:
        limit: Maximum number of products to return (default: 5)
        category: Optional category filter (e.g. "Electronics", "Shoes")

    Returns:
        JSON string with trending products

    ⏩ SHORT ON TIME? Run:
       cp solutions/module2/services/agent_tools.py pellier/backend/services/agent_tools.py
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
        product_id: Integer productId (1-40 in the boutique catalog).
        quantity: Units to add to current stock.

    ⏩ SHORT ON TIME? Run:
       cp solutions/module2/services/agent_tools__inventory.py pellier/backend/services/agent_tools.py
    """
    # === CHALLENGE · Stock Keeper · restock_shelf: START ===
    # Workshop format ships with this block as a stub (see the original
    # `return json.dumps({"error": "...stub state"})` body below in the
    # commented-out reference). Builder's Session format and the
    # shipped solution path call BusinessLogic.restock_shelf live.
    #
    # Cedar policy `max-restock-quantity` enforces the 500-unit ceiling
    # via BeforeToolCallEvent — we don't need to enforce it here.
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.restock_shelf(product_id, quantity))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

    # Workshop stub reference (kept as a teaching artifact — participants
    # see this exact block in the workshop format and replace it with
    # the live wiring above):
    #
    # return json.dumps({
    #     "error": "restock_shelf is in stub state",
    #     "hint": "Workshop build — implement or run the cp command above.",
    # })
    # === CHALLENGE · Stock Keeper · restock_shelf: END ===


@tool
def process_return(customer_id: str, product_id: int, reason: str) -> str:
    """Process a customer return. Theo's Experience Guide uses this.

    Two enforcement layers:
      - Cedar policy ``process-return-allowed-reasons`` gates the
        reason value before this tool is invoked (BeforeToolCallEvent).
        Free-form reasons are rejected without ever reaching SQL.
      - SQL gates ownership inside the transaction. The customer must
        have an order row for this product. Cedar can't enforce
        ownership because it requires a JOIN against live data.

    If reason='damaged', the call also decrements
    pellier.product_catalog.quantity by 1 (defloored at 0). All
    three operations — ownership check, INSERT, conditional UPDATE —
    run in a single transaction.

    Args:
        customer_id: Salesforce-style customer ID (must exist in customers
            and must have an order for this product_id).
        product_id: INTEGER productId (1-40 in the boutique catalog).
        reason: One of 'damaged', 'wrong_size', 'not_as_described',
            'changed_mind', 'other'. Cedar enforces this set before
            the tool runs.
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.process_return(customer_id, product_id, reason))
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

        # Track whether the category was explicitly passed by the
        # agent vs. auto-detected from a keyword map. Auto-detected
        # categories (e.g. "linen" → "Linen") are speculative — the
        # boutique catalog uses higher-level taxonomy ("Apparel",
        # "Home Decor", "Accessories"), so a strict substring filter
        # on an auto-detected category drops every vector-search hit.
        # The query embedding already encodes the user's intent; we
        # use the detected category only for pool sizing, not as a
        # hard post-filter.
        category_was_explicit = bool(category)
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
            # Only apply category as a hard filter when the agent
            # explicitly passed one. Auto-detected categories filter
            # too aggressively against the boutique's higher-level
            # category taxonomy.
            if (
                category_was_explicit
                and category
                and category.lower() not in product["category"].lower()
            ):
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
def find_pieces_hybrid(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5,
) -> str:
    """Hybrid pgvector + Postgres BM25 + Cohere Rerank v3.5. Anna's Curator uses this.

    Three-stage retrieval:
      1. Vector branch (pgvector cosine) and BM25 branch (tsvector
         ts_rank_cd) run in parallel against pellier.product_catalog.
      2. Reciprocal Rank Fusion merges the two ranked lists into a
         single candidate pool of ~30 products.
      3. Cohere Rerank v3.5 reorders the pool by relevance to the
         original query and returns the top ``limit``.

    Each stage adds a different kind of signal:
      - Vector catches *meaning*: "something beautiful" → editorial pieces
      - BM25 catches *literals*: "candle" → only candle-shaped products
      - Rerank catches *coherence*: "for a slow Sunday morning" → the
        ceramic mug pulls ahead of the lounge set when the candidate
        pool included both

    Args:
        query: Natural language search query
        max_price: Maximum price filter (optional, applied post-rerank)
        min_rating: Minimum star rating (default: 0.0, applied post-rerank)
        category: Category filter (optional — only applied as a hard
            filter when the agent passes it explicitly, mirroring
            find_pieces' behavior)
        limit: Number of final results (default: 5)
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.embeddings import EmbeddingService
        from services.hybrid_search import HybridSearch
        from services.rerank import get_rerank_service

        # Same explicit-vs-auto category guard as find_pieces. Anna's
        # auto-detected categories ("linen" → "Linen") still don't match
        # the boutique's higher-level taxonomy ("Apparel"); only filter
        # when the agent supplies an explicit category.
        category_was_explicit = bool(category)

        embedding_service = EmbeddingService()
        query_embedding = embedding_service.embed_query(query)

        hybrid = HybridSearch(_db_service)
        # Pool size 30 — enough material for the reranker to reorder
        # meaningfully; Cohere bills per call, not per candidate.
        candidates = _run_async(
            hybrid.search(
                query=query,
                query_embedding=query_embedding,
                k_vector=20,
                k_bm25=20,
                top_n=30,
            )
        )

        # Build the per-document text the reranker reads. Three fields
        # in priority order: name (carries brand identity), description
        # (carries style + use case), category (coarse semantic anchor).
        # Truncate descriptions at 240 chars to stay well below Cohere's
        # per-document token limit.
        def _doc_for_rerank(p: dict) -> str:
            name = (p.get("name") or "").strip()
            desc = (p.get("description") or "").strip()
            cat = (p.get("category") or "").strip()
            if len(desc) > 240:
                desc = desc[:237] + "…"
            return f"{name} — {desc} ({cat})"

        documents = [_doc_for_rerank(p) for p in candidates]
        rerank_service = get_rerank_service()
        rerank_results = rerank_service.rerank(
            query=query,
            documents=documents,
            top_n=min(limit * 3, len(documents)),  # over-rerank then filter
        )

        # Project candidates by reranked indices. If rerank failed
        # (returned []), fall back to RRF order — the Atelier will show
        # this as a missing rerank stage in telemetry.
        if rerank_results:
            ordered = [
                {**candidates[r["index"]],
                 "rerank_score": float(r["relevance_score"])}
                for r in rerank_results
            ]
            search_method = "hybrid+rerank"
        else:
            ordered = [{**c, "rerank_score": None} for c in candidates]
            search_method = "hybrid (rerank fallback to RRF order)"

        # Normalize field shapes to match find_pieces output.
        normalized = []
        for p in ordered:
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
                "rrf_score": p.get("rrf_score"),
                "rerank_score": p.get("rerank_score"),
            }
            if max_price and product["price"] > max_price:
                continue
            if min_rating and product["rating"] < min_rating:
                continue
            if (
                category_was_explicit
                and category
                and category.lower() not in product["category"].lower()
            ):
                continue
            normalized.append(product)

        normalized = normalized[:limit]

        return json.dumps({
            "status": "success",
            "query": query,
            "count": len(normalized),
            "products": normalized,
            "search_method": search_method,
            "pool_size": len(candidates),
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

    ⏩ SHORT ON TIME? Run:
       cp solutions/module2/services/agent_tools__inventory.py pellier/backend/services/agent_tools.py
    """
    # === CHALLENGE · Stock Keeper · running_low: START ===
    # WORKSHOP_EXERCISE_STUB (Workshop format only — Builder's session
    # pre-applies this via CloudFormation UserData.)
    #
    # Wire this tool to BusinessLogic.running_low(limit). Returns
    # products with quantity <= 5 ranked by rating.
    return json.dumps({
        "error": "running_low is in stub state",
        "hint": "Workshop build — implement or run the cp command above.",
    })
    # === CHALLENGE · Stock Keeper · running_low: END ===


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
            FROM pellier.product_catalog
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


# === RETURN POLICY TOOL (backed by pellier.return_policies table) ===

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
            FROM pellier.return_policies
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
            'FROM pellier.product_catalog WHERE "productId" = %s',
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
            'FROM pellier.product_catalog '
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
