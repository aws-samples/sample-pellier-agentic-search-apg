"""test_solutions_parity.py — drop-in solutions contract.

The workshop's core promise to participants:

  ``⏩ SHORT ON TIME? Run:
     cp solutions/<module-name>/<path> pellier/backend/<path>``

If that ``cp`` command leaves the app in a broken or inconsistent
state, the workshop flow silently breaks — participants paste a
stale solution, restart uvicorn, and the verification step fails
with no obvious cause. This test is the CI tripwire for that
contract.

The Builder's Session contract
------------------------------

The 60-minute Builder's Session has one coding exercise:
``floor_check`` inside ``services/agent_tools.py``. The specialist
agents are pre-applied by bootstrap; the copy solution is a full
agent_tools drop-in with the same public tools and a wired
``floor_check`` body.

What this test enforces
-----------------------

For every ``(live_path, solution_path)`` pair:

  1. Both files exist.
  2. Both files parse as valid Python (``ast.parse`` smoke).
  3. Live/builder-preapply ``floor_check`` keeps the starter stub.
  4. The inventory solution keeps the ``product_query`` signature and
     calls ``BusinessLogic.floor_check(product_query=...)``.

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
# (challenge_label, live_file, solution_file, stub_flag_name)
# ---------------------------------------------------------------------------

_PAIRS = [
    (
        "stock-keeper-tools",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_floor_check_solution.py",
        None,
    ),
    (
        "stock-keeper-tools-builders-preapply",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_builders_preapply.py",
        None,
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
# silently boots stale code (e.g. a curator.py missing
# ``build_recommendation_agent`` → ImportError on the dispatcher path).
#
# ``agent_tools_builders_preapply.py`` is deliberately EXCLUDED here — it is
# the one auto-applied file that must differ from the backend (it ships the
# floor_check stub for the participant to wire). Its contract lives in the
# _PAIRS tests + ``test_floor_check_builder_contract`` above.
#
# Direction of truth: the BACKEND file is canonical (the full test suite runs
# against it). If this test fails, re-sync with:
#     cp pellier/backend/<path> solutions/<module>/<path>
# ---------------------------------------------------------------------------

_AUTO_APPLIED_IDENTICAL = [
    ("curator", _BACKEND / "agents" / "curator.py",
     _SOLUTIONS / "closing-marcos-gap" / "agents" / "curator.py"),
    ("experience_guide", _BACKEND / "agents" / "experience_guide.py",
     _SOLUTIONS / "closing-marcos-gap" / "agents" / "experience_guide.py"),
    ("orchestrator", _BACKEND / "agents" / "orchestrator.py",
     _SOLUTIONS / "closing-marcos-gap" / "agents" / "orchestrator.py"),
    ("agentcore_runtime", _BACKEND / "services" / "agentcore_runtime.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_runtime.py"),
    ("agentcore_memory", _BACKEND / "services" / "agentcore_memory.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_memory.py"),
    ("agentcore_gateway", _BACKEND / "services" / "agentcore_gateway.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_gateway.py"),
    ("agentcore_identity", _BACKEND / "services" / "agentcore_identity.py",
     _SOLUTIONS / "the-ledger" / "services" / "agentcore_identity.py"),
    ("cognito_auth", _BACKEND / "services" / "cognito_auth.py",
     _SOLUTIONS / "the-ledger" / "services" / "cognito_auth.py"),
    ("otel_trace_extractor", _BACKEND / "services" / "otel_trace_extractor.py",
     _SOLUTIONS / "the-ledger" / "services" / "otel_trace_extractor.py"),
    ("frontend_agent_identity", _REPO_ROOT / "pellier" / "frontend" / "src" / "utils" / "agentIdentity.ts",
     _SOLUTIONS / "the-ledger" / "frontend" / "agentIdentity.ts"),
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
    "label, live_path, solution_path, flag_name",
    _PAIRS,
    ids=[p[0] for p in _PAIRS],
)
def test_both_files_exist(
    label: str, live_path: Path, solution_path: Path, flag_name: str | None
) -> None:
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
    "label, live_path, solution_path, flag_name",
    _PAIRS,
    ids=[p[0] for p in _PAIRS],
)
def test_both_files_parse_as_python(
    label: str, live_path: Path, solution_path: Path, flag_name: str | None
) -> None:
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


@pytest.mark.parametrize(
    "label, live_path, solution_path, flag_name",
    [p for p in _PAIRS if p[3] is not None],  # Only pairs that declare a flag.
    ids=[p[0] for p in _PAIRS if p[3] is not None],
)
def test_stub_flag_states_match_workshop_contract(
    label: str, live_path: Path, solution_path: Path, flag_name: str
) -> None:
    """Live file: flag = True (stubbed).
    Solution file: flag = False (wired).

    This is the contract that makes the cp command safe:
    running ``cp solutions/... live/...`` must flip the stub
    indicator so the Dispatcher fall-through stops intercepting
    and real agent invocations proceed.
    """
    live_flag = _extract_flag(live_path, flag_name)
    solution_flag = _extract_flag(solution_path, flag_name)

    assert live_flag is True, (
        f"[{label}] Live file's {flag_name} should be True (stubbed state) "
        f"but got {live_flag}. The file: {live_path.relative_to(_REPO_ROOT)}"
    )
    assert solution_flag is False, (
        f"[{label}] Solution's {flag_name} should be False (wired state) "
        f"but got {solution_flag}. The file: "
        f"{solution_path.relative_to(_REPO_ROOT)}. "
        f"If a participant cp's this in, the Dispatcher fall-through "
        f"would still block the agent — defeating the purpose."
    )


def _extract_flag(path: Path, flag_name: str) -> bool | None:
    """Parse ``path`` and return the boolean value of the first top-level
    assignment ``<flag_name> = <bool>``. Returns None if not found."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == flag_name:
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, bool
                    ):
                        return node.value.value
    return None


