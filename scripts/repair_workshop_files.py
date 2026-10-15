#!/usr/bin/env python3
"""Put every tracked workshop file back to the revision this box was built from.

A workshop box has no git checkout: bootstrap clones the pinned revision, records it in
``.workshop-ref.json`` and deletes ``.git``. A participant who edits or deletes a file
outside the marked regions therefore has nothing to ``git checkout`` from. This command
downloads that exact revision's tarball and writes back every file that differs or is
missing, so the tree matches the pin again.

    python3 scripts/repair_workshop_files.py            repair the files
    python3 scripts/repair_workshop_files.py --check    count what differs, change nothing

The full reset (scripts/reset-governed-workshop.sh) runs this first, before it rebuilds the
database.

It restores only what the pin contains. A file the participant created is left alone, and
the paths in ``PRESERVED`` (environment files, the AgentCore project, build output, the
virtual environment) are never read from the tarball or written. Each file is replaced
atomically, so a script that is running while it is replaced keeps reading its old copy.

Exit status: 0 repaired or already matching, 3 the revision could not be downloaded or
verified (the tree is untouched), 1 any other failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

REPO = Path(__file__).resolve().parents[1]
GITHUB_REPO = "aws-samples/sample-pellier-agentic-search-apg"
TARBALL_URL = "https://codeload.github.com/" + GITHUB_REPO + "/tar.gz/{sha}"
REF_FILE = ".workshop-ref.json"
DOWNLOAD_TIMEOUT_SECONDS = 60
EXIT_UNAVAILABLE = 3

# Runtime state that bootstrap or the participant's tools write inside the repository.
# Nothing here is ever overwritten, whatever the tarball holds. A path names a file, or
# a directory and everything under it.
PRESERVED = (
    ".env",
    ".provision.env",
    ".workshop-ref.json",
    ".agentcore-project",
    ".vscode",
    ".local",
    "pellier/start-backend.sh",
    "pellier/config/mcp-server-config.json",
    "pellier/frontend/.env",
    "pellier/frontend/dist",
    "pellier/frontend/node_modules",
    "pellier/backend/.env",
    "pellier/backend/.venv",
)
# Directories that are caches wherever they sit.
PRESERVED_ANYWHERE = ("__pycache__", "node_modules", ".venv")

RESTART_PATTERN = re.compile(r"^(pellier/backend/.*\.py|skills/.*)$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class RepairUnavailable(Exception):
    """The pinned revision could not be found, downloaded or verified; nothing was written."""


@dataclass
class Report:
    """What a repair did, in files."""

    restored: list[str] = field(default_factory=list)
    recreated: list[str] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def repaired(self) -> int:
        return len(self.restored) + len(self.recreated)


def is_preserved(relative: str) -> bool:
    """Whether a repository-relative path is runtime state that a repair must not touch."""
    parts = PurePosixPath(relative).parts
    if any(part in PRESERVED_ANYWHERE for part in parts):
        return True
    return any(
        relative == kept or relative.startswith(kept + "/") for kept in PRESERVED
    )


def pinned_sha(repo: Path) -> str:
    """The revision ``.workshop-ref.json`` records.

    Raises:
        RepairUnavailable: the file is missing or unreadable, or holds no full commit SHA.
    """
    path = repo / REF_FILE
    try:
        recorded = str(json.loads(path.read_text(encoding="utf-8")).get("resolved_sha", ""))
    except (OSError, ValueError, AttributeError) as exc:
        raise RepairUnavailable(f"cannot read the pinned revision from {path}: {exc}") from exc
    if not SHA_PATTERN.match(recorded):
        raise RepairUnavailable(
            f"{path} records resolved_sha {recorded!r}, which is not a 40-character commit"
        )
    return recorded


def download_tarball(sha: str, destination: Path) -> None:
    """Fetch the tarball for ``sha`` to ``destination``.

    Raises:
        RepairUnavailable: no network, GitHub refused, or the download was cut short.
    """
    url = TARBALL_URL.format(sha=sha)
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with destination.open("wb") as out:
                shutil.copyfileobj(response, out)
    except (OSError, urllib.error.URLError) as exc:
        raise RepairUnavailable(f"cannot download {url}: {exc}") from exc


def _safe_relative(name: str) -> str | None:
    """The member path below the top-level directory, or None for the directory itself.

    Raises:
        RepairUnavailable: the path would leave the repository.
    """
    parts = PurePosixPath(name).parts[1:]
    if not parts:
        return None
    if PurePosixPath(name).is_absolute() or ".." in parts:
        raise RepairUnavailable(f"the tarball holds an unsafe path: {name}")
    return "/".join(parts)


def verified_members(archive: tarfile.TarFile, sha: str) -> Iterator[tuple[str, tarfile.TarInfo]]:
    """Each file or symlink in the tarball with its repository path, after the SHA check.

    The archive must have exactly one top-level directory, named ``<repo>-<sha>``, and a
    pax comment, when present, must name the same commit.

    Raises:
        RepairUnavailable: the archive is not the pinned revision.
    """
    members = archive.getmembers()
    tops = {PurePosixPath(m.name).parts[0] for m in members if PurePosixPath(m.name).parts}
    expected = GITHUB_REPO.split("/")[1] + "-" + sha
    if tops != {expected}:
        raise RepairUnavailable(
            f"the tarball's top-level directory is {sorted(tops)}, expected {expected!r}; "
            "it is not the pinned revision"
        )
    comment = str(archive.pax_headers.get("comment", ""))
    if comment and comment != sha:
        raise RepairUnavailable(f"the tarball names commit {comment}, expected {sha}")
    for member in members:
        relative = _safe_relative(member.name)
        if relative is not None and (member.isfile() or member.issym()):
            yield relative, member


def _same(target: Path, member: tarfile.TarInfo, archive: tarfile.TarFile) -> bool:
    if member.issym():
        return target.is_symlink() and os.readlink(target) == member.linkname
    if target.is_symlink() or not target.is_file():
        return False
    if (target.stat().st_mode & 0o777) != (member.mode & 0o777):
        return False
    source = archive.extractfile(member)
    if source is None:
        return False
    with source, target.open("rb") as current:
        return source.read() == current.read()


def _write(target: Path, member: tarfile.TarInfo, archive: tarfile.TarFile) -> None:
    """Replace ``target`` with the member, atomically, keeping a symlink or the file's mode."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.repair-{os.getpid()}")
    try:
        if member.issym():
            os.symlink(member.linkname, temporary)
        else:
            source = archive.extractfile(member)
            if source is None:
                raise OSError(f"cannot read {member.name} from the tarball")
            with source, temporary.open("wb") as out:
                shutil.copyfileobj(source, out)
            temporary.chmod(member.mode & 0o777)
        os.replace(temporary, target)
    finally:
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink()


