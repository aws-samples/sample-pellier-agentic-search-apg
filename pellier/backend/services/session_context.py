"""Session ContextVar — propagate session_id to inner specialist agents.

Pattern I (agents-as-tools) builds inner specialist Agents inside @tool
wrappers in ``agents/style_advisor.py`` etc. Those wrappers don't take
a session_id parameter and shouldn't (Strands' @tool signature is the
LLM-facing contract). To audit tool calls inside the inner specialist
we need session_id reachable from the wrapper without plumbing it
through every signature, so we mirror the persona/skills pattern in
``services/persona_context.py`` and stash it on a ContextVar.

The outer chat handler sets the var once per request (next to the
persona + skills setup). Inner-agent code can read it to tag
session-scoped work with the correct session_id without plumbing it
through the LLM-facing @tool signature. (The in-process policy/audit
hook that originally consumed this was removed when enforcement moved
to the managed AgentCore Policy engine at the Gateway; the var remains
as the shared session handle.)

Empty default lets unit tests build inner agents without setting up
the full chat scaffold — downstream consumers tolerate a None
session_id by treating it as ``"_anonymous"``.
"""
from __future__ import annotations

import contextvars
from typing import Optional

session_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "pellier_session_id", default=None,
)
