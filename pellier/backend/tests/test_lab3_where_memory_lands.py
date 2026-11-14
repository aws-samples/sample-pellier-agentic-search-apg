"""The optional Memory read reports only what Theo actually said and what Memory holds."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import lab3_where_memory_lands as showcase

SESSION = "user-theo-session-live"


class Memory:
    def __init__(self, *, role="USER", preference="Likes stoneware", live=True):
        self.role = role
        self.preference = preference
        self.live = live

    def list_sessions(self, *, memoryId, actorId, nextToken=None):
        assert actorId == "CUST-THEO"
        if not nextToken:
            return {"sessionSummaries": [{"sessionId": "prefseed"}], "nextToken": "next"}
        return {"sessionSummaries": [{"sessionId": SESSION}] if self.live else []}

    def list_events(self, *, memoryId, actorId, sessionId, includePayloads):
        assert actorId == "CUST-THEO" and sessionId == SESSION and includePayloads
        message = {"role": self.role, "content": {"text": "I'm drawn to deep indigo linen."}}
        return {"events": [{"eventId": "live-turn", "payload": [{"conversational": message}]}]}

    def list_memory_records(self, *, memoryId, namespace):
        assert namespace == "/pellier/preferences/CUST-THEO/"
        return {"memoryRecordSummaries": [
            {"memoryRecordId": "theo-record", "namespaces": [namespace],
             "content": {"text": json.dumps({"preference": self.preference})}},
            {"memoryRecordId": "other", "namespaces": ["/pellier/preferences/CUST-ANNA/"],
             "content": {"text": json.dumps({"preference": "likes indigo"})}},
        ]}


def test_seed_record_and_live_event_do_not_prove_extraction():
    output = "\n".join(showcase.report(Memory(), "mem"))
    assert "live-turn" in output and SESSION in output
    assert "No matching preference record yet" in output
    assert "theo-record" not in output and "other" not in output


def test_report_names_the_customer_record_and_the_live_turn_separately():
    output = "\n".join(showcase.report(Memory(preference="Prefers indigo linen"), "mem"))
    assert "/pellier/preferences/CUST-THEO/" in output
    assert "live-turn" in output and "theo-record" in output and "Prefers indigo linen" in output


def test_a_record_or_assistant_message_alone_is_not_a_shopper_turn():
    for memory in (Memory(live=False), Memory(role="ASSISTANT")):
        output = "\n".join(showcase.report(memory, "mem"))
        assert "No matching shopper message" in output and "live-turn" not in output


def test_read_failure_is_visible_and_exits_one(monkeypatch, capsys):
    def unavailable():
        raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
    monkeypatch.setattr(showcase, "_connect", unavailable)
    assert showcase.main([]) == 1
    assert "AGENTCORE_MEMORY_ID is not configured" in capsys.readouterr().out
