"""``/api/observatory/*`` — Pellier Observatory read-only API endpoints.

This router provides the backend data layer for the Pellier Observatory
frontend surfaces. Most endpoints are read-only reference payloads with
graceful degradation when a live dependency is unavailable; the memory
surface is live-only and never serves static memory data.

Endpoints are additive to the existing ``routes/workshop.py`` router
(which also mounts at ``/api/observatory/``). No path conflicts — workshop
owns ``/query``, ``/resume``, ``/tool-registry``; this router owns the
observatory surface endpoints listed below.

Endpoints:
    GET  /sessions             — session list for persona
    GET  /sessions/{id}        — full session detail or 404
    GET  /agents               — 5 agents with status, tools, model config
    GET  /tools/list           — tools with signatures, status, metadata
    POST /tools/discover       — pgvector semantic search
    GET  /routing              — 3 routing patterns with active indicator
    GET  /memory/{persona}     — four memory types plus operational history
    GET  /performance          — metrics and benchmarks
    GET  /evaluations          — agent scorecards
    GET  /architecture         - system architecture diagram payload
    GET  /operator-lineage/{customer_id}
                              - live shopper-to-operator graph and outcome
    GET  /build-state          - shipped vs exercise maps for agents and tools
    GET  /readiness            - workshop readiness checks for live pillars
    GET  /proof-board          - required-path evidence cards and fallbacks
    POST /skills/route         - Live skill router demo (Sonnet 4.6)
    GET  /policies             - Cedar policies for the Write-path surface
    GET  /tool-audit/recent    - Recent rows from pellier.tool_audit
    GET  /identity-boundary    - Verified principal vs requested customer,
                                 Cedar decision, and keyed execution presence
                                 or absence, from pellier.governed_receipts
"""

from __future__ import annotations

import ast
import logging
import runpy
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
# Aliased: `Path` in this module is `pathlib.Path`, used for filesystem
# reads. Importing FastAPI's under the same name shadowed it and every
# `Path(__file__)` became a path-parameter declaration.
from fastapi import Path as PathParam
from pydantic import BaseModel, Field
from services.auth import authorize_customer_read, get_current_user, require_operator
from services.observatory_copy import OBSERVATORY_COPY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observatory", tags=["observatory"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ObservatorySessionSummary(BaseModel):
    """Summary of a single session for the sessions list."""
    id: str
    persona_id: str = Field(alias="personaId")
    opening_query: str = Field(alias="openingQuery")
    elapsed_ms: int = Field(alias="elapsedMs")
    agent_count: int = Field(alias="agentCount")
    routing_pattern: str = Field(alias="routingPattern")
    timestamp: str
    status: str

    model_config = {"populate_by_name": True}


class ObservatoryToolDiscoverRequest(BaseModel):
    """Request body for the tool discovery endpoint."""
    query: str = Field(
        default="show me something for long summer walks",
        min_length=1,
        description="Natural-language query for semantic tool discovery",
    )
    limit: int = Field(default=5, ge=1, le=9)


class ObservatoryToolDiscoverResult(BaseModel):
    """A single tool discovery result with similarity score."""
    rank: int
    tool_id: str
    name: str
    description: str
    similarity: float
    status: str


class ObservatoryToolDiscoverResponse(BaseModel):
    """Response from the tool discovery endpoint."""
    query: str
    results: list[ObservatoryToolDiscoverResult]
    duration_ms: int
    sql: str
    total_count: int


# ---------------------------------------------------------------------------
# Live data helpers
# ---------------------------------------------------------------------------


async def _live_db() -> Any:
    """Return Aurora or fail loudly; the Observatory never renders fixtures."""
    from app import db_service

    if db_service is None:
        raise HTTPException(
            status_code=503,
            detail="Aurora is unavailable; live Observatory data cannot be shown.",
        )
    return db_service


def _check_inventory_is_workshop_stub() -> bool:
    """True when the live ``check_inventory`` body still returns the starter stub."""
    try:
        import inspect
        from services import agent_tools

        src = inspect.getsource(agent_tools.check_inventory)
    except Exception:
        return True
    if "check_inventory is in stub state" in src:
        return True
    if "received_product_query" in src:
        return True
    return False


def _inventory_agent_definition_is_workshop_stub() -> bool:
    """True when the Inventory Agent definition still carries the starter stub."""
    try:
        from agents import inventory_agent

        return bool(getattr(inventory_agent, "_INVENTORY_AGENT_STUBBED", False))
    except Exception:
        return True


def _lab2_candidate_budget_is_workshop_stub() -> bool:
    """True while the live rerank pool still has the deliberately narrow starter budget."""
    try:
        from services.planned_hybrid_retrieval import DEFAULT_RERANK_POOL_K

        return DEFAULT_RERANK_POOL_K == 3
    except Exception:
        return True


def _lab3_gateway_catalogue_is_workshop_stub() -> bool:
    """True while ``get_ticket_history`` is still withheld from the Gateway.

    Read from the deploy source rather than imported: the backend cannot import
    ``scripts/deploy`` at runtime, which is why the target map in
    ``services/agentcore_gateway.py`` is pinned by a test instead of shared.
    """
    try:
        source = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "deploy"
            / "gateway_tool_schemas.py"
        ).read_text(encoding="utf-8")
    except Exception:
        return True
    for node in ast.walk(ast.parse(source)):
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target == "WORKSHOP_DEFERRED_TOOLS" and node.value is not None:
            try:
                deferred = ast.literal_eval(
                    node.value.args[0] if isinstance(node.value, ast.Call) else node.value
                )
            except Exception:
                return True
            return "get_ticket_history" in set(deferred)
    return True


def _lab3_support_contract_is_workshop_stub() -> bool:
    """True while the Runtime still asks the Gateway for what it does not publish."""
    try:
        from services.agentcore_gateway import (
            SUPPORT_CALLER_BOUND_TOOLS,
            SUPPORT_MANAGED_TOOLS,
        )

        return "issue_credit" in SUPPORT_MANAGED_TOOLS or not SUPPORT_CALLER_BOUND_TOOLS
    except Exception:
        return True


def _configured(value: Any) -> bool:
    """True when an env/config value is present and non-empty."""
    return bool(str(value or "").strip())


def _gateway_identity_configured(settings: Any) -> bool:
    """True when the governed Gateway helper can mint a Cognito JWT."""
    return all([
        _configured(settings.cognito_pool_id_resolved),
        _configured(settings.COGNITO_CLIENT_ID),
        _configured(getattr(settings, "COGNITO_TEST_CREDENTIALS_SECRET_ARN", None)),
    ])


def _readiness_check(
    *,
    check_id: str,
    label: str,
    state: str,
    detail: str,
    required: bool = True,
    href: str | None = None,
) -> dict[str, Any]:
    """Small serializable readiness row used by Observatory and tests."""
    out: dict[str, Any] = {
        "id": check_id,
        "label": label,
        "state": state,
        "detail": detail,
        "required": required,
    }
    if href:
        out["href"] = href
    return out


async def _workshop_counts() -> dict[str, int] | None:
    """Return the live counts used by the readiness and proof panels.

    None means the database is unavailable. The caller decides whether
    that is a hard fail or a pending proof state.
    """
    try:
        from app import db_service
        if db_service is None:
            return None
        row = await db_service.fetch_one(
            """
            SELECT
              (SELECT count(*) FROM pellier.product_catalog)::int AS catalog_count,
              (SELECT count(*) FROM pellier.warehouse_inventory)::int AS warehouse_count,
              (SELECT count(*) FROM pellier.tool_audit)::int AS audit_count
            """
        )
        if not row:
            return None
        d = dict(row)
        return {
            "catalog_count": int(d.get("catalog_count") or 0),
            "warehouse_count": int(d.get("warehouse_count") or 0),
            "audit_count": int(d.get("audit_count") or 0),
        }
    except Exception as exc:
        logger.warning("Observatory readiness counts unavailable: %s", exc)
        return None


async def _latest_audit_row(
    *,
    principal_sub: str,
    tool: str | None = None,
    caller: str | None = None,
) -> dict[str, Any] | None:
    """Return the latest audit row visible to one verified principal."""
    if not principal_sub:
        return None
    clauses = ["(gr.principal_id = %s OR gtr.principal_sub = %s)"]
    params: list[Any] = [principal_sub, principal_sub]
    if tool:
        clauses.append("ta.tool = %s")
        params.append(tool)
    if caller:
        clauses.append("ta.caller = %s")
        params.append(caller)
    where = f"WHERE {' AND '.join(clauses)}"
    try:
        from app import db_service
        if db_service is None:
            return None
        row = await db_service.fetch_one(
            f"""
            SELECT ta.audit_id,
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
              {where}
             ORDER BY ta.audit_id DESC
             LIMIT 1
            """,
            *params,
        )
        if not row:
            return None
        d = dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as exc:
        logger.warning("Observatory latest audit row unavailable: %s", exc)
        return None


async def _audit_row_by_id(
    audit_id: int | None, *, principal_sub: str
) -> dict[str, Any] | None:
    """Return one audit row only when its receipt belongs to the principal."""
    if not audit_id or not principal_sub:
        return None
    try:
        from app import db_service
        if db_service is None:
            return None
        row = await db_service.fetch_one(
            """
            SELECT ta.audit_id,
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
             WHERE ta.audit_id = %s
               AND (gr.principal_id = %s OR gtr.principal_sub = %s)
             LIMIT 1
            """,
            int(audit_id),
            principal_sub,
            principal_sub,
        )
        if not row:
            return None
        d = dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as exc:
        logger.warning("Observatory audit row lookup unavailable: %s", exc)
        return None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _declared_idempotency_key(
    audit_row: dict[str, Any] | None,
    governed_args: Any,
) -> str | None:
    """The key a governed attempt declared, from its audit row or its receipt.

    Both sources are already principal-scoped, so a key taken from them never
    widens a lookup beyond the caller's own evidence.
    """
    audit_args = _json_object((audit_row or {}).get("args"))
    receipt_args = _json_object(governed_args)
    idempotency_key = (
        audit_args.get("idempotency_key")
        or audit_args.get("idempotencyKey")
        or receipt_args.get("idempotency_key")
        or receipt_args.get("idempotencyKey")
    )
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        return None
    return idempotency_key.strip()


# Absence, for one declared key, searched in the three places an execution
# leaves a trace. Same rule as scripts/build_receipt.py::_DENY_ABSENCE and
# scripts/prove_identity_boundary.py: absence is only ever claimed for a key
# that was actually searched for. Deliberately not run-scoped, so an execution
# of the key in another run still surfaces as the contradiction it is.
_DENY_ABSENCE_SQL = """
SELECT
    (SELECT count(*) FROM pellier.tool_audit
      WHERE args->>'idempotency_key' = %s)             AS execution_rows,
    (SELECT count(*) FROM pellier.write_operations
      WHERE idempotency_key = %s)                        AS write_rows,
    (SELECT count(*) FROM pellier.write_operations
      WHERE idempotency_key = %s
        AND completed_at IS NOT NULL)                   AS completed_writes,
    (SELECT count(*) FROM pellier.inventory_ledger
      WHERE idempotency_key = %s)                        AS ledger_rows
"""


