"""
Bazaar Recommendation MCP Server — Lambda-hosted MCP server for product recommendations.

Exposes tools:
  - get_recommendations: Personalized product recommendations via semantic search
  - get_trending_products: Top products by recent purchase volume

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

def get_recommendations(query: str, category: str = None, max_price: float = None, limit: int = 5) -> dict:
    """Get personalized product recommendations using semantic search."""
    embedding = _get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    where_clauses = ["quantity > 0"]
    parameters = [
        {"name": "embedding", "value": {"stringValue": embedding_str}},
        {"name": "lim", "value": {"longValue": int(limit)}},
    ]
    if category:
        where_clauses.append("category = :cat")
        parameters.append({"name": "cat", "value": {"stringValue": str(category)}})
    if max_price:
        where_clauses.append("price <= :max_price")
        parameters.append({"name": "max_price", "value": {"doubleValue": float(max_price)}})
    where_sql = " AND ".join(where_clauses)

    # Single statement only: Data API execute_statement rejects a prepended
    # SET ("Multistatements aren't supported", box-verified 2026-06-12).
    # Column names follow the seeded schema (description/category/rating/badge
    # — 001_schema.sql), aliased to the keys downstream code expects.
    sql = f"""
        SELECT "productId", description AS product_description, price,
               rating AS stars, reviews,
               category AS category_name, quantity, "imgUrl", badge,
               1 - (embedding <=> :embedding::vector) AS similarity
        FROM {SCHEMA}.product_catalog
        WHERE {where_sql}
        ORDER BY embedding <=> :embedding::vector
        LIMIT :lim;
    """
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "query": query, "count": len(rows)}


def get_trending_products(limit: int = 10, category: str = None) -> dict:
    """Get trending products by recent purchase volume."""
    where = "WHERE category = :cat" if category else ""
    parameters = [{"name": "lim", "value": {"longValue": int(limit)}}]
    if category:
        parameters.append({"name": "cat", "value": {"stringValue": str(category)}})

    # The seeded catalog has no boughtInLastMonth column; trending is
    # rating × reviews, mirroring the in-process whats_trending
    # (business_logic.py) so both rails rank identically.
    sql = f"""
        SELECT "productId", description AS product_description, price,
               rating AS stars, reviews,
               category AS category_name, quantity, "imgUrl",
               (reviews::int * rating) AS trending_score
        FROM {SCHEMA}.product_catalog
        {where}
        ORDER BY trending_score DESC NULLS LAST
        LIMIT :lim;
    """
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "count": len(rows)}


# --- Lambda MCP handler ---

TOOLS = {
    "get_recommendations": {
        "fn": get_recommendations,
        "description": "Get personalized product recommendations based on a natural language description of what the user wants.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the user is looking for"},
                "category": {"type": "string", "description": "Filter by product category"},
                "max_price": {"type": "number", "description": "Maximum price filter"},
                "limit": {"type": "integer", "description": "Max results", "default": 5},
            },
            "required": ["query"],
        },
    },
    "get_trending_products": {
        "fn": get_trending_products,
        "description": "Get the most popular products by recent purchase volume. Optionally filter by category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 10},
                "category": {"type": "string", "description": "Filter by category"},
            },
            "required": [],
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
