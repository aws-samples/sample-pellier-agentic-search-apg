"""Shared escalation helpers for inner specialist agents (Pattern I).

Pattern I (agents-as-tools) builds a fresh inner specialist Agent each time
the orchestrator invokes one of the @tool wrappers in ``agents/search_agent.py``,
``agents/personalization_agent.py``, etc. Those inner specialists can emit an
``escalate_to_human`` payload that the outer wrapper has to surface back to
``services/chat.py`` so the chat UI can render the stylist handoff card.

This module surfaces escalation payloads and product envelopes across that
boundary. These helpers are not policy-related; policy enforcement lives in
the managed AgentCore Policy engine at the Gateway (Cedar, ENFORCE mode), not
in any in-process hook.
"""
from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar, Token
from typing import List, Optional

from services.product_envelope import select_products_for_reply as select_products_for_reply

logger = logging.getLogger(__name__)

product_collector_var: ContextVar[Optional[List[dict]]] = ContextVar(
    "pellier_product_collector",
    default=None,
)
specialist_reply_collector_var: ContextVar[Optional[List[str]]] = ContextVar(
    "pellier_specialist_reply_collector",
    default=None,
)


def set_product_collector(collector: List[dict]) -> Token:
    """Bind a server-owned product collector to the current agent turn."""
    return product_collector_var.set(collector)


def reset_product_collector(token: Token) -> None:
    """Restore the product collector that preceded the current turn."""
    product_collector_var.reset(token)


def set_specialist_reply_collector(collector: List[str]) -> Token:
    """Bind a collector for completed specialist prose in the current turn."""
    return specialist_reply_collector_var.set(collector)


def reset_specialist_reply_collector(token: Token) -> None:
    """Restore the specialist reply collector that preceded this turn."""
    specialist_reply_collector_var.reset(token)


def forward_or_append_products(text: str, products: List[dict]) -> str:
    """Forward products out-of-band, with a marker fallback for direct calls.

    The streamed chat path binds a collector before invoking Pattern I. This
    keeps retrieval data out of the outer router's model context while still
    preserving the historical fenced-JSON contract for standalone specialist
    calls that do not bind a collector.
    """
    if not products:
        return text

    collector = product_collector_var.get()
    if collector is not None:
        collector.extend(product for product in products if isinstance(product, dict))
        cleaned_text = re.sub(
            r"\n*```json\s*\[.*?\]\s*```",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        ).rstrip()
        reply_collector = specialist_reply_collector_var.get()
        if reply_collector is not None and cleaned_text:
            reply_collector.append(cleaned_text)
        return cleaned_text

    if re.search(r"```json\s*\[", text, re.IGNORECASE):
        return text
    return text + f"\n\n```json\n{json.dumps(products)}\n```"


def extract_escalation_payload(tool_results: List[str]) -> Optional[dict]:
    """Return the first ``{"type": "escalation", ...}`` payload in ``tool_results``.

    The chat surface needs the escalation payload to render the stylist
    handoff card. The payload originates inside an inner specialist's
    ``escalate_to_human`` call, so the outer ``support`` / ``search``
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
