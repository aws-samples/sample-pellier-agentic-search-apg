"""The shopper's limits carry across follow-up turns on the in-process rail.

Anna asks for "in stock, under $100, no candles"; her follow-up states none of
that and must still get it. A follow-up overrides only what it states, an
explicit release clears a limit, a new conversation starts clean, the set is
keyed by the verified principal and the session together, only the shopper's
own words are remembered, and ``browse_department`` applies the active limits
as ``search_products`` does. No model and no database: the extractor is a
stand-in and the SQL runner records what it was asked.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

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
SHOPPER = active_requirements.SOURCE_SHOPPER
ANNA = ActiveRequirements(
    price_max_usd=100.0, in_stock_only=True, exclusions=("candle",),
    sources={"budget": SHOPPER, "stock": SHOPPER, "exclusions": SHOPPER},
)

# Ordinary follow-ups that resemble a release and must keep every limit.
ORDINARY_FOLLOW_UPS = (
    "Show me anything else for the kitchen",
    "any price range you would suggest?",
    "no limits on color please",
    "show me anything similar",
    "which of those for a small kitchen?",
)

# A release phrase inside a negation keeps the limit it names.
NEGATED_RELEASES = (
    "don't ignore my budget",
    "please do not drop the price limit",
    "I would rather not include sold out items",
)


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

    # "Show me anything" is the extractor's call, reported as ``all``.
    everything = {**NOTHING_STATED, "lifted": ["all"]}
    merged, carried = merge(everything, before=ANNA, message="Show me anything")
    assert merged["price_max_usd"] is None and merged["in_stock_only"] is False
    assert merged["exclusions"] == [] and carried == []

    # The extractor can release one excluded value too.
    lifted = {**NOTHING_STATED, "lifted": ["candle"]}
    merged, carried = merge(lifted, before=ANNA, message="Candles are fine now")
    assert merged["exclusions"] == [] and carried == ["budget", "stock"]
    assert "lifted" not in merged


def test_the_reset_floor_reads_only_explicit_named_releases() -> None:
    resets = active_requirements.explicit_resets
    assert resets("ignore my budget") == {"budget"}
    assert resets("forget the budget, what would you pick?") == {"budget"}
    assert resets("drop the price limit") == {"budget"}
    assert resets("no price limit this time") == {"budget"}
    assert resets("in stock or not, I just want the mugs") == {"stock"}
    assert resets("include sold out ones too") == {"stock"}
    assert resets("it doesn't have to be in stock") == {"stock"}
    assert resets("candles are fine now") == {"candle"}
    for message in ("show me anything", "anything goes", "no limits", "any price"):
        assert resets(message) == set(), message


@pytest.mark.parametrize("message", ORDINARY_FOLLOW_UPS + NEGATED_RELEASES)
def test_an_ordinary_follow_up_keeps_every_limit(message: str) -> None:
    assert active_requirements.explicit_resets(message) == set()
    merged, carried = merge(NOTHING_STATED, before=ANNA, message=message)
    assert merged["price_max_usd"] == 100.0
    assert merged["in_stock_only"] is True
    assert merged["exclusions"] == ["candle"]
    assert carried == ["budget", "stock", "exclusions"]


def test_a_negation_blocks_only_the_release_it_sits_on() -> None:
    resets = active_requirements.explicit_resets
    assert resets("I would not say candles are fine now") == set()
    assert resets("no, don't ignore my budget") == set()
    # The negation belongs to the clause before the comma, not to the release.
    assert resets("I'm not sure, ignore my budget") == {"budget"}
    # The stock floor's own negation is the release, not a guard against it.
    assert resets("it does not have to be in stock") == {"stock"}


def test_a_follow_up_read_from_the_latest_message_alone_carries_the_rest() -> None:
    """The extractor reads only the latest message, so a follow-up that states no
    limit reads as nothing stated and every earlier limit is reported as carried;
    "make it under $50" overrides the budget alone."""
    remember("sess-anna", FIRST)
    history = [{"role": "user", "content": "in stock, under $100, no candles"}]

    token = active_requirements.bind_turn(
        session_id="sess-anna", message="which of those for a small kitchen?", conversation_history=history,
    )
    try:
        merged, carried = active_requirements.turn_requirements(lambda: dict(NOTHING_STATED))
    finally:
        active_requirements.reset_turn(token)
    assert merged["price_max_usd"] == 100.0 and merged["in_stock_only"] is True
    assert merged["exclusions"] == ["candle"]
    assert carried == ["budget", "stock", "exclusions"]

    token = active_requirements.bind_turn(
        session_id="sess-anna", message="make it under $50", conversation_history=history,
    )
    try:
        merged, carried = active_requirements.turn_requirements(
            lambda: {**NOTHING_STATED, "price_max_usd": 50.0, "soft_signal": "gift"}
        )
    finally:
        active_requirements.reset_turn(token)
    assert merged["price_max_usd"] == 50.0 and merged["in_stock_only"] is True
    assert merged["exclusions"] == ["candle"]
    assert carried == ["stock", "exclusions"]


def test_a_restated_value_reads_as_stated_not_carried() -> None:
    restated = {**NOTHING_STATED, "price_max_usd": 100.0}
    merged, carried = merge(restated, before=ANNA, message="still under $100 please")
    assert merged["price_max_usd"] == 100.0
    assert carried == ["stock", "exclusions"]

    no_candles = {**NOTHING_STATED, "exclusions": ["candle"]}
    merged, carried = merge(no_candles, before=ANNA, message="and still no candles")
    assert merged["exclusions"] == ["candle"]
    assert carried == ["budget", "stock"]


def test_a_new_conversation_starts_clean() -> None:
    remember("sess-anna", FIRST)
    assert active_requirements.active("sess-anna") == ANNA
    token = active_requirements.bind_turn(session_id="sess-anna", message="hi", conversation_history=[])
    try:
        assert active_requirements.active("sess-anna").is_empty()
        merged, carried = active_requirements.turn_requirements(lambda: dict(NOTHING_STATED))
        assert carried == []
        assert merged == {key: value for key, value in NOTHING_STATED.items() if key != "lifted"}
    finally:
        active_requirements.reset_turn(token)


def test_the_active_set_is_keyed_by_principal_and_session() -> None:
    remember("sess-anna", FIRST, principal="sub-anna")
    assert active_requirements.active("sess-anna", "sub-anna") == ANNA
    assert active_requirements.active("sess-anna").is_empty()
    assert active_requirements.active("sess-anna", "sub-theo").is_empty()

    # The same session id under another verified principal starts clean, and
    # the earlier principal's limits are gone with it.
    history = [{"role": "user", "content": "in stock, under $100, no candles"}]
    token = active_requirements.bind_turn(
        session_id="sess-anna", principal="sub-theo", message="and for me?", conversation_history=history,
    )
    try:
        merged, carried = active_requirements.turn_requirements(lambda: dict(NOTHING_STATED))
        assert carried == [] and merged["price_max_usd"] is None
        assert active_requirements.active("sess-anna", "sub-anna").is_empty()
    finally:
        active_requirements.reset_turn(token)


def test_the_turns_reading_becomes_the_active_set_with_its_source() -> None:
    reading = {**FIRST, "required_categories": ["Home"]}
    kept = remember("sess-anna", reading)
    assert kept == ActiveRequirements(
        100.0, True, ("candle",), ("Home",),
        sources={"budget": SHOPPER, "stock": SHOPPER, "exclusions": SHOPPER, "department": SHOPPER},
    )
    assert kept.kinds() == ("budget", "stock", "exclusions", "department")
    assert remember("sess-anna", NOTHING_STATED) == ActiveRequirements()


# ---------------------------------------------------------------------------
# Through the tools: one reading per turn, both tools apply it, only the
# shopper's words are remembered
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


def _bind(monkeypatch: pytest.MonkeyPatch, *, reading: Dict[str, Any], history: list, message: str):
    """Bind one turn whose extractor returns ``reading``; returns the runner and the readings made."""
    readings: List[str] = []

    def _read(_query: str) -> Dict[str, Any]:
        readings.append(_query)
        return dict(reading)

    monkeypatch.setattr(agent_tools, "_extract_query_structure", _read)
    monkeypatch.setattr(agent_tools, "_db_service", object())
    run = _Run()
    monkeypatch.setattr(agent_tools, "_run_sql", run)
    token = active_requirements.bind_turn(
        session_id="sess-anna", message=message, conversation_history=history,
    )
    words = shopper_words_var.set(message)
    return run, readings, (token, words)


def _unbind(bound) -> None:
    token, words = bound
    shopper_words_var.reset(words)
    active_requirements.reset_turn(token)


@pytest.fixture
def follow_up_turn(monkeypatch: pytest.MonkeyPatch):
    """Anna's second turn: the first reading is active, the extractor reads nothing new."""
    remember("sess-anna", FIRST)
    run, readings, bound = _bind(
        monkeypatch,
        reading=NOTHING_STATED,
        history=[{"role": "user", "content": "in stock, under $100, no candles"}],
        message="Which of those would you pick for a small kitchen?",
    )
    yield run, readings
    _unbind(bound)


