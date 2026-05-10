"""
Bazaar Search MCP Server — Lambda-hosted MCP server for semantic search + inventory.

Exposes tools:
  - semantic_search: Vector similarity search over product catalog
  - get_inventory_health: Stock level summary across categories
  - get_low_stock_products: Products below restock threshold
  - restock_product: Update product quantity

Deployed as a Lambda function behind AgentCore Gateway.
"""
import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)

# --- Database helpers (RDS Data API) ---

REGION = os.environ.get("REGION", "us-east-1")
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
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
    """Generate embedding via Bedrock Titan v2."""
    response = bedrock_client.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text, "dimensions": 1024}),
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


# --- MCP Tool implementations ---


def semantic_search(query: str, limit: int = 5, max_price: float = None, min_rating: float = None) -> dict:
    """Search products by semantic similarity using pgvector."""
    embedding = _get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    where_clauses = ["quantity > 0"]
    parameters = [
        {"name": "embedding", "value": {"stringValue": embedding_str}},
        {"name": "lim", "value": {"longValue": int(limit)}},
    ]
    if max_price:
        where_clauses.append("price <= :max_price")
        parameters.append({"name": "max_price", "value": {"doubleValue": float(max_price)}})
    if min_rating:
        where_clauses.append("stars >= :min_rating")
        parameters.append({"name": "min_rating", "value": {"doubleValue": float(min_rating)}})
    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SET hnsw.iterative_scan = 'relaxed_order';
        SELECT "productId", product_description, price, stars, reviews,
               category_name, quantity, "imgUrl",
               1 - (embedding <=> :embedding::vector) AS similarity
        FROM {SCHEMA}.product_catalog
        WHERE {where_sql}
        ORDER BY embedding <=> :embedding::vector
        LIMIT :lim;
    """
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "query": query, "count": len(rows)}


def get_inventory_health() -> dict:
    """Get inventory health summary across categories."""
    sql = f"""
        SELECT category_name,
               COUNT(*) AS total_products,
               SUM(CASE WHEN quantity < 10 THEN 1 ELSE 0 END) AS low_stock,
               AVG(quantity)::int AS avg_quantity
        FROM {SCHEMA}.product_catalog
        GROUP BY category_name
        ORDER BY low_stock DESC
        LIMIT 10;
    """
    rows = _execute_sql(sql)
    return {"categories": rows}


def get_low_stock_products(limit: int = 5) -> dict:
    """Get products with lowest stock levels."""
    sql = f"""
        SELECT "productId", product_description, price, stars, quantity, category_name
        FROM {SCHEMA}.product_catalog
        WHERE quantity > 0 AND quantity < 10
        ORDER BY quantity ASC
        LIMIT :lim;
    """
    parameters = [{"name": "lim", "value": {"longValue": int(limit)}}]
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "count": len(rows)}


def restock_product(product_id: str, quantity: int) -> dict:
    """Restock a product by adding quantity."""
    if quantity > 500:
        return {"error": "Restock quantity exceeds policy limit of 500", "denied": True}

    sql = f"""
        UPDATE {SCHEMA}.product_catalog
        SET quantity = quantity + :qty
        WHERE "productId" = :pid
        RETURNING "productId", product_description, quantity;
    """
    parameters = [
        {"name": "pid", "value": {"stringValue": str(product_id)}},
        {"name": "qty", "value": {"longValue": int(quantity)}},
    ]
    rows = _execute_sql(sql, parameters)
    if rows:
        return {"success": True, "product": rows[0]}
    return {"error": f"Product {product_id} not found"}


# --- Lambda MCP handler ---

TOOLS = {
    "semantic_search": {
        "fn": semantic_search,
        "description": "Search products by natural language query using vector similarity. Returns ranked products with similarity scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 5},
                "max_price": {"type": "number", "description": "Maximum price filter"},
                "min_rating": {"type": "number", "description": "Minimum star rating filter"},
            },
            "required": ["query"],
        },
    },
    "get_inventory_health": {
        "fn": get_inventory_health,
        "description": "Get inventory health summary showing stock levels across product categories.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "get_low_stock_products": {
        "fn": get_low_stock_products,
        "description": "Get products with critically low stock levels (below 10 units).",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max results", "default": 5}},
            "required": [],
        },
    },
    "restock_product": {
        "fn": restock_product,
        "description": "Restock a product by adding inventory. Quantity must be <= 500 per policy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product ID to restock"},
                "quantity": {"type": "integer", "description": "Quantity to add (max 500)"},
            },
            "required": ["product_id", "quantity"],
        },
    },
}


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda handler for MCP tool invocation via AgentCore Gateway."""
    tool_name = event.get("name", "")
    arguments = event.get("arguments", {})

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
