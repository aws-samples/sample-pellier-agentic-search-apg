"""
Bazaar Pricing MCP Server — Lambda-hosted MCP server for price analysis.

Exposes tools:
  - find_deals: Find products with best value (high ratings, competitive prices)
  - get_price_analysis: Price statistics by category
  - compare_products: Side-by-side comparison of two products

Deployed as a Lambda function behind AgentCore Gateway.
"""
import json
import logging
import os
from typing import Any

import boto3

from common.types import resolve_invocation

logger = logging.getLogger(__name__)

REGION = os.environ.get("REGION", "us-east-1")
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
# Cohere Embed v4 — MUST match the catalog seed + in-process path so the
# managed Gateway vector search shares the same embedding space.
EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "us.cohere.embed-v4:0")
SCHEMA = "pellier"

# Module-level clients for Lambda warm start reuse
rds_client = boto3.client("rds-data", region_name=REGION)
bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)


def _execute_sql(sql: str, parameters: list = None) -> list[dict]:
    """Execute SQL via RDS Data API and return rows as dicts."""
    params = {
        "resourceArn": DB_CLUSTER_ARN,
        "secretArn": SECRET_ARN,
        "database": DATABASE,
        "sql": sql,
        # Without this the Data API omits columnMetadata entirely, columns
        # is [] and the first returned row IndexErrors (box-verified
        # 2026-06-12 — "list index out of range" on every successful SELECT).
        "includeResultMetadata": True,
    }
    if parameters:
        params["parameters"] = parameters
    response = rds_client.execute_statement(**params)
    columns = [col["name"] for col in response.get("columnMetadata", [])]
    rows = []
    for record in response.get("records", []):
        row = {}
        for i, field in enumerate(record):
            if "stringValue" in field:
                row[columns[i]] = field["stringValue"]
            elif "longValue" in field:
                row[columns[i]] = field["longValue"]
            elif "doubleValue" in field:
                row[columns[i]] = field["doubleValue"]
            elif "booleanValue" in field:
                row[columns[i]] = field["booleanValue"]
            elif "isNull" in field:
                row[columns[i]] = None
            else:
                row[columns[i]] = str(field)
        rows.append(row)
    return rows


def _get_embedding(text: str) -> list[float]:
    """Generate a query embedding via Cohere Embed v4.

    Must match the catalog seed + in-process path (Cohere Embed v4,
    output_dimension=1024). Titan v2 would be a different vector space and
    break pgvector cosine ranking even at matching dimension.
    """
    response = bedrock_client.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=json.dumps(
            {"texts": [text], "input_type": "search_query", "output_dimension": 1024}
        ),
    )
    return json.loads(response["body"].read())["embeddings"]["float"][0]


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
        WHERE quantity > 0 AND rating >= 3.5 {price_filter}
        ORDER BY embedding <=> :embedding::vector
        LIMIT :lim;
    """
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "query": query, "count": len(rows)}


def get_price_analysis(category: str = None) -> dict:
    """Get price statistics (min, max, avg, median) by category."""
    where = "WHERE category = :cat" if category else ""
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
    "find_deals": {
        "fn": find_deals,
        "description": "Find best-value products matching a query. Ranks by rating-to-price ratio with semantic search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What kind of product deal to find"},
                "max_price": {"type": "number", "description": "Maximum price filter"},
                "limit": {"type": "integer", "description": "Max results", "default": 5},
            },
            "required": ["query"],
        },
    },
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
                "product_id_1": {"type": "string", "description": "First product ID"},
                "product_id_2": {"type": "string", "description": "Second product ID"},
            },
            "required": ["product_id_1", "product_id_2"],
        },
    },
}


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda handler for MCP tool invocation via AgentCore Gateway."""
    # Resolve BOTH invocation shapes (Gateway client_context-prefixed vs direct
    # {name,arguments}); shared helper in common/types.py, packaged into the zip.
    tool_name, arguments = resolve_invocation(event, context)

    if tool_name == "list_tools":
        return {
            "tools": [
                {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
                for name, spec in TOOLS.items()
            ]
        }

    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        result = TOOLS[tool_name]["fn"](**arguments)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}
