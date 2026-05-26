"""Golden-set journey regressions — Batch 4 evals spike (Day 1 CI gate).

Loads `tests/golden/journeys.json` and asserts each pinned Atelier session
fixture still matches the workshop's non-negotiable agent behavior:
which tools fire (and in what order), which products surface, and which
routing pattern owns the turn. Deterministic, no AWS calls, no model
invocations — purely structural assertions over the published fixtures.

Sister artifact: `services/agentcore_evals.py` (graduation path — env-flag-
gated `create_evaluation_job` call against AgentCore Evals). The Measure
surface copy distinguishes the two: golden-set runs every PR; AgentCore
Evals runs at prod cutover.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_FILE = Path(__file__).resolve().parent / "golden" / "journeys.json"


def _load_journeys() -> Dict[str, Any]:
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def _load_fixture(fixture_root: str, fixture_name: str) -> Dict[str, Any]:
    path = REPO_ROOT / fixture_root / fixture_name
    return json.loads(path.read_text(encoding="utf-8"))


def _assistant_turn(fixture: Dict[str, Any], turn_index: int) -> Dict[str, Any]:
    """Return the Nth assistant message (1-indexed) from the chat array."""
    assistants = [m for m in fixture.get("chat", []) if m.get("role") == "assistant"]
    if turn_index < 1 or turn_index > len(assistants):
        raise AssertionError(
            f"Fixture has {len(assistants)} assistant turns; asked for turn {turn_index}"
        )
    return assistants[turn_index - 1]


_JOURNEYS = _load_journeys()["journeys"]


@pytest.mark.parametrize("journey", _JOURNEYS, ids=[j["id"] for j in _JOURNEYS])
def test_golden_journey(journey: Dict[str, Any]) -> None:
    fixture_root = _load_journeys()["fixtureRoot"]
    fixture = _load_fixture(fixture_root, journey["fixture"])
    asserts = journey["asserts"]

    expected_pattern = asserts.get("routingPattern")
    if expected_pattern is not None:
        assert fixture.get("routingPattern") == expected_pattern, (
            f"{journey['id']}: routingPattern drift "
            f"(expected {expected_pattern!r}, got {fixture.get('routingPattern')!r})"
        )

    turn = _assistant_turn(fixture, asserts["turn"])
    tool_calls: List[Dict[str, Any]] = turn.get("toolCalls", [])
    tools_in_order = [tc["toolName"] for tc in tool_calls]
    tools_set = set(tools_in_order)

    if "expectedTools" in asserts:
        for tool in asserts["expectedTools"]:
            assert tool in tools_set, (
                f"{journey['id']}: expected tool {tool!r} missing "
                f"(saw {tools_in_order})"
            )

    if "expectedToolsInOrder" in asserts:
        expected = asserts["expectedToolsInOrder"]
        idx = -1
        for tool in expected:
            try:
                next_idx = tools_in_order.index(tool, idx + 1)
            except ValueError as exc:
                raise AssertionError(
                    f"{journey['id']}: tool ordering broken — expected "
                    f"{expected} as a subsequence; saw {tools_in_order}"
                ) from exc
            idx = next_idx

    if "forbiddenTools" in asserts:
        for tool in asserts["forbiddenTools"]:
            assert tool not in tools_set, (
                f"{journey['id']}: forbidden tool {tool!r} fired "
                f"(saw {tools_in_order})"
            )

    products = [p["name"] for p in turn.get("products", [])]
    products_set = set(products)

    if "expectedProductsAll" in asserts:
        for name in asserts["expectedProductsAll"]:
            assert name in products_set, (
                f"{journey['id']}: required product {name!r} missing "
                f"(surfaced {products})"
            )

    if "expectedProductsAny" in asserts:
        any_match = any(n in products_set for n in asserts["expectedProductsAny"])
        assert any_match, (
            f"{journey['id']}: none of {asserts['expectedProductsAny']} "
            f"surfaced (surfaced {products})"
        )


def test_golden_set_covers_all_three_personas() -> None:
    """The fixture set must keep teaching coverage across the three personas;
    if a future edit drops a persona, this test fails so we notice."""
    personas = {j["persona"] for j in _JOURNEYS}
    assert personas == {"marco", "anna", "theo"}, (
        f"Persona coverage drift — expected marco/anna/theo, got {personas}"
    )
