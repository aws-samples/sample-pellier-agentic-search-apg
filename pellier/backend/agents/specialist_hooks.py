"""Shared hook attachment for inner specialist agents (Pattern I).

Pattern I (agents-as-tools) builds a fresh inner specialist Agent each time
the orchestrator invokes one of the @tool wrappers in ``agents/style_advisor.py``,
``agents/curator.py``, etc. The outer orchestrator already has
``PolicyEnforcementHook`` registered (see ``services/chat.py:1869``), but the
inner specialist is a separate Agent and its own tool calls (``find_pieces``,
``style_match``, …) only show up in ``pellier.tool_audit`` if the hook is
attached to it as well.

This helper reads the current request's session_id from ``session_id_var``
(set once in the outer chat handler) and registers the policy provider on the
inner agent. The wrappers don't take session_id as a parameter — Strands'
``@tool`` signature is the LLM-facing contract — so the ContextVar is the
clean way to thread it through.

Best-effort: if Strands isn't importable or the agent has no hook surface, we
log and move on. Audit is observability — it should never block a tool call.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from services.session_context import session_id_var

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


def attach_policy_hook(agent: Any) -> None:
    """Attach ``PolicyEnforcementHook`` to an inner specialist agent.

    Mirrors the registration shape used on the outer orchestrator at
    ``services/chat.py:1869-1882``: prefer the lower-level ``hooks.add_hook``
    so the provider's ``register_hooks`` runs once and wires up every
    callback; fall back to ``agent.add_hook`` with the bound
    ``_on_before_tool`` for shims that only support callback-style hooks.
    """
    try:
        from services.policy_hook import PolicyEnforcementHook
    except Exception as exc:  # pragma: no cover — import-time failure
        logger.warning("PolicyEnforcementHook import failed: %s", exc)
        return

    session_id = session_id_var.get()
    provider = PolicyEnforcementHook(session_id=session_id)

    try:
        hooks_registry = getattr(agent, "hooks", None)
        if hooks_registry is not None and hasattr(hooks_registry, "add_hook"):
            hooks_registry.add_hook(provider)
        else:
            agent.add_hook(provider._on_before_tool)
    except Exception as exc:
        logger.warning("Inner specialist hook attach failed: %s", exc)
