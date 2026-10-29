"""A deleted lab file or lab folder comes back with a lab reset, and every lab command names it.

A participant box has no .git in the workspace: bootstrap moves the pinned checkout's .git to a
root-owned directory outside it, and a lab reset reads deleted files back with ``git show``.
The workspace and that history are built in separate temporary directories from files copied
out of this repository, never from its own .git, so the folder a test deletes is gone from
the workspace and from anything the code could fall back to.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

import pytest

from tests.test_lab_reset import FakeConnection, run_reset

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab_reference = importlib.import_module("lab_reference")
exercises = importlib.import_module("reset_participant_exercises")
check = importlib.import_module("workshop_check")
lab_run = importlib.import_module("lab_run")
lab1_vector = importlib.import_module("lab1_vector")
lab4_policy = importlib.import_module("lab4_policy")

MODULE = "pellier/backend/services/store_tools.py"


def _must_not_run(name: str):
    """These default to this repository's own files, so a gap that is not caught must not
    reach them."""
    def refuse(*_args, **_kwargs):
        raise AssertionError(f"lab_run.{name} ran although a lab file is missing")
    return refuse


@pytest.fixture(autouse=True)
def reset_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(check.RESET_POINTS_ENV, str(tmp_path / "points" / "points.json"))


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=cwd, check=True, capture_output=True)


SHIPPED = ("labs", "workshop", "solutions", "policies", "pellier/backend/services",
           "pellier/backend/agents", "scripts/deploy", "scripts/migrations")


@pytest.fixture()
def boxes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tuple[Path, Path]:
    """A workspace with no .git and, apart from it, the pinned history moved out.

    Both are built in temporary directories from files copied out of this repository, never
    from its own .git, the way bootstrap moves the pinned checkout's .git aside.
    """
    pinned = tmp_path / "pinned"
    for folder in SHIPPED:
        shutil.copytree(REPO / folder, pinned / folder, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "tests", "*.pyc"))
    _git(pinned, "init", "-q")
    _git(pinned, "add", "-A")
    _git(pinned, "commit", "-q", "-m", "pinned")
    history = tmp_path / "opt" / "source.git"
    history.parent.mkdir()
    shutil.move(str(pinned / ".git"), str(history))
    repo = tmp_path / "workspace"
    shutil.copytree(pinned, repo, symlinks=True)
    monkeypatch.setenv(lab_reference.SOURCE_ENV, str(history))
    monkeypatch.setattr(lab_run, "REPO", repo)
    monkeypatch.setattr(check, "REPO", repo)
    for name in ("install_solution", "install_task", "show_diff", "finish", "send",
                 "fast_track"):
        monkeypatch.setattr(lab_run, name, _must_not_run(name))
    return repo, history


def _line(lab: int, path: str) -> str:
    return (f"Lab {lab}: FILE MISSING ({path}). Next: run uv run scripts/lab_run.py reset "
            f"--lab {lab} to put back its starting code; your edits to that file are gone "
            "either way.")


def _shipped(path: str) -> bytes:
    return (REPO / path).read_bytes()


def test_a_deleted_marker_module_comes_back_whole_with_its_starter_region(boxes) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()

    exercises.restore_lab(repo, 1)

    assert (repo / MODULE).read_bytes() == _shipped(MODULE)
    assert exercises._check(repo, 1) == []


def test_a_file_that_exists_is_never_overwritten(boxes) -> None:
    repo, _ = boxes
    module = repo / MODULE
    module.write_text(module.read_text(encoding="utf-8") + "\n# kept\n", encoding="utf-8")

    exercises.restore_lab(repo, 1)

    assert module.read_text(encoding="utf-8").endswith("# kept\n")


def test_a_deleted_lab_folder_returns_with_every_link_pointing_where_it_did(boxes) -> None:
    repo, _ = boxes
    folder = "labs/01-retrieve"
    shutil.rmtree(repo / folder)
    assert not (repo / folder).exists()

    exercises.restore_lab(repo, 1)

    shipped = sorted(p for p in (REPO / folder).rglob("*") if p.is_symlink() or p.is_file())
    assert len(shipped) >= 8
    for entry in shipped:
        restored = repo / entry.relative_to(REPO)
        assert os.path.lexists(restored), entry
        assert restored.is_symlink() is entry.is_symlink(), entry
        if entry.is_symlink():
            assert os.readlink(restored) == os.readlink(entry), entry
            assert restored.exists(), f"{entry} dangles"
    assert (repo / folder / "solution" / "1A-vector-branch.py").is_symlink()


def test_a_reset_of_one_lab_leaves_another_labs_deleted_folder_alone(boxes) -> None:
    repo, _ = boxes
    shutil.rmtree(repo / "labs/02-ground")

    exercises.restore_lab(repo, 1)

    assert not (repo / "labs/02-ground").exists()


def test_missing_history_is_named_with_the_rule_and_a_facilitator(boxes, tmp_path: Path) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    nowhere = tmp_path / "no-history.git"

    with pytest.raises(FileNotFoundError) as caught:
        exercises.restore_lab(repo, 1, nowhere)

    message = str(caught.value)
    assert MODULE in message and str(nowhere) in message and "facilitator" in message


def test_the_workspace_has_no_git_and_the_history_is_not_reachable_from_it(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(repo.parent))

    status = subprocess.run(["git", "status"], cwd=repo, capture_output=True, text=True,
                            check=False)

    assert not (repo / ".git").exists()
    assert status.returncode != 0 and "not a git repository" in status.stderr
    assert history.is_dir() and repo not in history.parents


def test_every_git_read_names_the_history_as_a_safe_directory(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    (repo / MODULE).unlink()
    shutil.rmtree(repo / "labs/01-retrieve")
    seen = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append(list(argv))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(lab_reference.subprocess, "run", spy)

    exercises.restore_lab(repo, 1)

    assert len(seen) > 3
    for argv in seen:
        assert argv[:3] == ["git", "-c", f"safe.directory={history}"], argv
        assert f"--git-dir={history}" in argv
        assert "safe.directory=*" not in argv
    assert lab_reference.git_argv(history, "show")[2] == f"safe.directory={history}"


def test_bootstrap_moves_the_history_out_instead_of_deleting_it() -> None:
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    move = source.index('mv "$REPO_PATH/.git" "$LAB_SOURCE_GIT"')
    assert 'LAB_SOURCE_GIT="/opt/pellier/source.git"' in source
    assert 'rm -rf "$REPO_PATH/.git"' not in source
    assert source.index('"resolved_sha"') < move
    assert 'chown -hR root:root "$LAB_SOURCE_GIT"' in source
    assert 'chmod -R a+rX,go-w "$LAB_SOURCE_GIT"' in source
    assert not re.search(r"GIT_DIR=|export GIT_DIR|GIT_WORK_TREE=", source)
    assert lab_reference.DEFAULT_SOURCE == Path("/opt/pellier/source.git")


def test_lab_run_names_a_missing_file_and_exits_nonzero(
    boxes, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()

    for action in ("diff", "solution", "send", "finish"):
        assert lab_run.main([action, "--lab", "1"]) == 1
        assert _line(1, MODULE) in capsys.readouterr().out


def test_lab_run_names_a_deleted_lab_folder_through_its_alias(
    boxes, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _ = boxes
    shutil.rmtree(repo / "labs/04-govern")

    assert lab_run.main(["solution", "--lab", "4"]) == 1
    assert "Lab 4: FILE MISSING (labs/04-govern/4A-credit-policy.cedar)" in (
        capsys.readouterr().out)


def test_lab_run_reset_is_not_blocked_by_the_gap(boxes, monkeypatch) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    seen = []
    monkeypatch.setattr(lab_run.lab_reset, "reset_lab", lambda lab, **_kw: seen.append(lab))

    assert lab_run.main(["reset", "--lab", "1"]) == 0
    assert seen == [1]


def test_lab_checks_name_a_missing_file(boxes, capsys: pytest.CaptureFixture[str]) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    (repo / "policies/workshop_credit_limit.cedar").unlink()

    assert lab1_vector.main([]) == 1
    assert _line(1, MODULE) in capsys.readouterr().out
    assert lab4_policy.main([]) == 1
    assert _line(4, "policies/workshop_credit_limit.cedar") in capsys.readouterr().out


def test_the_exercise_check_names_a_missing_file(boxes) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    done = subprocess.run(
        [sys.executable, str(REPO / "scripts/reset_participant_exercises.py"),
         "--repo", str(repo), "--check", "--lab", "1"],
        capture_output=True, text=True, check=False)
    assert done.returncode == 1
    assert _line(1, MODULE) in done.stdout


def test_the_full_lab_reset_restores_a_deleted_folder_and_module_then_restarts(boxes) -> None:
    repo, _ = boxes
    shutil.rmtree(repo / "labs/01-retrieve")
    (repo / MODULE).unlink()
    events: list = []

    lines = run_reset(1, repo, FakeConnection(), events)

    assert events == ["managed 1", "restart", "healthy"]
    assert (repo / MODULE).read_bytes() == _shipped(MODULE)
    assert (repo / "labs/01-retrieve/README.md").is_file()
    assert any("Next:" in line for line in lines)
    assert exercises.lab_gap(1, repo, solutions=True) is None


def test_a_lab_reset_that_cannot_find_the_file_stops_before_anything_else(
    boxes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    monkeypatch.setenv(lab_reference.SOURCE_ENV, str(tmp_path / "nowhere.git"))
    events: list = []
    lab_reset = importlib.import_module("lab_reset")

    with pytest.raises(lab_reset.LabResetError, match="facilitator"):
        run_reset(1, repo, FakeConnection(), events)
    assert events == []


repair_files = importlib.import_module("repair_workshop_files")


def _pin(repo: Path, history: Path) -> str:
    sha = lab_reference.head_commit(history)
    assert sha
    (repo / ".workshop-ref.json").write_text(json.dumps({"resolved_sha": sha}), encoding="utf-8")
    return sha


def test_the_whole_workshop_repair_prefers_the_local_history_over_the_download(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    _pin(repo, history)
    shutil.rmtree(repo / "labs/03-deploy")
    (repo / MODULE).write_text("# the participant overwrote it\n", encoding="utf-8")

    def no_network(*_args, **_kwargs):
        raise AssertionError("the download ran although the local history held the pin")

    monkeypatch.setattr(repair_files, "download_tarball", no_network)

    report = repair_files.repair(repo)

    assert "labs/03-deploy/README.md" in report.recreated
    assert MODULE in report.restored
    assert (repo / MODULE).read_bytes() == _shipped(MODULE)


def test_the_repair_downloads_when_the_local_history_is_missing_or_at_another_commit(
    boxes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    _pin(repo, history)
    monkeypatch.setenv(lab_reference.SOURCE_ENV, str(tmp_path / "gone.git"))
    asked = []

    def download(sha: str, destination: Path) -> None:
        asked.append(sha)
        raise repair_files.RepairUnavailable("offline")

    monkeypatch.setattr(repair_files, "download_tarball", download)

    with pytest.raises(repair_files.RepairUnavailable, match="offline"):
        repair_files.repair(repo)
    assert len(asked) == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_a_checkout_aimed_at_the_read_only_history_is_refused(boxes) -> None:
    """What actually happens: Git cannot take its index lock inside the read-only gitdir."""
    repo, history = boxes
    for path in [history, *history.rglob("*")]:
        if not path.is_symlink():
            path.chmod(0o555 if path.is_dir() else 0o444)
    try:
        done = subprocess.run(
            ["git", f"--git-dir={history}", f"--work-tree={repo}", "checkout", "--", "."],
            capture_output=True, text=True, check=False,
            env={**os.environ, "GIT_CEILING_DIRECTORIES": str(repo.parent)})
        assert done.returncode != 0
        assert "Permission denied" in done.stderr or "index.lock" in done.stderr
        assert lab_reference.blob(history, MODULE) is not None
    finally:
        for path in [history, *history.rglob("*")]:
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() else 0o644)


def test_bootstrap_proves_the_participant_can_read_the_history_or_stops() -> None:
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    chmod = source.index('chmod -R a+rX,go-w "$LAB_SOURCE_GIT"')
    probe = source.index('sudo -u "$CODE_EDITOR_USER" git -c "safe.directory=$LAB_SOURCE_GIT"')
    stop = source.index('cannot read the pinned history at ${LAB_SOURCE_GIT}')
    assert chmod < probe < stop < source.index("Workspace detached from git")
    assert 'rev-parse HEAD' in source[probe:stop]
    assert '|| fail' in source[probe:stop + 80]


def test_a_pristine_workspace_repairs_to_nothing_through_the_local_history(boxes) -> None:
    """git archive must give GitHub's modes (0644, 0755), not its default umask-002 ones."""
    repo, history = boxes
    _pin(repo, history)

    report = repair_files.repair(repo)

    assert report.restored == [] and report.recreated == []
    assert report.unchanged > 100


