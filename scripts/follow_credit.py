#!/usr/bin/env python3
"""Follow Jessica's store credit end to end, through every system that recorded a step of it.

No single record tells the whole story, so this joins four of them:

    ADOT span       CloudWatch: the agent on AgentCore Runtime that asked, its model and turn
    AgentCore span  CloudWatch: who the Gateway accepted, what Cedar decided, whether the
                    Lambda ran
    Aurora          Pellier's rows: the request, the review, the approval, each tool run and
                    the credit
    pgAudit         the PostgreSQL log: the INSERT that reached pellier.store_credits

Three values join them. Jessica's turn ID is on her agent's span, on the ask_a_person audit row
and on her request. The Gateway request id on that audit row is the id of the Gateway call
that opened her request, so the check follows that one call and no other call in her turn.
The review's key is on Nadia's give_store_credit audit row, on the pgAudit line and on the
credit. The script starts from Jessica's newest credit in Aurora, reads
CloudWatch from just before her request, and never writes:

    uv run scripts/follow_credit.py

Spans reach CloudWatch about ten seconds after a call; the PostgreSQL log, about a minute after
the statement. Until both have arrived the script says it could not check yet.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_agentcore_calls as trace  # noqa: E402  (sibling module)
import workshop_check as check  # noqa: E402  (sibling module)
from wait_progress import waiting  # noqa: E402  (sibling module)

CUSTOMER = "CUST-JESSICA"
HANDOFF_TOOL = "ask_a_person"
CREDIT_TOOL = trace.AUDITED_TOOL
# CloudWatch is read from this long before her request, so no time window is guessed.
LEAD_S = 120
TITLE = "Jessica's store credit, end to end: CloudWatch spans, Aurora rows and pgAudit"
HEADER = ("When (UTC)", "Step", "What the record says", "Recorded in")
CONTRADICTION = ("Aurora and the Gateway's record of her handoff disagree. Raise your hand so a "
                 "facilitator can check it.")

# The same joins as workshop/wrap-up-reconstruct.sql: from her newest credit back to the
# review that keyed it and the request from her chat that the review answered. The handoff
# row is the one whose result names that request, so a second ask_a_person row in her turn
# cannot stand in for it.
STORY_SQL = """
WITH credit AS (
    SELECT * FROM pellier.store_credits WHERE customer_id = %(customer)s
     ORDER BY credit_id DESC LIMIT 1
), review AS (
    SELECT a.*, 'operator-review:' || a.id || ':' || left(a.action_hash, 32) AS write_key
      FROM pellier.approvals a JOIN credit c ON c.approval_id = a.id
     WHERE a.tool = 'give_store_credit'
), request AS (
    SELECT q.* FROM pellier.approvals q JOIN review r ON q.answered_by_review_id = r.id
     WHERE q.tool = 'store_credit_request'
     ORDER BY q.id LIMIT 1
)
SELECT c.credit_id, c.amount_cents, c.idempotency_key, c.created_at AS credited_at,
       r.id AS review_id, r.write_key, r.order_ids, r.requested_at AS proposed_at,
       (r.args->>'amount_cents')::int AS proposed_cents,
       coalesce(r.decided_by_name, 'A person') AS approver, r.decided_at,
       q.id AS request_id, q.source_turn_id AS turn_id, q.requested_at,
       (SELECT t.audit_id FROM pellier.tool_audit t
         WHERE t.tool = 'ask_a_person' AND t.session_id = q.source_turn_id
           AND t.result->>'request_id' = q.id::text
         ORDER BY t.audit_id LIMIT 1) AS handoff_audit_id,
       (SELECT t.args->>'gateway_request_id' FROM pellier.tool_audit t
         WHERE t.tool = 'ask_a_person' AND t.session_id = q.source_turn_id
           AND t.result->>'request_id' = q.id::text
         ORDER BY t.audit_id LIMIT 1) AS handoff_gateway_request_id,
       (SELECT t.audit_id FROM pellier.tool_audit t
         WHERE t.tool = 'give_store_credit' AND t.args->>'idempotency_key' = r.write_key
           AND t.result->>'status' = 'success'
           AND coalesce(t.result->>'idempotent_replay', 'false') <> 'true'
         ORDER BY t.audit_id LIMIT 1) AS credit_audit_id,
       (SELECT count(*) FROM pellier.store_credits s
         WHERE s.idempotency_key = r.write_key) AS credits_with_key,
       (SELECT t.args->>'gateway_request_id' FROM pellier.tool_audit t
         WHERE t.tool = 'give_store_credit' AND t.args->>'idempotency_key' = r.write_key
           AND t.result->>'status' = 'success'
           AND coalesce(t.result->>'idempotent_replay', 'false') <> 'true'
         ORDER BY t.audit_id LIMIT 1) AS credit_gateway_request_id
  FROM credit c
  LEFT JOIN review r ON true
  LEFT JOIN request q ON true;
