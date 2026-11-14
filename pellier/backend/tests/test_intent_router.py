"""The Router's intent for every seeded prompt, and the catalog requests it must not steal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.intent_router import (
    CATALOG, STOCK, SUPPORT, classify_intent, route_query, routing_reason)

SCENARIOS = json.loads(
    (Path(__file__).resolve().parents[3] / "data" / "scenarios.json").read_text())
_ITEMS = SCENARIOS if isinstance(SCENARIOS, list) else SCENARIOS["scenarios"]
PROMPTS = {item["id"]: item["prompt"] for item in _ITEMS}

EXPECTED = {
    1: CATALOG, 2: CATALOG, 3: CATALOG, 4: CATALOG, 5: CATALOG,
    6: CATALOG, 7: CATALOG, 8: STOCK, 9: CATALOG, 10: CATALOG, 25: STOCK,
    11: CATALOG, 12: CATALOG, 14: CATALOG, 15: CATALOG,
    16: CATALOG, 17: CATALOG, 18: SUPPORT, 19: SUPPORT, 20: SUPPORT,
    21: SUPPORT, 22: SUPPORT, 23: SUPPORT, 24: CATALOG, 26: CATALOG,
}


def test_every_seeded_prompt_is_pinned() -> None:
    assert set(PROMPTS) == set(EXPECTED)


@pytest.mark.parametrize("scenario", sorted(EXPECTED))
def test_each_seeded_prompt_reaches_its_agent(scenario: int) -> None:
    assert classify_intent(PROMPTS[scenario]) == EXPECTED[scenario], PROMPTS[scenario]


@pytest.mark.parametrize("query", [
    "Tear-resistant linen for travel",
    "A soft throw for slow evenings at home",
    "An in-stock housewarming gift under $80",
])
def test_catalog_requests_stay_with_the_catalog_agent(query: str) -> None:
    assert classify_intent(query) == CATALOG


REASONS = [
    ("How many Linen Throws are left in the Brooklyn warehouse?", STOCK,
     "how many, Brooklyn, warehouse"),
    ("Is the cashmere cardigan sold out?", STOCK, "sold out"),
    ("Is this available at all?", STOCK, "available"),
    ("Is the Velvet Opera Cape in stock?", STOCK, "in stock"),
    ("The mug arrived chipped, can you open a ticket?", SUPPORT, "arrived, chipped, ticket"),
    ("What did I buy last time?", SUPPORT, "what did I buy, last time"),
    ("I want a refund", SUPPORT, "refund"),
    ("An in-stock housewarming gift under $60", CATALOG, "housewarming, gift"),
    ("Compare the two throws", CATALOG, "compare"),
    ("What would go with the Hadley Linen Shirt?", CATALOG, "what would go with"),
    ("Find me a linen shirt", CATALOG, "find me, shirt"),
    ("Tell me about Pellier", CATALOG, "default"),
]


@pytest.mark.parametrize(("query", "intent", "reason"), REASONS)
def test_routing_reason_names_the_words_that_matched(query: str, intent: str, reason: str) -> None:
    assert route_query(query).intent == intent == classify_intent(query)
    assert routing_reason(query, intent) == reason


def test_routing_reason_follows_the_rule_order() -> None:
    route = route_query("The mug arrived damaged, how many are in the warehouse?")
    assert (route.intent, route.rule) == (SUPPORT, "support")
    assert "warehouse" not in route.words


def test_routing_reason_shows_at_most_three_words() -> None:
    reason = routing_reason("the ticket for my refund of the broken, damaged item", SUPPORT)
    assert reason == "ticket, refund, broken"


def test_routing_reason_does_not_repeat_a_word_inside_a_phrase_it_shows() -> None:
    jessica = "I sent the robe and the diffuser back. Can I have a store credit?"
    assert routing_reason(jessica, SUPPORT) == "store credit"
    assert routing_reason("Can I get store credit for the returned robe?", SUPPORT) == (
        "store credit, returned")


def test_routing_reason_shows_words_as_the_shopper_wrote_them_mid_sentence() -> None:
    assert routing_reason("Tell me: how many are in Brooklyn?", STOCK) == "how many, Brooklyn"
    assert routing_reason("HOW MANY are in Brooklyn?", STOCK) == "how many, Brooklyn"
    assert routing_reason("Thanks. What did I buy last time?", SUPPORT) == "what did I buy, last time"


def test_the_router_line_is_the_agent_and_the_words_that_chose_it() -> None:
    from services.chat import route_finding

    assert route_finding("Stock agent", "how many, Brooklyn, warehouse") == (
        "Sent to the Stock agent: how many, Brooklyn, warehouse")
    assert route_finding("Catalog agent", "default") == "Sent to the Catalog agent (default)"
    assert route_finding("Catalog agent", None) == "Sent to the Catalog agent"


def test_routing_reason_is_none_when_the_rules_choose_another_intent() -> None:
    assert routing_reason("How many are left?", CATALOG) is None
