"""Contracts for the source activity emitted to the storefront chat."""

from __future__ import annotations

import pytest

from config import settings
from services.chat import _completed_tool_event, _database_activity_event
from services.data_source import database_source_label


def test_completed_tool_event_includes_measured_duration() -> None:
    assert _completed_tool_event("search_products", 184) == {
        "type": "tool_call",
        "tool": "search_products",
        "status": "completed",
        "duration_ms": 184,
    }


def test_database_event_names_the_runtime_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DB_HOST", "127.0.0.1")
    event = _database_activity_event([
        {"operation": "SELECT", "table": "products"},
    ])

    assert event["type"] == "db_queries"
    assert event["source"] == "Local PostgreSQL"
    assert event["queries"][0]["table"] == "products"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", "Local PostgreSQL"),
        ("127.0.0.1", "Local PostgreSQL"),
        (
            "dat4xx.cluster-abc123.us-east-1.rds.amazonaws.com",
            "Aurora PostgreSQL",
        ),
        (
            "dat4xx.cluster-ro-abc123.us-east-1.rds.amazonaws.com",
            "Aurora PostgreSQL",
        ),
        ("postgres.example.com", "PostgreSQL"),
    ],
)
def test_database_source_label_reflects_the_configured_host(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    expected: str,
) -> None:
    monkeypatch.setattr(settings, "DB_HOST", host)
    assert database_source_label() == expected
