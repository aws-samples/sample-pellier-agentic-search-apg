"""The in-memory representation of one ``SKILL.md`` file."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """One skill loaded from ``skills/{name}/SKILL.md``.

    ``body`` is the markdown after the frontmatter: the instructions an agent
    carries in its system prompt (fixed mode) or opens through the loader tool
    (on-demand mode). ``description`` is what the agent reads in on-demand
    mode to decide whether a skill applies.
    """

    name: str = Field(..., description="Canonical name from frontmatter, e.g. 'the-packing-list'.")
    description: str = Field(..., description="What the skill is for, in one line.")
    version: str = Field(default="1.0", description="Skill version from frontmatter.")
    display_name: Optional[str] = Field(
        default=None,
        description="Pretty name for the shopper surface; falls back to the hyphen-split name.",
    )
    body: str = Field(..., description="Full markdown body after the frontmatter.")
    frontmatter: dict = Field(default_factory=dict, description="Raw parsed frontmatter.")
    path: str = Field(..., description="Filesystem path to the SKILL.md file.")
    token_estimate: int = Field(..., description="Rough token count: len(body) // 4.")

    @property
    def display_name_resolved(self) -> str:
        """``display_name`` when set, else the name with hyphens as spaces."""
        if self.display_name:
            return self.display_name
        return self.name.replace("-", " ")
