"""The terminal trace of a Gateway call, read from AgentCore's spans in ``aws/spans``.

The spans here keep the names and attributes the live service writes. An ALLOW
call has a Lambda invocation span; a DENY call has none, and the trace says the
target was never invoked rather than inferring it from the decision.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
trace = importlib.import_module("trace_agentcore_calls")

THEO_SUB, NADIA_SUB = "34389418-theo", "04c8b408-nadia"


def _span(name: str, request: str, start: int, **attrs: Any) -> Dict[str, Any]:
    return {"name": name, "traceId": f"trace-{request}", "startTimeUnixNano": str(start),
            "durationNano": "326000000", "attributes": {"aws.request.id": request, **attrs}}


def _call(request: str, start: int, tool: str, sub: str, decision: str,
          policies: List[str], reason: str = "", ran: bool = True,
          parent: str = "") -> List[Dict[str, Any]]:
    action = f"pellier-store-tools___{tool}"
    invoke = _span("AgentCore.Gateway.InvokeTool", request, start, **{
        "url.path": "tools/call", "tool.name": action, "latency_ms": 504,
        "aws.agentcore.policy.authorization_decision": decision})
    if parent:
        invoke["parentSpanId"] = parent
    spans = [
        _span("AgentCore.Gateway.InboundAuth", request, start, **{
            "auth.inbound.authorizer_type": "CUSTOM_JWT", "jwt.sub": sub,
            "jwt.token_use": "access"}),
        _span("AgentCore.Identity.Authorize", request, start + 1, component_owner="IDENTITY"),
        invoke,
        _span("AgentCore.Policy.AuthorizeAction", request, start + 2, **{
            "aws.agentcore.policy.authorization_decision": decision,
            "aws.agentcore.policy.determining_policies": policies,
            "aws.agentcore.policy.authorization_reason": reason}),
    ]
    if ran:
        spans.append(_span("AgentCore.Gateway.TargetInvocation", request, start + 3, **{
            "tool.name": action, "target.type": "LAMBDA"}))
    return spans


ALLOW = _call("req-allow", 1_000, "get_tickets", THEO_SUB, "ALLOW",
              ["get_tickets_owner_only-abc", "get_tickets_owner_only-abc"], parent="mcp-span")
RUNTIME = [
    {"name": "invoke_agent support", "traceId": "trace-req-allow", "attributes": {
        "gen_ai.agent.name": "support", "gen_ai.request.model": "global.anthropic.claude-opus-5-5",
        "turn.id": "turn-abc"}},
    {"name": "MCP send tools/call pellier-store-tools___get_tickets", "spanId": "mcp-span",
     "traceId": "trace-req-allow", "attributes": {}},
]
DENY = _call("req-deny", 2_000, "get_tickets", THEO_SUB, "DENY", [],
             reason="No policy applies to the request (denied by default).", ran=False)
LIST = [_span("AgentCore.Policy.PartiallyAuthorizeActions", "req-list", 3_000, **{
    "aws.agentcore.policy.allowed_tools": ["pellier-store-tools___get_tickets"]})]
CREDIT = _call("req-credit", 4_000, "give_store_credit", NADIA_SUB, "DENY",
               ["workshop_credit_limit-xyz"], reason="request missing field(s)", ran=False)
NAMES = {THEO_SUB: "theo", NADIA_SUB: "nadia"}


def test_an_allow_and_a_deny_read_as_two_calls_oldest_first() -> None:
    calls = trace.calls_from_spans(DENY + LIST + ALLOW + CREDIT, "get_tickets")
    assert [(c["request_id"], c["decision"]) for c in calls] == [
        ("req-allow", "ALLOW"), ("req-deny", "DENY")]
    allow, deny = calls
    assert allow["policies"] == ["get_tickets_owner_only-abc"]
    assert allow["lambda_ms"] == 326 and deny["lambda_ms"] is None
    assert allow["subject"] == THEO_SUB and allow["identity_checked"]


def test_the_deny_says_the_lambda_was_never_invoked() -> None:
    allow, deny = trace.calls_from_spans(ALLOW + DENY, "get_tickets")
    allow_lines = trace.render_call(allow, NAMES)
    deny_lines = trace.render_call(deny, NAMES)
    assert allow_lines[0].endswith("theo     get_tickets  ALLOW  ->  Lambda ran (326 ms)")
    assert allow_lines[3] == "  Policy    ALLOW, determined by get_tickets_owner_only-abc"
    assert deny_lines[0].endswith("DENY  ->  Lambda never called")
    assert deny_lines[2] == "  Identity  CUSTOM_JWT authorizer accepted theo's Cognito access token"
    assert deny_lines[3] == ("  Policy    DENY: No policy applies to the request "
                             "(denied by default).")
    assert "never invoked" in deny_lines[4]


def test_a_determining_policy_is_named_instead_of_the_service_reason() -> None:
    (credit,) = trace.calls_from_spans(CREDIT, "give_store_credit")
    lines = trace.render_call(credit, NAMES)
    assert lines[3] == "  Policy    DENY, determined by workshop_credit_limit-xyz"
    assert "missing field" not in "\n".join(lines)


def test_an_unknown_subject_prints_as_its_prefix() -> None:
    (allow,) = trace.calls_from_spans(ALLOW, "get_tickets")
    assert "sub 34389418..." in trace.render_call(allow, {})[0]


def test_the_runtime_line_names_the_agent_and_turn_or_says_the_call_was_direct() -> None:
    allow, deny = trace.calls_from_spans(ALLOW + DENY, "get_tickets")
    assert allow["parent_span_id"] == "mcp-span" and deny["parent_span_id"] is None
    assert trace.render_call(allow, NAMES, RUNTIME)[1] == (
        "  Runtime   Support agent on global.anthropic.claude-opus-5-5, turn turn-abc, "
        "made this call")
    assert trace.runtime_summary(deny, None) == (
        "none: this call came to the Gateway directly, not through the Runtime")
    assert trace.runtime_summary(allow, []).endswith("its spans are not in CloudWatch yet")
    assert trace.runtime_summary(allow, None).endswith("its spans are not readable")


def test_a_runtime_call_outside_a_pellier_turn_says_so_instead_of_an_empty_turn() -> None:
    # agentcore invoke (Lab 3, Go deeper) and the deploy's smoke test call the Runtime with no
    # Pellier turn, so its agent span carries turn.id "".
    (allow,) = trace.calls_from_spans(ALLOW, "get_tickets")
    direct = [dict(RUNTIME[0], attributes=dict(RUNTIME[0]["attributes"], **{"turn.id": ""})),
              RUNTIME[1]]
    assert trace.runtime_summary(allow, direct) == (
        "Support agent on global.anthropic.claude-opus-5-5, invoked directly with no Pellier "
        "turn, made this call")


class _Logs:
    """FilterLogEvents over the spans above, matching quoted terms as the service does."""

    def __init__(self, spans: List[Dict[str, Any]]) -> None:
        self.messages = [json.dumps(span) for span in spans]
        self.patterns: List[str] = []
        self.where: List[Dict[str, Any]] = []

    def get_paginator(self, operation: str) -> Any:
        assert operation == "filter_log_events"
        outer = self

        class _Paginator:
            def paginate(self, **kwargs: Any):
                pattern = kwargs["filterPattern"]
                outer.patterns.append(pattern)
                outer.where.append({k: v for k, v in kwargs.items() if k != "filterPattern"})
                terms = [term.strip('?"') for term in pattern.split()]
                hits = [m for m in outer.messages if any(term in m for term in terms)]
                yield {"events": [{"message": message} for message in hits]}

        return _Paginator()


def test_fetch_finds_the_calls_then_reads_every_span_of_each() -> None:
    logs = _Logs(ALLOW + DENY + LIST + CREDIT)
    calls = trace.fetch_calls(logs, "get_tickets", minutes=60, limit=6)
    assert [c["decision"] for c in calls] == ["ALLOW", "DENY"]
    first, second = logs.patterns
    assert first == '"pellier-store-tools___get_tickets"'
    assert second == '?"req-allow" ?"req-deny"'


def test_fetch_keeps_the_newest_calls_and_reports_none_when_there_are_none() -> None:
    logs = _Logs(ALLOW + DENY)
    assert [c["request_id"] for c in trace.fetch_calls(logs, "get_tickets", 60, 1)] == [
        "req-deny"]
    assert trace.fetch_calls(_Logs(LIST), "get_tickets", 60, 6) == []


def test_the_default_limit_keeps_nadias_first_deny_in_a_busy_lab_4() -> None:
    # Eighteen credit calls in the hour (the first Execute, then retries while a deploy settles,
    # Execute again, the replay and reruns of the 4A check): the Wrap-up still finds the first.
    calls = [_call("req-first", 1_000, "give_store_credit", NADIA_SUB, "DENY",
                   ["workshop_credit_limit-xyz"], ran=False)]
    calls += [_call(f"req-{n}", 2_000 + n * 10, "give_store_credit", NADIA_SUB, "DENY",
                    ["workshop_credit_limit-xyz"], ran=False) for n in range(17)]
    logs = _Logs([span for call in calls for span in call])
    fetched = trace.fetch_calls(logs, "give_store_credit", 60, trace.CALL_LIMIT)
    assert len(fetched) == 18
    assert fetched[0]["request_id"] == "req-first"


def test_subject_names_maps_the_workshop_sign_ins() -> None:
    class _Cognito:
        def admin_get_user(self, UserPoolId: str, Username: str) -> Dict[str, Any]:  # noqa: N803
            if Username == "jessica":
                raise RuntimeError("UserNotFoundException")
            return {"UserAttributes": [{"Name": "sub", "Value": f"sub-{Username}"}]}

    names = trace.subject_names(_Cognito(), "us-east-1_pool")
    assert names["sub-theo"] == "theo" and names["sub-nadia"] == "nadia"
    assert "sub-jessica" not in names
    assert trace.subject_names(_Cognito(), None) == {}


def test_runtime_spans_are_read_only_for_calls_the_runtime_made() -> None:
    calls = trace.calls_from_spans(ALLOW + DENY, "get_tickets")
    logs = _Logs(RUNTIME)
    found = trace.runtime_spans(logs, "/aws/bedrock-agentcore/runtimes/r-1-DEFAULT", calls, 60)
    assert list(found) == ["trace-req-allow"]
    assert [s["name"] for s in found["trace-req-allow"]][0] == "invoke_agent support"
    assert logs.patterns == ['?"trace-req-allow"']
    assert logs.where[0]["logGroupName"] == "/aws/bedrock-agentcore/runtimes/r-1-DEFAULT"
    assert logs.where[0]["logStreamNames"] == ["spans"]


def test_an_unreadable_runtime_group_leaves_the_gateway_chain_standing() -> None:
    calls = trace.calls_from_spans(ALLOW, "get_tickets")

    class _Denied:
        def get_paginator(self, operation: str) -> Any:
            raise RuntimeError("AccessDeniedException")

    assert trace.runtime_spans(_Denied(), "/aws/x-DEFAULT", calls, 60) == {"trace-req-allow": None}
    assert trace.runtime_spans(_Logs([]), None, calls, 60) == {"trace-req-allow": None}
    assert trace.runtime_spans(_Logs([]), "/aws/x-DEFAULT",
                               trace.calls_from_spans(DENY, "get_tickets"), 60) == {}


# ---------------------------------------------------------------------------
# Aurora: pgAudit's record of writes to pellier.store_credits, under each credit call
# ---------------------------------------------------------------------------
# The line shape is Aurora's PostgreSQL log prefix, then pgAudit's CSV: AUDIT_TYPE,
# STATEMENT_ID, SUBSTATEMENT_ID, CLASS, COMMAND, OBJECT_TYPE, OBJECT_NAME, STATEMENT and,
# with pgaudit.log_parameter on, PARAMETER as one quoted CSV field. The READ line is the
# example in the Aurora User Guide's "Auditing database objects" page, wrapped as the page
# prints it; the ROLE line is AWS re:Post's (rds-postgresql-cleartext-logging), with the
# PARAMETER field a session line carries when it logs none.

DOCS_READ_LINE = ("2017-06-12 19:09:49 UTC:...:rds_test@postgres:[11701]:LOG: AUDIT:\n"
                  "OBJECT,1,1,READ,SELECT,TABLE,public.t1,select * from t1;")
DOCS_ROLE_LINE = ("2020-07-09 13:33:50 UTC:x.x.x.x(58670):grysa@pg:[26513]:LOG: AUDIT: "
                  "SESSION,3,1,ROLE,CREATE ROLE,,,CREATE ROLE test_role WITH LOGIN "
                  "PASSWORD <REDACTED>,<not logged>")
KEY = "operator-review:1:c281de75b2622180306edddcfdf76873"
INSERT_LINE = (
    "2026-10-29 15:42:10 UTC:10.0.12.34(51234):pellier_admin@pellier:[23456]:LOG:  AUDIT: "
    "OBJECT,7,3,WRITE,INSERT,TABLE,pellier.store_credits,"
    '"INSERT INTO pellier.store_credits\n'
    "               (approval_id, customer_id, amount_cents, reason, issued_by, idempotency_key)\n"
    "        VALUES (v_review.id, p_customer_id, p_amount_cents, v_reason,\n"
    "                nullif(btrim(coalesce(p_issued_by, '')), ''), v_key)\n"
    '        RETURNING credit_id",'
    '"1,CUST-JESSICA,10000,""Store credit for 2 returned items: Waffle Bath Robe, Sage '
    '(order 20); Reed Diffuser (order 21)."",04c8b408-nadia,' + KEY + '"')
INSERT_SECOND = 1793288530.0  # 2026-10-29 15:42:10 UTC


def _event(message: str, ms: int = 0) -> Dict[str, Any]:
    return {"message": message, "timestamp": ms}


def _credit(request: str, start_s: float, ran: bool = True,
            gateway_ms: int = 900) -> Dict[str, Any]:
    return {"request_id": request, "started_ns": int(start_s * 1e9), "gateway_ms": gateway_ms,
            "lambda_ms": 600 if ran else None}


def test_a_pgaudit_line_from_the_aurora_docs_parses_and_is_not_a_credit_write() -> None:
    line = trace.parse_audit_event(_event(DOCS_READ_LINE))
    assert line is not None and line["second"] == 1497294589.0
    assert (line["audit_type"], line["class"], line["command"], line["object"]) == (
        "OBJECT", "READ", "SELECT", "public.t1")
    assert line["key"] is None
    role = trace.parse_audit_event(_event(DOCS_ROLE_LINE))
    assert role is not None and (role["audit_type"], role["class"], role["object"]) == (
        "SESSION", "ROLE", "")
    assert role["key"] is None
    assert trace.audited_writes([_event(DOCS_READ_LINE), _event(DOCS_ROLE_LINE)]) == []
    assert trace.parse_audit_event(_event("2026-10-29 15:42:10 UTC:...:LOG:  checkpoint")) is None


def test_the_credit_insert_keeps_its_multiline_statement_and_names_its_key() -> None:
    (write,) = trace.audited_writes([_event(INSERT_LINE), _event(DOCS_READ_LINE)])
    assert write["second"] == INSERT_SECOND
    assert (write["class"], write["command"], write["object"]) == (
        "WRITE", "INSERT", "pellier.store_credits")
    assert write["statement"].startswith("INSERT INTO pellier.store_credits\n")
    assert write["statement"].endswith("RETURNING credit_id")
    # Only the shape apply_store_credit admits reads as the key; the reason's ": " does not.
    assert write["key"] == KEY


def test_without_logged_parameters_the_write_still_counts_but_names_no_key() -> None:
    bare = INSERT_LINE[:INSERT_LINE.rindex(',"1,CUST')]
    (write,) = trace.audited_writes([_event(bare + ",<none>"), _event(bare)])[:1]
    assert write["key"] is None and write["command"] == "INSERT"
    assert len(trace.audited_writes([_event(bare + ",<none>"), _event(bare)])) == 2


def test_deny_allow_and_replay_read_as_nothing_one_insert_and_nothing() -> None:
    deny = _credit("req-deny", INSERT_SECOND - 300, ran=False, gateway_ms=200)
    allow = _credit("req-allow", INSERT_SECOND - 0.4)
    replay = _credit("req-replay", INSERT_SECOND + 4)
    writes = trace.audited_writes([_event(INSERT_LINE)])
    lines = trace.aurora_lines([deny, allow, replay], writes, None, now=INSERT_SECOND + 600)
    when = datetime.fromtimestamp(INSERT_SECOND).strftime("%H:%M:%S")
    assert lines == {
        "req-deny": "pgAudit: no write to pellier.store_credits during this call",
        "req-allow": f"pgAudit: INSERT into pellier.store_credits at {when}, key {KEY}",
        "req-replay": "pgAudit: no write to pellier.store_credits during this call",
    }


def test_the_aurora_line_does_not_take_the_policy_decision_on_trust() -> None:
    # pgAudit is the database's own record: a write inside a DENY's window shows, so a DENY
    # that somehow reached the table could not hide behind its span.
    deny = _credit("req-deny", INSERT_SECOND - 0.2, ran=False)
    lines = trace.aurora_lines([deny], trace.audited_writes([_event(INSERT_LINE)]), None,
                               now=INSERT_SECOND + 600)
    assert lines["req-deny"].startswith("pgAudit: INSERT into pellier.store_credits at ")


def test_a_second_of_clock_skew_keeps_the_write_with_its_call() -> None:
    # The write's second is [S, S + 1): one call ends 0.6 s before it, one starts 0.8 s after.
    late = _credit("req-allow", INSERT_SECOND - 1.1, gateway_ms=500)
    early = _credit("req-allow", INSERT_SECOND + 1.8, gateway_ms=500)
    far = _credit("req-other", INSERT_SECOND + 2.5, gateway_ms=500)
    writes = trace.audited_writes([_event(INSERT_LINE)])
    for call in (late, early):
        line = trace.aurora_lines([call], writes, None, now=INSERT_SECOND + 600)["req-allow"]
        assert line.startswith("pgAudit: INSERT into"), line
    assert trace.aurora_lines([far], writes, None, now=INSERT_SECOND + 600)["req-other"] == (
        "pgAudit: no write to pellier.store_credits during this call")


def test_a_call_inside_the_export_lag_waits_instead_of_claiming_nothing_reached_aurora() -> None:
    deny = _credit("req-deny", 10_000, ran=False)
    lines = trace.aurora_lines([deny], [], None, now=10_030)
    assert lines["req-deny"] == ("pgAudit: not exported yet; the PostgreSQL log lags about a "
                                 "minute, so run this again shortly")
    assert "no write" not in lines["req-deny"]
    later = trace.aurora_lines([deny], [], None, now=10_000 + trace.LOG_EXPORT_LAG_S + 5)
    assert later["req-deny"] == "pgAudit: no write to pellier.store_credits during this call"


def test_a_write_in_the_second_two_calls_share_goes_to_the_earlier_and_says_so() -> None:
    first = _credit("req-1", INSERT_SECOND + 0.1, ran=True, gateway_ms=300)
    second = _credit("req-2", INSERT_SECOND + 0.6, ran=True, gateway_ms=300)
    writes = trace.audited_writes([_event(INSERT_LINE)])
    lines = trace.aurora_lines([first, second], writes, None, now=INSERT_SECOND + 600)
    assert lines["req-1"].endswith("(the next call began in the same second)")
    assert lines["req-2"] == "pgAudit: no write to pellier.store_credits during this call"


def test_with_pgaudit_off_every_call_says_why_and_claims_no_absence() -> None:
    assert trace.pgaudit_off_reason({"extension": False}) == (
        "the pgaudit extension is not installed (the library did not load)")
    assert trace.pgaudit_off_reason({"extension": True, "audit_role": None}) == (
        "pgaudit.role is unset, not rds_pgaudit")
    assert trace.pgaudit_off_reason({"extension": True, "audit_role": "rds_pgaudit",
                                     "granted": False}) == (
        "rds_pgaudit holds no INSERT and UPDATE on pellier.store_credits")
    assert trace.pgaudit_off_reason({"extension": True, "audit_role": "rds_pgaudit",
                                     "granted": True}) is None


def test_the_aurora_line_sits_under_the_gateway_line_only_when_given() -> None:
    (credit,) = trace.calls_from_spans(CREDIT, "give_store_credit")
    plain = trace.render_call(credit, NAMES)
    with_db = trace.render_call(credit, NAMES, aurora="pgAudit: no write to x")
    assert len(plain) == 6 and len(with_db) == 7
    assert with_db[4].startswith("  Gateway") and with_db[5] == "  Aurora    pgAudit: no write to x"
    assert with_db[6] == plain[5]


class _Cursor:
    def __init__(self, status: Dict[str, Any]) -> None:
        self.status = status

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str) -> _Cursor:
        assert "pg_extension" in sql and "has_table_privilege" in sql
        return self

    def fetchone(self) -> Dict[str, Any]:
        return self.status


class _Conn(_Cursor):
    def cursor(self) -> _Cursor:
        return _Cursor(self.status)


class _AuditLogs:
    def __init__(self, events: List[Dict[str, Any]], error: str = "") -> None:
        self.events, self.error, self.asked = events, error, {}

    def get_paginator(self, name: str) -> _AuditLogs:
        assert name == "filter_log_events"
        return self

    def paginate(self, **kw: Any) -> List[Dict[str, Any]]:
        self.asked = kw
        if self.error:
            raise _ClientError(self.error)
        return [{"events": self.events}]


class _ClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


ON = {"extension": True, "audit_role": "rds_pgaudit", "granted": True}
ARN = "arn:aws:rds:us-west-2:123456789012:cluster:pellier-db-cluster"


def _db(monkeypatch: Any, status: Dict[str, Any], arn: str = ARN) -> None:
    check = importlib.import_module("workshop_check")
    monkeypatch.setattr(check, "db_config", lambda: {"host": "h"})
    monkeypatch.setattr(check, "connect", lambda cfg: _Conn(status))
    monkeypatch.setenv("DB_CLUSTER_ARN", arn)


def test_read_aurora_reads_the_clusters_postgresql_group_for_credit_writes(monkeypatch) -> None:
    _db(monkeypatch, ON)
    logs = _AuditLogs([_event(DOCS_READ_LINE), _event(INSERT_LINE)])
    writes, unavailable = trace.read_aurora(logs, 60)
    assert unavailable is None and [w["key"] for w in writes] == [KEY]
    assert logs.asked["logGroupName"] == "/aws/rds/cluster/pellier-db-cluster/postgresql"
    assert logs.asked["filterPattern"] == '"AUDIT:" "pellier.store_credits"'


def test_read_aurora_says_off_plainly_and_never_reads_the_log(monkeypatch) -> None:
    _db(monkeypatch, {"extension": False})
    logs = _AuditLogs([_event(INSERT_LINE)])
    writes, unavailable = trace.read_aurora(logs, 60)
    assert writes == [] and logs.asked == {}
    assert unavailable == ("pgAudit is off on this cluster: the pgaudit extension is not "
                           "installed (the library did not load)")


def test_read_aurora_tells_an_unreadable_log_from_an_empty_one(monkeypatch) -> None:
    _db(monkeypatch, ON)
    assert trace.read_aurora(_AuditLogs([], "ResourceNotFoundException"), 60) == ([], None)
    _, unavailable = trace.read_aurora(_AuditLogs([], "AccessDeniedException"), 60)
    assert unavailable == ("pgAudit is on, but /aws/rds/cluster/pellier-db-cluster/postgresql "
                           "could not be read: AccessDeniedException")
    _db(monkeypatch, ON, arn="")
    assert trace.read_aurora(_AuditLogs([]), 60)[1] == (
        "pgAudit is on, but DB_CLUSTER_ARN is not set, so its log group has no name")


def test_an_audit_line_cut_after_its_first_line_still_counts_the_write() -> None:
    first_line = INSERT_LINE.split("\n", 1)[0]
    (write,) = trace.audited_writes([_event(first_line)])
    assert write["command"] == "INSERT" and write["key"] is None
