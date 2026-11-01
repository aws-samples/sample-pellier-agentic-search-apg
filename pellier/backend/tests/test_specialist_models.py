"""Each specialist answers on one fixed Claude 5 model."""

from __future__ import annotations

import pytest

from config import settings
from services.specialist_models import build_intent_signal, model_for_intent


@pytest.mark.parametrize(
    ("intent", "setting"),
    [
        ("catalog", "BEDROCK_OPUS_MODEL"),
        ("support", "BEDROCK_OPUS_MODEL"),
        ("stock", "BEDROCK_REPORTING_MODEL"),
    ],
)
def test_each_intent_answers_on_its_configured_model(intent: str, setting: str) -> None:
    model_id, max_tokens = model_for_intent(intent)

    assert model_id == getattr(settings, setting)
    assert max_tokens > 0


def test_the_default_profiles_are_global_claude_5() -> None:
    assert settings.BEDROCK_OPUS_MODEL == "global.anthropic.claude-opus-5-5"
    assert settings.BEDROCK_REPORTING_MODEL == "global.anthropic.claude-sonnet-5-5"
    assert not hasattr(settings, "BEDROCK_FAST_MODEL")


def test_intent_signal_reports_the_model_that_answers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "BEDROCK_OPUS_MODEL", "global.anthropic.claude-opus-5-5")
    monkeypatch.setattr(settings, "BEDROCK_REPORTING_MODEL", "global.anthropic.claude-sonnet-5-5")

    assert build_intent_signal("support") == {
        "type": "intent_signal",
        "intent": "support",
        "agent": "Support agent",
        "classifier": "deterministic",
        "model_family": "opus",
        "model_id": "global.anthropic.claude-opus-5-5",
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
        "catalog",
        customer_id=dispatcher.customer_id,
    )
    assert "customer_id='CUST-MARCO'" in prompt


@pytest.mark.parametrize(
    ("module_name", "factory_name", "setting"),
    [
        ("agents.catalog_agent", "build_catalog_agent", "BEDROCK_OPUS_MODEL"),
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
        "catalog": "Catalog agent",
        "stock": "Stock agent",
        "support": "Support agent",
    }
    assert REPORTING_INTENTS == {"stock"}


def test_operator_graph_asks_for_the_sonnet_tier(monkeypatch) -> None:
    """CLAUDE.md puts the Investigator and Advisor on Sonnet; the operator tests stub the tier."""
    from services import operator_graph, specialist_models

    class _GraphNotBuilt(Exception):
        pass

    requested: list = []

    def _record(tier: str) -> tuple:
        requested.append(tier)
        return ("model-test", 1024)

    def _stop(*_args, **_kwargs):
        raise _GraphNotBuilt

    monkeypatch.setattr(specialist_models, "specialist_model", _record)
    monkeypatch.setattr(operator_graph, "_build_graph", _stop)

    with pytest.raises(_GraphNotBuilt):
        operator_graph.run_investigation(
            run=lambda *_a, **_k: [], run_customer=lambda *_a, **_k: [],
            customer_id="c-1", customer_name="Test Client", operator_sub="staff-1",
            turn_id="t-1", emit=lambda _event: None,
        )

    assert requested == ["sonnet"]
