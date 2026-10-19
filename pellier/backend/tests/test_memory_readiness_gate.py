"""Provisioning waits for the Memory a turn and Lab 3 read, and no longer.

User preferences gate handout (REQUIRED_STRATEGIES). Facts, summaries and episodes
serve the appendix's deep dive; an episode can form long after provisioning, so
scripts/deploy/check_memory_deep_dive.py confirms them in the background and
event_readiness.py reports the result without changing whether a box is ready.
"""
from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from services.memory_contract import (
    REFLECTION_NAMESPACE, REQUIRED_STRATEGIES, STRATEGIES, namespace,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))
sys.path.insert(0, str(ROOT / "scripts"))

import check_memory_deep_dive as deep_dive  # noqa: E402
import event_readiness  # noqa: E402
from verify_memory_readiness import verify_memory_readiness  # noqa: E402


def _resource() -> Dict[str, Any]:
    strategies = []
    for kind, (strategy_type, name, _union, template) in STRATEGIES.items():
        strategy = {"name": name, "type": strategy_type, "status": "ACTIVE",
                    "strategyId": f"{name}-id", "namespaceTemplates": [template]}
        if kind == "episodic":
            strategy["configuration"] = {"reflection": {"episodicReflectionConfiguration": {
                "namespaceTemplates": [REFLECTION_NAMESPACE]}}}
        strategies.append(strategy)
    return {"status": "ACTIVE", "eventExpiryDuration": 30, "strategies": strategies}


class _Control:
    def get_memory(self, memoryId: str) -> Dict[str, Any]:  # noqa: N803 - boto3 shape
        return {"memory": _resource()}


class _Data:
    """The data plane: events as written, and records only for ``extracted`` kinds."""

    def __init__(self, extracted: tuple[str, ...]) -> None:
        self.extracted = extracted
        self.events: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        self.records: Dict[str, Dict[str, Any]] = {}

    def create_event(self, **kwargs: Any) -> Dict[str, Any]:
        actor, session = kwargs["actorId"], kwargs["sessionId"]
        event = {"eventId": f"ev-{len(self.records) + sum(map(len, self.events.values()))}"}
        self.events.setdefault((actor, session), []).append(event)
        for kind in self.extracted:
            name = STRATEGIES[kind][1]
            path = namespace(kind, actor, session)
            self.records[kind] = {"memoryRecordId": f"{kind}-record", "memoryStrategyId": f"{name}-id",
                                  "namespaces": [path], "content": {"text": f"{kind} from the conversation"}}
        return {"event": event}

    def _matching(self, kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [r for r in self.records.values() if kwargs.get("namespace") in r["namespaces"]
                and kwargs.get("memoryStrategyId", r["memoryStrategyId"]) == r["memoryStrategyId"]]

    def get_paginator(self, operation: str) -> Any:
        data = self

        class _Paginator:
            def paginate(self, **kwargs: Any):
                if operation == "list_events":
                    yield {"events": data.events.get((kwargs["actorId"], kwargs["sessionId"]), [])}
                else:
                    yield {"memoryRecordSummaries": data._matching(kwargs)}
        return _Paginator()

    def get_memory_record(self, memoryId: str, memoryRecordId: str) -> Dict[str, Any]:  # noqa: N803
        return {"memoryRecord": next(r for r in self.records.values()
                                     if r["memoryRecordId"] == memoryRecordId)}


def test_handout_waits_only_for_user_preferences() -> None:
    assert REQUIRED_STRATEGIES == ("preferences",)
    proof = verify_memory_readiness(_Control(), _Data(("preferences",)), "mem-1", timeout=5)
    assert proof["status"] == "ready"
    assert set(proof["strategies"]) == {"preferences"}
    assert proof["namespaceIsolation"] is True


def test_records_that_formed_in_time_are_recorded_with_the_same_checks() -> None:
    proof = verify_memory_readiness(_Control(), _Data(tuple(STRATEGIES)[:3]), "mem-1", timeout=5)
    assert set(proof["strategies"]) == set(tuple(STRATEGIES)[:3])


def test_no_preference_record_fails_provisioning_and_names_it() -> None:
    with pytest.raises(RuntimeError, match="missing: preferences"):
        verify_memory_readiness(_Control(), _Data(("facts", "summary", "episodic")), "mem-1", timeout=0)


def _found(present: tuple[str, ...]) -> Dict[str, Any]:
    return {"strategies": {kind: {"records": [{"memoryRecordId": kind}] if kind in present else []}
                           for kind in (*STRATEGIES, "reflection")}}


def test_deep_dive_is_ready_once_every_strategy_holds_a_record() -> None:
    assert deep_dive.wait_for_deep_dive(lambda: _found(tuple(STRATEGIES)), timeout=60) == {
        "status": "ready", "missing": [], "elapsedSeconds": 0.0}


def test_deep_dive_names_what_had_not_formed_when_the_wait_ran_out() -> None:
    ticks = iter(range(0, 10_000, 30))
    reads = iter([_found(("preferences",)), _found(("preferences", "facts", "summary"))] * 10)
    result = deep_dive.wait_for_deep_dive(lambda: next(reads), timeout=60, poll=30,
                                          clock=lambda: float(next(ticks)), sleep=lambda _s: None)
    assert result["status"] == "incomplete"
    assert result["missing"] == ["episodic"]


def test_the_status_file_is_replaced_whole_and_readable(tmp_path: Path) -> None:
    path = tmp_path / "memory-deep-dive.json"
    deep_dive.write_status(path, {"status": "checking"})
    deep_dive.write_status(path, {"status": "ready", "missing": []})
    assert json.loads(path.read_text())["status"] == "ready"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.parametrize(("status", "expected"), [
    ({"status": "ready"}, "every strategy holds a record"),
    ({"status": "checking", "startedAt": "2026-10-19T10:00:00Z"}, "still forming"),
    ({"status": "incomplete", "missing": ["episodic"], "elapsedSeconds": 3600}, "episodic not formed"),
    ({"status": "error", "error": "AccessDenied"}, "could not read Memory (AccessDenied)"),
])
def test_the_readiness_note_says_where_the_deep_dive_stands(tmp_path: Path, status, expected) -> None:
    path = tmp_path / "memory-deep-dive.json"
    path.write_text(json.dumps(status))
    note = event_readiness.deep_dive_note(path)
    assert note and note.startswith("i  Memory deep dive (optional appendix):")
    assert expected in note


def test_an_unfinished_deep_dive_never_changes_readiness(tmp_path: Path, monkeypatch) -> None:
    status = tmp_path / "memory-deep-dive.json"
    status.write_text(json.dumps({"status": "incomplete", "missing": ["episodic"], "elapsedSeconds": 3600}))
    monkeypatch.setenv("PELLIER_MEMORY_DEEP_DIVE_FILE", str(status))
    monkeypatch.setattr(event_readiness, "run_checks",
                        lambda run, cap: (["+ OK    everything Lab 1 needs", "Ready for Lab 1"], 0))
    record = event_readiness.record_now(run=None, logs=lambda: None, local=tmp_path / "readiness.json",
                                        now=event_readiness.datetime(2026, 10, 19), instance_id="i-1", cap=5)
    assert record["ready"] is True
    assert record["final"] == event_readiness.READY
    assert any("episodic not formed" in line for line in record["lines"])
    assert event_readiness.deep_dive_note(tmp_path / "absent.json") is None
