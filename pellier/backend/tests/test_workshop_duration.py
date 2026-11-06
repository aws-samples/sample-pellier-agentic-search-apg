"""Every statement of the workshop's length agrees with its schedule.

CLAUDE.md's schedule paragraph is the one source: a total, and the blocks it splits into. The
blocks must add up to the total, the four labs' minutes must match workshop/story-arc.json, and
every "<N>-minute workshop" or "<N>-minute session" in a tracked or new file must say that total.
A Workshop Studio content scan found a template still giving the hands-on clock as the workshop's
length after the schedule became 120 minutes (2026-11-06); nothing in the repository compared them.
New files count too, so a claim is caught before its first commit.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCHEDULE_TOTAL = re.compile(r"The schedule is (\d+) minutes\.")
SCHEDULE_BLOCKS = re.compile(
    r"The opening block takes (\d+):.*?Lab 1 takes (\d+), Lab 2 (\d+), Before Lab 3 \(.*?\) (\d+), "
    r"Lab 3 (\d+), Lab 4 (\d+) and the\s+Wrap-up (\d+)\.",
    re.S,
)
LENGTH_CLAIM = re.compile(r"\b(\d{2,3})[- ]minute (?:workshop|session)\b", re.I)
SKIPPED = ("docs/superpowers/",)   # dated design history, not current claims


def _schedule() -> tuple[int, list[int]]:
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    total = SCHEDULE_TOTAL.search(text)
    blocks = SCHEDULE_BLOCKS.search(text)
    assert total and blocks, "CLAUDE.md lost its schedule paragraph"
    return int(total.group(1)), [int(n) for n in blocks.groups()]


def test_the_schedule_blocks_add_up_to_its_total() -> None:
    total, blocks = _schedule()
    assert sum(blocks) == total, f"schedule blocks {blocks} add up to {sum(blocks)}, not {total}"


def test_the_labs_minutes_match_the_story_arc() -> None:
    _, blocks = _schedule()
    lab1, lab2, lab3, lab4 = blocks[1], blocks[2], blocks[4], blocks[5]
    arc = json.loads((REPO / "workshop" / "story-arc.json").read_text(encoding="utf-8"))
    assert [lab["minutes"] for lab in arc["labs"]] == [lab1, lab2, lab3, lab4]


def test_every_stated_length_is_the_schedule_total() -> None:
    total, _ = _schedule()
    listing = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    tracked = subprocess.run(listing, cwd=REPO, capture_output=True,
                             check=True).stdout.decode().split("\0")
    wrong = []
    for name in tracked:
        if not name or name.startswith(SKIPPED):
            continue
        try:
            text = (REPO / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in LENGTH_CLAIM.finditer(text):
            if int(match.group(1)) != total:
                line = text.count("\n", 0, match.start()) + 1
                wrong.append(f"{name}:{line}: {match.group(0)!r}")
    assert not wrong, f"lengths that are not the {total}-minute schedule: {wrong}"