async def _deny_absence_verdict(
    latest_governed: dict[str, Any] | None,
    governed_audit: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Whether a DENY receipt's declared key left no execution anywhere.

    A null ``audit_id`` on the DENY row is one signal from the row whose claim
    is under test, and a row cannot be its own alibi. Returns ``(verified,
    detail)``; ``verified`` is True only after every table an execution would
    have written came back empty for the declared key.
    """
    if not latest_governed or latest_governed.get("decision") != "DENY":
        return False, ""
    key = _declared_idempotency_key(
        governed_audit, latest_governed.get("args")
    )
    if key is None:
        return False, (
            "DENY receipt declares no idempotency key, so no execution "
            "table can be searched; a null audit_id alone is not absence."
        )
    try:
        from app import db_service

        if db_service is None:
            return False, "Absence search unavailable: no database service."
        row = await db_service.fetch_one(_DENY_ABSENCE_SQL, key, key, key, key)
    except Exception as exc:
        logger.debug("Observatory absence search unavailable: %s", exc)
        return False, "Absence search unavailable; absence is unverified."
    counts = {
        name: int((row or {}).get(name) or 0)
        for name in ("execution_rows", "write_rows", "completed_writes", "ledger_rows")
    }
    if any(counts.values()):
        return False, (
            f"Contradicted: key {key} was denied yet tool_audit has "
            f"{counts['execution_rows']} row(s), write_operations "
            f"{counts['write_rows']} ({counts['completed_writes']} completed), "
            f"inventory_ledger {counts['ledger_rows']}."
        )
    return True, (
        f"Keyed search for {key} found no row in tool_audit, "
        "write_operations, or inventory_ledger: the denied tool did not execute."
    )


async def _write_operation_for_execution(
    audit_row: dict[str, Any] | None,
    governed_args: Any,
) -> dict[str, Any] | None:
    """Resolve the idempotency ledger from principal-scoped execution data.

    ``write_operations`` has no principal column of its own. The lookup key is
    therefore accepted only from the already principal-scoped governed receipt
    or its linked audit row; this helper never searches the ledger broadly.
    """
    idempotency_key = _declared_idempotency_key(audit_row, governed_args)
    if idempotency_key is None:
        return None
    try:
        from app import db_service
        if db_service is None:
            return None
        row = await db_service.fetch_one(
            """
            SELECT idempotency_key,
                   operation,
                   request_hash,
                   created_at,
                   completed_at,
                   result
              FROM pellier.write_operations
             WHERE idempotency_key = %s
             LIMIT 1
            """,
            idempotency_key,
        )
        if not row:
            return None
        result = dict(row)
        for field in ("created_at", "completed_at"):
            value = result.get(field)
            if value is not None and hasattr(value, "isoformat"):
                result[field] = value.isoformat()
        return result
    except Exception as exc:
        logger.debug("Observatory write-operation lookup unavailable: %s", exc)
        return None


async def _latest_governed_receipt(
    *,
    principal_sub: str,
    tool: str | None = None,
    caller: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the latest managed policy receipt owned by one principal."""
    if not principal_sub:
        return None
    clauses = ["gr.principal_id = %s"]
    params: list[Any] = [principal_sub]
    if session_id:
        clauses.append("gr.session_id = %s")
        params.append(session_id)
    if tool:
        clauses.append("gr.tool = %s")
        params.append(tool)
    if caller:
        clauses.append("gr.caller = %s")
        params.append(caller)
    where = f"WHERE {' AND '.join(clauses)}"
    try:
        from app import db_service
        if db_service is None:
            return None
        row = await db_service.fetch_one(
            f"""
            SELECT receipt_id,
                   audit_id,
                   session_id,
                   principal_id,
                   principal_label,
                   tool,
                   caller,
                   decision,
                   args,
                   policy_engine_id,
                   policy_name,
                   token_fingerprint_sha256,
                   verified_subject,
                   verified_username,
                   issuer,
                   client_id,
                   identity_source,
                   created_at
              FROM pellier.governed_receipts gr
              {where}
             ORDER BY gr.receipt_id DESC
             LIMIT 1
            """,
            *params,
        )
        if not row:
            return None
        d = dict(row)
        if d.get("created_at") is not None:
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as exc:
        logger.debug("Observatory governed receipt unavailable: %s", exc)
        return None


def _empty_managed_receipt(session_id: str | None = None) -> dict[str, Any]:
    return {
        "present": False,
        "traceKind": "",
        "runtime": "",
        "rail": "",
        "jwtPassthrough": False,
        "gatewayPassthrough": False,
        "traceId": None,
        "runtimeRequestId": None,
        "sessionId": session_id,
        "managedTrace": {},
        "evidenceProvenance": "",
        # Kept in step with the populated shape below: a field present in one
        # and absent in the other makes the frontend read `undefined` on
        # exactly the path where no receipt exists.
        "buildFingerprint": "",
        "localBuildFingerprint": "",
        "buildState": "unknown",
    }


def _latest_managed_receipt(
    session_id: str | None = None,
    *,
    principal_sub: str,
) -> dict[str, Any]:
    """Return a managed Runtime receipt only from the caller's cache scope."""
    if not session_id or not principal_sub:
        return _empty_managed_receipt(session_id)
    try:
        from services.agentcore_runtime import get_latest_trace

        trace = get_latest_trace(session_id, principal_sub=principal_sub)
    except Exception as exc:
        logger.debug("Managed receipt unavailable: %s", exc)
        return _empty_managed_receipt(session_id)
    return {
        "present": trace.get("traceKind") == "managed-runtime-receipt",
        "traceKind": trace.get("traceKind", ""),
        "runtime": trace.get("runtime", ""),
        "rail": trace.get("rail", ""),
        "jwtPassthrough": bool(trace.get("jwtPassthrough")),
        "gatewayPassthrough": bool(trace.get("gatewayPassthrough")),
        "traceId": trace.get("traceId"),
        "runtimeRequestId": trace.get("runtimeRequestId"),
        "sessionId": trace.get("sessionId") or session_id,
        "managedTrace": (
            trace.get("managedTrace")
            if isinstance(trace.get("managedTrace"), dict)
            else {}
        ),
        "evidenceProvenance": trace.get("evidenceProvenance", ""),
        # This projection is a whitelist: a field added to the trace dict does
        # not reach the frontend unless it is named here.
        "buildFingerprint": trace.get("buildFingerprint", ""),
        "localBuildFingerprint": trace.get("localBuildFingerprint", ""),
        "buildState": trace.get("buildState", "unknown"),
    }


def _build_fingerprint_evidence(receipt: dict[str, Any]) -> str:
    """Describe which revision the managed Runtime executed.

    Three outcomes, because two would misreport the third. A runtime deployed
    before the fingerprint mechanism existed reports nothing, and that is not
    the same finding as a stale deployment.
    """
    state = str(receipt.get("buildState") or "unknown")
    deployed = str(receipt.get("buildFingerprint") or "")
    local = str(receipt.get("localBuildFingerprint") or "")
    if state == "current":
        return (
            f"Runtime executed this checkout's revision (build {deployed[:12]})"  # copy-allow: observatory-evidence-line
        )
    if state == "stale":
        return (
            f"Runtime executed build {deployed[:12]}, but this checkout is "  # copy-allow: observatory-evidence-line
            f"{local[:12]}. The deployed package is not your current source."  # copy-allow: observatory-evidence-line
        )
    if not deployed:
        return (
            "Runtime did not report a build fingerprint. Re-render and deploy "  # copy-allow: observatory-evidence-line
            "the project to stamp one; until then the executed revision is "  # copy-allow: observatory-evidence-line
            "unproven, which is not the same as stale."  # copy-allow: observatory-evidence-line
        )
    return "Build fingerprint could not be compared against this checkout."  # copy-allow: observatory-evidence-line


async def _collect_readiness() -> dict[str, Any]:
    """Collect cheap workshop readiness checks without calling Bedrock."""
    from config import settings

    counts = await _workshop_counts()
    checks: list[dict[str, Any]] = []
    governed_format = str(settings.WORKSHOP_FORMAT).lower() == "governed"

    def managed_state(configured: bool) -> str:
        if configured:
            return "pass"
        return "fail" if governed_format else "warn"

    # The flag that GRADES every other governed check has to be checked itself.
    #
    # Found live on 2026-08-27: `WORKSHOP_FORMAT` absent from a backend `.env` made
    # `Settings` default to `builders`, `requires_managed_rail()` returned False, and a
    # real shopper turn executed `initiate_return` in process — no human review, no
    # Cedar verdict, no `tool_audit` receipt. Readiness reported nothing, because it
    # trusted the flag and merely downgraded the other checks from `fail` to `warn`.
    #
    # The deployment SHAPE is detectable independently of the flag: a governed box has
    # a Gateway and a policy engine configured. When those are present and the format
    # is not governed, that is a misconfiguration, not a supported local mode.
    from services.execution_rail import requires_managed_rail

    managed_required = requires_managed_rail("initiate_return")
    governed_shaped = bool(
        str(getattr(settings, "AGENTCORE_GATEWAY_ARN", "") or "").strip()
        and str(getattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "") or "").strip()
    )
    effective_format = str(settings.WORKSHOP_FORMAT or "<unset>")
    if governed_format and managed_required:
        rail_state = "pass"
        rail_detail = (
            f"WORKSHOP_FORMAT={effective_format}. Governed writes are managed-rail "
            "only: initiate_return, issue_credit and restock_inventory cannot run in "
            "process."
        )
    elif governed_format and not managed_required:
        rail_state = "fail"
        rail_detail = (
            f"WORKSHOP_FORMAT={effective_format} but requires_managed_rail() is False. "
            "Configuration and code disagree; governed writes would run unguarded."
        )
    elif governed_shaped:
        rail_state = "fail"
        rail_detail = (
            f"WORKSHOP_FORMAT={effective_format}, but this deployment has a Gateway "
            "and a policy engine configured. Governed writes would execute in process "
            "with no human review, no AgentCore Policy verdict and no tool_audit "
            "receipt. Set WORKSHOP_FORMAT=governed."
        )
    else:
        rail_state = "warn"
        rail_detail = (
            f"WORKSHOP_FORMAT={effective_format}. In-process writes are the supported "
            "behaviour for this lineage; the managed rail is not required."
        )
    checks.append(_readiness_check(
        check_id="managed_rail",
        label="Managed write rail",
        state=rail_state,
        detail=rail_detail,
        required=governed_format or governed_shaped,
    ))

    if counts is None:
        checks.append(_readiness_check(
            check_id="aurora",
            label="Aurora PostgreSQL",
            state="fail",
            detail="Database unavailable to the backend.",  # copy-allow: observatory-readiness-detail
            href="/observatory/search",
        ))
    else:
        catalog_count = counts["catalog_count"]
        warehouse_count = counts["warehouse_count"]
        audit_count = counts["audit_count"]
        warehouse_ready = (
            warehouse_count == 180 if governed_format else warehouse_count > 0
        )
        checks.append(_readiness_check(
            check_id="aurora",
            label="Aurora PostgreSQL",
            state="pass" if catalog_count >= 60 and warehouse_ready else "fail",
            detail=(
                f"Catalog {catalog_count} products, warehouse "
                f"{warehouse_count} rows"
                f"{' (expected exactly 180)' if governed_format else ''}, "
                f"audit ledger {audit_count} rows."
            ),
            href="/observatory/search",
        ))

    cognito_ready = _gateway_identity_configured(settings)
    checks.append(_readiness_check(
        check_id="identity",
        label="Cognito identity",
        state=managed_state(cognito_ready),
        detail=(
            "User pool, app client, and test credential secret configured for JWT passthrough."  # copy-allow: observatory-readiness-detail
            if cognito_ready
            else "Missing Cognito pool/client/test credential secret; Gateway JWT proof cannot run."
        ),
        required=governed_format,
        href="/observatory/production-patterns",
    ))

    memory_configured = _configured(settings.AGENTCORE_MEMORY_ID)
    checks.append(_readiness_check(
        check_id="memory",
        label="AgentCore Memory",
        state=managed_state(memory_configured),
        detail=(
            "AGENTCORE_MEMORY_ID set for working and semantic memory."
            if memory_configured
            else "AGENTCORE_MEMORY_ID empty; working and semantic memory cannot show managed records."
        ),
        required=governed_format,
        href="/observatory/memory",
    ))

    runtime_configured = _configured(settings.AGENTCORE_RUNTIME_ENDPOINT)
    checks.append(_readiness_check(
        check_id="runtime",
        label="AgentCore Runtime",
        state=managed_state(runtime_configured),
        detail=(
            "Runtime endpoint configured; chat can use the managed rail when USE_AGENTCORE_RUNTIME=true."
            if runtime_configured
            else "AGENTCORE_RUNTIME_ENDPOINT empty; managed runtime invoke cannot be demonstrated."
        ),
        required=governed_format,
        href="/observatory/proof-board#managed-rail",
    ))

    gateway_configured = _configured(settings.AGENTCORE_GATEWAY_URL)
    checks.append(_readiness_check(
        check_id="gateway",
        label="AgentCore Gateway",
        state=managed_state(gateway_configured),
        detail=(
            "Gateway URL configured; MCP tool calls can receive the caller JWT."
            if gateway_configured
            else "AGENTCORE_GATEWAY_URL empty; Gateway/JWT tool calls cannot run."
        ),
        required=governed_format,
        href="/observatory/proof-board#managed-rail",
    ))

    policy_engine_id = getattr(settings, "AGENTCORE_POLICY_ENGINE_ID", None)
    policy_configured = _configured(policy_engine_id)
    checks.append(_readiness_check(
        check_id="policy",
        label="AgentCore Policy",
        state=managed_state(policy_configured),
        detail=(
            "Managed Cedar policy engine configured for Gateway enforcement."  # copy-allow: observatory-readiness-detail
            if policy_configured
            else "Policy engine id empty; live Gateway ALLOW/DENY enforcement cannot run."
        ),
        required=governed_format,
        href="/observatory/write-path",
    ))

    model_ids = {
        "opus": settings.BEDROCK_OPUS_MODEL,
        "sonnet": settings.BEDROCK_SONNET_MODEL,
        "router": settings.BEDROCK_ROUTER_MODEL,
        "reporting": settings.BEDROCK_REPORTING_MODEL,
        "fast": settings.BEDROCK_FAST_MODEL,
        "embedding": settings.BEDROCK_EMBEDDING_MODEL,
        "rerank": settings.BEDROCK_RERANK_MODEL,
    }
    model_ready = all(_configured(v) for v in model_ids.values())
    checks.append(_readiness_check(
        check_id="models",
        label="Bedrock models",
        state="pass" if model_ready else "fail",
        detail=(
            "Opus, Sonnet, Haiku, Cohere Embed, and Cohere Rerank model ids are configured."  # copy-allow: observatory-readiness-detail
            if model_ready
            else "One or more model ids are empty; run the model-access preflight."
        ),
        href="/observatory/settings",
    ))

    # The evidence substrate. Added after a live run found the Observatory unable to
    # reconstruct a single operator-rail execution, and the cluster still carrying a
    # database object under a name the contract retired. Both were invisible to
    # readiness, so both shipped.
    substrate = await _evidence_substrate_state()
    checks.append(_readiness_check(
        check_id="evidence_substrate",
        label="Evidence substrate",
        state=substrate["state"],
        detail=substrate["detail"],
        href="/observatory/proof-board",
    ))

    blocking = [c for c in checks if c["required"] and c["state"] == "fail"]
    warnings = [c for c in checks if c["state"] == "warn"]
    status = "ready" if not blocking and not warnings else "attention"
    if blocking:
        status = "not_ready"

    return {
        "status": status,
        "checks": checks,
        "counts": counts or {},
        "models": model_ids,
    }


