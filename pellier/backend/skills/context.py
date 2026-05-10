"""
Per-request skill context — a ``ContextVar`` that carries the
currently-loaded skills through the agent pipeline.

The orchestrator (Haiku, dispatcher) runs in a background thread and
constructs its specialist agents inside ``@tool``-decorated functions.
Those specialists need access to the skills the router decided to
load for this turn, but we don't want to plumb ``loaded_skills`` as
a parameter through every function signature.

A ``ContextVar`` solves this cleanly: the chat pipeline ``.set()``s
the skills before invoking the orchestrator, specialist agent
factories read the current value when building their system prompt,
and the pipeline ``.reset(token)`` s afterward in a ``finally`` block
so a mid-stream error never leaks skills to the next request.

Important: ContextVars are thread-safe and asyncio-aware. Strands
runs the orchestrator in a background thread via ``asyncio.to_thread``
and the value set by the parent task propagates into the child
thread as expected for ``copy_context`` / ``run_in_executor`` flows.
"""
from __future__ import annotations

import contextvars
from typing import Optional

from .models import Skill

# The ContextVar itself. Default is an empty tuple so callers that
# haven't set it (e.g., unit tests, direct specialist invocations)
# still get deterministic behavior — zero skills loaded.
loaded_skills_var: contextvars.ContextVar[tuple[Skill, ...]] = (
    contextvars.ContextVar("pellier_loaded_skills", default=())
)


def set_loaded_skills(skills: list[Skill]) -> contextvars.Token:
    """
    Set the currently-loaded skills for this turn. Returns a ``Token``
    that the caller MUST pass to ``loaded_skills_var.reset(token)`` in
    a ``finally`` block to prevent skill leakage across requests.

    Convention:

        token = set_loaded_skills(decision_skills)
        try:
            orchestrator(message)
        finally:
            loaded_skills_var.reset(token)
    """
    return loaded_skills_var.set(tuple(skills))


def get_loaded_skills() -> tuple[Skill, ...]:
    """Return the currently-loaded skills, or an empty tuple."""
    return loaded_skills_var.get()


# Clear delimiter between the agent's base system prompt and the
# skill bodies injected for this turn. The delimiter itself is
# editorial — a participant reading the constructed prompt in a
# debugger can immediately see what's base vs what's injected.
_SKILL_DELIMITER = (
    "\n\n"
    "=======================================\n"
    "SKILLS · loaded for this turn only\n"
    "=======================================\n"
)


def inject_skills(
    base_system_prompt: str,
    loaded_skills: Optional[list[Skill]] = None,
) -> str:
    """
    Append loaded skill bodies to a specialist agent's system prompt.

    Called from specialist agent factories (recommendation, search,
    support, etc.) right before constructing their Strands Agent.
    The orchestrator does NOT call this — skills inject into the
    reasoning specialists that compose the editorial reply, not the
    Haiku dispatcher.

    If ``loaded_skills`` is omitted, reads from the ContextVar. The
    ContextVar path is the normal one; the explicit-param path exists
    for tests and for cases where the caller already has the list.

    Skills are appended in alphabetical order by name so a given
    combination of skills always produces a byte-identical system
    prompt — important for caching and for debugging.
    """
    skills = loaded_skills if loaded_skills is not None else list(get_loaded_skills())
    if not skills:
        return base_system_prompt

    ordered = sorted(skills, key=lambda s: s.name)
    sections = [base_system_prompt, _SKILL_DELIMITER]
    for skill in ordered:
        sections.append(f"\n### SKILL · {skill.name} (v{skill.version})\n")
        sections.append(skill.body.strip())
        sections.append("\n")
    return "".join(sections).rstrip() + "\n"
