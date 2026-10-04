"""Model invocation receipts retain usage metadata and reject content."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from services.model_invocation_receipt import (
    invocation_rows,
    persist_model_invocation_receipts,
)


def _execution() -> dict[str, Any]:
    return {
        "trace_id": "a" * 32,
        "spans": [
            {
                "name": "invoke_agent recommendation",
                "kind": "specialist",
                "startMs": 7,
                "durationMs": 42,
                "traceId": "a" * 32,
                "spanId": "b" * 16,
                "attributes": {
                    "gen_ai.agent.name": "recommendation",
                    "gen_ai.request.model": "global.anthropic.claude-opus-5",
                    "gen_ai.usage.input_tokens": 21,
                    "gen_ai.usage.output_tokens": 8,
                    "gen_ai.usage.total_tokens": 29,
                    "gen_ai.response.stop_reason": "end_turn",
                    "gen_ai.input.messages": "private shopper prompt",
                    "gen_ai.output.messages": "private model response",
                    "gen_ai.tool.call.arguments": {"customer_id": "CUST-SECRET"},
                    "gen_ai.tool.call.result": {"order_id": "ORDER-SECRET"},
                },
            },
            {
                "name": "execute_tool search_products",
                "kind": "tool",
                "startMs": 10,
                "durationMs": 12,
                "attributes": {
                    "gen_ai.tool.name": "search_products",
                    "gen_ai.tool.call.arguments": {"query": "private query"},
                },
            },
        ],
    }


def test_invocation_rows_are_metadata_only() -> None:
    rows = invocation_rows(
        turn_id="turn-" + ("1" * 32),
        session_id="session-1",
        principal_sub="principal-1",
        agent_execution=_execution(),
        default_model_id=None,
        source="otel",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["purpose"] == "agent:recommendation"
    assert row["model_id"] == "global.anthropic.claude-opus-5"
    assert row["inference_profile_id"] == row["model_id"]
    assert row["input_tokens"] == 21
    assert row["output_tokens"] == 8
    assert row["total_tokens"] == 29
    assert row["latency_ms"] == 42
    assert row["trace_id"] == "a" * 32
    assert row["span_id"] == "b" * 16

    serialized = repr(row)
    for forbidden in (
        "private shopper prompt",
        "private model response",
        "CUST-SECRET",
        "ORDER-SECRET",
        "private query",
        "gen_ai.input.messages",
        "gen_ai.tool.call.arguments",
    ):
        assert forbidden not in serialized


def test_runtime_summary_is_explicit_when_no_usage_span_exists() -> None:
    rows = invocation_rows(
        turn_id="turn-" + ("2" * 32),
        session_id="session-2",
        principal_sub="principal-2",
        agent_execution={
            "spans": [],
            "trace_id": "c" * 32,
            "total_duration_ms": 55,
            "usage": {"total_tokens": 0},
        },
        default_model_id="global.anthropic.claude-sonnet-5",
        source="otel",
    )

    assert len(rows) == 1
    assert rows[0]["source"] == "runtime-summary"
    assert rows[0]["purpose"] == "terminal agent response"
    assert rows[0]["total_tokens"] == 0


def test_error_span_is_not_reported_as_a_success() -> None:
    execution = _execution()
    execution["spans"][0]["statusCode"] = "error"

    rows = invocation_rows(
        turn_id="turn-" + ("4" * 32),
        session_id="session-4",
        principal_sub="principal-4",
        agent_execution=execution,
        default_model_id=None,
        source="otel",
    )

    assert rows[0]["outcome"] == "failed"


def test_arbitrary_span_name_is_not_persisted_as_purpose() -> None:
    execution = _execution()
    span = execution["spans"][0]
    span["name"] = "chat PRIVATE-SHOPPER-PHRASING"
    span["attributes"].pop("gen_ai.agent.name")

    rows = invocation_rows(
        turn_id="turn-" + ("5" * 32),
        session_id="session-5",
        principal_sub="principal-5",
        agent_execution=execution,
        default_model_id=None,
        source="otel",
    )

    assert rows[0]["purpose"] == "model invocation"
    assert "PRIVATE-SHOPPER-PHRASING" not in repr(rows[0])


def test_writer_uses_on_conflict_for_retry_idempotency() -> None:
    class _DB:
        calls: list[tuple[Any, ...]]

        def __init__(self) -> None:
            self.calls = []

        async def execute_query(self, query: str, *params: Any) -> None:
            self.calls.append((query, *params))

    db = _DB()
    rows = asyncio.run(
        persist_model_invocation_receipts(
            db,
            turn_id="turn-" + ("3" * 32),
            session_id="session-3",
            principal_sub="principal-3",
            agent_execution=_execution(),
            source="otel",
        )
    )

    assert len(rows) == 1
    assert len(db.calls) == 1
    assert "ON CONFLICT (invocation_key) DO NOTHING" in db.calls[0][0]
    assert "private shopper prompt" not in repr(db.calls[0])


def test_migration_schema_structurally_excludes_model_content() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "migrations"
        / "043_evidence_ledger.sql"
    ).read_text()
    columns = migration.split(
        "CREATE TABLE IF NOT EXISTS pellier.model_invocation_receipts (",
        1,
    )[1].split(");", 1)[0].lower()

    for forbidden_column in (
        "prompt_text",
        "completion_text",
        "request_text",
        "response_text",
        "tool_arguments",
        "tool_results",
        "message_content",
    ):
        assert forbidden_column not in columns
    assert "before update or delete" in migration.lower()
