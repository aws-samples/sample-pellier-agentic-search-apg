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
    Aurora     give_store_credit only: what pgAudit logged reaching pellier.store_credits

The Aurora line is database evidence, not AgentCore's: pgAudit's object audit writes one line
to the cluster's PostgreSQL log for each INSERT or UPDATE of pellier.store_credits, whoever
runs it (scripts/migrations/001_schema.sql grants rds_pgaudit those two privileges). A line is
matched to the call whose Gateway window holds its second; the log line's own time has
one-second precision. A DENY never reaches the table, an allowed call that writes leaves one
INSERT, and a retry with the same key leaves none.

A call made by the Runtime has the Runtime's MCP span as its parent. An ALLOW
has a Lambda invocation span. A DENY has none, because the Gateway never
called the Lambda:

    uv run scripts/trace_agentcore_calls.py --tool get_tickets
    uv run scripts/trace_agentcore_calls.py --tool give_store_credit

Spans reach CloudWatch about ten seconds after a call; the PostgreSQL log, about a minute
after the statement.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pellier" / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))

LOG_GROUP = "aws/spans"
# The Wrap-up names Nadia's first DENY, the oldest of her credit calls in the hour. Extra Execute
# again clicks, 4A check reruns and finish's 30 s retries can add a dozen more, so read enough.
CALL_LIMIT = 20
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

# pgAudit, for the one tool that writes money.
AUDITED_TOOL = "give_store_credit"
AUDITED_TABLE = "pellier.store_credits"
# The exported PostgreSQL log arrives about a minute after a statement (as observability_check
# says); a call newer than this has no absence to claim yet.
LOG_EXPORT_LAG_S = 90
# Aurora's log clock and AgentCore's span clock are separate hosts; a second of slack each side
# keeps a write inside its call when they differ by less than that.
CLOCK_SLACK_S = 1.0
_LINE_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC:")
_AUDIT = re.compile(r"AUDIT:\s+")
# The one key shape apply_store_credit admits (store_tools.execution_idempotency_key).
_CREDIT_KEY = re.compile(r"operator-review:\d+:[0-9a-f]{32}")
PGAUDIT_STATUS_SQL = """
SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgaudit') AS extension,
       current_setting('pgaudit.role', true) AS audit_role,
       CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rds_pgaudit')
            THEN has_table_privilege('rds_pgaudit', 'pellier.store_credits', 'INSERT')
             AND has_table_privilege('rds_pgaudit', 'pellier.store_credits', 'UPDATE')
            ELSE false END AS granted
"""


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
        return (f"called by the Runtime (parent span {call['parent_span_id']}); "
                f"its spans are {unread}")
    attrs = _attrs(agent)
    name = str(attrs.get("gen_ai.agent.name") or "").capitalize() or "An"
    # agentcore invoke and the deploy's smoke test call the Runtime outside a Pellier turn.
    turn = attrs.get("turn.id")
    where = f"turn {turn}" if turn else "invoked directly with no Pellier turn"
    return f"{name} agent on {attrs.get('gen_ai.request.model')}, {where}, made this call"


def render_call(call: Dict[str, Any], names: Dict[str, str],
                runtime: Optional[List[Dict[str, Any]]] = None,
                aurora: Optional[str] = None) -> List[str]:
    """Five lines for one call: when and who, then Runtime, Identity, Policy and Gateway.

    ``aurora``, when given, adds one more under Gateway: what pgAudit saw reach Aurora.
    """
    when = datetime.fromtimestamp(call["started_ns"] / 1e9, tz=timezone.utc).strftime("%H:%M:%S")
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
            *([f"  Aurora    {aurora}"] if aurora is not None else []),
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


def parse_audit_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One pgAudit line from the exported PostgreSQL log, or ``None`` for any other line.

    The line is ``<UTC time>:<host>:<user>@<db>:[<pid>]:LOG:  AUDIT: `` and then the CSV
    AUDIT_TYPE, STATEMENT_ID, SUBSTATEMENT_ID, CLASS, COMMAND, OBJECT_TYPE, OBJECT_NAME,
    STATEMENT and, with pgaudit.log_parameter on, PARAMETER (itself CSV, or ``<none>``).
    """
    message = str(event.get("message") or "")
    audit = _AUDIT.search(message)
    if audit is None:
        return None
    try:
        fields = next(csv.reader(io.StringIO(message[audit.end():].strip())))
    except (StopIteration, csv.Error):
        return None
    if len(fields) < 8:
        return None
    stamp = _LINE_TIME.match(message)
    if stamp:
        second = datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp()
    else:
        second = int(event.get("timestamp") or 0) // 1000
    params: List[str] = []
    if len(fields) > 8 and fields[8] not in ("", "<none>", "<not logged>"):
        params = next(csv.reader(io.StringIO(fields[8])), [])
    key = next((param for param in params if _CREDIT_KEY.fullmatch(param)), None)
    return {"second": float(second), "audit_type": fields[0], "class": fields[3],
            "command": fields[4], "object": fields[6], "statement": fields[7], "key": key}


def audited_writes(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The pgAudit WRITE lines on the credits table, oldest first."""
    lines = (parse_audit_event(event) for event in events)
    writes = [line for line in lines if line and line["class"] == "WRITE"
              and line["object"] == AUDITED_TABLE]
    return sorted(writes, key=lambda line: line["second"])


