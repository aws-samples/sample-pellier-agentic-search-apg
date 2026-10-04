"""Tests for ``services.tool_audit_writer`` — Theo's paper-trail layer.

The writer is fire-and-forget and bridges sync (Strands hook callback)
to async (psycopg). We mock the DB service + run loop so the tests
run offline without flakiness from real coroutine scheduling.

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_tool_audit_writer.py -v
"""
from __future__ import annotations

import logging
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import tool_audit_writer


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a fresh module-level state."""
    monkeypatch.setattr(tool_audit_writer, "_db_service", None)
    monkeypatch.setattr(tool_audit_writer, "_main_loop", None)
    monkeypatch.setattr(tool_audit_writer, "_pending_audits", {})


@pytest.fixture
def mock_db_with_loop(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub a DatabaseService whose async methods return a fixed audit_id.

    The writer's _run_async bridge expects to schedule a coroutine on
    the main event loop; in tests we replace it with a synchronous
    runner that awaits whatever coroutine the writer hands it. This
    keeps test wall-clock low and avoids cross-thread scheduling.
    """
    db = MagicMock()
    db.fetch_one = AsyncMock(return_value={"audit_id": 12345})
    db.execute_query = AsyncMock(return_value=None)
    monkeypatch.setattr(tool_audit_writer, "_db_service", db)

    import asyncio

    def _sync_run(coro: Any) -> Any:
        # Each call gets its own loop — we never have a "running" loop
        # in pytest's default config, so this is safe.
        return asyncio.new_event_loop().run_until_complete(coro)

    monkeypatch.setattr(tool_audit_writer, "_run_async", _sync_run)
    return db


# ---------------------------------------------------------------------------
# record_allow — INSERT before the tool runs
# ---------------------------------------------------------------------------


class TestRecordAllow:

    def test_insert_when_db_initialized(self, mock_db_with_loop: MagicMock) -> None:
        tool_audit_writer.record_allow(
            tool_use_id="abc-123",
            tool_name="give_store_credit",
            caller="agent",
            args={"customer_id": "c-theo", "product_id": 21, "reason": "damaged"},
            session_id="sess-1",
        )
        # INSERT was called once with the expected SQL shape.
        assert mock_db_with_loop.fetch_one.call_count == 1
        call_args = mock_db_with_loop.fetch_one.call_args
        sql = call_args.args[0]
        assert "INSERT INTO pellier.tool_audit" in sql
        assert "RETURNING audit_id" in sql
        # args column is JSONB — verify the JSON is well-formed.
        positional = call_args.args[1:]
        assert positional[0] == "sess-1"
        assert positional[1] == "give_store_credit"
        assert positional[2] == "agent"
        args_json = json.loads(positional[3])
        assert args_json["product_id"] == 21
        # tool_use_id → audit_id mapping captured for the After event.
        assert tool_audit_writer._pending_audits["abc-123"] == 12345

    def test_insert_records_gateway_caller(self, mock_db_with_loop: MagicMock) -> None:
        # The managed Gateway rail (experience Lambda) writes caller="gateway";
        # the in-process rail writes caller="agent". `caller` is the rail
        # discriminator in pellier.tool_audit, so prove the writer threads a
        # non-"agent" value straight through to the INSERT binding unchanged.
        tool_audit_writer.record_allow(
            tool_use_id="gw-1",
            tool_name="give_store_credit",
            caller="gateway",
            args={"customer_id": "theo", "product_id": 37, "reason": "damaged"},
            session_id="gateway-theo",
        )
        assert mock_db_with_loop.fetch_one.call_count == 1
        positional = mock_db_with_loop.fetch_one.call_args.args[1:]
        assert positional[1] == "give_store_credit"
        assert positional[2] == "gateway"  # NOT defaulted to "agent"

    def test_no_op_when_db_not_initialized(self) -> None:
        # _db_service stays None (autouse fixture).
        tool_audit_writer.record_allow(
            tool_use_id="abc-123",
            tool_name="give_store_credit",
            caller="agent",
            args={"x": 1},
            session_id="sess-1",
        )
        # Nothing in pending_audits → nothing was attempted.
        assert tool_audit_writer._pending_audits == {}

    def test_no_op_when_tool_use_id_missing(
        self, mock_db_with_loop: MagicMock,
    ) -> None:
        tool_audit_writer.record_allow(
            tool_use_id=None,
            tool_name="give_store_credit",
            caller="agent",
            args={"x": 1},
            session_id="sess-1",
        )
        # No INSERT because we couldn't correlate the After event.
        assert mock_db_with_loop.fetch_one.call_count == 0

    def test_insert_failure_is_visible_at_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # `_run_async` fails before it awaits, so use a synchronous stub and
        # avoid manufacturing an un-awaited AsyncMock coroutine in this test.
        monkeypatch.setattr(
            tool_audit_writer, "_db_service", MagicMock(fetch_one=MagicMock())
        )

        def _raise(_: Any) -> None:
            raise RuntimeError("insert unavailable")

        monkeypatch.setattr(tool_audit_writer, "_run_async", _raise)

        with caplog.at_level(logging.WARNING, logger=tool_audit_writer.__name__):
            tool_audit_writer.record_allow(
                tool_use_id="abc-123",
                tool_name="give_store_credit",
                caller="agent",
                args={"x": 1},
                session_id="sess-1",
            )

        assert "tool_audit INSERT failed: insert unavailable" in caplog.text


