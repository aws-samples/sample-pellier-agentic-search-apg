"""
Business Logic Layer for Pellier
Contains custom business logic for inventory, pricing, and trending analysis
"""
from typing import Dict, Any, List
from decimal import Decimal
import json


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
    
    async def get_trending_products(self, limit: int = 5, category: str = None) -> Dict[str, Any]:
        """
        Get trending products based on reviews, ratings, and popularity.

        Trending score = (reviews * stars) with high-rated products prioritized

        Args:
            limit: Number of trending products to return
            category: Optional category filter

        Returns:
            Dictionary with trending products and metadata
        """
        conditions = ["quantity > 0", "stars >= 4.0", "reviews > 50"]
        params: list = []

        if category:
            conditions.append("category_name ILIKE %s")
            params.append(f"%{category}%")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                "productId",
                product_description,
                price,
                stars,
                reviews,
                category_name,
                quantity,
                "productURL" as product_url,
                (reviews * stars) as trending_score
            FROM pellier.product_catalog
            WHERE {where_clause}
            ORDER BY trending_score DESC, stars DESC
            LIMIT %s
        """
        
        results = await self.db.fetch_all(query, limit)
        
        products = [convert_decimals(dict(row)) for row in results]
        
        return {
            "status": "success",
            "count": len(products),
            "products": products,
            "metadata": {
                "criteria": "reviews * stars, min 4.0 stars, min 50 reviews",
                "limit": limit
            }
        }
    
    async def get_inventory_health(self) -> Dict[str, Any]:
        """
        Get overall inventory health statistics.
        
        Returns:
            Dictionary with inventory health metrics and alerts
        """
        # Get inventory statistics
        stats_query = """
            SELECT 
                COUNT(*) as total_products,
                COUNT(CASE WHEN quantity = 0 THEN 1 END) as out_of_stock,
                COUNT(CASE WHEN quantity > 0 AND quantity < 10 THEN 1 END) as low_stock,
                COUNT(CASE WHEN quantity >= 10 THEN 1 END) as healthy_stock,
                AVG(quantity) as avg_quantity,
                SUM(quantity) as total_quantity
            FROM pellier.product_catalog
        """
        
        stats = await self.db.fetch_one(stats_query)
        stats_dict = convert_decimals(dict(stats))
        
        # Get critical items (low stock with high demand)
        critical_query = """
            SELECT 
                "productId",
                product_description,
                stars,
                reviews,
                quantity
            FROM pellier.product_catalog
            WHERE quantity < 10
              AND stars >= 4.0
              AND reviews > 100
            ORDER BY quantity ASC, reviews DESC
            LIMIT 10
        """
        
        critical_items = await self.db.fetch_all(critical_query)
        
        # Calculate health score (0-100)
        total = stats_dict['total_products']
        healthy = stats_dict['healthy_stock']
        health_score = int((healthy / total * 100)) if total > 0 else 0
        
        return {
            "status": "success",
            "health_score": health_score,
            "statistics": stats_dict,
            "critical_items": [convert_decimals(dict(row)) for row in critical_items],
            "alerts": self._generate_inventory_alerts(stats_dict)
        }
    
    async def get_price_analysis(self, category: str = None) -> Dict[str, Any]:
        """
        Get price statistics by category or overall.
        
        Args:
            category: Optional category filter
            
        Returns:
            Dictionary with price statistics and insights
        """
        if category:
            query = """
                SELECT 
                    category_name,
                    COUNT(*) as product_count,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    AVG(price) as avg_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
                FROM pellier.product_catalog
                WHERE category_name ILIKE %s
                  AND quantity > 0
                GROUP BY category_name
            """
            results = await self.db.fetch_all(query, f"%{category}%")
        else:
            query = """
                SELECT 
                    category_name,
                    COUNT(*) as product_count,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    AVG(price) as avg_price,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
                FROM pellier.product_catalog
                WHERE quantity > 0
                GROUP BY category_name
                ORDER BY product_count DESC
                LIMIT 10
            """
            results = await self.db.fetch_all(query)
        
        categories = [convert_decimals(dict(row)) for row in results]
        
        # Calculate overall statistics
        overall_query = """
            SELECT 
                COUNT(*) as total_products,
                MIN(price) as min_price,
                MAX(price) as max_price,
                AVG(price) as avg_price,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price) as median_price
            FROM pellier.product_catalog
            WHERE quantity > 0
        """
        
        overall = await self.db.fetch_one(overall_query)
        overall_dict = convert_decimals(dict(overall))
        
        return {
            "status": "success",
            "overall": overall_dict,
            "by_category": categories,
            "filter": category if category else "all"
        }
    
    async def restock_product(self, product_id: str, quantity: int) -> Dict[str, Any]:
        """
        Add stock to a product.
        
        Args:
            product_id: Product ID to restock
            quantity: Quantity to add
            
        Returns:
            Dictionary with restock confirmation
        """
        # Get current product info
        product_query = """
            SELECT "productId", product_description, quantity
            FROM pellier.product_catalog
            WHERE "productId" = %s
        """
        
        product = await self.db.fetch_one(product_query, product_id)
        
        if not product:
            return {
                "status": "error",
                "message": f"Product {product_id} not found"
            }
        
        old_quantity = product['quantity']
        new_quantity = old_quantity + quantity
        
        # Update quantity
        update_query = """
            UPDATE pellier.product_catalog
            SET quantity = quantity + %s
            WHERE "productId" = %s
        """
        
        await self.db.execute_query(update_query, quantity, product_id)
        
        return {
            "status": "success",
            "product_id": product_id,
            "product_name": product['product_description'],
            "old_quantity": old_quantity,
            "added_quantity": quantity,
            "new_quantity": new_quantity,
            "message": f"✅ Added {quantity} units to {product['product_description']}"
        }
    
    async def search_products(
        self,
        query: str,
        max_price: float = None,
        min_rating: float = 0.0,
        category: str = None,
        min_similarity: float = 0.1,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search products using semantic embeddings and pgvector similarity.

        Args:
            query: Natural language search query
            max_price: Maximum price filter
            min_rating: Minimum star rating
            category: Category filter
            min_similarity: Minimum similarity score (0-1) to filter out irrelevant results
            limit: Number of results
        """
        from services.embeddings import EmbeddingService
        import time

        # Generate query embedding with timing (reuse cached singleton)
        start_time = time.time()
        if not hasattr(self, '_embedding_service'):
            self._embedding_service = EmbeddingService()
        query_embedding = self._embedding_service.embed_query(query)
        embedding_time_ms = (time.time() - start_time) * 1000
        
        # Auto-detect category from query if not explicitly provided
        if not category:
            query_lower = query.lower()
            category_map = {
                'fragrance': 'Fragrances', 'perfume': 'Fragrances', 'cologne': 'Fragrances',
                'laptop': 'Laptops', 'macbook': 'Laptops', 'notebook': 'Laptops',
                'phone': 'Smartphones', 'smartphone': 'Smartphones', 'iphone': 'Smartphones', 'samsung galaxy': 'Smartphones',
                'watch': 'Watches', 'rolex': 'Watches', 'timepiece': 'Watches',
                'shoe': 'Shoes', 'sneaker': 'Shoes', 'nike': 'Shoes', 'jordan': 'Shoes',
                'furniture': 'Furniture', 'sofa': 'Furniture', 'bed': 'Furniture', 'table': 'Furniture',
                'kitchen': 'Kitchen Accessories', 'pan': 'Kitchen Accessories', 'knife': 'Kitchen Accessories',
                'sunglasses': 'Sunglasses', 'shades': 'Sunglasses',
                'bag': 'Bags', 'handbag': 'Bags', 'backpack': 'Bags',
                'dress': 'Dresses', 'gown': 'Dresses',
                'shirt': 'Shirts', 'tshirt': 'Shirts',
                'sports': 'Sports Accessories', 'football': 'Sports Accessories', 'basketball': 'Sports Accessories',
                'tablet': 'Tablets', 'ipad': 'Tablets',
                'beauty': 'Beauty', 'mascara': 'Beauty', 'lipstick': 'Beauty',
                'skin care': 'Skin Care', 'lotion': 'Skin Care',
                'motorcycle': 'Motorcycle',
                'jewel': 'Jewellery', 'earring': 'Jewellery',
            }
            for keyword, cat_name in category_map.items():
                if keyword in query_lower:
                    category = cat_name
                    break

        # Build SQL with filters - embedding first, then filters, then limit
        conditions = ["quantity > 0"]
        params = [str(query_embedding)]  # Embedding as first param
        
        if max_price:
            conditions.append("price <= %s")
            params.append(max_price)
        
        if min_rating:
            conditions.append("stars >= %s")
            params.append(min_rating)
        
        if category:
            conditions.append("category_name ILIKE %s")
            params.append(f"%{category}%")
        
        params.append(limit)  # Limit as last param
        where_clause = " AND ".join(conditions)
        
        # Use CTE to define embedding once and reuse it
        search_query = f"""
            WITH query_embedding AS (SELECT %s::vector as emb)
            SELECT 
                "productId",
                product_description,
                price,
                stars,
                reviews,
                category_name,
                quantity,
                "imgUrl",
                "productURL" as product_url,
                1 - (embedding <=> (SELECT emb FROM query_embedding)) as similarity
            FROM pellier.product_catalog
            WHERE {where_clause}
            ORDER BY embedding <=> (SELECT emb FROM query_embedding)
            LIMIT %s
        """
        
        # Execute query with timing
        db_start = time.time()
        results = await self.db.fetch_all(search_query, *params)
        db_time_ms = (time.time() - db_start) * 1000
        
        products = [convert_decimals(dict(row)) for row in results]

        # Filter out low-relevance results
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
                "min_similarity": min_similarity
            },
            "performance": {
                "bedrock_embedding_ms": round(embedding_time_ms, 2),
                "database_query_ms": round(db_time_ms, 2),
                "total_ms": round(embedding_time_ms + db_time_ms, 2)
            },
            "sql_query": search_query.replace("%s", "?"),
            "note": "⚠️ This is a Pellier workshop tool for educational purposes"
        }
    
    async def get_products_by_category(
        self,
        category: str,
        min_rating: float = 4.0,
        max_price: float = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Get products by category with filters.
        
        Args:
            category: Product category
            min_rating: Minimum star rating
            max_price: Maximum price
            limit: Number of results
        """
        conditions = ["category_name ILIKE %s", "quantity > 0"]
        params = [f"%{category}%"]
        
        if min_rating:
            conditions.append("stars >= %s")
            params.append(min_rating)
        
        if max_price:
            conditions.append("price <= %s")
            params.append(max_price)
        
        params.append(limit)
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                "productId",
                product_description,
                price,
                stars,
                reviews,
                category_name,
                quantity,
                "imgUrl",
                "productURL" as product_url
            FROM pellier.product_catalog
            WHERE {where_clause}
            ORDER BY stars DESC, reviews DESC
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
                "max_price": max_price
            }
        }
    
    async def get_low_stock_products(self, limit: int = 3) -> Dict[str, Any]:
        """
        Get products with low stock (quantity < 10) prioritized by demand.
        
        Args:
            limit: Number of products to return
            
        Returns:
            Dictionary with low-stock products
        """
        query = """
            SELECT 
                "productId",
                product_description,
                price,
                stars,
                reviews,
                category_name,
                quantity,
                "imgUrl",
                "productURL" as product_url
            FROM pellier.product_catalog
            WHERE quantity < 10
              AND stars >= 3.0
            ORDER BY quantity ASC, reviews DESC, stars DESC
            LIMIT %s
        """
        
        results = await self.db.fetch_all(query, limit)
        products = [convert_decimals(dict(row)) for row in results]
        
        return {
            "status": "success",
            "count": len(products),
            "products": products
        }
    
    async def personalized_search(
        self,
        query: str,
        preferences: Dict[str, Any] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Personalized product search with preference-based re-ranking.

        Runs a base semantic search then boosts scores for products
        matching user preferences (favorite categories, price range).

        Wire It Live: Participants implement the boost formula.

        Args:
            query: Natural language search query
            preferences: Dict with keys like 'categories', 'price_range', 'brands'
            limit: Number of results
        """
        # Run base semantic search
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
            category = (product.get("category_name") or "").lower()

            # --- Wire It Live: Personalization Boost ---
            # TODO (Workshop): Implement your own boost formula here.
            # Hint: boost matching categories by +0.1, matching price range by +0.05

            # Category match
            if preferred_categories and any(pc in category for pc in preferred_categories):
                boost += 0.1
                reasons.append(f"Matches your interest in {product.get('category_name', 'this category')}")

            # Price range match
            price = float(product.get("price", 0))
            if min_price is not None and max_price is not None:
                if min_price <= price <= max_price:
                    boost += 0.05
                    reasons.append(f"Within your ${min_price}–${max_price} budget")
            elif max_price is not None and price <= max_price:
                boost += 0.05
                reasons.append(f"Under your ${max_price} budget")

            # High rating boost
            stars = float(product.get("stars", 0))
            if stars >= 4.5:
                boost += 0.03
                reasons.append("Highly rated by customers")

            # --- End Wire It Live ---

            product["personalization_boost"] = round(boost, 3)
            product["recommendation_reasons"] = reasons
            original_sim = product.get("similarity", 0)
            product["personalized_score"] = round(original_sim + boost, 4)

        # Re-rank by personalized score
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

    def _generate_inventory_alerts(self, stats: Dict) -> List[str]:
        """Generate inventory alerts based on statistics"""
        alerts = []
        
        if stats['out_of_stock'] > 0:
            alerts.append(f"🚨 {stats['out_of_stock']} products out of stock")
        
        if stats['low_stock'] > 100:
            alerts.append(f"⚠️ {stats['low_stock']} products low stock (<10 units)")
        elif stats['low_stock'] > 0:
            alerts.append(f"⚠️ {stats['low_stock']} products need monitoring")
        
        if not alerts:
            alerts.append("✅ Inventory healthy")
        
        return alerts