async def _evidence_substrate_state() -> dict[str, str]:
    """Whether the tables an evidence reconstruction depends on are present and canonical.

    Four conditions, and each one shipped broken at least once:

      * `pellier.execution_receipts` — without it a Cedar DENY is provable only from an
        HTTP response body, and the ReviewRecord reports `policy: PENDING` for an action
        that was refused.
      * `pellier.operator_episodes` with its outcome index — without migration 026's
        index the writer raises a duplicate-key error on 024's index and the best-effort
        handler swallows it, so executions succeed and remember nothing.
      * `pellier.observatory_spans` present — the reserved, retention-bounded
        Aurora span cache. CloudWatch/AgentCore telemetry remains the managed
        span authority; durable proof comes from receipt tables.
      * `pellier.model_invocation_receipts` and
        `pellier.evidence_ledger_event_refs` — metadata-only model receipts and
        the typed projection index introduced by migration 043.
      * `pellier.agent_trace_spans` ABSENT — the repository contract retires that name
        for every database object, and this cluster carried it for weeks.

    An unreadable database is `warn`, not `fail`: a local clone with no cluster is a
    legitimate state, and reporting it as a release blocker trains people to ignore the
    panel.
    """
    try:
        from app import db_service
        if db_service is None:
            return {"state": "warn",
                    "detail": "No database connection, so the evidence tables could not be checked."}  # copy-allow: observatory-readiness-detail
        rows = await db_service.fetch_all(
            """
            SELECT table_name FROM information_schema.tables
             WHERE table_schema = 'pellier'
               AND table_name IN ('execution_receipts', 'operator_episodes',
                                  'observatory_spans', 'agent_trace_spans',
                                  'model_invocation_receipts',
                                  'evidence_ledger_event_refs')
            """
        )
        present = {str(r["table_name"]) for r in (rows or [])}
        index_rows = await db_service.fetch_all(
            """
            SELECT indexname FROM pg_indexes
             WHERE schemaname = 'pellier'
               AND indexname = 'operator_episodes_outcome_idx'
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("evidence substrate check unavailable: %s", exc)
        return {"state": "warn",
                "detail": "The evidence tables could not be read."}  # copy-allow: observatory-readiness-detail

    problems: list[str] = []
    for table in (
        "execution_receipts",
        "operator_episodes",
        "observatory_spans",
        "model_invocation_receipts",
        "evidence_ledger_event_refs",
    ):
        if table not in present:
            problems.append(f"pellier.{table} is missing")
    if "agent_trace_spans" in present:
        problems.append(
            "pellier.agent_trace_spans still exists; run migration 027"
        )
    if "operator_episodes" in present and not index_rows:
        problems.append(
            "operator_episodes_outcome_idx is missing; run migration 026, or every "
            "governed execution will fail to record its episode"
        )
    if problems:
        return {"state": "fail", "detail": ". ".join(problems) + "."}
    return {
        "state": "pass",
        "detail": (
            "Execution receipts, episodic memory, the typed ledger projection, "  # copy-allow: observatory-readiness-detail
            "redacted model receipts, and the reserved span cache are present; "
            "the retired trace object is gone."
        ),
    }


def _card_status(condition: bool, fallback: str = "pending") -> str:
    return "complete" if condition else fallback


async def _collect_proof_board(
    session_id: str | None = None, *, principal_sub: str
) -> dict[str, Any]:
    """Build the Observatory proof-card payload.

    The Proof Board is deliberately a read model. It reports evidence
    from source files, env/config, recent traces, and ``tool_audit``.
    It never calls Bedrock, Gateway, or the Runtime.
    """
    from config import settings

    readiness = await _collect_readiness()
    counts = readiness.get("counts") or {}
    governed_format = str(settings.WORKSHOP_FORMAT).lower() == "governed"
    check_inventory_wired = not _check_inventory_is_workshop_stub()
    latest_check_inventory = await _latest_audit_row(
        principal_sub=principal_sub, tool="check_inventory"
    )
    latest_initiate_return = await _latest_audit_row(
        principal_sub=principal_sub, tool="initiate_return"
    )
    latest_audit = await _latest_audit_row(principal_sub=principal_sub)
    latest_gateway = await _latest_audit_row(
        principal_sub=principal_sub, caller="gateway"
    )
    latest_governed = (
        await _latest_governed_receipt(
            principal_sub=principal_sub,
            caller="gateway",
            session_id=session_id,
        )
        if session_id
        else None
    )
    if not latest_governed:
        latest_governed = await _latest_governed_receipt(
            principal_sub=principal_sub, caller="gateway"
        )
    governed_audit = await _audit_row_by_id(
        latest_governed.get("audit_id") if latest_governed else None,
        principal_sub=principal_sub,
    )
    write_operation = await _write_operation_for_execution(
        governed_audit,
        latest_governed.get("args") if latest_governed else {},
    )
    managed_receipt = _latest_managed_receipt(
        session_id, principal_sub=principal_sub
    )
    policy_engine_id = getattr(settings, "AGENTCORE_POLICY_ENGINE_ID", None)

    runtime_configured = _configured(settings.AGENTCORE_RUNTIME_ENDPOINT)
    gateway_configured = _configured(settings.AGENTCORE_GATEWAY_URL)
    policy_configured = _configured(policy_engine_id)
    identity_configured = _gateway_identity_configured(settings)
    managed_rail_proven = all([
        managed_receipt.get("present"),
        managed_receipt.get("runtime") == "agentcore-managed",
        managed_receipt.get("rail") == "gateway-mcp",
        managed_receipt.get("jwtPassthrough"),
        managed_receipt.get("gatewayPassthrough"),
    ])
    governed_decision = latest_governed.get("decision") if latest_governed else ""
    governed_audit_present = bool(governed_audit)
    governed_absence_verified, absence_check_detail = await _deny_absence_verdict(
        latest_governed, governed_audit
    )
    managed_receipt.update({
        "policyConfigured": policy_configured,
        "gatewayAuditPresent": governed_audit_present if latest_governed else bool(latest_gateway),
        "gatewayAuditAbsenceVerified": governed_absence_verified,
        "latestGatewayAuditId": (
            governed_audit.get("audit_id")
            if governed_audit
            else latest_gateway.get("audit_id") if latest_gateway and not latest_governed else None
        ),
        "latestGatewayAuditAt": (
            governed_audit.get("created_at")
            if governed_audit
            else latest_gateway.get("created_at") if latest_gateway and not latest_governed else ""
        ),
        "governedReceiptPresent": bool(latest_governed),
        "latestGovernedReceiptId": latest_governed.get("receipt_id") if latest_governed else None,
        "latestGovernedReceiptAt": latest_governed.get("created_at") if latest_governed else "",
        "governedAuditId": latest_governed.get("audit_id") if latest_governed else None,
        "governedPrincipalId": latest_governed.get("principal_id") if latest_governed else "",
        "governedPrincipalLabel": latest_governed.get("principal_label") if latest_governed else "",
        "governedVerifiedSubject": latest_governed.get("verified_subject") if latest_governed else "",
        "governedVerifiedUsername": latest_governed.get("verified_username") if latest_governed else "",
        "governedIdentitySource": latest_governed.get("identity_source") if latest_governed else "",
        "governedTokenFingerprint": latest_governed.get("token_fingerprint_sha256") if latest_governed else "",
        "governedDecision": governed_decision,
        "governedTool": latest_governed.get("tool") if latest_governed else "",
        "governedPolicyName": latest_governed.get("policy_name") if latest_governed else "",
        "governedArgs": latest_governed.get("args") if latest_governed else {},
        "writeOperationPresent": bool(write_operation),
        "writeOperationKey": (
            write_operation.get("idempotency_key") if write_operation else ""
        ),
        "writeOperationName": (
            write_operation.get("operation") if write_operation else ""
        ),
        "writeOperationCompletedAt": (
            write_operation.get("completed_at") if write_operation else None
        ),
        "absenceCheckDetail": absence_check_detail,
    })

    cards = [
        {
            "id": "marco-floor-check",
            "lab": "Lab 1: Build a PostgreSQL-Grounded Agent",
            "group": "Agent and tool evidence",
            "title": "Wire Marco to check_inventory",
            "status": _card_status(check_inventory_wired and bool(latest_check_inventory), "needs_run" if check_inventory_wired else "needs_build"),
            "required": True,
            "surface": "Code Editor + Pellier",
            "summary": "The Inventory Agent tool is wired and Marco's warehouse turn leaves a check_inventory audit row.",
            "evidenceSource": "services.agent_tools.check_inventory + pellier.tool_audit",
            "lastUpdated": latest_check_inventory.get("created_at") if latest_check_inventory else None,
            "evidence": [
                "check_inventory source no longer returns the workshop stub" if check_inventory_wired else "check_inventory still looks like the workshop stub",
                (
                    f"Latest check_inventory row: audit_id {latest_check_inventory.get('audit_id')}"
                    if latest_check_inventory
                    else "No check_inventory row found yet"
                ),
            ],
            "fallback": {
                "label": "PostgreSQL proof",
                "command": (
                    "psql -X -v ON_ERROR_STOP=1 -P pager=off -c \""
                    "SELECT audit_id, session_id, caller, args, latency_ms "
                    "FROM pellier.tool_audit WHERE tool = 'check_inventory' "
                    "ORDER BY audit_id DESC LIMIT 3;\""
                ),
            },
            "links": [
                {"label": "Tools", "to": "/observatory/tools"},
                {"label": "Sessions", "to": "/observatory/sessions"},
            ],
        },
        {
            "id": "retrieval-comparison",
            "lab": "Lab 2: Build and Measure PostgreSQL Hybrid Retrieval",
            "group": "Retrieval evidence",
            "title": "Reconstruct Anna's hybrid retrieval receipt",
            "status": (
                "available"
                if int(counts.get("catalog_count") or 0) >= 60
                else "needs_data"
            ),
            "required": True,
            "surface": "Pellier + Code Editor",
            "summary": "The durable receipt exposes vector and lexical ranks, RRF, rerank, typed constraints, latency, and modeled cost for PostgreSQL reconstruction.",
            "evidenceSource": "pellier.retrieval_receipts + pellier.product_catalog",
            "evidence": [
                f"Catalog rows: {counts.get('catalog_count', 0)}",
                f"Embedding model: {settings.BEDROCK_EMBEDDING_MODEL}",
                f"Rerank model: {settings.BEDROCK_RERANK_MODEL}",
            ],
            "fallback": {
                "label": "PostgreSQL proof",
                "command": (
                    "psql -X -v ON_ERROR_STOP=1 -P pager=off -c \""
                    "SELECT receipt_id, hard_constraints, retrieval_config, "
                    "latency_breakdown, modeled_cost_usd "
                    "FROM pellier.retrieval_receipts "
                    "ORDER BY receipt_id DESC LIMIT 1;\""
                ),
            },
            "links": [
                {"label": "Retrieval comparison", "to": "/observatory/performance"},
                {"label": "Search pipeline", "to": "/observatory/search"},
            ],
        },
        {
            "id": "audit-ledger",
            "lab": "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore",
            "group": "Operational evidence",
            "title": "Prove the tool_audit ledger",
            "status": (
                "complete"
                if latest_initiate_return and latest_governed
                else "needs_run" if not latest_initiate_return
                else "needs_data"
            ),
            "required": True,
            "surface": "Aurora SQL",
            "summary": "Theo's executed return and the seeded principal-versus-customer mismatch are reconstructible without depending on a UI panel.",
            "evidenceSource": "pellier.tool_audit + pellier.governed_receipts",
            "lastUpdated": (
                latest_initiate_return.get("created_at")
                if latest_initiate_return
                else latest_audit.get("created_at") if latest_audit else None
            ),
            "evidence": [
                (
                    f"Latest initiate_return row: audit_id {latest_initiate_return.get('audit_id')}"
                    if latest_initiate_return
                    else "No initiate_return row found yet"
                ),
                (
                    f"Latest audit row: {latest_audit.get('tool')} by {latest_audit.get('caller')}"
                    if latest_audit
                    else "No audit rows found yet"
                ),
                (
                    f"Latest governed receipt: {latest_governed.get('principal_label')} -> {latest_governed.get('decision')}"
                    if latest_governed
                    else "No governed identity receipt found yet"
                ),
            ],
            "fallback": {
                "label": "SQL fallback",
                "command": (
                    "psql -X -v ON_ERROR_STOP=1 -P pager=off -c \"SELECT audit_id, session_id, tool, caller, args, result "
                    "FROM pellier.tool_audit WHERE tool = 'initiate_return' ORDER BY audit_id DESC LIMIT 3;\""
                ),
            },
            "links": [
                {"label": "Write-path", "to": "/observatory/write-path"},
            ],
        },
        {
            "id": "runtime-gateway-policy",
            "lab": "Lab 4: Build Governed Agent Actions with Cedar",
            "group": "Managed boundaries",
            "title": "Inspect the Gateway and Cedar boundary",
            "status": (
                "available"
                if (
                    runtime_configured
                    and gateway_configured
                    and identity_configured
                    and policy_configured
                )
                else "needs_config"
            ),
            "required": governed_format,
            "surface": "Managed governance",
            "summary": "Runtime receives the caller JWT, Gateway discovers tools, and Policy defines the Cedar boundary.",
            "evidenceSource": "pellier/backend/.env + managed policy config",
            "evidence": [
                "Runtime endpoint configured" if runtime_configured else "Runtime endpoint missing",
                "Gateway URL configured" if gateway_configured else "Gateway URL missing",
                "Cognito configured" if identity_configured else "Cognito config incomplete",
                "Policy engine configured" if policy_configured else "Policy engine not configured",
            ],
            "fallback": {
                "label": "AgentCore validation",
                "command": "cd .agentcore-project/pellier && npx -y @aws/agentcore@0.29.0 validate --json",
            },
            "links": [
                {"label": "Write-path", "to": "/observatory/write-path"},
            ],
        },
        {
            "id": "managed-rail",
            "lab": "Lab 3: Deploy and Operate Agents with Amazon Bedrock AgentCore",
            "group": "Managed boundaries",
            "title": "Prove the managed Runtime and Gateway rail",
            "status": _card_status(
                managed_rail_proven,
                (
                    "needs_run"
                    if runtime_configured and gateway_configured and identity_configured
                    else "needs_config"
                ),
            ),
            "required": governed_format,
            "surface": "Runtime receipt",
            "summary": "After the cross-turn Memory exercise, a managed Runtime turn must preserve the caller JWT and execute through Gateway/MCP.",
            "evidenceSource": "AgentCore Memory timeline + Runtime trace + pellier.tool_audit caller=gateway",
            "lastUpdated": latest_gateway.get("created_at") if latest_gateway else None,
            "evidence": [
                (
                    "AgentCore Memory configured for authenticated session history"
                    if _configured(settings.AGENTCORE_MEMORY_ID)
                    else "AgentCore Memory configuration missing"
                ),
                (
                    f"Managed receipt rail: {managed_receipt.get('rail')}"
                    if managed_receipt.get("present")
                    else "No managed Runtime receipt yet"
                ),
                f"JWT passthrough: {managed_receipt.get('jwtPassthrough')}",
                f"Gateway passthrough: {managed_receipt.get('gatewayPassthrough')}",
                (
                    f"Managed trace id: {managed_receipt.get('traceId')}"
                    if managed_receipt.get("traceId")
                    else "Managed trace id was not reported on the Runtime response"
                ),
                # Deliberately an evidence line, not an input to
                # managed_rail_proven. "The rail works" and "the rail ran the
                # revision I packaged" are two claims; collapsing them would
                # let a stale deployment pass as a proven rail, which is the
                # exact substitution this workshop teaches against.
                _build_fingerprint_evidence(managed_receipt),
                (
                    f"Latest gateway audit row: audit_id {latest_gateway.get('audit_id')}"
                    if latest_gateway
                    else "No caller='gateway' audit row found yet"
                ),
                (
                    f"Latest governed receipt: {latest_governed.get('principal_label')} -> {latest_governed.get('decision')}"
                    if latest_governed
                    else "No governed identity/policy receipt found yet"
                ),
            ],
            "fallback": {
                "label": "AgentCore Runtime proof",
                "command": (
                    "cd .agentcore-project/pellier && "
                    "npx -y @aws/agentcore@0.29.0 invoke "
                    "--runtime pellier_orchestrator "
                    "--session-id \"$RUNTIME_SESSION\" "
                    "--bearer-token \"$PELLIER_TOKEN\" "
                    "--prompt \"Check floor inventory for BK-01\" --json"
                ),
            },
            "links": [
                {"label": "Memory", "to": "/observatory/memory"},
                {"label": "Proof Board", "to": "/observatory/proof-board#managed-rail"},
                {"label": "Sessions", "to": "/observatory/sessions"},
            ],
        },
    ]

    card_order = {
        "marco-floor-check": 1,
        "retrieval-comparison": 2,
        "managed-rail": 3,
        "audit-ledger": 4,
        "runtime-gateway-policy": 5,
    }
    cards.sort(key=lambda card: card_order.get(card["id"], 99))

    return {
        "status": readiness["status"],
        "readiness": readiness,
        "managedReceipt": managed_receipt,
        "cards": cards,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _audit_result_status(result: Any) -> str:
    """An audit proves invocation; only an explicit outcome proves success."""
    if not isinstance(result, dict):
        return "unavailable"
    status = str(result.get("status") or "").lower()
    if result.get("error") or result.get("success") is False or status in {"failed", "error"}:
        return "failed"
    if status in {"denied", "forbidden", "denied-before-execution"}:
        return "denied"
    if result.get("success") is True or status in {"succeeded", "success", "complete", "completed"}:
        return "succeeded"
    return "unavailable"


@router.get("/sessions")
async def list_sessions(
    persona: Optional[str] = Query(default=None, description="Filter by persona ID"),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Return sessions evidenced by the live Aurora tool ledger."""
    db = await _live_db()
    try:
        rows = await db.fetch_all(
            """
            SELECT
                ta.session_id AS id,
                COALESCE(ss.persona_id, 'anonymous') AS "personaId",
                (
                    SELECT COALESCE(
                        NULLIF(first_audit.args->>'query', ''),
                        NULLIF(first_audit.args->>'message', ''),
                        first_audit.tool
                    )
                      FROM pellier.tool_audit first_audit
                     WHERE first_audit.session_id = ta.session_id
                     ORDER BY first_audit.created_at ASC, first_audit.audit_id ASC
                     LIMIT 1
                ) AS "openingQuery",
                GREATEST(
                    0,
                    floor(extract(epoch FROM max(ta.created_at) - min(ta.created_at)) * 1000)
                )::integer AS "elapsedMs",
                count(DISTINCT ta.caller)::integer AS "agentCount",
                CASE
                    WHEN bool_or(ta.caller = 'gateway') THEN 'Managed Gateway'
                    ELSE 'Storefront Dispatcher'
                END AS "routingPattern",
                max(ta.created_at) AS timestamp,
                CASE WHEN bool_or(
                    ta.result->>'success' = 'false'
                    OR NULLIF(ta.result->>'error', '') IS NOT NULL
                    OR ta.result->>'status' IN ('failed', 'error', 'denied')
                ) THEN 'failed'
                ELSE COALESCE((
                    SELECT terminal_status FROM pellier.governed_turn_receipts terminal
                     WHERE terminal.session_id = ta.session_id
                     ORDER BY terminal.created_at DESC, terminal.turn_id DESC LIMIT 1
                ), 'unknown') END AS status
              FROM pellier.tool_audit ta
              LEFT JOIN pellier.shopper_sessions ss ON ss.session_id = ta.session_id
             -- Both placeholders carry an explicit ::text cast. An uncast
             -- placeholder compared against NULL gives Postgres nothing to
             -- infer a type from, and the statement fails to plan with
             -- "could not determine data type of parameter $1". That is the
             -- default listing path (persona is None), so /sessions answered
             -- 503 for every unfiltered request. Keep literal placeholder
             -- tokens out of these comments: psycopg counts them.
             WHERE (%s::text IS NULL OR ss.persona_id = %s::text)
               AND (
                   (%s::text IS NULL AND NOT EXISTS (
                       SELECT 1 FROM pellier.governed_turn_receipts claim
                        WHERE claim.session_id = ta.session_id
                          AND COALESCE(claim.principal_sub, '') <> ''
                   ) AND NOT EXISTS (
                       SELECT 1 FROM pellier.governed_receipts claim
                        WHERE claim.session_id = ta.session_id
                   ))
                   OR (%s::text IS NOT NULL AND EXISTS (
                       SELECT 1 FROM pellier.governed_turn_receipts own
                        WHERE own.session_id = ta.session_id AND own.principal_sub = %s
                   ) AND NOT EXISTS (
                       SELECT 1 FROM pellier.governed_turn_receipts foreign_turn
                        WHERE foreign_turn.session_id = ta.session_id
                          AND foreign_turn.principal_sub IS NOT NULL
                          AND foreign_turn.principal_sub <> %s
                   ) AND NOT EXISTS (
                       SELECT 1 FROM pellier.governed_receipts foreign_decision
                        WHERE foreign_decision.session_id = ta.session_id
                          AND foreign_decision.principal_id IS DISTINCT FROM %s
                   ))
               )
             GROUP BY ta.session_id, ss.persona_id
             ORDER BY max(ta.created_at) DESC
             LIMIT 100
            """,
            persona,
            persona,
            (user or {}).get("sub"),
            (user or {}).get("sub"),
            (user or {}).get("sub"),
            (user or {}).get("sub"),
            (user or {}).get("sub"),
        )
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.exception("Failed to read Aurora sessions")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["SESSION_EVIDENCE_UNAVAILABLE"],
        ) from exc


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Build a replay from durable message and audit rows."""
    db = await _live_db()
    try:
        rows = await db.fetch_all(
            """
            SELECT
                ta.session_id AS id,
                COALESCE(ss.persona_id, 'anonymous') AS "personaId",
                (
                    SELECT COALESCE(
                        NULLIF(first_audit.args->>'query', ''),
                        NULLIF(first_audit.args->>'message', ''),
                        first_audit.tool
                    )
                      FROM pellier.tool_audit first_audit
                     WHERE first_audit.session_id = ta.session_id
                     ORDER BY first_audit.created_at ASC, first_audit.audit_id ASC
                     LIMIT 1
                ) AS "openingQuery",
                GREATEST(
                    0,
                    floor(extract(epoch FROM max(ta.created_at) - min(ta.created_at)) * 1000)
                )::integer AS "elapsedMs",
                count(DISTINCT ta.caller)::integer AS "agentCount",
                CASE
                    WHEN bool_or(ta.caller = 'gateway') THEN 'Managed Gateway'
                    ELSE 'Storefront Dispatcher'
                END AS "routingPattern",
                max(ta.created_at) AS timestamp,
                CASE WHEN bool_or(
                    ta.result->>'success' = 'false'
                    OR NULLIF(ta.result->>'error', '') IS NOT NULL
                    OR ta.result->>'status' IN ('failed', 'error', 'denied')
                ) THEN 'failed'
                ELSE COALESCE((
                    SELECT terminal_status FROM pellier.governed_turn_receipts terminal
                     WHERE terminal.session_id = ta.session_id
                     ORDER BY terminal.created_at DESC, terminal.turn_id DESC LIMIT 1
                ), 'unknown') END AS status
              FROM pellier.tool_audit ta
              LEFT JOIN pellier.shopper_sessions ss ON ss.session_id = ta.session_id
             WHERE ta.session_id = %s
             GROUP BY ta.session_id, ss.persona_id
            """,
            session_id,
        )
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=OBSERVATORY_COPY["SESSION_EVIDENCE_NOT_FOUND"],
            )
        summary = dict(rows[0])
        principal_sub = str((user or {}).get("sub") or "")
        # A replay carries the shopper's own words, the arguments every tool
        # was called with, and the ledger. Both branches below answer the same
        # question -- is this session the caller's, and only the caller's --
        # and the second branch used to be missing entirely, so a signed-out
        # reader could open any named shopper's turn by guessing a session id
        # while a signed-in one could not. Anonymous means anonymous: a session
        # is visible without a token only while no identified principal has
        # ever taken a turn in it.
        if principal_sub:
            visible = await db.fetch_one(
                """
                SELECT 1 AS visible
                  FROM pellier.governed_turn_receipts
                 WHERE session_id = %s
                   AND principal_sub = %s
                   AND NOT EXISTS (
                       SELECT 1
                         FROM pellier.governed_turn_receipts foreign_turn
                        WHERE foreign_turn.session_id = %s
                          AND foreign_turn.principal_sub IS NOT NULL
                          AND foreign_turn.principal_sub <> %s
                   )
                 LIMIT 1
                """,
                session_id,
                principal_sub,
                session_id,
                principal_sub,
            )
            if not visible:
                raise HTTPException(
                    status_code=404,
                    detail=OBSERVATORY_COPY["SESSION_EVIDENCE_NOT_FOUND"],
                )
        else:
            # `fetch_one` returning nothing is the visible case here, which
            # inverts the branch above: the query looks for a reason to
            # refuse. A session with no receipts at all is a genuinely
            # anonymous storefront session and stays readable, which is what
            # keeps the Observatory usable before anybody signs in.
            claimed = await db.fetch_one(
                """
                SELECT 1 AS claimed
                  FROM pellier.governed_turn_receipts
                 WHERE session_id = %s
                   AND COALESCE(principal_sub, '') <> ''
                 LIMIT 1
                """,
                session_id,
            )
            if claimed:
                raise HTTPException(
                    status_code=404,
                    detail=OBSERVATORY_COPY["SESSION_EVIDENCE_NOT_FOUND"],
                )
        foreign_decision = await db.fetch_one(
            """
            SELECT 1 FROM pellier.governed_receipts
             WHERE session_id = %s AND principal_id IS DISTINCT FROM %s
             LIMIT 1
            """,
            session_id, principal_sub or None,
        )
        if foreign_decision:
            raise HTTPException(status_code=404, detail=OBSERVATORY_COPY["SESSION_EVIDENCE_NOT_FOUND"])
        messages = [
            {
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["created_at"].isoformat(),
            }
            for row in map(
                dict,
                await db.fetch_all(
                    """
                    SELECT role, content, created_at
                      FROM pellier.messages
                     WHERE session_id = %s
                       AND role IN ('user', 'assistant')
                     ORDER BY created_at ASC, id ASC
                    """,
                    session_id,
                ),
            )
        ]
        audit_rows = [
            dict(row)
            for row in await db.fetch_all(
                """
                SELECT tool, caller, args, latency_ms, result, created_at
                  FROM pellier.tool_audit
                 WHERE session_id = %s
                 ORDER BY created_at ASC, audit_id ASC
                """,
                session_id,
            )
        ]
        ledger = None
        if principal_sub:
            from services.evidence_ledger import project_session_ledger

            ledger = await project_session_ledger(
                db,
                session_id=session_id,
                principal_sub=principal_sub,
                raise_on_error=True,
            )
        ledger_events = list((ledger or {}).get("events") or [])
        telemetry = (
            [
                {
                    "index": index,
                    "category": (
                        "managed"
                        if event.get("provenance")
                        in {
                            "agentcore-service-telemetry",
                            "cloudwatch-span",
                        }
                        else "owned"
                    ),
                    "title": event.get("title") or "Evidence event",
                    "description": (
                        event.get("summary")
                        or OBSERVATORY_COPY["EVIDENCE_RECORDED"]
                    ),
                    "status": event.get("status") or "unavailable",
                    "durationMs": int(event.get("durationMs") or 0),
                    "agent": (event.get("details") or {}).get("caller"),
                    "sql": event.get("sql"),
                    "rows": [event.get("details") or {}],
                    "eventKind": event.get("eventKind"),
                    "phase": event.get("phase"),
                    "provenance": event.get("provenance"),
                    "evidenceRef": event.get("evidenceRef"),
                    "occurredAt": event.get("occurredAt"),
                    "turnId": event.get("turnId"),
                    "traceId": event.get("traceId"),
                }
                for index, event in enumerate(ledger_events, start=1)
            ]
            if ledger_events
            else [
                {
                    "index": index,
                    "category": "managed" if row["caller"] == "gateway" else "owned",
                    "title": row["tool"],
                    "description": f"{row['caller']} invocation recorded in Aurora.",
                    "status": _audit_result_status(row.get("result")),
                    "durationMs": int(row.get("latency_ms") or 0),
                    "agent": row["caller"],
                    # Input and output together: the replay shows the exact
                    # arguments the tool ran with, not only what came back.
                    "rows": [
                        {
                            "args": row.get("args") or {},
                            "result": row.get("result") or {},
                        }
                    ],
                    "eventKind": "tool",
                    "phase": "execution",
                    "provenance": "aurora-receipt",
                }
                for index, row in enumerate(audit_rows, start=1)
            ]
        )
        return {
            **summary,
            "chat": messages,
            "telemetry": telemetry,
            "evidenceLedger": ledger,
            "brief": {
                "folioNumber": 0,
                "headline": "Live session evidence",
                "filedTime": summary["timestamp"].isoformat(),
                "sections": [],
                "products": [],
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to read session %s", session_id)
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["SESSION_EVIDENCE_UNAVAILABLE"],
        ) from exc


@router.get("/turns/{turn_id}/ledger")
async def get_turn_evidence_ledger(
    turn_id: str = PathParam(..., min_length=1, max_length=80),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Return one durable ledger only when it belongs to the verified caller."""
    principal_sub = str((user or {}).get("sub") or "")
    if not principal_sub:
        raise HTTPException(status_code=401, detail="authentication_required")
    from services.evidence_ledger import (
        EvidenceLedgerProjectionError,
        project_turn_ledger,
    )

    try:
        ledger = await project_turn_ledger(
            await _live_db(),
            turn_id=turn_id,
            principal_sub=principal_sub,
            raise_on_error=True,
        )
    except EvidenceLedgerProjectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="evidence_ledger_unavailable",
        ) from exc
    if ledger is None:
        raise HTTPException(status_code=404, detail="ledger_not_found")
    return ledger


