"""
Pellier Curation MCP Server - Lambda-hosted read and recommendation tools.

Exposes the five curation and evidence tools from the governed 15-tool
Gateway subset of Pellier's 17-tool MCP registry:
  - get_customer_preferences
  - get_audit_trail
  - get_trending_products
  - get_return_policy
  - get_related_products

Deployed as a Lambda function behind AgentCore Gateway.
"""
import json
import logging
import os
import re
from typing import Any

import boto3

from common.handler import build_handler
from common.dataapi import execute_sql as _execute_sql

logger = logging.getLogger(__name__)

REGION = os.environ.get("REGION", "us-east-1")
DB_REGION = os.environ.get("DB_REGION", REGION)
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
SCHEMA = "pellier"
_LIKE_METACHARACTERS = re.compile(r"([\\%_])")

# Module-level clients for Lambda warm start reuse



def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _resolve_customer_id(customer_id: str = "") -> str:
    """Normalize only the server-bound Aurora customer identifier."""
    return (customer_id or "").strip().upper()


def _prepare_like_pattern(term: str) -> str:
    """Return a literal contains-match pattern for PostgreSQL LIKE."""
    escaped = _LIKE_METACHARACTERS.sub(r"\\\1", str(term).lower())
    return f"%{escaped}%"


# --- Tool implementations ---

def get_customer_preferences(
    customer_id: str = "",
    limit: int = 5,
) -> dict:
    """Return a read-only customer, order, and episodic-memory snapshot."""
    resolved = _resolve_customer_id(customer_id)
    if not resolved:
        return {
            "status": "no_customer_context",
            "message": "Verified customer_id is required for profile context.",
            "read_only": True,
        }

    safe_limit = max(1, min(int(limit or 5), 10))
    customer = _execute_sql(
        f"""
        SELECT id, name, preferences_summary
          FROM {SCHEMA}.customers
         WHERE id = :customer_id;
        """,
        [{"name": "customer_id", "value": {"stringValue": resolved}}],
    )
    if not customer:
        return {"status": "not_found", "customer_id": resolved, "read_only": True}

    parameters = [
        {"name": "customer_id", "value": {"stringValue": resolved}},
        {"name": "limit", "value": {"longValue": safe_limit}},
    ]
    orders = _execute_sql(
        f"""
        SELECT o.product_id, pc.name, pc.brand, pc.category, pc.color,
               pc.price, o.quantity, o.placed_at
          FROM {SCHEMA}.orders o
          JOIN {SCHEMA}.product_catalog pc
            ON pc."productId" = o.product_id
         WHERE o.customer_id = :customer_id
         ORDER BY o.placed_at DESC
         LIMIT :limit;
        """,
        parameters,
    )
    facts = _execute_sql(
        f"""
        SELECT summary_text, ts_offset_days
          FROM {SCHEMA}.customer_episodic_seed
         WHERE customer_id = :customer_id
         ORDER BY ts_offset_days DESC
         LIMIT :limit;
        """,
        parameters,
    )
    return {
        "status": "success",
        "read_only": True,
        "customer": customer[0],
        "recent_orders": orders,
        "memory_facts": [
            {
                "summary": fact.get("summary_text"),
                "ts_offset_days": fact.get("ts_offset_days"),
            }
            for fact in facts
        ],
        "sources": [
            "pellier.customers",
            "pellier.orders",
            "pellier.customer_episodic_seed",
        ],
    }


