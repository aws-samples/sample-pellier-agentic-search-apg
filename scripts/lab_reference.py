"""Read the shipped lab files from the pinned Git history kept outside the workspace.

A participant box has no ``.git`` in the workspace, so a habitual ``git checkout -- .`` cannot
revert a task file; that is protection against habit, not against deliberate Git plumbing.
Bootstrap moves the pinned checkout's ``.git`` to a root-owned directory outside the workspace
instead of deleting it (``/opt/pellier/source.git``). A lab reset reads
a deleted file back from it, as ``git show HEAD:<path>`` does, and a deleted ``labs/0N-*``
folder as ``git ls-tree -r HEAD -- <folder>`` lists it. Links come back as links (mode 120000;
the blob is the target). Application modules come back whole and as shipped, where every
marked region equals its starter, so a restored module holds the starting code, never an
answer.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

SOURCE_ENV = "PELLIER_LAB_SOURCE_GIT"
DEFAULT_SOURCE = Path("/opt/pellier/source.git")
PARTICIPANT_FILES = "workshop/participant-files.json"
LAB_FOLDERS = {1: "01-retrieve", 2: "02-ground", 3: "03-deploy", 4: "04-govern"}
SYMLINK_MODE = "120000"
EXECUTABLE_MODE = "100755"


class LabFileMissing(FileNotFoundError):
    """A lab file is gone and the pinned history cannot bring it back."""


def source_dir() -> Path:
    """Where the pinned history is read from: the environment override, else the default."""
    return Path(os.environ.get(SOURCE_ENV, str(DEFAULT_SOURCE)))


def git_argv(source: Path, *args: str) -> List[str]:
    """The command line for one read of ``source``.

    The history is root-owned, so Git's ownership check would refuse it for the participant.
    ``safe.directory`` given on the command line is protected configuration that Git honours,
    and it names only this path; nothing is written to the participant's own Git config.
    """
    return ["git", "-c", f"safe.directory={source}", f"--git-dir={source}", *args]


def _run(source: Path, *args: str) -> Tuple[int, bytes, str]:
    """Run a read-only git command against ``source``: exit status, stdout and stderr."""
    try:
        done = subprocess.run(
            git_argv(source, *args), capture_output=True, check=False,
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
    except OSError as exc:
        return 127, b"", f"cannot run git: {exc}"
    return done.returncode, done.stdout, done.stderr.decode("utf-8", "replace").strip()


def _git(source: Path, *args: str) -> Optional[bytes]:
    """Run a read-only git command against ``source``; None when it cannot answer."""
    status, out, _err = _run(source, *args)
    return out if status == 0 else None


def history_problem(source: Path) -> Optional[str]:
    """Why the history itself cannot be read (git's own words), or None when it can."""
    status, _out, err = _run(source, "rev-parse", "HEAD")
    return None if status == 0 else (err or f"git exited {status}")


def tree(source: Path, *paths: str) -> List[Tuple[str, str]]:
    """``(mode, path)`` for every file and link at or under ``paths`` in HEAD."""
    out = _git(source, "ls-tree", "-r", "-z", "HEAD", "--", *paths)
    if not out:
        return []
    found = []
    for record in out.decode("utf-8").split("\0"):
        if record:
            meta, path = record.split("\t", 1)
            found.append((meta.split()[0], path))
    return found


def blob(source: Path, path: str) -> Optional[bytes]:
    """The content of ``path`` at HEAD (a link's target, for a link)."""
    return _git(source, "show", f"HEAD:{path}")


def lab_entries(source: Path, lab: int) -> List[str]:
    """One lab folder's entries plus the files its links point at, as HEAD has them."""
    entries = tree(source, f"labs/{LAB_FOLDERS[lab]}")
    found = [path for _mode, path in entries]
    targets = set()
    for mode, path in entries:
        content = blob(source, path) if mode == SYMLINK_MODE else None
        if content is not None:
            target = content.decode()
            joined = os.path.normpath(os.path.join(os.path.dirname(path), target))
            inside = not os.path.isabs(target) and joined != ".." and not joined.startswith("../")
            if inside:
                targets.add(joined)
    return found + sorted(targets - set(found))


def keep_version(repo: Path, alias: str, yours: bytes) -> str:
    """Save the participant's version beside ``alias`` as ``.bak``, ``.bak.2`` and on.

    A backup that already holds the same bytes is reused, so nothing is overwritten and a
    repeat run adds no copy. Returns the sentence to print.
    """
    number = 1
    while True:
        name = f"{alias}.bak" if number == 1 else f"{alias}.bak.{number}"
        backup = repo / name
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(yours)
            return f"your version is kept in {name}"
        if backup.read_bytes() == yours:
            return f"your version is already kept in {name}"
        number += 1


BACKUP_DIR_ENV = "PELLIER_RESET_BACKUP_DIR"
BACKUP_PARENT = Path("/var/lib/pellier/backups")


def reset_backup_dir() -> Path:
    """Where a reset parks a participant's earlier versions, outside the workspace.

    ``PELLIER_RESET_BACKUP_DIR`` names it outright: the whole-workshop reset sets one folder
    for its two steps. Otherwise a dated folder under /var/lib/pellier/backups on a workshop
    box, or under ~/.pellier-backups where that parent is not writable. Nothing is created
    until a file is parked.
    """
    named = os.environ.get(BACKUP_DIR_ENV)
    if named:
        return Path(named)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    parent = BACKUP_PARENT.parent
    usable = parent.is_dir() and os.access(parent, os.W_OK)
    return (BACKUP_PARENT if usable else Path.home() / ".pellier-backups") / stamp


def park_version(repo: Path, backup_dir: Path, alias: str, yours: bytes) -> Path:
    """Move a participant's version out of the workspace, keeping its lab folder and name.

    A later, different version of the same file in one reset gets ``.2``, ``.3`` and on, so
    nothing is overwritten; bytes already parked are not written twice. Returns the parked
    path. What root parks is handed to the repository's owner.
    """
    number = 1
    while True:
        name = alias if number == 1 else f"{alias}.{number}"
        parked = backup_dir / name
        if not parked.exists():
            parked.parent.mkdir(parents=True, exist_ok=True)
            parked.write_bytes(yours)
            folders = [p for p in parked.parents if backup_dir in p.parents or p == backup_dir]
            adopt(repo, [*folders, parked])
            return parked
        if parked.read_bytes() == yours:
            return parked
        number += 1


def park_backups(repo: Path, backup_dir: Path, aliases: Iterable[str]) -> List[Path]:
    """Move every ``.bak``, ``.bak.2`` and on that an apply step left beside the given links.

    Returns the parked paths. The workspace then shows the links alone, as a fresh box does.
    """
    moved: List[Path] = []
    for alias in dict.fromkeys(aliases):
        link = repo / alias
        for backup in sorted(link.parent.glob(link.name + ".bak*")):
            if not backup.is_file() or backup.is_symlink():
                continue
            relative = backup.relative_to(repo).as_posix()
            moved.append(park_version(repo, backup_dir, relative, backup.read_bytes()))
            backup.unlink()
    return moved


def aliases_by_source(repo: Path) -> Dict[str, str]:
    """The editor link of each file a participant edits, keyed by the file's repo path."""
    try:
        entries = json.loads((repo / PARTICIPANT_FILES).read_text("utf-8"))
        return {entry["source"]: entry["alias"] for entry in entries}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def adopt(repo: Path, created: List[Path]) -> None:
    """Give what was created to the repository's owner when root created it.

    A reset or repair run with sudo would otherwise leave root-owned files the participant
    cannot save. Nothing changes unless the effective user is root and the repo is not.
    """
    if os.geteuid() != 0:
        return
    owner = repo.stat()
    if owner.st_uid == 0:
        return
    for path in created:
        if os.path.lexists(path):
            os.lchown(path, owner.st_uid, owner.st_gid)


def new_parents(repo: Path, entry: str) -> List[Path]:
    """The folders above ``entry`` that do not exist yet, outermost first."""
    missing = [p for p in reversed((repo / entry).parents)
               if repo in p.parents and not os.path.lexists(p)]
    return missing


def restore_missing(repo: Path, source: Path, entries: Iterable[str]) -> List[str]:
    """Write each entry that is absent from ``repo`` out of HEAD; never overwrite.

    Returns:
        The entries put back, in order. Entries HEAD does not hold are skipped.
    """
    restored: List[str] = []
    for entry in dict.fromkeys(entries):
        if os.path.lexists(repo / entry):
            continue
        listed = tree(source, entry)
        content = blob(source, entry) if listed else None
        if content is None:
            continue
        mode = listed[0][0]
        created = new_parents(repo, entry)
        try:
            (repo / entry).parent.mkdir(parents=True, exist_ok=True)
            if mode == SYMLINK_MODE:
                (repo / entry).symlink_to(content.decode())
            else:
                (repo / entry).write_bytes(content)
                (repo / entry).chmod(0o755 if mode == EXECUTABLE_MODE else 0o644)
        finally:
            adopt(repo, [*created, repo / entry])
        restored.append(entry)
    return restored


def missing_message(path: str, source: Path) -> str:
    """Why a required file cannot be put back, and who can help."""
    problem = history_problem(source)
    if problem:
        return (f"{path} is missing and the pinned history ({source}) cannot be read: "
                f"{problem}. Ask a facilitator for help.")
    return (f"{path} is missing and the pinned history ({source}) holds no {path} to put "
            "back. A lab reset restores a deleted file only from that history. Ask a "
            "facilitator for help.")


def not_a_file_message(path: str) -> str:
    """A link or folder stands where a lab file belongs, so a reset cannot put the file back."""
    return (f"{path} is not a file (it is a link to nothing, or a folder). A lab reset never "
            "replaces what stands there. Ask a facilitator for help.")


def head_commit(source: Path) -> Optional[str]:
    """The commit HEAD names in the pinned history, or None when it cannot be read."""
    out = _git(source, "rev-parse", "HEAD")
    return out.decode().strip() if out else None


def write_archive(source: Path, prefix: str, destination: Path) -> bool:
    """Write HEAD as a gzip tarball under ``prefix/``, as GitHub's tarball is laid out."""
    # Git's default tar.umask is 002; GitHub's tarball modes are 0644 and 0755.
    return _git(source, "-c", "tar.umask=0022", "archive", "--format=tar.gz",
                f"--prefix={prefix}/", "-o", str(destination), "HEAD") is not None
