"""The terminal trace of a Gateway call, read from AgentCore's spans in ``aws/spans``.

The spans here keep the names and attributes the live service writes. An ALLOW
call has a Lambda invocation span; a DENY call has none, and the trace says the
target was never invoked rather than inferring it from the decision.
"""

from __future__ import annotations

import importlib
import json
import sys
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
        "gen_ai.agent.name": "support", "gen_ai.request.model": "global.anthropic.claude-opus-5",
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
        "  Runtime   Support agent on global.anthropic.claude-opus-5, turn turn-abc, "
        "made this call")
    assert trace.runtime_summary(deny, None) == (
        "none: this call came to the Gateway directly, not through the Runtime")
    assert trace.runtime_summary(allow, []).endswith("its spans are not in CloudWatch yet")
    assert trace.runtime_summary(allow, None).endswith("its spans are not readable")


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