# ---------------------------------------------------------------------------
# record_after — UPDATE with result + latency
# ---------------------------------------------------------------------------


class TestRecordAfter:

    def test_update_uses_pending_audit_id(self, mock_db_with_loop: MagicMock) -> None:
        # Seed a pending entry as if record_allow ran.
        tool_audit_writer._pending_audits["abc-123"] = 12345
        tool_audit_writer.record_after(
            tool_use_id="abc-123",
            result={"status": "success", "return_id": 42},
            latency_ms=187,
        )
        assert mock_db_with_loop.execute_query.call_count == 1
        sql = mock_db_with_loop.execute_query.call_args.args[0]
        assert "UPDATE pellier.tool_audit" in sql
        assert "result = %s::jsonb" in sql
        positional = mock_db_with_loop.execute_query.call_args.args[1:]
        result_json = json.loads(positional[0])
        assert result_json["return_id"] == 42
        assert positional[1] == 187
        assert positional[2] == 12345
        # The mapping is consumed (single-fire).
        assert "abc-123" not in tool_audit_writer._pending_audits

    def test_no_op_when_no_pending_entry(
        self, mock_db_with_loop: MagicMock,
    ) -> None:
        tool_audit_writer.record_after(
            tool_use_id="never-allowed",
            result={"x": 1},
            latency_ms=50,
        )
        assert mock_db_with_loop.execute_query.call_count == 0

    def test_truncates_oversized_result_payload(
        self, mock_db_with_loop: MagicMock,
    ) -> None:
        tool_audit_writer._pending_audits["abc-123"] = 99
        # Build a result that exceeds the 8KB cap.
        big_result = {"items": ["x" * 100 for _ in range(200)]}  # ~20KB JSON
        tool_audit_writer.record_after(
            tool_use_id="abc-123", result=big_result, latency_ms=10,
        )
        positional = mock_db_with_loop.execute_query.call_args.args[1:]
        truncated = json.loads(positional[0])
        assert truncated["_truncated"] is True
        assert "_head" in truncated
        assert len(positional[0]) < 9000  # Capped to ~8KB.

    def test_handles_unserializable_result(
        self, mock_db_with_loop: MagicMock,
    ) -> None:
        tool_audit_writer._pending_audits["abc-123"] = 99
        # An object whose default= still can't serialize — class instance.
        # default=str will succeed on most things; we use a self-referential
        # cycle that breaks json.dumps.
        cycle: Dict[str, Any] = {}
        cycle["self"] = cycle
        tool_audit_writer.record_after(
            tool_use_id="abc-123", result=cycle, latency_ms=10,
        )
        positional = mock_db_with_loop.execute_query.call_args.args[1:]
        payload = json.loads(positional[0])
        assert "_unserializable_repr" in payload

    def test_update_failure_is_visible_at_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr(
            tool_audit_writer,
            "_db_service",
            MagicMock(execute_query=MagicMock()),
        )
        tool_audit_writer._pending_audits["abc-123"] = 99

        def _raise(_: Any) -> None:
            raise RuntimeError("update unavailable")

        monkeypatch.setattr(tool_audit_writer, "_run_async", _raise)

        with caplog.at_level(logging.WARNING, logger=tool_audit_writer.__name__):
            tool_audit_writer.record_after(
                tool_use_id="abc-123",
                result={"status": "success"},
                latency_ms=10,
            )

        assert "tool_audit UPDATE failed: update unavailable" in caplog.text


