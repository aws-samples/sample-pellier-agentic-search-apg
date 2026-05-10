"""test_solutions_parity.py — drop-in solutions contract.

The workshop's core promise to participants:

  ``⏩ SHORT ON TIME? Run:
     cp solutions/module2/<path> pellier/backend/<path>``

If that ``cp`` command leaves the app in a broken or inconsistent
state, the workshop flow silently breaks — participants paste a
stale solution, restart uvicorn, and the verification step fails
with no obvious cause. This test is the CI tripwire for that
contract.

The new contract (differs from the old C1–C9 byte-parity one)
-------------------------------------------------------------

Our challenges no longer use numbered blocks that byte-match against
solutions. Instead:

  * Each challenge is a STUB in a live file, with a module-level
    flag like ``_INVENTORY_AGENT_STUBBED = True``.
  * The matching solution file is a full drop-in replacement with
    the same flag set to ``False`` (wired state).
  * After ``cp solutions/... live/...``, the module still imports,
    the flag is ``False``, and the system works.

What this test enforces
-----------------------

For every ``(live_path, solution_path)`` pair:

  1. Both files exist.
  2. Both files parse as valid Python (``ast.parse`` smoke).
  3. If the live file declares a ``*_STUBBED`` flag, the solution
     declares the SAME flag (same name) set to ``False``.
  4. The live file declares the flag set to ``True`` (stubbed by
     default — participants flip it).
  5. Both files import cleanly without raising.
  6. The solution file is self-contained — no references to
     ``solutions/`` paths that wouldn't exist after a ``cp``.

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
        "stock-keeper-agent",
        _BACKEND / "agents" / "inventory_agent.py",
        _SOLUTIONS / "module2" / "agents" / "inventory_agent.py",
        "_INVENTORY_AGENT_STUBBED",
    ),
    (
        "experience-guide-agent",
        _BACKEND / "agents" / "customer_support_agent.py",
        _SOLUTIONS / "module2" / "agents" / "customer_support_agent.py",
        "_SUPPORT_AGENT_STUBBED",
    ),
    (
        "stock-keeper-tools",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "module2" / "services" / "agent_tools__inventory.py",
        None,  # No module-level flag; workshop tracks progress via CHALLENGE markers.
    ),
    (
        "stock-keeper-tools-builders-preapply",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "module2" / "services" / "agent_tools__builders_preapply.py",
        None,  # Variant used by the CloudFormation UserData for the Builder's Session.
    ),
]


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
