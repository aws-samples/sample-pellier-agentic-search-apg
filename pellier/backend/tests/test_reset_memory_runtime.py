"""AgentCore Memory cleanup: every page is deleted, and residue is a failure.

Two ways the old script could report a cleaned Memory that was not clean:

1. Every list call asked for ``maxResults=100`` once and never followed ``nextToken``.
   The hundred-and-first event or preference record was never surveyed, so it was
   never deleted, and the summary counted only what it saw.
2. The delete pass reported its own call count. Nothing re-listed afterwards, so a
   record the service kept (a failed delete that returned 200, a record re-extracted
   from an event deleted a moment later) was invisible.

The fake client below pages every list call, records every delete, and can be told to
keep a record so the second survey finds it, or to keep an emptied session listed the
way the data plane does. The second of those is NOT residue: sessions and actors have
no delete, so a clean box can still list them.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "reset_memory_runtime.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pellier_reset_memory_runtime", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pages(items: List[Dict[str, Any]], key: str, size: int, token: Any) -> Dict[str, Any]:
    """Slice ``items`` into pages of ``size`` addressed by a numeric nextToken."""
    start = int(token) if token else 0
    page = items[start:start + size]
    body: Dict[str, Any] = {key: page}
    if start + size < len(items):
        body["nextToken"] = str(start + size)
    return body


class FakeMemoryClient:
    """Two-page answers everywhere, and a delete that actually removes the row."""

    PAGE = 2

    def __init__(
        self, *, sticky_record: str | None = None, sticky_sessions: bool = False
    ) -> None:
        # actor -> session -> [event ids]
        self.events: Dict[str, Dict[str, List[str]]] = {
            "operator-sub": {"s1": ["e1", "e2", "e3"], "s2": ["e4"], "s3": ["e5"]},
            "engineer-sub": {"s9": ["e9"]},
            "CUST-MARCO": {"m1": ["me1"]},
        }
        # actor -> [record ids]
        self.records: Dict[str, List[str]] = {
            "operator-sub": ["r1", "r2", "r3"],
            "engineer-sub": [],
            "CUST-MARCO": ["mr1"],
        }
        self.deleted_events: List[str] = []
        self.deleted_records: List[str] = []
        self.sticky_record = sticky_record
        # The data plane has no delete for a session or an actor. Both are derived
        # from events, and the service may keep listing an emptied one. This models
        # that: the events go, the session key stays.
        self.sticky_sessions = sticky_sessions
        self.list_calls: List[Dict[str, Any]] = []

    def list_actors(self, **kwargs: Any) -> Dict[str, Any]:
        self.list_calls.append({"op": "list_actors", **kwargs})
        actors = [{"actorId": a} for a in self.events if self.events[a] or self.records[a]]
        return _pages(actors, "actorSummaries", self.PAGE, kwargs.get("nextToken"))

    def list_sessions(self, **kwargs: Any) -> Dict[str, Any]:
        self.list_calls.append({"op": "list_sessions", **kwargs})
        sessions = [{"sessionId": s} for s in self.events.get(kwargs["actorId"], {})]
        return _pages(sessions, "sessionSummaries", self.PAGE, kwargs.get("nextToken"))

    def list_events(self, **kwargs: Any) -> Dict[str, Any]:
        self.list_calls.append({"op": "list_events", **kwargs})
        ids = self.events.get(kwargs["actorId"], {}).get(kwargs["sessionId"], [])
        return _pages([{"eventId": e} for e in ids], "events", self.PAGE, kwargs.get("nextToken"))

    def list_memory_records(self, **kwargs: Any) -> Dict[str, Any]:
        self.list_calls.append({"op": "list_memory_records", **kwargs})
        actor = kwargs["namespace"].split("/")[3]
        rows = [{"memoryRecordId": r, "content": {"text": r}} for r in self.records.get(actor, [])]
        return _pages(rows, "memoryRecordSummaries", self.PAGE, kwargs.get("nextToken"))

    def delete_event(self, **kwargs: Any) -> None:
        self.deleted_events.append(kwargs["eventId"])
        session = self.events[kwargs["actorId"]][kwargs["sessionId"]]
        session.remove(kwargs["eventId"])
        if not session and not self.sticky_sessions:
            del self.events[kwargs["actorId"]][kwargs["sessionId"]]

    def delete_memory_record(self, **kwargs: Any) -> None:
        self.deleted_records.append(kwargs["memoryRecordId"])
        if kwargs["memoryRecordId"] == self.sticky_record:
            return
        for rows in self.records.values():
            if kwargs["memoryRecordId"] in rows:
                rows.remove(kwargs["memoryRecordId"])


def test_paginate_follows_next_token_until_absent() -> None:
    module = _load_module()
    seen: List[Dict[str, Any]] = []

    def call(**kwargs: Any) -> Dict[str, Any]:
        seen.append(kwargs)
        if kwargs.get("nextToken") == "p2":
            return {"items": [{"id": 3}]}
        return {"items": [{"id": 1}, {"id": 2}], "nextToken": "p2"}

    items = module._paginate(call, "items", memoryId="m", maxResults=100)
    assert [i["id"] for i in items] == [1, 2, 3]
    assert seen == [
        {"memoryId": "m", "maxResults": 100},
        {"memoryId": "m", "maxResults": 100, "nextToken": "p2"},
    ]


def test_survey_and_cleanup_cover_every_page_of_every_list() -> None:
    module = _load_module()
    client = FakeMemoryClient()

    actors = module.survey(client, "mem-1")
    by_id = {a["actorId"]: a for a in actors}
    assert set(by_id) == {"operator-sub", "engineer-sub", "CUST-MARCO"}
    assert by_id["operator-sub"]["eventCount"] == 5
    assert len(by_id["operator-sub"]["sessions"]) == 3
    assert [r["memoryRecordId"] for r in by_id["operator-sub"]["records"]] == ["r1", "r2", "r3"]
    assert by_id["CUST-MARCO"]["preserve"] is True
    paged = [c for c in client.list_calls if "nextToken" in c]
    assert {c["op"] for c in paged} == {
        "list_actors", "list_sessions", "list_events", "list_memory_records"
    }

    counts = module.apply_cleanup(client, "mem-1", actors, apply=True)
    assert counts == {"events": 6, "records": 3, "actors": 2, "failures": 0}
    assert sorted(client.deleted_events) == ["e1", "e2", "e3", "e4", "e5", "e9"]
    assert sorted(client.deleted_records) == ["r1", "r2", "r3"]
    # The seeded persona actor is untouched.
    assert client.events["CUST-MARCO"] == {"m1": ["me1"]}
    assert client.records["CUST-MARCO"] == ["mr1"]
    assert module.residue(module.survey(client, "mem-1")) == []


def _run_main(module, monkeypatch: pytest.MonkeyPatch, client: FakeMemoryClient) -> int:
    _virtual_clock(module, monkeypatch)
    monkeypatch.setattr(module, "_env", lambda: {"AGENTCORE_MEMORY_ID": "mem-1"})
    monkeypatch.setattr(module, "_client", lambda _region: client)
    monkeypatch.setattr(sys, "argv", ["reset_memory_runtime.py", "--apply"])
    return module.main()


def _virtual_clock(module, monkeypatch: pytest.MonkeyPatch):
    now = [0.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(
        monotonic=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    ))
    return now


def test_successful_deletes_wait_for_visibility_without_repeating_writes(monkeypatch):
    module = _load_module()
    client = FakeMemoryClient()
    before = module.survey(client, "mem-1")
    observations = iter([before, before, [], []])
    monkeypatch.setattr(module, "survey", lambda *_: next(observations))

    assert _run_main(module, monkeypatch, client) == 0
    assert sorted(client.deleted_records) == ["r1", "r2", "r3"]
    assert sorted(client.deleted_events) == ["e1", "e2", "e3", "e4", "e5", "e9"]
    assert client.records["CUST-MARCO"] == ["mr1"]


def test_late_visible_record_restarts_clean_survey_count(monkeypatch):
    module = _load_module()
    now = _virtual_clock(module, monkeypatch)
    pending = module.survey(FakeMemoryClient(sticky_record="r2"), "mem-1")
    observations = iter([[], pending, [], []])
    monkeypatch.setattr(module, "survey", lambda *_: next(observations))

    assert module._report_residue(None, "mem-1") == []
    assert now[0] == 15


def test_verification_read_failure_is_not_treated_as_clean(monkeypatch):
    module = _load_module()
    _virtual_clock(module, monkeypatch)

    def unreadable(*_):
        raise PermissionError("Cannot verify Memory")

    monkeypatch.setattr(module, "survey", unreadable)
    with pytest.raises(PermissionError, match="Cannot verify"):
        module._report_residue(None, "mem-1")


def test_one_clean_read_at_deadline_does_not_prove_stable_cleanup(monkeypatch):
    module = _load_module()
    _virtual_clock(module, monkeypatch)
    pending = module.survey(FakeMemoryClient(), "mem-1")
    observations = iter([pending, []])
    monkeypatch.setattr(module, "survey", lambda *_: next(observations))
    with pytest.raises(RuntimeError, match="two clean surveys"):
        module._report_residue(None, "mem-1", timeout_seconds=5)


def test_apply_exits_two_and_names_the_residue_when_a_record_survives(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_module()
    client = FakeMemoryClient(sticky_record="r2")

    assert _run_main(module, monkeypatch, client) == 2
    out = capsys.readouterr().out
    assert "RESIDUE actor=operator-sub sessions=0 events=0 records=1" in out
    assert "RESIDUE actor=engineer-sub" not in out
    assert "RESIDUE actor=CUST-MARCO" not in out


def test_apply_exits_zero_when_the_second_survey_finds_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_module()
    client = FakeMemoryClient()

    assert _run_main(module, monkeypatch, client) == 0
    assert "RESIDUE" not in capsys.readouterr().out


def test_an_emptied_session_that_is_still_listed_is_not_residue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Residue is data the box still holds, not a name the service still lists.

    The data plane exposes no delete for a session or an actor: both are derived
    from events, and an emptied session can keep appearing in `list_sessions`.
    Counting that as residue quarantines a box whose Memory is genuinely clean,
    and only a full successful reset lifts the marker, so the box never recovers.
    """
    module = _load_module()
    client = FakeMemoryClient(sticky_sessions=True)

    assert _run_main(module, monkeypatch, client) == 0
    out = capsys.readouterr().out
    assert "RESIDUE" not in out
    # The sessions are still there. That is the whole point of the case.
    assert client.events["operator-sub"] == {"s1": [], "s2": [], "s3": []}


