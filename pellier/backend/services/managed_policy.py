"""
Managed AgentCore Policy — read surface for the Gateway-enforced Cedar engine.

The boutique's policy gate is now a **managed AgentCore Policy Engine** attached
to the AgentCore Gateway in ENFORCE mode (provisioned by
``scripts/deploy/deploy_policy.py``). The Gateway intercepts every tool call and
evaluates it against Cedar BEFORE the Lambda runs — argument-aware, default-deny,
forbid-wins. This replaced the old local ``BeforeToolCall`` hook + hand-rolled
fake-Cedar engine (both removed).

This module is the **read side** of that managed gate. It does NOT enforce
anything (the Gateway does) — it just lets the Atelier Policy surface show, live,
which Cedar policies are attached to the engine and what evidence the managed
rail produced.

Two reads:

  1. ``list_managed_policies()`` — boto3 ``bedrock-agentcore-control``
     ``list_policies(policyEngineId=...)`` + ``get_policy`` per id to pull the
     full Cedar ``definition``. Keyed on ``AGENTCORE_POLICY_ENGINE_ID`` (written
     to ``.env`` by the deploy script). Returns the policy statements so the
     surface can render "this is the Cedar the Gateway enforces".

  2. ``recent_decisions()`` — managed Policy emits ALLOW/DENY *decisions* to
     CloudWatch, not a queryable API. Rather than fabricate a decisions store,
     we return the ``pellier.tool_audit`` ALLOW rows: those rows ARE the
     managed-rail evidence (the experience Lambda writes a tool_audit row on the
     Gateway rail for every tool call that the Gateway ALLOWED through — see
     ``scripts/deploy/pellier_experience_server.py``). DENY decisions, by
     construction, never produce a tool_audit row because the tool never ran;
     the absence of a row for a denied call is itself the signal. If a queryable
     decisions API ships later, this is the one function to repoint.

Both reads are best-effort: a missing engine id, missing boto3, or an
unreachable control-plane returns an empty list with a ``source`` marker rather
than raising, so the Atelier surface degrades to "(no policies)" instead of a
500.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Env var the deploy script writes (``POLICY_ENGINE_ID=<id>`` → ``.env`` as
# ``AGENTCORE_POLICY_ENGINE_ID``). Read at call time (not import time) so a
# late-arriving .env still takes effect.
_ENGINE_ID_ENV = "AGENTCORE_POLICY_ENGINE_ID"


def _engine_id() -> str:
    return os.environ.get(_ENGINE_ID_ENV, "").strip()


def _region() -> str:
    """Region for the control-plane client. Mirror the backend's settings
    resolution but tolerate config import failure (this module is imported
    from routes that may run in a stripped env)."""
    try:
        from config import settings
        return settings.get_aws_region()
    except Exception:
        return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def list_managed_policies() -> Dict[str, Any]:
    """Return the Cedar policies attached to the managed policy engine.

    Shape (compatible with the Atelier Policy surface):
        {
            "source": "managed-engine" | "no-engine-id" | "error",
            "policy_engine_id": "<id or ''>",
            "policies": [
                {"id", "name", "description", "cedar"},
                ...
            ],
            "error": "<str>"   # only when source == "error"
        }

    ``cedar`` holds the Cedar statement pulled from the policy's
    ``definition.cedar.statement`` (the direct-Cedar shape the deploy script
    writes). ``applies_to`` is intentionally absent — managed Cedar encodes the
    gated action inside the statement itself (``action == AgentCore::Action::...``)
    rather than in a sidecar field.
    """
    engine_id = _engine_id()
    if not engine_id:
        return {
            "source": "no-engine-id",
            "policy_engine_id": "",
            "policies": [],
        }

    try:
        import boto3
    except Exception as exc:  # pragma: no cover — boto3 always present in deploy env
        logger.warning("boto3 unavailable for managed policy read: %s", exc)
        return {"source": "error", "policy_engine_id": engine_id, "policies": [], "error": str(exc)}

    try:
        client = boto3.client("bedrock-agentcore-control", region_name=_region())
        summaries = client.list_policies(policyEngineId=engine_id).get("policies", [])
        policies: List[Dict[str, Any]] = []
        for summary in summaries:
            policy_id = summary.get("policyId", "")
            name = summary.get("name", policy_id)
            description = summary.get("description", "")
            cedar = ""
            # The list summary may omit the full definition; fetch it per id.
            try:
                detail = client.get_policy(policyEngineId=engine_id, policyId=policy_id)
                description = detail.get("description", description)
                definition = detail.get("definition", {}) or {}
                cedar = (definition.get("cedar", {}) or {}).get("statement", "")
            except Exception as exc:
                logger.debug("get_policy(%s) failed: %s", policy_id, exc)
            policies.append({
                "id": policy_id,
                "name": name,
                "description": description,
                "cedar": cedar,
            })
        return {
            "source": "managed-engine",
            "policy_engine_id": engine_id,
            "policies": policies,
        }
    except Exception as exc:
        logger.warning("Managed policy list failed: %s", exc)
        return {"source": "error", "policy_engine_id": engine_id, "policies": [], "error": str(exc)}


async def recent_decisions(db_service: Any, session_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """Return recent managed-rail decisions as the tool_audit ALLOW rows.

    Managed Policy emits decisions to CloudWatch rather than a queryable API
    (see module docstring), so the ALLOW evidence is the ``pellier.tool_audit``
    rows the experience Lambda writes on the Gateway rail. Each row is an
    implicit ALLOW: the Gateway let the tool through, the Lambda ran it, and the
    row records args + result + latency. DENY decisions produce no row.

    Shape:
        {
            "source": "tool-audit",
            "session_id": "<session or '_anonymous'>",
            "decisions": [
                {"audit_id", "tool", "caller", "args", "latency_ms",
                 "created_at", "decision": "ALLOW"},
                ...
            ],
            "count": <int>,
        }

    Best-effort: returns an empty list (not an exception) when the DB is
    unavailable, so the Atelier surface stays a non-fatal read.
    """
    sid = session_id or "_anonymous"
    if db_service is None:
        return {"source": "tool-audit", "session_id": sid, "decisions": [], "count": 0}

    limit = max(1, min(500, int(limit)))
    if session_id:
        sql = (
            "SELECT audit_id, session_id, tool, caller, args, latency_ms, created_at "
            "FROM pellier.tool_audit WHERE session_id = %s "
            "ORDER BY created_at DESC LIMIT %s"
        )
        params = (session_id, limit)
    else:
        sql = (
            "SELECT audit_id, session_id, tool, caller, args, latency_ms, created_at "
            "FROM pellier.tool_audit ORDER BY created_at DESC LIMIT %s"
        )
        params = (limit,)

    try:
        rows = await db_service.fetch_all(sql, *params)
    except Exception as exc:
        logger.warning("Managed decisions (tool_audit) read failed: %s", exc)
        return {"source": "tool-audit", "session_id": sid, "decisions": [], "count": 0, "error": str(exc)}

    decisions: List[Dict[str, Any]] = []
    for r in rows or []:
        created = r.get("created_at")
        decisions.append({
            "audit_id": r.get("audit_id"),
            "tool": r.get("tool"),
            "caller": r.get("caller"),
            "args": r.get("args"),
            "latency_ms": r.get("latency_ms"),
            "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
            # Every tool_audit row is an ALLOW by construction — a denied
            # call never reached the Lambda, so it never wrote a row.
            "decision": "ALLOW",
        })
    return {"source": "tool-audit", "session_id": sid, "decisions": decisions, "count": len(decisions)}