"""

# Each Aurora link the chain needs, and what its absence means.
AURORA_LINKS = (
    ("review_id", "her credit names no give_store_credit review"),
    ("request_id", "no request from her chat was answered by that review"),
    ("turn_id", "her request records no turn"),
    ("handoff_audit_id", "no ask_a_person audit row in her turn opened her request"),
    ("credit_audit_id", "no give_store_credit audit row applied the review's key"),
)


@dataclass
class Followed:
    """The chain as far as its records reach, and the state of the whole."""

    state: str
    rows: List[List[str]] = field(default_factory=list)
    observed: str = ""
    next_step: str = ""
    joins: List[str] = field(default_factory=list)


def _clock(moment: Any) -> str:
    if isinstance(moment, datetime):
        return moment.astimezone(timezone.utc).strftime("%H:%M:%S")
    if isinstance(moment, (int, float)) and moment:
        return datetime.fromtimestamp(moment, tz=timezone.utc).strftime("%H:%M:%S")
    return ""


def _span_clock(call: Dict[str, Any]) -> str:
    return _clock(call["started_ns"] / 1e9)


def _dollars(cents: Any) -> str:
    return f"${int(cents or 0) / 100:,.2f}"


def agent_span(runtime: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """The ADOT span the Runtime's agent wrote for its turn, if CloudWatch has it."""
    return next((span for span in runtime or []
                 if str(span.get("name", "")).startswith("invoke_agent ")), None)


def handoff_call(calls: List[Dict[str, Any]], request_id: str) -> Optional[Dict[str, Any]]:
    """The ask_a_person call with this Gateway request id, never the newest one in her turn."""
    matches = [call for call in calls if call.get("request_id") == request_id]
    return matches[0] if matches else None


