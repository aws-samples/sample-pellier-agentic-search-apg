"""Shared escalation helpers for inner specialist agents (Pattern I).

Pattern I (agents-as-tools) builds a fresh inner specialist Agent each time
the orchestrator invokes one of the @tool wrappers in ``agents/style_advisor.py``,
``agents/curator.py``, etc. Those inner specialists can emit an
``escalate_to_stylist`` payload that the outer wrapper has to surface back to
``services/chat.py`` so the chat UI can render the stylist handoff card.

This module provides the two helpers that do that surfacing —
``extract_escalation_payload`` and ``append_escalation_marker``. They are not
policy-related; policy enforcement now lives entirely in the managed AgentCore
Policy engine at the Gateway (Cedar, ENFORCE mode), not in any in-process hook.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def extract_escalation_payload(tool_results: List[str]) -> Optional[dict]:
    """Return the first ``{"type": "escalation", ...}`` payload in ``tool_results``.

    The chat surface needs the escalation payload to render the stylist
    handoff card. The payload originates inside an inner specialist's
    ``escalate_to_stylist`` call, so the outer ``support`` / ``search``
    wrapper has to surface it back to chat.py — chat.py only sees the
    wrapper's return value, not the inner Agent's tool results.

    Returns ``None`` if no tool result is a valid escalation envelope.
    """
    for result_str in tool_results:
        try:
            data = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("type") == "escalation":
            return data
    return None


def append_escalation_marker(text: str, payload: dict) -> str:
    """Append the escalation payload as an inline JSON code block.

    Mirrors the products marker convention used by ``_ensure_products_in_output``
    so chat.py's existing JSON-block scanner can detect either kind of
    payload in any tool's stringified result. Idempotent — already-embedded
    markers are preserved.
    """
    marker = f"\n\n```json\n{json.dumps(payload)}\n```"
    if marker.strip() in text:
        return text
    return text + marker
