"""Skills are fixed per agent with no model call; on demand, the agent opens its own."""

from __future__ import annotations

import asyncio

import pytest
from strands.hooks.events import BeforeInvocationEvent

from skills import (
    FIXED_SKILLS,
    SKILL_MODE_FIXED,
    SKILL_MODE_ON_DEMAND,
    get_registry,
    inject_skills,
    normalize_skill_mode,
    on_demand_plugin,
    skill_receipt,
    skills_for,
)


def test_the_fixed_mapping_is_the_brief_table() -> None:
    assert FIXED_SKILLS == {
        "shopping": ("the-gift-table", "the-makers-shelf", "the-packing-list", "the-proof-counter"),
        "stock": ("the-proof-counter",),
        "support": ("the-care-card", "the-proof-counter"),
    }
    for agent_key, names in FIXED_SKILLS.items():
        assert tuple(skill.name for skill in skills_for(agent_key)) == names


def test_fixed_mode_carries_the_bodies_in_the_prompt() -> None:
    prompt = inject_skills("BASE", skills_for("support"))
    care_card = get_registry().get("the-care-card")
    assert care_card is not None
    assert care_card.body.strip() in prompt
    assert "the-proof-counter" in prompt
    assert "the-gift-table" not in prompt


def test_request_field_normalizes_to_a_known_mode_and_defaults_to_fixed() -> None:
    assert normalize_skill_mode(None) == SKILL_MODE_FIXED
    assert normalize_skill_mode("") == SKILL_MODE_FIXED
    assert normalize_skill_mode("ON_DEMAND") == SKILL_MODE_ON_DEMAND
    assert normalize_skill_mode("anything else") == SKILL_MODE_FIXED


def test_the_receipt_records_how_each_skill_loaded() -> None:
    fixed = skill_receipt("stock", SKILL_MODE_FIXED)
    assert fixed == [
        {
            "name": "the-proof-counter",
            "display_name": "The Proof Counter",
            "path": "skills/the-proof-counter/SKILL.md",
            "loaded": "fixed",
        }
    ]
    on_demand = skill_receipt("shopping", SKILL_MODE_ON_DEMAND, ["the-gift-table", "not-a-skill"])
    assert [(skill["name"], skill["loaded"]) for skill in on_demand] == [("the-gift-table", "on demand")]
    assert skill_receipt("shopping", SKILL_MODE_ON_DEMAND) == []


# ---------------------------------------------------------------------------
# On demand: the Strands AgentSkills plugin, driven offline
# ---------------------------------------------------------------------------


@pytest.fixture
def shopping_on_demand():
    from agents.shopping_agent import build_shopping_agent

    agent = build_shopping_agent(allow_handoff=False, skill_mode=SKILL_MODE_ON_DEMAND)
    asyncio.run(agent.hooks.invoke_callbacks_async(BeforeInvocationEvent(agent=agent)))
    return agent


def test_on_demand_prompt_lists_names_and_descriptions_only(shopping_on_demand) -> None:
    prompt = str(shopping_on_demand.system_prompt)
    registry = get_registry()
    for name in FIXED_SKILLS["shopping"]:
        skill = registry.get(name)
        assert skill is not None
        assert f"<name>{name}</name>" in prompt
        assert skill.description.split(":")[0] in prompt
        assert skill.body.strip() not in prompt, f"{name} body leaked into the on-demand prompt"
    assert "<name>the-care-card</name>" not in prompt
    assert "skills" in shopping_on_demand.tool_names


def test_load_skill_returns_the_body_and_refuses_out_of_set_and_unknown_names(shopping_on_demand) -> None:
    body = get_registry().get("the-gift-table").body.strip()

    loaded = shopping_on_demand.tool.skills(skill_name="the-gift-table", record_direct_tool_call=False)
    assert loaded["status"] == "success"
    assert body in loaded["content"][0]["text"]

    out_of_set = shopping_on_demand.tool.skills(skill_name="the-care-card", record_direct_tool_call=False)
    assert "not found" in out_of_set["content"][0]["text"]
    assert "the-care-card" not in out_of_set["content"][0]["text"].split("Available skills:")[1]

    unknown = shopping_on_demand.tool.skills(skill_name="the-crystal-ball", record_direct_tool_call=False)
    assert "not found" in unknown["content"][0]["text"]


def test_fixed_mode_agents_have_no_loader_tool() -> None:
    from agents.support_agent import build_support_agent

    agent = build_support_agent()
    assert "skills" not in agent.tool_names
    assert get_registry().get("the-care-card").body.strip() in str(agent.system_prompt)


def test_the_plugin_carries_only_the_agents_own_skills() -> None:
    plugin = on_demand_plugin("support")
    assert sorted(skill.name for skill in plugin.get_available_skills()) == [
        "the-care-card", "the-proof-counter",
    ]
