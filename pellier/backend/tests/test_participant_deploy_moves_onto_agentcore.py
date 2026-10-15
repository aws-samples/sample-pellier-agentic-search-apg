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
    assert out[-1] == "Pellier is now using AgentCore. Continue with Theo's requests."


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
    assert "move_onto_agentcore(repo)" in block
    assert "reset_to_starters=args.reset_to_starters" in block
