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

import logging
from typing import Any

from services.session_context import session_id_var

logger = logging.getLogger(__name__)


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