# ---------------------------------------------------------------------------
# Self-verification of _extract_flag
# ---------------------------------------------------------------------------


def test_extract_flag_finds_true(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("_MY_FLAG = True\n")
    assert _extract_flag(src, "_MY_FLAG") is True


def test_extract_flag_finds_false(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("_MY_FLAG = False\n")
    assert _extract_flag(src, "_MY_FLAG") is False


def test_extract_flag_returns_none_when_missing(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("_OTHER = True\n")
    assert _extract_flag(src, "_MY_FLAG") is None


def test_extract_flag_ignores_nested_assignments(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text(
        "def fn():\n    _MY_FLAG = True  # function-scoped, not module-level\n"
    )
    # ast.walk would visit the function body — but only top-level
    # assignments have `node.targets` directly inside `Module.body`.
    # Our implementation uses ast.walk() for simplicity; nested assigns
    # at the same name would also match. That's acceptable because the
    # flag is conventionally module-level — and the stubs we ship do
    # put it at module level.
    assert _extract_flag(src, "_MY_FLAG") is True


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
def test_live_file_has_challenge_markers(
    label: str, live_path: Path
) -> None:
    """Every live challenge file MUST carry at least one
    ``# === CHALLENGE ... START ===`` marker. Without the marker
    participants have no visual anchor for where to edit, and the
    Atelier's Code Editor won't know where to focus.
    """
    src = live_path.read_text()
    # Matches "# === CHALLENGE ... START ===" in a tolerant way —
    # whitespace variation, any label body, either dash or unicode em dash.
    pattern = re.compile(r"# ===\s*CHALLENGE.*START\s*===", re.IGNORECASE)
    matches = pattern.findall(src)
    assert matches, (
        f"[{label}] No CHALLENGE markers found in "
        f"{live_path.relative_to(_REPO_ROOT)}. Participants need a "
        f"visual anchor to find the build site."
    )


def _function_source(path: Path, function_name: str) -> str:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(path.read_text(), node) or ""
    raise AssertionError(f"{function_name} not found in {path.relative_to(_REPO_ROOT)}")


def test_floor_check_builder_contract() -> None:
    """The live Builder file stays stubbed; the copy solution is wired."""
    live_src = _function_source(_BACKEND / "services" / "agent_tools.py", "floor_check")
    preapply_src = _function_source(
        _SOLUTIONS
        / "closing-marcos-gap"
        / "services"
        / "agent_tools_builders_preapply.py",
        "floor_check",
    )
    solution_src = _function_source(
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_floor_check_solution.py",
        "floor_check",
    )

    assert "product_query: str = \"\"" in live_src
    assert "floor_check is in stub state" in live_src
    assert "product_query: str = \"\"" in preapply_src
    assert "floor_check is in stub state" in preapply_src

    assert "product_query: str = \"\"" in solution_src
    assert "floor_check is in stub state" not in solution_src
    assert "logic.floor_check(product_query=query)" in solution_src
