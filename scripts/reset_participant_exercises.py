#!/usr/bin/env python3
"""Restore the governed workshop task files to their incomplete starters.

This restores files. The live database state the SQL files commit (Task 2B's
pellier.check_stock, Task 3B's row policies, Task 4B's credit-writer privileges) is
restored by the schema rebuild in scripts/setup/database-reset.sh, which
reset-governed-workshop.sh runs first: scripts/migrations/001_schema.sql installs each
as shipped. ``--lab N`` restores one lab's files only; scripts/lab_reset.py (run by
``lab_run.py reset --lab N``) adds that lab's database piece and managed state.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_reference  # noqa: E402  (sibling module)

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MarkerExercise:
    exercise_id: str
    lab: int
    starter: str
    destination: str
    marker: str


@dataclass(frozen=True)
class FileExercise:
    exercise_id: str
    lab: int
    starter: str
    destination: str


MARKER_EXERCISES = (
    MarkerExercise(
        exercise_id="lab-1-vector-branch",
        lab=1,
        starter="workshop/starters/lab-1/vector-branch.pyfrag",
        destination="pellier/backend/services/store_tools.py",
        marker="WORKSHOP - Vector branch - order by meaning",
    ),
    MarkerExercise(
        exercise_id="lab-2-stock-agent",
        lab=2,
        starter="workshop/starters/lab-2/stock-agent-definition.pyfrag",
        destination="pellier/backend/agents/stock_agent.py",
        marker="WORKSHOP - Stock agent - definition",
    ),
    MarkerExercise(
        exercise_id="lab-1-preserve-requirements",
        lab=1,
        starter="workshop/starters/lab-1/preserve-requirements.pyfrag",
        destination="pellier/backend/services/search_plan.py",
        marker="WORKSHOP - Search plan - preserve requirements",
    ),
    MarkerExercise(
        exercise_id="lab-3-gateway-catalogue",
        lab=3,
        starter="workshop/starters/lab-3/gateway-published-tools.pyfrag",
        destination="scripts/deploy/gateway_tool_schemas.py",
        marker="WORKSHOP - Gateway catalogue - published tools",
    ),
    MarkerExercise(
        exercise_id="lab-3-support-gateway-tools",
        lab=3,
        starter="workshop/starters/lab-3/support-gateway-tools.pyfrag",
        destination="pellier/backend/services/agentcore_gateway.py",
        marker="WORKSHOP - Support agent - Gateway tools",
    ),
)

FILE_EXERCISES = (
    FileExercise(
        exercise_id="lab-2-check-stock",
        lab=2,
        starter="workshop/starters/lab-2-check-stock.sql",
        destination="workshop/lab-2-check-stock.sql",
    ),
    FileExercise(
        exercise_id="lab-3-row-ownership",
        lab=3,
        starter="workshop/starters/lab-3-row-ownership.sql",
        destination="workshop/lab-3-row-ownership.sql",
    ),
    FileExercise(
        exercise_id="lab-1-fusion",
        lab=1,
        starter="workshop/starters/lab-1-fusion.sql",
        destination="workshop/lab-1-fusion.sql",
    ),
    FileExercise(
        exercise_id="lab-4-cedar",
        lab=4,
        starter="workshop/starters/workshop_credit_limit.cedar",
        destination="policies/workshop_credit_limit.cedar",
    ),
    FileExercise(
        exercise_id="lab-4-credit-writer",
        lab=4,
        starter="workshop/starters/lab-4-credit-writer.sql",
        destination="workshop/lab-4-credit-writer.sql",
    ),
)


def _marker_bounds(text: str, marker: str) -> tuple[int, int, int, int]:
    start_token = f"# === {marker}: START ==="
    end_token = f"# === {marker}: END ==="
    if text.count(start_token) != 1 or text.count(end_token) != 1:
        raise ValueError(f"expected one marker pair for {marker!r}")

    start = text.index(start_token)
    start_line_end = text.index("\n", start) + 1
    end_token_start = text.index(end_token, start_line_end)
    end = text.rfind("\n", start_line_end, end_token_start) + 1
    end_line_end = text.find("\n", end_token_start)
    if end_line_end == -1:
        end_line_end = len(text)
    else:
        end_line_end += 1
    return start, start_line_end, end, end_line_end


def _marker_body(text: str, marker: str) -> str:
    _start, body_start, body_end, _end = _marker_bounds(text, marker)
    return text[body_start:body_end].rstrip()


def _restore_marker(destination: str, starter_body: str, marker: str) -> str:
    _start, body_start, body_end, _end = _marker_bounds(destination, marker)
    return (
        destination[:body_start]
        + starter_body.rstrip("\n")
        + "\n"
        + destination[body_end:]
    )


def _read(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def exercises_for(lab: int | None) -> tuple[tuple[MarkerExercise, ...], tuple[FileExercise, ...]]:
    """The marker and file tasks of one lab, or of every lab when ``lab`` is None."""
    if lab is None:
        return MARKER_EXERCISES, FILE_EXERCISES
    if lab not in {exercise.lab for exercise in (*MARKER_EXERCISES, *FILE_EXERCISES)}:
        raise ValueError(f"no participant task files for Lab {lab}")
    return (
        tuple(e for e in MARKER_EXERCISES if e.lab == lab),
        tuple(e for e in FILE_EXERCISES if e.lab == lab),
    )


def _check(repo: Path, lab: int | None = None) -> list[str]:
    markers, files = exercises_for(lab)
    mismatches: list[str] = []
    for exercise in markers:
        starter = _read(repo / exercise.starter).rstrip()
        destination = _read(repo / exercise.destination)
        if _marker_body(destination, exercise.marker) != starter:
            mismatches.append(exercise.exercise_id)
        else:
            print(f"{exercise.exercise_id}: as shipped, ready")

    for exercise in files:
        starter = (repo / exercise.starter).read_bytes()
        destination_path = repo / exercise.destination
        if not destination_path.is_file() or destination_path.read_bytes() != starter:
            mismatches.append(exercise.exercise_id)
        else:
            print(f"{exercise.exercise_id}: as shipped, ready")
    return mismatches


def _restore(repo: Path, lab: int | None = None) -> None:
    markers, files = exercises_for(lab)
    for exercise in markers:
        starter = _read(repo / exercise.starter)
        destination_path = repo / exercise.destination
        destination = _read(destination_path)
        destination_path.write_text(
            _restore_marker(destination, starter, exercise.marker),
            encoding="utf-8",
        )
        print(f"restored {exercise.exercise_id}: {exercise.destination}")

    for exercise in files:
        starter_path = repo / exercise.starter
        destination_path = repo / exercise.destination
        if not starter_path.is_file():
            raise FileNotFoundError(starter_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(starter_path, destination_path)
        print(f"restored {exercise.exercise_id}: {exercise.destination}")


def _labs(lab: int | None) -> tuple[int, ...]:
    return tuple(lab_reference.LAB_FOLDERS) if lab is None else (lab,)


def put_back_deleted_files(repo: Path, lab: int | None, source: Path | None = None) -> list[str]:
    """Restore the lab's deleted files from the pinned history; never overwrite a file.

    Covers the lab's ``labs/0N-*`` entries (links, README, solution aliases), the files those
    links point at (a deleted application module returns whole, so its marked region is its
    starter), and the lab's starters and destinations.

    Raises:
        FileNotFoundError: a starter or destination is still missing; the pinned history
            holds no copy of it.
    """
    source = source or lab_reference.source_dir()
    markers, files = exercises_for(lab)
    needed = [path for e in (*markers, *files) for path in (e.starter, e.destination)]
    entries = [lab_reference.PARTICIPANT_FILES, *needed]
    for number in _labs(lab):
        entries += lab_reference.lab_entries(source, number)
    restored = lab_reference.restore_missing(repo, source, entries)
    for path in restored:
        print(f"put back {path} from the pinned history; edits you made to it are gone")
    for path in needed:
        if not (repo / path).is_file():
            message = (lab_reference.not_a_file_message(path) if os.path.lexists(repo / path)
                       else lab_reference.missing_message(path, source))
            raise lab_reference.LabFileMissing(message)
    return restored


def restore_lab(repo: Path, lab: int | None = None, source: Path | None = None) -> list[str]:
    """Restore one lab's files (every lab's when None); return the exercise ids restored.

    Raises:
        ValueError: the lab has no participant task files, or a marker pair is damaged.
        FileNotFoundError: a file is missing and the pinned history cannot bring it back.
        RuntimeError: a file still differs from its starter after the restore.
    """
    exercises_for(lab)
    put_back_deleted_files(repo, lab, source)
    _restore(repo, lab)
    mismatches = _check(repo, lab)
    if mismatches:
        raise RuntimeError("participant task file reset failed: " + ", ".join(mismatches))
    markers, files = exercises_for(lab)
    return [exercise.exercise_id for exercise in (*markers, *files)]


def _lab_paths(repo: Path, lab: int, solutions: bool) -> tuple[list[str], list[str]]:
    """The files and the editor links the lab's commands read, each in the order a gap is named."""
    markers, files = exercises_for(lab)
    paths = [e.destination for e in (*markers, *files)] + [e.starter for e in (*markers, *files)]
    listing = repo / lab_reference.PARTICIPANT_FILES
    if not listing.is_file():
        return [lab_reference.PARTICIPANT_FILES, *paths], []
    mine = [entry for entry in json.loads(listing.read_text(encoding="utf-8"))
            if entry["alias"].startswith(f"labs/0{lab}-")]
    if solutions:
        paths += [entry["solution"] for entry in mine]
    return paths, [entry["alias"] for entry in mine]


