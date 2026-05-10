"""Tests for routes/boutique.py — briefing + pulse.

Covers:
  - Time-of-day greeting branching (morning / afternoon / evening / night).
  - Anonymous vs signed-in branching for the briefing.
  - Best-effort given_name extraction from Cognito email claims.
  - Pulse returns 4 metrics with valid source tags.
  - Catalog snapshot degrades gracefully when DB fails.

Database is stubbed via an in-process fake — no live Aurora needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest

from routes import boutique


# ---------------------------------------------------------------------------
# _time_of_day_greeting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hour,expected_phase",
    [
        (5, "morning"),
        (11, "morning"),
        (12, "afternoon"),
        (16, "afternoon"),
        (17, "evening"),
        (21, "evening"),
        (22, "night"),
        (2, "night"),
        (4, "night"),
    ],
)
def test_time_of_day_greeting_with_name(hour: int, expected_phase: str) -> None:
    now = datetime(2026, 4, 25, hour, 0, 0)
    greeting = boutique._time_of_day_greeting(now, "Shayon")
    assert greeting == f"Good {expected_phase}, Shayon."


def test_time_of_day_greeting_anonymous_has_no_name() -> None:
    greeting = boutique._time_of_day_greeting(
        datetime(2026, 4, 25, 9, 0, 0), None
    )
    assert greeting == "Good morning."
    assert "," not in greeting  # no "Good morning, ." bug


# ---------------------------------------------------------------------------
# _extract_given_name
# ---------------------------------------------------------------------------


def test_extract_given_name_prefers_explicit_claim() -> None:
    name = boutique._extract_given_name(
        {"given_name": "Ana", "email": "ignored@example.com"}
    )
    assert name == "Ana"


def test_extract_given_name_derives_from_email_local_part() -> None:
    assert (
        boutique._extract_given_name({"email": "shayon.sanyal@example.com"})
        == "Shayon"
    )
    # `+` and `_` split as local-part separators.
    assert boutique._extract_given_name({"email": "ana+pellier@x.com"}) == "Ana"
    assert boutique._extract_given_name({"email": "yuki_ito@x.com"}) == "Yuki"


def test_extract_given_name_handles_anonymous_or_missing() -> None:
    assert boutique._extract_given_name(None) is None
    assert boutique._extract_given_name({}) is None
    assert boutique._extract_given_name({"email": "anonymous"}) is None


def test_extract_given_name_strips_digits() -> None:
    """Local-part like ``user42`` should drop to ``User``, not ``User42``."""
    assert boutique._extract_given_name({"email": "user42@x.com"}) == "User"


# ---------------------------------------------------------------------------
# briefing endpoint
# ---------------------------------------------------------------------------


class FakeDB:
    """In-process DatabaseService stand-in exposing fetch_one only.

    Responses are keyed by a substring match on the SQL so the tests can
    prescribe different shapes per query without a full engine.
    """

    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[str] = []

    async def fetch_one(self, sql: str, *params: Any) -> Optional[dict]:
        self.calls.append(sql)
        for key, value in self.responses.items():
            if key in sql:
                return value
        return None


@pytest.fixture
def fake_db_full() -> FakeDB:
    """Fake DB keyed on the live boutique catalog column names.

    The catalog uses ``name``, ``description``, ``category``,
    ``badge``, ``rating``, ``reviews``. Legacy columns (``category_name``,
    ``"isBestSeller"``, ``product_description``, ``stars``) no longer
    exist — asserting on those is how we caught the production schema
    mismatch that broke the first ship.
    """
    return FakeDB(
        {
            "COUNT(*)": {"n": 92, "c": 6},
            # Bestseller-pick query matches on ``ORDER BY rating`` — keep
            # the fixture key narrow so it doesn't collide with the count.
            "ORDER BY": {
                "productId": "PSPRT0044",
                "name": "Ethiopia Guji Natural",
                "description": "Light roast, floral, natural process",
                "category": "Beans",
                "badge": "Bestseller",
            },
            "preferences_summary": {
                "preferences_summary": "Prefers cold-brew-friendly beans. Browses linen."
            },
        }
    )


@pytest.fixture
def fake_db_empty() -> FakeDB:
    return FakeDB({"COUNT(*)": {"n": 0, "c": 0}})


@pytest.mark.asyncio
async def test_briefing_signed_in_uses_given_name_and_preference(
    monkeypatch: pytest.MonkeyPatch, fake_db_full: FakeDB
) -> None:
    monkeypatch.setattr("app.db_service", fake_db_full, raising=False)
    user = {"sub": "u_marco", "email": "marco@example.com"}

    resp = await boutique.briefing(user=user)

    assert resp.greeting.startswith("Good ")
    assert "Marco" in resp.greeting
    # Real product count appears in the line AND as a chip.
    assert "92" in resp.line
    chip_labels = [c.label for c in resp.chips]
    assert "92" in chip_labels
    # Bestseller pick chip includes a product_id.
    product_chips = [c for c in resp.chips if c.kind == "product"]
    assert product_chips and product_chips[0].product_id == "PSPRT0044"
    # Preference snippet made it in.
    assert "cold-brew-friendly" in resp.line.lower()
    # The stub chip is visible so attendees see the scaffolding honestly.
    stub_chips = [c for c in resp.chips if c.source == "stub"]
    assert len(stub_chips) == 1
    # Three actions, exactly one primary.
    assert len(resp.actions) == 3
    assert sum(1 for a in resp.actions if a.primary) == 1


@pytest.mark.asyncio
async def test_briefing_anonymous_omits_name_and_preference(
    monkeypatch: pytest.MonkeyPatch, fake_db_full: FakeDB
) -> None:
    monkeypatch.setattr("app.db_service", fake_db_full, raising=False)
    resp = await boutique.briefing(user=None)

    assert "," not in resp.greeting  # "Good evening." not "Good evening, ."
    # The preference line is signed-in only — must not leak for anon.
    assert "cold-brew-friendly" not in resp.line.lower()
    # Catalog-facts still render for anon visitors.
    assert "92" in resp.line


@pytest.mark.asyncio
async def test_briefing_degrades_when_db_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``app.db_service`` is None (pre-boot / lifespan failure), the
    briefing MUST still return 200-shape data rather than raise."""
    monkeypatch.setattr("app.db_service", None, raising=False)

    resp = await boutique.briefing(user=None)
    # Greeting + actions always ship.
    assert resp.greeting.startswith("Good ")
    assert len(resp.actions) == 3


