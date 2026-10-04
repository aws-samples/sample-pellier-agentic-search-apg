"""The Claude model each specialist answers with.

Routing is deterministic and calls no model. Editorial specialists (search,
recommendation, support) answer on Opus; reporting specialists (pricing,
inventory) answer on Sonnet.
"""

from __future__ import annotations

import os
from typing import Literal

try:
    from config import settings
except ModuleNotFoundError:
    class _RuntimeSettings:
        """Model settings for the minimal managed Runtime source bundle."""

        BEDROCK_OPUS_MODEL = (
            os.environ.get("BEDROCK_OPUS_MODEL")
            or os.environ.get("AGENT_MODEL_ID")
            or os.environ.get("BEDROCK_ROUTER_MODEL", "")
        )
        BEDROCK_REPORTING_MODEL = (
            os.environ.get("BEDROCK_REPORTING_MODEL")
            or os.environ.get("BEDROCK_SONNET_MODEL")
            or os.environ.get("BEDROCK_ROUTER_MODEL")
            or os.environ.get("AGENT_MODEL_ID", "")
        )
        AGENT_MAX_TOKENS_OPUS = int(
            os.environ.get("AGENT_MAX_TOKENS_OPUS", "1200")
        )
        AGENT_MAX_TOKENS_SONNET = int(
            os.environ.get("AGENT_MAX_TOKENS_SONNET", "2048")
        )

    settings = _RuntimeSettings()

ModelTier = Literal["opus", "sonnet"]

REPORTING_INTENTS = frozenset({"pricing", "inventory"})


def specialist_model(tier: ModelTier) -> tuple[str, int]:
    """Return the model ID and output ceiling for one specialist tier."""
    if tier == "opus":
        return settings.BEDROCK_OPUS_MODEL, settings.AGENT_MAX_TOKENS_OPUS
    return settings.BEDROCK_REPORTING_MODEL, settings.AGENT_MAX_TOKENS_SONNET


def model_for_intent(intent: str) -> tuple[str, int]:
    """Return the model ID and output ceiling for a routed intent."""
    normalized_intent = "support" if intent == "customer_support" else intent
    tier: ModelTier = "sonnet" if normalized_intent in REPORTING_INTENTS else "opus"
    return specialist_model(tier)


def build_intent_signal(intent: str) -> dict:
    """Build the public SSE event describing the real routing decision."""
    normalized_intent = "support" if intent == "customer_support" else intent
    model_id, _ = model_for_intent(normalized_intent)
    model_id_lower = model_id.lower()
    model_family = (
        "opus"
        if "opus" in model_id_lower
        else "sonnet"
        if "sonnet" in model_id_lower
        else "unknown"
    )
    return {
        "type": "intent_signal",
        "intent": normalized_intent,
        "classifier": "deterministic",
        "model_family": model_family,
        "model_id": model_id,
    }
