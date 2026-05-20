#!/usr/bin/env python3
"""Sync Atelier `skills.json` fixture from `/skills/*/SKILL.md`.

This keeps frontend fixture copy aligned with the runtime skill registry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
FIXTURE_PATH = REPO_ROOT / "pellier" / "frontend" / "src" / "atelier" / "fixtures" / "skills.json"
sys.path.insert(0, str(REPO_ROOT / "pellier" / "backend"))

from skills.registry import _parse_frontmatter

# Workshop-facing metadata that is not stored in SKILL.md frontmatter.
SKILL_UI_META: dict[str, dict[str, object]] = {
    "the-packing-list": {
        "signals": ["linen", "travel", "pack flat", "natural fibers", "Goa", "weekend"],
        "loadedBy": ["Curator", "Style Advisor"],
    },
    "the-gift-table": {
        "signals": ["gift", "birthday", "housewarming", "milestone", "wrap", "thoughtful"],
        "loadedBy": ["Curator", "Style Advisor"],
    },
    "the-makers-shelf": {
        "signals": ["hand-thrown", "ceramic", "kiln", "slow", "ritual", "patina"],
        "loadedBy": ["Curator", "Experience Guide"],
    },
}

PERSONA_DISPLAY = {
    "marco": "Marco",
    "anna": "Anna",
    "theo": "Theo",
}


def load_skill(skill_file: Path) -> dict[str, object]:
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text)

    name = str(frontmatter.get("name", "")).strip()
    if not name:
        raise ValueError(f"Missing `name` in {skill_file}")

    persona = str(frontmatter.get("persona", "")).strip().lower()
    if persona not in PERSONA_DISPLAY:
        raise ValueError(f"Unsupported persona '{persona}' in {skill_file}")

    ui_meta = SKILL_UI_META.get(name)
    if not ui_meta:
        raise ValueError(f"Missing fixture UI metadata for skill '{name}'")

    return {
        "name": name,
        "displayName": str(frontmatter.get("display_name") or name),
        "persona": persona,
        "personaDisplayName": PERSONA_DISPLAY[persona],
        "description": str(frontmatter.get("description") or ""),
        "version": str(frontmatter.get("version") or "1.0"),
        "loadedBy": ui_meta["loadedBy"],
        "body": body.strip(),
        "signals": ui_meta["signals"],
        "status": "live",
    }


def main() -> None:
    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skill_files:
        raise SystemExit(f"No skills found in {SKILLS_DIR}")

    skills = [load_skill(path) for path in skill_files]
    skills.sort(key=lambda s: str(s["name"]))

    FIXTURE_PATH.write_text(json.dumps(skills, indent=2) + "\n", encoding="utf-8")
    print(f"Synced {len(skills)} skills to {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