@router.get("/agents")
async def list_agents():
    """Return the active, source-controlled agent topology."""
    try:
        from config import settings
        from services import agent_tools
        import inspect

        inventory_status = (
            "exercise"
            if "stub state" in inspect.getsource(agent_tools.check_inventory)
            else "shipped"
        )
        return [
            {
                "numeral": numeral,
                "name": name,
                "role": role,
                "status": status,
                "tools": tools,
                # This is the Balanced-mode model assigned by each factory.
                # Per-turn Editorial/Fast overrides remain visible in the Workbench
                # execution contract, where the actual response model is shown.
                "model": (
                    settings.BEDROCK_OPUS_MODEL
                    if model_tier == "opus"
                    else settings.BEDROCK_REPORTING_MODEL
                ),
            }
            for numeral, name, role, status, tools, model_tier in (
                (
                    "I",
                    "Search Agent",
                    "Interprets shopper intent and retrieves grounded catalog options.",
                    "shipped",
                    ["search_products", "browse_category", "compare_products"],
                    "opus",
                ),
                (
                    "II",
                    "Personalization Agent",
                    "Combines customer context with hybrid retrieval.",
                    "shipped",
                    ["search_products_hybrid", "get_customer_preferences"],
                    "opus",
                ),
                (
                    "III",
                    "Pricing Agent",
                    "Explains price ranges and compares current catalog value.",
                    "shipped",
                    ["get_price_analysis", "compare_products"],
                    "sonnet",
                ),
                (
                    "IV",
                    "Inventory Agent",
                    "Reads the warehouse system of record for availability.",
                    inventory_status,
                    ["check_inventory", "get_low_stock"],
                    "sonnet",
                ),
                (
                    "V",
                    "Customer Service Agent",
                    "Handles policy-aware post-purchase requests.",
                    "shipped",
                    ["get_return_policy", "initiate_return", "escalate_to_human"],
                    "opus",
                ),
            )
        ]
    except Exception as exc:
        logger.exception("Failed to inspect active agent topology")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["AGENT_TOPOLOGY_UNAVAILABLE"],
        ) from exc