def lab_gap(lab: int, repo: Path | None = None, solutions: bool = False) -> str | None:
    """The FILE MISSING line for the first lab file that is gone, or None when all are there.

    A link to nothing where a file belongs counts as gone: reading it would fail the same way.
    A reset cannot fix that case, so it gets the facilitator message, not the reset command.
    """
    repo = repo or REPO
    files, aliases = _lab_paths(repo, lab, solutions)
    gone = [p for p in files if not (repo / p).is_file()]
    gone += [p for p in aliases if not os.path.lexists(repo / p)]
    if not gone:
        return None
    if os.path.lexists(repo / gone[0]):
        return f"Lab {lab}: {lab_reference.not_a_file_message(gone[0])}"
    return (f"Lab {lab}: FILE MISSING ({gone[0]}). Next: run uv run scripts/lab_run.py "
            f"reset --lab {lab} to put back its starting code; your edits to that file "
            "are gone either way.")


def refuse_if_gap(lab: int, repo: Path | None = None, solutions: bool = False) -> bool:
    """Print the FILE MISSING line and return True when a file the lab's commands read is gone."""
    message = lab_gap(lab, repo, solutions)
    if message:
        print(message, flush=True)
    return message is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lab",
        type=int,
        choices=(1, 2, 3, 4),
        help="Restore or check only this lab (default: every lab)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Pellier governed repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify starter state without writing files",
    )
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()

    try:
        if args.check:
            if any(refuse_if_gap(number, repo) for number in _labs(args.lab)):
                return 1
            mismatches = _check(repo, args.lab)
            if mismatches:
                print(
                    "participant task files are not as shipped: "
                    + ", ".join(mismatches),
                    file=sys.stderr,
                )
                return 1
            return 0

        restore_lab(repo, args.lab)
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"participant task file reset failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
