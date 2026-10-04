"""Which skills each agent carries, fixed, with no model call.

Skills are procedural memory: checked-in skills plus MCP schemas. Each agent
loads a fixed set into its system prompt at construction. The optional
on-demand mode is progressive disclosure the way Agent Skills define it: the
agent sees only each skill's name and description and opens the full
instructions with an agent-local loader tool when it decides they apply.

The loader comes from the Strands SDK (``strands.vended_plugins.skills``).
It is not a store tool: it reads this repository, is not published to the
Gateway, has no Cedar policy and writes no ``tool_audit`` row. The managed
rail always uses the fixed mapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from strands.vended_plugins.skills import AgentSkills
from strands.vended_plugins.skills import Skill as StrandsSkill

from services.turn_steps import SKILL_LOAD_TOOL, SKILL_MODE_FIXED, SKILL_MODE_ON_DEMAND

from .loader import get_registry
from .models import Skill

SKILL_MODES = (SKILL_MODE_FIXED, SKILL_MODE_ON_DEMAND)

# Tools an agent carries that are not store tools and never reach the ledger.
AGENT_LOCAL_TOOLS = frozenset({SKILL_LOAD_TOOL})

FIXED_SKILLS: Dict[str, tuple[str, ...]] = {
    "shopping": (
        "the-gift-table",
        "the-makers-shelf",
        "the-packing-list",
        "the-proof-counter",
    ),
    "stock": ("the-proof-counter",),
    "support": ("the-care-card", "the-proof-counter"),
}

_SKILL_DELIMITER = (
    "\n\n"
    "=======================================\n"
    "SKILLS - loaded for this agent\n"
    "=======================================\n"
)


def normalize_skill_mode(value: Any) -> str:
    """Coerce a request field to a known mode; the default stays fixed."""
    mode = str(value or "").strip().lower()
    return mode if mode in SKILL_MODES else SKILL_MODE_FIXED


def skill_path(skill: Skill) -> str:
    """The checked-in path, ``skills/<name>/SKILL.md``, in a checkout or the bundle.

    Relative to the directory that holds the ``skills`` folder: the repository
    root in a checkout, the bundle on the managed Runtime. Never a developer's
    absolute path.
    """
    try:
        return (
            Path(skill.path).resolve().relative_to(get_registry().skills_dir.parent).as_posix()
        )
    except ValueError:
        return f"skills/{skill.name}/SKILL.md"


def skills_for(agent_key: str) -> List[Skill]:
    """The fixed skills of one agent, in the mapping's order, missing ones skipped."""
    registry = get_registry()
    loaded: List[Skill] = []
    for name in FIXED_SKILLS.get(agent_key, ()):
        skill = registry.get(name)
        if skill is not None:
            loaded.append(skill)
    return loaded


def inject_skills(base_system_prompt: str, skills: Sequence[Skill]) -> str:
    """Append skill bodies to a system prompt, in name order for stable prompts."""
    if not skills:
        return base_system_prompt
    sections = [base_system_prompt, _SKILL_DELIMITER]
    for skill in sorted(skills, key=lambda s: s.name):
        sections.append(f"\n### SKILL - {skill.name} (v{skill.version})\n")
        sections.append(skill.body.strip())
        sections.append("\n")
    return "".join(sections).rstrip() + "\n"


def on_demand_plugin(agent_key: str) -> AgentSkills:
    """The loader plugin for one agent, carrying only that agent's skills.

    The plugin lists names and descriptions in the system prompt before each
    invocation and registers the ``skills`` tool that returns one skill's
    instructions. A name outside the agent's set, or an unknown name, is
    refused with the available names. The location it prints is the
    checked-in path relative to the repository, never an absolute one.
    """
    sources = [
        StrandsSkill(
            name=skill.name,
            description=skill.description,
            instructions=skill.body,
            path=Path(skill_path(skill)).parent,
        )
        for skill in skills_for(agent_key)
    ]
    return AgentSkills(skills=sources)


def skill_receipt(
    agent_key: str,
    mode: str,
    loaded_on_demand: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    """What the turn receipt says about skills: each name, path and how it loaded."""
    mode = normalize_skill_mode(mode)
    if mode == SKILL_MODE_FIXED:
        return [
            {
                "name": skill.name,
                "display_name": skill.display_name_resolved,
                "path": skill_path(skill),
                "loaded": "fixed",
            }
            for skill in skills_for(agent_key)
        ]
    registry = get_registry()
    receipt: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for name in loaded_on_demand:
        skill = registry.get(name)
        # A skill opened twice was loaded once; the receipt says so once.
        if skill is None or skill.name in seen:
            continue
        seen.add(skill.name)
        receipt.append({
            "name": skill.name,
            "display_name": skill.display_name_resolved,
            "path": skill_path(skill),
            "loaded": "on demand",
        })
    return receipt


def skill_display_names() -> Dict[str, str]:
    """Name to display name, for the step labels of the loader."""
    return {skill.name: skill.display_name_resolved for skill in get_registry().get_all()}


def skill_paths() -> Dict[str, str]:
    """Name to repository path, for the loader's findings."""
    return {skill.name: skill_path(skill) for skill in get_registry().get_all()}


def available_skill_names(agent_key: str) -> Optional[List[str]]:
    """The names an agent may open, or ``None`` for an unknown agent."""
    if agent_key not in FIXED_SKILLS:
        return None
    return [skill.name for skill in skills_for(agent_key)]