def paid_call(calls: List[Dict[str, Any]], writes: List[Dict[str, Any]],
              key: str, request_id: Optional[str] = None,
              ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Join the committed receipt's Gateway request id, never a time-window guess."""
    inserts = [w for w in writes if w["key"] == key and w["command"] == "INSERT"]
    if not inserts:
        return inserts, None
    matches = [call for call in calls if request_id and call.get("request_id") == request_id
               and call.get("tool") == CREDIT_TOOL and call.get("decision") == "ALLOW"
               and call.get("lambda_ms") is not None]
    holder = matches[0] if len(matches) == 1 else None
    return inserts, holder


def _identity(call: Dict[str, Any], names: Dict[str, str]) -> str:
    subject = call["subject"] or ""
    who = names.get(subject) or (f"sub {subject[:8]}..." if subject else "no one")
    return f"The Gateway accepted {who}'s Cognito {call['token_use']} token"


def _policy(call: Dict[str, Any]) -> str:
    if call["policies"]:
        return f"{call['decision']}, determined by {', '.join(call['policies'])}"
    return f"{call['decision']}: {call['reason'] or 'no policy named'}"


def handoff_rows(story: Dict[str, Any], call: Dict[str, Any], span: Dict[str, Any],
                 names: Dict[str, str]) -> List[List[str]]:
    """Her turn: the agent that asked, the Gateway's checks, and the request it opened."""
    attrs = trace._attrs(span)
    agent = str(attrs.get("gen_ai.agent.name") or "").capitalize() or "An"
    when = _span_clock(call)
    return [
        [when, "Agent", f"{agent} agent on {attrs.get('gen_ai.request.model')} called "
         f"{HANDOFF_TOOL} in turn {check.short(story['turn_id'], 18)}",
         "CloudWatch: ADOT span"],
        [when, "Identity", _identity(call, names), "CloudWatch: AgentCore span"],
        [when, "Policy", _policy(call), "CloudWatch: AgentCore span"],
        [_clock(story["requested_at"]), "Request",
         f"{HANDOFF_TOOL} ran and opened request {story['request_id']} for the same turn",
         f"Aurora: tool_audit {story['handoff_audit_id']}, approvals {story['request_id']}"],
    ]


def decision_rows(story: Dict[str, Any]) -> List[List[str]]:
    """The review the Advisor proposed and the person who approved it, both from Aurora."""
    orders = ", ".join(str(order) for order in story.get("order_ids") or []) or "none"
    review = f"Aurora: approvals {story['review_id']}"
    return [
        [_clock(story["proposed_at"]), "Review",
         f"The Advisor proposed {_dollars(story['proposed_cents'])} for orders {orders}", review],
        [_clock(story["decided_at"]), "Approval",
         f"{story['approver']} approved review {story['review_id']}", review],
    ]


def credit_rows(story: Dict[str, Any], call: Dict[str, Any], insert: Dict[str, Any],
                names: Dict[str, str]) -> List[List[str]]:
    """Nadia's Execute through the Gateway, the INSERT pgAudit saw, and the credit row."""
    when = _span_clock(call)
    return [
        [when, "Identity", _identity(call, names), "CloudWatch: AgentCore span"],
        [when, "Policy", _policy(call), "CloudWatch: AgentCore span"],
        [when, "Tool", f"{CREDIT_TOOL} ran in the Lambda with the review's key",
         f"Aurora: tool_audit {story['credit_audit_id']}"],
        [_clock(insert["second"]), "Database",
         f"INSERT into {trace.AUDITED_TABLE} with the same key", "PostgreSQL log: pgAudit"],
        [_clock(story["credited_at"]), "Credit",
         f"Credit {story['credit_id']}, {_dollars(story['amount_cents'])}, with the same key",
         f"Aurora: store_credits {story['credit_id']}"],
    ]


def aurora_gap(story: Optional[Dict[str, Any]]) -> Optional[Followed]:
    """NOT YET PASSED without a credit; FAILED when a link between her rows is missing."""
    if not story or story.get("credit_id") is None:
        return Followed(check.NOT_YET, observed="Jessica has no store credit yet",
                        next_step="if you have not approved Jessica's credit, return to Task 4A "
                                  "and approve it as Nadia. Then follow Pay the credit once and "
                                  "check the records in Lab 4. Run this again after the replay.")
    for column, meaning in AURORA_LINKS:
        if story.get(column) is None:
            return Followed(check.FAILED, observed=meaning,
                            next_step="run psql -f workshop/wrap-up-reconstruct.sql to see "
                                      "which row is missing.")
    if story["idempotency_key"] != story["write_key"] or story["credits_with_key"] != 1:
        return Followed(check.FAILED, observed=(
            f"the review's key is on {check.counted(story['credits_with_key'], 'credit')} "
            f"({story['write_key']}); the credit's own key is {story['idempotency_key']}"))
    return None


@dataclass
class Records:
    """What CloudWatch and the PostgreSQL log hold for the window around her credit.

    Attributes:
        handoffs: The Gateway's ask_a_person calls.
        runtime: The Runtime's spans for those calls by trace id, ``None`` where unreadable.
        credits: The Gateway's give_store_credit calls.
        writes: pgAudit's credit-table writes.
        unavailable: Why pgAudit could not be read, or ``None`` when it was.
        names: Workshop sign-ins by Cognito subject.
    """

    handoffs: List[Dict[str, Any]]
    runtime: Dict[str, Any]
    credits: List[Dict[str, Any]]
    writes: List[Dict[str, Any]]
    unavailable: Optional[str]
    names: Dict[str, str]


def _credit_half(story: Dict[str, Any], records: Records, rows: List[List[str]],
                 now: float) -> Followed:
    """Nadia's Execute and what reached Aurora, after her turn's rows are in place."""
    if records.unavailable and records.unavailable.startswith(trace.BLIND_SPOT):
        # pgAudit can never record this write, so waiting changes nothing: a defect, not a lag.
        return Followed(check.FAILED, rows, observed=records.unavailable,
                        next_step="this is a fault in the workshop's database, not in your "
                                  "labs. Raise your hand so a facilitator can check it.")
    if records.unavailable:
        return Followed(check.COULD_NOT_CHECK, rows, observed=records.unavailable)
    inserts, paid = paid_call(records.credits, records.writes, story["write_key"],
                             story.get("credit_gateway_request_id"))
    if not inserts:
        if now - story["credited_at"].timestamp() < trace.LOG_EXPORT_LAG_S:
            return Followed(check.COULD_NOT_CHECK, rows,
                            observed="the PostgreSQL log has not been exported yet",
                            next_step="the log arrives about a minute after the write; run "
                                      "this again shortly.")
        return Followed(check.FAILED, rows,
                        observed="pgAudit logged no INSERT with the review's key")
    if paid is None:
        return Followed(check.COULD_NOT_CHECK, rows, observed=(
            f"no {CREDIT_TOOL} ALLOW with target execution matches the receipt's Gateway request id"),
            next_step="run this again in a moment.")
    if len(inserts) != 1:
        return Followed(check.FAILED, rows, observed=(
            f"pgAudit logged {len(inserts)} INSERTs with the review's key"))
    subject = paid.get("subject")
    if (not subject or not paid.get("identity_checked") or not paid.get("token_use")
            or "nadia" not in records.names.values()):
        return Followed(check.COULD_NOT_CHECK, rows,
                        observed="the Gateway records do not confirm who sent the credit",
                        next_step="run this again shortly to check the Gateway identity record.")
    if records.names.get(subject) != "nadia":
        caller = records.names.get(subject) or f"sub {subject[:8]}..."
        return Followed(check.FAILED, rows, observed=f"the credit's caller was {caller}, not Nadia",
                        next_step="keep the result and show it to a facilitator.")
    return Followed(check.PASSED, rows + credit_rows(story, paid, inserts[0], records.names),
                    joins=[
        f"Turn  {story['turn_id']} joins the agent's span, the audit row and her request.",
        f"Call  {story['handoff_gateway_request_id']} joins that audit row to the Gateway's "
        "span for the call.",
        f"Key   {story['write_key']} joins the audit row, the pgAudit line and the credit.",
        "Paid once: pgAudit logged one INSERT with this key, and Aurora holds one credit with it.",
    ])


def _later(story: Dict[str, Any], observed: str, state: str = check.COULD_NOT_CHECK,
           next_step: str = "") -> Followed:
    """A verdict on her handoff, with only the Aurora rows that stand on their own."""
    return Followed(state, decision_rows(story), observed=observed, next_step=(
        next_step or "spans reach CloudWatch about ten seconds after a call; run this again "
                     "shortly."))


def _caller_problem(story: Dict[str, Any], call: Dict[str, Any],
                    names: Dict[str, str]) -> Optional[Followed]:
    """FAILED when someone other than Jessica made the call; waiting when that is unknown."""
    subject = call.get("subject")
    if (not subject or not call.get("identity_checked") or not call.get("token_use")
            or "jessica" not in names.values()):
        return _later(story, "the Gateway's record of her handoff does not say who made it")
    if names.get(subject) != "jessica":
        who = names.get(subject) or f"sub {subject[:8]}..."
        return _later(story, f"the handoff call that opened her request was made by {who}, "
                             "not by Jessica", check.FAILED, CONTRADICTION)
    return None


def _handoff_problem(story: Dict[str, Any], call: Dict[str, Any],
                     records: Records) -> Optional[Followed]:
    """Why the identified call cannot complete the proof, or ``None`` when it can."""
    if call.get("decision") == "DENY":
        return _later(story, "the Gateway DENIED the handoff call that Aurora recorded as "
                             "run", check.FAILED, CONTRADICTION)
    problem = _caller_problem(story, call, records.names)
    if problem:
        return problem
    if call.get("decision") != "ALLOW" or call.get("lambda_ms") is None:
        return _later(story, "CloudWatch does not yet hold the policy decision and the "
                             "Lambda's run for her handoff call")
    spans = records.runtime.get(call["trace_id"])
    if spans is None:
        return _later(story, "the Runtime's log group could not be read")
    span = agent_span(spans)
    if span is None:
        return _later(story, f"no agent span for her handoff {HANDOFF_TOOL} call is in "
                             "CloudWatch")
    if trace._attrs(span).get("turn.id") != story["turn_id"]:
        return _later(story, "the agent span of the handoff call that opened her request "
                             "names a different turn", check.FAILED, CONTRADICTION)
    return None


def _handoff_gap(story: Dict[str, Any], records: Records) -> Tuple[
        Optional[Followed], Optional[Dict[str, Any]]]:
    """Find the one call that opened her request, then require it to be hers and to have run."""
    request_id = story.get("handoff_gateway_request_id")
    if not request_id:
        return Followed(check.COULD_NOT_CHECK, decision_rows(story), observed=(
            "her handoff's audit row predates the Gateway request id, so the call that "
            "opened her request cannot be identified"),
            next_step="keep the existing credit. Run psql -f workshop/wrap-up-reconstruct.sql "
                      "to inspect its Aurora records."), None
    call = handoff_call(records.handoffs, request_id)
    if call is None:
        return _later(story, f"the {HANDOFF_TOOL} call with Gateway request id {request_id} "
                             "is not in CloudWatch"), None
    return _handoff_problem(story, call, records), call


def follow(story: Optional[Dict[str, Any]], records: Records, now: float) -> Followed:
    """Join Aurora's rows, the agent's and AgentCore's spans and pgAudit into one chain.

    Args:
        story: Jessica's credit, review and request, from :data:`STORY_SQL`.
        records: What CloudWatch and the PostgreSQL log hold around her credit.
        now: The current time, for the PostgreSQL log's export lag.

    Returns:
        The chain as far as its records reach, and PASSED only when every link is found.
    """
    gap = aurora_gap(story)
    if gap:
        return gap
    assert story is not None
    gap, call = _handoff_gap(story, records)
    if gap:
        return gap
    assert call is not None
    span = agent_span(records.runtime[call["trace_id"]])
    assert span is not None
    rows = handoff_rows(story, call, span, records.names) + decision_rows(story)
    return _credit_half(story, records, rows, now)


def _join_line(join: str) -> str:
    """A join sentence wrapped under its label: ``Turn``, ``Call``, ``Key`` or ``Paid once:``."""
    label, _, rest = join.partition(" ")
    if label in ("Turn", "Call", "Key"):
        return check.wrapped(f"{label:<6}", rest.lstrip())
    return check.wrapped("", join)


def report(followed: Followed) -> str:
    """The chain as a table, then the joins, or the state and what to do next."""
    lines = [check.wrapped("", TITLE), ""]
    if followed.rows:
        lines += [check.table(HEADER, followed.rows), ""]
    if followed.state == check.PASSED:
        return "\n".join([*lines, *(_join_line(join) for join in followed.joins), "",
                          check.closing("End-to-end check", True)])
    lines.append(check.wrapped("", f"{followed.state}  {followed.observed}"))
    if followed.next_step:
        lines.append(check.wrapped("Next  ", followed.next_step))
    return "\n".join([*lines, check.closing("End-to-end check", False)])


def read_story() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Jessica's newest credit with its review and request, or why Aurora could not be read."""
    cfg = check.db_config()
    if cfg is None:
        return None, check.missing_settings_reason()
    try:
        with check.connect(cfg) as conn, conn.cursor() as cur:
            return cur.execute(STORY_SQL, {"customer": CUSTOMER}).fetchone(), None
    except Exception as exc:  # noqa: BLE001 - the line names the failure instead of guessing
        return None, f"the database could not be read ({type(exc).__name__})"


def read_records(story: Dict[str, Any]) -> Records:
    """Every span and log line the chain needs, from just before her request until now."""
    import boto3
    from config import settings
    from runtime_log_delivery import runtime_log_group

    minutes = math.ceil((time.time() - story["requested_at"].timestamp() + LEAD_S) / 60)
    logs = boto3.client("logs", region_name=settings.aws_region_resolved)
    handoffs = trace.fetch_calls_by_request(
        logs, HANDOFF_TOOL, [story.get("handoff_gateway_request_id")], minutes)
    try:
        group: Optional[str] = runtime_log_group(settings.AGENTCORE_RUNTIME_ENDPOINT or "")
    except ValueError:
        group = None
    writes, unavailable = trace.read_aurora(logs, minutes)
    return Records(
        handoffs=handoffs,
        runtime=trace.runtime_spans(logs, group, handoffs, minutes),
        credits=trace.fetch_calls_by_request(
            logs, CREDIT_TOOL, [story.get("credit_gateway_request_id")], minutes),
        writes=writes, unavailable=unavailable,
        names=trace.subject_names(
            boto3.client("cognito-idp", region_name=settings.cognito_region_resolved),
            settings.cognito_pool_id_resolved))


def collect(now: float) -> Followed:
    """Read Aurora first; read CloudWatch only when her rows are all there."""
    story, unreadable = read_story()
    if unreadable:
        return Followed(check.COULD_NOT_CHECK, observed=unreadable)
    gap = aurora_gap(story)
    if gap:
        return gap
    assert story is not None
    try:
        return follow(story, read_records(story), now)
    except Exception as exc:  # noqa: BLE001 - report the AWS error code, not the request
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        why = code or f"{type(exc).__name__}: {exc}"
        return Followed(check.COULD_NOT_CHECK, observed=f"CloudWatch could not be read ({why})")


def main(argv: Optional[List[str]] = None) -> int:
    """Print usage for ``--help`` or a flag the script does not have before it reads anything."""
    argparse.ArgumentParser(
        prog="follow_credit.py", description=__doc__.split("\n\n")[0]
    ).parse_args(sys.argv[1:] if argv is None else argv)
    from gateway_client import _load_env

    _load_env()
    with waiting("Reading Aurora, CloudWatch and the PostgreSQL log", typical=6):
        followed = collect(time.time())
    print(report(followed))
    return 0 if followed.state == check.PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main())
