"""Lab 3's memory proof: Theo's first conversation is recorded at provisioning.

The seed writes his conversation (session ``prefseed``), waits within its
budget for the user-preference record AgentCore extracts, and reports both
ids. ``showcase_agentcore_memory.py provisioned --persona theo`` prints the
same pair as Expected, Observed and Evidence. The service is replaced by a
fake that answers the two list operations the way the data plane does.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO = Path(__file__).resolve().parents[3]
for path in (REPO / "scripts", REPO / "scripts" / "deploy"):
    sys.path.insert(0, str(path))
seed = importlib.import_module("seed_agentcore_memory")
showcase = importlib.import_module("showcase_agentcore_memory")
check = importlib.import_module("workshop_check")

from services.memory_contract import STRATEGIES  # noqa: E402

STRATEGY_ID = "PellierUserPreferences-abc"
NAMESPACE = "/pellier/preferences/CUST-THEO/"
THEO_EVENT = {"eventId": "0000001-theo-1", "payload": [
    {"conversational": {"role": "USER", "content": {"text": seed.SEED_TURNS["CUST-THEO"][0][0]}}}]}
THEO_RECORD = {"memoryRecordId": "mem-theo-1", "memoryStrategyId": STRATEGY_ID,
               "namespaces": [NAMESPACE],
               "content": {"text": "Prefers hand-thrown ceramics and stoneware, slow craft."}}


class _Pages:
    def __init__(self, rows: Dict[str, List[Dict[str, Any]]], calls: List[Dict[str, Any]]) -> None:
        self.rows, self.calls = rows, calls

    def get_paginator(self, operation: str) -> Any:
        rows, calls = self.rows, self.calls

        class _Paginator:
            def paginate(self, **kwargs: Any):
                calls.append({"operation": operation, **kwargs})
                key = "events" if operation == "list_events" else "memoryRecordSummaries"
                yield {key: list(rows.get(operation, []))}

        return _Paginator()


class _Control:
    def get_memory(self, memoryId: str) -> Dict[str, Any]:  # noqa: N803 - boto3 shape
        name = STRATEGIES["preferences"][1]
        return {"memory": {"status": "ACTIVE",
                           "strategies": [{"name": name, "strategyId": STRATEGY_ID}]}}


def _seeded(events: List[Dict[str, Any]], records: List[Dict[str, Any]]):
    calls: List[Dict[str, Any]] = []
    data = _Pages({"list_events": events, "list_memory_records": records}, calls)
    return seed.seeded_memory(_Control(), data, "mem-1", "CUST-THEO"), calls


def test_theo_tells_pellier_his_taste_at_provisioning() -> None:
    said = " ".join(user for user, _assistant in seed.SEED_TURNS["CUST-THEO"]).lower()
    for taste in ("ceramics", "stoneware", "slow"):
        assert taste in said


def test_the_reader_lists_his_session_and_his_preference_namespace() -> None:
    seeded, calls = _seeded([THEO_EVENT], [THEO_RECORD])
    assert [e["eventId"] for e in seeded["events"]] == ["0000001-theo-1"]
    assert [r["memoryRecordId"] for r in seeded["records"]] == ["mem-theo-1"]
    events_call, records_call = calls
    assert (events_call["actorId"], events_call["sessionId"]) == ("CUST-THEO", "prefseed")
    assert records_call["namespace"] == NAMESPACE
    assert records_call["memoryStrategyId"] == STRATEGY_ID


def test_a_record_from_another_namespace_is_not_his() -> None:
    foreign = {**THEO_RECORD, "namespaces": ["/pellier/preferences/CUST-JESSICA/"]}
    seeded, _calls = _seeded([THEO_EVENT], [foreign])
    assert seeded["records"] == []


def test_the_finding_prints_event_ids_beside_record_ids() -> None:
    seeded, _calls = _seeded([THEO_EVENT], [THEO_RECORD])
    finding = showcase.provisioned_finding(seeded, "mem-1")
    assert finding.state == check.PROVED
    assert finding.observed == "1 source event(s), 1 preference record(s)"
    rendered = check.render(finding)
    assert "source event 0000001-theo-1" in rendered
    assert "PellierUserPreferences record mem-theo-1" in rendered
    assert "  Expected  " in rendered and "  Evidence  " in rendered


def test_no_record_yet_is_not_yet_and_no_conversation_contradicts() -> None:
    waiting, _ = _seeded([THEO_EVENT], [])
    assert showcase.provisioned_finding(waiting, "mem-1").state == check.NOT_YET
    missing, _ = _seeded([], [])
    finding = showcase.provisioned_finding(missing, "mem-1")
    assert finding.state == check.CONTRADICTED
    assert "seed_agentcore_memory.py" in finding.next_step


def test_the_seed_reports_theos_ids_for_lab_3(monkeypatch: pytest.MonkeyPatch) -> None:
    created: List[Dict[str, Any]] = []

    class _Data(_Pages):
        def create_event(self, **kwargs: Any) -> Dict[str, Any]:
            created.append(kwargs)
            return {"event": {"eventId": f"e-{len(created)}"}}

    data = _Data({"list_events": [THEO_EVENT], "list_memory_records": [THEO_RECORD]}, [])
    clients = {"bedrock-agentcore-control": _Control(), "bedrock-agentcore": data}
    monkeypatch.setattr(seed.boto3, "client", lambda name, **_kw: clients[name])
    monkeypatch.setattr(seed, "_wait_for_memory", lambda control, memory_id: {"status": "ACTIVE"})
    monkeypatch.setattr(seed, "verify_memory_readiness",
                        lambda *a, **k: {"strategies": {}})

    result = seed.seed("mem-1", "us-east-1", timeout=5)
    assert result["lab3_theo"] == {"source_event_ids": ["0000001-theo-1"],
                                   "preference_record_ids": ["mem-theo-1"]}
    assert {call["sessionId"] for call in created} == {"prefseed"}


def test_reprovisioning_reuses_the_existing_conversation(monkeypatch):
    created = []

    class Data(_Pages):
        def create_event(self, **kwargs):
            created.append(kwargs)
            return {"event": {"eventId": "new"}}

    pairs = seed.SEED_TURNS["CUST-THEO"]
    events = [{"eventId": str(index), "payload": [
        {"conversational": {"content": {"text": text}, "role": role}}
        for role, text in (("USER", user), ("ASSISTANT", assistant))
    ]} for index, (user, assistant) in enumerate(pairs)]
    data = Data({"list_events": events, "list_memory_records": [THEO_RECORD]}, [])
    clients = {"bedrock-agentcore-control": _Control(), "bedrock-agentcore": data}
    monkeypatch.setattr(seed, "SEED_TURNS", {"CUST-THEO": pairs})
    monkeypatch.setattr(seed.boto3, "client", lambda name, **_k: clients[name])
    monkeypatch.setattr(seed, "verify_memory_readiness", lambda *a, **k: {"strategies": {}})
    for _ in range(2):
        result = seed.seed("mem-1", "us-east-1", timeout=5)
        assert result["events_created"] == 0
        assert result["events_already_present"] == 2
        assert result["lab3_theo"]["source_event_ids"] == ["0", "1"]
    assert created == []
