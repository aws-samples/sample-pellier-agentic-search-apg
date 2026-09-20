"""
Pellier Search MCP Server — Lambda-hosted MCP server for catalog discovery.

Exposes the six catalog and inventory tools from the governed 15-tool
Gateway subset of Pellier's 17-tool MCP registry:
  - search_products
  - search_products_hybrid
  - browse_category
  - check_inventory
  - get_low_stock
  - restock_inventory

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
import hashlib
import logging
import os
import re
import time
from typing import Any

import boto3

from common.types import resolve_invocation
from common.handler import audit_read_call
from common.dataapi import (
    execute_write as _execute_write,
    begin_transaction as _begin_transaction,
    commit_transaction as _commit_transaction,
    rollback_transaction as _rollback_transaction,
    execute_in_transaction as _execute_in_transaction,
    execute_sql as _execute_sql,
    query_embedding as _get_embedding,
    write_tool_audit,
)

logger = logging.getLogger(__name__)

# --- Database helpers (RDS Data API) ---

REGION = os.environ.get("REGION", "us-east-1")
DB_REGION = os.environ.get("DB_REGION", REGION)
DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DATABASE", "postgres")
# Cohere Embed v4 — MUST match the catalog seed + in-process path so the
# managed Gateway vector search shares the same embedding space.
EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "us.cohere.embed-v4:0")
SCHEMA = "pellier"
_TURN_ID_RE = re.compile(r"^turn-[0-9a-f]{32}$")
_LIKE_METACHARACTERS = re.compile(r"([\\%_])")


def _prepare_like_pattern(term: str) -> str:
    """Return a literal contains-match pattern for PostgreSQL LIKE.

    The same helper the in-process path uses (``app._prepare_like_pattern``)
    and the recommend server's copy. Escaping matters more here than it looks:
    the category filter is a hard SQL predicate applied to *both* retrieval
    branches before fusion, so an unescaped ``%`` or ``_`` in caller text does
    not merely widen a display filter, it changes which candidates the
    reranker ever sees. The value stays a bound parameter either way.
    """
    escaped = _LIKE_METACHARACTERS.sub(r"\\\1", str(term).lower())
    return f"%{escaped}%"
_GATEWAY_RETRIEVAL_INSERT = f"""
    INSERT INTO {SCHEMA}.retrieval_receipts (
        turn_id, query_hash, query_preview, search_plan,
        hard_constraints, soft_preferences, exclusions, relaxations,
        embedding_model, rerank_model, retrieval_config, index_parameters,
        candidate_product_ids, vector_ranks, lexical_ranks, rrf_scores,
        rerank_scores, merchandising_rules, memory_record_ids_used,
        citation_ids, citation_snapshots, citation_snapshot_hash,
        latency_breakdown, rail
    ) VALUES (
        :turn_id, :query_hash, :query_preview, :search_plan::jsonb,
        :hard_constraints::jsonb, :soft_preferences::jsonb,
        :exclusions::jsonb, :relaxations::jsonb,
        :embedding_model, :rerank_model, :retrieval_config::jsonb,
        :index_parameters::jsonb, :candidate_product_ids::jsonb,
        :vector_ranks::jsonb, :lexical_ranks::jsonb, :rrf_scores::jsonb,
        :rerank_scores::jsonb, :merchandising_rules::jsonb,
        :memory_record_ids_used::jsonb, :citation_ids::jsonb,
        :citation_snapshots::jsonb, :citation_snapshot_hash,
        :latency_breakdown::jsonb, :rail
    )
