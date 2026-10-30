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
        "Can search match intent and keep every shopper limit?",
        "Can every stock answer be backed by a warehouse record?",
        "Can each shopper access only their own records on AgentCore?",
        "Can approved credits stay within limits and be written once?",
    ]


@pytest.mark.parametrize("name", COPIES)
def test_every_copy_asks_the_same_questions_and_calls_them_questions(name: str) -> None:
    text = (REPO / name).read_text(encoding="utf-8")
    assert all(f'"{question}"' in text for question in QUESTIONS), name
    assert "Leadership question" in text
    assert "worry" not in text.lower(), f"{name} still says worry"
