"""Tool Registry — Aurora pgvector deconstruction of MCP Gateway discovery.

This module is the Week 2 *teaching* surface for `/workshop` card 7. It
demonstrates the same primitive AgentCore Gateway provides (semantic
tool discovery) implemented directly over Postgres + pgvector, so
attendees can see what a managed primitive does for them.

Production recommendation stays "use Gateway". This module runs in
**shadow mode** alongside Gateway during workshop turns — both rank
the 9 tools on every query, and card 7 shows the two rankings
side-by-side. When Gateway isn't configured, the pgvector ranking is
the only thing card 7 has to show (the Card 7 banner makes this
explicit so attendees can tell dual-rank from single-source at a
glance).

Table: ``tools`` (migration 001), seeded by ``scripts/seed_tool_registry.py``.
Column reference:
    tool_id           TEXT PRIMARY KEY
    name              TEXT
    description       TEXT
    description_emb   vector(1024)   (Cohere Embed v4, input_type=search_document)
    enabled           BOOLEAN
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def discover_tools(
    db_service: Any,
    query_embedding: List[float],
    limit: int = 3,
    ef_search: int = 40,
) -> Dict[str, Any]:
    """Rank enabled tools by cosine similarity against ``query_embedding``.

    Returns a structured result with the ranking plus timing + SQL text so
    the workshop panel emitter has everything it needs in one call. The
    caller (AgentContext emitter) translates this into a
    ``TOOL REGISTRY · DISCOVER`` panel.

    Args:
        db_service: The app's DatabaseService (provides ``get_connection``).
            Uses the same pool + pgvector registration as vector_search.
        query_embedding: 1024-float Cohere embedding of the user turn
            (same vector the orchestrator uses for semantic product
            search — emitted once, reused for both).
        limit: Top-K to return. Card 7 shows the top 3 for visual parity
            with typical Gateway ``semantic_search`` result sets.
        ef_search: HNSW per-query accuracy knob. 40 matches vector_search
            default; tools table is tiny so accuracy is not the concern.

    Returns:
        Dict with keys:
            rows: list of dicts: ``{tool_id, name, description, similarity}``
                sorted by similarity desc.
            sql: the executed SQL text (for panel display).
            duration_ms: wall-clock of the query (rounded).
            total_count: how many enabled tools were in the pool.

        On error (including "tools table empty" — seeder hasn't run),
        returns ``{"rows": [], "error": "<message>", ...}`` so callers
        can degrade gracefully without raising.
    """
    sql = """
        WITH q AS (SELECT %s::vector AS emb)
        SELECT
            tool_id,
            name,
            description,
            1 - (description_emb <=> (SELECT emb FROM q)) AS similarity
        FROM tools
        WHERE enabled = true
          AND description_emb IS NOT NULL
        ORDER BY description_emb <=> (SELECT emb FROM q)
        LIMIT %s
    """
    ef_sql = int(ef_search)
    start = time.time()
    try:
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"SET LOCAL hnsw.ef_search = {ef_sql}")
                await cur.execute(sql, [query_embedding, int(limit)])
                raw = await cur.fetchall()
                await cur.execute(
                    "SELECT count(*) AS n FROM tools "
                    "WHERE enabled = true AND description_emb IS NOT NULL"
                )
                count_row = await cur.fetchone()
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        logger.warning("tool registry discovery failed: %s", exc)
        return {
            "rows": [],
            "sql": sql.strip(),
            "duration_ms": duration_ms,
            "total_count": 0,
            "error": str(exc),
        }

    duration_ms = int((time.time() - start) * 1000)
    total = _row_value(count_row, "n", default=0)
    rows: List[Dict[str, Any]] = []
    for r in raw:
        rows.append(
            {
                "tool_id": _row_value(r, "tool_id"),
                "name": _row_value(r, "name"),
                "description": _row_value(r, "description"),
                "similarity": float(_row_value(r, "similarity", default=0.0)),
            }
        )
    return {
        "rows": rows,
        "sql": sql.strip(),
        "duration_ms": duration_ms,
        "total_count": int(total or 0),
    }


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    """Extract a value from a dict_row or tuple-ish row.

    The app's connection factory uses ``dict_row``, but tests sometimes
    feed back plain dicts or psycopg Row objects; handle both so the
    helper is usable in unit tests without spinning up a real pool.
    """
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "__getitem__"):
        try:
            return row[key]
        except (KeyError, TypeError):
            return default
    return default
