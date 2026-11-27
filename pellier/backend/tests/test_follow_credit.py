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
             "handoff_audit_id": 812, "handoff_gateway_request_id": "req-ask",
             "credit_audit_id": 820, "credits_with_key": 1,
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
        assert "Task 4A" in followed.next_step and "Pay the credit once" in followed.next_step
        assert "finish --lab 4" not in followed.next_step


def test_a_missing_aurora_link_fails_and_names_the_link() -> None:
    followed = follow_credit.follow(_story(handoff_audit_id=None), _records(), NOW)
    assert followed.state == check.FAILED
    assert followed.observed == "no ask_a_person audit row in her turn opened her request"
    keyed = follow_credit.follow(_story(credits_with_key=2), _records(), NOW)
    assert keyed.state == check.FAILED and "the review's key is on 2 credits" in keyed.observed


def test_an_agent_span_from_another_turn_is_not_hers() -> None:
    other = dict(AGENT_SPAN, attributes=dict(AGENT_SPAN["attributes"], **{"turn.id": "turn-x"}))
    followed = follow_credit.follow(_story(), _records(runtime={"trace-req-ask": [other]}), NOW)
    assert followed.state == check.FAILED
    assert "names a different turn" in followed.observed
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


def _span_for(call: Dict[str, Any], turn: str = TURN) -> Dict[str, Any]:
    attrs = dict(AGENT_SPAN["attributes"], **{"turn.id": turn})
    return dict(AGENT_SPAN, traceId=call["trace_id"], attributes=attrs)


def _two_calls(identified: Dict[str, Any], other: Dict[str, Any], **changes: Any) -> Any:
    """Both calls made in her turn, both with her turn's agent span."""
    runtime = {c["trace_id"]: [_span_for(c)] for c in (identified, other)}
    return _records(handoffs=[identified, other], runtime=runtime, **changes)


def _policy_row(followed: Any) -> str:
    return next(row[2] for row in followed.rows if row[1] == "Policy")


def test_a_newer_denied_call_in_her_turn_does_not_replace_the_call_that_opened_her_request():
    newer = _call("req-newer", BASE + timedelta(seconds=30), "ask_a_person", NADIA_SUB, "DENY",
                  ["baseline_permit_workshop_tools-q1"], parent="mcp-span", ran=False)
    followed = follow_credit.follow(_story(), _two_calls(HANDOFF, newer), NOW)
    assert followed.state == check.PASSED
    assert _policy_row(followed) == "ALLOW, determined by baseline_permit_workshop_tools-q1"
    assert followed.rows[1][2] == "The Gateway accepted jessica's Cognito access token"
    assert any("req-ask" in line for line in followed.joins)


def test_the_identified_call_being_denied_fails_even_when_another_call_was_allowed():
    denied = _call("req-ask-denied", BASE, "ask_a_person", JESSICA_SUB, "DENY",
                   ["baseline_permit_workshop_tools-q1"], parent="mcp-span", ran=False)
    older = dict(HANDOFF, started_ns=HANDOFF["started_ns"] - 5 * NS)
    records = _two_calls(denied, older)
    followed = follow_credit.follow(_story(handoff_gateway_request_id="req-ask-denied"),
                                    records, NOW)
    assert followed.state == check.FAILED
    assert "DENIED" in followed.observed
    assert follow_credit.follow(_story(), records, NOW).state == check.PASSED


def test_a_denied_handoff_with_no_target_run_and_no_caller_cannot_pass():
    bare = dict(HANDOFF, decision="DENY", lambda_ms=None, subject=None, token_use=None,
                identity_checked=False)
    followed = follow_credit.follow(_story(), _records(handoffs=[bare]), NOW)
    assert followed.state != check.PASSED
    assert follow_credit.report(followed).endswith("End-to-end check failed")


def test_a_handoff_with_no_target_span_or_no_policy_decision_waits_for_cloudwatch():
    for changes in ({"lambda_ms": None}, {"decision": "none", "policies": []}):
        call = dict(HANDOFF, **changes)
        followed = follow_credit.follow(_story(), _records(handoffs=[call]), NOW)
        assert followed.state == check.COULD_NOT_CHECK, changes
        assert "about ten seconds" in followed.next_step


