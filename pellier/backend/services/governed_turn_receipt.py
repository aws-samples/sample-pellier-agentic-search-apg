"""Durable, principal-scoped receipt for one governed shopper turn.

The governed workshop has several truthful but partial records:

* ``retrieval_receipts`` explains ranked catalog evidence.
* ``tool_audit`` proves that a tool target executed.
* ``governed_receipts`` records an explicit Gateway/Cedar decision.
* AgentCore Runtime exposes trace correlation IDs, not replayable spans.

This module joins those records at terminal turn time into the immutable
``governed_turn_receipts`` table. It never fills gaps with inference: an absent
policy decision is stored as ``NOT_EVALUATED`` and a missing retrieval receipt
produces no citations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Answer text is split into sentences at ". ", "! ", and "? ".
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

_INSERT_SQL = """
    INSERT INTO pellier.governed_turn_receipts (
        turn_id, session_id, principal_sub, principal_verified, rail,
        model_config, retrieval_receipt_id, citations, tool_audit_ids,
        policy_events, trace, handoff_context, terminal_outcome,
        terminal_status, latency_ms
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s::jsonb, %s, %s::jsonb, %s::jsonb,
        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s
    )
"""

_RETRIEVAL_SQL = """
    SELECT receipt_id,
           embedding_model,
           rerank_model,
           retrieval_config,
           citation_ids,
           citation_snapshots,
           citation_snapshot_hash
      FROM pellier.retrieval_receipts
     WHERE turn_id = %s
     ORDER BY created_at DESC
     LIMIT 1
"""

_AUDIT_SQL = """
    SELECT audit_id, tool, caller, latency_ms, created_at
      FROM pellier.tool_audit
     WHERE args->>'turn_id' = %s
     ORDER BY audit_id ASC
"""

# No current writer of pellier.governed_receipts puts a turn_id in args —
# the Lab 4 CLI, the forensic seed, and the migration seed all correlate by
# session_id instead — so this query returns no rows today and the receipt
# honestly reports NOT_EVALUATED. The join is kept as the contract for a
# future writer that records per-turn Cedar decisions; do not "fix" it by
# joining on session_id, which would attribute one turn's decision to every
# turn in the session.
_POLICY_SQL = """
    SELECT receipt_id,
           audit_id,
           tool,
           caller,
           decision,
           policy_engine_id,
           policy_name,
           created_at
      FROM pellier.governed_receipts
     WHERE args->>'turn_id' = %s
     ORDER BY receipt_id ASC
"""

_RECEIPT_BY_TURN_SQL = """
    SELECT turn_id,
           session_id,
           principal_sub,
           principal_verified,
           rail,
           model_config,
           retrieval_receipt_id,
           citations,
           tool_audit_ids,
           policy_events,
           trace,
           handoff_context,
           terminal_outcome,
           terminal_status,
           latency_ms,
           created_at
      FROM pellier.governed_turn_receipts
     WHERE turn_id = %s
       AND principal_sub = %s
     LIMIT 1
"""

_VISIBLE_AUDIT_SQL = """
    SELECT DISTINCT ta.audit_id,
           ta.session_id,
           ta.tool,
           ta.caller,
           ta.args,
           ta.result,
           ta.latency_ms,
           ta.created_at
      FROM pellier.tool_audit ta
      LEFT JOIN pellier.governed_receipts gr
        ON gr.audit_id = ta.audit_id
      LEFT JOIN pellier.governed_turn_receipts gtr
        ON gtr.tool_audit_ids @> jsonb_build_array(
            jsonb_build_object('audit_id', ta.audit_id)
        )
     WHERE gr.principal_id = %s
        OR gtr.principal_sub = %s
     ORDER BY ta.audit_id DESC
     LIMIT %s
"""


def _decode_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _json(value: Any) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"))


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _as_rows(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows or []]


def _model_config(retrieval: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return model identifiers, never prompt or response content."""
    try:
        from config import settings

        agent_model = (
            getattr(settings, "BEDROCK_ROUTER_MODEL", None)
            or getattr(settings, "AGENT_MODEL_ID", None)
            or None
        )
    except Exception:
        agent_model = None

    return {
        "agent_model": agent_model,
        "embedding_model": (retrieval or {}).get("embedding_model"),
        "rerank_model": (retrieval or {}).get("rerank_model"),
        "retrieval_config": _decode_json(
            (retrieval or {}).get("retrieval_config"), {}
        ),
    }