@router.get("/tools/list")
async def list_tools():
    """Return the Aurora tool registry and current invocation counts."""
    db = await _live_db()
    try:
        rows = await db.fetch_all(
            """
            SELECT
                t.name,
                t.description,
                t.schema,
                t.owner_agent,
                t.requires_approval,
                count(ta.audit_id)::integer AS invocation_count
              FROM pellier.tools t
              LEFT JOIN pellier.tool_audit ta ON ta.tool = t.name
             WHERE t.enabled = true
             GROUP BY
                t.tool_id, t.name, t.description, t.schema,
                t.owner_agent, t.requires_approval
             ORDER BY t.name ASC
            """
        )
        return [
            {
                "numeral": numeral,
                "functionName": row["name"],
                "description": row["description"],
                "status": "shipped",
                "mutationType": "write"
                if bool(row.get("requires_approval"))
                else "read",
                "signature": str(
                    (row.get("schema") or {}).get("title")
                    or f"{row['name']}(...)"
                ),
                "usedBy": [row.get("owner_agent") or "Pellier"],
                "invocationCount": int(row.get("invocation_count") or 0),
                "version": "Aurora registry",
            }
            for numeral, raw in enumerate(rows, start=1)
            for row in [dict(raw)]
        ]
    except Exception as exc:
        logger.exception("Failed to read Aurora tool registry")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["TOOL_REGISTRY_UNAVAILABLE"],
        ) from exc


@router.post("/tools/discover", response_model=ObservatoryToolDiscoverResponse)
async def discover_tools_endpoint(payload: ObservatoryToolDiscoverRequest):
    """Semantic tool discovery via the live Aurora pgvector registry."""
    start = time.time()
    try:
        from services.embeddings import EmbeddingService
        from services.tool_registry import discover_tools

        result = await discover_tools(
            await _live_db(),
            EmbeddingService().embed_query(payload.query),
            limit=payload.limit,
        )
        results = [
            ObservatoryToolDiscoverResult(
                rank=index,
                tool_id=row.get("tool_id", row.get("name", "")),
                name=row.get("name", ""),
                description=row.get("description", ""),
                similarity=round(float(row.get("similarity", 0.0)), 4),
                status="shipped",
            )
            for index, row in enumerate(result.get("rows") or [], start=1)
        ]
        return ObservatoryToolDiscoverResponse(
            query=payload.query,
            results=results,
            duration_ms=int(
                result.get("duration_ms") or ((time.time() - start) * 1000)
            ),
            sql=str(result.get("sql") or ""),
            total_count=int(result.get("total_count") or len(results)),
        )
    except Exception as exc:
        logger.exception("Live tool discovery failed")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["TOOL_DISCOVERY_UNAVAILABLE"],
        ) from exc


@router.get("/routing")
async def list_routing():
    """Return the source-controlled paths in the running service."""
    return [dict(path) for path in OBSERVATORY_COPY["ROUTING"]]


@router.get("/scenarios")
async def list_live_scenarios(
    persona: str = Query(default="fresh", min_length=1, max_length=64),
):
    """Return guided shopper requests and preview images from Aurora."""
    db = await _live_db()
    try:
        rows = await db.fetch_all(
            """
            SELECT
                ws.scenario_id AS id,
                ws.ordinal,
                ws.prompt,
                ws.journey_role,
                ws.journey_stage,
                pc.name AS product_name,
                pc."imgUrl" AS image_url
              FROM pellier.workshop_scenarios ws
              LEFT JOIN pellier.product_catalog pc
                ON pc."productId" = ws.preview_product_id
             WHERE ws.persona_id = %s
             ORDER BY ws.ordinal ASC
            """,
            persona,
        )
        return {
            "persona": persona,
            "scenarios": [
                {
                    "id": int(row["id"]),
                    "ordinal": int(row["ordinal"]),
                    "prompt": row["prompt"],
                    "journeyRole": row.get("journey_role") or (
                        "required" if int(row["ordinal"]) <= 3 else "explore"
                    ),
                    "journeyStage": row.get("journey_stage"),
                    "productName": row.get("product_name"),
                    "imageUrl": row.get("image_url"),
                }
                for raw in rows
                for row in [dict(raw)]
            ],
        }
    except Exception as exc:
        logger.exception("Failed to read live scenarios for %s", persona)
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["SCENARIOS_UNAVAILABLE"],
        ) from exc


