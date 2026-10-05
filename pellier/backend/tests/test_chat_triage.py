"""Tests for ``services.chat.classify_triage`` — deterministic small-talk short-circuit.

The triage classifier runs before any orchestrator dispatch so
greetings/meta/thanks queries never depend on an LLM roll. These
tests pin the bucket mapping so a workshop demo that opens with "hi"
is guaranteed to produce a reply.
"""

from __future__ import annotations

import pytest

from services.chat import classify_intent, classify_triage, _TRIAGE_REPLIES


class TestTriageGreetings:
    @pytest.mark.parametrize(
        "query",
        [
            "hi",
            "Hi",
            "HI!",
            "hello",
            "Hello.",
            "hey",
            "hey there",
            "howdy",
            "yo",
            "good morning",
            "Good Afternoon",
            "good evening",
            "hi there",
            "hello, can you help me out",  # short-enough greeting prefix
        ],
    )
    def test_recognises_common_greetings(self, query: str) -> None:
        assert classify_triage(query) == "greeting"


class TestTriageMeta:
    @pytest.mark.parametrize(
        "query",
        [
            "what can you do",
            "What can you do?",
            "who are you",
            "what are you",
            "how do you work",
            "what are your capabilities",
            "help",
            "how can you help",
            "what can I ask",
        ],
    )
    def test_recognises_meta_queries(self, query: str) -> None:
        assert classify_triage(query) == "meta"


class TestTriageThanks:
    @pytest.mark.parametrize(
        "query",
        ["thanks", "thank you", "thanks!", "thx", "ty", "appreciate it"],
    )
    def test_recognises_thanks(self, query: str) -> None:
        assert classify_triage(query) == "thanks"


class TestTriageFallsThrough:
    @pytest.mark.parametrize(
        "query",
        [
            "find me a linen shirt under $150",
            "what's low on stock right now",
            "compare two mens shirts",
            "return policy?",
            "best linen shirt for travel",
            "",  # empty query
            "    ",  # whitespace
        ],
    )
    def test_real_queries_are_not_triaged(self, query: str) -> None:
        assert classify_triage(query) is None

    def test_long_query_starting_with_hi_is_not_triaged(self) -> None:
        """Long queries that happen to start with 'hi' are real
        questions, not greetings. The 60-char ceiling is what
        separates 'hi!' from 'hi, can you find me a linen shirt
        under $150 in a travel-friendly fabric?'"""
        long_q = (
            "hi, can you find me a linen shirt under $150 in a "
            "travel-friendly fabric please"
        )
        assert len(long_q) > 60
        assert classify_triage(long_q) is None


class TestTriageRepliesShape:
    def test_every_bucket_has_a_reply(self) -> None:
        for bucket in ("greeting", "meta", "thanks"):
            assert bucket in _TRIAGE_REPLIES
            assert _TRIAGE_REPLIES[bucket]
            # On-brand: should not start with generic "I can help"
            assert len(_TRIAGE_REPLIES[bucket]) > 20


class TestIntentPairing:
    @pytest.mark.parametrize(
        "query",
        [
            "What would go with the Hadley Linen Shirt?",
            "What pairs with the Ecru overshirt?",
            "What goes well with the pour-over set, keeping to the same materials and "
            "morning routine?",
        ],
    )
    def test_pairing_turns_route_to_shopping(self, query: str) -> None:
        assert classify_intent(query) == "shopping"


class TestIntentStock:
    @pytest.mark.parametrize(
        "query",
        [
            "Is the Hadley shirt in Brooklyn?",
            "How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what "
            "ship window is recorded?",
            "Do you have the linen overshirt in Austin?",
            "Can the camp shirt ship from Portland?",
        ],
    )
    def test_city_stock_questions_route_to_stock(self, query: str) -> None:
        assert classify_intent(query) == "stock"


@pytest.mark.parametrize("query, expected", [
    ("A housewarming gift under $100 that is currently in stock.", "shopping"),
    ("Keep it under $100 and in stock. Show me the strongest two options.", "shopping"),
    ("Which one should I choose? Compare the two options using their current prices and "
     "availability.", "shopping"),
    ("Find me a linen shirt that is in stock", "shopping"),
    ("Do you have any available candles for a gift?", "shopping"),
    ("Is the Hadley Linen Shirt in stock?", "stock"),
    ("Show me how many candles are available in Brooklyn", "stock"),
    ("Show me low stock inventory", "stock"),
])
def test_availability_constraints_do_not_override_product_selection(query, expected):
    assert classify_intent(query) == expected


@pytest.mark.parametrize("query", [
    "Show my support ticket history.",
    "Please list my support tickets.",
    "What happened to my ticket?",
])
def test_ticket_history_routes_to_the_support_agent(query):
    assert classify_intent(query) == "support"


@pytest.mark.parametrize("query", [
    "What did I buy last time?",
    "Show my orders",
    "I want a refund for the chipped mug",
    "Can I get store credit?",
])
def test_returns_and_past_purchases_route_to_support(query):
    assert classify_intent(query) == "support"


@pytest.mark.parametrize("query", [
    "Which is cheaper, the linen shirt or the camp shirt?",
    "Browse the home department",
    "A gift for my sister",
])
def test_price_compare_and_browse_stay_with_shopping(query):
    assert classify_intent(query) == "shopping"


# The guide's Lab 1 and Lab 2 requests, verbatim. The guide lives in another
# repository, so these are pinned here: a wording change on either side that
# sends a request to the wrong agent fails the lab silently (Anna's limits on
# the Stock agent, or Marco's cape on the Shopping agent).
GUIDE_SENTENCES = (
    ("A housewarming gift for a friend who loves slow mornings. In stock, under $100, "
     "and no candles.", "shopping"),
    ("A gift with a watch, under $100, in stock, no candles.", "shopping"),
    ("Is the Velvet Opera Cape in stock?", "stock"),
    ("How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship "
     "window is recorded?", "stock"),
    ("What linen do you have for 10 days in Goa?", "shopping"),
)


@pytest.mark.parametrize("sentence, agent", GUIDE_SENTENCES)
def test_the_guides_lab_1_and_2_requests_reach_their_agent(sentence: str, agent: str) -> None:
    assert classify_intent(sentence) == agent


def test_the_guides_requests_are_the_one_click_lab_prompts() -> None:
    import json
    from pathlib import Path

    scenarios = json.loads(
        (Path(__file__).resolve().parents[3] / "data" / "scenarios.json").read_text())
    offered = {row["prompt"] for row in scenarios if row["persona"] in ("anna", "marco")}
    required = {row["prompt"] for row in scenarios
                if row["persona"] in ("anna", "marco") and row["journey_role"] == "required"}
    assert {sentence for sentence, _agent in GUIDE_SENTENCES} <= offered
    assert required <= {sentence for sentence, _agent in GUIDE_SENTENCES}
