"""Each lab answers one leadership question, worded once in workshop/story-arc.json.

The arc keeps its ``worry`` key, because the Workshop Studio validator reads it; its values
are the four questions. The repository's own copies must say the same thing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
QUESTIONS = [lab["worry"] for lab in
             json.loads((REPO / "workshop" / "story-arc.json").read_text())["labs"]]
COPIES = ("README.md", "WORKSHOP.md", "docs/WORKSHOP-STORY-ARC.md")


def test_the_arc_holds_four_questions() -> None:
    assert QUESTIONS == [
        "Can we deliver relevant recommendations while preserving every customer requirement?",
        "Can we rely on the assistant's answers when making commitments to customers?",
        "When we deploy the agent on AgentCore, how do we ensure every request carries the "
        "right identity and permissions?",
        "Can the assistant act within approved limits, with a record of exactly what changed?",
    ]


@pytest.mark.parametrize("name", COPIES)
def test_every_copy_asks_the_same_questions_and_calls_them_questions(name: str) -> None:
    text = (REPO / name).read_text(encoding="utf-8")
    assert all(f'"{question}"' in text for question in QUESTIONS), name
    assert "Leadership question" in text
    assert "worry" not in text.lower(), f"{name} still says worry"