@pytest.mark.asyncio
async def test_briefing_handles_empty_catalog(
    monkeypatch: pytest.MonkeyPatch, fake_db_empty: FakeDB
) -> None:
    """Zero-product catalog drops the count-clause + pick but keeps actions."""
    monkeypatch.setattr("app.db_service", fake_db_empty, raising=False)
    resp = await boutique.briefing(user=None)
    # Doesn't claim "92 products" when there are 0.
    assert "0 products" not in resp.line
    assert "watching the boutique" in resp.line
    assert len(resp.actions) == 3


# ---------------------------------------------------------------------------
# pulse endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pulse_returns_four_metrics_with_valid_source_tags(
    monkeypatch: pytest.MonkeyPatch, fake_db_full: FakeDB
) -> None:
    monkeypatch.setattr("app.db_service", fake_db_full, raising=False)

    resp = await boutique.pulse()

    assert len(resp.metrics) == 4
    ids = [m.id for m in resp.metrics]
    assert ids == ["catalog", "agent_activity", "your_picks", "cost"]
    for m in resp.metrics:
        assert m.source in {"real", "stub", "partial"}
        assert m.primary  # non-empty
        assert m.label
    # Catalog metric carries the real count.
    catalog = next(m for m in resp.metrics if m.id == "catalog")
    assert catalog.source == "real"
    assert "92" in catalog.primary
    # Cost metric labeled honestly as process-scoped.
    cost = next(m for m in resp.metrics if m.id == "cost")
    assert cost.source == "partial"
    assert "process-scoped" in cost.secondary.lower()


@pytest.mark.asyncio
async def test_catalog_snapshot_uses_live_column_names_not_legacy(
    monkeypatch: pytest.MonkeyPatch, fake_db_full: FakeDB
) -> None:
    """Regression test for the first-ship bug: the catalog snapshot was
    written against the legacy column names (``category_name``,
    ``"isBestSeller"``, ``product_description``, ``stars``) which no
    longer exist on the boutique catalog. The snapshot SHALL query only
    columns that live in ``services/business_logic.py``'s documented
    schema: ``name``, ``category``, ``description``, ``badge``,
    ``rating``, ``reviews``."""
    monkeypatch.setattr("app.db_service", fake_db_full, raising=False)
    await boutique._catalog_snapshot(fake_db_full)

    joined_sql = " ".join(fake_db_full.calls).lower()
    # Legacy columns — SHALL NOT appear.
    assert "category_name" not in joined_sql
    assert "isbestseller" not in joined_sql
    assert "product_description" not in joined_sql
    assert " stars" not in joined_sql  # leading space avoids matching SQL *
    # Live columns — SHALL appear.
    assert "category" in joined_sql
    assert "badge" in joined_sql
    assert "rating" in joined_sql


@pytest.mark.asyncio
async def test_pulse_survives_db_snapshot_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the catalog snapshot throws, pulse still returns 4 metrics —
    the catalog one just shows 0 products."""

    class BoomDB:
        async def fetch_one(self, sql: str, *params: Any) -> Optional[dict]:
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.db_service", BoomDB(), raising=False)
    resp = await boutique.pulse()

    assert len(resp.metrics) == 4
    catalog = next(m for m in resp.metrics if m.id == "catalog")
    assert "0 products" in catalog.primary