_PERSONA_TO_CUSTOMER_ID = {
    "marco": "CUST-MARCO",
    "anna": "CUST-ANNA",
    "theo": "CUST-THEO",
    "fresh": "CUST-FRESH",
    "jessica": "CUST-JESSICA",
}


async def _load_live_episodic(persona: str) -> list:
    """Read persona events, orders, and returns from Aurora."""
    customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower())
    if not customer_id:
        return []
    try:
        from app import db_service
        if db_service is None:
            return []
        rows = await db_service.fetch_all(
            """
            WITH events AS (
                SELECT
                    'seed-' || id::text AS id,
                    summary_text AS content,
                    ts_offset_days,
                    NULL::timestamptz AS happened_at
                  FROM pellier.customer_episodic_seed
                 WHERE customer_id = %s
                UNION ALL
                SELECT
                    'order-' || o.id::text AS id,
                    'Ordered ' || pc.name || ' (' || pc.color || ')' AS content,
                    NULL::int AS ts_offset_days,
                    o.placed_at AS happened_at
                  FROM pellier.orders o
                  JOIN pellier.product_catalog pc
                    ON pc."productId" = o.product_id
                 WHERE o.customer_id = %s
                UNION ALL
                SELECT
                    'return-' || r.id::text AS id,
                    'Return ' || r.status || ' for ' || pc.name || ' - reason: ' || r.reason AS content,
                    NULL::int AS ts_offset_days,
                    r.requested_at AS happened_at
                  FROM pellier.returns r
                  JOIN pellier.product_catalog pc
                    ON pc."productId" = r.product_id
                 WHERE r.customer_id = %s
            )
            SELECT id, content, ts_offset_days, happened_at
              FROM events
             ORDER BY happened_at DESC NULLS LAST,
                      ts_offset_days DESC NULLS LAST,
                      id DESC
             LIMIT 20
            """,
            customer_id,
            customer_id,
            customer_id,
        )
        if not rows:
            return []
        items = []
        for r in rows:
            d = dict(r)
            items.append({
                "id": f"ep-live-{d.get('id')}",
                "content": d.get("content", ""),
                "substrate": "episodic",
                "tsOffsetDays": d.get("ts_offset_days"),
                "timestamp": d.get("happened_at").isoformat()
                if d.get("happened_at") is not None
                else None,
            })
        return items
    except Exception as exc:
        logger.warning("Live episodic read failed for %s: %s", persona, exc)
        return []


async def _load_live_procedural() -> list:
    """Read procedural knowledge from runtime skills and MCP schemas.

    Procedural memory is the checked-in know-how that tells the agent how
    work should be performed. Runtime skills provide conditional instructions;
    the canonical Gateway schemas provide the tool contracts. This helper reads
    both real source surfaces and never derives know-how from execution logs.
    """
    items = []
    try:
        from skills import get_registry

        for skill in get_registry().get_all():
            items.append({
                "id": f"proc-skill-{skill.name}",
                "content": (
                    f"Runtime skill {skill.name} v{skill.version}: "
                    f"{skill.description}"
                ),
                "substrate": "procedural",
            })
    except Exception as exc:
        logger.warning("Runtime skill registry read failed: %s", exc)

    schema_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "deploy"
        / "gateway_tool_schemas.py"
    )
    try:
        tool_surfaces = runpy.run_path(str(schema_path)).get("TOOL_SCHEMAS", {})
        for surface, config in sorted(tool_surfaces.items()):
            tool_names = [
                str(tool.get("name", ""))
                for tool in config.get("tools", [])
                if tool.get("name")
            ]
            items.append({
                "id": f"proc-mcp-{surface}",
                "content": (
                    f"MCP {surface} contract: {', '.join(tool_names)}"
                ),
                "substrate": "procedural",
            })
    except Exception as exc:
        logger.warning("Canonical MCP schema read failed from %s: %s", schema_path, exc)

    return items


async def _load_live_operational_history() -> list:
    """Aggregate live tool_audit rows into operational evidence.

    Every ALLOWed tool call writes to pellier.tool_audit (reads and
    writes alike), so this aggregate covers the full per-tool signal.
    What we can honestly surface today is per-tool call counts and
    average latency — the same shape an intent-aware aggregate will
    take once intent / persona_id / success columns land on the table.
    """
    try:
        from app import db_service
        if db_service is None:
            return []
        rows = await db_service.fetch_all(
            """
            SELECT tool,
                   count(*)::int AS calls,
                   round(avg(latency_ms)::numeric, 0)::int AS avg_ms
              FROM pellier.tool_audit
             GROUP BY tool
             ORDER BY calls DESC, tool ASC
             LIMIT 6
            """,
        )
        if not rows:
            return []
        items = []
        for i, r in enumerate(rows):
            d = dict(r)
            items.append({
                "id": f"operational-live-{i}",
                "content": (
                    f"{d.get('tool')} - fired {d.get('calls')}x, "
                    f"avg {d.get('avg_ms')}ms"
                ),
                "substrate": "operational",
            })
        return items
    except Exception as exc:
        logger.warning("Live operational-history read failed: %s", exc)
        return []


async def _load_live_working(persona: str, *, namespace: Optional[str] = None) -> list:
    """Read the exact authenticated namespace selected by the route."""
    if not namespace:
        return []
    try:
        from services.agentcore_memory import AgentCoreMemory
        turns = await AgentCoreMemory(strict=True).get_session_history(namespace)
    except Exception as exc:
        logger.warning("Live working read failed for %s: %s", persona, exc)
        raise
    return [
        {
            "id": f"wk-live-{i}",
            "content": str(turn.get("content", ""))[:160],
            "substrate": "working",
            "timestamp": turn.get("timestamp"),
        }
        for i, turn in enumerate(turns[-6:])
    ]


async def _load_live_semantic(persona: str, *, namespace: Optional[str] = None) -> list:
    """Read extraction under the same actor as the shopper event writer.

    Shopper actors are isolated per authenticated session. Customer onboarding
    seeds are a different namespace and cannot stand in for learned memory.
    """
    if not namespace:
        return []
    from services.agentcore_memory import AgentCoreMemory
    preferences = await AgentCoreMemory(strict=True).get_semantic_memories(namespace)
    return [
        {"id": f"sem-live-{i}", "content": str(pref).strip()[:200], "substrate": "semantic"}
        for i, pref in enumerate(preferences) if str(pref).strip()
    ]


def _live_substrate(
    label: str,
    store: str,
    caveat: str = "",
    source: str = "live",
) -> dict:
    panel = {
        "label": label,
        "store": store,
        "source": source,
        "items": [],
    }
    if caveat:
        panel["caveat"] = caveat
    return panel


@router.get("/memory-showcase/{persona}")
async def get_memory_showcase(
    persona: str,
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Read an owned showcase; never provision, seed, or invoke on page load."""
    import asyncio
    from services.memory_showcase import MemoryShowcase

    customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower(), "")
    principal_sub = authorize_customer_read(user, customer_id)
    try:
        return await asyncio.to_thread(lambda: MemoryShowcase().inspect(principal_sub))
    except Exception as exc:
        logger.warning("Memory showcase read unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail=OBSERVATORY_COPY["MEMORY_SHOWCASE_UNAVAILABLE"]
        ) from exc


@router.get("/memory/{persona}")
async def get_memory(
    persona: str,
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Read the verified customer's memory; persona selection grants no access."""
    customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower(), "")
    principal_sub = authorize_customer_read(user, customer_id)
    from services.agentcore_identity import AgentCoreIdentityService

    try:
        db = await _live_db()
        namespace = await AgentCoreIdentityService.latest_shopper_namespace(db, principal_sub)
        _sem_store = (
            f"/pellier/preferences/{namespace}/" if namespace
            else "No authenticated conversation recorded yet"
        )
        data = {
            "persona": persona,
            "working": _live_substrate(
                "Conversation events: AgentCore Memory",
                namespace or "No authenticated conversation recorded yet",
                "No live session turns found yet. Create a Pellier turn for this persona, then reload.",
            ),
            "semantic": _live_substrate(
                "User preferences: AgentCore Memory",
                _sem_store,
                (
                    "No USER_PREFERENCE records found yet. Extraction is "
                    "asynchronous after conversation; this panel stays empty "
                    "until AgentCore Memory has durable preference records."
                ),
                "settling",
            ),
            "episodic": _live_substrate(
                "Customer history: Aurora PostgreSQL",
                "pellier.customer_episodic_seed + orders + returns",
                "No live Aurora events found for this persona yet.",
            ),
            "procedural": _live_substrate(
                "Runtime instructions: repository",
                "skills/*/SKILL.md + scripts/deploy/gateway_tool_schemas.py",
                "No runtime skills or canonical MCP schemas were readable.",
            ),
            "operational": _live_substrate(
                "Tool execution history: Aurora PostgreSQL",
                "pellier.tool_audit (aggregate)",
                "No live tool_audit rows found yet. Run a turn that calls a tool, then reload.",
            ),
        }

        data["working"]["items"] = await _load_live_working(persona, namespace=namespace)
        if data["working"]["items"]:
            data["working"].pop("caveat", None)

        data["semantic"]["items"] = await _load_live_semantic(persona, namespace=namespace)
        if data["semantic"]["items"]:
            data["semantic"]["source"] = "live"
            data["semantic"].pop("caveat", None)

        data["episodic"]["items"] = await _load_live_episodic(persona)
        if data["episodic"]["items"]:
            data["episodic"].pop("caveat", None)

        data["procedural"]["items"] = await _load_live_procedural()
        if data["procedural"]["items"]:
            data["procedural"].pop("caveat", None)

        data["operational"]["items"] = await _load_live_operational_history()
        if data["operational"]["items"]:
            data["operational"].pop("caveat", None)

        return data
    except Exception as exc:
        logger.error("Failed to load memory for %s: %s", persona, exc)
        raise HTTPException(status_code=500, detail="Failed to load memory state")  # copy-allow: observatory-error-detail


@router.get("/performance")
async def get_performance():
    """Return metrics calculated from the live Aurora evidence ledger."""
    db = await _live_db()
    try:
        rows = await db.fetch_all(
            """
            SELECT tool, latency_ms
              FROM pellier.tool_audit
             WHERE latency_ms IS NOT NULL
             ORDER BY created_at DESC
             LIMIT 1000
            """
        )
        latencies = [int(dict(row)["latency_ms"]) for row in rows]
        sorted_latencies = sorted(latencies)
        p50 = (
            sorted_latencies[(len(sorted_latencies) - 1) // 2]
            if sorted_latencies
            else 0
        )
        return {
            "coldStartP50": 0,
            "warmReuseP50": p50,
            "sampleCount": len(latencies),
            "histogram": [],
            "latencyBudget": [],
            "pgvectorComparison": [],
            "pgvectorTuning": [],
            "searchStrategies": [],
            "storageUsage": [],
        }
    except Exception as exc:
        logger.exception("Failed to calculate Aurora performance metrics")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["PERFORMANCE_UNAVAILABLE"],
        ) from exc


@router.get("/evaluations")
async def get_evaluations():
    """Expose only evaluation runs that are actually configured or recorded."""
    try:
        from services import agentcore_evals

        managed = agentcore_evals.describe_configuration()
        return {
            "provenance": "managed" if managed["configured"] else "unavailable",
            "states": {
                "localGate": {
                    "label": "Local deterministic gate",
                    "available": True,
                    "describes": "current source validation; not a managed evaluation run",
                    "sources": [
                        "tests/test_golden_journeys.py",
                        "scripts/eval_retrieval_harness.py",
                    ],
                },
                "managed": {
                    "label": "Managed AgentCore evaluation",
                    "available": managed["configured"],
                    "describes": (
                        "real deployed Runtime, trace-backed"
                        if managed["configured"]
                        else "not provisioned — read the local gate instead"
                    ),
                    "operation": managed["operation"],
                    "configuration": managed,
                },
            },
            "scorecards": [],
        }
    except Exception as exc:
        logger.exception("Failed to inspect evaluation configuration")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["EVALUATION_UNAVAILABLE"],
        ) from exc


@router.get("/architecture")
async def get_architecture():
    """Return source-controlled architecture facts, never measured results."""
    return [dict(layer) for layer in OBSERVATORY_COPY["ARCHITECTURE"]]