def test_a_handoff_with_no_caller_evidence_waits_instead_of_passing():
    for changes in ({"subject": None}, {"subject": "sub-nobody-known"}):
        followed = follow_credit.follow(_story(), _records(handoffs=[dict(HANDOFF, **changes)],
                                                           names={}), NOW)
        assert followed.state == check.COULD_NOT_CHECK, changes
    for changes in ({"token_use": None}, {"identity_checked": False}):
        records = _records(handoffs=[dict(HANDOFF, **changes)])
        assert follow_credit.follow(_story(), records, NOW).state == check.COULD_NOT_CHECK


def test_the_identified_call_not_in_cloudwatch_yet_waits_even_if_another_call_is_there():
    other = dict(HANDOFF, request_id="req-other", trace_id="trace-req-other")
    records = _two_calls(other, dict(other, request_id="req-third", trace_id="trace-req-third"))
    followed = follow_credit.follow(_story(), records, NOW)
    assert followed.state == check.COULD_NOT_CHECK
    assert "req-ask" in followed.observed
    assert "about ten seconds" in followed.next_step


def test_a_missing_runtime_span_for_the_identified_call_waits():
    followed = follow_credit.follow(_story(), _records(runtime={"trace-req-ask": []}), NOW)
    assert followed.state == check.COULD_NOT_CHECK


def test_a_handoff_record_from_before_the_gateway_request_id_cannot_be_identified():
    followed = follow_credit.follow(_story(handoff_gateway_request_id=None), _records(), NOW)
    assert followed.state == check.COULD_NOT_CHECK
    assert "predates the Gateway request id" in followed.observed
    assert "psql -f workshop/wrap-up-reconstruct.sql" in followed.next_step
    assert "finish --lab 4" not in followed.next_step


def test_payment_needs_nadias_identified_caller():
    for changes in ({"subject": None}, {"token_use": None}, {"identity_checked": False}):
        result = follow_credit.follow(_story(), _records(credits=[dict(PAID, **changes)]), NOW)
        assert result.state == check.COULD_NOT_CHECK, changes
    partial = follow_credit.follow(_story(), _records(names={JESSICA_SUB: "jessica"}), NOW)
    assert partial.state == check.COULD_NOT_CHECK
    wrong = follow_credit.follow(_story(), _records(credits=[dict(PAID, subject=JESSICA_SUB)]), NOW)
    assert wrong.state == check.FAILED and "jessica" in wrong.observed


def test_a_handoff_made_by_another_shopper_fails():
    other = dict(HANDOFF, subject=NADIA_SUB)
    followed = follow_credit.follow(_story(), _records(handoffs=[other]), NOW)
    assert followed.state == check.FAILED
    assert "made by nadia, not by Jessica" in followed.observed


def test_the_identified_calls_agent_span_naming_another_turn_fails():
    records = _records(runtime={"trace-req-ask": [_span_for(HANDOFF, "turn-x")]})
    followed = follow_credit.follow(_story(), records, NOW)
    assert followed.state == check.FAILED
    assert "names a different turn" in followed.observed


# The end-to-end check holds the exact Gateway request ids, so later activity in the hour
# cannot push the calls it identified out of a newest-N window.
sys.path.insert(0, str(Path(__file__).resolve().parent))
trace_tests = importlib.import_module("test_trace_agentcore_calls")


def _busy_logs(identified: Dict[str, str], tool: str, later: int = 25) -> Any:
    """Spans for the identified call, then ``later`` newer calls to the same tool."""
    spans = trace_tests._call(identified["request"], 1_000, tool, trace_tests.NADIA_SUB,
                              "ALLOW", ["p-1"], parent="mcp-span")
    for n in range(later):
        spans += trace_tests._call(f"req-later-{n}", 5_000 + n * 10, tool,
                                   trace_tests.NADIA_SUB, "ALLOW", ["p-1"])
    return trace_tests._Logs(spans)


