"""``scripts/lab3_check.py``: Task 3B's four findings.

Each never blurs "did not happen" with "could not look".

The build is one query on ``tool_audit.build_fingerprint`` beside this
checkout's digest; the memory is the managed rail's own AgentCore Memory read
for Theo beside the record his provisioning conversation produced; the reads
are the executed Gateway ``get_tickets`` rows in Theo's turns; the probe is
Theo's own token asking for Jessica's tickets. A 401 or a transport error is never a Cedar
decision.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
lab3 = importlib.import_module("lab3_check")
check = lab3.check

BUILD = "b" * 64
BUILD_ROW = {"audit_id": 7, "turn_id": "turn-theo", "tool": "get_tickets",
             "deployed_fingerprint": BUILD}


class TestTheBuild:
    def test_the_same_build_is_proved_and_prints_both(self) -> None:
        finding = lab3.judge_build(BUILD_ROW, BUILD)
        assert finding.state == check.PROVED
        assert f"deployed build   {BUILD}" in finding.evidence
        assert f"this checkout    {BUILD}" in finding.evidence

    def test_another_build_contradicts_and_names_the_deploy(self) -> None:
        finding = lab3.judge_build(BUILD_ROW, "c" * 64)
        assert finding.state == check.CONTRADICTED
        assert "--mode participant" in finding.next_step
        # Choosing the shopper already signed in starts nothing; signing out
        # first gives the retry a new Runtime session.
        assert "Sign out, choose Theo, and send it again." in finding.next_step

    def test_no_turn_is_not_yet_and_an_unstamped_row_is_unchecked(self) -> None:
        assert lab3.judge_build(None, BUILD).state == check.NOT_YET
        unstamped = {**BUILD_ROW, "deployed_fingerprint": None}
        assert lab3.judge_build(unstamped, BUILD).state == check.UNCHECKED
        assert lab3.judge_build(BUILD_ROW, "").state == check.UNCHECKED

    def test_the_checkout_digest_is_the_runtime_fingerprint(self) -> None:
        from services.build_fingerprint import compute_fingerprint

        assert lab3.local_fingerprint() == compute_fingerprint(REPO / "pellier" / "backend")


class TestTheReads:
    THEO = {"audit_id": 7, "turn_id": "turn-theo", "customer_id": "CUST-THEO"}

    def test_theos_own_reads_are_proved(self) -> None:
        finding = lab3.judge_tickets([self.THEO])
        assert finding.state == check.PROVED
        assert finding.observed == "1 executed call(s), 1 for CUST-THEO, 0 for anyone else"

    def test_a_read_for_jessica_contradicts(self) -> None:
        finding = lab3.judge_tickets([self.THEO, {**self.THEO, "customer_id": "CUST-JESSICA"}])
        assert finding.state == check.CONTRADICTED
        assert "CUST-JESSICA" in " ".join(finding.evidence)

    def test_no_read_is_not_yet(self) -> None:
        assert lab3.judge_tickets([]).state == check.NOT_YET


class TestTheProbe:
    DENY = {"action": "pellier-store-tools___get_tickets", "turn_id": "turn-lab3-probe-1",
            "outcome": "deny", "cedar_denial": True,
            "error": "Tool call not allowed due to policy enforcement"}

    def test_a_cedar_denial_with_no_row_is_proved(self) -> None:
        finding = lab3.judge_probe(self.DENY, 0)
        assert finding.state == check.PROVED
        assert "the Gateway said: Tool call not allowed" in finding.evidence[-1]

    def test_an_allow_contradicts(self) -> None:
        allow = {**self.DENY, "outcome": "allow", "cedar_denial": False, "error": None}
        assert lab3.judge_probe(allow, 1).state == check.CONTRADICTED

    def test_a_401_or_transport_error_is_not_a_policy_decision(self) -> None:
        failure = {**self.DENY, "outcome": "error", "cedar_denial": False, "error": "401"}
        finding = lab3.judge_probe(failure, 0)
        assert finding.state == check.UNCHECKED
        assert "not a policy decision" in finding.next_step

    def test_a_denial_that_left_a_row_contradicts(self) -> None:
        assert lab3.judge_probe(self.DENY, 1).state == check.CONTRADICTED

    def test_a_denial_whose_rows_could_not_be_read_is_unchecked(self) -> None:
        """Could not look is not did not happen: no rows read, no verdict on them."""
        finding = lab3.judge_probe(self.DENY, None)
        assert finding.state == check.UNCHECKED
        assert "could not be read" in finding.observed
        assert "rows not read" in " ".join(finding.evidence)

    def test_no_managed_environment_is_unchecked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in ("AGENTCORE_GATEWAY_URL", "COGNITO_TEST_CREDENTIALS_SECRET_ARN"):
            monkeypatch.delenv(key, raising=False)
        import gateway_client

        monkeypatch.setattr(gateway_client, "_load_env", lambda: None)
        finding = lab3.run_probe(None)
        assert finding.state == check.UNCHECKED
        assert "workshop box" in finding.next_step


THEO_EVENT = {"eventId": "0000001-theo-1", "payload": [{"conversational": {
    "role": "USER", "content": {"text": "I'm building a home slowly, with hand-thrown ceramics"}}}]}
SEEDED = {"actor": "CUST-THEO", "session": "prefseed",
          "namespace": "/pellier/preferences/CUST-THEO/", "events": [THEO_EVENT],
          "records": [{"memoryRecordId": "mem-theo-1"}]}
REMEMBERED = [{"record_id": "mem-theo-1",
               "preference": "Prefers hand-thrown ceramics and stoneware"}]


class TestTheMemory:
    def test_the_managed_read_returning_the_provisioned_record_is_proved(self) -> None:
        finding = lab3.judge_memory("mem-1", SEEDED, REMEMBERED)
        assert finding.state == check.PROVED
        evidence = "\n".join(finding.evidence)
        assert "source event 0000001-theo-1 (actor CUST-THEO, session prefseed)" in evidence
        assert "record mem-theo-1: Prefers hand-thrown ceramics and stoneware" in evidence
        assert ("Remembered: AgentCore Memory record mem-theo-1 (user preference)"
                in evidence), "the line the Builder view prints"

    def test_no_extraction_yet_is_not_yet(self) -> None:
        waiting = {**SEEDED, "records": []}
        assert lab3.judge_memory("mem-1", waiting, []).state == check.NOT_YET

    def test_a_missing_conversation_or_a_read_that_misses_it_contradicts(self) -> None:
        missing = lab3.judge_memory("mem-1", {**SEEDED, "events": [], "records": []}, [])
        assert missing.state == check.CONTRADICTED
        assert "seed_agentcore_memory.py" in missing.next_step
        assert lab3.judge_memory("mem-1", SEEDED, []).state == check.CONTRADICTED
        foreign = [{"record_id": "mem-other", "preference": "Not from provisioning"}]
        assert lab3.judge_memory("mem-1", SEEDED, foreign).state == check.CONTRADICTED

    def test_memory_that_cannot_be_read_is_unchecked(self) -> None:
        def _no_memory() -> dict:
            raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")

        finding = lab3.memory_finding(_no_memory)
        assert finding.state == check.UNCHECKED
        assert "AGENTCORE_MEMORY_ID" in finding.evidence[0]

    def test_the_check_reads_with_the_managed_rails_own_strict_client(self, monkeypatch) -> None:
        """The same read the storefront's managed rail makes, keyed on CUST-THEO."""
        import seed_agentcore_memory
        import services.agentcore_memory as memory_module
        from config import settings

        reads: list = []

        class _Strict:
            def __init__(self, *, memory_id: str, region: str, strict: bool) -> None:
                reads.append(("init", memory_id, strict))

            async def get_semantic_memories(self, customer_id: str) -> list:
                reads.append(("read", customer_id))
                return list(REMEMBERED)

        import gateway_client

        monkeypatch.setattr(gateway_client, "_load_env", lambda: None)
        monkeypatch.setattr(settings, "AGENTCORE_MEMORY_ID", "mem-1", raising=False)
        monkeypatch.setattr(memory_module, "AgentCoreMemory", _Strict)
        monkeypatch.setattr(seed_agentcore_memory, "seeded_memory",
                            lambda control, data, memory_id, actor: dict(SEEDED))
        monkeypatch.setattr("boto3.client", lambda *a, **k: object())
        found = lab3.read_memory()
        assert reads == [("init", "mem-1", True), ("read", "CUST-THEO")]
        assert lab3.judge_memory(found["memory_id"], found["seeded"],
                                 found["remembered"]).state == check.PROVED