def apply_archive(repo: Path, archive: tarfile.TarFile, sha: str, write: bool = True) -> Report:
    """Compare every tracked file with the repository and, when ``write``, restore the rest.

    Raises:
        RepairUnavailable: the archive is not the pinned revision.
    """
    report = Report()
    for relative, member in verified_members(archive, sha):
        if is_preserved(relative):
            continue
        target = repo / relative
        if target.is_dir() and not target.is_symlink():
            report.skipped.append(f"{relative} (a directory is in its place)")
            continue
        if _same(target, member, archive):
            report.unchanged += 1
            continue
        existed = target.is_symlink() or target.exists()
        (report.restored if existed else report.recreated).append(relative)
        if write:
            _write(target, member, archive)
    return report


def repair(
    repo: Path,
    write: bool = True,
    fetch: Callable[[str, Path], None] | None = None,
) -> Report:
    """Download the pinned revision and restore every tracked file that differs.

    Args:
        repo: The repository root.
        write: False counts what differs without changing anything.
        fetch: Writes the tarball for a SHA to a path; defaults to the GitHub download.

    Raises:
        RepairUnavailable: the revision is unknown, cannot be downloaded or is not the pin.
    """
    sha = pinned_sha(repo)
    with tempfile.TemporaryDirectory(prefix="pellier-repair-") as scratch:
        tarball = Path(scratch) / "revision.tar.gz"
        (fetch or download_tarball)(sha, tarball)
        try:
            with tarfile.open(tarball, "r:gz") as archive:
                return apply_archive(repo, archive, sha, write)
        except (tarfile.TarError, EOFError) as exc:
            raise RepairUnavailable(f"the downloaded tarball is unreadable: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo", type=Path, default=REPO, help="repository root")
    parser.add_argument("--check", action="store_true", help="count differences, write nothing")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser().resolve()
    try:
        sha = pinned_sha(repo)
        print(f"Pinned revision {sha[:12]}: downloading its tarball", flush=True)
        report = repair(repo, write=not args.check)
    except RepairUnavailable as exc:
        print(f"workshop files NOT repaired: {exc}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except OSError as exc:
        print(f"workshop file repair failed: {exc}", file=sys.stderr)
        return 1
    verb = "differ from" if args.check else "restored to"
    print(
        f"{report.repaired} file(s) {verb} the pin: {len(report.restored)} changed, "
        f"{len(report.recreated)} missing; {report.unchanged} already matched",
        flush=True,
    )
    for relative in [*report.restored, *report.recreated][:20]:
        print(f"  {relative}", flush=True)
    for line in report.skipped:
        print(f"  skipped {line}", file=sys.stderr, flush=True)
    changed = [*report.restored, *report.recreated]
    if not args.check and any(RESTART_PATTERN.match(path) for path in changed):
        print("  Next: restart the backend (sudo systemctl restart pellier) so it runs the "
              "restored code.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
