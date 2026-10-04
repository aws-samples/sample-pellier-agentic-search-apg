"""The shopper's limits carry across follow-up turns on the in-process rail.

Anna asks for "in stock, under $100, no candles"; her follow-up states none of
that and must still get it. A follow-up overrides only what it states, an
explicit reset clears a limit, a new conversation starts clean, and
``browse_department`` applies the active limits as ``search_products`` does.
No model and no database: the extractor is a stand-in and the SQL runner
records what it was asked.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

import services.agent_tools as agent_tools
from services import active_requirements, tool_evidence
from services.active_requirements import ActiveRequirements, merge, remember
from services.turn_identity import shopper_words_var

FIRST = {
    "price_max_usd": 100.0, "in_stock_only": True, "exclusions": ["candle"],
    "required_categories": [], "tags": [], "soft_signal": "housewarming gift",
    "extraction_status": "parsed", "lifted": [],
}
NOTHING_STATED = {
    "price_max_usd": None, "in_stock_only": False, "exclusions": [],
    "required_categories": [], "tags": [], "soft_signal": "small kitchen",
    "extraction_status": "parsed", "lifted": [],
}
ANNA = ActiveRequirements(price_max_usd=100.0, in_stock_only=True, exclusions=("candle",))


@pytest.fixture(autouse=True)
def _clean_sessions():
    active_requirements.forget_session("sess-anna")
    yield
    active_requirements.forget_session("sess-anna")


# ---------------------------------------------------------------------------
# The merge rule
# ---------------------------------------------------------------------------


def test_a_follow_up_keeps_the_limits() -> None:
    merged, carried = merge(NOTHING_STATED, before=ANNA, message="Which of those for a small kitchen?")
    assert merged["price_max_usd"] == 100.0
    assert merged["in_stock_only"] is True
    assert merged["exclusions"] == ["candle"]
    assert carried == ["budget", "stock", "exclusions"]


def test_an_override_changes_only_the_stated_limit() -> None:
    stated = {**NOTHING_STATED, "price_max_usd": 80.0}
    merged, carried = merge(stated, before=ANNA, message="Something under $80 instead")
    assert merged["price_max_usd"] == 80.0
    assert merged["in_stock_only"] is True and merged["exclusions"] == ["candle"]
    assert carried == ["stock", "exclusions"]

    added = {**NOTHING_STATED, "exclusions": ["wool"]}
    merged, carried = merge(added, before=ANNA, message="And nothing in wool")
    assert merged["exclusions"] == ["wool", "candle"]
    assert carried == ["budget", "stock", "exclusions"]


def test_an_explicit_reset_clears_the_stated_limit() -> None:
    merged, carried = merge(NOTHING_STATED, before=ANNA, message="Ignore my budget, what else?")
    assert merged["price_max_usd"] is None
    assert merged["in_stock_only"] is True and merged["exclusions"] == ["candle"]
    assert carried == ["stock", "exclusions"]

    merged, carried = merge(NOTHING_STATED, before=ANNA, message="Show me anything")
    assert merged["price_max_usd"] is None and merged["in_stock_only"] is False
    assert merged["exclusions"] == [] and carried == []

    # The extractor can report a release too, including one excluded value.
    lifted = {**NOTHING_STATED, "lifted": ["candle"]}
    merged, carried = merge(lifted, before=ANNA, message="Candles are fine now")
    assert merged["exclusions"] == [] and carried == ["budget", "stock"]
    assert "lifted" not in merged


def test_the_reset_floor_reads_the_shoppers_own_words() -> None:
    assert active_requirements.explicit_resets("ignore my budget") == {"budget"}
    assert active_requirements.explicit_resets("show me anything") == {"all"}
    assert active_requirements.explicit_resets("in stock or not, I just want the mugs") == {"stock"}
    assert active_requirements.explicit_resets("candles are fine now") == {"candle"}
    assert active_requirements.explicit_resets("which of those for a small kitchen?") == set()


def test_a_new_conversation_starts_clean() -> None:
    remember("sess-anna", {"hard_constraints": {"price_max_usd": 100, "in_stock_only": True,
                                                "categories": []}, "exclusions": ["candle"]})
    assert active_requirements.active("sess-anna") == ANNA
    token = active_requirements.bind_turn(session_id="sess-anna", message="hi", conversation_history=[])
    try:
        assert active_requirements.active("sess-anna").is_empty()
        merged, carried = active_requirements.turn_requirements(lambda: dict(NOTHING_STATED))
        assert carried == []
        assert merged == {key: value for key, value in NOTHING_STATED.items() if key != "lifted"}
    finally:
        active_requirements.reset_turn(token)


def test_the_plan_that_ran_becomes_the_active_set() -> None:
    plan = {
        "hard_constraints": {"price_max_usd": 100.0, "in_stock_only": True, "categories": ["Home"]},
        "exclusions": ["candle"], "category_source": "shopper",
    }
    assert remember("sess-anna", plan) == ActiveRequirements(100.0, True, ("candle",), ("Home",))
    # A department an agent guessed never becomes a requirement.
    guessed = {**plan, "category_source": None}
    assert remember("sess-anna", guessed).categories == ()


# ---------------------------------------------------------------------------
# Through the tools: one reading per turn, both tools apply it
# ---------------------------------------------------------------------------


class _Run:
    """Records every statement and returns one row the browse query shapes."""

    def __init__(self) -> None:
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "FROM pellier.product_catalog" in sql and "LIKE" in sql:
            return [{"productId": "31", "name": "Stoneware Pour-Over Set", "brand": "Pellier",
                     "color": "Ash gray", "price": 58, "rating": 4.9, "reviews": 134,
                     "category": "Kitchen and table", "imgUrl": "/p.webp", "badge": None,
                     "tags": '["ceramic","slow","home"]'}]
        return []


@pytest.fixture
def follow_up_turn(monkeypatch: pytest.MonkeyPatch):
    """Anna's second turn: the first plan is active, the extractor reads nothing new."""
    remember("sess-anna", {"hard_constraints": {"price_max_usd": 100, "in_stock_only": True,
                                                "categories": []}, "exclusions": ["candle"]})
    readings: List[str] = []

    def _read(_query: str) -> Dict[str, Any]:
        readings.append(_query)
        return dict(NOTHING_STATED)

    monkeypatch.setattr(agent_tools, "_extract_query_structure", _read)
    monkeypatch.setattr(agent_tools, "_db_service", object())
    run = _Run()
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    token = active_requirements.bind_turn(
        session_id="sess-anna",
        message="Which of those would you pick for a small kitchen?",
        conversation_history=[{"role": "user", "content": "in stock, under $100, no candles"}],
    )
    words = shopper_words_var.set("Earlier: in stock, under $100, no candles\nNow: small kitchen")
    yield run, readings
    shopper_words_var.reset(words)
    active_requirements.reset_turn(token)


