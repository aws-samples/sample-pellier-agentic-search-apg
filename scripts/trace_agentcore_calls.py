#!/usr/bin/env python3
"""Read AgentCore's own spans for recent Gateway calls to one tool.

AgentCore writes a span for each managed step of a Gateway call to the
CloudWatch log group ``aws/spans`` (Transaction Search), and the Runtime writes
its agent's spans to its own log group under the same trace id. This script
reads both, and never writes, so each call reads as one chain:

    Runtime    the agent and turn that made the call, or none for a direct call
    Identity   the Gateway checked the caller's Cognito access token
    Policy     Cedar's decision, and the policy that determined it
    Gateway    the call, and whether the Lambda target ran

A call made by the Runtime has the Runtime's MCP span as its parent. An ALLOW
has a Lambda invocation span. A DENY has none, because the Gateway never
called the Lambda:

    python3 scripts/trace_agentcore_calls.py --tool get_tickets
    python3 scripts/trace_agentcore_calls.py --tool give_store_credit

Spans reach CloudWatch about ten seconds after a call.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pellier" / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))

LOG_GROUP = "aws/spans"
RUNTIME_STREAM = "spans"
TARGET = "pellier-store-tools"
# The workshop sign-ins, so a token subject prints as a name.
WORKSHOP_USERS = ("anna", "marco", "theo", "jessica", "nadia")
_NAME = {
    "invoke": "AgentCore.Gateway.InvokeTool",
    "inbound": "AgentCore.Gateway.InboundAuth",
    "identity": "AgentCore.Identity.Authorize",
    "policy": "AgentCore.Policy.AuthorizeAction",
    "target": "AgentCore.Gateway.TargetInvocation",
}
_DECISION = "aws.agentcore.policy.authorization_decision"


def _attrs(span: Dict[str, Any]) -> Dict[str, Any]:
    return span.get("attributes") or {}


def _named(spans: Iterable[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    return [span for span in spans if span.get("name") == _NAME[key]]


def _policies(spans: List[Dict[str, Any]]) -> List[str]:
    """The determining policies, once each, in the order the service named them."""
    seen: List[str] = []
    for span in _named(spans, "policy"):
        for policy in _attrs(span).get("aws.agentcore.policy.determining_policies") or []:
            if policy not in seen:
                seen.append(str(policy))
    return seen


def one_call(spans: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One Gateway ``tools/call`` from the spans sharing its request id."""
    invoke = next((s for s in _named(spans, "invoke")
                   if _attrs(s).get("url.path") == "tools/call"), None)
    if invoke is None:
        return None
    attrs = _attrs(invoke)
    inbound = next(iter(_named(spans, "inbound")), {})
    policy = next(iter(_named(spans, "policy")), {})
    target = next(iter(_named(spans, "target")), None)
    return {
        "request_id": attrs.get("aws.request.id"),
        "trace_id": invoke.get("traceId"),
        "parent_span_id": invoke.get("parentSpanId") or None,
        "started_ns": int(invoke.get("startTimeUnixNano") or 0),
        "tool": str(attrs.get("tool.name") or "").split("___")[-1],
        "decision": attrs.get(_DECISION) or _attrs(policy).get(_DECISION) or "none",
        "policies": _policies(spans),
        "reason": _attrs(policy).get("aws.agentcore.policy.authorization_reason"),
        "subject": _attrs(inbound).get("jwt.sub"),
        "token_use": _attrs(inbound).get("jwt.token_use"),
        "authorizer": _attrs(inbound).get("auth.inbound.authorizer_type"),
        "identity_checked": bool(_named(spans, "identity")),
        "gateway_ms": attrs.get("latency_ms"),
        "lambda_ms": (int(target["durationNano"]) // 1_000_000) if target else None,
    }


def calls_from_spans(spans: Iterable[Dict[str, Any]], tool: str) -> List[Dict[str, Any]]:
    """Every ``tools/call`` to ``tool`` in ``spans``, oldest first."""
    by_request: Dict[str, List[Dict[str, Any]]] = {}
    for span in spans:
        request_id = _attrs(span).get("aws.request.id")
        if request_id:
            by_request.setdefault(str(request_id), []).append(span)
    calls = [one_call(group) for group in by_request.values()]
    mine = [call for call in calls if call and call["tool"] == tool]
    return sorted(mine, key=lambda call: call["started_ns"])


def runtime_summary(call: Dict[str, Any], runtime: Optional[List[Dict[str, Any]]]) -> str:
    """Who made the call: the Runtime's agent and turn, or nothing above the Gateway.

    ``runtime`` is the Runtime spans sharing the call's trace id, or ``None``
    when the Runtime's log group could not be read.
    """
    if not call["parent_span_id"]:
        return "none: this call came to the Gateway directly, not through the Runtime"
    agent = next((s for s in runtime or [] if str(s.get("name", "")).startswith("invoke_agent ")),
                 None)
    if agent is None:
        unread = "not readable" if runtime is None else "not in CloudWatch yet"
        return f"called by the Runtime (parent span {call['parent_span_id']}); its spans are {unread}"
    attrs = _attrs(agent)
    name = str(attrs.get("gen_ai.agent.name") or "").capitalize() or "An"
    return (f"{name} agent on {attrs.get('gen_ai.request.model')}, "
            f"turn {attrs.get('turn.id')}, made this call")


def render_call(call: Dict[str, Any], names: Dict[str, str],
                runtime: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """Five lines for one call: when and who, then Runtime, Identity, Policy and Gateway."""
    when = datetime.fromtimestamp(call["started_ns"] / 1e9).strftime("%H:%M:%S")
    subject = call["subject"] or ""
    who = names.get(subject) or (f"sub {subject[:8]}..." if subject else "no token")
    ran = call["lambda_ms"] is not None
    outcome = f"Lambda ran ({call['lambda_ms']} ms)" if ran else "Lambda never called"
    identity = (f"{call['authorizer']} authorizer accepted {who}'s Cognito "
                f"{call['token_use']} token") if call["identity_checked"] else "no Identity span"
    if call["policies"]:
        policy = f"{call['decision']}, determined by {', '.join(call['policies'])}"
    else:
        policy = f"{call['decision']}: {call['reason'] or 'no policy named'}"
    gateway = (f"tools/call {call['gateway_ms']} ms; {TARGET} Lambda span present" if ran
               else "tools/call refused; no Lambda span: the target was never invoked")
    return [f"{when}  {who:<8} {call['tool']}  {call['decision']}  ->  {outcome}",
            f"  Runtime   {runtime_summary(call, runtime)}",
            f"  Identity  {identity}",
            f"  Policy    {policy}",
            f"  Gateway   {gateway}",
            f"  trace {call['trace_id']}  request {call['request_id']}"]


def _filter(logs: Any, start_ms: int, pattern: str, group: str = LOG_GROUP,
            **where: Any) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    for page in logs.get_paginator("filter_log_events").paginate(
        logGroupName=group, startTime=start_ms, filterPattern=pattern, **where,
    ):
        for event in page.get("events", []):
            try:
                spans.append(json.loads(event["message"]))
            except (KeyError, ValueError):
                continue
    return spans


def fetch_calls(logs: Any, tool: str, minutes: int, limit: int) -> List[Dict[str, Any]]:
    """The newest ``limit`` calls to ``tool``: find their requests, then read every span."""
    start_ms = int((time.time() - minutes * 60) * 1000)
    action = f"{TARGET}___{tool}"
    # A tool list names every tool it allowed, so keep only the calls themselves.
    tagged = [span for span in _filter(logs, start_ms, f'"{action}"')
              if _attrs(span).get("tool.name") == action]
    requests = []
    for span in sorted(tagged, key=lambda s: int(s.get("startTimeUnixNano") or 0)):
        request_id = _attrs(span).get("aws.request.id")
        if request_id and request_id not in requests:
            requests.append(request_id)
    requests = requests[-limit:]
    if not requests:
        return []
    spans = _filter(logs, start_ms, " ".join(f'?"{r}"' for r in requests))
    return calls_from_spans(spans, tool)


def runtime_spans(logs: Any, group: Optional[str], calls: List[Dict[str, Any]],
                  minutes: int) -> Dict[str, Optional[List[Dict[str, Any]]]]:
    """The Runtime's spans for each call it made, by trace id.

    A trace id maps to ``None`` when the Runtime's log group cannot be read.
    """
    traces = sorted({c["trace_id"] for c in calls if c["parent_span_id"] and c["trace_id"]})
    if not traces:
        return {}
    start_ms = int((time.time() - minutes * 60) * 1000)
    try:
        if not group:
            raise ValueError("no Runtime configured")
        spans = _filter(logs, start_ms, " ".join(f'?"{t}"' for t in traces), group,
                        logStreamNames=[RUNTIME_STREAM])
    except Exception:  # noqa: BLE001 - the Gateway chain still prints; this line says why not
        return {trace: None for trace in traces}
    found: Dict[str, Optional[List[Dict[str, Any]]]] = {trace: [] for trace in traces}
    for span in spans:
        if span.get("traceId") in found:
            found[span["traceId"]].append(span)
    return found


def subject_names(cognito: Any, pool_id: Optional[str]) -> Dict[str, str]:
    """The workshop sign-ins by Cognito subject; empty when the pool cannot be read."""
    names: Dict[str, str] = {}
    if not pool_id:
        return names
    for username in WORKSHOP_USERS:
        try:
            user = cognito.admin_get_user(UserPoolId=pool_id, Username=username)
        except Exception:  # noqa: BLE001 - a missing user prints as its subject
            continue
        sub = next((a["Value"] for a in user.get("UserAttributes", []) if a["Name"] == "sub"), "")
        if sub:
            names[sub] = username
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tool", required=True, help="a store tool, for example get_tickets")
    parser.add_argument("--minutes", type=int, default=60, help="how far back to read")
    parser.add_argument("--limit", type=int, default=6, help="the newest calls to show")
    args = parser.parse_args()

    import boto3
    from gateway_client import _load_env
    from runtime_log_delivery import runtime_log_group

    _load_env()
    from config import settings

    region = settings.aws_region_resolved
    logs = boto3.client("logs", region_name=region)
    try:
        calls = fetch_calls(logs, args.tool, args.minutes, args.limit)
    except Exception as exc:  # noqa: BLE001 - report the AWS error code, not the request
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
        print(f"Could not read {LOG_GROUP}: {code}", file=sys.stderr)
        return 1
    print(f"AgentCore spans for {args.tool}, last {args.minutes} minutes ({LOG_GROUP})")
    if not calls:
        print(f"No {args.tool} call yet. Spans arrive about ten seconds after a call; "
              "run this again in a moment.")
        return 1
    names = subject_names(boto3.client("cognito-idp", region_name=settings.cognito_region_resolved),
                          settings.cognito_pool_id_resolved)
    try:
        group: Optional[str] = runtime_log_group(settings.AGENTCORE_RUNTIME_ENDPOINT or "")
    except ValueError:
        group = None
    runtime = runtime_spans(logs, group, calls, args.minutes)
    for call in calls:
        print()
        print("\n".join(render_call(call, names, runtime.get(call["trace_id"]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
