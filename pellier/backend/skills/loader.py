"""
Startup loader and accessor for the SkillRegistry.

The registry is a process-global singleton — skills are read from
disk once at boot, then served from memory for the lifetime of the
process. ``load_registry()`` is called from ``app.py`` during FastAPI
lifespan startup; ``get_registry()`` is a FastAPI-friendly accessor
any route or service can use.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .registry import SkillRegistry

logger = logging.getLogger(__name__)

# This package: pellier/backend/skills in a checkout, or the bundle's own
# ``skills`` directory on the managed Runtime.
_PACKAGE_DIR = Path(__file__).resolve().parent

_registry: Optional[SkillRegistry] = None


def _default_skills_dir() -> Path:
    """Where the ``*/SKILL.md`` files live for this layout.

    In a checkout they sit beside ``pellier/`` at the repository root. The
    Runtime bundle has no repository root, so the renderer stages them inside
    this package, and the package directory is the fallback.
    """
    try:
        checkout = _PACKAGE_DIR.parents[2] / "skills"
    except IndexError:
        return _PACKAGE_DIR
    if any(checkout.glob("*/SKILL.md")):
        return checkout
    return _PACKAGE_DIR


def load_registry(skills_dir: Optional[Path] = None) -> SkillRegistry:
    """
    Instantiate the skill registry, load all skills from disk, and
    cache the result in a module-global. Idempotent — subsequent
    calls return the cached registry unless ``skills_dir`` changes.

    Logs a summary line at INFO so the operator can confirm which
    skills boot picked up and at what token cost:

        ✅ Loaded 5 skills from /path/to/skills: the-care-card (360t), the-gift-table (380t), ...
    """
    global _registry

    resolved = (skills_dir or _env_skills_dir() or _default_skills_dir()).resolve()

    # Re-scan if the directory changed (mostly useful in tests).
    if _registry is not None and _registry.skills_dir == resolved:
        return _registry

    registry = SkillRegistry(resolved)
    skills = registry.load()

    if skills:
        summary = ", ".join(
            f"{s.name} ({s.token_estimate}t)" for s in registry.get_all()
        )
        logger.info(
            "✅ Loaded %d skill%s from %s: %s",
            len(skills),
            "" if len(skills) == 1 else "s",
            resolved,
            summary,
        )
    else:
        logger.info(
            "ℹ️ No skills loaded from %s (directory empty or missing)",
            resolved,
        )

    _registry = registry
    return registry


def get_registry() -> SkillRegistry:
    """
    Return the loaded registry. Lazily initializes on first access
    so tests and scripts that import the registry without going
    through the FastAPI lifespan still work.
    """
    global _registry
    if _registry is None:
        _registry = load_registry()
    return _registry


def _env_skills_dir() -> Optional[Path]:
    """Allow ``PELLIER_SKILLS_DIR`` env var to override the default path."""
    value = os.environ.get("PELLIER_SKILLS_DIR")
    return Path(value) if value else None
