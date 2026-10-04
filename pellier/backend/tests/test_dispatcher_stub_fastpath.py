"""The workshop scaffold must not simulate an answer for an unbuilt specialist."""

from __future__ import annotations

import pytest

from services import chat as chat_module
from services.chat import EnhancedChatService
from skills import SkillRouter
from config import settings


@pytest.mark.asyncio
async def test_inventory_stub_returns_before_skill_router_or_specialist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("exercise-state dispatcher invoked Bedrock-backed work")

    monkeypatch.setattr(SkillRouter, "route", unexpected_call)
    monkeypatch.setattr(
        chat_module,
        "_build_dispatcher_specialist",
        unexpected_call,
    )
    monkeypatch.setattr(settings, "AGENTCORE_MEMORY_ID", "memory-test")

    service = EnhancedChatService(db_service=object())
    events = [
        event
        async for event in service.chat_stream(
            message=(
                "Is the Hadley shirt at the Brooklyn warehouse, "
                "and can it still ship in time?"
            ),
            turn_id="turn-00000000000000000000000000000000",
            session_id="session-00000000000000000000000000000000",
            user={"sub": "shopper-sub", "customer_id": "CUST-MARCO"},
        )
    ]

    assert not any(event["type"] == "skill_routing" for event in events)
    assert not any(
        event.get("source") == "Amazon Bedrock"
        for event in events
        if event["type"] == "agent_step"
    )
    step = next(event for event in events if event["type"] == "agent_step")
    assert step == {
        "type": "agent_step",
        "agent": "Inventory Agent",
        "action": "Workshop build required",
        "status": "blocked",
        "source": "Pellier build state",
    }
    build_required = next(event for event in events if event["type"] == "build_required")
    assert build_required["code"] == "workshop_build_required"
    assert "intentionally unbuilt" in build_required["message"]
    assert not any(event["type"] == "error" for event in events)
    complete = next(event for event in events if event["type"] == "complete")
    assert complete["response"]["success"] is False
    assert complete["response"]["agent_execution"]["model"] is None
    assert complete["response"]["agent_execution"]["build_required"] is True
    assert events[-1]["type"] == "complete"
