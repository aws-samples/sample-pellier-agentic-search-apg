#!/usr/bin/env python3
"""Restore the governed workshop exercises to their incomplete starters."""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarkerExercise:
    exercise_id: str
    starter: str
    destination: str
    marker: str


@dataclass(frozen=True)
class FileExercise:
    exercise_id: str
    starter: str
    destination: str


MARKER_EXERCISES = (
    MarkerExercise(
        exercise_id="lab-1-inventory-agent",
        starter="workshop/starters/lab-1/inventory-agent-definition.pyfrag",
        destination="pellier/backend/agents/inventory_agent.py",
        marker="WORKSHOP · Inventory Agent · definition",
    ),
    MarkerExercise(
        exercise_id="lab-1-inventory-tool",
        starter="workshop/starters/lab-1/check-inventory-tool.pyfrag",
        destination="pellier/backend/services/agent_tools.py",
        marker="WORKSHOP · Inventory Agent · check_inventory",
    ),
    MarkerExercise(
        exercise_id="lab-2-preserve-requirements",
        starter="workshop/starters/lab-2/preserve-requirements.pyfrag",
        destination="pellier/backend/services/search_plan.py",
        marker="WORKSHOP · Search plan · preserve requirements",
    ),
    MarkerExercise(
        exercise_id="lab-3-gateway-catalogue",
        starter="workshop/starters/lab-3/gateway-published-tools.pyfrag",
        destination="scripts/deploy/gateway_tool_schemas.py",
        marker="WORKSHOP · Gateway catalogue · published tools",
    ),
    MarkerExercise(
        exercise_id="lab-3-support-reconcile",
        starter="workshop/starters/lab-3/support-reconcile.pyfrag",
        destination="pellier/backend/services/agentcore_gateway.py",
        marker="WORKSHOP · Managed catalogue · support reconcile",
    ),
)

FILE_EXERCISES = (
    FileExercise(
        exercise_id="lab-4-rls",
        starter="workshop/starters/lab-4-rls.sql",
        destination="workshop/lab-4-rls.sql",
    ),
    FileExercise(
        exercise_id="lab-2-rrf",
        starter="workshop/starters/lab-2-rrf.sql",
        destination="workshop/lab-2-rrf.sql",
    ),
    FileExercise(
        exercise_id="lab-4-absence",
        starter="workshop/starters/lab-4-absence.sql",
        destination="workshop/lab-4-absence.sql",
    ),
    FileExercise(
        exercise_id="lab-4-cedar",
        starter="workshop/starters/workshop_identity_match_forbid.cedar",
        destination="policies/workshop_identity_match_forbid.cedar",
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


def _check(repo: Path) -> list[str]:
    mismatches: list[str] = []
    for exercise in MARKER_EXERCISES:
        starter = _read(repo / exercise.starter).rstrip()
        destination = _read(repo / exercise.destination)
        if _marker_body(destination, exercise.marker) != starter:
            mismatches.append(exercise.exercise_id)
        else:
            print(f"starter {exercise.exercise_id}: ready")

    for exercise in FILE_EXERCISES:
        starter = (repo / exercise.starter).read_bytes()
        destination_path = repo / exercise.destination
        if not destination_path.is_file() or destination_path.read_bytes() != starter:
            mismatches.append(exercise.exercise_id)
        else:
            print(f"starter {exercise.exercise_id}: ready")
    return mismatches


def _restore(repo: Path) -> None:
    for exercise in MARKER_EXERCISES:
        starter = _read(repo / exercise.starter)
        destination_path = repo / exercise.destination
        destination = _read(destination_path)
        destination_path.write_text(
            _restore_marker(destination, starter, exercise.marker),
            encoding="utf-8",
        )
        print(f"restored {exercise.exercise_id}: {exercise.destination}")

    for exercise in FILE_EXERCISES:
        starter_path = repo / exercise.starter
        destination_path = repo / exercise.destination
        if not starter_path.is_file():
            raise FileNotFoundError(starter_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(starter_path, destination_path)
        print(f"restored {exercise.exercise_id}: {exercise.destination}")


def main() -> int:
    parser = argparse.ArgumentParser()
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
            mismatches = _check(repo)
            if mismatches:
                print(
                    "participant exercises are not at starter state: "
                    + ", ".join(mismatches),
                    file=sys.stderr,
                )
                return 1
            return 0

        _restore(repo)
        mismatches = _check(repo)
        if mismatches:
            print(
                "participant exercise reset failed: " + ", ".join(mismatches),
                file=sys.stderr,
            )
            return 1
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"participant exercise reset failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