"""

# Module-level clients for Lambda warm start reuse
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=REGION)










# --- MCP Tool implementations ---


def _write_tool_audit_in_transaction(
    transaction_id: str,
    tool: str,
    args: dict,
    result: dict,
    latency_ms: int,
) -> None:
    """Audit a stock mutation in its own transaction.

    `restock_inventory` is an operator action: its arguments carry a product and a
    warehouse, never a customer, so the session handle names the acting role.
    Deriving `gateway-<customer_id>` here would write `gateway-unknown` on
    every row.
    """
    write_tool_audit(
        transaction_id,
        tool=tool,
        args=args,
        result=result,
        latency_ms=latency_ms,
        session_id="gateway-stock-keeper",
    )


# Mirrors ``HybridSearch._build_or_tsquery`` in services/hybrid_search.py.
# ``plainto_tsquery`` ANDs every stem together, so a conversational query such
# as "a thoughtful gift for someone who loves morning rituals" matches no
# description at all and the lexical branch contributes nothing. The in-process
# rail OR-joins the meaningful tokens and lets ``to_tsquery`` stem them; this
# rail must do the same or the two rails rank one catalog differently.
# tests/test_gateway_eligibility_parity.py holds the two builders to identical
# output and the stop-word set to the same literal.
_FTS_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "have", "has",
    "are", "was", "were", "from", "into", "out", "but", "not",
    "any", "all", "some", "one", "two", "three", "what", "where",
    "when", "how", "who", "why", "you", "your", "yours", "our",
    "their", "they", "them", "his", "her", "him", "she", "him",
    "let", "lets", "just", "really", "also", "more", "most",
    "much", "many", "very",
    # Conversational filler that never adds retrieval signal.
    "something", "someone", "somebody", "anything", "anyone",
    "thing", "things", "stuff", "kind", "sort", "type",
    "good", "great", "nice", "really", "would", "could", "should",
    "want", "need", "like", "love", "loves", "loving",
    # Generic shopping verbs.
    "find", "show", "give", "get", "browse", "recommend",
    "suggest", "help", "tell", "look", "looking",
})


def _build_or_tsquery(query: str) -> str:
    """OR-of-tokens input for ``to_tsquery``, identical to the in-process builder."""
    if not query:
        return ""
    cleaned = re.sub(r"[^\w\s-]", " ", query.lower())
    tokens = [t.strip("-") for t in cleaned.split() if len(t) > 2]
    tokens = [t for t in tokens if t not in _FTS_STOP_WORDS]
    seen: set = set()
    unique: list = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return " | ".join(unique)


def _as_number(value: Any) -> float | None:
    """A row value as a float, or ``None`` when it cannot be judged."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _violates_hard_filters(
    row: dict[str, Any],
    *,
    max_price: float | None = None,
    min_rating: float | None = None,
    category: str | None = None,
) -> bool:
    """Post-rerank eligibility recheck, mirroring the in-process executor.

    ``services/planned_hybrid_retrieval.py::_violates_hard_constraints`` rechecks
    every returned row against the hard predicates after the reranker, so a row
    that slipped past the SQL is never returned. A field the row does not carry,
    or carries as something uncoercible, cannot be judged and is left to the SQL
    predicate, which remains the enforcement point.
    """
    price = _as_number(row.get("price"))
    if max_price and price is not None and price > float(max_price) + 1e-9:
        return True
    rating = _as_number(row.get("stars", row.get("rating")))
    if min_rating and rating is not None and rating < float(min_rating) - 1e-9:
        return True
    name = row.get("category_name", row.get("category"))
    if category and name is not None and str(category).lower() not in str(name).lower():
        return True
    quantity = _as_number(row.get("quantity"))
    if quantity is not None and quantity <= 0:
        return True
    return False


