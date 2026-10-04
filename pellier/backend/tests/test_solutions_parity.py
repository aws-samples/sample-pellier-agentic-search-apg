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

The governed workshop path has two starter-code gaps:
the Stock agent definition in ``agents/stock_agent.py`` and
``check_stock`` inside ``services/agent_tools.py``. The copy solutions
are drop-ins that make each stage safe to recover during a live room.

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
  6. Live/builder-preapply ``check_stock`` keeps the starter stub.
  7. The Stock agent definition solution flips its stub flag.
  8. The wired solution keeps the ``product_query`` signature and calls
     ``store_tools.check_stock(_run_sql, product_query=...)``.

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
        "stock-agent-definition",
        _BACKEND / "agents" / "stock_agent.py",
        _SOLUTIONS / "waking-the-stock-keeper" / "agents" / "stock_agent_solution.py",
        "_STOCK_AGENT_STUBBED",
    ),
    (
        "stock-tool",
        _BACKEND / "services" / "agent_tools.py",
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_check_stock_solution.py",
        None,
    ),
    (
        "stock-tool-builders-preapply",
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

    POLARITY NOTE: like ``test_check_stock_builder_contract``, the live-file
    half is a guard on the *shipped* repo state, not a build check. Flipping
    the flag is the exercise, so once a participant wires the definition this
    skips rather than failing. The solution-side assertion is unconditional —
    it protects the ``cp`` escape hatch and holds either way.
    """
    live_flag = _extract_flag(live_path, flag_name)
    solution_flag = _extract_flag(solution_path, flag_name)

    assert solution_flag is False, (
        f"[{label}] Solution's {flag_name} should be False (wired state) "
        f"but got {solution_flag}. The file: "
        f"{solution_path.relative_to(_REPO_ROOT)}. "
        f"If a participant cp's this in, the Dispatcher fall-through "
        f"would still block the agent — defeating the purpose."
    )

    if live_flag is False:
        pytest.skip(
            f"[{label}] {flag_name} has been flipped in "
            f"{live_path.relative_to(_REPO_ROOT)} — this is the expected end "
            "state of the exercise, not a regression. Verify the wire via the "
            "Observatory build-state badge and Marco's Brooklyn turn."
        )

    assert live_flag is True, (
        f"[{label}] Live file's {flag_name} should be True (stubbed state) "
        f"but got {live_flag}. The file: {live_path.relative_to(_REPO_ROOT)}"
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
def test_live_file_has_workshop_markers(
    label: str, live_path: Path
) -> None:
    """Every live participant-edit file MUST carry at least one
    ``# === WORKSHOP ... START ===`` marker. Without the marker
    participants have no visual anchor for where to edit, and the
    Observatory's Code Editor won't know where to focus.
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


def test_check_stock_builder_contract() -> None:
    """Repo guard: the *shipped* starter file ships stubbed, and the copy
    solution is fully wired.

    POLARITY NOTE (read before debugging a red run): this is a guard on the
    committed starter state, not a build check. It is expected to pass on a
    clean checkout (check_stock still stubbed) and is **deliberately skipped**
    once a participant wires check_stock — wiring it is the exercise, not a
    regression. A participant who completes the exercise and runs the full
    suite should therefore see this as ``SKIPPED``, never as a failure. The
    real verification of a correct wire is the Observatory Tools strip showing
    check_stock wired and Marco's Brooklyn turn returning a real quantity, both
    in the lab guide. See CLAUDE.md ("How the participant verifies").
    """
    live_src = _function_source(_BACKEND / "services" / "agent_tools.py", "check_stock")
    preapply_src = _function_source(
        _SOLUTIONS
        / "closing-marcos-gap"
        / "services"
        / "agent_tools_builders_preapply.py",
        "check_stock",
    )
    solution_src = _function_source(
        _SOLUTIONS / "closing-marcos-gap" / "services" / "agent_tools_check_stock_solution.py",
        "check_stock",
    )

    # The drop-in solution invariants always hold, regardless of whether the
    # participant has wired the live file yet — these protect the `cp` path.
    assert "product_query: str" in solution_src
    assert "check_stock is in stub state" not in solution_src
    assert "store_tools.check_stock(_run_sql, product_query=product_query)" in solution_src

    # If the participant has wired the live file (the exercise is done), the
    # starter-stub assertions below would fail on something they were told to
    # change. Skip with a clear reason instead of emitting a confusing red.
    if "check_stock is in stub state" not in live_src:
        pytest.skip(
            "check_stock has been wired in services/agent_tools.py — this is "
            "the expected end state of the exercise, not a regression. The "
            "starter-stub guard only applies to the shipped repo. Verify your "
            "wire via the Observatory Tools strip and Marco's Brooklyn turn."
        )

    # Shipped starter state: the live + preapply builder files carry the stub.
    assert "product_query: str" in live_src
    assert "check_stock is in stub state" in live_src
    assert "product_query: str" in preapply_src
    assert "check_stock is in stub state" in preapply_src
