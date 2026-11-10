"""A Python edit that does not parse stops the backend from starting.

Event 2026-11-10: Task 1B's Solution line, pasted at column 0 inside an indented method, was an
IndentationError. ``lab_run.py restart`` waited 120 seconds and said only that the backend was
not healthy. The restart and the health wait now name the file, the line and the way out.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import lab_run  # noqa: E402

BROKEN = ("class SearchPlan:\n"
          "    def _next_attempt(self, relaxations):\n"
          "        # START\n"
          "return replace(self, relaxations=list(relaxations))\n")


def _repo(tmp_path: Path, text: str) -> Path:
    files = [{"alias": "labs/01-retrieve/1B-search-plan.py",
              "source": "pellier/backend/services/search_plan.py",
              "solution": "solutions/lab-1-retrieve/retrieval/search_plan_solution.py"},
             {"alias": "labs/02-ground/2B-check-stock.sql",
              "source": "workshop/lab-2-check-stock.sql",
              "solution": "solutions/lab-2-ground/sql/lab-2-check-stock-solution.sql"}]
    (tmp_path / "workshop").mkdir()
    (tmp_path / "workshop" / "participant-files.json").write_text(json.dumps(files))
    (tmp_path / "workshop" / "lab-2-check-stock.sql").write_text("not python at all (\n")
    source = tmp_path / "pellier" / "backend" / "services" / "search_plan.py"
    source.parent.mkdir(parents=True)
    source.write_text(text)
    return tmp_path


def test_a_line_pasted_at_the_wrong_indentation_is_named(tmp_path: Path) -> None:
    problem = lab_run.python_edit_problem(_repo(tmp_path, BROKEN))
    assert problem is not None
    assert "labs/01-retrieve/1B-search-plan.py, line 4" in problem
    assert "IndentationError" in problem
    assert "uv run scripts/lab_run.py solution --lab 1 --task 1B" in problem


def test_files_that_parse_and_files_that_are_not_python_raise_nothing(tmp_path: Path) -> None:
    assert lab_run.python_edit_problem(_repo(tmp_path, "x = 1\n")) is None


def test_a_restart_refuses_at_once_instead_of_waiting_on_a_backend_that_cannot_start(
        tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lab_run, "REPO", _repo(tmp_path, BROKEN))
    ran = []
    with pytest.raises(lab_run.LabRunError) as refused:
        lab_run.restart_backend(lab_run.Backend("http://localhost:1"), run=ran.append)
    assert ran == []
    assert "IndentationError" in str(refused.value)


def test_the_repository_as_shipped_has_no_such_problem() -> None:
    assert lab_run.python_edit_problem() is None