def test_async_bridge_failure_is_visible_at_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Future:
        def result(self, timeout: float) -> None:
            raise RuntimeError("loop unavailable")

    monkeypatch.setattr(tool_audit_writer, "_main_loop", object())
    monkeypatch.setattr(
        tool_audit_writer.asyncio,
        "run_coroutine_threadsafe",
        lambda _coro, _loop: _Future(),
    )

    with caplog.at_level(logging.WARNING, logger=tool_audit_writer.__name__):
        assert tool_audit_writer._run_async(object()) is None

    assert "tool_audit _run_async: loop unavailable" in caplog.text


def test_operator_audit_failure_is_visible_at_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        tool_audit_writer,
        "_db_service",
        MagicMock(execute_query=MagicMock()),
    )

    def _raise(_: Any) -> None:
        raise RuntimeError("operator audit unavailable")

    monkeypatch.setattr(tool_audit_writer, "_run_async", _raise)

    with caplog.at_level(logging.WARNING, logger=tool_audit_writer.__name__):
        tool_audit_writer.record_operator_mutation(
            tool_name="give_store_credit",
            caller="rest",
            principal_sub="operator-1",
            args={"customer_id": "CUST-JESSICA", "amount_cents": 2500},
            result={"status": "success"},
        )

    assert "operator tool_audit INSERT failed: operator audit unavailable" in caplog.text


class TestFillOnceAlignment:
    """Migration 047 makes tool_audit fill-once at the database boundary.

    The writer's UPDATE is the one completion that trigger admits. These pin the
    statement to that shape, so a second delivery of the same After event is a
    no-op row count rather than an exception from inside the database.
    """

    def test_the_update_only_completes_a_row_that_is_still_open(
        self, mock_db_with_loop: MagicMock,
    ) -> None:
        tool_audit_writer._pending_audits["abc-123"] = 12345
        tool_audit_writer.record_after(
            tool_use_id="abc-123", result={"status": "success"}, latency_ms=12,
        )
        sql = mock_db_with_loop.execute_query.call_args.args[0]
        assert "result IS NULL" in sql
        assert "latency_ms IS NULL" in sql
        # And it still touches only the two completable columns.
        assignments = sql.split("SET", 1)[1].split("WHERE", 1)[0]
        for frozen in ("tool", "caller", "args", "session_id", "created_at"):
            assert frozen not in assignments

    def test_a_rejected_completion_is_visible_at_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A trigger refusal must not vanish: silent evidence loss is the failure mode."""
        monkeypatch.setattr(
            tool_audit_writer, "_db_service", MagicMock(execute_query=MagicMock()),
        )
        tool_audit_writer._pending_audits["abc-123"] = 12345

        def _raise(_: Any) -> None:
            raise RuntimeError("tool_audit row 12345 already finalized")

        monkeypatch.setattr(tool_audit_writer, "_run_async", _raise)
        with caplog.at_level(logging.WARNING, logger=tool_audit_writer.__name__):
            tool_audit_writer.record_after(
                tool_use_id="abc-123", result={"status": "success"}, latency_ms=12,
            )
        assert "already finalized" in caplog.text
