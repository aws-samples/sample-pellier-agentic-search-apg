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
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
namespaces = importlib.import_module("lab3_memory_namespaces")

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
    assert "the agent never reads this one" in lines[lines.index(f"/pellier/preferences/{LIVE}/") + 1]
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
