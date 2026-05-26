"""Tests for scripts/seed_tool_registry.py — the tool-spec loader.

The full seeder hits Bedrock + Postgres; those paths are covered
end-to-end by the solution parity check and a manual smoke run. These
tests cover the pure Python bits: spec loading stays in sync with
Gateway's tool name list, docstrings feed the embedding input
correctly, and the sensitive-tool set matches the approvals policy.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SEEDER_PATH = REPO_ROOT / "scripts" / "seed_tool_registry.py"


@pytest.fixture(scope="module")
def seeder_module():
    """Load scripts/seed_tool_registry.py as a module without running main()."""
    spec = importlib.util.spec_from_file_location("_seed_tool_registry", SEEDER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_seed_tool_registry"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_tool_specs_match_gateway_name_list(seeder_module) -> None:
    """Seeder MUST load exactly the 13 Gateway tool names, in the same order."""
    from services.agentcore_gateway import GATEWAY_TOOL_NAMES

    specs = seeder_module._load_tool_specs()
    assert [s["tool_id"] for s in specs] == list(GATEWAY_TOOL_NAMES)
    assert len(specs) == 13


def test_every_tool_has_nonempty_description(seeder_module) -> None:
    """A missing docstring means an empty embedding input — seeder must refuse
    to proceed rather than silently indexing noise."""
    specs = seeder_module._load_tool_specs()
    for s in specs:
        assert s["description"], s["tool_id"]
        # First-paragraph trim: descriptions must not leak "SHORT ON TIME"
        # fast-path hints into the embedding input.
        assert "SHORT ON TIME" not in s["description"], s["tool_id"]


def test_write_path_tools_require_approval(seeder_module) -> None:
    """The approvals gate is narrow. Both write-path tools require approval:
    ``restock_shelf`` (inventory write) and ``process_return`` (refund / dollars
    out). Widening it needs a deliberate code change here + a test update, not
    accidental drift."""
    specs = {s["tool_id"]: s for s in seeder_module._load_tool_specs()}
    sensitive = {name for name, spec in specs.items() if spec["requires_approval"]}
    assert sensitive == {"restock_shelf", "process_return"}


def test_owner_agent_assigned_for_every_tool(seeder_module) -> None:
    """Atelier Tools surface shows provenance per tool; 'unknown' owner
    means the map fell out of sync with Gateway's name list.

    Owners are the 5 boutique-branded specialists. Mirrors the
    agents/*.py factories.
    """
    specs = seeder_module._load_tool_specs()
    valid_owners = {
        "style_advisor",
        "curator",
        "value_analyst",
        "stock_keeper",
        "experience_guide",
    }
    for s in specs:
        assert s["owner_agent"] in valid_owners, (
            f"{s['tool_id']} → {s['owner_agent']}"
        )
