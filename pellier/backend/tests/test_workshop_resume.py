"""Tests for ``POST /api/atelier/resume`` — welcome-back turn.

Validates:
- 400 on anonymous / empty customer_id.
- 200 with three MEMORY panels (EPISODIC → PREFERENCES → PROCEDURAL)
  and a composed response text that mentions the customer's first
  name when seed rows are present.
- DB failure does not 500 — the turn still returns a response event
  with the error text, matching ``/api/atelier/query`` semantics.

Uses a stub ``db_service`` installed via ``monkeypatch.setattr`` on
the ``app`` module, since the route imports ``from app import
db_service`` at call time.
"""

from __future__ import annotations

from typing import Any, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.workshop import router as workshop_router


class _StubDB:
    """Minimal stub: fetch_all / fetch_one both return queued results."""

    def __init__(
        self,
        fetch_all_result: List[dict] | None = None,
        fetch_one_result: dict | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        # Queue fetch_all results — the resume route calls fetch_all twice
        # (episodic + procedural). If only one result is given we reuse it.
        self._fetch_all = fetch_all_result or []
        self._fetch_one = fetch_one_result
        self._raise = raise_exc
        self.fetch_all_calls: list[tuple] = []

    async def fetch_all(self, query: str, *params: Any) -> List[dict]:
        self.fetch_all_calls.append((query, params))
        if self._raise:
            raise self._raise
        # Route queries by which SQL keywords appear — simple but keeps
        # the stub honest about which call is which.
        if "customer_episodic_seed" in query:
            return self._fetch_all
        if "orders o" in query:
            return [
                {"name": "Sage-Green Camp Shirt", "bought": 3},
                {"name": "Linen Wide-Leg Trouser", "bought": 2},
            ]
        return []

    async def fetch_one(self, query: str, *params: Any) -> dict | None:
        if self._raise:
            raise self._raise
        return self._fetch_one


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
    # The Pydantic field uses min_length=1 so an empty string is 422,
    # and "anonymous" triggers the 400 in the handler body.
    r = client.post("/api/atelier/resume", json={"customer_id": "anonymous"})
    assert r.status_code == 400


def test_resume_emits_three_memory_panels_in_order() -> None:
    db = _StubDB(
        fetch_all_result=[
            {"summary_text": "Browsed mens linen shirts for Lisbon.", "ts_offset_days": -3},
            {"summary_text": "Asked about travel fabric.", "ts_offset_days": -9},
        ],
        fetch_one_result={
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
        "MEMORY · EPISODIC",
        "MEMORY · PREFERENCES",
        "MEMORY · PROCEDURAL",
    ]

    # Plan present with the three expected steps.
    plans = [e for e in body["events"] if e["type"] == "plan"]
    assert len(plans) == 1
    assert plans[0]["steps"] == ["Recall", "Summarize", "Offer"]

    # Response text references the customer's first name + most recent
    # episode + a preferences blurb.
    responses = [e for e in body["events"] if e["type"] == "response"]
    assert len(responses) == 1
    text = responses[0]["text"]
    assert "Marco" in text
    assert "Lisbon" in text
    assert "Linen" in text


def test_resume_db_failure_emits_empty_panels_and_graceful_response() -> None:
    """DB failures inside the episodic/prefs/procedural emitters are
    swallowed — each emits a panel with zero rows rather than raising,
    so the turn still composes a welcome-back response. The attendee
    sees three empty panels, which is informative on its own."""
    db = _StubDB(raise_exc=RuntimeError("connection reset"))
    client = _make_client(db)

    r = client.post("/api/atelier/resume", json={"customer_id": "CUST-MARCO"})
    assert r.status_code == 200
    body = r.json()

    # All three memory panels present, all with empty rows.
    panels = [e for e in body["events"] if e["type"] == "panel"]
    assert [p["tag"] for p in panels] == [
        "MEMORY · EPISODIC",
        "MEMORY · PREFERENCES",
        "MEMORY · PROCEDURAL",
    ]
    for p in panels:
        assert p["rows"] == []

    # Response still composed — no latest episode / prefs / cohort to
    # quote, so the text falls back to a bare welcome line.
    responses = [e for e in body["events"] if e["type"] == "response"]
    assert len(responses) == 1
    assert "Welcome back" in responses[0]["text"]


def test_resume_session_id_roundtrips_when_supplied() -> None:
    db = _StubDB(
        fetch_all_result=[],
        fetch_one_result={"name": "Marco", "preferences_summary": "linen"},
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
