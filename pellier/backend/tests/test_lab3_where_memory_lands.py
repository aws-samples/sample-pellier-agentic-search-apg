"""Lab 3's Go deeper command prints where a live turn's preference lands beside the agent's read.

The client is a stand-in for ``bedrock-agentcore``: the command only lists actors and
records, so the stand-in answers those two calls, paged, and records every namespace asked.
"""

from __future__ import annotations

import base64
import importlib
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
namespaces = importlib.import_module("lab3_where_memory_lands")

SUB = "34886418-50a1-70cd-9eab-89aabfa0efeb"
LIVE = f"user-{SUB}-session-persona-theo-0001"


class FakeMemory:
    def __init__(self, actors: List[str], records: Dict[str, List[str]]) -> None:
        self.actors, self.by_namespace, self.asked = actors, records, []

    def list_actors(self, memoryId: str, nextToken: str = "") -> Dict[str, Any]:
        half = len(self.actors) // 2
        page = self.actors[half:] if nextToken else self.actors[:half]
        return {"actorSummaries": [{"actorId": a} for a in page],
                **({} if nextToken else {"nextToken": "page-2"})}

    def list_memory_records(self, memoryId: str, namespace: str) -> Dict[str, Any]:
        self.asked.append(namespace)
        return {"memoryRecordSummaries": [
            {"memoryRecordId": f"mem-{i}", "content": {"text": json.dumps({"preference": text})}}
            for i, text in enumerate(self.by_namespace.get(namespace, []))]}


def test_the_customer_namespace_comes_first_and_each_session_actor_after_it() -> None:
    memory = FakeMemory(
        ["CUST-THEO", LIVE, "CUST-MARCO", "user-someone-else-session-x"],
        {"/pellier/preferences/CUST-THEO/": ["Prefers hand-thrown stoneware"],
         f"/pellier/preferences/{LIVE}/": ["Likes ash glazes"]})
    lines = namespaces.report(memory, "mem-id", SUB)
    assert lines[0] == "/pellier/preferences/CUST-THEO/"
    assert "the agent reads this one" in lines[1]
    assert "  mem-0  Prefers hand-thrown stoneware" in lines
    assert f"/pellier/preferences/{LIVE}/" in lines
    after_live = lines[lines.index(f"/pellier/preferences/{LIVE}/") + 1]
    assert "the agent never reads this one" in after_live
    assert "  mem-0  Likes ash glazes" in lines
    assert memory.asked == ["/pellier/preferences/CUST-THEO/", f"/pellier/preferences/{LIVE}/"]


def test_empty_session_actors_are_counted_not_listed() -> None:
    lines = namespaces.report(FakeMemory([LIVE, LIVE + "-2"], {}), "mem-id", SUB)
    assert lines[-1] == "2 more session actor(s) of Theo's hold no record yet"
    assert lines.count("  no record yet") == 1, "only the customer's own empty namespace"
    assert f"/pellier/preferences/{LIVE}/" not in lines


def test_the_subject_comes_from_the_tokens_claims() -> None:
    claims = base64.urlsafe_b64encode(json.dumps({"sub": SUB}).encode()).decode().rstrip("=")
    assert namespaces.token_subject(f"header.{claims}.signature") == SUB


def test_without_memory_settings_it_says_why_and_exits_one(monkeypatch, capsys) -> None:
    def no_memory() -> Any:
        raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")

    monkeypatch.setattr(namespaces, "_connect", no_memory)
    assert namespaces.main([]) == 1
    assert "AGENTCORE_MEMORY_ID is not configured" in capsys.readouterr().out


class TimedMemory(FakeMemory):
    """Answers list_events too, and lets a record land after a number of polls."""

    def __init__(self, actors: List[str], turn_ages: Dict[str, float], now: Any,
                 lands_after: int = -1) -> None:
        super().__init__(actors, {})
        self.turn_ages, self.now, self.lands_after, self.polls = turn_ages, now, lands_after, 0

    def list_events(self, memoryId: str, actorId: str, sessionId: str,
                    includePayloads: bool) -> Dict[str, Any]:
        assert actorId == sessionId, "a live turn's actor and session are the same namespace"
        age = self.turn_ages.get(actorId)
        return {"events": [] if age is None else [
            {"eventId": "e1", "eventTimestamp": self.now - timedelta(seconds=age + 60)},
            {"eventId": "e2", "eventTimestamp": self.now - timedelta(seconds=age)}]}

    def list_memory_records(self, memoryId: str, namespace: str) -> Dict[str, Any]:
        if namespace == f"/pellier/preferences/{LIVE}/":
            self.polls += 1
            if 0 <= self.lands_after < self.polls:
                self.by_namespace[namespace] = ["Drawn to deep indigo linen"]
        return super().list_memory_records(memoryId, namespace)


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_only_a_recent_turn_with_nothing_extracted_is_waited_for() -> None:
    old = LIVE + "-old"
    memory = TimedMemory([LIVE, old, "CUST-THEO"], {LIVE: 40.0, old: 900.0}, NOW)
    assert namespaces.extracting(memory, "mem-id", SUB, now=NOW) == [(LIVE, 40.0)]


def test_the_wait_ends_when_the_record_lands() -> None:
    memory = TimedMemory([LIVE], {LIVE: 40.0}, NOW, lands_after=2)
    ticks = [0.0]
    landed = namespaces.wait_for_extraction(
        memory, "mem-id", [(LIVE, 40.0)],
        sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds), now=lambda: ticks[0])
    assert landed is True
    assert ticks[0] == 2 * namespaces.POLL_SECONDS


def test_the_wait_gives_up_once_the_turn_is_too_old_to_yield_a_record() -> None:
    memory = TimedMemory([LIVE], {LIVE: 200.0}, NOW)
    ticks = [0.0]
    landed = namespaces.wait_for_extraction(
        memory, "mem-id", [(LIVE, 200.0)],
        sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds), now=lambda: ticks[0])
    assert landed is False
    assert ticks[0] == namespaces.EXTRACTION_LIMIT_SECONDS - 200.0


def test_main_waits_then_prints_the_landed_record(monkeypatch, capsys) -> None:
    memory = TimedMemory([LIVE], {LIVE: 30.0}, datetime.now(timezone.utc), lands_after=1)
    monkeypatch.setattr(namespaces, "_connect", lambda: (memory, "mem-id", SUB))
    monkeypatch.setattr(namespaces.time, "sleep", lambda _seconds: None)
    assert namespaces.main([]) == 0
    out = capsys.readouterr().out
    assert "nothing is extracted from it yet. Waiting for it" in out
    assert "  mem-0  Drawn to deep indigo linen" in out
