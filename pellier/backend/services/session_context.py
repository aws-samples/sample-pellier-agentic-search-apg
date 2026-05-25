"""Session ContextVar — propagate session_id to inner specialist agents.

Pattern I (agents-as-tools) builds inner specialist Agents inside @tool
wrappers in ``agents/style_advisor.py`` etc. Those wrappers don't take
a session_id parameter and shouldn't (Strands' @tool signature is the
LLM-facing contract). To audit tool calls inside the inner specialist
we need session_id reachable from the wrapper without plumbing it
through every signature, so we mirror the persona/skills pattern in
``services/persona_context.py`` and stash it on a ContextVar.

The outer chat handler sets the var once per request (next to the
persona + skills setup). Wrappers read it when attaching the
PolicyEnforcementHook so the inner specialist's tool calls show up
in pellier.tool_audit with the correct session_id.

Empty default lets unit tests build inner agents without setting up
the full chat scaffold — ``record_allow`` already tolerates a None
session_id by writing ``"_anonymous"``.
"""
from __future__ import annotations

import contextvars
from typing import Optional

session_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "pellier_session_id", default=None,
)
