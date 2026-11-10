"""A participant deploy's lines fit the terminal; every other mode prints what it always did.

Drives the formatters with a stubbed terminal: no AWS, no deploy.
"""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROVISIONER_PATH = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pellier_provisioner_width", PROVISIONER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provisioner = _load()

INVOKE = [
    "invoke", "--runtime", "pellier_orchestrator",
    "--session-id", "builders-smoke-" + "a1" * 16,
    "--bearer-token", "SECRET.JWT.VALUE",
    "--prompt", "Smoke test: find one linen item under 150. Do not mutate data.", "--json",
]


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch):
    def at(width: int, participant: bool = True, tty: bool = True) -> None:
        monkeypatch.setitem(provisioner._PARTICIPANT_VIEW, "on", participant)
        monkeypatch.setattr(provisioner.sys, "stdout", _Tty() if tty else io.StringIO())
        monkeypatch.setattr(provisioner.workshop_check, "terminal_width", lambda: width)
    return at


@pytest.mark.parametrize("width", [100, 84])
def test_the_echoed_invoke_fits_and_keeps_the_token_redacted(terminal, width: int) -> None:
    terminal(width)
    line = provisioner._echoed(INVOKE)
    assert len(line) <= width
    assert line.startswith("+ agentcore invoke")
    assert "SECRET" not in line


@pytest.mark.parametrize("width", [100, 84])
def test_a_short_command_is_echoed_whole(terminal, width: int) -> None:
    terminal(width)
    assert provisioner._echoed(["deploy", "--yes", "--json"]) == "+ agentcore deploy --yes --json"


@pytest.mark.parametrize("width", [100, 84])
def test_the_retry_echo_keeps_its_note_within_width(terminal, width: int) -> None:
    terminal(width)
    note = "    # again: the synth deployed nothing"
    line = provisioner._echoed(INVOKE, note)
    assert len(line) <= width and line.endswith(note)


@pytest.mark.parametrize("participant,tty", [(False, True), (True, False), (False, False)])
def test_other_modes_and_logs_echo_the_full_command(terminal, participant: bool, tty: bool) -> None:
    terminal(84, participant=participant, tty=tty)
    line = provisioner._echoed(INVOKE)
    assert line == "+ agentcore " + " ".join(provisioner._redacted(INVOKE))
    assert "SECRET" not in line and "<redacted>" in line


@pytest.mark.parametrize("width", [100, 84])
def test_two_deploys_wraps_at_words_and_loses_none(terminal, width: int) -> None:
    terminal(width)
    text = provisioner._human(provisioner.TWO_DEPLOYS)
    assert all(len(line) <= width for line in text.splitlines())
    assert " ".join(text.split()) == provisioner.TWO_DEPLOYS


def test_a_log_keeps_the_sentence_on_one_line(terminal) -> None:
    terminal(84, tty=False)
    assert provisioner._human(provisioner.TWO_DEPLOYS) == provisioner.TWO_DEPLOYS
    terminal(84, participant=False)
    assert provisioner._human(provisioner.TWO_DEPLOYS, "WARNING: ").startswith("WARNING: Two")


def test_a_prefix_hangs_over_the_wrapped_lines(terminal) -> None:
    terminal(60)
    text = provisioner._human("word " * 30, "WARNING: ")
    assert all(len(line) <= 60 for line in text.splitlines())
    assert all(line.startswith(" " * 9) for line in text.splitlines()[1:])


def test_quoted_phrases_still_exist() -> None:
    assert provisioner.ALREADY_ON_AGENTCORE == "Pellier is already using AgentCore."
    assert provisioner.MOVED_ONTO_AGENTCORE.startswith("Pellier is now using AgentCore.")
    source = PROVISIONER_PATH.read_text(encoding="utf-8")
    assert "Deployed your changes" in source
    assert "Your build answers on AgentCore Runtime" in source


def test_the_status_line_stays_off_a_terminal_only() -> None:
    source = PROVISIONER_PATH.read_text(encoding="utf-8")
    assert "if not _fitted_to_terminal():\n        print(\n            json.dumps(" in source
