"""Tests for the Atelier MEMORY · WORKING panel live overlay
(``routes.atelier_observatory._load_live_working``).

The Working panel is persona-scoped and carries no session id. It must
surface the SAME turns ``GET /api/agent/session/{id}`` returns for the
persona's latest storefront session, so the Atelier panel and that API
agree. Before the fix the overlay scanned the in-memory ``_SESSION_STORE``
for a ``user-{customer_id}-session-`` prefix — a namespace the anonymous
storefront never writes (it writes ``anon-{session_id}``) and a store the
SDK path never populates on a provisioned box — so the panel always fell
back to its fixture even after the participant made real turns.

These tests pin the corrected contract:
  * resolve the persona's latest session from ``pellier.tool_audit``
    (``persona-{persona}-{uuid}``), scoped to the persona;
  * rebuild the anonymous namespace ``anon-{session_id}``;
  * read it back via ``AgentCoreMemory.get_session_history`` (same path
    the section-3 API uses);
  * degrade to ``None`` (honest fixture fallback) on no session, empty
    history, or DB error — never a fabricated ``live``.

Uses a stub ``app.db_service`` and a patched ``get_session_history`` so
the suite runs offline without Aurora or AgentCore.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

import pytest

from routes import atelier_observatory as ao


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _StubDB:
    """Minimal ``fetch_one`` stub. ``row`` is returned verbatim; when
    ``raise_exc`` is set, ``fetch_one`` raises it to exercise the
    defensive-return path."""

    def __init__(
        self,
        row: Optional[dict] = None,
        raise_exc: Optional[Exception] = None,
    ) -> None:
        self.row = row
        self.raise_exc = raise_exc
        self.calls: list[tuple] = []

    async def fetch_one(self, query: str, *params: Any) -> Optional[dict]:
        self.calls.append((query, params))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.row


@pytest.fixture
def patch_memory(monkeypatch):
    """Patch ``AgentCoreMemory.get_session_history`` to return canned
    turns and capture the namespace it was asked for."""
    captured: dict = {}

    def _install(turns: List[dict]):
        from services.agentcore_memory import AgentCoreMemory

        async def _fake_history(self, session_ns: str):
            captured["namespace"] = session_ns
            return turns

        monkeypatch.setattr(AgentCoreMemory, "get_session_history", _fake_history)
        return captured

    return _install


def test_working_overlay_resolves_session_and_reads_anon_namespace(
    monkeypatch, patch_memory
) -> None:
    """Happy path: a Marco session in tool_audit is resolved, the
    anonymous namespace is rebuilt, and the history turns surface as
    working-panel items."""
    db = _StubDB(row={"session_id": "persona-marco-abc123"})
    monkeypatch.setattr(ao, "db_service", db, raising=False)
    # ao does ``from app import db_service`` inside the function, so the
    # patch target is the ``app`` module global.
    import app

    monkeypatch.setattr(app, "db_service", db, raising=False)

    captured = patch_memory([
        {"role": "user", "content": "What linen do you have for 10 days in Goa?"},
        {"role": "assistant", "content": "Here are four linen pieces."},
    ])

    items = _run(ao._load_live_working("marco"))

    assert items is not None
    assert len(items) == 2
    assert items[0]["substrate"] == "working"
    assert items[0]["content"].startswith("What linen")
    # Read the SAME anonymous namespace the storefront wrote under.
    assert captured["namespace"] == "anon-persona-marco-abc123"
    # The DB lookup is persona-scoped, not a bare "latest row".
    _query, params = db.calls[0]
    assert params == ("persona-marco-%",)


def test_working_overlay_returns_none_when_no_session(
    monkeypatch, patch_memory
) -> None:
    """No tool_audit row for the persona → None so the panel keeps its
    fixture (a persona who never shopped this session)."""
    db = _StubDB(row=None)
    import app

    monkeypatch.setattr(app, "db_service", db, raising=False)
    patch_memory([{"role": "user", "content": "unused"}])

    assert _run(ao._load_live_working("marco")) is None


def test_working_overlay_returns_none_when_history_empty(
    monkeypatch, patch_memory
) -> None:
    """Session resolved but history reads back empty → None (honest
    fixture, never a fabricated live)."""
    db = _StubDB(row={"session_id": "persona-marco-abc123"})
    import app

    monkeypatch.setattr(app, "db_service", db, raising=False)
    patch_memory([])

    assert _run(ao._load_live_working("marco")) is None


def test_working_overlay_returns_none_on_db_error(
    monkeypatch, patch_memory
) -> None:
    """A DB failure is swallowed into None — the panel is a teaching
    overlay and must not 500 the memory route."""
    db = _StubDB(raise_exc=RuntimeError("aurora unreachable"))
    import app

    monkeypatch.setattr(app, "db_service", db, raising=False)
    patch_memory([{"role": "user", "content": "unused"}])

    assert _run(ao._load_live_working("marco")) is None


def test_working_overlay_returns_none_for_unknown_persona(monkeypatch) -> None:
    """An unknown persona never touches the DB."""
    db = _StubDB(row={"session_id": "persona-x-1"})
    import app

    monkeypatch.setattr(app, "db_service", db, raising=False)

    assert _run(ao._load_live_working("nobody")) is None
    assert db.calls == []
