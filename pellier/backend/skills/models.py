"""The in-memory representation of one ``SKILL.md`` file.

A plain dataclass, so the managed Runtime bundle that ships this package
reaches no third-party import root the backend's ``pyproject.toml`` does not
declare.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Skill:
    """One skill loaded from ``skills/{name}/SKILL.md``.

    ``body`` is the markdown after the frontmatter: the instructions an agent
    carries in its system prompt (fixed mode) or opens through the loader tool
    (on-demand mode). ``description`` is what the agent reads in on-demand
    mode to decide whether a skill applies.

    Attributes:
        name: Canonical name from frontmatter, e.g. ``the-packing-list``.
        description: What the skill is for, in one line.
        body: Full markdown body after the frontmatter.
        path: Filesystem path to the ``SKILL.md`` file.
        token_estimate: Rough token count, ``len(body) // 4``.
        version: Skill version from frontmatter.
        display_name: Pretty name for the shopper surface; falls back to the
            hyphen-split name.
        frontmatter: Raw parsed frontmatter.
    """

    name: str
    description: str
    body: str
    path: str
    token_estimate: int
    version: str = "1.0"
    display_name: Optional[str] = None
    frontmatter: dict = field(default_factory=dict)

    @property
    def display_name_resolved(self) -> str:
        """``display_name`` when set, else the name with hyphens as spaces."""
        if self.display_name:
            return self.display_name
        return self.name.replace("-", " ")