def get_audit_trail(
    customer_id: str = "",
    session_id: str = "",
    tool_name: str = "",
    caller: str = "",
    limit: int = 3,
) -> dict:
    """Return recent read-only audit receipts for one verified customer."""
    resolved_customer = _resolve_customer_id(customer_id)
    if not resolved_customer:
        return {
            "status": "no_customer_context",
            "message": "Verified customer_id is required for trace receipts.",
            "read_only": True,
        }

    filters = ["args->>'customer_id' = :customer_id"]
    parameters = [
        {
            "name": "customer_id",
            "value": {"stringValue": resolved_customer},
        }
    ]
    for field, value in (
        ("session_id", session_id),
        ("tool", tool_name),
        ("caller", caller.lower() if caller else ""),
    ):
        clean = (value or "").strip()
        if clean:
            filters.append(f"{field} = :{field}")
            parameters.append(
                {"name": field, "value": {"stringValue": clean}}
            )
    safe_limit = max(1, min(int(limit or 3), 10))
    parameters.append({"name": "limit", "value": {"longValue": safe_limit}})
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = _execute_sql(
        f"""
        SELECT audit_id, session_id, tool, caller, args, result,
               latency_ms, created_at
          FROM {SCHEMA}.tool_audit
          {where}
         ORDER BY audit_id DESC
         LIMIT :limit;
        """,
        parameters,
    )
    if not rows:
        return {
            "status": "no_allow_receipt",
            "read_only": True,
            "filters": {
                "customer_id": resolved_customer,
                "session_id": (session_id or "").strip() or None,
                "tool_name": (tool_name or "").strip() or None,
                "caller": (caller or "").strip().lower() or None,
            },
            "interpretation": (
                "No pellier.tool_audit ALLOW row matched these filters."
            ),
        }

    receipts = []
    for row in rows:
        result = _decode_json(row.get("result"))
        if isinstance(result, dict):
            status = result.get("status") or result.get("type")
            if status is None and "error" in result:
                status = "error"
            result_summary = {
                "status": status or "recorded",
                "keys": sorted(str(key) for key in result)[:10],
            }
        elif isinstance(result, list):
            result_summary = {"status": "recorded", "items": len(result)}
        else:
            result_summary = {
                "status": "pending" if result is None else "recorded"
            }
        receipts.append(
            {
                "audit_id": row.get("audit_id"),
                "session_id": row.get("session_id"),
                "tool": row.get("tool"),
                "caller": row.get("caller"),
                "decision": "ALLOW",
                "args": _decode_json(row.get("args")),
                "result_summary": result_summary,
                "latency_ms": row.get("latency_ms"),
                "created_at": row.get("created_at"),
            }
        )
    return {
        "status": "success",
        "read_only": True,
        "count": len(receipts),
        "receipts": receipts,
        "source": "pellier.tool_audit",
    }


def get_trending_products(limit: int = 5, category: str = None) -> dict:
    """Return products ranked by rating times review volume."""
    conditions = ["rating >= 4.0", "reviews::int > 50", '"imgUrl" IS NOT NULL']
    parameters = [
        {
            "name": "limit",
            "value": {"longValue": max(1, min(int(limit or 5), 20))},
        }
    ]
    if category:
        conditions.append("lower(category) LIKE :category")
        parameters.append(
            {
                "name": "category",
                "value": {"stringValue": _prepare_like_pattern(category)},
            }
        )
    rows = _execute_sql(
        f"""
        SELECT "productId", name, brand, color, "imgUrl", price, rating,
               reviews, category, badge, tags,
               (reviews::int * rating) AS trending_score
          FROM {SCHEMA}.product_catalog
         WHERE {' AND '.join(conditions)}
         ORDER BY trending_score DESC, rating DESC
         LIMIT :limit;
        """,
        parameters,
    )
    return {
        "status": "success",
        "count": len(rows),
        "products": rows,
        "metadata": {
            "criteria": "reviews * rating, min 4.0 rating, min 50 reviews",
            "limit": max(1, min(int(limit or 5), 20)),
            "category_filter": category,
        },
    }


def get_return_policy(category: str = "default") -> dict:
    """Return the exact category policy, falling back to the default row."""
    parameters = [
        {"name": "category", "value": {"stringValue": category or "default"}}
    ]
    rows = _execute_sql(
        f"""
        SELECT category_name, return_window_days, conditions, refund_method
          FROM {SCHEMA}.return_policies
         WHERE category_name = :category;
        """,
        parameters,
    )
    if not rows and category != "default":
        rows = _execute_sql(
            f"""
            SELECT category_name, return_window_days, conditions, refund_method
              FROM {SCHEMA}.return_policies
             WHERE category_name = 'default';
            """
        )
    if not rows:
        return {"error": f"No return policy found for category: {category}"}
    return rows[0]


