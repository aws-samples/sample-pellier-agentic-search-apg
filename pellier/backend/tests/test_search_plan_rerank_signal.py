"""What the reranker scores: the shopper's taste when they stated one, else the search's words.

On the 2026-11-09 release event Theo asked "Pick one piece you think I'd love." The search
itself used the Catalog agent's words, which carry his remembered taste (stoneware, linen),
but Cohere Rerank scored the pool against his sentence, which names nothing to look for, and
returned five cotton blankets. ``build_plan`` now gives the reranker the agent's words when the
shopper's phrase is only request words, and changes nothing for a phrase that names a product,
material, style or occasion.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from services.catalog_vocabulary import KNOWN_CATEGORIES, KNOWN_MATERIALS, KNOWN_TAGS
from services.search_plan import REQUEST_WORDS, build_plan, names_what_to_find

pytestmark = pytest.mark.usefixtures("completed_search_plan")

SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios.json"
CATALOG = Path(__file__).resolve().parents[3] / "data" / "pellier_catalog.json"
AGENT_WORDS = "hand-thrown stoneware and raw linen"


@pytest.mark.parametrize("phrase", [
    "Pick one piece you think I'd love.", "pick one piece you think i\u2019d love",
    "I\u02bcd love one", "one piece you think I'd love", "Surprise me!",
    "What would you recommend for me?", "something I'd like", "something for her",
    "what's popular", "your favorite", "what should I buy",
    "Choose something for me based on my taste", "  ",
])
def test_a_phrase_of_request_words_ranks_by_the_searchs_own_words(phrase: str) -> None:
    assert not names_what_to_find(phrase)
    plan = build_plan(AGENT_WORDS, {"soft_signal": phrase, "extraction_status": "parsed"})
    assert plan.soft.soft_signal == AGENT_WORDS


@pytest.mark.parametrize("phrase", [
    "housewarming gift for a friend who loves slow mornings", "a cozy layer for cooler nights",
    "something in linen", "a piece for my kitchen", "pick a candle", "Something to wear",
    "something one-of-a-kind", "a one-piece wallet", "hand-thrown", "gift ideas",
])
def test_a_phrase_that_names_something_still_ranks_by_the_shoppers_words(phrase: str) -> None:
    assert names_what_to_find(phrase)
    plan = build_plan(AGENT_WORDS, {"soft_signal": phrase, "extraction_status": "parsed"})
    assert plan.soft.soft_signal == phrase


def test_every_scripted_request_but_theos_pick_names_what_to_find() -> None:
    """The scripted journeys rank exactly as before, except the one that leans on Memory."""
    prompts = {row["id"]: row["prompt"] for row in json.loads(SCENARIOS.read_text())
               if isinstance(row, dict) and "prompt" in row}
    assert len(prompts) > 20
    vague = {prompt for prompt in prompts.values() if not names_what_to_find(prompt)}
    assert vague == {"Pick one piece you think I'd love."}


def test_a_missing_phrase_names_nothing() -> None:
    assert not names_what_to_find(None)  # type: ignore[arg-type]


def test_no_request_word_is_a_catalog_term() -> None:
    """A word the catalog filters or ranks on is never treated as filler."""
    catalog = {word for term in [*KNOWN_CATEGORIES, *KNOWN_TAGS, *KNOWN_MATERIALS]
               for word in re.findall(r"[a-z]+", term.lower())}
    catalog.discard("and")  # it only joins two category words, as in "Kitchen and table"
    assert not REQUEST_WORDS & catalog, sorted(REQUEST_WORDS & catalog)


# Request words that also occur in product names but name nothing alone: connectives, and the
# generic words in names such as "Three Piece Set", "Apron-Style" or "Guitar Pick". A shopper
# who writes one of these beside a real word ("a guitar pick") keeps their phrase.
IN_NAMES_BUT_GENERIC = frozenset("""
    a all and any as at by can for from in of on or the to with you
    look one option options perfect pick piece pieces style type
""".split())


def test_no_request_word_names_a_product() -> None:
    """A word a product's name rests on ("throw", "mug") is never treated as filler."""
    products = [json.loads(line.strip().rstrip(","))
                for line in CATALOG.read_text().splitlines() if line.lstrip().startswith("{")]
    names = {word for product in products
             for word in re.findall(r"[a-z]+(?:[-'][a-z]+)*", product["name"].lower())}
    assert len(names) > 1000
    product_words = (REQUEST_WORDS & names) - IN_NAMES_BUT_GENERIC
    assert not product_words, sorted(product_words)
