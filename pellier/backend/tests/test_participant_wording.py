"""Participants read four verbs, never "worksheet" or "exercise".

Run (run something supplied and read it), Apply (1A to 4A, a supplied change installed by
command), Build (1B to 4B and Lab 1's optional fusion file) and Prove (the check that prints
``Lab NX check passed``). A file is never labelled a worksheet or an exercise. The rule covers
what participants read: the lab READMEs, START_HERE.md, the workshop map and SQL files, and
the messages the checks and lab_run.py print. Internal identifiers, comments in Python and
history keep their names, and a journey stage id may still be the string "exercise".
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterator, List

import pytest

REPO = Path(__file__).resolve().parents[3]
RETIRED = re.compile(r"worksheet|\bexercises?\b", re.IGNORECASE)


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
def test_participant_documents_use_the_four_verbs(path: Path) -> None:
    lines = [f"{number}: {line.strip()}"
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             if RETIRED.search(line)]
    assert lines == [], f"{path.relative_to(REPO)} still labels a file: {lines}"


@pytest.mark.parametrize("path", _printing_scripts(), ids=lambda p: p.name)
def test_printed_messages_use_the_four_verbs(path: Path) -> None:
    printed = [text for text in _message_strings(path)
               if text != "exercise" and RETIRED.search(text)]
    assert printed == [], f"{path.name} prints a retired label: {printed}"
