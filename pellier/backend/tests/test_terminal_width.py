"""What the lab scripts print must read well in a laptop's terminal.

Code Editor on a 1440-pixel laptop gives the workshop terminal about 100 columns and 12 lines.
A line longer than the terminal breaks wherever the edge falls, mid-word and under its label.
``workshop_check.wrapped`` is the one way a script prints a labelled sentence: it breaks at
words and keeps later lines under the first.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import workshop_check as check  # noqa: E402

LAPTOP = 100
SENTENCE = ("pgAudit: no exported write to pellier.store_credits in this window; absence does "
            "not prove non-execution")


def test_a_short_line_is_left_alone() -> None:
    assert check.wrapped("  Policy    ", "DENY, determined by credit_limit", LAPTOP) == \
        "  Policy    DENY, determined by credit_limit"


def test_a_long_line_breaks_at_words_under_its_own_text() -> None:
    lines = check.wrapped("  Aurora    ", SENTENCE, LAPTOP).splitlines()
    assert len(lines) == 2
    assert all(len(line) <= LAPTOP for line in lines)
    assert lines[0].startswith("  Aurora    pgAudit: no exported write")
    assert lines[1].startswith(" " * len("  Aurora    ")) and not lines[1][12:].startswith(" ")
    assert " ".join(line[12:] for line in lines) == SENTENCE


def test_a_word_longer_than_the_room_stays_whole() -> None:
    """A key or a command is copied as one piece, so it is never cut to fit."""
    key = "operator-review:2:" + "c" * 90
    lines = check.wrapped("Key   ", f"{key} joins the audit row and the credit.", LAPTOP)
    assert key in lines.splitlines()[0]


@pytest.mark.parametrize("width", [84, 100, 120])
def test_the_terminals_own_width_is_used_when_none_is_given(
        monkeypatch: pytest.MonkeyPatch, width: int) -> None:
    monkeypatch.setattr(check, "terminal_width", lambda: width)
    assert all(len(line) <= width for line in check.wrapped("Next      ", SENTENCE).splitlines())


def test_an_empty_text_keeps_its_label() -> None:
    assert check.wrapped("Observed  ", "", LAPTOP) == "Observed  "
