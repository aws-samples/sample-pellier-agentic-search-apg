"""The full reset repairs every tracked file from the revision the box was built from.

A workshop box has no git checkout, so ``scripts/repair_workshop_files.py`` downloads the
pinned revision's tarball and writes back what differs. These tests build small tarballs in
a temporary directory; the real download is exercised on a workshop box.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
repair = importlib.import_module("repair_workshop_files")

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "f" * 40
TOP = "sample-pellier-agentic-search-apg-" + SHA
RESET = REPO / "scripts" / "reset-governed-workshop.sh"


def make_tarball(
    path: Path,
    files: Dict[str, str],
    *,
    top: str = TOP,
    modes: Optional[Dict[str, int]] = None,
    links: Optional[Dict[str, str]] = None,
    comment: Optional[str] = SHA,
) -> None:
    """Write a codeload-shaped tarball: one top directory, an optional pax comment."""
    headers = {"comment": comment} if comment else {}
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT, pax_headers=headers) as archive:
        folder = tarfile.TarInfo(top)
        folder.type = tarfile.DIRTYPE
        folder.mode = 0o755
        archive.addfile(folder)
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            info.mode = (modes or {}).get(name, 0o644)
            archive.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)


def box(tmp_path: Path, sha: str = SHA) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".workshop-ref.json").write_text(json.dumps({"resolved_sha": sha}))
    return repo


def fetch_from(tarball: Path):
    def fetch(_sha: str, destination: Path) -> None:
        destination.write_bytes(tarball.read_bytes())

    return fetch


# ---------------------------------------------------------------------------
# What is repaired
# ---------------------------------------------------------------------------


def test_modified_and_deleted_files_are_restored_and_counted(tmp_path: Path) -> None:
    repo = box(tmp_path)
    (repo / "a").mkdir()
    (repo / "a" / "kept.txt").write_text("same")
    # The tarball's mode, set outright: a box shell under umask 077 would write 0600 and
    # count the kept file as changed.
    (repo / "a" / "kept.txt").chmod(0o644)
    (repo / "a" / "edited.txt").write_text("participant edit")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"a/kept.txt": "same", "a/edited.txt": "original",
                           "a/deleted.txt": "original too"})

    report = repair.repair(repo, fetch=fetch_from(tarball))

    assert (repo / "a" / "edited.txt").read_text() == "original"
    assert (repo / "a" / "deleted.txt").read_text() == "original too"
    assert report.restored == ["a/edited.txt"]
    assert report.recreated == ["a/deleted.txt"]
    assert report.unchanged == 1
    assert report.repaired == 2


def test_a_file_the_participant_created_is_left_alone(tmp_path: Path) -> None:
    repo = box(tmp_path)
    (repo / "notes.md").write_text("my notes")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"README.md": "readme"})

    repair.repair(repo, fetch=fetch_from(tarball))

    assert (repo / "notes.md").read_text() == "my notes"


def test_symlinks_are_kept_as_symlinks_and_modes_are_kept(tmp_path: Path) -> None:
    repo = box(tmp_path)
    (repo / "labs").mkdir()
    (repo / "labs" / "link.py").write_text("a copy a zip extraction made")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"scripts/run.sh": "#!/bin/sh\n", "pellier/app.py": "x"},
                 modes={"scripts/run.sh": 0o755},
                 links={"labs/link.py": "../pellier/app.py"})

    repair.repair(repo, fetch=fetch_from(tarball))

    assert (repo / "labs" / "link.py").is_symlink()
    assert os.readlink(repo / "labs" / "link.py") == "../pellier/app.py"
    assert (repo / "scripts" / "run.sh").stat().st_mode & 0o777 == 0o755


def test_a_mode_change_alone_is_repaired(tmp_path: Path) -> None:
    repo = box(tmp_path)
    (repo / "run.sh").write_text("#!/bin/sh\n")
    (repo / "run.sh").chmod(0o644)
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"run.sh": "#!/bin/sh\n"}, modes={"run.sh": 0o755})

    report = repair.repair(repo, fetch=fetch_from(tarball))

    assert report.restored == ["run.sh"]
    assert (repo / "run.sh").stat().st_mode & 0o777 == 0o755


def test_a_replaced_file_gets_a_new_inode_so_a_running_script_keeps_its_copy(
    tmp_path: Path,
) -> None:
    repo = box(tmp_path)
    (repo / "reset.sh").write_text("old")
    before = (repo / "reset.sh").stat().st_ino
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"reset.sh": "new"})

    repair.repair(repo, fetch=fetch_from(tarball))

    assert (repo / "reset.sh").read_text() == "new"
    assert (repo / "reset.sh").stat().st_ino != before


def test_check_counts_without_writing(tmp_path: Path) -> None:
    repo = box(tmp_path)
    (repo / "a.txt").write_text("edited")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"a.txt": "original", "b.txt": "missing"})

    report = repair.repair(repo, write=False, fetch=fetch_from(tarball))

    assert report.repaired == 2
    assert (repo / "a.txt").read_text() == "edited"
    assert not (repo / "b.txt").exists()


def test_a_directory_in_a_files_place_is_skipped_not_deleted(tmp_path: Path) -> None:
    repo = box(tmp_path)
    (repo / "a.txt").mkdir()
    (repo / "a.txt" / "mine").write_text("keep")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"a.txt": "original"})

    report = repair.repair(repo, fetch=fetch_from(tarball))

    assert report.skipped and report.repaired == 0
    assert (repo / "a.txt" / "mine").read_text() == "keep"


# ---------------------------------------------------------------------------
# What is never touched
# ---------------------------------------------------------------------------

PRESERVED_PATHS = [
    ".env",
    ".provision.env",
    ".workshop-ref.json",
    ".agentcore-project/agentcore/agentcore.json",
    ".vscode/settings.json",
    ".local/lab-reset-points.json",
    "pellier/start-backend.sh",
    "pellier/config/mcp-server-config.json",
    "pellier/frontend/.env",
    "pellier/frontend/dist/index.html",
    "pellier/frontend/node_modules/pkg/index.js",
    "pellier/backend/.env",
    "pellier/backend/.venv/bin/python",
    "pellier/backend/services/__pycache__/store_tools.pyc",
    "deep/er/node_modules/x.js",
]


@pytest.mark.parametrize("relative", PRESERVED_PATHS)
def test_preserved_paths_are_recognised(relative: str) -> None:
    assert repair.is_preserved(relative)


def test_a_tracked_file_is_not_preserved() -> None:
    for relative in ("scripts/migrations/001_schema.sql", "workshop/lab-2-check-stock.sql",
                     "pellier/backend/services/store_tools.py", "START_HERE.md",
                     "pellier/config/cognito-branding/hosted-ui.css", ".envrc.example"):
        assert not repair.is_preserved(relative), relative


def test_preserved_paths_are_never_overwritten_even_when_the_tarball_holds_them(
    tmp_path: Path,
) -> None:
    repo = box(tmp_path)
    kept = {}
    for relative in PRESERVED_PATHS:
        if relative == ".workshop-ref.json":
            continue
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("runtime state " + relative)
        kept[relative] = target.read_text()
    ref_before = (repo / ".workshop-ref.json").read_text()
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {**{p: "from the tarball" for p in PRESERVED_PATHS},
                           "tracked.txt": "tracked"})

    repair.repair(repo, fetch=fetch_from(tarball))

    for relative, text in kept.items():
        assert (repo / relative).read_text() == text, relative
    assert (repo / ".workshop-ref.json").read_text() == ref_before
    assert (repo / "tracked.txt").read_text() == "tracked"


def test_preserved_paths_cover_what_bootstrap_writes_inside_the_repository() -> None:
    """Every runtime file bootstrap creates under the repository root is on the list."""
    bootstrap = (REPO / "scripts" / "bootstrap-labs.sh").read_text()
    written = {
        ".env": r'cat > "\$REPO_PATH/\.env"',
        "pellier/frontend/.env": r'cat > "\$REPO_PATH/pellier/frontend/\.env"',
        "pellier/start-backend.sh": r'cat > "\$REPO_PATH/pellier/start-backend\.sh"',
        ".workshop-ref.json": r'tee "\$REPO_PATH/\.workshop-ref\.json"',
        "pellier/backend/.env": r'ln -sf "\$REPO_PATH/\.env" "\$REPO_PATH/pellier/backend/\.env"',
    }
    for relative, pattern in written.items():
        assert re.search(pattern, bootstrap), f"bootstrap no longer writes {relative}"
        assert repair.is_preserved(relative), relative
    assert ".provision.env" in bootstrap and repair.is_preserved(".provision.env")
    assert ".agentcore-project" in bootstrap and repair.is_preserved(".agentcore-project/x")
    assert "pellier/config/mcp-server-config.json" in bootstrap
    assert repair.is_preserved("pellier/config/mcp-server-config.json")


def test_nothing_preserved_is_a_tracked_file() -> None:
    """A preserved path that git tracks could never be repaired."""
    if not (REPO / ".git").exists():
        pytest.skip("needs a git checkout")
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True,
                             text=True, check=True).stdout.splitlines()
    assert [path for path in tracked if repair.is_preserved(path)] == []


# ---------------------------------------------------------------------------
# The pin: which revision, and proof it is the one downloaded
# ---------------------------------------------------------------------------


def test_the_pin_comes_from_workshop_ref(tmp_path: Path) -> None:
    assert repair.pinned_sha(box(tmp_path)) == SHA


@pytest.mark.parametrize("recorded", ["unknown", "", "main", "abc123", "G" * 40])
def test_a_pin_that_is_not_a_full_commit_is_unavailable(tmp_path: Path, recorded: str) -> None:
    with pytest.raises(repair.RepairUnavailable):
        repair.pinned_sha(box(tmp_path, recorded))


def test_a_missing_ref_file_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(repair.RepairUnavailable, match="cannot read"):
        repair.pinned_sha(tmp_path)


def test_the_download_url_is_codeload_for_that_sha() -> None:
    assert repair.TARBALL_URL.format(sha=SHA) == (
        "https://codeload.github.com/aws-samples/sample-pellier-agentic-search-apg/tar.gz/" + SHA)


def test_a_tarball_for_another_revision_is_refused_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    repo = box(tmp_path)
    (repo / "a.txt").write_text("edited")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"a.txt": "other revision"},
                 top="sample-pellier-agentic-search-apg-" + OTHER_SHA, comment=OTHER_SHA)

    with pytest.raises(repair.RepairUnavailable, match="not the pinned revision"):
        repair.repair(repo, fetch=fetch_from(tarball))

    assert (repo / "a.txt").read_text() == "edited"


def test_a_tarball_whose_commit_comment_differs_is_refused(tmp_path: Path) -> None:
    repo = box(tmp_path)
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"a.txt": "x"}, comment=OTHER_SHA)

    with pytest.raises(repair.RepairUnavailable, match="names commit"):
        repair.repair(repo, fetch=fetch_from(tarball))

    assert not (repo / "a.txt").exists()


def test_a_path_that_leaves_the_repository_is_refused(tmp_path: Path) -> None:
    repo = box(tmp_path)
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"../evil.txt": "x"})

    with pytest.raises(repair.RepairUnavailable, match="unsafe path"):
        repair.repair(repo, fetch=fetch_from(tarball))

    assert not (tmp_path / "evil.txt").exists()


def test_a_corrupt_download_is_unavailable(tmp_path: Path) -> None:
    repo = box(tmp_path)

    def fetch(_sha: str, destination: Path) -> None:
        destination.write_bytes(b"not a tarball")

    with pytest.raises(repair.RepairUnavailable, match="unreadable"):
        repair.repair(repo, fetch=fetch)


# ---------------------------------------------------------------------------
# A failed download: say so, change nothing, exit 3 so the reset can continue
# ---------------------------------------------------------------------------


def test_a_failed_download_exits_three_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = box(tmp_path)
    (repo / "a.txt").write_text("edited")

    def unavailable(_sha: str, _destination: Path) -> None:
        raise repair.RepairUnavailable("cannot download the tarball: no network")

    monkeypatch.setattr(repair, "download_tarball", unavailable)

    assert repair.main(["--repo", str(repo)]) == repair.EXIT_UNAVAILABLE == 3
    assert "NOT repaired" in capsys.readouterr().err
    assert (repo / "a.txt").read_text() == "edited"


def test_an_unusable_pin_exits_three(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert repair.main(["--repo", str(tmp_path)]) == 3
    assert "NOT repaired" in capsys.readouterr().err


def test_main_prints_how_many_files_were_repaired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = box(tmp_path)
    (repo / "pellier" / "backend").mkdir(parents=True)
    (repo / "pellier" / "backend" / "app.py").write_text("edited")
    tarball = tmp_path / "pin.tar.gz"
    make_tarball(tarball, {"pellier/backend/app.py": "original", "gone.txt": "x"})
    monkeypatch.setattr(repair, "download_tarball", fetch_from(tarball))

    assert repair.main(["--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "2 file(s) restored to the pin: 1 changed, 1 missing" in out
    assert "restart the backend" in out


# ---------------------------------------------------------------------------
# The full reset runs it first
# ---------------------------------------------------------------------------


def test_the_reset_repairs_files_before_it_rebuilds_the_database() -> None:
    body = RESET.read_text()
    repair_call = body.index("\n_repair_workshop_files\n")
    assert body.index("\n_quiesce_services\n") < repair_call
    assert repair_call < body.index("reset_participant_exercises.py")
    assert repair_call < body.index('bash "$REPO/scripts/setup/database-reset.sh"')


def test_the_reset_continues_when_the_download_is_unavailable() -> None:
    body = RESET.read_text()
    function = body[body.index("_repair_workshop_files() {"):body.index("_load_restore_functions() {")]
    unavailable = function[function.index('"$rc" -eq 3'):]
    assert "warn " in unavailable.split("else")[0]
    assert "exit" not in unavailable.split("else")[0]
    assert "Continuing the reset" in function
    assert 'fail "Workshop file repair failed' in function


def test_the_reset_loads_the_restore_functions_only_after_the_repair() -> None:
    body = RESET.read_text()
    assert body.index("\n_repair_workshop_files\n") < body.index("\n_load_restore_functions\n")


def test_the_reset_does_not_run_the_repair_when_only_a_lab_is_reset() -> None:
    lab_script = (REPO / "scripts" / "reset-agentcore-lab.sh").read_text()
    assert "repair_workshop_files" not in lab_script
