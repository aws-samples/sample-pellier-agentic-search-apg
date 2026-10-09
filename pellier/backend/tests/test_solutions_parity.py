"""test_solutions_parity.py — drop-in solutions contract.

The workshop's core promise to participants:

  ``⏩ SHORT ON TIME? Run:
     cp solutions/<module-name>/<path> pellier/backend/<path>``

If that ``cp`` command leaves the app in a broken or inconsistent
state, the workshop flow silently breaks — participants paste a
stale solution, restart uvicorn, and the verification step fails
with no obvious cause. This test is the CI tripwire for that
contract.

Workshop solution contract
--------------------------

Lab 2 has two starters that run and fail visibly: the Stock agent
definition in ``agents/stock_agent.py`` connects only the catalog tools, none
of which reads ``warehouse_inventory``, and ``check_stock`` in
``services/agent_tools.py`` folds not_found into zero. The copy solutions are drop-ins that make each stage
safe to recover during a live room.

What this test enforces
-----------------------

For every ``(live_path, solution_path)`` pair:

  1. Both files exist.
  2. Both files parse as valid Python (``ast.parse`` smoke).
  3. Builder-preapply matches the live starter module outside the marked
     ``check_stock`` challenge block.
  4. Both recovery files expose the same public ``@tool`` functions and
     signatures as the live module.
  5. The wired solution differs from live only inside the marked
     ``check_stock`` challenge block.
  6. The starter fragments are the shipped starters' regions.
  7. The wired solution keeps the ``product_query`` signature and returns
     ``store_tools.check_stock(_run_sql, product_query=...)`` unchanged.

Scope table
-----------

Pairs are hard-coded below. Add new workshop challenges by extending
``_PAIRS`` — the test parametrizes across it automatically.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------

# tests/test_solutions_parity.py → parents[0]=tests, [1]=backend,
# [2]=pellier, [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "pellier" / "backend"
_SOLUTIONS = _REPO_ROOT / "solutions"


# ---------------------------------------------------------------------------
# (challenge_label, live_file, solution_file)
# ---------------------------------------------------------------------------

_PAIRS = [
    (
        "stock-agent-definition",
        _BACKEND / "agents" / "stock_agent.py",
        _SOLUTIONS / "waking-the-stock-keeper" / "agents" / "stock_agent_solution.py",
    ),
    (
        "stock-tool",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_check_stock_solution.py",
    ),
    (
        "stock-tool-builders-preapply",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_builders_preapply.py",
    ),
]


# ---------------------------------------------------------------------------
# Bootstrap auto-applied files (bootstrap-labs.sh ``copy_solution`` block).
#
# These are NOT participant-edited "drop-in" solutions — bootstrap copies
# each one OVER its backend twin at provision time (``cp solution backend``),
# so the app the participant lands on IS the solution copy. The contract is
# therefore stricter than the _PAIRS contract above: the solution file MUST
# be byte-identical to the live backend file, or a freshly-provisioned box
# silently boots stale code.
#
# The copy block is gated on ``WORKSHOP_FORMAT=builders``. A governed box
# skips it entirely ("preserving Stock agent and check_stock scaffolds"),
# so a desync cannot clobber a governed provision — but byte-identity is
# still enforced here because the builders format runs from this same
# branch and the files double as documented recovery drop-ins.
#
# ``agent_tools_builders_preapply.py`` is checked separately below. It is a
# full-module bootstrap replacement and must match the live starter file
# everywhere *outside* the ``check_stock`` markers. The body itself is the
# exercise, so it is masked out — a participant who completes the lab must
# not turn the suite red.
#
# Direction of truth: the BACKEND file is canonical (the full test suite runs
# against it). If this test fails, re-sync with:
#     cp pellier/backend/<path> solutions/<module>/<path>
# ---------------------------------------------------------------------------

# `agentcore_gateway.py` is deliberately absent: on the governed lineage it
# carries Lab 3b's marker region, so its solution twin holds the RECONCILED
# support contract and must differ from the shipped starter. Bootstrap does not
# copy it here; `reset_participant_exercises.py` owns its starter state, and
# `tests/test_workshop_marker_contract.py` asserts both ends of that contract.
_AUTO_APPLIED_IDENTICAL = [
    ("agentcore_runtime", _BACKEND / "services" / "agentcore_runtime.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_runtime.py"),
    ("agentcore_memory", _BACKEND / "services" / "agentcore_memory.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_memory.py"),
    ("agentcore_identity", _BACKEND / "services" / "agentcore_identity.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_identity.py"),
    ("cognito_auth", _BACKEND / "services" / "cognito_auth.py",
     _SOLUTIONS / "the-ledger" / "services" / "cognito_auth.py"),
    ("otel_trace_extractor", _BACKEND / "services" / "otel_trace_extractor.py",
     _SOLUTIONS / "the-ledger" / "services" / "otel_trace_extractor.py"),
]


@pytest.mark.parametrize(
    "label, backend_path, solution_path",
    _AUTO_APPLIED_IDENTICAL,
    ids=[p[0] for p in _AUTO_APPLIED_IDENTICAL],
)
def test_auto_applied_solution_matches_backend(
    label: str, backend_path: Path, solution_path: Path
) -> None:
    """Bootstrap cp's each of these solution files over its backend twin.

    They MUST be byte-identical, or a freshly-provisioned environment boots
    stale code that the full test suite (which runs against the backend copy)
    never exercises. This is the CI tripwire for solutions-parity drift on
    the auto-applied set.
    """
    assert backend_path.exists(), (
        f"[{label}] backend file missing: {backend_path.relative_to(_REPO_ROOT)}"
    )
    assert solution_path.exists(), (
        f"[{label}] solution file missing: {solution_path.relative_to(_REPO_ROOT)}"
    )
    backend_src = backend_path.read_text()
    solution_src = solution_path.read_text()
    assert solution_src == backend_src, (
        f"[{label}] bootstrap auto-applies this solution over the backend, but "
        f"the two have DRIFTED. A fresh-provisioned box would boot the stale "
        f"solution copy. Re-sync with:\n"
        f"    cp {backend_path.relative_to(_REPO_ROOT)} "
        f"{solution_path.relative_to(_REPO_ROOT)}"
    )


@pytest.mark.parametrize(
    "label, live_path, solution_path",
    _PAIRS,
    ids=[p[0] for p in _PAIRS],
)
def test_both_files_exist(label: str, live_path: Path, solution_path: Path) -> None:
    """Both the live challenge file and its solution file MUST exist."""
    assert live_path.exists(), (
        f"[{label}] Live challenge file missing: "
        f"{live_path.relative_to(_REPO_ROOT)}"
    )
    assert solution_path.exists(), (
        f"[{label}] Solution drop-in missing: "
        f"{solution_path.relative_to(_REPO_ROOT)}"
    )


@pytest.mark.parametrize(
    "label, live_path, solution_path",
    _PAIRS,
    ids=[p[0] for p in _PAIRS],
)
def test_both_files_parse_as_python(label: str, live_path: Path, solution_path: Path) -> None:
    """Both files MUST parse as valid Python.

    Participants will run the live file through uvicorn's hot-reload;
    the solution file will be cp'd in when they run the fallback
    command. A syntax error in either is an immediate workshop-breaker.
    """
    for path in (live_path, solution_path):
        try:
            ast.parse(path.read_text())
        except SyntaxError as exc:
            pytest.fail(
                f"[{label}] Python syntax error in "
                f"{path.relative_to(_REPO_ROOT)}: {exc}"
            )


# ---------------------------------------------------------------------------
# Smoke: live modules import cleanly (module-level code runs without error).
#
# We import the live file via importlib under a unique module name so
# we don't interfere with other tests that rely on services.agent_tools
# in the default sys.modules state.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, live_path",
    [(p[0], p[1]) for p in _PAIRS],
    ids=[p[0] for p in _PAIRS],
)
def test_live_file_has_workshop_markers(
    label: str, live_path: Path
) -> None:
    """Every live participant-edit file MUST carry at least one
    ``# === WORKSHOP ... START ===`` marker. Without the marker
    participants have no visual anchor for where to edit.
    """
    src = live_path.read_text()
    # Matches "# === WORKSHOP ... START ===" in a tolerant way —
    # whitespace variation, any label body, either dash or unicode em dash.
    pattern = re.compile(r"# ===\s*WORKSHOP.*START\s*===", re.IGNORECASE)
    matches = pattern.findall(src)
    assert matches, (
        f"[{label}] No WORKSHOP markers found in "
        f"{live_path.relative_to(_REPO_ROOT)}. Participants need a "
        f"visual anchor to find the build site."
    )


def _function_source(path: Path, function_name: str) -> str:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(path.read_text(), node) or ""
    raise AssertionError(f"{function_name} not found in {path.relative_to(_REPO_ROOT)}")


def _tool_signatures(path: Path) -> dict[str, str]:
    """Return every public ``@tool`` function and its AST-normalized signature."""
    tree = ast.parse(path.read_text())
    signatures = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        is_tool = any(
            isinstance(decorator, ast.Name) and decorator.id == "tool"
            for decorator in node.decorator_list
        )
        if is_tool:
            signatures[node.name] = ast.dump(node.args, include_attributes=False)
    return signatures


def _outside_check_stock_block(path: Path) -> str:
    """Mask the only participant-editable block so all other bytes can compare."""
    source = path.read_text()
    start = "# === WORKSHOP - Stock agent - check_stock: START ==="
    end = "# === WORKSHOP - Stock agent - check_stock: END ==="
    assert source.count(start) == 1, f"{path} must contain exactly one START marker"
    assert source.count(end) == 1, f"{path} must contain exactly one END marker"
    before, remainder = source.split(start, 1)
    _challenge, after = remainder.split(end, 1)
    return f"{before}{start}\n<check_stock challenge block>\n    {end}{after}"


def test_builder_preapply_matches_live_starter() -> None:
    """Bootstrap replaces the live module with this file on every fresh box.

    Compared with the ``check_stock`` body masked out, for the same reason
    ``test_check_stock_builder_contract`` skips once the tool is wired: the
    body is the exercise. A raw byte comparison turns a *completed* exercise
    into a failing suite, which lands on whoever debugs a box mid-workshop.
    Everything outside the markers must still match byte for byte — that is
    the drift this guard exists to catch.
    """
    live_path = _BACKEND / "services" / "agent_tools.py"
    preapply_path = (
        _SOLUTIONS
        / "closing-marcos-gap"
        / "services"
        / "agent_tools_builders_preapply.py"
    )
    assert _outside_check_stock_block(preapply_path) == _outside_check_stock_block(
        live_path
    ), (
        "Builder bootstrap would replace services/agent_tools.py with a stale "
        "module. Re-sync agent_tools_builders_preapply.py from the live starter."
    )


def test_agent_tools_recovery_files_keep_public_tool_parity() -> None:
    """A full-module recovery copy cannot add, remove, or reshape public tools."""
    live_path = _BACKEND / "services" / "agent_tools.py"
    recovery_paths = [
        _SOLUTIONS
        / "closing-marcos-gap"
        / "services"
        / "agent_tools_builders_preapply.py",
        _SOLUTIONS
        / "closing-marcos-gap"
        / "services"
        / "agent_tools_check_stock_solution.py",
    ]
    expected = _tool_signatures(live_path)
    for recovery_path in recovery_paths:
        assert _tool_signatures(recovery_path) == expected, (
            f"{recovery_path.relative_to(_REPO_ROOT)} has drifted from the live "
            "public @tool contract."
        )


def test_check_stock_solution_diff_is_scoped_to_challenge_block() -> None:
    """The escape hatch may wire ``check_stock`` and change nothing else."""
    live_path = _BACKEND / "services" / "agent_tools.py"
    solution_path = (
        _SOLUTIONS
        / "closing-marcos-gap"
        / "services"
        / "agent_tools_check_stock_solution.py"
    )
    assert _outside_check_stock_block(solution_path) == _outside_check_stock_block(
        live_path
    ), "The check_stock escape hatch differs outside its marked challenge block."


def test_check_stock_solution_passes_the_shared_answer_on_unchanged() -> None:
    """The ``cp`` escape hatch: the solution returns store_tools' envelope as is.

    The starter's own failure (not_found folded into zero) and the solution's
    fix are asserted on the real schema by ``tests/test_lab2_starter_failure.py``.
    """
    solution_src = _function_source(
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_check_stock_solution.py",
        "check_stock",
    )
    assert "product_query: str" in solution_src
    assert "return _reply(store_tools.check_stock(_run_sql, product_query=product_query))" in (
        solution_src)
    assert '.get("status")' not in solution_src, "the solution must not rewrite the status"


def test_the_starter_fragments_are_the_shipped_starters() -> None:
    """``reset_participant_exercises.py`` restores these; they must be what ships.

    Compared with the builder pre-apply copy, which mirrors the shipped starter
    whatever a participant has done to the live file.
    """
    starters = _REPO_ROOT / "workshop" / "starters" / "lab-2"
    preapply = (_SOLUTIONS / "closing-marcos-gap" / "services"
                / "agent_tools_builders_preapply.py").read_text()
    fragment = (starters / "check-stock-tool.pyfrag").read_text()
    assert fragment.strip() in preapply
    assert 'if result.get("status") == "not_found":' in fragment
