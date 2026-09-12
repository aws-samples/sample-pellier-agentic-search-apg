"""Keep the current README, SQL exercises, and agent-grant contract aligned.

The root README describes the required path. Legacy recovery documentation
does not define the current participant edits. The tool must remain directly
testable before its separate agent grant is completed.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
README = REPO / "README.md"
STARTER = REPO / "scripts/builders_starter.py"


def _starter():
    spec = importlib.util.spec_from_file_location("builders_starter", STARTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract_section() -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index("### Joining the 60-minute Builders' Session")
    return text[start : text.index("For the optional visual retrieval comparison", start)]


def _granted_tools(block: str) -> list[str]:
    """Parse INVENTORY_AGENT_TOOLS out of one marked grant block."""
    body = "\n".join(
        line for line in block.splitlines() if not line.lstrip().startswith("#")
    )
    tree = ast.parse(body)
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign))
    return [element.id for element in assignment.value.elts]


def test_starter_preserves_sql_exercises_and_independent_agent_grant() -> None:
    """Warehouse SQL and the agent grant remain separate steps.

    The middle state — a working tool the agent still cannot select — is
    the lesson, so it must survive as its own position on the path.
    """
    starter = _starter()

    assert _granted_tools(starter.STARTER_AGENT_GRANT) == [
        "restock_shelf",
        "running_low",
    ]
    assert _granted_tools(starter.COMPLETE_AGENT_GRANT) == [
        "floor_check",
        "restock_shelf",
        "running_low",
    ]
    assert starter.TOOL_STUB_MARKER in starter.INVENTORY_STARTER
    assert set(starter.RETRIEVAL_BLOCKS) == {"eligibility", "rank fusion"}
    inventory_source = starter._paths(REPO)["inventory_sql"].read_text(encoding="utf-8")
    assert starter.TOOL_BODY_START in inventory_source
    assert starter.TOOL_BODY_END in inventory_source

    verify = inspect.getsource(starter.verify_state)
    for state in ("starter", "tool-wired", "complete"):
        assert f'"{state}"' in verify


def test_readme_names_all_three_files_the_participant_edits() -> None:
    """The guide must name both SQL exercises and the separate tool list."""
    section = _contract_section()

    assert "workshop/retrieval.sql" in section
    assert "pellier/backend/services/inventory_sql.py" in section
    assert "pellier/backend/agents/stock_keeper.py" in section
    assert "INVENTORY_AGENT_TOOLS" in section


def test_readme_does_not_claim_a_single_edited_file() -> None:
    """Guard the exact phrasing that caused the drift."""
    text = README.read_text(encoding="utf-8")

    assert "The only file participants change" not in text
    assert "One mandatory code build" not in text
    # The stale governed-branch exercise must not reappear here.
    assert "author three queries against" not in text


def test_readme_edited_paths_all_exist() -> None:
    """Every path the contract tells a participant to edit must be real."""
    section = _contract_section()

    for match in re.findall(r"`((?:pellier/[\w/]+\.py|workshop/[\w/]+\.sql))`", section):
        assert (REPO / match).is_file(), f"contract names a missing file: {match}"
