"""Tests for `services.agentcore_gateway`.

  * The managed Router partitions the nine published tools across the three
    agents, and every tool lives on the one Gateway target.
  * Server-owned context (the verified customer and the turn id) is bound
    before a caller-bound tool executes, so the model cannot choose whose
    records to read.
  * The capability tiers and the safe-input allow-list agree with the
    published catalogue.

No live Gateway, no Bedrock, no network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

import services.agentcore_gateway as gateway
from services import store_tools

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "deploy"))
from gateway_tool_schemas import TOOL_SCHEMAS  # noqa: E402

NINE_TOOLS = set(store_tools.TOOL_NAMES)
TARGET = "pellier-store-tools"


def test_the_nine_tools_are_the_catalogue() -> None:
    assert NINE_TOOLS == {
        "search_products", "browse_department", "compare_products", "check_stock",
        "get_orders", "get_return_policy", "get_tickets", "give_store_credit", "ask_a_person",
    }
    assert set(gateway.GATEWAY_TOOL_TIERS) == NINE_TOOLS
    assert set(gateway.GATEWAY_TARGET_FOR_TOOL) == NINE_TOOLS
    assert set(gateway.GATEWAY_TARGET_FOR_TOOL.values()) == {TARGET}
    published = {tool["name"] for config in TOOL_SCHEMAS.values() for tool in config["tools"]}
    assert published == NINE_TOOLS
    assert [config["target_name"] for config in TOOL_SCHEMAS.values()] == [TARGET]


def test_managed_agents_partition_the_shopper_catalogue() -> None:
    assert set(gateway.MANAGED_SPECIALIST_TOOLS) == {"shopping", "stock", "support"}
    assert gateway.MANAGED_SPECIALIST_TOOLS["shopping"] == (
        "search_products", "browse_department", "compare_products", "ask_a_person",
    )
    assert gateway.MANAGED_SPECIALIST_TOOLS["stock"] == ("check_stock",)
    assert gateway.MANAGED_SPECIALIST_TOOLS["support"] == gateway.SUPPORT_MANAGED_TOOLS
    bound = set().union(*gateway.MANAGED_SPECIALIST_TOOLS.values())
    assert bound == NINE_TOOLS - {"give_store_credit"}


def test_the_cedar_action_id_embeds_the_one_target() -> None:
    assert gateway.gateway_action_id("give_store_credit") == f"{TARGET}___give_store_credit"
    with pytest.raises(KeyError):
        gateway.gateway_action_id("_".join(("issue", "credit")))


def test_the_tiers_name_the_one_money_movement() -> None:
    assert gateway.mutation_tool_names() == ["give_store_credit"]
    assert gateway.tools_in_tier(gateway.TIER_ESCALATION) == ["ask_a_person"]
    assert set(gateway.tools_in_tier(gateway.TIER_READ)) == NINE_TOOLS - {"give_store_credit", "ask_a_person"}
    assert gateway.tool_tier("_".join(("restock", "inventory"))) == gateway.TIER_OPERATOR_MUTATION


def test_every_published_input_field_is_safe_to_inspect() -> None:
    """A tool argument the catalogue declares is one the trace may show."""
    declared = {
        name
        for config in TOOL_SCHEMAS.values()
        for tool in config["tools"]
        for name in tool["inputSchema"]["properties"]
    }
    assert declared <= gateway._SAFE_TOOL_INPUT_FIELDS, declared - gateway._SAFE_TOOL_INPUT_FIELDS


@pytest.mark.parametrize(
    ("published", "logical"),
    [
        ("get_tickets", "get_tickets"),
        ("pellier-store-tools__get_tickets", "get_tickets"),
        ("pellier-store-tools___get_tickets", "get_tickets"),
    ],
)
def test_logical_gateway_tool_name_strips_target_prefix(published: str, logical: str) -> None:
    assert gateway._logical_gateway_tool_name(published) == logical


def test_server_context_overrides_model_identity_and_correlation() -> None:
    bound = gateway._bind_server_tool_context(
        {
            "name": f"{TARGET}___get_orders",
            "toolUseId": "call-1",
            "input": {"customer_id": "CUST-THEO", "turn_id": "turn-model-value", "limit": 3},
        },
        customer_id="CUST-MARCO",
        turn_id="turn-" + ("a" * 32),
    )

    assert bound["input"] == {
        "customer_id": "CUST-MARCO",
        "turn_id": "turn-" + ("a" * 32),
        "limit": 3,
    }


def test_customer_scope_records_what_the_model_asked_for_and_what_the_server_bound() -> None:
    """Theo signed in, the model asks for Jessica: the server overwrites, and says so."""
    scope = gateway._customer_scope(
        {"name": f"{TARGET}___get_orders", "input": {"customer_id": "CUST-JESSICA"}},
        "CUST-THEO",
    )

    assert scope == {
        "customer_scope": "server",
        "requested_other_customer": True,
        "requested_customer": "CUST-JESSICA",
        "bound_customer": "CUST-THEO",
        "binding": "overwritten",
    }


def test_customer_scope_matched_and_bound_verdicts() -> None:
    same = gateway._customer_scope(
        {"name": f"{TARGET}___get_orders", "input": {"customer_id": "CUST-THEO"}},
        "CUST-THEO",
    )
    none = gateway._customer_scope(
        {"name": f"{TARGET}___get_orders", "input": {"limit": 5}},
        "CUST-THEO",
    )

    assert (same["binding"], same["requested_customer"], same["bound_customer"]) == (
        "matched", "CUST-THEO", "CUST-THEO",
    )
    assert (none["binding"], none["requested_customer"], none["bound_customer"]) == (
        "bound", None, "CUST-THEO",
    )


def test_customer_scope_marks_an_unbound_tool_as_chosen_by_the_model(monkeypatch) -> None:
    """The Lab 3A starter: `get_tickets` is published but the model still picks the customer."""
    monkeypatch.setattr(
        gateway, "_CUSTOMER_SCOPED_TOOL_NAMES",
        gateway._CUSTOMER_SCOPED_TOOL_NAMES - {"get_tickets"},
    )
    call = {"name": f"{TARGET}___get_tickets", "input": {"customer_id": "CUST-THEO"}}

    assert gateway._customer_scope(call, "CUST-THEO") == {
        "customer_scope": "model",
        "requested_other_customer": False,
        "requested_customer": "CUST-THEO",
        "bound_customer": None,
        "binding": "unbound",
    }


def test_customer_scope_follows_the_caller_bound_set(monkeypatch) -> None:
    """The Lab 3A build: once bound, the server decides and records that it did."""
    monkeypatch.setattr(
        gateway, "_CUSTOMER_SCOPED_TOOL_NAMES",
        gateway._CUSTOMER_SCOPED_TOOL_NAMES | {"get_tickets"},
    )
    call = {"name": f"{TARGET}___get_tickets", "input": {"customer_id": "CUST-JESSICA"}}

    assert gateway._customer_scope(call, "CUST-THEO") == {
        "customer_scope": "server",
        "requested_other_customer": True,
        "requested_customer": "CUST-JESSICA",
        "bound_customer": "CUST-THEO",
        "binding": "overwritten",
    }


def test_customer_scope_is_empty_for_a_tool_with_no_customer() -> None:
    call = {"name": f"{TARGET}___search_products", "input": {"query": "linen"}}

    assert gateway._customer_scope(call, "CUST-MARCO") == {}


def test_get_orders_is_bound_outside_the_lab_region() -> None:
    assert "get_orders" in gateway._CUSTOMER_SCOPED_TOOL_NAMES
    assert gateway._CUSTOMER_SCOPED_TOOL_NAMES >= gateway.SUPPORT_CALLER_BOUND_TOOLS
    # The handoff is bound when the caller is known and never refused.
    assert "ask_a_person" not in gateway._CUSTOMER_SCOPED_TOOL_NAMES
    assert gateway._CUSTOMER_BOUND_WHEN_KNOWN_TOOL_NAMES == frozenset({"ask_a_person"})


def test_the_handoff_is_bound_to_a_known_caller() -> None:
    bound = gateway._bind_server_tool_context(
        {
            "name": f"{TARGET}___ask_a_person",
            "toolUseId": "call-4",
            "input": {"reason": "I want a person.", "customer_id": "CUST-JESSICA"},
        },
        customer_id="CUST-THEO",
        turn_id="turn-" + ("d" * 32),
    )

    assert bound["input"] == {
        "reason": "I want a person.",
        "customer_id": "CUST-THEO",
        "turn_id": "turn-" + ("d" * 32),
    }
    scope = gateway._customer_scope(
        {"name": f"{TARGET}___ask_a_person", "input": {"customer_id": "CUST-JESSICA"}},
        "CUST-THEO",
    )
    assert scope == {
        "customer_scope": "server",
        "requested_other_customer": True,
        "requested_customer": "CUST-JESSICA",
        "bound_customer": "CUST-THEO",
        "binding": "overwritten",
    }


def test_the_handoff_still_runs_for_an_unknown_caller() -> None:
    """Anyone may ask for a person; the model's customer is dropped, not trusted.

    The local rail does the same: `store_tools.ask_a_person` completes the
    handoff and withholds only the credit review when no customer is known.
    """
    bound = gateway._bind_server_tool_context(
        {
            "name": f"{TARGET}___ask_a_person",
            "toolUseId": "call-5",
            "input": {"reason": "I want a person.", "customer_id": "CUST-JESSICA"},
        },
        customer_id="",
        turn_id="turn-" + ("e" * 32),
    )

    assert bound["input"] == {"reason": "I want a person.", "turn_id": "turn-" + ("e" * 32)}


def test_customer_scoped_tool_requires_verified_customer_context() -> None:
    with pytest.raises(ValueError, match="verified Aurora customer context"):
        gateway._bind_server_tool_context(
            {
                "name": f"{TARGET}___get_orders",
                "toolUseId": "call-2",
                "input": {"limit": 5},
            },
            customer_id="",
            turn_id="turn-" + ("b" * 32),
        )


def test_non_customer_tool_still_receives_server_turn_id() -> None:
    bound = gateway._bind_server_tool_context(
        {
            "name": f"{TARGET}___search_products",
            "toolUseId": "call-3",
            "input": {"query": "linen", "turn_id": "untrusted"},
        },
        customer_id="CUST-MARCO",
        turn_id="turn-" + ("c" * 32),
    )

    assert bound["input"] == {"query": "linen", "turn_id": "turn-" + ("c" * 32)}


def test_an_unknown_intent_cannot_build_a_managed_agent() -> None:
    with pytest.raises(ValueError, match="unknown intent"):
        gateway._managed_specialist_spec("pricing")


def test_the_managed_prompt_names_the_agent_and_binds_the_turn() -> None:
    intent, prompt, tools, skills = gateway._managed_specialist_spec(
        "support", turn_id="turn-" + ("d" * 32), customer_id="CUST-THEO",
    )
    assert intent == "support" and tools == gateway.SUPPORT_MANAGED_TOOLS
    assert "Support agent" in prompt
    assert "turn_id='turn-" in prompt and "CUST-THEO" in prompt


def test_the_managed_agent_carries_the_same_fixed_skills_and_reports_them() -> None:
    """The deployed agent is the same agent: its prompt carries the fixed skills,
    and what it reports is what the prompt carried."""
    from skills import get_registry

    _, prompt, _, skills = gateway._managed_specialist_spec("support")
    assert [skill["name"] for skill in skills] == ["the-care-card", "the-proof-counter"]
    assert all(skill["loaded"] == "fixed" for skill in skills)
    assert skills[0]["path"] == "skills/the-care-card/SKILL.md"
    assert get_registry().get("the-care-card").body.strip() in prompt
    assert get_registry().get("the-gift-table").body.strip() not in prompt


def test_the_managed_report_is_empty_when_the_bundle_carries_no_skills(monkeypatch) -> None:
    import skills as skills_package

    monkeypatch.setattr(skills_package, "skills_for", lambda _agent: [])
    _, prompt, _, skills = gateway._managed_specialist_spec("support")
    assert skills == []
    assert "SKILLS - loaded for this agent" not in prompt


def test_the_managed_shopping_prompt_carries_limits_across_the_conversation() -> None:
    _, prompt, _, _ = gateway._managed_specialist_spec("shopping")
    assert "browse_department as arguments" in prompt
    assert "including limits the shopper stated earlier in this conversation" in prompt


def test_a_requested_customer_is_emitted_only_in_the_customer_id_shape() -> None:
    """A model string that is not a customer id never becomes evidence."""
    scope = gateway._customer_scope(
        {"name": f"{TARGET}___get_orders", "input": {"customer_id": "jessica's account"}},
        "CUST-THEO",
    )
    assert scope["requested_customer"] is None
    assert scope["requested_other_customer"] is True
    assert scope["binding"] == "overwritten"
    lowercase = gateway._customer_scope(
        {"name": f"{TARGET}___get_orders", "input": {"customer_id": "cust-theo"}},
        "CUST-THEO",
    )
    assert lowercase["requested_customer"] == "CUST-THEO"
    assert lowercase["binding"] == "matched"


def test_gateway_tool_names_are_read_through_the_strands_tool_interface() -> None:
    """Strands 1.48's ``MCPAgentTool`` exposes ``tool_name`` and ``tool_spec``, not ``name``.

    Both the live Router and the Lab 3A twin use that public interface.
    """
    import ast

    from strands.tools.mcp.mcp_agent_tool import MCPAgentTool

    assert hasattr(MCPAgentTool, "tool_name") and hasattr(MCPAgentTool, "tool_spec")
    assert not hasattr(MCPAgentTool, "name")
    backend = Path(__file__).resolve().parents[1]
    for path in (
        backend / "services" / "agentcore_gateway.py",
        backend.parents[1] / "solutions" / "the-ledger" / "services" / "agentcore_gateway.py",
    ):
        source = path.read_text()
        invalid = [
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute) and node.attr == "name"
            and isinstance(node.value, ast.Name) and node.value.id == "tool"
        ]
        assert not invalid, f"{path.name} reads MCPAgentTool.name"
        assert "tool.tool_name" in source


def test_a_shopper_agent_may_not_bind_the_staff_only_gateway_tool() -> None:
    """A tool published for human-approved credits cannot be bound to a shopper agent."""
    gateway.assert_no_staff_only_binding("shopping", ["search_products", "compare_products"])
    with pytest.raises(RuntimeError, match="staff-only Gateway tools: give_store_credit"):
        gateway.assert_no_staff_only_binding("support", ["get_return_policy", "give_store_credit"])
    assert gateway.STAFF_ONLY_GATEWAY_TOOLS == frozenset({"give_store_credit"})
    for tools in gateway.MANAGED_SPECIALIST_TOOLS.values():
        assert not set(tools) & gateway.STAFF_ONLY_GATEWAY_TOOLS


def test_the_result_summary_keeps_only_bounded_fields() -> None:
    summary: Dict[str, Any] = gateway._result_summary(
        {"content": [{"text": json.dumps({"status": "success", "count": 2, "orders": [{"x": 1}]})}]},
        [{"productId": "7"}, {"name": "unnamed"}],
    )
    assert summary == {"product_count": 2, "product_ids": ["7"], "status": "success", "count": 2}
