"""
Per-request persona context — a ``ContextVar`` that carries the
active shopper's LTM preamble through the agent pipeline.

Problem this solves: the chat pipeline builds a ``PERSONA CONTEXT``
block (the shopper's name, known-facts, and past-order list) and
prepends it to the orchestrator's ``full_message``. But when the
orchestrator (Haiku, dispatcher) routes to a specialist via the
Strands "Agents as Tools" pattern, it passes only the ``query``
argument to the ``@tool`` function — and Haiku's paraphrase of the
query frequently strips the preamble. The specialist then answers
without ever seeing the shopper's history.

The fix mirrors the ``skills/context.py`` pattern: the chat pipeline
``.set()``s the preamble in a ContextVar before invoking the
orchestrator, the recommendation specialist's factory reads it when
building its system prompt, and the pipeline ``.reset(token)`` s
afterward in a ``finally`` block so the preamble never leaks across
requests.

ContextVars are thread-safe and asyncio-aware. Strands runs the
orchestrator in a background thread via ``asyncio.to_thread`` and
the value set by the parent task propagates into the child thread
as expected for ``copy_context`` / ``run_in_executor`` flows.
"""
from __future__ import annotations

import contextvars
from typing import Optional

# Default is an empty string so callers that haven't set it (tests,
# anonymous sessions, direct specialist invocations) still get
# deterministic behavior — no preamble injected.
persona_preamble_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "pellier_persona_preamble", default=""
)


def set_persona_preamble(preamble: str) -> contextvars.Token:
    """Set the active persona preamble for this turn. Returns a ``Token``
    the caller MUST pass to ``persona_preamble_var.reset(token)`` in a
    ``finally`` block so the preamble doesn't leak into the next request.

    Convention:

        token = set_persona_preamble(preamble)
        try:
            orchestrator(message)
        finally:
            persona_preamble_var.reset(token)
    """
    return persona_preamble_var.set(preamble or "")


def get_persona_preamble() -> str:
    """Return the currently-set persona preamble, or an empty string."""
    return persona_preamble_var.get()


# Clear delimiter between the specialist's base system prompt and the
# persona preamble. The delimiter is scannable in the final rendered
# prompt so prompt debugging is easier.
_PERSONA_DELIMITER = "\n\n<persona-preamble source=\"aurora-ltm\">\n"
_PERSONA_CLOSER = "\n</persona-preamble>"


def inject_persona_preamble(base_prompt: str, preamble: Optional[str] = None) -> str:
    """Append the current persona preamble to a specialist's base system
    prompt. No-op when no persona is active (anonymous sessions).

    If ``preamble`` is omitted, reads from the ContextVar. The explicit
    parameter path exists for tests and for cases where the caller
    already has the preamble in hand.
    """
    body = preamble if preamble is not None else get_persona_preamble()
    if not body.strip():
        return base_prompt
    return f"{base_prompt}{_PERSONA_DELIMITER}{body.strip()}{_PERSONA_CLOSER}"
