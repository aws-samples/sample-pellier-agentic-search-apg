"""What the shopper requires survives the agent's wording and later turns.

Each update is applied by deterministic code, and a change counts only when a
quote from the shopper's own message supports it.
"""
from __future__ import annotations

from services.shopping_requirements import Requirements, apply_update, failed_turn

FIRST = "A gift under $100, in stock, no candles. I'd prefer a watch."


def _first() -> Requirements:
    return apply_update(
        Requirements(session_id="s1"),
        {
            "change": "update",
            "price_max_usd": 100, "in_stock_only": True,
            "add_exclusions": ["candle"], "preferences": ["watch"],
            "quotes": {
                "price_max_usd": "under $100", "in_stock_only": "in stock",
                "add_exclusions": "no candles", "preferences": "I'd prefer a watch",
            },
        },
        FIRST,
        turn_id="t1",
    )


def test_a_stated_request_sets_every_requirement() -> None:
    req = _first()
    assert (req.price_max_usd, req.in_stock_only, req.exclusions) == (100.0, True, ("candle",))
    assert req.preferences == ("watch",)
    assert (req.revision, req.request_id, req.turn_id, req.status) == (1, 1, "t1", "parsed")


def test_show_me_more_keeps_everything() -> None:
    later = apply_update(_first(), {"change": "keep"}, "Show me more", turn_id="t2")
    assert (later.price_max_usd, later.in_stock_only, later.exclusions) == (100.0, True, ("candle",))
    assert (later.revision, later.status) == (2, "parsed")


def test_lifting_an_exclusion_keeps_the_budget() -> None:
    later = apply_update(
        _first(),
        {"change": "update", "remove_exclusions": ["candle"],
         "quotes": {"remove_exclusions": "candles are fine now"}},
        "Actually, candles are fine now.",
        turn_id="t2",
    )
    assert later.exclusions == () and later.price_max_usd == 100.0


def test_changing_the_budget_keeps_the_exclusion() -> None:
    later = apply_update(
        _first(),
        {"change": "update", "price_max_usd": 150, "quotes": {"price_max_usd": "make the budget $150"}},
        "Make the budget $150.",
        turn_id="t2",
    )
    assert later.price_max_usd == 150.0 and later.exclusions == ("candle",)


def test_a_change_without_the_shoppers_words_is_ignored_and_asked_about() -> None:
    later = apply_update(
        _first(),
        {"change": "update", "remove_exclusions": ["candle"], "price_max_usd": 500,
         "quotes": {"remove_exclusions": "candles are fine", "price_max_usd": "spend whatever"}},
        "What else do you have?",
        turn_id="t2",
    )
    assert later.exclusions == ("candle",) and later.price_max_usd == 100.0
    assert later.status == "unclear"
    assert set(later.ignored_changes) == {"remove_exclusions", "price_max_usd"}


def test_a_new_shopping_request_starts_clean_only_when_the_shopper_says_so() -> None:
    fresh = apply_update(
        _first(),
        {"change": "new_request", "add_exclusions": ["leather"],
         "quotes": {"new_request": "something for my brother", "add_exclusions": "no leather"}},
        "Now something for my brother, no leather.",
        turn_id="t2",
    )
    assert (fresh.request_id, fresh.price_max_usd, fresh.in_stock_only) == (2, None, False)
    assert fresh.exclusions == ("leather",)

    unsupported = apply_update(
        _first(), {"change": "new_request", "quotes": {}}, "Show me more", turn_id="t3",
    )
    assert unsupported.request_id == 1 and unsupported.exclusions == ("candle",)
    assert unsupported.status == "unclear"


def test_an_exclusion_outside_the_vocabulary_is_kept_unenforced() -> None:
    later = apply_update(
        _first(),
        {"change": "update", "add_exclusions": ["plastic"], "quotes": {"add_exclusions": "no plastic"}},
        "Oh, and no plastic.",
        turn_id="t2",
    )
    assert later.exclusions == ("candle",)
    assert later.unenforced_exclusions == ("plastic",)


def test_a_failed_read_keeps_the_previous_requirements() -> None:
    later = failed_turn(_first(), turn_id="t2")
    assert (later.price_max_usd, later.exclusions) == (100.0, ("candle",))
    assert (later.revision, later.status, later.turn_id) == (2, "extraction_failed", "t2")


def test_the_snapshot_feeds_the_planner_with_the_agents_search_words() -> None:
    from services.search_plan import build_plan

    payload = _first().as_extraction(search_words="housewarming gifts")
    plan = build_plan("housewarming gifts", payload)
    clauses, params = plan.compile_predicates()
    assert "NOT (tags ?| %s OR materials ?| %s)" in clauses and ["candle"] in params
    assert "price <= %s" in clauses and "quantity > 0" in clauses
    assert plan.soft.soft_signal == "housewarming gifts"
    assert plan.extraction_status == "parsed"


def test_an_unclear_turn_tells_the_answer_to_ask() -> None:
    from services.search_plan import build_plan

    unclear = apply_update(
        _first(), {"change": "update", "remove_exclusions": ["candle"], "quotes": {}},
        "hmm", turn_id="t2",
    )
    plan = build_plan("gifts", unclear.as_extraction(search_words="gifts"))
    assert "ask" in plan.constraint_notice().lower()
    assert ["candle"] in plan.compile_predicates()[1]


def test_a_malformed_proposal_is_a_failed_read_not_an_empty_one() -> None:
    import pytest

    from services.structured_extract import _sanitize_update

    for bad in ({"change": "maybe"}, {"change": "update", "add_exclusions": "candle"},
                {"change": "update", "in_stock_only": "yes"}, {"change": "keep", "quotes": []}):
        with pytest.raises(ValueError):
            _sanitize_update(bad)
    assert _sanitize_update({"change": "keep"})["extraction_status"] == "parsed"


def test_an_unreachable_model_reports_a_failed_read() -> None:
    from services.structured_extract import StructuredExtractor

    class _Client:
        def invoke_model(self, **_kwargs):
            raise RuntimeError("model unavailable")

    extractor = StructuredExtractor.__new__(StructuredExtractor)
    extractor.client, extractor.model_id = _Client(), "test-model"
    assert extractor.extract_update("no candles", {}) == {"extraction_status": "extraction_failed"}
