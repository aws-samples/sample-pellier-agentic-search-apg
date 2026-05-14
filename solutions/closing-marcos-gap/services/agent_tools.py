"""
Strands SDK Tools for Agents
Provides @tool decorated functions for agent use with live database access.
Uses hybrid search (vector + keyword + Cohere Rerank) for maximum relevance.
"""
from strands import tool
import json
import asyncio

# Global service references
_db_service = None
_rerank_service = None
_main_loop = None

def set_db_service(db_service):
    """Set the database service instance"""
    global _db_service
    _db_service = db_service

def set_rerank_service(rerank_service):
    """Set the rerank service instance for hybrid search"""
    global _rerank_service
    _rerank_service = rerank_service

def set_main_loop(loop):
    """Store reference to the main uvicorn event loop for cross-thread dispatch"""
    global _main_loop
    _main_loop = loop

def _run_async(coro):
    """Run async coroutine from a sync context (e.g. Strands @tool in a background thread).

    Dispatches to the main uvicorn event loop via run_coroutine_threadsafe so that
    the AsyncConnectionPool (bound to the main loop) works correctly.
    """
    if _main_loop and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        return future.result(timeout=30)
    # Fallback for standalone / test contexts where no main loop is set
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
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
def get_inventory_health() -> str:
    """Get current inventory health statistics with live data from database"""
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.get_inventory_health())
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def get_trending_products(limit: int = 5, category: str = None) -> str:
    """Get the most popular and trending products, optionally filtered by category. Use when customers ask about bestsellers, what's hot, or popular items.

    Args:
        limit: Maximum number of products to return (default: 5)
        category: Optional category filter (e.g. "Electronics", "Shoes")

    Returns:
        JSON string with trending products

    ⏩ SHORT ON TIME? Run:
       cp solutions/closing-marcos-gap/services/agent_tools.py pellier/backend/services/agent_tools.py
    """
    # === CHALLENGE 2: START ===
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.get_trending_products(limit, category))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
    # === CHALLENGE 2: END ===

@tool
def get_price_analysis(category: str = None) -> str:
    """Get category price analysis with live data from database (matches Part 2 notebook)"""
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.get_price_analysis(category))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def restock_product(product_id: str, quantity: int) -> str:
    """Restock a product in database with live execution"""
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})
    
    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.restock_product(product_id, quantity))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

_CATEGORY_MAP = {
    'fragrance': 'Fragrances', 'perfume': 'Fragrances', 'cologne': 'Fragrances',
    'laptop': 'Laptops', 'macbook': 'Laptops', 'notebook': 'Laptops', 'computer': 'Laptops',
    'phone': 'Smartphones', 'smartphone': 'Smartphones', 'iphone': 'Smartphones', 'samsung galaxy': 'Smartphones',
    'watch': 'Watches', 'rolex': 'Watches', 'timepiece': 'Watches',
    'shoe': 'Shoes', 'sneaker': 'Shoes', 'nike': 'Shoes', 'jordan': 'Shoes',
    'furniture': 'Furniture', 'sofa': 'Furniture', 'bed': 'Furniture', 'table': 'Furniture', 'chair': 'Furniture',
    'kitchen': 'Kitchen Accessories', 'pan': 'Kitchen Accessories', 'knife': 'Kitchen Accessories', 'cookware': 'Kitchen Accessories', 'spatula': 'Kitchen Accessories',
    'sunglasses': 'Sunglasses', 'shades': 'Sunglasses',
    'bag': 'Bags', 'handbag': 'Bags', 'backpack': 'Bags', 'purse': 'Bags',
    'dress': 'Dresses', 'gown': 'Dresses',
    'shirt': 'Shirts', 'tshirt': 'Shirts', 'polo': 'Shirts',
    'top': 'Tops', 'crop top': 'Tops', 'blouse': 'Tops',
    'sports': 'Sports Accessories', 'football': 'Sports Accessories', 'basketball': 'Sports Accessories', 'yoga': 'Sports Accessories',
    'tablet': 'Tablets', 'ipad': 'Tablets',
    'beauty': 'Beauty', 'mascara': 'Beauty', 'lipstick': 'Beauty', 'makeup': 'Beauty',
    'skin care': 'Skin Care', 'lotion': 'Skin Care', 'moisturizer': 'Skin Care',
    'motorcycle': 'Motorcycle', 'helmet': 'Motorcycle',
    'vehicle': 'Vehicle', 'car': 'Vehicle', 'tesla': 'Vehicle',
    'jewel': 'Jewellery', 'earring': 'Jewellery', 'necklace': 'Jewellery', 'bracelet': 'Jewellery', 'ring': 'Jewellery',
    'grocer': 'Groceries', 'food': 'Groceries', 'snack': 'Groceries',
    'mobile': 'Mobile Accessories', 'charger': 'Mobile Accessories', 'power bank': 'Mobile Accessories',
    'headphone': 'Mobile Accessories', 'headphones': 'Mobile Accessories', 'earbuds': 'Mobile Accessories', 'earphone': 'Mobile Accessories',
    'candle': 'Home Decoration', 'decor': 'Home Decoration', 'decoration': 'Home Decoration',
}