def get_related_products(
    source_product_name: str,
    product_id: int | None = None,
    limit: int = 5,
) -> dict:
    """Find products nearest to a verified named source product."""
    source_name = " ".join((source_product_name or "").split())
    if not source_name:
        return {
            "error": "source_product_name is required",
            "code": "source_product_name_required",
        }
    source_pattern = _prepare_like_pattern(source_name)

    source_rows = _execute_sql(
        f"""
        SELECT "productId", name, brand, price, embedding::text AS embedding
          FROM {SCHEMA}.product_catalog
         WHERE (
                LOWER(TRIM(name)) = LOWER(:source_product_name)
                OR LOWER(name) LIKE :source_product_pattern ESCAPE '\\'
               )
           AND NOT (tags ? 'archive')
         ORDER BY CASE
                    WHEN LOWER(TRIM(name)) = LOWER(:source_product_name) THEN 0
                    ELSE 1
                  END,
                  "productId"
         LIMIT 2;
        """,
        [
            {
                "name": "source_product_name",
                "value": {"stringValue": source_name},
            },
            {
                "name": "source_product_pattern",
                "value": {"stringValue": source_pattern},
            },
        ],
    )
    if not source_rows:
        return {
            "error": f"No curated product matches {source_name!r}",
            "code": "source_product_not_found",
        }
    if len(source_rows) > 1:
        return {
            "error": (
                f"More than one curated product matches {source_name!r}; "
                "search first and retry with the exact product name."
            ),
            "code": "source_product_ambiguous",
            "candidates": [
                {
                    "productId": str(row["productId"]).strip(),
                    "name": row["name"],
                }
                for row in source_rows
            ],
        }

    source = source_rows[0]
    product_id_text = str(source["productId"]).strip()
    if product_id is not None and str(product_id).strip() != product_id_text:
        return {
            "error": (
                f"product_id {product_id} does not identify {source['name']!r}"
            ),
            "code": "source_product_mismatch",
            "source": {
                "productId": product_id_text,
                "name": source["name"],
            },
        }
    embedding = source.pop("embedding", None)
    if not embedding:
        return {"error": f"Product {source['name']!r} has no embedding"}

    matches = _execute_sql(
        f"""
        SELECT "productId", name, brand, color, price, rating, reviews,
               category, "imgUrl",
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity_score
          FROM {SCHEMA}.product_catalog
         WHERE "productId" <> :product_id
           AND embedding IS NOT NULL
         ORDER BY embedding <=> CAST(:embedding AS vector)
         LIMIT :limit;
        """,
        [
            {"name": "embedding", "value": {"stringValue": embedding}},
            {"name": "product_id", "value": {"stringValue": product_id_text}},
            {
                "name": "limit",
                "value": {"longValue": max(1, min(int(limit or 5), 20))},
            },
        ],
    )
    return {"source": source, "matches": matches, "count": len(matches)}


# --- Lambda MCP handler ---

TOOLS = {
    "get_customer_preferences": {
        "fn": get_customer_preferences,
        "description": "Read a safe customer preference, order, and memory snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["customer_id"],
        },
    },
    "get_audit_trail": {
        "fn": get_audit_trail,
        "description": "Read recent ALLOW receipts from pellier.tool_audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "session_id": {"type": "string"},
                "tool_name": {"type": "string"},
                "caller": {"type": "string"},
                "limit": {"type": "integer", "default": 3},
            },
            "required": ["customer_id"],
        },
    },
    "get_trending_products": {
        "fn": get_trending_products,
        "description": "Get products ranked by rating and review volume.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
                "category": {"type": "string", "description": "Filter by category"},
            },
            "required": [],
        },
    },
    "get_return_policy": {
        "fn": get_return_policy,
        "description": "Look up the return and care policy for a category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": "default"},
            },
            "required": [],
        },
    },
    "get_related_products": {
        "fn": get_related_products,
        "description": (
            "Find complementary products from a verified named source product."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_product_name": {"type": "string"},
                "product_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["source_product_name"],
        },
    },
}


# No transaction or audit wiring on this surface, so the shared
# invocation contract is used as-is.
lambda_handler = build_handler(TOOLS)
