"""Jessica's credit followed end to end: her agent's ADOT span, AgentCore's spans, Aurora's rows
and pgAudit's INSERT, joined by her turn ID and the review's key.

The spans keep the names and attributes the live service writes, as in
test_trace_agentcore_calls.py. A link that is missing names itself, and a record that has not
reached CloudWatch yet reads COULD NOT CHECK rather than FAILED.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
follow_credit = importlib.import_module("follow_credit")
check = importlib.import_module("workshop_check")

JESSICA_SUB, NADIA_SUB = "7f1c2e90-jessica", "04c8b408-nadia"
NAMES = {JESSICA_SUB: "jessica", NADIA_SUB: "nadia"}
TURN = "turn-c36b4da400904d278732bfa644aaf2a9"
KEY = "operator-review:13:" + "ab" * 16
BASE = datetime(2026, 11, 5, 5, 0, 0, tzinfo=timezone.utc)
NOW = (BASE + timedelta(minutes=20)).timestamp()
NS = 1_000_000_000


def _call(request: str, at: datetime, tool: str, sub: str, decision: str,
          policies: List[str], parent: str = "", ran: bool = True) -> Dict[str, Any]:
    return {"request_id": request, "trace_id": f"trace-{request}", "parent_span_id": parent or None,
            "started_ns": int(at.timestamp() * NS), "tool": tool, "decision": decision,
            "policies": policies, "reason": None, "subject": sub, "token_use": "access",
            "authorizer": "CUSTOM_JWT", "identity_checked": True, "gateway_ms": 900,
            "lambda_ms": 412 if ran else None}


HANDOFF = _call("req-ask", BASE, "ask_a_person", JESSICA_SUB, "ALLOW",
                ["baseline_permit_workshop_tools-q1"], parent="mcp-span")
DENIED = _call("req-deny", BASE + timedelta(minutes=5), "give_store_credit", NADIA_SUB, "DENY",
               ["credit_limit-q6"], ran=False)
PAID = _call("req-paid", BASE + timedelta(minutes=9), "give_store_credit", NADIA_SUB, "ALLOW",
             ["credit_limit-q6"])
AGENT_SPAN = {"name": "invoke_agent support", "traceId": "trace-req-ask", "attributes": {
    "gen_ai.agent.name": "support", "gen_ai.request.model": "global.anthropic.claude-opus-5-5",
    "turn.id": TURN}}
INSERT = {"second": PAID["started_ns"] / NS + 0.4, "audit_type": "OBJECT", "class": "WRITE",
          "command": "INSERT", "object": "pellier.store_credits", "statement": "INSERT ...",
          "key": KEY}


def _story(**changes: Any) -> Dict[str, Any]:
    story = {"credit_id": 7, "amount_cents": 4000, "idempotency_key": KEY,
             "credited_at": BASE + timedelta(minutes=9, seconds=1), "review_id": 13,
             "write_key": KEY, "order_ids": [1041, 1042],
             "proposed_at": BASE + timedelta(minutes=2), "proposed_cents": 4000, "approver": "Nadia", "decided_at": BASE + timedelta(minutes=4),
             "request_id": 12, "turn_id": TURN, "requested_at": BASE + timedelta(seconds=1),
             "handoff_audit_id": 812, "credit_audit_id": 820, "credits_with_key": 1,
             "credit_gateway_request_id": "req-paid"}
    story.update(changes)
    return story


def _records(**changes: Any) -> Any:
    fields = {"handoffs": [HANDOFF], "runtime": {"trace-req-ask": [AGENT_SPAN]},
              "credits": [DENIED, PAID], "writes": [INSERT], "unavailable": None, "names": NAMES}
    fields.update(changes)
    return follow_credit.Records(**fields)


def test_every_record_joins_into_one_chain_from_her_agent_to_the_credit() -> None:
    followed = follow_credit.follow(_story(), _records(), NOW)
    assert followed.state == check.PASSED
    steps = [row[1] for row in followed.rows]
    assert steps == ["Agent", "Identity", "Policy", "Request", "Review", "Approval",
                     "Identity", "Policy", "Tool", "Database", "Credit"]
    agent, identity, policy = followed.rows[:3]
    assert agent[2] == ("Support agent on global.anthropic.claude-opus-5-5 called ask_a_person "
                        "in turn turn-c36b4da400904...")
    assert agent[3] == "CloudWatch: ADOT span"
    assert identity[2] == "The Gateway accepted jessica's Cognito access token"
    assert policy[2] == "ALLOW, determined by baseline_permit_workshop_tools-q1"
    assert followed.rows[3][3] == "Aurora: tool_audit 812, approvals 12"
    assert followed.rows[5][2] == "Nadia approved review 13"
    assert followed.rows[6][2] == "The Gateway accepted nadia's Cognito access token"
    assert followed.rows[9][2:] == ["INSERT into pellier.store_credits with the same key",
                                    "PostgreSQL log: pgAudit"]
    assert followed.rows[10][2] == "Credit 7, $40.00, with the same key"
    assert any(TURN in line for line in followed.joins)
    assert any(KEY in line for line in followed.joins)


def test_the_paid_call_is_the_one_that_holds_the_insert_not_the_earlier_deny() -> None:
    followed = follow_credit.follow(_story(), _records(), NOW)
    nadia_policy = followed.rows[7]
    assert nadia_policy[0] == "05:09:00"
    assert nadia_policy[2] == "ALLOW, determined by credit_limit-q6"


def test_the_report_ends_with_the_pass_line_only_when_every_link_is_found() -> None:
    passed = follow_credit.report(follow_credit.follow(_story(), _records(), NOW))
    assert passed.splitlines()[-1] == "End-to-end check passed"
    assert "CloudWatch: ADOT span" in passed and "PostgreSQL log: pgAudit" in passed
    waiting = follow_credit.report(follow_credit.follow(_story(), _records(writes=[]),
                                                        BASE.timestamp() + 9 * 60 + 30))
    assert waiting.splitlines()[-1] == "End-to-end check failed"
    assert "COULD NOT CHECK  the PostgreSQL log has not been exported yet" in waiting


def test_no_credit_yet_is_not_yet_and_reads_nothing_else() -> None:
    for story in (None, _story(credit_id=None)):
        followed = follow_credit.follow(story, _records(handoffs=[], credits=[]), NOW)
        assert followed.state == check.NOT_YET
        assert "finish Lab 4" in followed.next_step


def test_a_missing_aurora_link_fails_and_names_the_link() -> None:
    followed = follow_credit.follow(_story(handoff_audit_id=None), _records(), NOW)
    assert followed.state == check.FAILED
    assert followed.observed == "no ask_a_person audit row carries her request's turn"
    keyed = follow_credit.follow(_story(credits_with_key=2), _records(), NOW)
    assert keyed.state == check.FAILED and "2 credit(s) carry the review's key" in keyed.observed


def test_an_agent_span_from_another_turn_is_not_hers() -> None:
    other = dict(AGENT_SPAN, attributes=dict(AGENT_SPAN["attributes"], **{"turn.id": "turn-x"}))
    followed = follow_credit.follow(_story(), _records(runtime={"trace-req-ask": [other]}), NOW)
    assert followed.state == check.COULD_NOT_CHECK
    assert followed.observed == "no ask_a_person call in CloudWatch carries her turn's agent span"
    assert [row[1] for row in followed.rows] == ["Review", "Approval"]


def test_an_unreadable_runtime_group_says_so_instead_of_blaming_the_turn() -> None:
    followed = follow_credit.follow(_story(), _records(runtime={"trace-req-ask": None}), NOW)
    assert followed.state == check.COULD_NOT_CHECK
    assert followed.observed == "the Runtime's log group could not be read"


def test_pgaudit_off_or_unread_cannot_vouch_for_the_write() -> None:
    reason = "pgAudit is off on this cluster: the pgaudit extension is not installed"
    followed = follow_credit.follow(_story(), _records(writes=[], unavailable=reason), NOW)
    assert followed.state == check.COULD_NOT_CHECK and followed.observed == reason
    assert [row[1] for row in followed.rows][:4] == ["Agent", "Identity", "Policy", "Request"]


def test_pgaudit_that_cannot_see_the_gateways_credit_fails_instead_of_waiting() -> None:
    # A log that can never record the write is a defect, not a log still on its way: this is
    # the gap that made this check fail on governed 5f099fe2, and it must keep failing.
    trace = importlib.import_module("trace_agentcore_calls")
    reason = trace.gateway_blind_spot({"gateway_login_seen": False, "runs_as": "postgres"})
    followed = follow_credit.follow(_story(), _records(writes=[], unavailable=reason), NOW)
    assert followed.state == check.FAILED and followed.observed == reason
    assert followed.next_step == ("this is a fault in the workshop's database, not in your labs. "
                                  "Raise your hand so a facilitator can check it.")
    assert follow_credit.report(followed).endswith("End-to-end check failed")


def test_no_insert_after_the_export_lag_fails() -> None:
    followed = follow_credit.follow(_story(), _records(writes=[]), NOW)
    assert followed.state == check.FAILED
    assert followed.observed == "pgAudit logged no INSERT with the review's key"


def test_an_insert_with_another_key_is_not_her_credit() -> None:
    probe = dict(INSERT, key="operator-review:99:" + "cd" * 16)
    followed = follow_credit.follow(_story(), _records(writes=[probe]), NOW)
    assert followed.state == check.FAILED


def test_two_inserts_with_her_key_fail_the_paid_once_claim() -> None:
    again = dict(INSERT, second=INSERT["second"] + 30)
    followed = follow_credit.follow(_story(), _records(writes=[INSERT, again]), NOW)
    assert followed.state == check.FAILED
    assert followed.observed == "pgAudit logged 2 INSERTs with the review's key"


def test_an_insert_no_gateway_call_holds_waits_for_the_spans() -> None:
    followed = follow_credit.follow(_story(), _records(credits=[DENIED]), NOW)
    assert followed.state == check.COULD_NOT_CHECK
    assert followed.observed == "no give_store_credit ALLOW with target execution matches the receipt's Gateway request id"


def test_the_story_sql_follows_the_same_joins_as_the_wrap_up_reconstruction() -> None:
    reconstruct = (REPO / "workshop" / "wrap-up-reconstruct.sql").read_text(encoding="utf-8")
    for join in ("c.approval_id = a.id", "q.answered_by_review_id = r.id",
                 "'operator-review:' || a.id || ':' || left(a.action_hash, 32)",
                 "t.session_id = q.source_turn_id"):
        assert join in reconstruct and join in follow_credit.STORY_SQL


def test_an_overlapping_denial_cannot_become_the_paid_call():
    denied = dict(DENIED, started_ns=PAID["started_ns"])
    inserts, paid = follow_credit.paid_call([denied, PAID], [INSERT], KEY, "req-paid")
    assert inserts == [INSERT] and paid == PAID
    assert follow_credit.paid_call([denied, PAID], [INSERT], KEY, "req-deny")[1] is None
    assert follow_credit.paid_call([denied, PAID], [INSERT], KEY)[1] is None
    assert follow_credit.follow(_story(credit_gateway_request_id=None), _records(), NOW).state != check.PASSED


def test_a_correlated_allow_with_missing_target_span_is_incomplete():
    result = follow_credit.follow(_story(), _records(credits=[dict(PAID, lambda_ms=None)]), NOW)
    assert result.state == check.COULD_NOT_CHECK
