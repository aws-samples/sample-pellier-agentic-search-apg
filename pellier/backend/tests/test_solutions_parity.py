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

Lab 2 has one Python starter that runs and fails visibly: the Stock agent
definition in ``agents/stock_agent.py`` connects only the catalog tools, none
of which reads ``warehouse_inventory``. Its other task is SQL: the
``pellier.check_stock`` worksheet, proved on real PostgreSQL by
``tests/test_lab2_check_stock_postgres.py``. The copy solutions are drop-ins
that make each stage safe to recover during a live room.

What this test enforces
-----------------------

For every ``(live_path, solution_path)`` pair:

  1. Both files exist.
  2. Both files parse as valid Python (``ast.parse`` smoke).
  3. The live file carries a WORKSHOP marker.

Every bootstrap auto-applied file, the builders ``agent_tools`` copy among
them, is byte-identical to its backend twin.

Scope table
-----------

Pairs are hard-coded below. Add new workshop challenges by extending
``_PAIRS`` — the test parametrizes across it automatically.
"""

from __future__ import annotations

import ast
import re
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
        _SOLUTIONS / "lab-2-ground" / "agents" / "stock_agent_solution.py",
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
# ``agent_tools_builders_preapply.py`` is one of them: ``check_stock``'s answer
# lives in the database function ``pellier.check_stock``, so the module holds
# no exercise and its builders copy is the module itself.
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
    ("agent_tools_builders_preapply", _BACKEND / "services" / "agent_tools.py",
     _SOLUTIONS / "lab-2-ground" / "services" / "agent_tools_builders_preapply.py"),
    ("agentcore_runtime", _BACKEND / "services" / "agentcore_runtime.py",
     _SOLUTIONS / "lab-3-deploy" / "services" / "agentcore_runtime.py"),
    ("agentcore_memory", _BACKEND / "services" / "agentcore_memory.py",
     _SOLUTIONS / "lab-3-deploy" / "services" / "agentcore_memory.py"),
    ("agentcore_identity", _BACKEND / "services" / "agentcore_identity.py",
     _SOLUTIONS / "lab-3-deploy" / "services" / "agentcore_identity.py"),
    ("cognito_auth", _BACKEND / "services" / "cognito_auth.py",
     _SOLUTIONS / "lab-3-deploy" / "services" / "cognito_auth.py"),
    ("otel_trace_extractor", _BACKEND / "services" / "otel_trace_extractor.py",
     _SOLUTIONS / "lab-3-deploy" / "services" / "otel_trace_extractor.py"),
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
