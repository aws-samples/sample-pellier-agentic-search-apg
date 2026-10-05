"""Both rails answer under one set of output rules.

Each agent's output rules live once, in ``pellier_copy.OUTPUT_RULES``. The
in-process agents end their prompts with them, and the managed Runtime appends
the same text to its Gateway-backed prompt. Without them, the managed answers in
the dev deploy carried em dashes and the managed Support agent opened a store
credit review for Theo's chipped bowl, which he never asked for.
"""

from __future__ import annotations

import pytest

from pellier_copy import OUTPUT_RULES
from services.agentcore_gateway import _managed_specialist_prompt, unpublished_tools_prompt

SPECIALISTS = ("shopping", "stock", "support")


@pytest.mark.parametrize("specialist", SPECIALISTS)
def test_the_managed_prompt_ends_with_the_agents_own_output_rules(specialist: str) -> None:
    prompt = _managed_specialist_prompt(specialist, turn_id="turn-1", customer_id="CUST-THEO")

    assert OUTPUT_RULES[specialist] in prompt
    assert "em dashes" in " ".join(OUTPUT_RULES[specialist].split())


def test_the_managed_support_prompt_carries_the_copy_and_credit_sentences() -> None:
    prompt = _managed_specialist_prompt("support", customer_id="CUST-THEO")

    for sentence in (
        "Set credit_request to true only when the shopper asks for store credit",
        "never name or suggest an amount",
        "Do not name an amount, a timeframe or an outcome.",
        "Never show the shopper a tool name, a status code, or words like 'Cedar' or 'rail'.",
        "No markdown tables, numbered lists, emojis or em dashes.",
        "Never ask a follow-up question.",
    ):
        assert sentence in prompt, sentence


@pytest.mark.parametrize(
    ("module_name", "factory_name", "specialist"),
    [
        ("agents.shopping_agent", "build_shopping_agent", "shopping"),
        ("agents.stock_agent", "build_stock_agent", "stock"),
        ("agents.support_agent", "build_support_agent", "support"),
    ],
)
def test_the_in_process_agent_carries_the_same_rules(
    module_name: str, factory_name: str, specialist: str
) -> None:
    module = __import__(module_name, fromlist=[factory_name])
    agent = getattr(module, factory_name)()

    assert OUTPUT_RULES[specialist] in agent.system_prompt


def test_the_unpublished_note_offers_a_person_without_naming_the_tool() -> None:
    with_handoff = unpublished_tools_prompt(("get_tickets",), can_hand_off=True)
    without = unpublished_tools_prompt(("check_stock",))

    assert "can't look up support tickets here" in with_handoff
    assert "Offer to hand this to a person." in with_handoff
    assert "ask_a_person" not in with_handoff
    assert "a person" not in without
