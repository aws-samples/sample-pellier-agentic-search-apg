"""
Pellier Search MCP Server — Lambda-hosted MCP server for catalog discovery.

Exposes tools:
  - semantic_search:      Vector similarity search (Anna's pure-vector path)
  - find_pieces_hybrid:   Vector + Postgres FTS + Cohere Rerank v3.5
                          (Anna's production retrieval pipeline)
  - get_inventory_health: Stock-level summary across categories
  - get_low_stock_products: Products below the restock threshold
  - restock_product:      Update product quantity (bounded by policy)

Deployed as a Lambda function behind AgentCore Gateway. The Lambda
mirrors the in-process @tool functions in ``pellier/backend/services/``
— same JSON envelopes, same error shapes — so swapping the orchestrator
between the in-process path and the Gateway path is invisible to the
agent's prompt.

References:
    Cohere Rerank on Bedrock:
        https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-cohere-rerank.html
    RDS Data API:
        https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.html
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


def find_pieces_hybrid(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5,
) -> dict:
    """Hybrid retrieval: pgvector + Postgres FTS → RRF → Cohere Rerank v3.5.

    Mirrors `services.agent_tools.find_pieces_hybrid` but runs inside the
    Lambda microVM instead of the orchestrator's process. Three stages:

      1. Vector branch (pgvector cosine, k=20) and FTS branch
         (`ts_rank_cd`, k=20) execute in a single SQL statement against
         `pellier.product_catalog`. RDS Data API can't run multi-statement
         transactions, so we fold the two ranked lists into a CTE plus
         Reciprocal Rank Fusion (RRF) inside the same query.
      2. The merged ~30-candidate pool is sent to Cohere Rerank v3.5
         (`us.cohere.rerank-v3-5:0`) via Bedrock `invoke_model`.
      3. Top `limit` results are returned, with post-rerank filters for
         max_price and min_rating applied last so the rerank order is
         preserved.

    On a Bedrock failure (rate limit, invalid response), we fall back to
    RRF order — the Atelier surfaces this as a missing rerank stage in
    telemetry rather than crashing the request.
    """
    embedding = _get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    # Hybrid retrieval in a single statement. RRF merges the two
    # ranked lists by `1/(60 + rank)` — the same constant the
    # in-process implementation uses, so participants get a one-to-one
    # comparison between paths.
    sql = f"""
        SET hnsw.iterative_scan = 'relaxed_order';
        WITH vector_results AS (
          SELECT "productId" AS pid,
                 row_number() OVER (ORDER BY embedding <=> :embedding::vector) AS vrank
          FROM {SCHEMA}.product_catalog
          WHERE quantity > 0
          LIMIT 20
        ),
        fts_results AS (
          SELECT "productId" AS pid,
                 row_number() OVER (ORDER BY ts_rank_cd(description_tsv, plainto_tsquery(:query)) DESC) AS frank
          FROM {SCHEMA}.product_catalog
          WHERE quantity > 0
            AND description_tsv @@ plainto_tsquery(:query)
          LIMIT 20
        ),
        rrf AS (
          SELECT COALESCE(v.pid, f.pid) AS pid,
                 COALESCE(1.0 / (60 + v.vrank), 0) +
                 COALESCE(1.0 / (60 + f.frank), 0) AS rrf_score
          FROM vector_results v
          FULL OUTER JOIN fts_results f USING (pid)
        )
        SELECT pc."productId", pc.product_description, pc.price, pc.stars,
               pc.reviews, pc.category_name, pc.quantity, pc."imgUrl",
               rrf.rrf_score
        FROM rrf
        JOIN {SCHEMA}.product_catalog pc ON pc."productId" = rrf.pid
        ORDER BY rrf.rrf_score DESC
        LIMIT 30;
    """
    parameters = [
        {"name": "embedding", "value": {"stringValue": embedding_str}},
        {"name": "query", "value": {"stringValue": query}},
    ]
    candidates = _execute_sql(sql, parameters)

    # Rerank stage. Cohere wants plain text per document; we mirror
    # the in-process `_doc_for_rerank` shape (name + description + cat).
    documents = []
    for p in candidates:
        desc = (p.get("product_description") or "").strip()
        cat = (p.get("category_name") or "").strip()
        if len(desc) > 240:
            desc = desc[:237] + "…"
        documents.append(f"{desc} ({cat})")

    rerank_results = _bedrock_rerank(query, documents, top_n=min(limit * 3, 30))
    if rerank_results:
        ordered = [
            {**candidates[r["index"]], "rerank_score": float(r["relevance_score"])}
            for r in rerank_results
        ]
        search_method = "hybrid+rerank"
    else:
        ordered = [{**c, "rerank_score": None} for c in candidates]
        search_method = "hybrid (rerank fallback to RRF order)"

    # Apply post-rerank filters last so the rerank ordering is honoured.
    filtered = []
    for p in ordered:
        if max_price is not None:
            try:
                if float(p.get("price") or 0) > float(max_price):
                    continue
            except (TypeError, ValueError):
                pass
        if min_rating:
            try:
                if float(p.get("stars") or 0) < float(min_rating):
                    continue
            except (TypeError, ValueError):
                pass
        if category and category.lower() not in (p.get("category_name") or "").lower():
            continue
        filtered.append(p)
        if len(filtered) >= limit:
            break

    return {
        "status": "success",
        "query": query,
        "count": len(filtered),
        "products": filtered,
        "search_method": search_method,
        "pool_size": len(candidates),
    }


def _bedrock_rerank(query: str, documents: list, top_n: int) -> list:
    """Call Cohere Rerank v3.5 on Bedrock; return [] on any failure.

    Returning [] (instead of raising) matches the in-process service so
    the caller can fall back to RRF order. The Atelier surfaces a
    missing-rerank state from this signal — useful demo when the
    workshop wants to show graceful degradation under Bedrock pressure.
    """
    if not documents:
        return []
    body = {
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
        "api_version": 2,
    }
    try:
        response = bedrock_client.invoke_model(
            modelId="us.cohere.rerank-v3-5:0",
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(response["body"].read())
        return payload.get("results", [])
    except Exception as exc:
        logger.warning(f"Cohere rerank failed: {exc}")
        return []


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
    "find_pieces_hybrid": {
        "fn": find_pieces_hybrid,
        "description": "Hybrid retrieval over the catalog: pgvector cosine + Postgres FTS merged via RRF, reranked by Cohere Rerank v3.5. Higher quality than semantic_search at the cost of one extra Bedrock call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "max_price": {"type": "number", "description": "Maximum price filter (post-rerank)"},
                "min_rating": {"type": "number", "description": "Minimum star rating filter (post-rerank)", "default": 0.0},
                "category": {"type": "string", "description": "Category substring filter (post-rerank). Leave unset to let the reranker pick across categories."},
                "limit": {"type": "integer", "description": "Max results to return", "default": 5},
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