def test_the_build_and_reads_are_read_from_the_real_schema(fresh_db: Any) -> None:  # noqa: F811
    """One query on tool_audit.build_fingerprint, and every executed ticket read."""
    cfg = {"DB_HOST": str(fresh_db.socket), "DB_PORT": "5432", "DB_NAME": "postgres",
           "DB_USER": "postgres", "DB_PASSWORD": ""}
    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", autocommit=True) as conn:
        conn.execute("""
            INSERT INTO pellier.tool_audit
                   (session_id, tool, caller, args, result, latency_ms, build_fingerprint)
            VALUES ('turn-theo-1', 'get_tickets', 'gateway', '{"customer_id": "CUST-THEO"}',
                    '{"status": "success"}', 12, %s),
                   ('persona-theo-x', 'get_tickets', 'agent', '{"customer_id": "CUST-THEO"}',
                    '{"status": "success"}', 9, NULL)""", (BUILD,))
    rows = lab3.read_rows(cfg)
    assert rows["build"]["deployed_fingerprint"] == BUILD
    assert [r["customer_id"] for r in rows["tickets"]] == ["CUST-THEO"], "Gateway reads only"
    assert lab3.judge_build(rows["build"], BUILD).state == check.PROVED
    assert lab3.judge_tickets(rows["tickets"]).state == check.PROVED


