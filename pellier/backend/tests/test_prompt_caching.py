"""Every Bedrock model the agents use turns on Strands prompt caching (strategy "auto")."""

from __future__ import annotations

from typing import Any

import pytest
from strands.models import BedrockModel, CacheConfig

from config import settings
from services import model_fallback, specialist_models
from services.model_fallback import FallbackBedrockModel, specialist_bedrock_model

OPUS, SONNET = "global.anthropic.claude-opus-5-5", "global.anthropic.claude-sonnet-5-5"


def _auto(model: Any) -> bool:
    config = model.config.get("cache_config")
    return isinstance(config, CacheConfig) and config.strategy == "auto"


def _recognised(model_id: str) -> bool:
    """Whether Strands' own detection maps this ID to a cache strategy under "auto"."""
    probe = BedrockModel(model_id=model_id, max_tokens=16, cache_config=CacheConfig("auto"))
    return probe._cache_strategy is not None


def test_a_specialist_with_a_fallback_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_fallback, "specialist_model", lambda _tier: (SONNET, 2048))
    model = specialist_bedrock_model(OPUS, 1200)
    assert isinstance(model, FallbackBedrockModel) and _auto(model)


def test_a_specialist_without_a_fallback_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_fallback, "specialist_model", lambda _tier: (SONNET, 2048))
    model = specialist_bedrock_model(SONNET, 2048)
    assert not isinstance(model, FallbackBedrockModel) and _auto(model)


def test_a_turn_that_falls_back_keeps_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_fallback, "specialist_model", lambda _tier: (SONNET, 2048))
    model = specialist_bedrock_model(OPUS, 1200)
    assert isinstance(model, FallbackBedrockModel)
    model.fall_back(RuntimeError("unavailable"))
    assert model.config["model_id"] == SONNET and _auto(model)


def test_the_stock_agent_caches() -> None:
    from agents.stock_agent import build_stock_agent

    assert _auto(build_stock_agent().model)


def test_the_operators_investigator_and_advisor_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import strands
    import strands.models

    from services import operator_graph

    built: list[dict[str, Any]] = []

    class _Model:
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)

    class _Agent:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(strands.models, "BedrockModel", _Model)
    monkeypatch.setattr(strands, "Agent", _Agent)

    class _Case:
        customer_name, customer_id, turn_id = "Jessica", "CUST-JESSICA", "turn-test"

    hooks = {operator_graph.INVESTIGATOR_NODE: object(), operator_graph.ADVISOR_NODE: object()}
    try:
        operator_graph._build_graph(_Case(), SONNET, hooks)
    except Exception:  # noqa: BLE001 - the graph needs real agents; both models are built before it
        pass
    assert sorted(kw["max_tokens"] for kw in built) == sorted(
        [operator_graph._INVESTIGATOR_MAX_TOKENS, operator_graph._ADVISOR_MAX_TOKENS])
    assert all(kw.get("cache_config") == model_fallback.PROMPT_CACHE for kw in built)


@pytest.mark.parametrize("model_id", [
    settings.BEDROCK_OPUS_MODEL, settings.BEDROCK_SONNET_MODEL, settings.BEDROCK_REPORTING_MODEL,
    specialist_models.specialist_model("opus")[0], specialist_models.specialist_model("sonnet")[0],
])
def test_the_workshop_model_ids_are_recognised_by_auto(model_id: str) -> None:
    assert _recognised(model_id)


def test_auto_does_not_guess_for_a_non_claude_id() -> None:
    assert not _recognised("amazon.nova-pro-v1:0")