def semantic_search(
    query: str,
    limit: int = 5,
    max_price: float = None,
    min_rating: float = None,
    category: str = None,
) -> dict:
    """Search products by semantic similarity using pgvector.

    Every filter, ``category`` included, is a SQL predicate, so the limit
    applies after the filters exactly as ``BusinessLogic.search_products``
    applies it in process. Filtering the top rows afterwards would return
    fewer than ``limit`` pieces whenever a category is asked for.
    """
    embedding = _get_embedding(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    # Same eligibility floor as services/vector_search.py: in stock and not a
    # seeded archive distractor. Swapping rails must not widen the catalog.
    where_clauses = ["quantity > 0", "NOT (tags ? 'archive')"]
    parameters = [
        {"name": "embedding", "value": {"stringValue": embedding_str}},
        {"name": "lim", "value": {"longValue": int(limit)}},
    ]
    if max_price:
        where_clauses.append("price <= :max_price")
        parameters.append({"name": "max_price", "value": {"doubleValue": float(max_price)}})
    if min_rating:
        where_clauses.append("rating >= :min_rating")
        parameters.append({"name": "min_rating", "value": {"doubleValue": float(min_rating)}})
    if category:
        where_clauses.append("lower(category) LIKE :category")
        parameters.append(
            {"name": "category", "value": {"stringValue": _prepare_like_pattern(category)}}
        )
    where_sql = " AND ".join(where_clauses)

    # NO session GUCs here: each Data API execute_statement carries exactly
    # one statement ("Multistatements aren't supported", box-verified
    # 2026-06-12 — a prepended SET killed EVERY read tool on the Gateway
    # path). Multi-call transactions via transactionId are fine; a second
    # statement inside ONE call is not. The
    # hnsw.iterative_scan tuning stays on the in-process rail (psycopg);
    # at this catalog's scale it doesn't change recall anyway.
    #
    # Column names: the seeded schema (001_schema.sql) is description/
    # category/rating/badge — NOT the Amazon-dataset names these servers
    # were first written against (box-verified 2026-06-12: 42703). Aliases
    # keep the response keys the downstream Python already expects.
    sql = f"""
        SELECT "productId", name, description AS product_description, price,
               rating AS stars, reviews,
               category AS category_name, quantity, "imgUrl", updated_at,
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
        SELECT category AS category_name,
               COUNT(*) AS total_products,
               SUM(CASE WHEN quantity < 10 THEN 1 ELSE 0 END) AS low_stock,
               AVG(quantity)::int AS avg_quantity
        FROM {SCHEMA}.product_catalog
        GROUP BY category
        ORDER BY low_stock DESC
        LIMIT 10;
    """
    rows = _execute_sql(sql)
    return {"categories": rows}


def get_low_stock_products(limit: int = 5) -> dict:
    """Get products with lowest stock levels."""
    sql = f"""
        SELECT "productId", description AS product_description, price,
               rating AS stars, quantity, category AS category_name
        FROM {SCHEMA}.product_catalog
        WHERE quantity > 0 AND quantity < 10
        ORDER BY quantity ASC
        LIMIT :lim;
    """
    parameters = [{"name": "lim", "value": {"longValue": int(limit)}}]
    rows = _execute_sql(sql, parameters)
    return {"products": rows, "count": len(rows)}


def search_products_hybrid(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5,
) -> dict:
    """Hybrid retrieval: pgvector + Postgres FTS, RRF, Cohere Rerank v3.5.

    Mirrors `services.agent_tools.search_products_hybrid` but runs inside the
    Lambda microVM instead of the orchestrator's process. Three stages:

      1. Vector branch (pgvector cosine, k=20) and FTS branch
         (`ts_rank_cd` over the same OR-joined `to_tsquery` the in-process
         rail builds, k=20) execute in a single SQL statement against
         `pellier.product_catalog`. Each Data API `ExecuteStatement`
         carries exactly one statement, so we fold the two ranked lists
         into a CTE plus Reciprocal Rank Fusion (RRF) inside the same
         query. (Multi-call transactions are supported, see the
         `transactionId` path in `initiate_return`, but they still send
         one statement per call.) The hard filters (`max_price`,
         `min_rating`, `category`, and in-stock) are WHERE predicates on
         BOTH branches, before fusion, so an invalid row never enters the
         pool, never consumes reranker capacity, and never shortens the
         final list after the fact.
      2. The merged ~30-candidate pool is sent to Cohere Rerank v3.5
         (`cohere.rerank-v3-5:0`) through the Bedrock Agent Runtime
         `rerank` API (see `_bedrock_rerank`; IAM: `bedrock:Rerank`).
      3. The top `limit` reranked rows are returned in rerank order.

    On a Bedrock failure (rate limit, invalid response), we fall back to
    RRF order; the Observatory surfaces this as a missing rerank stage in
    telemetry rather than crashing the request.
    """
    retrieval_started = time.monotonic()
    embedding = _get_embedding(query)
    embedding_ms = int((time.monotonic() - retrieval_started) * 1000)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    # Mirrors services/hybrid_search.py: both branches gate on stock and on
    # the archive tag before fusion, so RRF never sees a retired piece.
    where_clauses = ["quantity > 0", "NOT (tags ? 'archive')"]
    parameters = [
        {"name": "embedding", "value": {"stringValue": embedding_str}},
        {"name": "ts_query", "value": {"stringValue": _build_or_tsquery(query)}},
    ]
    if max_price:
        where_clauses.append("price <= :max_price")
        parameters.append({"name": "max_price", "value": {"doubleValue": float(max_price)}})
    if min_rating:
        where_clauses.append("rating >= :min_rating")
        parameters.append({"name": "min_rating", "value": {"doubleValue": float(min_rating)}})
    if category:
        where_clauses.append("lower(category) LIKE :category")
        parameters.append(
            {
                "name": "category",
                "value": {"stringValue": _prepare_like_pattern(category)},
            }
        )
    where_sql = " AND ".join(where_clauses)

    # Hybrid retrieval in a single statement. RRF merges the two ranked
    # lists by `1/(60 + rank)`, the same constant the in-process
    # implementation uses, so participants get a one-to-one comparison
    # between paths. Single statement only: Data API rejects a prepended
    # SET (see semantic_search). The CTE shape folds everything into one
    # query, and the same hard predicates gate both branches.
    sql = f"""
        WITH vector_results AS (
          SELECT "productId" AS pid,
                 row_number() OVER (ORDER BY embedding <=> :embedding::vector) AS vrank
          FROM {SCHEMA}.product_catalog
          WHERE {where_sql}
          LIMIT 20
        ),
        fts_results AS (
          SELECT "productId" AS pid,
                 row_number() OVER (ORDER BY ts_rank_cd(description_tsv, to_tsquery('english', :ts_query)) DESC) AS frank
          FROM {SCHEMA}.product_catalog
          WHERE {where_sql}
            AND description_tsv @@ to_tsquery('english', :ts_query)
          LIMIT 20
        ),
        rrf AS (
          SELECT COALESCE(v.pid, f.pid) AS pid,
                 v.vrank AS vector_rank,
                 f.frank AS lexical_rank,
                 COALESCE(1.0 / (60 + v.vrank), 0) +
                 COALESCE(1.0 / (60 + f.frank), 0) AS rrf_score
          FROM vector_results v
          FULL OUTER JOIN fts_results f USING (pid)
        )
        SELECT pc."productId", pc.name, pc.description AS product_description, pc.price,
               pc.rating AS stars,
               pc.reviews, pc.category AS category_name, pc.quantity, pc."imgUrl",
               pc.updated_at,
               rrf.vector_rank, rrf.lexical_rank, rrf.rrf_score
        FROM rrf
        JOIN {SCHEMA}.product_catalog pc ON pc."productId" = rrf.pid
        ORDER BY rrf.rrf_score DESC
        LIMIT 30;
    """
    candidate_query_started = time.monotonic()
    candidates = _execute_sql(sql, parameters)
    candidate_query_ms = int((time.monotonic() - candidate_query_started) * 1000)

    # Rerank stage. Cohere wants plain text per document; we mirror
    # the in-process `_doc_for_rerank` shape (name + description + cat).
    documents = []
    for p in candidates:
        desc = (p.get("product_description") or "").strip()
        cat = (p.get("category_name") or "").strip()
        if len(desc) > 240:
            desc = desc[:237] + "…"
        name = (p.get("name") or "").strip()
        documents.append(f"{name} — {desc} ({cat})")

    rerank_started = time.monotonic()
    rerank_results = _bedrock_rerank(query, documents, top_n=min(limit * 3, 30))
    rerank_ms = int((time.monotonic() - rerank_started) * 1000)
    if rerank_results:
        ordered = [
            {**candidates[r["index"]], "rerank_score": float(r["relevance_score"])}
            for r in rerank_results
        ]
        search_method = "hybrid+rerank"
    else:
        ordered = [{**c, "rerank_score": None} for c in candidates]
        search_method = "hybrid (rerank fallback to RRF order)"

    # The hard filters ran in SQL before fusion and are rechecked on the
    # reranked rows, as the in-process executor does, so a row that slipped
    # past the SQL is never returned on this rail either.
    eligible = [
        row
        for row in ordered
        if not _violates_hard_filters(
            row, max_price=max_price, min_rating=min_rating, category=category
        )
    ]
    filtered = eligible[: max(1, int(limit))]

    return {
        "status": "success",
        "query": query,
        "count": len(filtered),
        "products": filtered,
        "search_method": search_method,
        "strategy": "gateway-hybrid-rerank",
        "pool_size": len(candidates),
        # This does not leave the Lambda. ``lambda_handler`` uses it to
        # persist the exact candidate/ranking evidence, then removes it
        # before returning the MCP result to the Runtime model.
        "_receipt_evidence": {
            "candidates": candidates,
            "ordered": ordered,
            "selected": filtered,
            "embedding_model": EMBED_MODEL_ID,
            "rerank_model": (
                "cohere.rerank-v3-5:0" if rerank_results else None
            ),
            "retrieval_config": {
                "strategy": "gateway-hybrid-rerank",
                "rrf_k": 60,
                "candidate_limit": 30,
                "rerank_top_n": min(limit * 3, 30),
                "rerank_applied": bool(rerank_results),
                "hard_filters_before_fusion": True,
                "eligibility_recheck": True,
                "eligibility_dropped": len(ordered) - len(eligible),
            },
            "index_parameters": {
                "vector_candidate_limit": 20,
                "lexical_candidate_limit": 20,
            },
            "latency_breakdown": {
                "embedding_ms": embedding_ms,
                "candidate_query_ms": candidate_query_ms,
                "rerank_ms": rerank_ms,
            },
        },
    }


def _gateway_receipt_product_id(row: dict[str, Any]) -> str | None:
    value = row.get("productId", row.get("product_id"))
    return str(value) if value is not None and str(value).strip() else None


def _gateway_citation_snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    """Capture the catalog evidence used by this Lambda invocation."""
    product_id = _gateway_receipt_product_id(row)
    if product_id is None:
        return None
    name = " ".join(str(row.get("name") or product_id).split())
    description = " ".join(
        str(row.get("description", row.get("product_description", "")) or "").split()
    )
    quote = f"{name}: {description}".rstrip(":").strip()[:280]
    updated_at = row.get("updated_at")
    revision = (
        updated_at.isoformat()
        if hasattr(updated_at, "isoformat")
        else str(updated_at).strip() or None
    )
    return {
        "entity_id": product_id,
        "source_uri": f"aurora://pellier/product_catalog/{product_id}",
        "revision": revision,
        "quote": quote,
    }


def _gateway_citation_snapshot_hash(snapshots: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        snapshots,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rank_values(
    rows: list[dict[str, Any]], key: str
) -> dict[str, float | int]:
    values: dict[str, float | int] = {}
    for row in rows:
        product_id = _gateway_receipt_product_id(row)
        value = row.get(key)
        if product_id is None or value is None:
            continue
        try:
            values[product_id] = (
                int(value) if key in {"vector_rank", "lexical_rank"} else float(value)
            )
        except (TypeError, ValueError):
            continue
    return values


def _similarity_scores(rows: list[dict[str, Any]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in rows:
        product_id = _gateway_receipt_product_id(row)
        value = row.get("similarity")
        if product_id is None or value is None:
            continue
        try:
            scores[product_id] = float(value)
        except (TypeError, ValueError):
            continue
    return scores


def _receipt_json_parameter(name: str, value: Any) -> dict[str, Any]:
    return {
        "name": name,
        "value": {
            "stringValue": json.dumps(
                value,
                default=str,
                separators=(",", ":"),
            )
        },
    }


def _receipt_string_parameter(name: str, value: str | None) -> dict[str, Any]:
    value_field = {"isNull": True} if value is None else {"stringValue": value}
    return {"name": name, "value": value_field}


def _persist_gateway_retrieval_receipt(
    *,
    turn_id: Any,
    query: str,
    arguments: dict[str, Any],
    evidence: dict[str, Any],
    latency_ms: int,
) -> bool:
    """Persist Gateway retrieval facts without making catalog search brittle.

    The Lambda has no authenticated shopper principal or session identifier to
    infer safely. It writes only a route-minted turn correlation identifier;
    the trusted storefront then joins the record to principal/session evidence
    in ``governed_turn_receipts`` once the complete turn terminates.
    """
    if not isinstance(turn_id, str) or not _TURN_ID_RE.fullmatch(turn_id):
        logger.warning("Gateway retrieval receipt skipped: missing valid server turn id")
        return False

    candidates = [
        row for row in evidence.get("candidates", []) if isinstance(row, dict)
    ]
    ordered = [row for row in evidence.get("ordered", []) if isinstance(row, dict)]
    selected = [
        row for row in evidence.get("selected", []) if isinstance(row, dict)
    ]
    candidate_product_ids = [
        product_id
        for row in candidates
        if (product_id := _gateway_receipt_product_id(row)) is not None
    ]
    citation_ids = [
        product_id
        for row in selected
        if (product_id := _gateway_receipt_product_id(row)) is not None
    ]
    citation_snapshots = [
        snapshot
        for row in selected
        if (snapshot := _gateway_citation_snapshot(row)) is not None
    ]
    hard_constraints = {
        "in_stock": True,
        **{
            key: arguments[key]
            for key in ("max_price", "min_rating", "category")
            if arguments.get(key) not in (None, "", 0, 0.0)
        },
    }
    retrieval_config = evidence.get("retrieval_config") or {}
    search_plan = {
        "source": "agentcore-gateway-lambda",
        "strategy": retrieval_config.get("strategy", "hybrid"),
        "hard_constraints": hard_constraints,
        "soft_preferences": {},
        "exclusions": [],
        "relaxations": [],
    }
    normalized_query = " ".join(query.lower().split())
    vector_ranks = evidence.get("vector_ranks")
    if not isinstance(vector_ranks, dict):
        vector_ranks = _rank_values(candidates, "vector_rank")
    lexical_ranks = evidence.get("lexical_ranks")
    if not isinstance(lexical_ranks, dict):
        lexical_ranks = _rank_values(candidates, "lexical_rank")
    rrf_scores = evidence.get("rrf_scores")
    if not isinstance(rrf_scores, dict):
        rrf_scores = _rank_values(candidates, "rrf_score")
    rerank_scores = evidence.get("rerank_scores")
    if not isinstance(rerank_scores, dict):
        rerank_scores = _rank_values(ordered, "rerank_score")
    latency_breakdown = {
        **{
            key: max(0, int(value))
            for key, value in (evidence.get("latency_breakdown") or {}).items()
            if isinstance(value, (int, float))
        },
        "total_ms": max(0, int(latency_ms)),
    }
    parameters = [
        _receipt_string_parameter("turn_id", turn_id),
        _receipt_string_parameter(
            "query_hash",
            hashlib.sha256(normalized_query.encode("utf-8")).hexdigest(),
        ),
        _receipt_string_parameter("query_preview", query[:120]),
        _receipt_json_parameter("search_plan", search_plan),
        _receipt_json_parameter("hard_constraints", hard_constraints),
        _receipt_json_parameter("soft_preferences", {}),
        _receipt_json_parameter("exclusions", []),
        _receipt_json_parameter("relaxations", []),
        _receipt_string_parameter(
            "embedding_model",
            str(evidence["embedding_model"])
            if evidence.get("embedding_model")
            else None,
        ),
        _receipt_string_parameter(
            "rerank_model",
            str(evidence["rerank_model"])
            if evidence.get("rerank_model")
            else None,
        ),
        _receipt_json_parameter(
            "retrieval_config", retrieval_config
        ),
        _receipt_json_parameter(
            "index_parameters", evidence.get("index_parameters") or {}
        ),
        _receipt_json_parameter("candidate_product_ids", candidate_product_ids),
        _receipt_json_parameter("vector_ranks", vector_ranks),
        _receipt_json_parameter("lexical_ranks", lexical_ranks),
        _receipt_json_parameter("rrf_scores", rrf_scores),
        _receipt_json_parameter("rerank_scores", rerank_scores),
        _receipt_json_parameter("merchandising_rules", []),
        _receipt_json_parameter("memory_record_ids_used", []),
        _receipt_json_parameter("citation_ids", citation_ids),
        _receipt_json_parameter("citation_snapshots", citation_snapshots),
        _receipt_string_parameter(
            "citation_snapshot_hash",
            _gateway_citation_snapshot_hash(citation_snapshots)
            if citation_snapshots
            else None,
        ),
        _receipt_json_parameter("latency_breakdown", latency_breakdown),
        _receipt_string_parameter("rail", "gateway-mcp"),
    ]
    try:
        _execute_write(_GATEWAY_RETRIEVAL_INSERT, parameters)
        return True
    except Exception as exc:
        logger.warning("Gateway retrieval receipt insert failed: %s", exc)
        return False


def _bedrock_rerank(query: str, documents: list, top_n: int) -> list:
    """Call Cohere Rerank v3.5 on Bedrock; return [] on any failure.

    Returning [] (instead of raising) matches the in-process service so
    the caller can fall back to RRF order. The Observatory surfaces a
    missing-rerank state from this signal — useful demo when the
    workshop wants to show graceful degradation under Bedrock pressure.
    """
    if not documents:
        return []
    model_id = "cohere.rerank-v3-5:0"
    model_arn = f"arn:aws:bedrock:{REGION}::foundation-model/{model_id}"
    sources = [
        {
            "type": "INLINE",
            "inlineDocumentSource": {
                "type": "TEXT",
                "textDocument": {"text": document},
            },
        }
        for document in documents
    ]
    try:
        response = bedrock_agent_runtime_client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            sources=sources,
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": model_arn},
                    "numberOfResults": min(top_n, len(sources)),
                },
            },
        )
        return [
            {
                "index": item.get("index"),
                "relevance_score": item.get("relevanceScore", 0.0),
            }
            for item in response.get("results", [])
        ]
    except Exception as exc:
        logger.warning(f"Cohere rerank failed: {exc}")
        return []


def restock_product(
    product_id: str,
    quantity: int,
    idempotency_key: str,
    warehouse_id: str = "BK-01",
    *,
    audit_arguments: dict | None = None,
) -> dict:
    """Execute the shared idempotent restock transaction in Aurora."""
    if quantity > 500:
        return {"error": "Restock quantity exceeds policy limit of 500", "denied": True}
    clean_key = str(idempotency_key or "").strip()
    if not clean_key:
        return {"error": "idempotency_key is required"}
    clean_warehouse = str(warehouse_id or "BK-01").strip() or "BK-01"
    request_payload = json.dumps(
        {
            "operation": "restock_inventory",
            "arguments": {
                "product_id": int(product_id),
                "quantity": int(quantity),
                "warehouse_id": clean_warehouse,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(request_payload.encode("utf-8")).hexdigest()
    started = time.monotonic()
    transaction_id = _begin_transaction()
    try:
        rows = _execute_in_transaction(
            transaction_id,
            f"SELECT {SCHEMA}.restock_shelf_idempotent("
            ":idempotency_key, :request_hash, :pid, :qty, :warehouse_id"
            ") AS result;",
            [
                {"name": "idempotency_key", "value": {"stringValue": clean_key}},
                {"name": "request_hash", "value": {"stringValue": request_hash}},
                {"name": "pid", "value": {"stringValue": str(product_id)}},
                {"name": "qty", "value": {"longValue": int(quantity)}},
                {"name": "warehouse_id", "value": {"stringValue": clean_warehouse}},
            ],
        )
        raw_result = rows[0].get("result") if rows else None
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        if result and result.get("status") == "success":
            response = {"success": True, "product": result}
        elif result and result.get("status") == "policy_blocked":
            response = {"error": result.get("message"), "denied": True}
        else:
            response = {
                "error": (result or {}).get("message", "Restock failed"),
                "result": result,
            }
        _write_tool_audit_in_transaction(
            transaction_id,
            "restock_inventory",
            audit_arguments
            or {
                "product_id": product_id,
                "quantity": quantity,
                "idempotency_key": clean_key,
                "warehouse_id": clean_warehouse,
            },
            response,
            int((time.monotonic() - started) * 1000),
        )
        _commit_transaction(transaction_id)
        return response
    except Exception:
        _rollback_transaction(transaction_id)
        raise


def search_products(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5,
) -> dict:
    """Canonical semantic catalog search used by Search Agent."""
    result = semantic_search(
        query=query,
        limit=limit,
        max_price=max_price,
        min_rating=min_rating,
        category=category,
    )
    candidates = [dict(product) for product in result.get("products", [])]
    result["status"] = "success"
    result["search_method"] = "semantic"
    selected = [
        product
        for product in result.get("products", [])
        if isinstance(product, dict)
    ]
    result["_receipt_evidence"] = {
        "candidates": candidates,
        "ordered": selected,
        "selected": selected,
        "embedding_model": EMBED_MODEL_ID,
        "rerank_model": None,
        "retrieval_config": {
            "strategy": "vector_similarity",
            "ranking_signal": "cosine_similarity",
            "similarity_scores": _similarity_scores(candidates),
        },
        "index_parameters": {},
        "vector_ranks": {
            product_id: rank
            for rank, product in enumerate(candidates, start=1)
            if (product_id := _gateway_receipt_product_id(product)) is not None
        },
        "lexical_ranks": {},
        "rrf_scores": {},
        "rerank_scores": {},
    }
    return result


def browse_category(
    category: str,
    min_rating: float = 0.0,
    max_price: float = None,
    limit: int = 5,
) -> dict:
    """Browse one category with deterministic rating and price filters."""
    # Mirrors BusinessLogic.get_products_by_category: archived rows never browse.
    conditions = [
        "lower(category) LIKE :category",
        "quantity > 0",
        "NOT (tags ? 'archive')",
    ]
    parameters = [
        {
            "name": "category",
            "value": {"stringValue": _prepare_like_pattern(category)},
        },
        {"name": "limit", "value": {"longValue": max(1, min(int(limit), 20))}},
    ]
    if min_rating:
        conditions.append("rating >= :min_rating")
        parameters.append(
            {"name": "min_rating", "value": {"doubleValue": float(min_rating)}}
        )
    if max_price is not None:
        conditions.append("price <= :max_price")
        parameters.append(
            {"name": "max_price", "value": {"doubleValue": float(max_price)}}
        )
    rows = _execute_sql(
        f"""
        SELECT "productId", name, brand, color, description, price,
               rating, reviews, category, quantity, "imgUrl", badge
          FROM {SCHEMA}.product_catalog
         WHERE {' AND '.join(conditions)}
         ORDER BY rating DESC, reviews::int DESC
         LIMIT :limit;
        """,
        parameters,
    )
    return {
        "status": "success",
        "category": category,
        "count": len(rows),
        "products": rows,
    }


def check_inventory(product_query: str = "") -> dict:
    """Return aggregate stock health or one product's warehouse breakdown."""
    tokens = [token for token in str(product_query).strip().split() if token]
    if not tokens:
        stats = _execute_sql(
            f"""
            SELECT COUNT(*) AS total_products,
                   SUM(quantity) AS total_units,
                   COUNT(*) FILTER (WHERE quantity <= 5) AS running_low_count,
                   COUNT(*) FILTER (WHERE quantity = 0) AS out_of_stock_count,
                   ROUND(AVG(quantity), 1) AS avg_quantity
              FROM {SCHEMA}.product_catalog;
            """
        )
        critical = get_low_stock_products(limit=5).get("products", [])
        return {
            "status": "success",
            "statistics": stats[0] if stats else {},
            "critical_items": critical,
        }

    clauses = []
    parameters = []
    for index, token in enumerate(tokens):
        name = f"token{index}"
        clauses.append(f"lower(name) LIKE :{name}")
        parameters.append(
            {"name": name, "value": {"stringValue": _prepare_like_pattern(token)}}
        )
    candidates = _execute_sql(
        f"""
        SELECT "productId", name, brand, color, price
          FROM {SCHEMA}.product_catalog
         WHERE {' AND '.join(clauses)}
         ORDER BY rating DESC NULLS LAST
         LIMIT 5;
        """,
        parameters,
    )
    if not candidates:
        return {
            "status": "not_found",
            "query": product_query,
            "message": f"No product matched '{product_query}'.",
        }
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "query": product_query,
            "candidates": candidates,
        }

    product = candidates[0]
    warehouses = _execute_sql(
        f"""
        SELECT w.id AS warehouse_id,
               w.display_name AS warehouse_name,
               w.city,
               w.ship_window_min,
               w.ship_window_max,
               wi.quantity
          FROM {SCHEMA}.warehouse_inventory wi
          JOIN {SCHEMA}.warehouses w ON w.id = wi.warehouse_id
         WHERE wi.product_id = :product_id
         ORDER BY wi.quantity DESC, w.id ASC;
        """,
        [
            {
                "name": "product_id",
                "value": {"stringValue": str(product["productId"])},
            }
        ],
    )
    return {
        "status": "success",
        "product": product,
        "total_units": sum(int(row.get("quantity") or 0) for row in warehouses),
        "warehouses": warehouses,
    }


def get_low_stock(limit: int = 5) -> dict:
    """Canonical low-stock read used by Inventory Agent."""
    result = get_low_stock_products(limit=limit)
    for product in result.get("products", []):
        quantity = int(product.get("quantity") or 0)
        product["restock_urgency"] = (
            "critical" if quantity <= 2 else "low" if quantity <= 5 else "watch"
        )
    result["status"] = "success"
    return result


def restock_inventory(
    product_id: int,
    quantity: int,
    idempotency_key: str,
    warehouse_id: str = "BK-01",
    *,
    audit_arguments: dict | None = None,
) -> dict:
    """Canonical bounded inventory write used by Inventory Agent."""
    if int(quantity) <= 0:
        return {"status": "error", "message": "Quantity must be positive."}
    result = restock_product(
        str(product_id),
        int(quantity),
        idempotency_key,
        warehouse_id,
        audit_arguments=audit_arguments,
    )
    if result.get("success"):
        product = result["product"]
        return {
            "status": "success",
            "product_id": product.get("product_id"),
            "name": product.get("name"),
            "new_quantity": product.get("new_quantity"),
            "added": int(quantity),
            "warehouse_id": product.get("warehouse_id"),
            "idempotent_replay": product.get("idempotent_replay", False),
        }
    if result.get("denied"):
        return {"status": "policy_blocked", "message": result["error"]}
    return {"status": "error", "message": result.get("error", "Restock failed")}


# --- Lambda MCP handler ---

# Every hybrid filter is a SQL predicate on both branches before fusion, never
# a post-pass over the fused list. One sentence, three parameters.
_PRE_FUSION_FILTER = "{} filter (SQL predicate on both branches before fusion)."

TOOLS = {
    "search_products": {
        "fn": search_products,
        "description": "Search products by natural language query using vector similarity. Returns ranked products with similarity scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 5},
                "max_price": {"type": "number", "description": "Maximum price filter"},
                "min_rating": {"type": "number", "description": "Minimum star rating filter"},
                "category": {"type": "string", "description": "Optional category substring filter"},
            },
            "required": ["query"],
        },
    },
    "search_products_hybrid": {
        "fn": search_products_hybrid,
        "description": "Hybrid retrieval over the catalog: pgvector cosine + Postgres FTS merged via RRF, reranked by Cohere Rerank v3.5. Higher quality than semantic_search at the cost of one extra Bedrock call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "max_price": {
                    "type": "number",
                    "description": _PRE_FUSION_FILTER.format("Maximum price"),
                },
                "min_rating": {
                    "type": "number",
                    "description": _PRE_FUSION_FILTER.format("Minimum star rating"),
                    "default": 0.0,
                },
                "category": {
                    "type": "string",
                    "description": (
                        _PRE_FUSION_FILTER.format("Category substring")
                        + " Leave unset to let the reranker pick across categories."
                    ),
                },
                "limit": {"type": "integer", "description": "Max results to return", "default": 5},
            },
            "required": ["query"],
        },
    },
    "browse_category": {
        "fn": browse_category,
        "description": "Browse products in a category with optional rating and price filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Product category"},
                "min_rating": {"type": "number", "default": 0.0},
                "max_price": {"type": "number"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["category"],
        },
    },
    "check_inventory": {
        "fn": check_inventory,
        "description": "Check aggregate inventory or a named product across the Brooklyn, Austin, and Portland warehouses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_query": {"type": "string", "description": "Optional product name or partial name"},
            },
            "required": [],
        },
    },
    "get_low_stock": {
        "fn": get_low_stock,
        "description": "Get products with critically low stock levels (below 10 units).",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max results", "default": 5}},
            "required": [],
        },
    },
    "restock_inventory": {
        "fn": restock_inventory,
        "description": "Restock a product by adding inventory. Quantity must be <= 500 per policy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "Product ID to restock"},
                "quantity": {"type": "integer", "description": "Quantity to add (max 500)"},
                "idempotency_key": {"type": "string", "description": "Stable unique key for this intended write"},
                "warehouse_id": {"type": "string", "description": "Warehouse receiving stock; defaults to BK-01"},
            },
            "required": ["product_id", "quantity", "idempotency_key"],
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
        started = time.monotonic()
        audit_arguments = dict(arguments)
        execution_arguments = {
            key: value for key, value in arguments.items() if key != "turn_id"
        }
        if tool_name == "restock_inventory":
            result = restock_inventory(
                **execution_arguments,
                audit_arguments=audit_arguments,
            )
        else:
            result = TOOLS[tool_name]["fn"](**execution_arguments)
        receipt_evidence = None
        if tool_name in {"search_products", "search_products_hybrid"} and isinstance(
            result, dict
        ):
            receipt_evidence = result.pop("_receipt_evidence", None)
            if isinstance(receipt_evidence, dict):
                _persist_gateway_retrieval_receipt(
                    turn_id=audit_arguments.get("turn_id"),
                    query=str(execution_arguments.get("query") or ""),
                    arguments=execution_arguments,
                    evidence=receipt_evidence,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
        if tool_name != "restock_inventory":
            audit_read_call(tool_name, audit_arguments, result, started)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}
