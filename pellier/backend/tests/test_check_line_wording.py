"""Plain words in the lines a participant reads in the terminal: box labels and cut names."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import workshop_check as check  # noqa: E402

lab1 = importlib.import_module("lab1_retry")
lab3_rls = importlib.import_module("lab3_row_ownership_check")
lab4_credit = importlib.import_module("lab4_credit")
observability = importlib.import_module("observability_check")

PRODUCT = {"name": "Cotton Tea Towel Pair, Sage, 50 x 70 cm", "price": 18, "quantity": 4,
           "category": "kitchen", "tags": []}


def test_a_lab_task_box_still_says_task() -> None:
    finding = check.Finding("1B", "title", check.PASSED, "expected", "observed")
    assert "Task 1B" in check.render(finding)


def test_a_finding_can_carry_its_own_label() -> None:
    finding = check.Finding("1", "title", check.PASSED, "expected", "observed", label="Record")
    text = check.render(finding)
    assert "Record 1" in text and "Task" not in text


def test_the_observability_boxes_are_records_not_tasks() -> None:
    class _Broken:
        def __getattr__(self, name: str):
            raise RuntimeError("no AWS here")

    findings = observability.check(_Broken(), _Broken(), _Broken(), "arn:aws:rds:x:y:cluster:c", 5)
    assert len(findings) == 3
    boxes = [check.render(finding) for finding in findings]
    for number, box in enumerate(boxes, start=1):
        assert f"Record {number}" in box and "Task" not in box
        rows = [line for line in box.splitlines() if line.startswith("\u2502")]
        assert {line.split("\u2502")[1] for line in rows} >= {" Record %d " % number}
        assert len({line.index("\u2502", 1) for line in rows}) == 1


def test_a_cut_product_name_ends_in_dots() -> None:
    rows, _ = lab1._rows(["P1"], {"P1": PRODUCT}, lab1.limits_of({}, []))
    name = rows[0][1]
    assert len(name) == 30 and name.endswith("...")


def test_a_name_of_exactly_the_column_width_is_kept_whole() -> None:
    name = "x" * 30
    assert lab1._cut(name) == name
    assert lab1._cut(name + "y") == "x" * 27 + "..."


def test_a_name_that_fits_is_not_marked() -> None:
    rows, _ = lab1._rows(["P1"], {"P1": {**PRODUCT, "name": "Tea Towel"}}, lab1.limits_of({}, []))
    assert rows[0][1] == "Tea Towel"


@pytest.mark.parametrize("module, title", [
    (lab4_credit, "the credit-writer role writes only through the function"),
    (lab3_rls, "the live policy stops a wrong query"),
])
def test_the_in_process_path_has_one_spelling(module, title: str) -> None:
    finding = module.unchecked("in-process", RuntimeError("no database"))
    assert finding.title == f"in-process path: {title}"
    assert "in-process" in module._PATHS and "in process" not in module._PATHS
    assert "in process" not in module._PATHS["in-process"]
