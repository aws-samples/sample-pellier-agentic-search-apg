"""Routing decisions carry only their explicitly supplied context."""

from skills.loader import load_registry
from skills.router import SkillRouter


def test_reusing_a_router_does_not_reuse_agent_conversation(monkeypatch):
    import strands
    import strands.models

    observed = []

    class StatefulClassifier:
        def __init__(self, **kwargs):
            self.messages = []

        def __call__(self, message):
            self.messages.append(message)
            observed.append(list(self.messages))
            return '{"load": [], "considered": []}'

    monkeypatch.setattr(strands, "Agent", StatefulClassifier)
    monkeypatch.setattr(strands.models, "BedrockModel", lambda **kwargs: object())
    router = SkillRouter(load_registry())
    router.route("linen for Goa", context="A ten-day trip")
    router.route("What is this duvet made of?")
    assert observed == [
        ["Prior context:\nA ten-day trip\n\nCurrent message:\nlinen for Goa"],
        ["What is this duvet made of?"],
    ]