@router.get("/build-state")
async def get_build_state():
    """Return current source/registry state without a reference fixture."""
    try:
        db = await _live_db()
        tool_rows = await db.fetch_all(
            "SELECT name FROM pellier.tools WHERE enabled = true ORDER BY name"
        )
        inventory = (
            "exercise" if _inventory_agent_definition_is_workshop_stub() else "shipped"
        )
        check_inventory = (
            "exercise" if _check_inventory_is_workshop_stub() else "shipped"
        )
        # The inventory exercise is source-defined rather than discovered from
        # the optional Aurora tool catalog. That catalog describes additional
        # registered tools; it must not erase the one tool a participant is
        # editing and proving in Lab 1.
        agent_map = {"Inventory Agent": inventory}
        tool_map = {dict(row)["name"]: "shipped" for row in tool_rows}
        tool_map["check_inventory"] = check_inventory
        # Every guided build, keyed by the lab step the guide names. Source
        # defined, like the two above: a participant's edit is visible here the
        # moment the backend reloads, without a deploy or a database round trip.
        exercises = {
            "1a": "exercise" if inventory == "exercise" else "shipped",
            "1b": "exercise" if check_inventory == "exercise" else "shipped",
            "2b": (
                "exercise" if _lab2_candidate_budget_is_workshop_stub() else "shipped"
            ),
            "3a": (
                "exercise"
                if _lab3_gateway_catalogue_is_workshop_stub()
                else "shipped"
            ),
            "3b": (
                "exercise"
                if _lab3_support_contract_is_workshop_stub()
                else "shipped"
            ),
        }
        return {
            "agents": agent_map,
            "tools": tool_map,
            "exercises": exercises,
        }
    except Exception as exc:
        logger.exception("Failed to build live build-state")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["BUILD_STATE_UNAVAILABLE"],
        ) from exc


async def get_workshop_readiness():
    """Return cheap readiness checks for the live workshop pillars.

    This is the API version of ``scripts/health-gate.sh`` for the
    Observatory. It does not call Bedrock, Runtime, Gateway, or Policy; it
    only reads config and small Aurora counts so participants can open
    the panel without triggering managed services.
    """
    try:
        return await _collect_readiness()
    except Exception as exc:
        logger.error("Failed to build readiness payload: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load readiness")  # copy-allow: observatory-error-detail


