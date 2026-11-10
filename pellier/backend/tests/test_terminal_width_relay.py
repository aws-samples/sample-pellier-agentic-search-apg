"""A catch-up relays its children's output, so the children must learn the terminal's width.

``lab_run.py finish`` (the guide's Running behind command) and ``reset`` run each step as a
child process and pass its lines along. The child writes to a pipe, not a terminal, so it
cannot measure the screen: a check drew its boxes 120 columns wide inside a 100-column
terminal, and the participant deploy printed the long form it keeps for logs. The parent now
tells the child how wide the terminal is.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import lab_reset  # noqa: E402
import lab_run  # noqa: E402
import provision_agentcore_end_to_end as deploy  # noqa: E402
import workshop_check as check  # noqa: E402

SAYS_WIDTH = [sys.executable, "-c",
              f"import os; print(os.environ.get('{check.RELAYED_COLUMNS_ENV}'))"]


@pytest.fixture
def laptop_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """This process writes to a 100-column terminal."""
    monkeypatch.delenv(check.RELAYED_COLUMNS_ENV, raising=False)
    monkeypatch.setattr(check, "_is_terminal", lambda stream: True)
    monkeypatch.setattr(check.shutil, "get_terminal_size",
                        lambda fallback=(80, 24): os.terminal_size((100, 12)))


def test_a_relayed_child_is_told_the_terminals_width(laptop_terminal: None, capfd) -> None:
    assert lab_reset.relay(SAYS_WIDTH, cwd=REPO, timeout=30) == 0
    assert capfd.readouterr().out.strip() == "100"


def test_a_child_is_told_nothing_when_no_one_is_watching(
        monkeypatch: pytest.MonkeyPatch, capfd) -> None:
    """Output that goes to a log or a pipe keeps the shape it has always had."""
    monkeypatch.delenv(check.RELAYED_COLUMNS_ENV, raising=False)
    monkeypatch.setattr(check, "_is_terminal", lambda stream: False)
    assert lab_reset.relay(SAYS_WIDTH, cwd=REPO, timeout=30) == 0
    assert capfd.readouterr().out.strip() == "None"


def test_a_width_already_passed_down_is_passed_on(monkeypatch: pytest.MonkeyPatch, capfd) -> None:
    """A relayed command that relays in turn is itself writing to a pipe."""
    monkeypatch.setenv(check.RELAYED_COLUMNS_ENV, "100")
    monkeypatch.setattr(check, "_is_terminal", lambda stream: False)
    assert lab_reset.relay(SAYS_WIDTH, cwd=REPO, timeout=30) == 0
    assert capfd.readouterr().out.strip() == "100"


@pytest.mark.parametrize("told, expected", [("100", 99), ("84", 83), ("400", check.WIDTH)])
def test_a_relayed_child_fits_what_it_prints_to_that_width(
        monkeypatch: pytest.MonkeyPatch, told: str, expected: int) -> None:
    monkeypatch.setenv(check.RELAYED_COLUMNS_ENV, told)
    assert check.terminal_width() == expected


@pytest.mark.parametrize("told", ["", "wide", "0", "-5", "\u00b2", "1e2"])
def test_a_width_that_is_not_a_number_is_ignored(
        monkeypatch: pytest.MonkeyPatch, told: str) -> None:
    monkeypatch.delenv(check.RELAYED_COLUMNS_ENV, raising=False)
    measured = check.terminal_width()
    monkeypatch.setenv(check.RELAYED_COLUMNS_ENV, told)
    assert check.terminal_width() == measured


def test_a_relayed_participant_deploy_prints_for_a_person(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inside a catch-up the deploy writes to a pipe, and a person still reads it."""
    monkeypatch.setitem(deploy._PARTICIPANT_VIEW, "on", True)
    monkeypatch.setattr(deploy.sys.stdout, "isatty", lambda: False, raising=False)
    monkeypatch.delenv(check.RELAYED_COLUMNS_ENV, raising=False)
    assert not deploy._fitted_to_terminal()
    monkeypatch.setenv(check.RELAYED_COLUMNS_ENV, "100")
    assert deploy._fitted_to_terminal()
    monkeypatch.setitem(deploy._PARTICIPANT_VIEW, "on", False)
    assert not deploy._fitted_to_terminal(), "only the participant deploy changes"


def test_the_catch_up_echoes_the_deploy_as_the_guide_writes_it() -> None:
    """The catch-up printed the deploy with the repository's whole path, 127 columns in a
    100-column terminal. It runs from that folder, so "$PWD" is the same command, the one the
    guide gives and a participant can copy."""
    repo = Path("/workshop/sample-pellier-agentic-search-apg")
    shown = lab_run.shown_command(lab_run._deploy(repo), repo)
    assert shown == lab_run.DEPLOY
    assert len(f"  $ {shown}") <= 100
    assert lab_run.shown_command(["psql", "-f", "workshop/lab-4-absence.sql"], repo) == \
        "psql -f workshop/lab-4-absence.sql"
