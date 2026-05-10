"""Tests for `services.agent_tools.whats_trending` (Module 2 — Challenge 2).

Covers Requirement 2.4.1 and 2.4.2 from
`.kiro/specs/pellier-storefront/requirements.md` and the coding-standards
tool pattern (`_db_service` availability check, `_run_async` bridging,
`json.dumps` return, `{"error": str(e)}` envelope on exception).

No live database or Bedrock call — the BusinessLogic dependency is stubbed so
these tests run offline. Runnable from the repo root per `pytest.ini`:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_agent_tools.py -v
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import pytest

import services.agent_tools as agent_tools
import services.business_logic as business_logic_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _SentinelDB:
    """Opaque placeholder — the stubbed BusinessLogic ignores it."""


@pytest.fixture
def trending_payload() -> Dict[str, Any]:
    """A payload with 3+ products so we can assert the happy-path shape."""
    return {
        "status": "success",
        "count": 3,
        "products": [
            {
                "productId": 1,
                "product_description": "Italian Linen Camp Shirt — Sand",
                "price": 128.0,
                "stars": 4.8,
                "reviews": 420,
                "category_name": "Linen",
                "quantity": 12,
                "trending_score": 2016.0,
            },
            {
                "productId": 2,
                "product_description": "Sundress in Washed Linen — Golden Ochre",
                "price": 148.0,
                "stars": 4.9,
                "reviews": 310,
                "category_name": "Dresses",
                "quantity": 8,
                "trending_score": 1519.0,
            },
            {
                "productId": 3,
                "product_description": "Signature Straw Tote — Natural",
                "price": 68.0,
                "stars": 4.7,
                "reviews": 280,
                "category_name": "Accessories",
                "quantity": 15,
                "trending_score": 1316.0,
            },
        ],
        "metadata": {
            "criteria": "reviews * stars, min 4.0 stars, min 50 reviews",
            "limit": 5,
            "category_filter": None,
        },
    }


@pytest.fixture(autouse=True)
def reset_module_globals():
    """Snapshot and restore `_db_service` / `_main_loop` so tests don't leak."""
    saved_db = agent_tools._db_service
    saved_loop = agent_tools._main_loop
    yield
    agent_tools._db_service = saved_db
    agent_tools._main_loop = saved_loop


class _StubBusinessLogic:
    """Drop-in replacement that returns a canned payload or raises."""

    def __init__(self, db_service: Any, *, payload: Optional[Dict[str, Any]] = None,
                 raise_exc: Optional[Exception] = None) -> None:
        self._db = db_service
        self._payload = payload
        self._raise_exc = raise_exc

    async def whats_trending(
        self, limit: int = 5, category: Optional[str] = None
    ) -> Dict[str, Any]:
        if self._raise_exc is not None:
            raise self._raise_exc
        # Echo the limit/category the tool forwarded so tests can assert wiring.
        payload = dict(self._payload or {})
        metadata = dict(payload.get("metadata", {}))
        metadata["limit"] = limit
        metadata["category_filter"] = category
        payload["metadata"] = metadata
        return payload


def _install_stub_business_logic(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: Optional[Dict[str, Any]] = None,
    raise_exc: Optional[Exception] = None,
) -> None:
    def factory(db_service: Any) -> _StubBusinessLogic:
        return _StubBusinessLogic(db_service, payload=payload, raise_exc=raise_exc)

    monkeypatch.setattr(business_logic_module, "BusinessLogic", factory)


def _invoke_tool(**kwargs: Any) -> str:
    """Call the underlying @tool-wrapped function directly.

    Strands' `@tool` produces a `DecoratedFunctionTool` whose original callable
    is exposed via the standard `__wrapped__` attribute (functools convention).
    Fall back to calling the decorated object itself when the attribute is
    missing so the test survives SDK upgrades that inline the decorator.
    """
    fn = getattr(agent_tools.whats_trending, "__wrapped__",
                 agent_tools.whats_trending)
    return fn(**kwargs)


# ---------------------------------------------------------------------------
# Happy path — Req 2.4.1 / 2.4.2
# ---------------------------------------------------------------------------


def test_happy_path_returns_at_least_three_products_as_valid_json(
    monkeypatch: pytest.MonkeyPatch, trending_payload: Dict[str, Any]
) -> None:
    """Tool SHALL return a JSON string with >=3 products on the happy path."""
    agent_tools._db_service = _SentinelDB()
    agent_tools._main_loop = None  # force the asyncio.new_event_loop fallback
    _install_stub_business_logic(monkeypatch, payload=trending_payload)

    out = _invoke_tool(limit=5, category=None)

    # Must be a parseable JSON string.
    assert isinstance(out, str)
    parsed = json.loads(out)
    assert parsed["status"] == "success"
    assert isinstance(parsed["products"], list)
    assert len(parsed["products"]) >= 3


def test_happy_path_forwards_limit_and_category_to_business_logic(
    monkeypatch: pytest.MonkeyPatch, trending_payload: Dict[str, Any]
) -> None:
    """limit and category SHALL flow through to BusinessLogic unchanged."""
    agent_tools._db_service = _SentinelDB()
    agent_tools._main_loop = None
    _install_stub_business_logic(monkeypatch, payload=trending_payload)

    out = _invoke_tool(limit=7, category="Dresses")

    parsed = json.loads(out)
    # The stub echoes the forwarded args into metadata so we can assert wiring.
    assert parsed["metadata"]["limit"] == 7
    assert parsed["metadata"]["category_filter"] == "Dresses"


# ---------------------------------------------------------------------------
# _db_service unavailable — Req 2.4.2 (availability check)
# ---------------------------------------------------------------------------


def test_missing_db_service_returns_error_envelope() -> None:
    """When `_db_service is None` the tool SHALL return an error envelope."""
    agent_tools._db_service = None

    out = _invoke_tool(limit=5)

    parsed = json.loads(out)
    assert "error" in parsed
    assert "not initialized" in parsed["error"].lower()


# ---------------------------------------------------------------------------
# Exception path — Req 2.4.2 (error envelope)
# ---------------------------------------------------------------------------


def test_raised_exception_returns_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raised exception SHALL be caught and returned as {"error": str(e)}."""
    agent_tools._db_service = _SentinelDB()

    # Force _run_async to raise — the tool's try/except is what we're testing,
    # not the asyncio bridging layer. A real failure surfaces here identically
    # whether it came from the BusinessLogic coroutine or the bridge itself.
    def _boom(_coro: Any) -> Any:
        # Close the coroutine explicitly so the test doesn't emit a
        # "coroutine was never awaited" RuntimeWarning.
        _coro.close()
        raise RuntimeError("db connection refused")

    monkeypatch.setattr(agent_tools, "_run_async", _boom)
    # BusinessLogic must still be importable — the tool imports it before
    # calling `_run_async`, so a sentinel stub is sufficient.
    _install_stub_business_logic(monkeypatch)

    out = _invoke_tool(limit=5)

    parsed = json.loads(out)
    assert set(parsed.keys()) == {"error"}
    assert parsed["error"] == "db connection refused"
