"""Fresh-account starter overlay contract for the builders session."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "builders_starter.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("builders_starter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for relative in (
        "pellier/backend/services/inventory_sql.py",
        "pellier/backend/agents/stock_keeper.py",
        "workshop/retrieval.sql",
    ):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, destination)
    return repo


def test_starter_overlay_installs_and_verifies_both_gaps(
    tmp_path: Path,
) -> None:
    module = _load_script()
    repo = _fixture_repo(tmp_path)

    state = module.apply_starter(repo)

    assert state["floor_check"] == "exercise"
    assert state["Stock Keeper"] == "exercise"
    assert "floor_check" not in state["inventoryTools"]
    assert "WORKSHOP_INVENTORY_SQL_STUB" in (
        repo / "pellier/backend/services/inventory_sql.py"
    ).read_text(encoding="utf-8")
    assert "WORKSHOP_AGENT_GRANT_STUB" in (
        repo / "pellier/backend/agents/stock_keeper.py"
    ).read_text(encoding="utf-8")


def test_starter_overlay_distinguishes_tool_from_agent_completion(
    tmp_path: Path,
) -> None:
    module = _load_script()
    repo = _fixture_repo(tmp_path)
    module.apply_starter(repo)

    tools_path = repo / "pellier/backend/services/inventory_sql.py"
    starter_source = tools_path.read_text(encoding="utf-8")
    starter_before = starter_source.split(module.TOOL_BODY_START, 1)[0]
    starter_after = starter_source.split(module.TOOL_BODY_END, 1)[1]

    tool_state = module.complete_tool(repo)
    completed_source = tools_path.read_text(encoding="utf-8")

    assert tool_state["floor_check"] == "shipped"
    assert tool_state["Stock Keeper"] == "exercise"
    assert completed_source.split(module.TOOL_BODY_START, 1)[0] == starter_before
    assert completed_source.split(module.TOOL_BODY_END, 1)[1] == starter_after

    module.complete_agent(repo)
    complete = module.verify_state(repo, "complete")
    assert complete["floor_check"] == "shipped"
    assert complete["Stock Keeper"] == "shipped"
    assert "floor_check" in complete["inventoryTools"]


def test_retrieval_recovery_preserves_scaffold_and_reset(tmp_path):
    module = _load_script()
    repo = _fixture_repo(tmp_path)
    module.apply_starter(repo)
    path = repo / "workshop/retrieval.sql"
    before = path.read_text().split("-- === WORKSHOP: eligibility: START ===")[0]
    assert module.complete_retrieval(repo)["retrieval"] == "shipped"
    complete = path.read_text()
    assert complete.startswith(before)
    assert "sum(1.0 / (60 + rank))" in complete
    assert "quantity > 0" in complete
    assert module.apply_starter(repo)["retrieval"] == "exercise"
