"""Participants read "exercise" and "query", never "worksheet".

A SQL file a participant edits and runs, which commits only when its probes pass, is an
exercise; one they only run and read is a query. The rule covers what participants read:
the lab READMEs, START_HERE.md, the workshop map and SQL files, and the messages the checks
and lab_run.py print. Internal identifiers, comments in Python and history keep their names.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List

import pytest

REPO = Path(__file__).resolve().parents[3]
RETIRED = "worksheet"


def _documents() -> List[Path]:
    paths = [REPO / "START_HERE.md", REPO / "workshop" / "README.md"]
    paths += sorted(REPO.glob("labs/*/README.md")) + sorted(REPO.glob("labs/*/solution/README.md"))
    paths += sorted((REPO / "workshop").glob("*.sql"))
    return paths


def _printing_scripts() -> List[Path]:
    scripts = REPO / "scripts"
    return sorted(scripts.glob("lab*_check.py")) + [scripts / "lab4_credit.py",
                                                     scripts / "lab_run.py"]


def _docstrings(tree: ast.AST) -> Iterator[ast.Constant]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                yield body[0].value


def _message_strings(path: Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node) for node in _docstrings(tree)}
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def test_the_rule_covers_every_file_it_names() -> None:
    assert len(_documents()) > 15
    assert all(path.is_file() for path in _documents() + _printing_scripts())


@pytest.mark.parametrize("path", _documents(), ids=lambda p: str(p.relative_to(REPO)))
def test_participant_documents_say_exercise_or_query(path: Path) -> None:
    lines = [f"{number}: {line.strip()}"
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             if RETIRED in line.lower()]
    assert lines == [], f"{path.relative_to(REPO)} still says {RETIRED}"


@pytest.mark.parametrize("path", _printing_scripts(), ids=lambda p: p.name)
def test_printed_messages_say_exercise_or_query(path: Path) -> None:
    printed = [text for text in _message_strings(path) if RETIRED in text.lower()]
    assert printed == [], f"{path.name} prints {RETIRED}"
