"""Lab 3's look at all four Memory strategies, and the shopper beside Theo.

``showcase_agentcore_memory.py strategies`` lists what AgentCore made from one
provisioning conversation: preferences, facts, the session summary, the episode
and its reflection, each in its own namespace. The fake answers each list call
by namespace, the way the data plane filters, so a record filed for one
shopper can never be printed for another.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[3]
for path in (REPO / "scripts", REPO / "scripts" / "deploy"):
    sys.path.insert(0, str(path))
showcase = importlib.import_module("showcase_agentcore_memory")

from services.memory_contract import STRATEGIES  # noqa: E402

IDS = {name: f"{name}-id" for _type, name, _union, _template in STRATEGIES.values()}
THEO = {
    "/pellier/preferences/CUST-THEO/": ("PellierUserPreferences", json.dumps(
        {"preference": "Prefers hand-thrown ceramics, stoneware, and linen throws"})),
    "/pellier/facts/CUST-THEO/": ("PellierFacts", "The user is slowly building a home."),
    "/pellier/summaries/CUST-THEO/prefseed/": ("PellierSessionSummary",
        '<topic name="Home Aesthetic">\n The user prefers quiet, tactile pieces. \n</topic>'),
    "/pellier/episodes/CUST-THEO/prefseed/": ("PellierEpisodes", json.dumps({
        "situation": "Building a home slowly.", "intent": "To have his taste recorded.",
        "assessment": "Yes", "justification": "The assistant recorded it."})),
    "/pellier/episodes/CUST-THEO/": ("PellierEpisodes", json.dumps(
        {"title": "Preference Profiling Through Active Listening", "hints": "Mirror the user."})),
}


class _Data:
    def __init__(self, records: Dict[str, Any], events: List[Dict[str, Any]]) -> None:
        self.records, self.events, self.calls = records, events, []

    def get_paginator(self, operation: str) -> Any:
        outer = self

        class _Paginator:
            def paginate(self, **kwargs: Any):
                outer.calls.append({"operation": operation, **kwargs})
                if operation == "list_events":
                    mine = kwargs["actorId"] == "CUST-THEO"
                    yield {"events": list(outer.events) if mine else []}
                    return
                rows = []
                path = kwargs["namespace"]
                if path in outer.records:
                    name, text = outer.records[path]
                    rows.append({"memoryRecordId": f"mem-{len(outer.calls)}",
                                 "memoryStrategyId": IDS[name], "namespaces": [path],
                                 "content": {"text": text}})
                yield {"memoryRecordSummaries": rows}

        return _Paginator()


class _Control:
    def get_memory(self, memoryId: str) -> Dict[str, Any]:  # noqa: N803 - boto3 shape
        return {"memory": {"strategies": [{"name": n, "strategyId": i} for n, i in IDS.items()]}}


EVENTS = [
    {"eventId": "2", "eventTimestamp": "2026-10-07T20:15:02", "payload": [
        {"conversational": {"role": "USER", "content": {"text": "One quiet tactile piece."}}}]},
    {"eventId": "1", "eventTimestamp": "2026-10-07T20:15:01", "payload": [
        {"conversational": {"role": "USER", "content": {"text": "Hand-thrown ceramics."}}}]},
]


def _found(actor: str, records: Dict[str, Any] = THEO) -> Dict[str, Any]:
    return showcase.strategy_records(_Control(), _Data(records, EVENTS), "mem-1", actor)


def test_every_strategy_and_the_reflection_is_read_in_its_own_namespace() -> None:
    data = _Data(THEO, EVENTS)
    found = showcase.strategy_records(_Control(), data, "mem-1", "CUST-THEO")
    reads = [(c["namespace"], c["memoryStrategyId"]) for c in data.calls
             if c["operation"] == "list_memory_records"]
    assert reads == [
        ("/pellier/preferences/CUST-THEO/", IDS["PellierUserPreferences"]),
        ("/pellier/facts/CUST-THEO/", IDS["PellierFacts"]),
        ("/pellier/summaries/CUST-THEO/prefseed/", IDS["PellierSessionSummary"]),
        ("/pellier/episodes/CUST-THEO/prefseed/", IDS["PellierEpisodes"]),
        ("/pellier/episodes/CUST-THEO/", IDS["PellierEpisodes"]),
    ]
    assert all(len(s["records"]) == 1 for s in found["strategies"].values())
    assert [e["eventId"] for e in found["events"]] == ["1", "2"]


def test_each_record_reads_as_one_plain_line() -> None:
    text = showcase.render_strategies(_found("CUST-THEO"), "mem-1")
    assert "Prefers hand-thrown ceramics, stoneware, and linen throws" in text
    assert "Home Aesthetic: The user prefers quiet, tactile pieces." in text
    assert "goal met: Yes. To have his taste recorded." in text
    assert "Preference Profiling Through Active Listening" in text
    assert "<topic" not in text and '{"' not in text


def test_reach_and_use_are_said_for_every_strategy() -> None:
    text = showcase.render_strategies(_found("CUST-THEO"), "mem-1")
    blocks = text.split("\n\n")[1:]
    assert [block.splitlines()[0].split(" (")[0] for block in blocks] == [
        "USER_PREFERENCE", "SEMANTIC", "SUMMARIZATION", "EPISODIC", "EPISODIC reflection"]
    reach = [block.splitlines()[1] for block in blocks]
    assert [showcase.FOLLOWS in line for line in reach] == [True, True, False, False, True]
    used = [block.splitlines()[2] for block in blocks]
    assert used[0].startswith("  Pellier: read into every signed-in turn")
    assert all(line == f"  Pellier: {showcase.NOT_READ}" for line in used[1:])


def test_a_shopper_with_no_records_is_named_beside_theo() -> None:
    text = showcase.render_strategies(_found("CUST-THEO"), "mem-1", _found("CUST-JESSICA"))
    assert text.endswith(
        "CUST-JESSICA, the same five reads: 0 records. CUST-JESSICA's turns are given no "
        "remembered preference, and none of CUST-THEO's: every read is keyed by the "
        "signed-in customer.")


def test_a_second_shopper_is_counted_in_their_own_namespaces_with_their_preferences() -> None:
    marco = {path.replace("CUST-THEO", "CUST-MARCO"): row for path, row in THEO.items()}
    marco["/pellier/preferences/CUST-MARCO/"] = ("PellierUserPreferences", json.dumps(
        {"preference": "Prefers earthy tones: sand, olive, and terracotta."}))
    head, preference = showcase._versus_lines("CUST-THEO", _found("CUST-MARCO", marco))
    assert head.startswith("CUST-MARCO, the same five reads: 1 USER_PREFERENCE, 1 SEMANTIC")
    assert "under CUST-MARCO's own namespaces" in head
    assert head.endswith("CUST-MARCO's turns are given:")
    assert preference.endswith("  Prefers earthy tones: sand, olive, and terracotta.")


class _Misfiled(_Data):
    """A data plane that answers Theo's reads with records filed for Jessica."""

    def get_paginator(self, operation: str) -> Any:
        inner = super().get_paginator(operation)

        class _Paginator:
            def paginate(self, **kwargs: Any):
                for page in inner.paginate(**kwargs):
                    for row in page.get("memoryRecordSummaries", []):
                        row["namespaces"] = [path.replace("CUST-THEO", "CUST-JESSICA")
                                             for path in row["namespaces"]]
                    yield page

        return _Paginator()


def test_a_record_filed_under_another_shopper_is_never_printed() -> None:
    found = showcase.strategy_records(_Control(), _Misfiled(THEO, EVENTS), "mem-1", "CUST-THEO")
    assert all(not strategy["records"] for strategy in found["strategies"].values())


def test_an_empty_strategy_says_extraction_may_still_be_running() -> None:
    found = _found("CUST-THEO", {k: v for k, v in THEO.items() if "episodes" not in k})
    text = showcase.render_strategies(found, "mem-1")
    assert text.count("none yet: AgentCore extracts after the conversation") == 2
