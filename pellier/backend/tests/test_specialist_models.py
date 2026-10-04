"""Each specialist answers on one fixed Claude 5 model."""

from __future__ import annotations

import pytest

from config import settings
from services.specialist_models import build_intent_signal, model_for_intent


@pytest.mark.parametrize(
    ("intent", "setting"),
    [
        ("shopping", "BEDROCK_OPUS_MODEL"),
        ("support", "BEDROCK_OPUS_MODEL"),
        ("stock", "BEDROCK_REPORTING_MODEL"),
    ],
)
def test_each_intent_answers_on_its_configured_model(intent: str, setting: str) -> None:
    model_id, max_tokens = model_for_intent(intent)

    assert model_id == getattr(settings, setting)
    assert max_tokens > 0


def test_the_default_profiles_are_global_claude_5() -> None:
    assert settings.BEDROCK_OPUS_MODEL == "global.anthropic.claude-opus-5"
    assert settings.BEDROCK_REPORTING_MODEL == "global.anthropic.claude-sonnet-5"
    assert not hasattr(settings, "BEDROCK_FAST_MODEL")


def test_intent_signal_reports_the_model_that_answers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "BEDROCK_OPUS_MODEL", "global.anthropic.claude-opus-5")
    monkeypatch.setattr(settings, "BEDROCK_REPORTING_MODEL", "global.anthropic.claude-sonnet-5")

    assert build_intent_signal("support") == {
        "type": "intent_signal",
        "intent": "support",
        "agent": "Support agent",
        "classifier": "deterministic",
        "model_family": "opus",
        "model_id": "global.anthropic.claude-opus-5",
    }
    assert build_intent_signal("stock")["model_family"] == "sonnet"


def test_managed_dispatcher_keeps_the_caller_scope(monkeypatch) -> None:
    from services import agentcore_gateway

    monkeypatch.setattr(
        agentcore_gateway,
        "_runtime_or_app_setting",
        lambda name, default="": (
            "https://gateway.example/mcp"
            if name == "AGENTCORE_GATEWAY_URL"
            else default
        ),
    )

    dispatcher = agentcore_gateway.create_gateway_dispatcher(
        access_token="jwt",
        customer_id="CUST-MARCO",
        routing_query="find a resort shirt",
    )

    assert dispatcher is not None
    assert dispatcher.customer_id == "CUST-MARCO"
    assert dispatcher.routing_query == "find a resort shirt"
    prompt = agentcore_gateway._managed_specialist_prompt(
        "shopping",
        customer_id=dispatcher.customer_id,
    )
    assert "customer_id='CUST-MARCO'" in prompt


@pytest.mark.parametrize(
    ("module_name", "factory_name", "setting"),
    [
        ("agents.shopping_agent", "build_shopping_agent", "BEDROCK_OPUS_MODEL"),
        ("agents.support_agent", "build_support_agent", "BEDROCK_OPUS_MODEL"),
    ],
)
def test_every_specialist_factory_builds_on_its_configured_model(
    module_name: str,
    factory_name: str,
    setting: str,
) -> None:
    module = __import__(module_name, fromlist=[factory_name])
    agent = getattr(module, factory_name)()

    assert agent.model.config["model_id"] == getattr(settings, setting)


def test_the_router_and_agent_display_names_are_fixed() -> None:
    from services.specialist_models import AGENT_NAMES, REPORTING_INTENTS, ROUTER_NAME

    assert ROUTER_NAME == "Router"
    assert AGENT_NAMES == {
        "shopping": "Shopping agent",
        "stock": "Stock agent",
        "support": "Support agent",
    }
    assert REPORTING_INTENTS == {"stock"}
