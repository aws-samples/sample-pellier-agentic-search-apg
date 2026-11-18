"""A ready participant deploy moves Pellier onto AgentCore, and only then.

Lab 3 used to switch the storefront's rail with its own command, ``lab3-start.sh``. The
participant deploy now runs that switch itself once the deployment reports ready, so the
move happens at the one moment the managed path is known to serve the participant's
build. These tests drive the joint with fakes: no AWS, no systemd.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROVISIONER_PATH = REPO_ROOT / "scripts" / "provision_agentcore_end_to_end.py"


def _load_provisioner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "pellier_agentcore_provisioner_switch", PROVISIONER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provisioner = _load_provisioner()


class Runs:
    """Every command run, each answering with the scripted exit status."""

    def __init__(self, returncode: int = 0) -> None:
        self.commands: List[List[str]] = []
        self.returncode = returncode

    def __call__(self, argv: List[str], **kwargs: Any) -> Any:
        self.commands.append(argv)
        return type("Completed", (), {"returncode": self.returncode})()


def _repo(tmp_path: Path, env_line: str = "") -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".env").write_text(f"AWS_REGION=us-east-1\n{env_line}\n")
    return tmp_path


def test_a_fresh_deploy_switches_onto_agentcore_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo, runs = _repo(tmp_path), Runs()
    assert provisioner.move_onto_agentcore(
        repo, run=runs, run_env=tmp_path / "absent-run.env") == 0
    assert runs.commands == [["bash", str(repo / "scripts" / "lab3-start.sh"), "theo"]]
    out = capsys.readouterr().out.splitlines()
    assert out[-4:] == ["Pellier is now using AgentCore. Continue with Theo's requests.", "",
                        "Next: when your ownership tests have passed, send Theo's three requests.",
                        "      uv run scripts/lab_run.py send --lab 3"]


@pytest.mark.parametrize("where", ["env", "run_env"])
def test_a_repeated_deploy_leaves_the_rail_and_the_service_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], where: str,
) -> None:
    run_env = tmp_path / "run.env"
    if where == "env":
        repo = _repo(tmp_path, "USE_AGENTCORE_RUNTIME=true")
    else:
        repo = _repo(tmp_path, "USE_AGENTCORE_RUNTIME=false")
        run_env.write_text('USE_AGENTCORE_RUNTIME="true"\n')
    runs = Runs()
    assert provisioner.move_onto_agentcore(repo, run=runs, run_env=run_env) == 0
    assert runs.commands == []
    assert capsys.readouterr().out.splitlines()[-1] == "Pellier is already using AgentCore."


def test_the_service_setting_wins_over_the_repository_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "USE_AGENTCORE_RUNTIME=true")
    run_env = tmp_path / "run.env"
    run_env.write_text("USE_AGENTCORE_RUNTIME=false\n")
    runs = Runs()
    provisioner.move_onto_agentcore(repo, run=runs, run_env=run_env)
    assert len(runs.commands) == 1


def test_a_failed_switch_reports_it_and_never_claims_the_move(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    assert provisioner.move_onto_agentcore(
        repo, run=Runs(returncode=1), run_env=tmp_path / "absent") == 1
    captured = capsys.readouterr()
    assert "Pellier is now using AgentCore" not in captured.out
    assert "bash scripts/lab3-start.sh theo" in captured.err


def test_a_failed_deploy_never_moves_the_rail() -> None:
    moves: List[str] = []

    def update() -> int:
        raise RuntimeError("Participant update checks did not pass: targets_attached")

    with pytest.raises(RuntimeError):
        provisioner._participant_then_move(update, lambda: moves.append("move") or 0,
                                           reset_to_starters=False)
    assert moves == []
    assert provisioner._participant_then_move(lambda: 1, lambda: moves.append("move") or 0,
                                              reset_to_starters=False) == 1
    assert moves == []


def test_a_workshop_reset_deploy_never_moves_the_rail() -> None:
    moves: List[str] = []
    assert provisioner._participant_then_move(lambda: 0, lambda: moves.append("move") or 0,
                                              reset_to_starters=True) == 0
    assert moves == []


def test_a_ready_deploy_moves_and_returns_the_moves_status() -> None:
    moves: List[str] = []
    assert provisioner._participant_then_move(lambda: 0, lambda: moves.append("move") or 7,
                                              reset_to_starters=False) == 7
    assert moves == ["move"]


def test_main_routes_the_participant_update_through_the_move() -> None:
    source = PROVISIONER_PATH.read_text(encoding="utf-8")
    start = source.index('if args.mode == "participant":')
    block = source[start:source.index("_require_release_log_protection(", start)]
    assert "_participant_then_move(" in block
    assert "move_onto_agentcore(repo, progress=progress)" in block
    assert "reset_to_starters=args.reset_to_starters" in block


def test_the_move_is_the_deploys_last_step_and_the_closing_line_stays_last(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    progress = provisioner.Progress()
    progress.expect(1)
    assert provisioner.move_onto_agentcore(
        _repo(tmp_path), run=Runs(), run_env=tmp_path / "absent", progress=progress) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "  - 1/1  Moving Pellier onto AgentCore (usually about 0:45)"
    assert out[1].endswith("1/1  Moved Pellier onto AgentCore")
    assert out[2].startswith("  Done in ")
    assert out[-4:] == ["Pellier is now using AgentCore. Continue with Theo's requests.", "",
                        "Next: when your ownership tests have passed, send Theo's three requests.",
                        "      uv run scripts/lab_run.py send --lab 3"]


def test_a_failed_move_marks_its_step_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    progress = provisioner.Progress()
    assert provisioner.move_onto_agentcore(
        _repo(tmp_path), run=Runs(returncode=1), run_env=tmp_path / "absent",
        progress=progress) == 1
    captured = capsys.readouterr()
    assert "Moving Pellier onto AgentCore: failed" in captured.out
    assert "Done in" not in captured.out


def _lab3_start_message(persona: str) -> str:
    import re

    source = (REPO_ROOT / "scripts" / "lab3-start.sh").read_text(encoding="utf-8")
    line = next(row for row in source.splitlines() if re.match(rf"\s*{re.escape(persona)}\)", row))
    match = re.search(r'MESSAGE="([^"]*)"', line)
    assert match, line
    return match.group(1)


def test_the_moves_theo_turn_states_no_taste_memory_could_merge() -> None:
    """Event of 2026-11-17: the move's Theo turn said "Hand-thrown ceramics for a slower morning
    routine". Since live turns write to Memory, extraction merged it into his seeded preference
    about a minute later and replaced that record, so a Task 3B turn sent in that minute used a
    record that was gone by the check. The move asks a question with no taste in it.
    """
    import re
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts" / "deploy"))
    sys.path.insert(0, str(REPO_ROOT / "pellier" / "backend"))
    from seed_agentcore_memory import SEED_TURNS
    from services.intent_router import route_query

    message = _lab3_start_message("*")
    assert route_query(message).intent == "support"
    seeded = " ".join(" ".join(turn) for turn in SEED_TURNS["CUST-THEO"]).lower()
    taste = {word for word in re.findall(r"[a-z]+", seeded) if len(word) > 4}
    assert not taste & set(re.findall(r"[a-z]+", message.lower())), message


def test_a_participant_deploy_opens_with_its_steps_not_the_setup_stage(monkeypatch) -> None:
    """Owner, 2026-11-17: the participant deploy's first line read "Managed AgentCore stage:
    managed resource provisioning", jargon above "Deploying your changes to AgentCore". Setup
    logs keep the stage name; a participant's deploy starts with its numbered steps."""
    monkeypatch.setitem(provisioner._PARTICIPANT_VIEW, "on", True)
    assert provisioner._stage_line("managed resource provisioning") is None
    monkeypatch.setitem(provisioner._PARTICIPANT_VIEW, "on", False)
    assert provisioner._stage_line("managed resource provisioning") == (
        "Managed AgentCore stage: managed resource provisioning")


