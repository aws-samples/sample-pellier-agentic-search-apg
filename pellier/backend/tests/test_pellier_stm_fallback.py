"""Regression test for Pellier writes to the local STM fallback."""

from __future__ import annotations

import asyncio

from services import agentcore_memory
from services.agentcore_memory import AgentCoreMemory
from services.chat import _append_pellier_stm_turn


def test_pellier_turn_writes_when_agentcore_memory_id_is_unset(monkeypatch) -> None:
    monkeypatch.setattr(agentcore_memory, "_SESSION_STORE", {})
    monkeypatch.setattr(agentcore_memory.settings, "AGENTCORE_MEMORY_ID", None)

    asyncio.run(
        _append_pellier_stm_turn(
            "persona-marco-fallback",
            "Show me linen for Goa.",
            "Here are two breathable options.",
        )
    )

    history = asyncio.run(
        AgentCoreMemory().get_session_history(
            "anon-persona-marco-fallback"
        )
    )
    assert history == [
        {"role": "user", "content": "Show me linen for Goa."},
        {"role": "assistant", "content": "Here are two breathable options."},
    ]


def test_live_customer_turn_uses_the_same_actor_as_preference_recall(monkeypatch):
    from services.turn_identity import TurnIdentity

    monkeypatch.setattr(agentcore_memory, "_SESSION_STORE", {})
    monkeypatch.setattr(agentcore_memory.settings, "AGENTCORE_MEMORY_ID", None)
    memory = AgentCoreMemory()
    identity = TurnIdentity(principal_sub="theo-sub", shopper_customer_id="CUST-THEO", authenticated=True)
    namespace = "user-theo-sub-session-gifts"
    asyncio.run(_append_pellier_stm_turn("gifts", "I like indigo.", "Understood.", identity=identity))
    history, _ = asyncio.run(memory.get_memory_events(actor_id="CUST-THEO", session_id=namespace))
    assert [turn["content"] for turn in history] == ["I like indigo.", "Understood."]
    assert asyncio.run(memory.get_session_history(namespace, customer_id="CUST-THEO")) == history
    for actor, session in [("CUST-THEO", "user-theo-sub-session-new"), ("CUST-ANNA", namespace)]:
        assert asyncio.run(memory.get_memory_events(actor_id=actor, session_id=session))[0] == []


def test_a_simulated_persona_writes_only_to_the_anonymous_session(monkeypatch):
    from services.turn_identity import TurnIdentity

    monkeypatch.setattr(agentcore_memory, "_SESSION_STORE", {})
    monkeypatch.setattr(agentcore_memory.settings, "AGENTCORE_MEMORY_ID", None)
    simulated = TurnIdentity(shopper_customer_id="CUST-THEO", persona_is_simulated=True)
    asyncio.run(_append_pellier_stm_turn("shared", "I like indigo.", "OK.", identity=simulated))
    memory = AgentCoreMemory()
    assert len(asyncio.run(memory.get_session_history("anon-shared"))) == 2
    assert asyncio.run(memory.get_memory_events(actor_id="CUST-THEO", session_id="anon-shared"))[0] == []


def test_existing_conversation_remains_readable_after_customer_mapping_changes(monkeypatch):
    monkeypatch.setattr(agentcore_memory, "_SESSION_STORE", {})
    monkeypatch.setattr(agentcore_memory.settings, "AGENTCORE_MEMORY_ID", None)
    memory = AgentCoreMemory()
    namespace = "user-theo-sub-session-gifts"
    old = {"role": "user", "content": "First turn"}
    new = {"role": "user", "content": "Second turn"}
    asyncio.run(memory.append_session_turns(namespace, [old]))
    asyncio.run(memory.append_session_turns(namespace, [new], customer_id="CUST-THEO"))
    assert asyncio.run(memory.get_session_history(namespace, customer_id="CUST-THEO")) == [old, new]
    assert asyncio.run(memory.get_session_history("user-anna-sub-session-gifts", customer_id="CUST-ANNA")) == []
