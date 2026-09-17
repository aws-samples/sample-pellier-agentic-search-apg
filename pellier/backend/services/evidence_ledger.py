"""Principal-scoped projection of Pellier's canonical evidence sources.

This is a read model, not a new source of truth. Every event carries a source
reference and provenance so the Observatory can distinguish durable Aurora
receipts from CloudWatch spans, AgentCore service telemetry, and live-only
presentation events.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


class EvidenceLedgerProjectionError(RuntimeError):
    """The durable projection could not be read from canonical sources."""


_EVENTS_BY_TURN_SQL = """
    SELECT turn_id, session_id, event_kind, phase, status, provenance,
           source_kind, source_id, occurred_at, duration_ms, summary
      FROM pellier.evidence_ledger_event_refs
     WHERE turn_id = %s
       AND principal_sub = %s
"""

_EVENTS_BY_SESSION_SQL = """
    SELECT turn_id, session_id, event_kind, phase, status, provenance,
           source_kind, source_id, occurred_at, duration_ms, summary
      FROM pellier.evidence_ledger_event_refs
     WHERE session_id = %s
       AND principal_sub = %s
"""

_QUERY_SQL_BY_TURN = """
    SELECT receipt_id, generated_sql
      FROM pellier.governed_query_receipts
     WHERE turn_id = %s
       AND principal_sub = %s
"""

_RETRIEVAL_SQL_BY_TURN = """
    SELECT receipt_id, query_preview, vector_ranks, lexical_ranks, rrf_scores,
           rerank_scores, merchandising_rules, memory_record_ids_used,
           latency_breakdown
      FROM pellier.retrieval_receipts
     WHERE turn_id = %s
       AND principal_sub = %s
"""

# Principal-scoped like the receipts above: an audit row is visible only
# through the governed turn receipt that names its turn.
_TOOL_AUDIT_SQL_BY_TURN = """
    SELECT ta.audit_id, ta.args, ta.result
      FROM pellier.tool_audit ta
      JOIN pellier.governed_turn_receipts gtr
        ON gtr.turn_id = ta.args->>'turn_id'
     WHERE gtr.turn_id = %s
       AND gtr.principal_sub = %s