@router.get("/proof-board")
async def get_proof_board(
    session_id: Optional[str] = Query(
        default=None,
        description="Session id for the latest managed Runtime receipt",
    ),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Return required-path proof cards plus terminal fallbacks.

    The payload is intentionally operational: each card has a stable
    ``id`` for URL anchors, a status, short evidence lines, and a
    curl/SQL fallback. The frontend renders it at
    ``/observatory/proof-board`` and Pellier trace chips deep-link to
    individual anchors.
    """
    try:
        return await _collect_proof_board(
            session_id=session_id,
            principal_sub=str((user or {}).get("sub") or ""),
        )
    except Exception as exc:
        logger.error("Failed to build proof-board payload: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load proof board")  # copy-allow: observatory-error-detail


class ObservatorySkillRouteRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


@router.post("/skills/route")
async def route_skills_endpoint(payload: ObservatorySkillRouteRequest):
    """Live skill-router demo for the Observatory Skills surface.

    Calls services/skills.SkillRouter.route() against the user query
    and returns the same RouterDecision shape the chat pipeline emits
    as an SSE skill_routing event:
        {loaded_skills, considered, elapsed_ms, user_message}

    Read-only; never raises. Returns an empty decision on any failure
    (matches the chat pipeline's behavior — skills stay dormant if the
    router can't decide).
    """
    try:
        from skills import SkillRouter, get_registry
        skill_router = SkillRouter(get_registry())
        decision = skill_router.route(payload.query)
        return {
            "loaded_skills": list(decision.loaded_skills or []),
            "considered": list(decision.considered or []),
            "elapsed_ms": int(decision.elapsed_ms or 0),
            "user_message": payload.query[:500],
        }
    except Exception as exc:
        logger.warning("Observatory skill route failed: %s", exc)
        return {
            "loaded_skills": [],
            "considered": [],
            "elapsed_ms": 0,
            "user_message": payload.query[:500],
            "error": "skill_routing_unavailable",
        }


@router.get("/policies")
async def get_cedar_policies():
    """Return the Cedar policies attached to the managed AgentCore Policy
    engine (Gateway-enforced, ENFORCE mode). Used by the Observatory's
    Write-path surface to show "policy is code, code is enforcement".

    Reads the managed engine via boto3 ``bedrock-agentcore-control``
    keyed on ``AGENTCORE_POLICY_ENGINE_ID``. The old local fake-Cedar
    ``PolicyService`` was removed — the Gateway is the one gate now.
    ``cedar`` carries the managed policy's Cedar statement; managed
    policies have no ``applies_to`` sidecar (the gated action is encoded
    inside the Cedar statement itself), so it is reported as null.
    """
    try:
        from services.managed_policy import list_managed_policies
        result = list_managed_policies()
        policies = result.get("policies", [])
        return {
            "count": len(policies),
            "source": result.get("source"),
            "policy_engine_id": result.get("policy_engine_id", ""),
            "policies": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description"),
                    "applies_to": None,
                    "cedar": p.get("cedar"),
                }
                for p in policies
            ],
        }
    except Exception as exc:
        logger.error("Failed to load policies: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load policies")  # copy-allow: observatory-error-detail


@router.get("/executions")
async def list_governed_executions(
    limit: int = Query(default=20, ge=1, le=50),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Governed operator executions this principal performed, newest first.

    Read-only and principal-scoped. The visibility authority is
    ``execution_receipts.actor_principal`` — the operator AgentCore Policy authorized —
    which is the operator-rail counterpart of ``governed_receipts.principal_id``. No
    existing filter was weakened to make these rows appear.
    """
    try:
        from app import db_service
        principal_sub = str((user or {}).get("sub") or "")
        if db_service is None or not principal_sub:
            return {"count": 0, "executions": []}

        from services.governed_execution import list_executions

        rows = await list_executions(
            db_service, principal_sub=principal_sub, limit=limit
        )
        return {"count": len(rows), "executions": rows}
    except Exception as exc:
        logger.error("Failed to list governed executions: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list executions")  # copy-allow: observatory-error-detail


@router.get("/operator-lineage/{customer_id}")
async def get_operator_lineage(
    customer_id: str = PathParam(..., min_length=1, max_length=64),
    review_id: int | None = Query(default=None, ge=1),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Reconstruct the live storefront-to-operator loop for one client.

    No fixture fallback. The handoff is untrusted context from the append-only
    shopper receipt; the review is the durable human checkpoint; graph metadata
    comes from an actually persisted Operator Concierge artifact; execution
    evidence is principal-scoped to the operator who performed it.
    """
    from app import db_service

    if db_service is None:
        raise HTTPException(status_code=503, detail="database_unavailable")

    from services import governed_execution
    from services import operator_concierge_sessions as sessions
    from services import operator_review
    from services import shopper_handoff
    from services.data_source import database_source_label

    try:
        if review_id is None:
            handoff = await shopper_handoff.resolve_latest_for_customer(
                db_service, customer_id=customer_id
            )
        else:
            handoff = await shopper_handoff.resolve_for_review(
                db_service,
                review_id=review_id,
                expected_customer_id=customer_id,
            )
    except shopper_handoff.HandoffIntegrityError as exc:
        logger.error("Operator lineage mismatch for %s", customer_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Operator lineage handoff read failed for %s: %s", customer_id, exc)
        raise HTTPException(status_code=503, detail="operator_lineage_unavailable") from exc

    if not handoff:
        return {
            "customerId": customer_id,
            "dataSource": database_source_label(),
            "handoff": None,
            "review": None,
            "orchestration": None,
            "execution": None,
        }

    review_id = int((handoff.get("proposal") or {}).get("reviewId") or 0)
    review_row = await operator_review.get_review(db_service, review_id)
    if not review_row or str(review_row.get("customer_id") or "") != customer_id:
        raise HTTPException(status_code=409, detail="shopper_handoff_lineage_mismatch")

    receipt = await governed_execution.latest_receipt(db_service, review_id)
    review = {
        "reviewId": review_id,
        "customerId": customer_id,
        "customerName": review_row.get("customer_name") or customer_id,
        "action": review_row.get("action"),
        "status": review_row.get("status"),
        "sourceTurnId": review_row.get("source_turn_id"),
        "executionTurnId": review_row.get("execution_turn_id"),
        "actionHash": review_row.get("action_hash"),
        "requestedAt": (
            review_row["requested_at"].isoformat()
            if hasattr(review_row.get("requested_at"), "isoformat")
            else review_row.get("requested_at")
        ),
        "decidedAt": (
            review_row["decided_at"].isoformat()
            if hasattr(review_row.get("decided_at"), "isoformat")
            else review_row.get("decided_at")
        ),
    }

    orchestration = None
    try:
        graph_artifact = await sessions.load_graph_artifact_for_review(
            db_service,
            customer_id=customer_id,
            review_id=review_id,
            action_hash=str(review.get("actionHash") or ""),
        )
        if graph_artifact:
            orchestration = {
                **graph_artifact["orchestration"],
                "sessionId": graph_artifact.get("sessionId"),
                "turnId": graph_artifact.get("turnId"),
            }
    except Exception as exc:  # noqa: BLE001 - review lineage remains useful
        logger.warning(
            "Operator graph artifact unavailable for review %s: %s",
            review_id,
            exc,
        )

    execution = None
    principal_sub = str((user or {}).get("sub") or "")
    if receipt and principal_sub:
        execution = await governed_execution.reconstruct_execution(
            db_service,
            review_id=review_id,
            principal_sub=principal_sub,
        )

    return {
        "customerId": customer_id,
        "customerName": review["customerName"],
        "dataSource": database_source_label(),
        "handoff": handoff,
        "review": review,
        "orchestration": orchestration,
        "execution": execution,
    }


@router.get("/executions/{review_id}")
async def reconstruct_governed_execution(
    review_id: int = PathParam(..., ge=1),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """One governed execution, reconstructed layer by layer from durable artifacts.

    The spine is the execution receipt, not ``tool_audit``. For a governed system,
    execution evidence begins at the authorization attempt: a Cedar DENY correctly
    writes no audit row and claims no idempotency key, and a reconstruction rooted at
    the tool cannot render it at all. Each layer reports whether it is present and why,
    so an absent layer reads as the evidence it is rather than as missing data.
    """
    try:
        from app import db_service
        if db_service is None:
            raise HTTPException(status_code=503, detail="database_unavailable")
        principal_sub = str((user or {}).get("sub") or "")
        if not principal_sub:
            return {
                "review_id": review_id,
                "status": "sign_in_required",
                "execution": None,
            }

        from services.governed_execution import reconstruct_execution

        story = await reconstruct_execution(
            db_service, review_id=review_id, principal_sub=principal_sub
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Reconstruction failed for review %s: %s", review_id, exc)
        raise HTTPException(status_code=500, detail="Failed to reconstruct execution")  # copy-allow: observatory-error-detail

    if story is None:
        # Either nothing was executed, or it was executed by a different principal.
        # One status for both on purpose: distinguishing them would tell a caller that
        # an execution they may not read exists.
        raise HTTPException(status_code=404, detail="no_execution_for_principal")
    return story


@router.get("/tool-audit/recent")
async def get_recent_tool_audit(
    limit: int = Query(default=10, ge=1, le=50),
    user: Optional[dict[str, Any]] = Depends(get_current_user),
):
    """Return the most recent rows from pellier.tool_audit, in reverse
    chronological order. Used by the Write-path surface to demonstrate
    that every ALLOWed tool call (read or write) is reconstructible
    from a single row (args + result + latency_ms).

    Read-only and principal-scoped. An audit row must be joined to either an
    explicit policy receipt or a durable governed turn receipt for the
    verified caller; raw ledger history is never a browser-wide feed.
    """
    try:
        from app import db_service
        principal_sub = str((user or {}).get("sub") or "")
        if db_service is None or not principal_sub:
            return {"count": 0, "rows": []}

        from services.governed_turn_receipt import get_visible_tool_audit

        normalized = await get_visible_tool_audit(
            db_service, principal_sub=principal_sub, limit=limit
        )
        return {"count": len(normalized), "rows": normalized}
    except Exception as exc:
        logger.error("Failed to load tool_audit: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load tool audit")  # copy-allow: observatory-error-detail


@router.get("/identity-boundary")
async def identity_boundary(
    _operator: dict[str, Any] = Depends(require_operator),
):
    """Reconstruct the governed identity boundary from Aurora receipts.

    This operator-only read model backs Lab 4's visual. It answers one question for
    each recorded attempt: which verified principal asked for which customer's
    data, what the policy engine decided, and whether an execution row exists
    that carries that attempt's key.

    It reports; it does not evaluate. Every field comes from
    ``pellier.governed_receipts``, which the CLI proof writes after Cognito has
    validated the exact bearer token used, so the Observatory cannot claim an
    identity the Gateway never accepted. Rows arrive only from
    ``scripts/prove_identity_boundary.py`` or ``gateway_initiate_return.py
    --record-receipt``; an empty table renders as "not run yet", never as a
    pass.

    Never returned: the access token, the password, or the Secrets Manager
    value. ``verified_subject`` is truncated here rather than in the client, so
    the full subject does not travel to the browser at all. The stored
    ``token_fingerprint_sha256`` is a safe correlation handle and is passed
    through as-is.

    ``execution_row`` is the honest three-state answer. ``present`` means an
    execution row carries this attempt's key. ``absent`` means the key was
    searched for and found nowhere, which is what makes a DENY provable.
    ``unknown`` means the receipt predates keyed correlation, and is NEVER
    reported as absence: "we did not look" and "it is not there" are different
    claims, and only the second one proves anything.
    """
    db = await _live_db()

    def _truncate_subject(subject: str) -> str:
        clean = (subject or "").strip()
        if len(clean) <= 12:
            return clean
        return f"{clean[:8]}…{clean[-4:]}"

    try:
        rows = await db.fetch_all(
            """
            SELECT
                gr.receipt_id                              AS "receiptId",
                gr.session_id                              AS "correlationKey",
                COALESCE(
                    NULLIF(gr.args->>'idempotency_key', ''),
                    gr.session_id
                )                                          AS "idempotencyKey",
                gr.verified_username                       AS "verifiedUsername",
                gr.verified_subject                        AS "verifiedSubject",
                gr.args->>'customer_id'                    AS "requestedCustomerId",
                gr.decision                                AS decision,
                gr.policy_name                             AS "policyName",
                gr.policy_engine_id                        AS "policyEngineId",
                gr.token_fingerprint_sha256                AS "tokenFingerprint",
                gr.identity_source                         AS "identitySource",
                gr.tool                                    AS tool,
                gr.audit_id                                AS "auditId",
                gr.created_at                              AS "createdAt",
                mapping.customer_ids                        AS "mappedCustomerIds",
                (
                    SELECT count(*)
                      FROM pellier.tool_audit ta
                     WHERE ta.tool = 'initiate_return'
                       AND ta.args->>'idempotency_key' = COALESCE(
                         NULLIF(gr.args->>'idempotency_key', ''),
                         gr.session_id
                     )
                       AND ta.args->>'customer_id' = gr.args->>'customer_id'
                       AND ta.args->>'product_id' = gr.args->>'product_id'
                       AND ta.args->>'reason' = gr.args->>'reason'
                )::integer                                 AS "keyedAuditRows",
                (
                    SELECT count(*)
                      FROM pellier.write_operations wo
                      JOIN pellier.returns r
                        ON r.id::text = wo.result->>'return_id'
                     WHERE wo.idempotency_key = COALESCE(
                         NULLIF(gr.args->>'idempotency_key', ''),
                         gr.session_id
                     )
                       AND wo.operation = 'initiate_return'
                       AND wo.completed_at IS NOT NULL
                       AND wo.result->>'status' = 'success'
                       AND r.customer_id = gr.args->>'customer_id'
                       AND r.product_id = gr.args->>'product_id'
                       AND r.reason = gr.args->>'reason'
                )::integer                                 AS "keyedWriteRows"
              FROM pellier.governed_receipts gr
              LEFT JOIN LATERAL (
                  SELECT array_agg(pc.customer_id ORDER BY pc.customer_id) AS customer_ids
                    FROM pellier.principal_customers pc
                   WHERE pc.principal_sub = gr.verified_subject
              ) mapping ON TRUE
             ORDER BY gr.created_at DESC, gr.receipt_id DESC
             LIMIT 30
            """
        )
    except Exception as exc:
        logger.exception("Failed to read governed identity receipts")
        raise HTTPException(
            status_code=503,
            detail=OBSERVATORY_COPY["IDENTITY_BOUNDARY_UNAVAILABLE"],
        ) from exc

    attempts = []
    for row in rows:
        record = dict(row)
        receipt_key = (record.get("correlationKey") or "").strip()
        idempotency_key = (record.get("idempotencyKey") or "").strip()
        audit_rows = record.get("keyedAuditRows") or 0
        source = (record.get("identitySource") or "").strip().lower()
        raw_mapping = record.get("mappedCustomerIds") or []
        mapped_customers = [
            customer.strip()
            for customer in raw_mapping
            if isinstance(customer, str) and customer.strip()
        ] if isinstance(raw_mapping, (list, tuple)) else []
        # Migration 010 seeds one deterministic forensic incident into this same
        # table. It is a teaching fixture, not a provider decision, and it
        # predates keyed correlation: its session_id is a readable label rather
        # than an idempotency key. Reporting "absent" for it would manufacture a
        # negative proof out of a row nobody ever keyed, which is the exact
        # failure mode this view exists to rule out.
        is_fixture = source in {"seeded", "fixture"} or source.startswith("seeded")
        if is_fixture or not idempotency_key:
            execution_row = "unknown"
        elif audit_rows > 0:
            execution_row = "present"
        else:
            execution_row = "absent"

        requested = (record.get("requestedCustomerId") or "").strip()
        mapped = mapped_customers[0] if len(mapped_customers) == 1 else ""
        # Whether the principal was asking about its own customer. Reported as a
        # fact about the two values, not as an authorization verdict: Cedar owns
        # that, and `decision` above carries its answer.
        if len(mapped_customers) > 1:
            ownership = "ambiguous-mapping"
        elif requested and mapped:
            ownership = "own-customer" if requested == mapped else "other-customer"
        else:
            ownership = "unmapped"

        attempts.append(
            {
                "receiptId": record.get("receiptId"),
                "correlationKey": receipt_key,
                "idempotencyKey": idempotency_key,
                "verifiedUsername": record.get("verifiedUsername"),
                "verifiedSubject": _truncate_subject(record.get("verifiedSubject") or ""),
                "requestedCustomerId": requested or None,
                "mappedCustomerId": mapped or None,
                "mappingCardinality": len(mapped_customers),
                "ownership": ownership,
                "decision": (record.get("decision") or "").upper() or "NOT_EVALUATED",
                "policyName": record.get("policyName"),
                "policyEngineId": record.get("policyEngineId"),
                "tokenFingerprint": record.get("tokenFingerprint"),
                "identitySource": record.get("identitySource"),
                # Per-row, not per-page. A page-level badge would let one
                # seeded row inherit the credibility of the live ones beside it.
                "provenance": "Fixture" if is_fixture else "Authoritative",
                "tool": record.get("tool"),
                "executionRow": execution_row,
                "keyedAuditRows": audit_rows,
                "durableWriteRows": record.get("keyedWriteRows") or 0,
                "auditId": record.get("auditId"),
                "createdAt": record.get("createdAt"),
            }
        )

    # Live proof and seeded reference are separate collections, not one list with
    # a page-level badge. A "weakest row wins" summary was the first shape here
    # and it was wrong in a specific way: migration 010 seeds a permanent
    # forensic fixture, so the page could never report a valid live run as
    # authoritative no matter how many times a participant proved it.
    fixtures = [a for a in attempts if a["provenance"] == "Fixture"]
    live = [a for a in attempts if a["provenance"] == "Authoritative"]

    # The proof driver keys every attempt `identity-boundary-<run>-<case>`, so
    # the run is recoverable from the key and one command's four cases stay
    # together. Anything else live is grouped under its own key as a run of one.
    def _run_of(attempt: dict[str, Any]) -> str:
        key = attempt.get("correlationKey") or ""
        parts = key.split("-")
        if len(parts) >= 4 and parts[0] == "identity" and parts[1] == "boundary":
            return "-".join(parts[:3])
        return key or f"receipt-{attempt.get('receiptId')}"

    runs: list[dict[str, Any]] = []
    seen_runs: dict[str, dict[str, Any]] = {}
    for attempt in live:
        run_id = _run_of(attempt)
        run = seen_runs.get(run_id)
        if run is None:
            # `attempts` is ordered newest first, so the first sighting of a run
            # carries its most recent timestamp.
            run = {"runId": run_id, "startedAt": attempt.get("createdAt"), "attempts": []}
            seen_runs[run_id] = run
            runs.append(run)
        run["attempts"].append(attempt)

    for run in runs:
        cases = run["attempts"]
        decisions = {c["decision"] for c in cases}
        # Summaries are computed inside one run only. Mixing runs would let a
        # stale failure follow a participant who has since fixed their policy.
        run["caseCount"] = len(cases)
        run["denyCount"] = sum(1 for c in cases if c["decision"] == "DENY")
        run["allowCount"] = sum(1 for c in cases if c["decision"] == "ALLOW")
        run["provenance"] = "Authoritative"
        # "Two DENYs and one ALLOW" is not a complete proof: it could be three
        # unrelated receipts. The driver writes exactly four named cases, with
        # two Jessica invocations sharing one durable write key. Require that
        # concrete contract before the Observatory calls a run held.
        expected_cases = {
            f"{run['runId']}-marco": ("marco", "CUST-MARCO", "DENY", "absent"),
            f"{run['runId']}-anna": ("anna", "CUST-ANNA", "DENY", "absent"),
            f"{run['runId']}-jessica": (
                "jessica",
                "CUST-JESSICA",
                "ALLOW",
                "present",
            ),
            f"{run['runId']}-jessica-replay": (
                "jessica",
                "CUST-JESSICA",
                "ALLOW",
                "present",
            ),
        }
        cases_by_receipt: dict[str, list[dict[str, Any]]] = {}
        for case in cases:
            cases_by_receipt.setdefault(case["correlationKey"], []).append(case)

        matrix_shape_held = (
            len(cases) == len(expected_cases)
            and set(cases_by_receipt) == set(expected_cases)
            and all(len(group) == 1 for group in cases_by_receipt.values())
        )
        matrix_cases_held = matrix_shape_held
        for receipt_key, (
            expected_username,
            expected_customer,
            expected_decision,
            expected_execution,
        ) in expected_cases.items():
            case = cases_by_receipt.get(receipt_key, [None])[0]
            if case is None:
                matrix_cases_held = False
                continue
            if (
                (case.get("verifiedUsername") or "").lower() != expected_username
                or case.get("requestedCustomerId") != "CUST-JESSICA"
                or case.get("mappedCustomerId") != expected_customer
                or case.get("mappingCardinality") != 1
                or case.get("tool") != "initiate_return"
                or case.get("decision") != expected_decision
                or case.get("executionRow") != expected_execution
            ):
                matrix_cases_held = False
                continue
            if expected_decision == "DENY" and (
                case.get("keyedAuditRows") != 0 or case.get("durableWriteRows") != 0
            ):
                matrix_cases_held = False

        jessica = cases_by_receipt.get(f"{run['runId']}-jessica", [None])[0]
        replay = cases_by_receipt.get(
            f"{run['runId']}-jessica-replay", [None]
        )[0]
        replay_contract_held = bool(
            jessica
            and replay
            and jessica.get("idempotencyKey")
            and jessica.get("idempotencyKey") == replay.get("idempotencyKey")
            and jessica.get("keyedAuditRows") == 2
            and replay.get("keyedAuditRows") == 2
            and jessica.get("durableWriteRows") == 1
            and replay.get("durableWriteRows") == 1
        )
        run["complete"] = matrix_cases_held and replay_contract_held
        run["contradiction"] = next(
            (
                f"{c['verifiedUsername']}: {c['decision']} with execution "
                f"{c['executionRow']}"
                for c in cases
                if (c["decision"] == "DENY" and c["executionRow"] == "present")
                or (c["decision"] == "ALLOW" and c["executionRow"] == "absent")
            ),
            None,
        )
        run["decisions"] = sorted(decisions)

    return {
        # Flat list retained for callers that want the raw rows.
        "attempts": attempts,
        "count": len(attempts),
        "liveRuns": runs,
        "liveCount": len(live),
        # The run a participant is looking at: the newest live one. Its summary is
        # computed only from its own cases.
        "selectedRunId": runs[0]["runId"] if runs else None,
        "fixtures": fixtures,
        "fixtureCount": len(fixtures),
        "emptyReason": None if runs else OBSERVATORY_COPY["IDENTITY_BOUNDARY_EMPTY"],
    }
