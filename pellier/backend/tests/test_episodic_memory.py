"""Tests for ``services.episodic_memory`` — Aurora-seeded MEMORY · EPISODIC panel.

Covers:
- Anonymous callers emit a skipped panel (no rows, explicit meta).
- A known customer with seed rows emits a populated panel with
  relative timestamps.
- An unknown customer (empty query result) emits a "no seed rows"
  panel rather than raising.
- DB failure emits a panel with zero rows rather than propagating —
  episodic is a teaching overlay and must not break the turn.

Uses a stub ``db_service`` with a queued-result ``fetch_all`` so the
suite runs offline without Aurora.
"""

from __future__ import annotations

import asyncio
from typing import Any, List

from services.agent_context import AgentContext
from services.episodic_memory import (
    _format_relative,
    emit_memory_episodic_panel,
    fetch_episodic_seed,
)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _StubDB:
    """Minimal fetch_all stub. ``result`` is returned verbatim; when
    ``raise_exc`` is set, ``fetch_all`` raises it to exercise the
    defensive-return path."""

    def __init__(
        self,
        result: List[dict] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.result = result or []
        self.raise_exc = raise_exc
        self.calls: list[tuple] = []

    async def fetch_all(self, query: str, *params: Any) -> List[dict]:
        self.calls.append((query, params))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.result


def test_format_relative_covers_days_weeks_months() -> None:
    assert _format_relative(0) == "today"
    assert _format_relative(-1) == "1 day ago"
    assert _format_relative(-3) == "3 days ago"
    assert _format_relative(-7) == "1 week ago"
    assert _format_relative(-14) == "2 weeks ago"
    assert _format_relative(-30) == "1 month ago"
    assert _format_relative(-60) == "2 months ago"


def test_fetch_episodic_seed_returns_empty_for_anonymous() -> None:
    db = _StubDB(result=[{"summary_text": "x", "ts_offset_days": -1}])
    rows = _run(fetch_episodic_seed(db, "anonymous"))
    assert rows == []
    # Anonymous callers must never hit the DB.
    assert db.calls == []


def test_fetch_episodic_seed_returns_empty_on_db_error() -> None:
    db = _StubDB(raise_exc=RuntimeError("pg connection lost"))
    rows = _run(fetch_episodic_seed(db, "CUST-MARCO"))
    assert rows == []


def test_fetch_episodic_seed_maps_rows_to_canonical_shape() -> None:
    db = _StubDB(
        result=[
            {"summary_text": "saw a linen shirt", "ts_offset_days": -3},
            {"summary_text": "asked about travel fabric", "ts_offset_days": -9},
        ]
    )
    rows = _run(fetch_episodic_seed(db, "CUST-MARCO", limit=2))
    assert rows == [
        {"summary_text": "saw a linen shirt", "ts_offset_days": -3},
        {"summary_text": "asked about travel fabric", "ts_offset_days": -9},
    ]
    # LIMIT parameter flows through to the SQL binding.
    assert db.calls[0][1] == ("CUST-MARCO", 2)


def test_emit_memory_episodic_panel_anonymous_emits_skipped_panel() -> None:
    ctx = AgentContext(session_id="s1", customer_id="anonymous", query="q")
    db = _StubDB()
    _run(emit_memory_episodic_panel(ctx, db_service=db))

    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert len(panels) == 1
    assert panels[0]["tag"] == "MEMORY · EPISODIC"
    assert panels[0]["rows"] == []
    assert "anonymous" in panels[0]["meta"]


def test_emit_memory_episodic_panel_populates_rows_for_known_customer() -> None:
    ctx = AgentContext(session_id="s1", customer_id="CUST-MARCO", query="q")
    db = _StubDB(
        result=[
            {"summary_text": "browsed linen shirts", "ts_offset_days": -3},
            {"summary_text": "asked about wrinkle resistance", "ts_offset_days": -9},
            {"summary_text": "added sage-green shirt", "ts_offset_days": -14},
        ]
    )
    rows = _run(emit_memory_episodic_panel(ctx, db_service=db))

    assert len(rows) == 3
    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert len(panels) == 1
    p = panels[0]
    assert p["tag"] == "MEMORY · EPISODIC"
    assert p["columns"] == ["when", "summary"]
    assert p["rows"] == [
        ["3 days ago", "browsed linen shirts"],
        ["1 week ago", "asked about wrinkle resistance"],
        ["2 weeks ago", "added sage-green shirt"],
    ]
    assert "CUST-MARCO" in p["meta"]
    assert p["trace_index"] == 1


def test_emit_memory_episodic_panel_no_seed_rows_still_emits_panel() -> None:
    """Unknown customer — empty result set. Panel still emits with a
    meta line pointing at the seed migration."""
    ctx = AgentContext(session_id="s1", customer_id="CUST-9999", query="q")
    db = _StubDB(result=[])
    _run(emit_memory_episodic_panel(ctx, db_service=db))

    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert len(panels) == 1
    assert panels[0]["rows"] == []
    assert "no seed rows" in panels[0]["meta"]
    assert "003_workshop_episodic_seed" in panels[0]["meta"]


def test_emit_memory_episodic_panel_survives_db_error() -> None:
    """DB error → panel with zero rows, NOT an unhandled exception."""
    ctx = AgentContext(session_id="s1", customer_id="CUST-MARCO", query="q")
    db = _StubDB(raise_exc=RuntimeError("connection reset"))

    _run(emit_memory_episodic_panel(ctx, db_service=db))

    panels = [e for e in ctx.events if e["type"] == "panel"]
    assert len(panels) == 1
    assert panels[0]["rows"] == []
