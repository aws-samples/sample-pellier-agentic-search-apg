"""Runtime skills: the procedural memory each agent carries.

Skills are checked-in ``skills/*/SKILL.md`` files. The registry reads them
once at boot; ``assignments`` says which agent carries which, injects them
into a system prompt, and builds the optional on-demand loader. There is no
model call anywhere in this package.
"""

from __future__ import annotations

from .assignments import (
    AGENT_LOCAL_TOOLS,
    FIXED_SKILLS,
    SKILL_MODE_FIXED,
    SKILL_MODE_ON_DEMAND,
    SKILL_MODES,
    available_skill_names,
    inject_skills,
    normalize_skill_mode,
    on_demand_plugin,
    skill_display_names,
    skill_path,
    skill_paths,
    skill_receipt,
    skills_for,
)
from .loader import get_registry, load_registry
from .models import Skill
from .registry import SkillRegistry

__all__ = [
    "AGENT_LOCAL_TOOLS",
    "FIXED_SKILLS",
    "SKILL_MODE_FIXED",
    "SKILL_MODE_ON_DEMAND",
    "SKILL_MODES",
    "Skill",
    "SkillRegistry",
    "available_skill_names",
    "get_registry",
    "inject_skills",
    "load_registry",
    "normalize_skill_mode",
    "on_demand_plugin",
    "skill_display_names",
    "skill_path",
    "skill_paths",
    "skill_receipt",
    "skills_for",
]