def test_the_gateway_line_says_which_published_tools_a_shopper_does_not_see() -> None:
    """Owner, 2026-11-17: "The Gateway publishes 8 tools to a signed-in caller" came right after
    Task 3A's "9 of 9 tools published". The line names the staff-only tool the shopper cannot see."""
    published = frozenset({"search_products", "get_tickets", "give_store_credit"})
    visible = ["search_products", "get_tickets"]
    assert provisioner._shopper_tools_line(visible, published) == (
        "A shopper sees 2 of 3 Gateway tools; give_store_credit is staff-only")
    before_3a = frozenset({"search_products", "give_store_credit"})
    assert provisioner._shopper_tools_line(["search_products"], before_3a) == (
        "A shopper sees 1 of 2 Gateway tools; give_store_credit is staff-only")
    assert provisioner._shopper_tools_line(["a", "b"], frozenset({"a", "b"})) == (
        "A shopper sees 2 of 2 Gateway tools")


@pytest.mark.parametrize("already", [False, True])
def test_the_closing_line_is_green_on_a_terminal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    already: bool,
) -> None:
    """Owner, 2026-11-17: the line that says Pellier now runs on AgentCore is a success and
    reads green like a passed check; off a terminal it stays plain text."""
    run_env = tmp_path / "run.env"
    if already:
        run_env.write_text("USE_AGENTCORE_RUNTIME=true\n")
    monkeypatch.setattr(provisioner.workshop_check, "colour_enabled", lambda stream=None: True)
    assert provisioner.move_onto_agentcore(_repo(tmp_path), run=Runs(), run_env=run_env) == 0
    line = (provisioner.ALREADY_ON_AGENTCORE if already else provisioner.MOVED_ONTO_AGENTCORE)
    out = capsys.readouterr().out
    assert provisioner.workshop_check.paint(line, provisioner.workshop_check.PASSED) in out
    assert "\033[" in provisioner.workshop_check.paint(line, provisioner.workshop_check.PASSED)