def test_the_identified_call_is_found_by_its_request_id_beyond_the_newest_window() -> None:
    logs = _busy_logs({"request": "req-ask"}, "ask_a_person")
    newest = trace_tests.trace.fetch_calls(logs, "ask_a_person", 60, trace_tests.trace.CALL_LIMIT)
    assert "req-ask" not in [c["request_id"] for c in newest]
    found = trace_tests.trace.fetch_calls_by_request(logs, "ask_a_person", ["req-ask"], 60)
    assert [c["request_id"] for c in found] == ["req-ask"]
    assert logs.patterns[-1] == '?"req-ask"'


def test_a_request_id_that_is_not_in_cloudwatch_finds_nothing_and_none_means_no_read() -> None:
    logs = _busy_logs({"request": "req-ask"}, "ask_a_person", later=2)
    assert trace_tests.trace.fetch_calls_by_request(logs, "ask_a_person", ["req-gone"], 60) == []
    before = len(logs.patterns)
    assert trace_tests.trace.fetch_calls_by_request(logs, "ask_a_person", [None, ""], 60) == []
    assert len(logs.patterns) == before


def test_read_records_looks_up_both_identified_calls_however_busy_the_hour_was(
        monkeypatch: Any) -> None:
    import boto3

    handoff = trace_tests._call("req-ask", 1_000, "ask_a_person", trace_tests.NADIA_SUB,
                                "ALLOW", ["p-1"], parent="mcp-span")
    paid = trace_tests._call("req-paid", 2_000, "give_store_credit", trace_tests.NADIA_SUB,
                             "ALLOW", ["p-2"])
    later: List[Dict[str, Any]] = []
    for n in range(25):
        later += trace_tests._call(f"later-a-{n}", 5_000 + n * 10, "ask_a_person",
                                   trace_tests.NADIA_SUB, "ALLOW", ["p-1"])
        later += trace_tests._call(f"later-p-{n}", 5_000 + n * 10, "give_store_credit",
                                   trace_tests.NADIA_SUB, "ALLOW", ["p-2"])
    logs = trace_tests._Logs(handoff + paid + later)
    monkeypatch.setattr(boto3, "client", lambda *a, **k: logs)
    monkeypatch.setattr(follow_credit.trace, "read_aurora", lambda _logs, _minutes: ([], None))
    monkeypatch.setattr(follow_credit.trace, "subject_names", lambda *_a: {})
    story = _story(requested_at=datetime.now(timezone.utc))

    records = follow_credit.read_records(story)

    assert [c["request_id"] for c in records.handoffs] == ["req-ask"]
    assert [c["request_id"] for c in records.credits] == ["req-paid"]
    assert follow_credit.handoff_call(records.handoffs, "req-ask") is not None
    assert follow_credit.paid_call(records.credits, [INSERT], KEY, "req-paid")[1] is not None


def test_help_prints_usage_and_exits_before_settings_or_any_service(
        monkeypatch: Any, capsys: Any) -> None:
    import boto3
    import gateway_client

    def touched(*_a: Any, **_k: Any) -> None:
        raise AssertionError("--help must not load settings or contact a service")

    monkeypatch.setattr(gateway_client, "_load_env", touched)
    monkeypatch.setattr(boto3, "client", touched)
    monkeypatch.setattr(follow_credit, "collect", touched)
    for flag in ("--help", "-h"):
        monkeypatch.setattr(sys, "argv", ["follow_credit.py", flag])
        try:
            follow_credit.main()
        except SystemExit as stop:
            assert stop.code == 0
        else:
            raise AssertionError("--help must exit")
        assert "usage: follow_credit.py" in capsys.readouterr().out


def test_an_unknown_flag_prints_usage_and_exits_2_before_settings(
        monkeypatch: Any, capsys: Any) -> None:
    import gateway_client

    def touched(*_a: Any, **_k: Any) -> None:
        raise AssertionError("a bad flag must not load settings")

    monkeypatch.setattr(gateway_client, "_load_env", touched)
    monkeypatch.setattr(sys, "argv", ["follow_credit.py", "--nope"])
    try:
        follow_credit.main()
    except SystemExit as stop:
        assert stop.code == 2
    else:
        raise AssertionError("an unknown flag must exit")
    assert "usage: follow_credit.py" in capsys.readouterr().err