"""

_PHASE_ORDER = {
    "routing": 10,
    "context": 20,
    "evidence": 30,
    "reasoning": 40,
    "governance": 50,
    "execution": 60,
    "terminal": 90,
    # Operator review decisions and their governed execution happen after the
    # shopper turn is terminal. Keeping that lifecycle after the immutable turn
    # receipt prevents a later human action from being presented as if it ran
    # during the shopper rail.
    "follow_up": 100,
}

_EVENT_TITLES = {
    "route": "Execution route recorded",
    "plan": "Plan checkpoint",
    "memory": "Memory context",
    "retrieval": "Hybrid retrieval receipt",
    "rerank": "Rerank receipt",
    "model": "Model invocation receipt",
    "tool": "Tool execution receipt",
    "policy": "Policy decision",
    "aurora": "Governed Aurora query",
    "write": "Aurora write receipt",
    "response": "Terminal turn receipt",
    "operator_review": "Operator review lifecycle",
}


def _decode(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value is not None else None


def _rows(values: Iterable[Any]) -> List[Dict[str, Any]]:
    return [dict(value) for value in values or []]


def _event_summary(kind: str, summary: Dict[str, Any]) -> str:
    if kind == "route":
        return f"{summary.get('rail') or 'unknown'} rail captured at terminal persistence."
    if kind == "retrieval":
        citations = summary.get("citation_ids")
        count = len(citations) if isinstance(citations, list) else 0
        candidates = int(summary.get("candidate_count") or 0)
        return f"{candidates} candidates evaluated; {count} catalog citations retained."
    if kind == "aurora":
        if summary.get("accepted") is False:
            return "Generated SQL was rejected before database execution."
        return (
            f"Read-only query executed as {summary.get('role_used') or 'bounded role'}; "
            f"{int(summary.get('row_count') or 0)} rows returned."
        )
    if kind == "model":
        total = summary.get("total_tokens")
        token_note = f"{int(total)} tokens" if total is not None else "token usage unavailable"
        return f"{summary.get('purpose') or 'Model call'}; {token_note}."
    if kind == "tool":
        return (
            f"{summary.get('caller') or 'agent'} executed "
            f"{summary.get('tool') or 'a tool target'}."
        )
    if kind == "policy":
        return f"Policy outcome: {summary.get('decision') or 'NOT_EVALUATED'}."
    if kind == "response":
        return (
            f"Turn ended {summary.get('terminal_status') or 'without a recorded status'} "
            f"with {int(summary.get('citation_count') or 0)} citations and "
            f"{int(summary.get('tool_count') or 0)} tool receipts."
        )
    if kind == "operator_review":
        action = str(summary.get("action") or "prepared action")
        lifecycle = str(summary.get("lifecycle") or "")
        if lifecycle == "review_opened":
            return (
                f"{action} was prepared for Operator review. "
                "The shopper rail did not execute the mutation."
            )
        if lifecycle == "confirmed":
            return (
                f"An operator confirmed {action}. "
                "Governed execution had not started at this checkpoint."
            )
        if lifecycle == "declined":
            return (
                f"An operator declined {action}. "
                "The governed execution path was not entered."
            )
        if lifecycle == "execution_recorded":
            return (
                f"Operator execution for {action}: policy "
                f"{summary.get('policy_outcome') or 'NOT_EVALUATED'}; Aurora "
                f"{summary.get('aurora_outcome') or 'NOT_REACHED'}; evidence "
                f"{summary.get('evidence_outcome') or 'unavailable'}."
            )
    return "Evidence recorded."


def _event_title(kind: str, summary: Dict[str, Any]) -> str:
    if kind != "operator_review":
        return _EVENT_TITLES.get(kind, "Evidence event")
    lifecycle = str(summary.get("lifecycle") or "")
    if lifecycle == "review_opened":
        return "Operator review opened"
    if lifecycle == "confirmed":
        return "Operator confirmed the prepared action"
    if lifecycle == "declined":
        return "Operator declined the prepared action"
    if lifecycle == "execution_recorded":
        return "Operator execution receipt"
    return _EVENT_TITLES[kind]


def _event(
    row: Dict[str, Any],
    *,
    sql_by_receipt: Dict[str, str],
    retrieval_by_receipt: Dict[str, Dict[str, Any]],
    tool_by_audit: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    kind = str(row.get("event_kind") or "response")
    source_kind = str(row.get("source_kind") or "unknown")
    source_id = str(row.get("source_id") or "")
    summary = _decode(row.get("summary"), {})
    if not isinstance(summary, dict):
        summary = {}
    details: Dict[str, Any] = dict(summary)
    sql = None
    if source_kind == "governed_query_receipt":
        sql = sql_by_receipt.get(source_id)
    if source_kind == "retrieval_receipt":
        details.update(retrieval_by_receipt.get(source_id, {}))
    if source_kind == "tool_audit" and tool_by_audit:
        # The view's summary names the tool and caller only; the recorded
        # input and output travel with the event so replay can show exactly
        # what ran, not just that it ran.
        details.update(tool_by_audit.get(source_id, {}))
    return {
        "sequence": 0,
        "eventKind": kind,
        "phase": str(row.get("phase") or "terminal"),
        "status": str(row.get("status") or "unavailable"),
        "provenance": str(row.get("provenance") or "aurora-receipt"),
        "occurredAt": _iso(row.get("occurred_at")),
        "durationMs": row.get("duration_ms"),
        "turnId": str(row.get("turn_id") or ""),
        "sessionId": row.get("session_id"),
        "traceId": summary.get("trace_id")
        or (_decode(summary.get("trace"), {}) or {}).get("traceId"),
        "evidenceRef": {
            "kind": source_kind,
            "id": source_id,
        },
        "title": _event_title(kind, summary),
        "summary": _event_summary(kind, summary),
        "details": details,
        "sql": sql,
    }


def _denied_then_executed(events: List[Dict[str, Any]]) -> List[str]:
    """Find a DENY linked to the exact executed audit row on the same turn.

    A tool can be requested more than once, including across turns in a session
    ledger. Its name alone cannot correlate a denial to an execution attempt.
    A null tool result still proves entry into the tool when its audit row exists.
    """
    executed = {
        (
            str(event["turnId"]),
            str((event.get("details") or {}).get("tool")),
            str((event.get("evidenceRef") or {})["id"]),
        )
        for event in events
        if event.get("eventKind") == "tool"
        and event.get("turnId")
        and (event.get("details") or {}).get("tool")
        and (event.get("evidenceRef") or {}).get("kind") == "tool_audit"
        and (event.get("evidenceRef") or {}).get("id") is not None
    }
    contradicted = set()
    for event in events:
        details = event.get("details") or {}
        if (
            event.get("eventKind") == "policy"
            and event.get("status") == "denied"
            and details.get("audit_id") is not None
            and (
                str(event.get("turnId")),
                str(details.get("tool")),
                str(details["audit_id"]),
            ) in executed
        ):
            contradicted.add(str(details["tool"]))
    return sorted(contradicted)


def _sufficiency(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kinds = {event["eventKind"] for event in events}
    by_kind = {
        kind: [event for event in events if event["eventKind"] == kind]
        for kind in kinds
    }
    policy_events = [event for event in events if event["eventKind"] == "policy"]
    policy_not_enforced = bool(policy_events) and all(
        event["status"] == "not_enforced" for event in policy_events
    )
    contradicted = _denied_then_executed(events)
    contradiction_detail = (
        "A DENY links to the exact executed audit row for "
        f"{', '.join(contradicted)} on the same turn. tool_audit records only calls that ran, "
        "so these two receipts cannot both hold; read them side by side before "
        "concluding anything about this turn."
    )
    checks = [
        {
            "id": "terminal-receipt",
            "label": "Immutable terminal receipt",
            "status": "satisfied" if "response" in kinds else "missing",
            "detail": "The turn is anchored by governed_turn_receipts.",
        },
        {
            "id": "retrieval-evidence",
            "label": "Retrieval evidence",
            "status": (
                "satisfied"
                if any(
                    event["status"] == "succeeded"
                    for event in by_kind.get("retrieval", [])
                )
                else "not_applicable"
                if "retrieval" not in kinds
                else "missing"
            ),
            "detail": "Constraints, ranking stages, model ids and citations come from retrieval_receipts.",
        },
        {
            "id": "model-usage",
            "label": "Redacted model usage",
            "status": (
                "satisfied"
                if any(
                    event["status"] == "succeeded"
                    for event in by_kind.get("model", [])
                )
                else "missing"
                if "model" in kinds
                else "unavailable"
            ),
            "detail": "Metadata only; prompts and completions are not retained.",
        },
        {
            "id": "tool-execution",
            "label": "Tool execution evidence",
            "status": (
                "contradicted"
                if contradicted
                else "satisfied"
                if "tool" in kinds
                else "not_reached"
                if any(event["status"] == "denied" for event in policy_events)
                else "not_applicable"
            ),
            "detail": (
                contradiction_detail
                if contradicted
                else "A tool event exists only when tool_audit proves the target ran."
            ),
        },
        {
            "id": "policy-decision",
            "label": "Policy decision",
            "status": (
                "contradicted"
                if contradicted
                else "not_enforced"
                if policy_not_enforced
                else "satisfied"
                if policy_events
                else "unavailable"
            ),
            "detail": (
                contradiction_detail
                if contradicted
                else "NOT_EVALUATED is distinct from ALLOW and DENY."
            ),
        },
        {
            "id": "trace-correlation",
            "label": "Trace correlation",
            "status": (
                "satisfied"
                if any(event.get("traceId") for event in events)
                else "unavailable"
            ),
            "detail": "CloudWatch or AgentCore trace identifiers locate service telemetry without copying span payloads into Aurora.",
        },
    ]
    uncorrelated = any(
        policy.get("turnId")
        and (policy.get("details") or {}).get("tool")
        and (policy.get("details") or {}).get("audit_id") is None
        and policy["status"] == "denied"
        and any(
            tool.get("turnId") == policy.get("turnId")
            and (tool.get("details") or {}).get("tool")
            == (policy.get("details") or {}).get("tool")
            for tool in by_kind.get("tool", [])
        )
        for policy in policy_events
    )
    if uncorrelated:
        checks.append({
            "id": "policy-execution-correlation",
            "label": "Policy and execution correlation",
            "status": "unavailable",
            "detail": (
                "A denial and execution name the same tool on a turn, but no "
                "audit-row link establishes that they describe the same attempt. "
                "Compare the exact request keys before concluding a contradiction."
            ),
        })
    return checks


def _order(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    turn_anchors: Dict[str, str] = {}
    for event in events:
        turn_id = str(event.get("turnId") or "")
        occurred_at = str(event.get("occurredAt") or "")
        if not turn_id:
            continue
        current = turn_anchors.get(turn_id)
        if current is None or (occurred_at and occurred_at < current):
            turn_anchors[turn_id] = occurred_at
    ordered = sorted(
        events,
        key=lambda event: (
            turn_anchors.get(str(event.get("turnId") or ""), ""),
            _PHASE_ORDER.get(str(event.get("phase") or ""), 80),
            event.get("occurredAt") or "",
            event.get("eventKind") or "",
            str((event.get("evidenceRef") or {}).get("id") or ""),
        ),
    )
    for sequence, event in enumerate(ordered, start=1):
        event["sequence"] = sequence
    return ordered


async def _tool_details(
    db: Any, *, turn_ids: List[str], principal_sub: str
) -> Dict[str, Dict[str, Any]]:
    """Recorded args and result per audit row, keyed by audit_id as text."""
    tool_by_audit: Dict[str, Dict[str, Any]] = {}
    for turn_id in turn_ids:
        try:
            rows = _rows(
                await db.fetch_all(_TOOL_AUDIT_SQL_BY_TURN, turn_id, principal_sub)
            )
        except Exception as exc:  # pragma: no cover - degraded read keeps the ledger
            logger.warning("tool audit detail read failed: %s", exc)
            return {}
        for row in rows:
            tool_by_audit[str(row.get("audit_id"))] = {
                "args": _decode(row.get("args"), {}),
                "result": _decode(row.get("result"), {}),
            }
    return tool_by_audit


async def _details(
    db: Any, *, turn_ids: List[str], principal_sub: str
) -> tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
    sql_by_receipt: Dict[str, str] = {}
    retrieval_by_receipt: Dict[str, Dict[str, Any]] = {}
    for turn_id in turn_ids:
        query_rows = _rows(
            await db.fetch_all(_QUERY_SQL_BY_TURN, turn_id, principal_sub)
        )
        for row in query_rows:
            sql_by_receipt[str(row.get("receipt_id"))] = str(
                row.get("generated_sql") or ""
            )
        retrieval_rows = _rows(
            await db.fetch_all(_RETRIEVAL_SQL_BY_TURN, turn_id, principal_sub)
        )
        for row in retrieval_rows:
            object_fields = {
                "vector_ranks",
                "lexical_ranks",
                "rrf_scores",
                "rerank_scores",
                "latency_breakdown",
            }
            retrieval_by_receipt[str(row.get("receipt_id"))] = {
                key: _decode(row.get(key), {} if key in object_fields else [])
                for key in (
                    "vector_ranks",
                    "lexical_ranks",
                    "rrf_scores",
                    "rerank_scores",
                    "merchandising_rules",
                    "memory_record_ids_used",
                    "latency_breakdown",
                )
            }
            # The stored preview (not the full shopper phrasing) lets the
            # Observatory open the Search pipeline on the same text a turn
            # actually retrieved with, instead of a default example query.
            retrieval_by_receipt[str(row.get("receipt_id"))]["query_preview"] = (
                str(row.get("query_preview") or "")
            )
    return sql_by_receipt, retrieval_by_receipt


async def _project(
    db: Any,
    *,
    rows: List[Dict[str, Any]],
    principal_sub: str,
) -> Dict[str, Any]:
    turn_ids = sorted(
        {str(row.get("turn_id") or "") for row in rows if row.get("turn_id")}
    )
    sql_by_receipt, retrieval_by_receipt = await _details(
        db,
        turn_ids=turn_ids,
        principal_sub=principal_sub,
    )
    tool_by_audit = await _tool_details(
        db, turn_ids=turn_ids, principal_sub=principal_sub
    )
    events = _order(
        [
            _event(
                row,
                sql_by_receipt=sql_by_receipt,
                retrieval_by_receipt=retrieval_by_receipt,
                tool_by_audit=tool_by_audit,
            )
            for row in rows
        ]
    )
    return {
        "version": "1.0",
        "authority": "canonical-receipt-projection",
        "principalScoped": True,
        "events": events,
        "evidenceSufficiency": _sufficiency(events),
    }


async def project_turn_ledger(
    db: Any,
    *,
    turn_id: str,
    principal_sub: str,
    raise_on_error: bool = False,
) -> Optional[Dict[str, Any]]:
    """Project one turn only when its terminal receipt belongs to the caller."""
    if db is None or not principal_sub:
        return None
    try:
        rows = _rows(
            await db.fetch_all(_EVENTS_BY_TURN_SQL, turn_id, principal_sub)
        )
        if not rows:
            return None
        ledger = await _project(db, rows=rows, principal_sub=principal_sub)
        ledger["turnId"] = turn_id
        ledger["sessionId"] = rows[0].get("session_id")
        return ledger
    except Exception as exc:
        logger.warning("turn evidence ledger projection failed: %s", exc)
        if raise_on_error:
            raise EvidenceLedgerProjectionError(
                "turn evidence ledger projection unavailable"
            ) from exc
        return None


async def project_session_ledger(
    db: Any,
    *,
    session_id: str,
    principal_sub: str,
    raise_on_error: bool = False,
) -> Optional[Dict[str, Any]]:
    """Project every visible governed turn in one session."""
    if db is None or not principal_sub:
        return None
    try:
        rows = _rows(
            await db.fetch_all(_EVENTS_BY_SESSION_SQL, session_id, principal_sub)
        )
        if not rows:
            return None
        ledger = await _project(db, rows=rows, principal_sub=principal_sub)
        ledger["sessionId"] = session_id
        ledger["turnIds"] = sorted(
            {str(row.get("turn_id")) for row in rows if row.get("turn_id")}
        )
        return ledger
    except Exception as exc:
        logger.warning("session evidence ledger projection failed: %s", exc)
        if raise_on_error:
            raise EvidenceLedgerProjectionError(
                "session evidence ledger projection unavailable"
            ) from exc
        return None
