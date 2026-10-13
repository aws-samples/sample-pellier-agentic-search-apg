"""Every task has one check command of one shape: ``python3 scripts/labN_check.py --task NX``.

Labs 2 and 3 keep both tasks' checks in their own script; Labs 1 and 4 route each task to
its sibling module. The task is always named, and the names the shape replaced stay gone.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

ROUTES = {"lab1_check": {"1A": "lab1_vector", "1B": "lab1_retry"},
          "lab4_check": {"4A": "lab4_policy", "4B": "lab4_credit"}}
RETIRED = ("lab1_vector_check", "lab1_compare", "lab2_contract_check", "lab4_policy_check",
           "lab4_credit_check", "lab3_rls_check", "lab3_memory_namespaces", "lab-3-rls",
           "lab-1-rrf", "lab-1-hnsw", "go-deeper-rrf", "WORKSHOP_DEFERRED_TOOLS",
           "SUPPORT_MANAGED_TOOLS", "support reconcile", "_with_relaxations")


@pytest.mark.parametrize(("command", "task"), [(c, t) for c, r in ROUTES.items() for t in r])
def test_each_task_runs_its_own_module(command: str, task: str, monkeypatch) -> None:
    dispatcher = importlib.import_module(command)
    module = importlib.import_module(ROUTES[command][task])
    seen = []
    monkeypatch.setattr(module, "main", lambda argv: seen.append(list(argv)) or 0)
    assert dispatcher.main(["--task", task]) == 0
    assert seen == [[]]


@pytest.mark.parametrize("command", ["lab1_check", "lab2_check", "lab3_check", "lab4_check"])
def test_the_task_is_always_named(command: str, capsys) -> None:
    with pytest.raises(SystemExit) as stopped:
        importlib.import_module(command).main([])
    assert stopped.value.code == 2
    assert "--task" in capsys.readouterr().err


def test_the_check_commands_are_the_four_labs_and_one_helper() -> None:
    names = sorted(path.stem for path in SCRIPTS.glob("lab*_check.py"))
    assert names == ["lab1_check", "lab2_check", "lab3_check", "lab3_row_ownership_check",
                     "lab4_check"]


def test_the_task_modules_are_not_commands() -> None:
    for module in ("lab1_vector", "lab1_retry", "lab4_policy", "lab4_credit"):
        text = (SCRIPTS / f"{module}.py").read_text(encoding="utf-8")
        assert '__name__ == "__main__"' not in text, module
        assert not text.startswith("#!"), module


def test_no_replaced_name_survives_outside_the_history() -> None:
    tracked = subprocess.run(["git", "grep", "-l", "-E", "|".join(RETIRED), "--", ".",
                              ":!docs/release-readiness", ":!docs/superpowers",
                              ":!pellier/backend/tests/test_lab_checks.py"],
                             cwd=REPO, capture_output=True, text=True)
    assert tracked.stdout.strip() == "", tracked.stdout