def test_browse_department_applies_the_active_limits(follow_up_turn) -> None:
    run, readings = follow_up_turn
    channel = tool_evidence.open_channel()
    try:
        parsed = json.loads(agent_tools.browse_department.__wrapped__(department="Kitchen and table"))
        evidence = tool_evidence.take("browse_department")
    finally:
        tool_evidence.close_channel(channel)

    sql, params = run.calls[0]
    assert "price <= %s" in sql and "quantity > 0" in sql and "NOT (tags ?| %s OR materials ?| %s)" in sql
    assert params == ("%kitchen and table%", 100.0, ["candle"], ["candle"], 5)
    assert parsed["count"] == 1
    assert parsed["search_plan"]["hard_constraints"]["in_stock_only"] is True
    assert parsed["search_plan"]["exclusions"] == ["candle"]
    assert evidence == {"requirements": {"carried": ["budget", "stock", "exclusions"]}}
    assert len(readings) == 1


def test_outside_a_turn_browse_reads_no_requirements(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_tools, "_db_service", object())
    run = _Run()
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    monkeypatch.setattr(agent_tools, "_extract_query_structure", lambda _q: pytest.fail("read outside a turn"))
    parsed = json.loads(agent_tools.browse_department.__wrapped__(department="Home", limit=3))
    sql, params = run.calls[0]
    assert "price <=" not in sql and "quantity > 0" not in sql
    assert params == ("%home%", 3)
    assert parsed["hard_constraints_enforced"] == []


def test_search_and_browse_share_one_reading_in_a_turn(follow_up_turn, monkeypatch) -> None:
    run, readings = follow_up_turn
    from services import store_tools

    seen: Dict[str, Any] = {}

    def spy(_run: Any, **kwargs: Any) -> Dict[str, Any]:
        seen["extracted"] = kwargs["extracted"]
        return {"status": "success", "count": 0, "products": [], "search_plan": {
            "hard_constraints": {"price_max_usd": 100.0, "in_stock_only": True, "categories": []},
            "exclusions": ["candle"],
        }}

    monkeypatch.setattr(store_tools, "search_products", spy)
    from types import SimpleNamespace

    import services.embeddings as embeddings_module
    import services.rerank as rerank_module

    monkeypatch.setattr(
        embeddings_module, "EmbeddingService",
        lambda *a, **k: SimpleNamespace(embed_query=lambda _q: [0.0]),
    )
    monkeypatch.setattr(
        rerank_module, "get_rerank_service", lambda: SimpleNamespace(rerank=lambda **_k: []),
    )

    agent_tools.search_products.__wrapped__(query="small kitchen")
    agent_tools.browse_department.__wrapped__(department="Kitchen and table")

    assert seen["extracted"]["price_max_usd"] == 100.0
    assert seen["extracted"]["in_stock_only"] is True
    assert seen["extracted"]["exclusions"] == ["candle"]
    assert len(readings) == 1, "the shopper's words are read once per turn"
    assert "quantity > 0" in run.calls[-1][0]