def test_the_reads_are_theos_turns_only(fresh_db: Any) -> None:  # noqa: F811
    """Jessica's own Lab 4 turn reads her tickets on the Gateway; that is not Theo's read.

    A read for another customer inside a turn bound to Theo still contradicts.
    """
    cfg = {"DB_HOST": str(fresh_db.socket), "DB_PORT": "5432", "DB_NAME": "postgres",
           "DB_USER": "postgres", "DB_PASSWORD": ""}
    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", autocommit=True) as conn:
        conn.execute("""
            INSERT INTO pellier.tool_audit
                   (session_id, tool, caller, args, result, latency_ms, build_fingerprint)
            VALUES ('turn-theo-scope', 'get_tickets', 'gateway', '{"customer_id": "CUST-THEO"}',
                    '{"status": "success"}', 12, %s),
                   ('turn-jessica-scope', 'get_tickets', 'gateway',
                    '{"customer_id": "CUST-JESSICA"}', '{"status": "success"}', 11, %s),
                   ('turn-jessica-scope', 'ask_a_person', 'gateway',
                    '{"customer_id": "CUST-JESSICA"}', '{"status": "handed_off"}', 10, %s)""",
                     (BUILD, BUILD, BUILD))
    mine = [r for r in lab3.read_rows(cfg)["tickets"] if r["turn_id"].endswith("-scope")]
    assert [r["turn_id"] for r in mine] == ["turn-theo-scope"]
    assert lab3.judge_tickets(mine).state == check.PROVED

    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", autocommit=True) as conn:
        conn.execute("""
            INSERT INTO pellier.tool_audit
                   (session_id, tool, caller, args, result, latency_ms, build_fingerprint)
            VALUES ('turn-theo-scope', 'get_tickets', 'gateway', '{"customer_id": "CUST-JESSICA"}',
                    '{"status": "success"}', 9, %s)""", (BUILD,))
    mine = [r for r in lab3.read_rows(cfg)["tickets"] if r["turn_id"].endswith("-scope")]
    assert [r["customer_id"] for r in mine] == ["CUST-THEO", "CUST-JESSICA"]
    assert lab3.judge_tickets(mine).state == check.CONTRADICTED
