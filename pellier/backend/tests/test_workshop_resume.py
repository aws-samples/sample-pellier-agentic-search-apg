"""Tests for ``POST /api/atelier/resume`` — welcome-back turn.

Validates:
- 400 on anonymous / empty customer_id.
- 200 with the four MEMORY substrate panels in the MemoryDashboard's
  "four owners" order (WORKING → SEMANTIC → EPISODIC → PROCEDURAL) and a
  composed response text that mentions the customer's first name + most
  recent episode + a preference blurb when seed rows are present.
- PROCEDURAL reads the tool_audit aggregate (not the cohort-overlap
  JOIN) — the same source the standalone Atelier Procedural panel uses.
- DB failure does not 500 — every emitter swallows its read error and
  emits an empty panel, so the turn still composes a response event.

Uses a stub ``db_service`` installed via ``monkeypatch.setattr`` on the
``app`` module, since the route imports ``from app import db_service`` at
call time. Working + Semantic read AgentCore Memory directly, which is
offline-safe (in-memory fallback → empty) without a provisioned account,
so those two panels render empty in these tests — the honest degrade.
"""

from __future__ import annotations

from typing import Any, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.workshop import router as workshop_router


class _StubDB:
    """Minimal stub routing fetch_all / fetch_one by SQL keyword."""

    def __init__(
        self,
        episodic_rows: List[dict] | None = None,
        identity_row: dict | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._episodic = episodic_rows or []
        self._identity = identity_row
        self._raise = raise_exc
        self.fetch_all_calls: list[tuple] = []
        self.fetch_one_calls: list[tuple] = []

    async def fetch_all(self, query: str, *params: Any) -> List[dict]:
        self.fetch_all_calls.append((query, params))
        if self._raise:
            raise self._raise
        if "customer_episodic_seed" in query:
            return self._episodic
        if "tool_audit" in query:
            # Procedural aggregate: tool / calls / avg_ms.
            return [
                {"tool": "find_pieces", "calls": 7, "avg_ms": 240},
                {"tool": "floor_check", "calls": 3, "avg_ms": 95},
            ]
        return []

    async def fetch_one(self, query: str, *params: Any) -> dict | None:
        self.fetch_one_calls.append((query, params))
        if self._raise:
            raise self._raise
        # Working panel resolves the persona's latest session from
        # tool_audit; identity read hits pellier.customers.
        if "tool_audit" in query:
            return {"session_id": "persona-marco-abc123"}
        if "customers" in query:
            return self._identity
        return None


def _make_client(stub_db: _StubDB) -> TestClient:
    """Build a FastAPI app with the workshop router + a stubbed
    ``app.db_service`` attribute so the route's lazy import resolves."""
    import app as app_module

    app_module.db_service = stub_db  # type: ignore[attr-defined]
    fast = FastAPI()
    fast.include_router(workshop_router)
    return TestClient(fast)


def test_resume_rejects_anonymous_customer() -> None:
    db = _StubDB()
    client = _make_client(db)
    # "anonymous" triggers the 400 in the handler body.
    r = client.post("/api/atelier/resume", json={"customer_id": "anonymous"})
    assert r.status_code == 400


def test_resume_emits_four_substrate_panels_in_owner_order() -> None:
    db = _StubDB(
        episodic_rows=[
            {"summary_text": "Browsed mens linen shirts for Lisbon.", "ts_offset_days": -3},
            {"summary_text": "Asked about travel fabric.", "ts_offset_days": -9},
        ],
        identity_row={
            "name": "Marco Ferraro",
            "preferences_summary": "Linen & summer staples.",
        },
    )
    client = _make_client(db)

    r = client.post("/api/atelier/resume", json={"customer_id": "CUST-MARCO"})
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert body["session_id"].startswith("ws-")

    tags = [e["tag"] for e in body["events"] if e["type"] == "panel"]
    assert tags == [
        "MEMORY · WORKING",
        "MEMORY · SEMANTIC",
        "MEMORY · EPISODIC",
        "MEMORY · PROCEDURAL",
    ]

    # PROCEDURAL panel reads the tool_audit aggregate, not the cohort JOIN.
    procedural = next(
        e for e in body["events"] if e.get("tag") == "MEMORY · PROCEDURAL"
    )
    assert "tool_audit" in procedural["sql"]
    assert procedural["columns"] == ["tool", "calls", "avg_latency"]
    assert any("find_pieces" in row[0] for row in procedural["rows"])

    # Plan present with the three expected steps.
    plans = [e for e in body["events"] if e["type"] == "plan"]
    assert len(plans) == 1
    assert plans[0]["steps"] == ["Recall", "Summarize", "Offer"]

    # Response text references the customer's first name + most recent
    # episode + a preference blurb (falls back to stated prefs offline).
    responses = [e for e in body["events"] if e["type"] == "response"]
    assert len(responses) == 1
    text = responses[0]["text"]
    assert "Marco" in text
    assert "Lisbon" in text
    assert "Linen" in text


def test_resume_procedural_is_not_customer_scoped() -> None:
    """The procedural aggregate query carries no customer_id param — it
    aggregates over every ALLOWed call, matching the standalone panel."""
    db = _StubDB(episodic_rows=[], identity_row={"name": "Marco", "preferences_summary": "linen"})
    client = _make_client(db)

    r = client.post("/api/atelier/resume", json={"customer_id": "CUST-MARCO"})
    assert r.status_code == 200

    audit_calls = [c for c in db.fetch_all_calls if "tool_audit" in c[0]]
    assert len(audit_calls) == 1
    # Single param: the LIMIT. No customer_id threaded in.
    assert audit_calls[0][1] == (6,)


def test_resume_db_failure_emits_empty_panels_and_graceful_response() -> None:
    """DB failures inside the emitters are swallowed — each emits a panel
    with zero rows rather than raising, so the turn still composes a
    welcome-back response. The attendee sees four empty panels."""
    db = _StubDB(raise_exc=RuntimeError("connection reset"))
    client = _make_client(db)

    r = client.post("/api/atelier/resume", json={"customer_id": "CUST-MARCO"})
    assert r.status_code == 200
    body = r.json()

    panels = [e for e in body["events"] if e["type"] == "panel"]
    assert [p["tag"] for p in panels] == [
        "MEMORY · WORKING",
        "MEMORY · SEMANTIC",
        "MEMORY · EPISODIC",
        "MEMORY · PROCEDURAL",
    ]
    for p in panels:
        assert p["rows"] == []

    # Response still composed — no episode / prefs to quote, so the text
    # falls back to a bare welcome line.
    responses = [e for e in body["events"] if e["type"] == "response"]
    assert len(responses) == 1
    assert "Welcome back" in responses[0]["text"]


def test_resume_session_id_roundtrips_when_supplied() -> None:
    db = _StubDB(
        episodic_rows=[],
        identity_row={"name": "Marco", "preferences_summary": "linen"},
    )
    client = _make_client(db)

    r = client.post(
        "/api/atelier/resume",
        json={"customer_id": "CUST-MARCO", "session_id": "ws-fixed123"},
    )
    assert r.status_code == 200
    assert r.json()["session_id"] == "ws-fixed123"


@pytest.fixture(autouse=True)
def _reset_db_service() -> None:
    """Reset ``app.db_service`` between tests so stubs don't leak."""
    yield
    try:
        import app as app_module

        app_module.db_service = None  # type: ignore[attr-defined]
    except Exception:
        pass