def _trace_metadata(trace: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep only service correlation metadata, never reconstructed spans."""
    trace = trace or {}
    managed = trace.get("managedTrace")
    if not isinstance(managed, dict):
        managed = {}
    allowed = {
        "traceKind": trace.get("traceKind"),
        "runtime": trace.get("runtime"),
        "rail": trace.get("rail"),
        "evidenceProvenance": trace.get("evidenceProvenance"),
        # Which revision answered. Without these three the fingerprint
        # comparison lives only in the in-memory runtime receipt and dies with
        # the backend, so nothing durable can say whether the managed rail ran
        # the participant's package or the deployment before it -- and the
        # build receipt had no way to make that claim.
        "buildFingerprint": trace.get("buildFingerprint"),
        "localBuildFingerprint": trace.get("localBuildFingerprint"),
        "buildState": trace.get("buildState"),
        "traceId": trace.get("traceId"),
        "runtimeRequestId": trace.get("runtimeRequestId"),
        # The AgentCore Runtime session, distinct from Pellier's `sessionId`.
        # Trace lookups (`agentcore traces list`) key on this one.
        "runtimeSessionId": trace.get("runtimeSessionId"),
        "sessionId": trace.get("sessionId"),
        # Persist service outcomes, never conversation content. The Lab 3
        # receipt must survive restart without relying on retrieval LTM IDs.
        "memory": {
            key: trace["memory"][key]
            for key in (
                "source", "turns_loaded", "turns_persisted", "namespace_scope",
                "read_status", "write_status", "error_code",
            )
            if isinstance(trace.get("memory"), dict) and key in trace["memory"]
        },
        "managedTrace": {
            key: managed.get(key)
            for key in (
                "region",
                "logGroupPrefix",
                "traceId",
                "runtimeRequestId",
                "sessionId",
                "logsInsightsQuery",
                "xrayConsoleUrl",
                "logsConsoleUrl",
            )
            if managed.get(key) is not None
        },
    }
    return {key: value for key, value in allowed.items() if value not in (None, {}, "")}


def _receipt_citations(
    *,
    retrieval_receipt_id: Optional[int],
    citation_snapshots: Any,
    expected_snapshot_hash: Any,
) -> List[Dict[str, Any]]:
    """Return only the catalog evidence captured at retrieval time.

    Re-querying ``product_catalog`` here would make an old governed receipt
    describe the catalog today rather than the product data used to answer the
    original turn. A missing or invalid snapshot is therefore an honest
    absence of citations, never a mutable catalog fallback.
    """
    snapshots = _decode_json(citation_snapshots, [])
    if not isinstance(snapshots, list) or not snapshots:
        return []
    if not isinstance(expected_snapshot_hash, str) or not expected_snapshot_hash:
        return []
    from services.retrieval_receipt import citation_snapshot_hash

    if citation_snapshot_hash(snapshots) != expected_snapshot_hash:
        logger.warning(
            "retrieval citation snapshot hash mismatch for receipt %s",
            retrieval_receipt_id,
        )
        return []

    citations: List[Dict[str, Any]] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        product_id = str(snapshot.get("entity_id") or "").strip()
        source_uri = str(snapshot.get("source_uri") or "").strip()
        quote = str(snapshot.get("quote") or "").strip()
        if not product_id or not source_uri or not quote:
            continue
        citations.append(
            {
                "evidence_id": (
                    f"retrieval-{retrieval_receipt_id}-catalog-{product_id}"
                    if retrieval_receipt_id is not None
                    else f"catalog-{product_id}"
                ),
                "source_uri": source_uri,
                "revision": snapshot.get("revision"),
                "quote": quote[:280],
                "entity_id": product_id,
            }
        )
    return citations


def _citation_product_name(citation: Dict[str, Any]) -> str:
    """Recover the product name from a snapshot quote.

    The retrieval writer captures ``Name: description``, but a catalog row with
    no description is captured as the bare name, and a hand-seeded snapshot may
    carry neither shape. Take the text before the first colon when there is
    one, and the whole quote when there is not, so a separator-less quote
    degrades to "the quote is the name" rather than to a description read as a
    name.

    Args:
        citation: One citation dict as built by :func:`_receipt_citations`.

    Returns:
        The recovered name, whitespace collapsed. Empty when the quote is.
    """
    quote = " ".join(str(citation.get("quote") or "").split())
    return quote.split(":", 1)[0].strip() or quote


def _name_phrase_pattern(name: str) -> "re.Pattern[str]":
    r"""Compile a case-insensitive whole-phrase matcher for one product name.

    Word-character lookarounds rather than ``\b`` so a name that begins or ends
    in punctuation still anchors: ``\b`` is defined against the adjacent
    character class, and would silently never match ``Bowl (Small)``.

    Args:
        name: The product name recovered from a citation quote.

    Returns:
        A compiled pattern that matches the name only as a whole phrase.
    """
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)


def map_answer_claims(
    answer_text: Optional[str], citations: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Map each answer sentence to the cited products it names.

    A sentence that names at least one cited product becomes a claim with
    the evidence ids behind it, in citation order. A sentence that names none
    is listed as unsupported. Matching is case-insensitive on the product name
    captured at retrieval time, so the mapping never reads the live catalog and
    never invents support.

    The name must appear as a whole phrase on word boundaries. A bare substring
    test attached a short or common-word name to sentences it did not support:
    a product called ``Ash`` claimed every sentence containing ``wash`` or
    ``cashmere``.

    Args:
        answer_text: The assistant's final answer.
        citations: Citation dicts as built by ``_receipt_citations``.

    Returns:
        ``(claims, unsupported)`` where each claim is
        ``{"text": sentence, "evidence_ids": [...]}``.
    """
    text = " ".join((answer_text or "").split())
    if not text:
        return [], []
    patterns: List[Tuple[Any, str]] = []
    for citation in citations:
        name = _citation_product_name(citation)
        evidence_id = citation.get("evidence_id")
        if name and evidence_id:
            patterns.append((_name_phrase_pattern(name), str(evidence_id)))
    claims: List[Dict[str, Any]] = []
    unsupported: List[str] = []
    for sentence in (part.strip() for part in _SENTENCE_BOUNDARY.split(text)):
        if not sentence:
            continue
        evidence_ids = [
            evidence_id
            for pattern, evidence_id in patterns
            if pattern.search(sentence)
        ]
        if evidence_ids:
            claims.append({"text": sentence, "evidence_ids": evidence_ids})
        else:
            unsupported.append(sentence)
    return claims, unsupported


def _terminal_outcome(
    *,
    terminal_error_code: Optional[str],
    answer_text: Optional[str],
    citations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the outcome JSON: the error code, and the answer's claims map."""
    outcome: Dict[str, Any] = {}
    if terminal_error_code:
        outcome["error_code"] = terminal_error_code
    if answer_text:
        claims, unsupported = map_answer_claims(answer_text, citations)
        outcome["claims"] = claims
        outcome["unsupported"] = unsupported
    return outcome


def _policy_events(
    rows: List[Dict[str, Any]],
    *,
    terminal_error_code: Optional[str],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "receipt_id": row.get("receipt_id"),
                "audit_id": row.get("audit_id"),
                "tool": row.get("tool"),
                "caller": row.get("caller"),
                "decision": row.get("decision"),
                "policy_engine_id": row.get("policy_engine_id"),
                "policy_name": row.get("policy_name"),
                "created_at": _iso(row.get("created_at")),
                "source": "governed_receipts",
            }
        )
    if events:
        return events
    if terminal_error_code == "policy_denied":
        return [
            {
                "decision": "DENY",
                "source": "managed_runtime_error",
                "reason": "The managed Runtime returned an explicit policy_denied code.",
            }
        ]
    return [
        {
            "decision": "NOT_EVALUATED",
            "source": "absence",
            "reason": "No governed policy decision was recorded for this turn.",
        }
    ]


def _record_policy_span(
    policy_events: List[Dict[str, Any]],
    *,
    turn_id: str,
    principal_sub: Optional[str],
) -> None:
    """Emit the policy boundary span for this turn's resolved decision.

    Pellier does not make the Cedar decision — AgentCore Gateway evaluates
    policy before the target runs, out of process. What happens here is
    Pellier *resolving* what that decision was, from any
    ``pellier.governed_receipts`` row recorded with this turn's id. No
    current writer records one (see the note on ``_POLICY_SQL``), so today
    every turn resolves to ``NOT_EVALUATED`` — an honest "no per-turn Cedar
    record exists", not a defect. The span records that resolution so the
    reconstruction CLI can show the policy leg alongside identity and
    execution.

    Three verdicts reach this function and all three are meaningful:

    ``ALLOW`` / ``DENY``
        A governed decision was recorded for the turn.
    ``NOT_EVALUATED``
        No Cedar decision exists — the ordinary in-process rail. This is
        emitted deliberately rather than skipped: "no policy ran" and
        "policy allowed it" are different facts, and a missing span would
        let a reader infer the second from the first.

    ``policy_mode`` is omitted on purpose. The Gateway's LOG_ONLY/ENFORCE
    setting is engine configuration, not turn data, and reading it per turn
    would mean a control-plane call on every receipt. Guessing it would be
    worse than leaving it absent.

    Observability never fails evidence collection: any exception here is
    swallowed, because the receipt insert is the durable artifact and this
    span is only a locator for it.
    """
    try:
        from services import evidence_spans

        verdict = None
        for event in policy_events:
            decision = event.get("decision")
            if decision:
                verdict = str(decision)
                break

        with evidence_spans.policy_span(
            turn_id=turn_id,
            principal_sub=principal_sub,
            policy_verdict=verdict,
            caller="gateway" if verdict in {"ALLOW", "DENY"} else "in-process",
        ):
            pass
    except Exception:  # pragma: no cover - a span must never break a receipt
        logger.debug("policy evidence span skipped", exc_info=True)


def _summary(
    *,
    turn_id: str,
    rail: str,
    terminal_status: str,
    citations: List[Dict[str, Any]],
    audit_rows: List[Dict[str, Any]],
    policy_events: List[Dict[str, Any]],
    latency_ms: Optional[int],
) -> Dict[str, Any]:
    return {
        "turn_id": turn_id,
        "rail": rail,
        "terminal_status": terminal_status,
        "citation_count": len(citations),
        "tool_count": len(audit_rows),
        "policy_decision": policy_events[0].get("decision")
        if policy_events
        else "NOT_EVALUATED",
        "latency_ms": latency_ms,
    }


async def persist_turn_receipt(
    db: Any,
    *,
    turn_id: str,
    session_id: Optional[str],
    principal_sub: Optional[str],
    rail: str,
    terminal_status: str,
    latency_ms: Optional[int],
    trace: Optional[Dict[str, Any]] = None,
    terminal_error_code: Optional[str] = None,
    handoff_context: Optional[Dict[str, Any]] = None,
    answer_text: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Persist one immutable turn record and return its truthful summary.

    Receipt persistence is evidence collection. The shopper turn has already
    reached a terminal state, so a database failure is logged and represented
    by ``None`` rather than changing that outcome or inventing a receipt.

    When ``answer_text`` is given, ``terminal_outcome`` also carries the
    answer's sentences mapped to the citations they name (``claims``) and the
    sentences no citation supports (``unsupported``).
    """
    if db is None:
        return None
    try:
        # Start the independent reads together, then process policy first and
        # emit its evidence span before propagating a retrieval/audit failure.
        #
        # Processing order is deliberate: the policy read and span used to sit
        # after the retrieval and citation reads, so a cluster missing
        # `pellier.retrieval_receipts` lost the policy evidence entirely —
        # the whole block aborted before the span was emitted. The policy
        # leg does not depend on retrieval, so it no longer waits on it.
        policy_result, retrieval_result, audit_result = await asyncio.gather(
            db.fetch_all(_POLICY_SQL, turn_id),
            db.fetch_one(_RETRIEVAL_SQL, turn_id),
            db.fetch_all(_AUDIT_SQL, turn_id),
            return_exceptions=True,
        )
        if isinstance(policy_result, BaseException):
            raise policy_result
        policy_rows = _as_rows(policy_result)
        policy_events = _policy_events(
            policy_rows, terminal_error_code=terminal_error_code
        )
        _record_policy_span(
            policy_events,
            turn_id=turn_id,
            principal_sub=principal_sub,
        )

        if isinstance(retrieval_result, BaseException):
            raise retrieval_result
        if isinstance(audit_result, BaseException):
            raise audit_result
        retrieval = retrieval_result
        retrieval_row = dict(retrieval) if retrieval else None
        audit_rows = _as_rows(audit_result)
        receipt_id = (
            int(retrieval_row["receipt_id"])
            if retrieval_row and retrieval_row.get("receipt_id") is not None
            else None
        )
        citations = _receipt_citations(
            retrieval_receipt_id=receipt_id,
            citation_snapshots=(retrieval_row or {}).get("citation_snapshots"),
            expected_snapshot_hash=(
                retrieval_row or {}
            ).get("citation_snapshot_hash"),
        )
        outcome = _terminal_outcome(
            terminal_error_code=terminal_error_code,
            answer_text=answer_text,
            citations=citations,
        )
        from services.shopper_handoff import attach_evidence_refs

        durable_handoff = attach_evidence_refs(
            handoff_context or {},
            retrieval_receipt_id=receipt_id,
            audit_rows=audit_rows,
        )
        await db.execute_query(
            _INSERT_SQL,
            turn_id,
            session_id,
            principal_sub,
            bool(principal_sub),
            rail,
            _json(_model_config(retrieval_row)),
            receipt_id,
            _json(citations),
            _json(
                [
                    {
                        "audit_id": row.get("audit_id"),
                        "tool": row.get("tool"),
                        "caller": row.get("caller"),
                        "latency_ms": row.get("latency_ms"),
                        "created_at": _iso(row.get("created_at")),
                    }
                    for row in audit_rows
                ]
            ),
            _json(policy_events),
            _json(_trace_metadata(trace)),
            _json(durable_handoff),
            _json(outcome),
            terminal_status,
            latency_ms,
        )
        return _summary(
            turn_id=turn_id,
            rail=rail,
            terminal_status=terminal_status,
            citations=citations,
            audit_rows=audit_rows,
            policy_events=policy_events,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning("governed turn receipt insert failed: %s", exc)
        return None


async def get_turn_receipt(
    db: Any, *, turn_id: str, principal_sub: str
) -> Optional[Dict[str, Any]]:
    """Return one persisted receipt only when it belongs to the caller."""
    if db is None or not principal_sub:
        return None
    try:
        row = await db.fetch_one(_RECEIPT_BY_TURN_SQL, turn_id, principal_sub)
    except Exception as exc:
        logger.warning("governed turn receipt read failed: %s", exc)
        return None
    if not row:
        return None
    receipt = dict(row)
    for key in (
        "model_config",
        "citations",
        "tool_audit_ids",
        "policy_events",
        "trace",
        "handoff_context",
        "terminal_outcome",
    ):
        receipt[key] = _decode_json(
            receipt.get(key),
            {}
            if key in {
                "model_config",
                "trace",
                "handoff_context",
                "terminal_outcome",
            }
            else [],
        )
    receipt["created_at"] = _iso(receipt.get("created_at"))
    return receipt


async def get_visible_tool_audit(
    db: Any, *, principal_sub: str, limit: int
) -> List[Dict[str, Any]]:
    """Return only audit rows linked to the verified principal's receipts."""
    if db is None or not principal_sub:
        return []
    safe_limit = max(1, min(50, int(limit)))
    try:
        rows = await db.fetch_all(
            _VISIBLE_AUDIT_SQL, principal_sub, principal_sub, safe_limit
        )
    except Exception as exc:
        logger.warning("principal-scoped tool audit read failed: %s", exc)
        return []
    normalized = _as_rows(rows)
    for row in normalized:
        row["created_at"] = _iso(row.get("created_at"))
    return normalized