def _detect_category(query: str) -> str | None:
    """Auto-detect product category from query keywords."""
    query_lower = query.lower()
    for keyword, cat_name in _CATEGORY_MAP.items():
        if keyword in query_lower:
            return cat_name
    return None

@tool
def search_products(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5
) -> str:
    """Search products using hybrid AI search (semantic + keyword + reranking) for best relevance.

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
        from services.hybrid_search import HybridSearchService
        from services.embeddings import EmbeddingService

        # Auto-detect category from query if not provided
        if not category:
            category = _detect_category(query)

        embedding_service = EmbeddingService()
        query_embedding = embedding_service.embed_query(query)

        hybrid = HybridSearchService(_db_service)

        # Fetch more candidates so post-filtering still yields enough results
        pool_size = 30 if category else 20

        if _rerank_service:
            result = _run_async(hybrid.search_with_rerank(
                query=query,
                embedding=query_embedding,
                rerank_service=_rerank_service,
                limit=pool_size,
                candidate_pool_size=pool_size,
            ))
        else:
            result = _run_async(hybrid.search(
                query=query,
                embedding=query_embedding,
                limit=pool_size,
            ))

        # Normalize field names and apply filters
        products = result.get("results", [])
        normalized = []
        for p in products:
            product = {
                "productId": p.get("product_id", ""),
                "product_description": p.get("product_description", ""),
                "price": float(p["price"]) if hasattr(p.get("price"), '__float__') else p.get("price", 0),
                "stars": float(p["rating"]) if hasattr(p.get("rating"), '__float__') else p.get("rating", 0),
                "reviews": p.get("reviews", 0),
                "category_name": p.get("category_name", ""),
                "quantity": p.get("quantity", 0),
                "imgUrl": p.get("img_url", ""),
                "productURL": p.get("product_url", ""),
            }
            if max_price and product["price"] > max_price:
                continue
            if min_rating and product["stars"] < min_rating:
                continue
            if category and category.lower() not in product["category_name"].lower():
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
def get_product_by_category(
    category: str,
    min_rating: float = 0.0,
    max_price: float = None,
    limit: int = 5
) -> str:
    """Get products by category with filters
    
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
def get_low_stock_products(limit: int = 3) -> str:
    """Get products with low stock (quantity < 10) prioritized by demand

    Args:
        limit: Number of results (default: 3)
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        from services.business_logic import BusinessLogic
        logic = BusinessLogic(_db_service)
        result = _run_async(logic.get_low_stock_products(limit))
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# === WIRE IT LIVE (Lab 2) ===
@tool
def compare_products(product_id_1: str, product_id_2: str) -> str:
    """Compare two products side by side by their product IDs.

    Args:
        product_id_1: First product ID to compare
        product_id_2: Second product ID to compare
    """
    if not _db_service:
        return json.dumps({"error": "Database service not initialized"})

    try:
        query = """
            SELECT "productId", product_description, price, stars, reviews,
                   category_name, quantity, "imgUrl", "productURL"
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
            return {
                "productId": row.get("productId", ""),
                "name": row.get("product_description", "").split(" — ")[0].split(" - ")[0],
                "price": float(row.get("price", 0)),
                "stars": float(row.get("stars", 0)),
                "reviews": int(row.get("reviews", 0)),
                "category": row.get("category_name", ""),
                "inStock": int(row.get("quantity", 0)) > 0,
                "quantity": int(row.get("quantity", 0)),
            }

        product_1 = fmt(p1)
        product_2 = fmt(p2)

        # Determine winner for each metric
        comparison = {
            "price_winner": product_1["productId"] if product_1["price"] <= product_2["price"] else product_2["productId"],
            "rating_winner": product_1["productId"] if product_1["stars"] >= product_2["stars"] else product_2["productId"],
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
def get_return_policy(category: str = "default") -> str:
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
