"""The agent and Claude model each routed intent answers with.

The Router is deterministic and calls no model. The Shopping and Support
agents answer on Opus; the Stock agent, which reports counts, answers on
Sonnet.
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

# The three intents the Router returns, and the agent each one reaches.
AGENT_NAMES: dict[str, str] = {
    "shopping": "Shopping agent",
    "stock": "Stock agent",
    "support": "Support agent",
}
ROUTER_NAME = "Router"

REPORTING_INTENTS = frozenset({"stock"})


def specialist_model(tier: ModelTier) -> tuple[str, int]:
    """Return the model ID and output ceiling for one specialist tier."""
    if tier == "opus":
        return settings.BEDROCK_OPUS_MODEL, settings.AGENT_MAX_TOKENS_OPUS
    return settings.BEDROCK_REPORTING_MODEL, settings.AGENT_MAX_TOKENS_SONNET


def model_for_intent(intent: str) -> tuple[str, int]:
    """Return the model ID and output ceiling for a routed intent."""
    tier: ModelTier = "sonnet" if intent in REPORTING_INTENTS else "opus"
    return specialist_model(tier)


def agent_name(intent: str) -> str:
    """The display name of the agent a routed intent reaches."""
    return AGENT_NAMES[intent]


def build_intent_signal(intent: str) -> dict:
    """Build the public SSE event describing the real routing decision."""
    model_id, _ = model_for_intent(intent)
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
        "intent": intent,
        "agent": agent_name(intent),
        "classifier": "deterministic",
        "model_family": model_family,
        "model_id": model_id,
    }
