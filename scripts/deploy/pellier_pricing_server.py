"""
Bazaar Pricing MCP Server — Lambda-hosted MCP server for price analysis.

Exposes the two pricing tools from the governed 15-tool Gateway subset of
Pellier's 17-tool MCP registry:
  - get_price_analysis: Price statistics by category
  - compare_products: Side-by-side comparison of two products

Deployed as a Lambda function behind AgentCore Gateway.
"""
import json
import logging
import os
from typing import Any

import boto3

from common.handler import build_handler
from common.dataapi import (
    execute_sql as _execute_sql,
    query_embedding as _get_embedding,
)

logger = logging.getLogger(__name__)

REGION = os.environ.get("REGION", "us-east-1")
DB_REGION = os.environ.get("DB_REGION", REGION)
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
# Cohere Embed v4 — MUST match the catalog seed + in-process path so the
# managed Gateway vector search shares the same embedding space.
EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "us.cohere.embed-v4:0")
SCHEMA = "pellier"

# Module-level clients for Lambda warm start reuse






# --- Tool implementations ---

def find_deals(query: str, max_price: float = None, limit: int = 5) -> dict:
    """Find best-value products matching a query, sorted by rating-to-price ratio."""
    embedding = _get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    price_filter = "AND price <= :max_price" if max_price else ""
    parameters = [
        {"name": "embedding", "value": {"stringValue": embedding_str}},
        {"name": "lim", "value": {"longValue": int(limit)}},
    ]
    if max_price:
        parameters.append({"name": "max_price", "value": {"doubleValue": float(max_price)}})

    # Single statement only: Data API execute_statement rejects a prepended
    # SET ("Multistatements aren't supported", box-verified 2026-06-12).
    # Column names follow the seeded schema (description/category/rating —
    # 001_schema.sql), aliased to the keys downstream code expects.
    sql = f"""
        SELECT "productId", description AS product_description, price,
               rating AS stars, reviews,
               category AS category_name, quantity, "imgUrl",
               1 - (embedding <=> :embedding::vector) AS similarity,
               CASE WHEN price > 0 THEN rating / price * 100 ELSE 0 END AS value_score
        FROM {SCHEMA}.product_catalog
        WHERE quantity > 0 AND rating >= 3.5
          AND NOT (tags ? 'archive') {price_filter}
        ORDER BY embedding <=> :embedding::vector
        LIMIT :lim;
    """
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "query": query, "count": len(rows)}


def get_price_analysis(category: str = None) -> dict:
    """Get price statistics (min, max, avg, median) by category.

    Excludes archived rows, mirroring ``BusinessLogic.get_price_analysis`` on
    the in-process rail: without this predicate, min/max/avg/median price by
    category would be skewed by retired products that the storefront never
    shows, and the managed and in-process rails would report different
    numbers for the same category.
    """
    where = (
        "WHERE category = :cat AND NOT (tags ? 'archive')"
        if category
        else "WHERE NOT (tags ? 'archive')"
    )
    parameters = []
    if category:
        parameters.append({"name": "cat", "value": {"stringValue": str(category)}})

    sql = f"""
        SELECT category AS category_name,
               COUNT(*) AS product_count,
               MIN(price)::numeric(10,2) AS min_price,
               MAX(price)::numeric(10,2) AS max_price,
               AVG(price)::numeric(10,2) AS avg_price,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::numeric(10,2) AS median_price
        FROM {SCHEMA}.product_catalog
        {where}
        GROUP BY category
        ORDER BY avg_price DESC
        LIMIT 15;
    """
    rows = _execute_sql(sql, parameters if parameters else None)
    return {"categories": rows}


def compare_products(product_id_1: str, product_id_2: str) -> dict:
    """Compare two products side by side."""
    sql = f"""
        SELECT "productId", description AS product_description, price,
               rating AS stars, reviews,
               category AS category_name, quantity, badge
        FROM {SCHEMA}.product_catalog
        WHERE "productId" IN (:pid1, :pid2);
    """
    parameters = [
        {"name": "pid1", "value": {"stringValue": str(product_id_1)}},
        {"name": "pid2", "value": {"stringValue": str(product_id_2)}},
    ]
    rows = _execute_sql(sql, parameters)
    if len(rows) < 2:
        return {"error": "One or both products not found", "found": rows}
    return {"product_1": rows[0], "product_2": rows[1]}


# --- Lambda MCP handler ---

TOOLS = {
    "get_price_analysis": {
        "fn": get_price_analysis,
        "description": "Get price statistics (min, max, avg, median) across product categories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category name to analyze (omit for all)"},
            },
            "required": [],
        },
    },
    "compare_products": {
        "fn": compare_products,
        "description": "Compare two products side by side on price, rating, reviews, and availability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id_1": {"type": "integer", "description": "First product ID"},
                "product_id_2": {"type": "integer", "description": "Second product ID"},
            },
            "required": ["product_id_1", "product_id_2"],
        },
    },
}


# No transaction or audit wiring on this surface, so the shared
# invocation contract is used as-is.
lambda_handler = build_handler(TOOLS)