def _spy_search(monkeypatch: pytest.MonkeyPatch, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Stand in for the pipeline: record the kwargs, return a result with ``plan``."""
    from services import store_tools

    seen: Dict[str, Any] = {}

    def spy(_run: Any, **kwargs: Any) -> Dict[str, Any]:
        seen.update(kwargs)
        return {"status": "success", "count": 0, "products": [], "search_plan": plan}

    monkeypatch.setattr(store_tools, "search_products", spy)
    import services.embeddings as embeddings_module
    import services.rerank as rerank_module

    monkeypatch.setattr(
        embeddings_module, "EmbeddingService",
        lambda *a, **k: SimpleNamespace(embed_query=lambda _q: [0.0]),
    )
    monkeypatch.setattr(
        rerank_module, "get_rerank_service", lambda: SimpleNamespace(rerank=lambda **_k: []),
    )
    return seen


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
    # In a turn the one read fetches the page grid's rows too; the model still reads five.
    assert params == ("%kitchen and table%", 100.0, ["candle"], ["candle"], 30)
    assert parsed["count"] == 1
    assert parsed["search_plan"]["hard_constraints"]["in_stock_only"] is True
    assert parsed["search_plan"]["exclusions"] == ["candle"]
    assert evidence["requirements"] == {"carried": ["budget", "stock", "exclusions"]}
    assert evidence["results"]["product_ids"] == ["31"]
    assert [(tag["label"], tag["origin"]) for tag in evidence["results"]["limits"]] == [
        ("Under $100", "carried"), ("In stock", "carried"), ("No candles", "carried"),
    ]
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
    seen = _spy_search(monkeypatch, {
        "hard_constraints": {"price_max_usd": 100.0, "in_stock_only": True, "categories": []},
        "exclusions": ["candle"],
    })

    agent_tools.search_products.__wrapped__(query="small kitchen")
    agent_tools.browse_department.__wrapped__(department="Kitchen and table")

    assert seen["extracted"]["price_max_usd"] == 100.0
    assert seen["extracted"]["in_stock_only"] is True
    assert seen["extracted"]["exclusions"] == ["candle"]
    assert len(readings) == 1, "the shopper's words are read once per turn"
    assert "quantity > 0" in run.calls[-1][0]


def test_a_model_chosen_max_price_is_never_carried_as_the_shoppers_limit(monkeypatch) -> None:
    """The agent's ``max_price`` argument shapes one search; the shopper's words are what carry."""
    # Turn 1: the shopper named no budget; the model passed max_price=50.
    _, _, bound = _bind(monkeypatch, reading=NOTHING_STATED, history=[], message="a housewarming gift")
    try:
        seen = _spy_search(monkeypatch, {
            "hard_constraints": {"price_max_usd": 50.0, "in_stock_only": False, "categories": []},
            "exclusions": [],
        })
        agent_tools.search_products.__wrapped__(query="housewarming gift", max_price=50)
        assert seen["max_price"] == 50
    finally:
        _unbind(bound)
    assert active_requirements.active("sess-anna").is_empty()

    # Turn 1 again: the shopper said "under $100"; the model still passed 50.
    _, _, bound = _bind(monkeypatch, reading=FIRST, history=[], message="a gift under $100, in stock, no candles")
    try:
        _spy_search(monkeypatch, {
            "hard_constraints": {"price_max_usd": 50.0, "in_stock_only": True, "categories": []},
            "exclusions": ["candle"],
        })
        agent_tools.search_products.__wrapped__(query="housewarming gift", max_price=50)
    finally:
        _unbind(bound)
    kept = active_requirements.active("sess-anna")
    assert kept.price_max_usd == 100.0
    assert kept.sources == {"budget": SHOPPER, "stock": SHOPPER, "exclusions": SHOPPER}


def test_browse_keeps_a_shopper_stated_department(monkeypatch) -> None:
    """"Home only" survives a later browse of another department."""
    remember("sess-anna", {**FIRST, "required_categories": ["Home"]})
    run, _, bound = _bind(
        monkeypatch,
        reading=NOTHING_STATED,
        history=[{"role": "user", "content": "Home only, under $100, in stock, no candles"}],
        message="what is good in Kitchen and table?",
    )
    try:
        parsed = json.loads(agent_tools.browse_department.__wrapped__(department="Kitchen and table"))
    finally:
        _unbind(bound)
    # The browsed department is the LIKE predicate; the stated one is not
    # applied on top of it, and it stays in force for the next search.
    assert parsed["search_plan"]["hard_constraints"]["categories"] == []
    assert run.calls[0][1] == ("%kitchen and table%", 100.0, ["candle"], ["candle"], 5)
    assert active_requirements.active("sess-anna").categories == ("Home",)
