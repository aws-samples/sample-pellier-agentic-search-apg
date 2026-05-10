"""Tests for the Week 2 Tool Registry pgvector discovery (Card 7 shadow mode).

Covers ``services.tool_registry.discover_tools`` and the panel emitter in
``services.workshop_panels``. psycopg is mocked via a FakeDB so tests
run offline against no real Aurora instance — same pattern as
``test_vector_search.py``.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Sequence

import pytest

from services.agent_context import AgentContext
from services.tool_registry import discover_tools
from services import workshop_panels


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeCursor:
    """Records every ``cur.execute(sql, params)`` call and serves fetch results
    in call order. Set ``rows_by_call_index`` to control fetchall per-call;
    unset calls return ``[]``.
    """

    def __init__(
        self,
        rows_by_call_index: Optional[Dict[int, List[Dict[str, Any]]]] = None,
        fetchone_by_call_index: Optional[Dict[int, Optional[Dict[str, Any]]]] = None,
    ):
        self.calls: List[tuple[str, Optional[Sequence[Any]]]] = []
        self._rows_by_call_index = rows_by_call_index or {}
        self._fetchone_by_call_index = fetchone_by_call_index or {}
        self._last_call_index: int = -1

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(
        self, sql: str, params: Optional[Sequence[Any]] = None
    ) -> None:
        self.calls.append((sql, params))
        self._last_call_index = len(self.calls) - 1

    async def fetchall(self) -> List[Dict[str, Any]]:
        return list(self._rows_by_call_index.get(self._last_call_index, []))

    async def fetchone(self) -> Optional[Dict[str, Any]]:
        return self._fetchone_by_call_index.get(self._last_call_index)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeDB:
    def __init__(self, cursor: FakeCursor):
        self.cursor = cursor
        self.conn = FakeConnection(cursor)

    @asynccontextmanager
    async def get_connection(self):
        yield self.conn


@pytest.fixture
def embedding() -> List[float]:
    return [0.02] * 1024


# ---------------------------------------------------------------------------
# discover_tools — SQL shape
# ---------------------------------------------------------------------------


def test_discover_tools_uses_cte_and_cosine(embedding: List[float]) -> None:
    """SQL SHALL use the CTE pattern and cosine <=> ordering."""
    cur = FakeCursor(
        rows_by_call_index={
            1: [  # the SELECT is call index 1 (after SET LOCAL at 0)
                {
                    "tool_id": "find_pieces",
                    "name": "find_pieces",
                    "description": "Semantic product search.",
                    "similarity": 0.87,
                },
            ],
        },
        fetchone_by_call_index={2: {"n": 9}},  # count() is call index 2
    )
    db = FakeDB(cur)
    _run(discover_tools(db, embedding, limit=3, ef_search=40))

    # SET LOCAL is first, SELECT is second, COUNT is third.
    assert len(cur.calls) == 3
    set_sql, _set_params = cur.calls[0]
    select_sql, select_params = cur.calls[1]

    assert set_sql.strip() == "SET LOCAL hnsw.ef_search = 40"
    assert "%s" not in set_sql  # utility SET never parameterised

    # CTE + cosine + 1 - distance similarity formula.
    assert "WITH q AS (SELECT %s::vector AS emb)" in select_sql
    assert re.search(
        r"ORDER\s+BY\s+description_emb\s*<=>\s*\(SELECT\s+emb\s+FROM\s+q\)",
        select_sql,
    ), select_sql
    assert re.search(
        r"1\s*-\s*\(description_emb\s*<=>\s*\(SELECT\s+emb\s+FROM\s+q\)\)\s+AS\s+similarity",
        select_sql,
    ), select_sql

    # Params pass the embedding and the limit, in that order.
    assert select_params[0] is embedding
    assert select_params[1] == 3


def test_discover_tools_returns_rows_in_similarity_shape(
    embedding: List[float],
) -> None:
    cur = FakeCursor(
        rows_by_call_index={
            1: [
                {
                    "tool_id": "find_pieces",
                    "name": "find_pieces",
                    "description": "Semantic product search.",
                    "similarity": 0.87,
                },
                {
                    "tool_id": "whats_trending",
                    "name": "whats_trending",
                    "description": "Bestsellers.",
                    "similarity": 0.42,
                },
            ],
        },
        fetchone_by_call_index={2: {"n": 9}},
    )
    result = _run(discover_tools(FakeDB(cur), embedding))

    assert [r["name"] for r in result["rows"]] == [
        "find_pieces",
        "whats_trending",
    ]
    assert result["rows"][0]["similarity"] == pytest.approx(0.87)
    assert result["total_count"] == 9
    assert result["duration_ms"] >= 0
    assert "error" not in result


def test_discover_tools_handles_empty_table(embedding: List[float]) -> None:
    """Seeder not yet run → zero rows, zero count, no error key."""
    cur = FakeCursor(
        rows_by_call_index={1: []},
        fetchone_by_call_index={2: {"n": 0}},
    )
    result = _run(discover_tools(FakeDB(cur), embedding))

    assert result["rows"] == []
    assert result["total_count"] == 0
    assert "error" not in result


def test_discover_tools_swallows_db_errors(embedding: List[float]) -> None:
    """A broken DB returns a structured error, never raises — teaching surface
    must degrade gracefully so the rest of the workshop turn survives."""

    class BoomCursor:
        async def __aenter__(self):
            raise RuntimeError("connection closed")

        async def __aexit__(self, *args):
            return None

    class BoomConn:
        def cursor(self):
            return BoomCursor()

    class BoomDB:
        @asynccontextmanager
        async def get_connection(self):
            yield BoomConn()

    result = _run(discover_tools(BoomDB(), embedding))
    assert result["rows"] == []
    assert "error" in result
    assert "connection closed" in result["error"]


# ---------------------------------------------------------------------------
# ef_search coercion — parity with hybrid_search SET LOCAL fix
# ---------------------------------------------------------------------------


def test_ef_search_is_coerced_to_int(embedding: List[float]) -> None:
    """Any attempt to smuggle SQL through ef_search MUST be int-coerced so
    interpolation into SET LOCAL can never include user strings."""
    cur = FakeCursor(
        rows_by_call_index={1: []},
        fetchone_by_call_index={2: {"n": 0}},
    )
    _run(discover_tools(FakeDB(cur), embedding, ef_search=64))
    set_sql, _ = cur.calls[0]
    assert set_sql.strip().endswith("= 64")


# ---------------------------------------------------------------------------
# workshop_panels — TOOL REGISTRY · DISCOVER panel shape
# ---------------------------------------------------------------------------


def test_tool_registry_panel_emits_panel_event(embedding: List[float]) -> None:
    cur = FakeCursor(
        rows_by_call_index={
            1: [
                {
                    "tool_id": "find_pieces",
                    "name": "find_pieces",
                    "description": "Semantic product search.",
                    "similarity": 0.91,
                },
            ],
        },
        fetchone_by_call_index={2: {"n": 9}},
    )
    ctx = AgentContext(session_id="ws-t", query="linen")
    _run(
        workshop_panels.emit_tool_registry_panel(
            ctx, db_service=FakeDB(cur), query_embedding=embedding, limit=3
        )
    )
    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert len(panels) == 1
    p = panels[0]
    assert p["tag"] == "TOOL REGISTRY · DISCOVER"
    assert p["tag_class"] == "cyan"
    assert p["columns"] == ["name", "similarity"]
    assert p["rows"] == [["find_pieces", "0.910"]]
    assert "9 tool(s) indexed" in p["meta"]


def test_tool_registry_panel_meta_prompts_seeder_when_empty(
    embedding: List[float],
) -> None:
    cur = FakeCursor(
        rows_by_call_index={1: []},
        fetchone_by_call_index={2: {"n": 0}},
    )
    ctx = AgentContext(session_id="ws-t")
    _run(
        workshop_panels.emit_tool_registry_panel(
            ctx, db_service=FakeDB(cur), query_embedding=embedding
        )
    )
    panel = [e for e in ctx.events if e["type"] == "panel"][0]
    assert "seed_tool_registry.py" in panel["meta"]


# ---------------------------------------------------------------------------
# workshop_panels — GATEWAY · DISCOVER "skipped" panel when URL unset
# ---------------------------------------------------------------------------


def test_gateway_panel_emits_skipped_when_url_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", None, raising=False)

    ctx = AgentContext(session_id="ws-t", query="linen")
    result = workshop_panels.emit_gateway_panel(ctx, query_text="linen")

    assert result == {"configured": False, "url": None}
    panel = [e for e in ctx.events if e["type"] == "panel"][0]
    assert panel["tag"] == "GATEWAY · DISCOVER"
    assert "not set" in panel["meta"]
    assert panel["rows"] == []
