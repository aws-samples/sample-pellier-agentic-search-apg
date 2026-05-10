"""
Pydantic models for the skills layer.

Two models live here:
  - ``Skill``: the in-memory representation of one SKILL.md file
  - ``RouterDecision``: the output of ``SkillRouter.route()``

Both are serializable so ``RouterDecision`` can be emitted verbatim
over the SSE stream for the Atelier UI.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """
    An in-memory representation of a skill loaded from
    ``/skills/{name}/SKILL.md``.

    The registry loads all skills at boot. ``body`` is the markdown
    content after the frontmatter — this is what gets injected into
    the specialist agent's system prompt when the router decides to
    load the skill for a turn.
    """

    name: str = Field(
        ...,
        description="Canonical name from frontmatter, e.g. 'style-advisor'.",
    )
    description: str = Field(
        ...,
        description="Activation contract — the router's entire input. "
        "The router decides whether to load the skill based only on this string.",
    )
    version: str = Field(
        default="1.0",
        description="Skill version from frontmatter.",
    )
    display_name: Optional[str] = Field(
        default=None,
        description="Optional pretty name for storefront attribution "
        "(e.g. 'Style advisor'). Falls back to ``name.replace('-', ' ')`` "
        "when absent.",
    )

    body: str = Field(
        ...,
        description="Full markdown body after frontmatter — the skill "
        "content injected into the agent's system prompt when loaded.",
    )
    frontmatter: dict = Field(
        default_factory=dict,
        description="Raw parsed frontmatter dict for debugging and "
        "future-proofing against new fields.",
    )
    path: str = Field(
        ...,
        description="Filesystem path to the SKILL.md file.",
    )
    token_estimate: int = Field(
        ...,
        description="Rough token count computed once at load: len(body) // 4.",
    )

    @property
    def display_name_resolved(self) -> str:
        """Return ``display_name`` if set, otherwise derive from hyphen-split."""
        if self.display_name:
            return self.display_name
        return self.name.replace("-", " ")


class RouterDecision(BaseModel):
    """
    Output of ``SkillRouter.route()`` — what loaded, what was considered
    but rejected, timing, and the raw LLM response for debugging.

    Emitted verbatim as an SSE event (type ``skill_routing``) so the
    Atelier UI can render the live activation log and the storefront
    can render the attribution line. The storefront reads
    ``loaded_skills``; the Atelier reads the full object.
    """

    loaded_skills: list[str] = Field(
        default_factory=list,
        description="Skill names the router decided to inject this turn.",
    )
    considered: list[dict] = Field(
        default_factory=list,
        description="Skills the router evaluated but rejected, each as "
        "``{name, reason}``. Used by the Atelier live log; optional.",
    )
    elapsed_ms: int = Field(
        default=0,
        description="Router LLM call duration in milliseconds.",
    )
    raw_response: str = Field(
        default="",
        description="Raw LLM response for debugging parse failures. "
        "Never shown in the UI; logged on error.",
    )
    user_message: str = Field(
        default="",
        description="The message that was routed on, truncated to 500 chars.",
    )

    @classmethod
    def empty(cls, user_message: str = "") -> "RouterDecision":
        """Fallback when the router fails to parse or errors out."""
        return cls(
            loaded_skills=[],
            considered=[],
            elapsed_ms=0,
            raw_response="",
            user_message=user_message[:500],
        )
