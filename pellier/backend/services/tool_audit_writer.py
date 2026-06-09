"""
Tool Audit Writer — fire-and-forget INSERT/UPDATE pair against pellier.tool_audit.

Theo's anchor capability is "Aurora as agent system-of-record." Every
tool call an agent runs — read or write — gets a row in
``pellier.tool_audit`` so the entire turn is reconstructible from a
single SELECT, and procedural memory has the full per-tool signal
(which tool ran for which intent, at which latency).

Why a separate writer module:

* Audit ≠ enforcement. Enforcement now lives entirely in the managed
  AgentCore Policy engine at the Gateway (Cedar, ENFORCE mode); this
  writer is its own concern so that failing to audit can't fail a tool
  call, and a failing tool call can't fail the audit.
* The ALLOW-side INSERT happens BEFORE the tool body runs, so we have
  a row to UPDATE with the result + latency in AfterToolCallEvent. If
  the tool raises, the row remains with result=NULL — which is itself
  a real signal (a tool that started but didn't finish).
* DENY decisions never reach pellier.tool_audit: a call the managed
  Gateway policy denies never runs the tool, so it never writes a row.
  Audit is for what *happened*; the absence of a row for a denied call
  is the "what was prevented" signal. Two different teaching surfaces.

The writes go through ``DatabaseService.execute_query`` so they share
the same connection pool + per-cursor logging the rest of the backend
uses. Latency-wise the INSERT adds ~5-10ms; we take that cost on
every tool call because the alternative — async fire-and-forget
through a queue — would be a bigger teaching distraction than the
cost itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Module-level state. The DatabaseService and main event loop are
# injected at app startup (services.agent_tools owns the same pattern
# for set_db_service / set_main_loop).
_db_service: Any = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# Map of tool_use_id → last-inserted audit_id, so AfterToolCallEvent
# can locate the row to UPDATE. Bounded so a runaway agent can't grow
# this map indefinitely.
_PENDING_MAX = 5000
_pending_lock = threading.Lock()
_pending_audits: Dict[str, int] = {}


def set_db_service(db: Any) -> None:
    """App startup hook — wire the writer to the live DB pool."""
    global _db_service
    _db_service = db


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """App startup hook — capture the uvicorn event loop so the @tool
    callback (which runs in a worker thread) can dispatch async DB
    writes back onto it."""
    global _main_loop
    _main_loop = loop


def _run_async(coro: Any) -> Any:
    """Bridge from sync (Strands callback) to async (DB driver).

    The Strands hook callbacks fire in a thread that is NOT the main
    uvicorn loop. ``run_coroutine_threadsafe`` schedules the coroutine
    on the captured main loop and blocks until it returns.

    Returns None if the loop isn't captured yet (audit silently no-ops
    so a bootstrap-order issue doesn't blow up tool calls).
    """
    if _main_loop is None:
        return None
    try:
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        return future.result(timeout=5.0)
    except Exception as exc:
        logger.debug("tool_audit _run_async: %s", exc)
        return None


# -----------------------------------------------------------------
# ALLOW-side: INSERT a placeholder row before the tool runs
# -----------------------------------------------------------------


def record_allow(
    tool_use_id: Optional[str],
    tool_name: str,
    caller: str,
    args: Dict[str, Any],
    session_id: Optional[str],
) -> None:
    """INSERT a row into ``pellier.tool_audit`` for an ALLOW decision.

    Called from an in-process AfterToolCall telemetry path right after a
    tool the Gateway ALLOWED begins running. The row's ``result`` and
    ``latency_ms`` start NULL and get UPDATEd in AfterToolCallEvent
    (record_after).

    If the INSERT fails, we log at DEBUG and move on — audit is
    decoration; the tool call must still proceed.
    """
    if _db_service is None:
        return
    if not tool_use_id:
        # No id to correlate with the After event; skip the round-trip.
        return

    sql = (
        "INSERT INTO pellier.tool_audit "
        "(session_id, tool, caller, args, result, latency_ms) "
        "VALUES (%s, %s, %s, %s::jsonb, NULL, NULL) "
        "RETURNING audit_id"
    )
    try:
        row = _run_async(
            _db_service.fetch_one(
                sql,
                session_id or "_anonymous",
                tool_name,
                caller or "agent",
                json.dumps(args, default=str),
            )
        )
    except Exception as exc:
        logger.debug("tool_audit INSERT failed: %s", exc)
        return
    if not row:
        return
    audit_id = row.get("audit_id")
    if audit_id is None:
        return
    with _pending_lock:
        if len(_pending_audits) >= _PENDING_MAX:
            # Drop oldest entry — the After event is unlikely to fire
            # for a tool that's been pending more than a thousand calls.
            try:
                _pending_audits.pop(next(iter(_pending_audits)))
            except StopIteration:
                pass
        _pending_audits[tool_use_id] = audit_id


# -----------------------------------------------------------------
# After: UPDATE the row with the tool's result + latency
# -----------------------------------------------------------------


def record_after(
    tool_use_id: Optional[str],
    result: Any,
    latency_ms: int,
) -> None:
    """UPDATE the previously-INSERTed audit row with result + latency.

    Strands' AfterToolCallEvent fires once the tool returns. We look
    up the audit_id by tool_use_id, UPDATE the row, and discard the
    pending mapping. Same fire-and-forget posture as record_allow —
    audit failures don't surface to the tool call.
    """
    if _db_service is None or not tool_use_id:
        return
    with _pending_lock:
        audit_id = _pending_audits.pop(tool_use_id, None)
    if audit_id is None:
        return

    # Cap the result payload so a tool that returns 50KB of products
    # doesn't blow up the JSONB cell. The first 8KB is plenty for the
    # workshop's "what did the agent see?" replay — and the cell
    # remains queryable as JSONB.
    try:
        result_str = json.dumps(result, default=str)
    except Exception:
        result_str = json.dumps({"_unserializable_repr": repr(result)[:1024]})
    if len(result_str) > 8192:
        result_str = json.dumps({
            "_truncated": True,
            "_original_len": len(result_str),
            "_head": result_str[:8000],
        })

    sql = (
        "UPDATE pellier.tool_audit "
        "SET result = %s::jsonb, latency_ms = %s "
        "WHERE audit_id = %s"
    )
    try:
        _run_async(
            _db_service.execute_query(sql, result_str, int(latency_ms), audit_id)
        )
    except Exception as exc:
        logger.debug("tool_audit UPDATE failed: %s", exc)