def test_a_reset_run_as_root_hands_what_it_creates_to_the_repository_owner(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    shutil.rmtree(repo / "labs/01-retrieve")
    (repo / MODULE).unlink()
    chowned = []
    monkeypatch.setattr(lab_reference.os, "geteuid", lambda: 0)
    monkeypatch.setattr(lab_reference.os, "lchown",
                        lambda path, uid, gid: chowned.append((Path(path), uid, gid)))

    exercises.restore_lab(repo, 1)

    owner = repo.stat()
    paths = {path for path, uid, gid in chowned if (uid, gid) == (owner.st_uid, owner.st_gid)}
    assert repo / MODULE in paths
    assert repo / "labs/01-retrieve" in paths and repo / "labs/01-retrieve/solution" in paths
    assert repo / "labs/01-retrieve/README.md" in paths
    assert repo / "labs/01-retrieve/solution/1A-vector-branch.py" in paths
    assert repo / "labs" not in paths


def test_an_unreadable_history_is_named_with_gits_own_words(boxes, tmp_path: Path) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    broken = tmp_path / "broken.git"
    broken.mkdir()

    with pytest.raises(FileNotFoundError) as caught:
        exercises.restore_lab(repo, 1, broken)

    message = str(caught.value)
    assert "cannot be read" in message and "not a git repository" in message
    assert "holds no" not in message and "facilitator" in message


def test_a_path_missing_from_a_readable_history_says_so(boxes, monkeypatch) -> None:
    repo, history = boxes
    (repo / MODULE).unlink()
    monkeypatch.setattr(lab_reference, "tree", lambda *_a, **_k: [])

    with pytest.raises(FileNotFoundError, match="holds no"):
        exercises.restore_lab(repo, 1)


def test_a_dangling_link_where_a_file_belongs_is_the_facilitator_error(
    boxes, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _ = boxes
    (repo / MODULE).unlink()
    (repo / MODULE).symlink_to("nowhere.py")

    assert lab_run.main(["diff", "--lab", "1"]) == 1
    printed = capsys.readouterr().out
    assert f"Lab 1: {MODULE} is not a file" in printed and "facilitator" in printed
    assert "lab_run.py reset" not in printed
    with pytest.raises(FileNotFoundError, match="facilitator"):
        exercises.restore_lab(repo, 1)


def test_link_targets_outside_the_repository_are_not_followed(tmp_path: Path) -> None:
    pinned = tmp_path / "pinned"
    folder = pinned / "labs" / "01-retrieve"
    folder.mkdir(parents=True)
    (pinned / "..dotdir").mkdir()
    (pinned / "..dotdir" / "f").write_text("kept\n", encoding="utf-8")
    (folder / "absolute").symlink_to("/etc/hosts")
    (folder / "outside").symlink_to("../../../outside")
    (folder / "dots").symlink_to("../../..dotdir/f")
    _git(pinned, "init", "-q")
    _git(pinned, "add", "-A")
    _git(pinned, "commit", "-q", "-m", "pinned")

    entries = lab_reference.lab_entries(pinned / ".git", 1)

    assert "..dotdir/f" in entries
    assert "/etc/hosts" not in entries and "../outside" not in entries
    assert not any(e.startswith(("/", "../")) for e in entries)


def test_a_repair_run_as_root_hands_what_it_creates_and_rewrites_to_the_repository_owner(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    _pin(repo, history)
    shutil.rmtree(repo / "labs/03-deploy")
    (repo / MODULE).write_text("# rewritten by the participant\n", encoding="utf-8")
    chowned = []
    monkeypatch.setattr(lab_reference.os, "geteuid", lambda: 0)
    monkeypatch.setattr(lab_reference.os, "lchown",
                        lambda path, uid, gid: chowned.append((Path(path), uid, gid)))

    repair_files.repair(repo)

    owner = repo.stat()
    paths = {path for path, uid, gid in chowned if (uid, gid) == (owner.st_uid, owner.st_gid)}
    assert repo / MODULE in paths
    assert repo / "labs/03-deploy" in paths and repo / "labs/03-deploy/solution" in paths
    assert repo / "labs/03-deploy/README.md" in paths
    assert repo / "labs" not in paths


def test_a_repair_run_as_the_owner_changes_no_ownership(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    _pin(repo, history)
    (repo / MODULE).unlink()
    monkeypatch.setattr(lab_reference.os, "lchown", lambda *_a: pytest.fail("chown ran"))

    repair_files.repair(repo)


def test_a_failure_part_way_still_hands_over_the_folders_it_created(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    _pin(repo, history)
    shutil.rmtree(repo / "labs/03-deploy")
    chowned = []
    monkeypatch.setattr(lab_reference.os, "geteuid", lambda: 0)
    monkeypatch.setattr(lab_reference.os, "lchown",
                        lambda path, uid, gid: chowned.append(Path(path)))
    real = Path.write_bytes

    def fail_on_readme(self: Path, data: bytes) -> int:
        if self.name == "README.md" and "03-deploy" in self.parts:
            raise OSError("disk full")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail_on_readme)

    with pytest.raises(OSError, match="disk full"):
        lab_reference.restore_missing(repo, history, ["labs/03-deploy/README.md"])

    assert repo / "labs/03-deploy" in chowned


def test_the_bootstrap_probe_keeps_stderr_out_of_the_revision_and_runs_from_root() -> None:
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    start = source.index("probe_err=$(mktemp)")
    probe = source[start:source.index("recorded_sha=", start)]
    assert '2>"$probe_err"' in probe and "2>&1" not in probe
    assert "cd / && sudo -u" in probe
    assert '$(cat "$probe_err")' in probe


def test_a_repair_that_fails_part_way_still_hands_over_the_folders_it_created(
    boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, history = boxes
    _pin(repo, history)
    shutil.rmtree(repo / "labs/03-deploy")
    chowned = []
    monkeypatch.setattr(lab_reference.os, "geteuid", lambda: 0)
    monkeypatch.setattr(lab_reference.os, "lchown",
                        lambda path, uid, gid: chowned.append(Path(path)))

    def full_disk(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(repair_files.os, "replace", full_disk)

    with pytest.raises(OSError, match="disk full"):
        repair_files.repair(repo)

    assert any(path.parts[-2:-1] == ("03-deploy",) or path.name == "03-deploy"
               for path in chowned)
