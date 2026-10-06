"""The Router's intent for every seeded prompt, and the shopping requests it must not steal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.intent_router import SHOPPING, STOCK, SUPPORT, classify_intent

SCENARIOS = json.loads(
    (Path(__file__).resolve().parents[3] / "data" / "scenarios.json").read_text())
_ITEMS = SCENARIOS if isinstance(SCENARIOS, list) else SCENARIOS["scenarios"]
PROMPTS = {item["id"]: item["prompt"] for item in _ITEMS}

EXPECTED = {
    1: SHOPPING, 2: SHOPPING, 3: SHOPPING, 4: SHOPPING, 5: SHOPPING,
    6: SHOPPING, 7: SHOPPING, 8: STOCK, 9: SHOPPING, 10: SHOPPING, 25: STOCK,
    11: SHOPPING, 12: SHOPPING, 14: SHOPPING, 15: SHOPPING,
    16: SHOPPING, 17: SHOPPING, 18: SUPPORT, 19: SUPPORT, 20: SUPPORT,
    21: SUPPORT, 22: SUPPORT, 23: SUPPORT, 24: SHOPPING,
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
def test_shopping_requests_stay_with_the_shopping_agent(query: str) -> None:
    assert classify_intent(query) == SHOPPING