def test_residue_counts_events_and_records_but_reports_sessions() -> None:
    """One predicate, stated directly, so the rule is not inferred from a fake."""
    module = _load_module()
    empty = {
        "actorId": "operator-sub",
        "preserve": False,
        "sessions": [{"sessionId": "s1", "eventIds": []}],
        "eventCount": 0,
        "records": [],
    }
    assert module.residue([empty]) == []
    assert module.residue([{**empty, "eventCount": 1}]) == [{**empty, "eventCount": 1}]
    with_record = {**empty, "records": [{"memoryRecordId": "r1", "text": "r1"}]}
    assert module.residue([with_record]) == [with_record]
    # A preserved actor holding both is still never residue.
    assert module.residue([{**with_record, "preserve": True, "eventCount": 4}]) == []


def test_survey_covers_facts_summaries_episodes_and_preferences() -> None:
    module = _load_module()

    class AllStrategiesClient(FakeMemoryClient):
        def list_memory_records(self, **kwargs):
            self.list_calls.append({"op": "list_memory_records", **kwargs})
            prefix, actor = kwargs["namespace"].split("/")[2:4]
            return {"memoryRecordSummaries": [{"memoryRecordId": f"{actor}-{prefix}", "content": {"text": prefix}}]}

    client = AllStrategiesClient()
    actors = module.survey(client, "memory")
    owned = next(a for a in actors if a["actorId"] == "operator-sub")
    assert {r["text"] for r in owned["records"]} == {"preferences", "facts", "summaries", "episodes"}
    assert next(a for a in actors if a["actorId"] == "CUST-MARCO")["preserve"] is True
    assert not client.deleted_events and not client.deleted_records