def pgaudit_off_reason(status: Dict[str, Any]) -> Optional[str]:
    """Why pgAudit cannot vouch for the credits table, or ``None`` when it can."""
    if not status.get("extension"):
        return "the pgaudit extension is not installed (the library did not load)"
    if status.get("audit_role") != "rds_pgaudit":
        return f"pgaudit.role is {status.get('audit_role') or 'unset'}, not rds_pgaudit"
    if not status.get("granted"):
        return f"rds_pgaudit holds no INSERT and UPDATE on {AUDITED_TABLE}"
    return None


def _window(call: Dict[str, Any]) -> Tuple[float, float]:
    start = call["started_ns"] / 1e9
    end = start + float(call.get("gateway_ms") or 0) / 1000
    return start - CLOCK_SLACK_S, end + CLOCK_SLACK_S


def aurora_lines(calls: List[Dict[str, Any]], writes: List[Dict[str, Any]],
                 unavailable: Optional[str], now: float) -> Dict[str, str]:
    """The Aurora line for each call, by request id.

    A write belongs to the earliest call whose Gateway window, with CLOCK_SLACK_S each side,
    overlaps the write's second.
    A call with no write says so only once the PostgreSQL log has had time to arrive.
    ``unavailable``, when set, is every call's line: why there is no record to read.
    """
    if unavailable:
        return {call["request_id"]: unavailable for call in calls}
    owned: Dict[str, List[Dict[str, Any]]] = {call["request_id"]: [] for call in calls}
    shared: Dict[str, bool] = {}
    for write in writes:
        second = write["second"]
        hits = [c for c in calls if _window(c)[0] < second + 1 and second <= _window(c)[1]]
        if hits:
            first = hits[0]["request_id"]
            owned[first].append(write)
            shared[first] = shared.get(first, False) or len(hits) > 1
    lines: Dict[str, str] = {}
    for call in calls:
        mine = owned[call["request_id"]]
        if mine:
            parts = []
            for write in mine:
                when = datetime.fromtimestamp(write["second"], tz=timezone.utc).strftime("%H:%M:%S")
                key = f", key {write['key']}" if write["key"] else ""
                parts.append(f"{write['command']} into {AUDITED_TABLE} at {when}{key}")
            note = " (the next call began in the same second)" if shared[call["request_id"]] else ""
            lines[call["request_id"]] = "pgAudit: " + "; ".join(parts) + note
        elif now - _window(call)[1] < LOG_EXPORT_LAG_S:
            lines[call["request_id"]] = ("pgAudit: not exported yet; the PostgreSQL log lags "
                                         "about a minute, so run this again shortly")
        else:
            lines[call["request_id"]] = f"pgAudit: no write to {AUDITED_TABLE} during this call"
    return lines


def read_aurora(logs: Any, minutes: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """pgAudit's status and its credit-table writes, read without writing: (writes, why not).

    ``why not`` is ``None`` when the log was read; otherwise it is the Aurora line to print.
    """
    import workshop_check as check
    from observability_check import aws_code, cluster_id

    cfg = check.db_config()
    if cfg is None:
        return [], f"pgAudit not checked: {check.missing_settings_reason()}"
    try:
        with check.connect(cfg) as conn, conn.cursor() as cur:
            status = cur.execute(PGAUDIT_STATUS_SQL).fetchone() or {}
    except Exception as exc:  # noqa: BLE001 - the line names the failure instead of guessing
        return [], f"pgAudit not checked: the database could not be read ({type(exc).__name__})"
    reason = pgaudit_off_reason(status)
    if reason:
        return [], f"pgAudit is off on this cluster: {reason}"
    cluster = cluster_id(os.environ.get("DB_CLUSTER_ARN", ""))
    if not cluster:
        return [], "pgAudit is on, but DB_CLUSTER_ARN is not set, so its log group has no name"
    group = f"/aws/rds/cluster/{cluster}/postgresql"
    start_ms = int((time.time() - minutes * 60) * 1000)
    events: List[Dict[str, Any]] = []
    try:
        for page in logs.get_paginator("filter_log_events").paginate(
                logGroupName=group, startTime=start_ms,
                filterPattern=f'"AUDIT:" "{AUDITED_TABLE}"'):
            events.extend(page.get("events", []))
    except Exception as exc:  # noqa: BLE001 - the group appears with its first exported line
        if aws_code(exc) != "ResourceNotFoundException":
            return [], f"pgAudit is on, but {group} could not be read: {aws_code(exc)}"
    return audited_writes(events), None


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
    parser.add_argument("--limit", type=int, default=CALL_LIMIT, help="the newest calls to show")
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
    aurora: Dict[str, str] = {}
    if args.tool == AUDITED_TOOL:
        writes, unavailable = read_aurora(logs, args.minutes)
        aurora = aurora_lines(calls, writes, unavailable, time.time())
    for call in calls:
        print()
        print("\n".join(render_call(call, names, runtime.get(call["trace_id"]),
                                     aurora.get(call["request_id"]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
