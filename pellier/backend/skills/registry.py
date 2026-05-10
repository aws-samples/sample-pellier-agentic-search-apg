"""
SkillRegistry — in-memory store of skills loaded at application boot.

The registry scans a configurable directory (default: ``/skills/`` at
project root) for ``SKILL.md`` files, parses each one's YAML
frontmatter, and holds the resulting ``Skill`` objects in memory.

Per-request cost is zero — filesystem reads happen once at startup.
Hot reload (``uvicorn --reload``) re-runs the scan because it
re-imports the module; production boots read once and stay.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .models import Skill

logger = logging.getLogger(__name__)

# Frontmatter delimiter — three dashes on their own line, top of file.
_FM_DELIM = re.compile(r"^---\s*$", re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse a minimal YAML-style frontmatter block out of a markdown file.

    Supports the subset used by our SKILL.md files:
      - ``key: value`` pairs on their own lines
      - Values may be unquoted strings, numbers, or ``true``/``false``
      - Long description values wrapped on one line are fine

    Returns ``(frontmatter_dict, body_without_frontmatter)``. If the
    file doesn't start with ``---``, returns ``({}, text)``.

    Intentionally small — we don't want a YAML dependency just for
    four-field frontmatters. If we ever ship a skill with nested
    frontmatter, we'll add ``python-frontmatter`` then.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text

    # Find the closing delimiter after the opening one
    lines = stripped.splitlines(keepends=True)
    if not _FM_DELIM.match(lines[0].rstrip("\n")):
        return {}, text

    close_idx: Optional[int] = None
    for i, line in enumerate(lines[1:], start=1):
        if _FM_DELIM.match(line.rstrip("\n")):
            close_idx = i
            break

    if close_idx is None:
        # No closing delimiter — treat as body
        return {}, text

    fm_lines = lines[1:close_idx]
    body = "".join(lines[close_idx + 1:])

    fm: dict = {}
    for raw_line in fm_lines:
        line = raw_line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Strip optional surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        # Minimal type coercion
        if value.lower() == "true":
            fm[key] = True
        elif value.lower() == "false":
            fm[key] = False
        elif value.lower() in ("null", "~"):
            fm[key] = None
        else:
            # Keep versions and numeric-looking values as strings —
            # frontmatter semantics are easier to reason about that way.
            fm[key] = value

    return fm, body


class SkillRegistry:
    """
    In-memory store of skills. Scan once at startup, serve forever.
    """

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir.resolve()
        self._skills: dict[str, Skill] = {}

    def load(self) -> list[Skill]:
        """
        Scan ``skills_dir`` for ``*/SKILL.md`` files and populate the
        registry. Returns the list of loaded skills.

        Silently skips folders that are missing SKILL.md or fail to
        parse — we don't want a typo in one skill to bring the app
        down. Parse errors are logged at WARNING so workshop
        participants debugging a new skill can see what went wrong.
        """
        self._skills.clear()

        if not self._skills_dir.exists():
            logger.warning(
                "Skills directory %s does not exist — loading 0 skills",
                self._skills_dir,
            )
            return []

        for skill_file in sorted(self._skills_dir.glob("*/SKILL.md")):
            try:
                skill = self._load_one(skill_file)
                if skill.name in self._skills:
                    logger.warning(
                        "Duplicate skill name '%s' at %s — keeping first",
                        skill.name,
                        skill_file,
                    )
                    continue
                self._skills[skill.name] = skill
            except Exception as exc:
                logger.warning(
                    "Failed to load skill at %s: %s", skill_file, exc
                )

        return list(self._skills.values())

    def _load_one(self, skill_file: Path) -> Skill:
        """Parse a single SKILL.md into a ``Skill`` object."""
        text = skill_file.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(text)

        name = frontmatter.get("name")
        description = frontmatter.get("description")
        if not name:
            raise ValueError(f"SKILL.md at {skill_file} missing 'name' in frontmatter")
        if not description:
            raise ValueError(f"SKILL.md at {skill_file} missing 'description' in frontmatter")

        return Skill(
            name=name,
            description=description,
            version=str(frontmatter.get("version", "1.0")),
            display_name=frontmatter.get("display_name"),
            body=body.strip(),
            frontmatter=frontmatter,
            path=str(skill_file),
            token_estimate=max(1, len(body) // 4),
        )

    def get_all(self) -> list[Skill]:
        """Return all loaded skills, sorted by name for determinism."""
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get(self, name: str) -> Optional[Skill]:
        """Look up a skill by canonical name; returns None if absent."""
        return self._skills.get(name)

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    @property
    def skills_dir(self) -> Path:
        return self._skills_dir
