"""A fixed skill that fails to load is a startup error, not a silently thinner agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from skills.assignments import FIXED_SKILLS
from skills.loader import load_registry

REPO_SKILLS = Path(__file__).resolve().parents[3] / "skills"


@pytest.fixture(autouse=True)
def keep_global_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """``load_registry`` caches a process-global; leave the shared one untouched."""
    import skills.loader as loader

    monkeypatch.setattr(loader, "_registry", loader._registry)


def _copy_skills(target: Path, *, skip: str = "", break_one: str = "") -> None:
    for folder in REPO_SKILLS.glob("*/SKILL.md"):
        name = folder.parent.name
        if name == skip:
            continue
        out = target / name
        out.mkdir()
        text = folder.read_text(encoding="utf-8")
        if name == break_one:
            text = "no frontmatter at all\n"
        (out / "SKILL.md").write_text(text, encoding="utf-8")


def test_the_checked_in_skills_satisfy_every_fixed_assignment(tmp_path: Path) -> None:
    _copy_skills(tmp_path)
    registry = load_registry(tmp_path)
    needed = {name for names in FIXED_SKILLS.values() for name in names}
    assert needed <= {skill.name for skill in registry.get_all()}


def test_a_skill_that_fails_to_parse_stops_startup_naming_it(tmp_path: Path) -> None:
    _copy_skills(tmp_path, break_one="evidence")
    with pytest.raises(RuntimeError, match="evidence"):
        load_registry(tmp_path)


def test_a_missing_skills_directory_stops_startup(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="care-and-returns"):
        load_registry(tmp_path / "absent")
