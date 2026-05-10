"""Tests for ``BusinessLogic.process_return`` and the ``process_return`` @tool.

The atomic transaction is the central correctness claim: ownership check
→ INSERT into returns → conditional UPDATE of product_catalog.quantity,
all in one go. We mock psycopg so these run offline; the real Aurora
write is exercised in the live verification phase.

Runnable from the repo root:
    blaize-bazaar/backend/.venv/bin/python -m pytest \
        blaize-bazaar/backend/tests/test_process_return.py -v
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Sequence

import pytest

from services.business_logic import BusinessLogic


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Scripted FakeCursor — feeds different fetchone() responses to each
# step of the process_return transaction so we can exercise success
# and rejection paths without a live DB.
# ---------------------------------------------------------------------------


class FakeCursor:
    """Records every execute(); fetchone() returns scripted responses."""

    def __init__(self, fetchone_returns: List[Optional[Dict[str, Any]]]):
        self._returns = list(fetchone_returns)
        self._next = 0
        self.executes: List[tuple[str, Optional[Sequence[Any]]]] = []

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(self, sql: str, params: Any = None) -> None:
        self.executes.append((sql, params))

    async def fetchone(self) -> Optional[Dict[str, Any]]:
        if self._next >= len(self._returns):
            return None
        out = self._returns[self._next]
        self._next += 1
        return out


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeDB:
    def __init__(self, fetchone_returns: List[Optional[Dict[str, Any]]]):
        self.cursor = FakeCursor(fetchone_returns)
        self.conn = FakeConnection(self.cursor)

    @asynccontextmanager
    async def get_connection(self):
        yield self.conn


# ---------------------------------------------------------------------------
# Defense-in-depth: bad reasons rejected before SQL runs
# ---------------------------------------------------------------------------


class TestReasonValidation:

    def test_unknown_reason_returns_policy_blocked(self) -> None:
        db = FakeDB([])  # SQL never runs
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-1", 21, "evil"))
        assert result["status"] == "policy_blocked"
        assert "evil" in result["message"]
        # No SQL executed because the guard runs before get_connection().
        assert db.cursor.executes == []

    def test_empty_reason_returns_policy_blocked(self) -> None:
        db = FakeDB([])
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-1", 21, ""))
        assert result["status"] == "policy_blocked"

    @pytest.mark.parametrize("reason", [
        "damaged", "wrong_size", "not_as_described", "changed_mind", "other",
    ])
    def test_canonical_reasons_pass_validation(self, reason: str) -> None:
        # Ownership check returns no rows so the call rejects on
        # ownership, but only AFTER reason validation passed (proving
        # the reason was canonical).
        db = FakeDB([None])
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-1", 21, reason))
        # If reason had been blocked, status would be "policy_blocked";
        # we expect "error" because ownership failed.
        assert result["status"] == "error"
        assert "did not order" in result["message"]


# ---------------------------------------------------------------------------
# Ownership: SQL JOIN gates whose state the agent can mutate
# ---------------------------------------------------------------------------


class TestOwnership:

    def test_no_order_row_rejects_with_error(self) -> None:
        db = FakeDB([None])  # ownership check returns no row
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-99", 21, "damaged"))
        assert result["status"] == "error"
        assert "did not order" in result["message"]
        # Only the SELECT 1 ran — no INSERT or UPDATE attempted.
        assert len(db.cursor.executes) == 1
        assert "SELECT 1 FROM orders" in db.cursor.executes[0][0]

    def test_owned_product_proceeds_to_insert(self) -> None:
        db = FakeDB([
            {"?column?": 1},                                          # ownership
            {"id": 42},                                                # INSERT RETURNING
            {"productId": 21, "name": "Wabi-Sabi Bowl", "quantity": 8},  # UPDATE for damaged
        ])
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-theo", 21, "damaged"))
        assert result["status"] == "success"
        assert result["return_id"] == 42


# ---------------------------------------------------------------------------
# Damaged-only quantity decrement
# ---------------------------------------------------------------------------


class TestQuantityAdjustment:

    def test_damaged_decrements_quantity(self) -> None:
        db = FakeDB([
            {"?column?": 1},
            {"id": 42},
            {"productId": 21, "name": "Wabi-Sabi Bowl", "quantity": 7},
        ])
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-theo", 21, "damaged"))
        assert result["status"] == "success"
        assert result["new_quantity"] == 7
        assert result["name"] == "Wabi-Sabi Bowl"
        # Three SQL statements: ownership SELECT, INSERT, UPDATE.
        assert len(db.cursor.executes) == 3
        sqls = [s[0] for s in db.cursor.executes]
        assert "SELECT 1 FROM orders" in sqls[0]
        assert "INSERT INTO returns" in sqls[1]
        assert "UPDATE blaize_bazaar.product_catalog" in sqls[2]
        assert "GREATEST(quantity - 1, 0)" in sqls[2]

    def test_non_damaged_does_not_update_quantity(self) -> None:
        db = FakeDB([
            {"?column?": 1},
            {"id": 42},
            {"productId": 21, "name": "Wabi-Sabi Bowl"},  # SELECT for name only
        ])
        logic = BusinessLogic(db)  # type: ignore[arg-type]
        result = _run(logic.process_return("c-theo", 21, "changed_mind"))
        assert result["status"] == "success"
        assert result["new_quantity"] is None
        # Three statements but the third is a SELECT, not an UPDATE.
        assert len(db.cursor.executes) == 3
        third_sql = db.cursor.executes[2][0]
        assert "UPDATE" not in third_sql
        assert "SELECT" in third_sql


# ---------------------------------------------------------------------------
# Tool wrapper — the @tool that agents actually call
# ---------------------------------------------------------------------------


class TestToolWrapper:

    def test_returns_json_envelope_when_db_uninitialized(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import services.agent_tools as agent_tools
        monkeypatch.setattr(agent_tools, "_db_service", None)
        result = json.loads(agent_tools.process_return("c-1", 21, "damaged"))
        assert "Database service not initialized" in result["error"]
