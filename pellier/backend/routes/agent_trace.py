"""``/api/agent-trace/*`` — Pellier Labs Observatory read-only API endpoints.

This router provides the backend data layer for Pellier Labs Observatory
frontend surfaces. All endpoints are read-only and return fixture data
initially, with graceful degradation when the database is unavailable.

Endpoints are additive to the existing ``routes/workshop.py`` router
(which also mounts at ``/api/agent-trace/``). No path conflicts — workshop
owns ``/query``, ``/resume``, ``/tool-registry``; this router owns the
observatory surface endpoints listed below.

Endpoints:
    GET  /sessions             — session list for persona
    GET  /sessions/{id}        — full session detail or 404
    GET  /agents               — 5 agents with status, tools, model config
    GET  /tools                — tools with signatures, status, metadata
    POST /tools/discover       — pgvector semantic search
    GET  /routing              — 3 routing patterns with active indicator
    GET  /memory/{persona}     — four memory types plus operational history
    GET  /performance          — metrics and benchmarks
    GET  /evaluations          — agent scorecards
    GET  /observatory          — dashboard summary
    GET  /architecture         - system architecture diagram payload
    GET  /build-state          - shipped vs exercise maps for agents and tools
    GET  /readiness            - workshop readiness checks for live pillars
    GET  /proof-board          - required-path evidence cards and fallbacks
    POST /skills/route         - Live skill router demo (Sonnet 4.6)
    GET  /policies             - Cedar policies for the Write-path surface
    GET  /tool-audit/recent    - Recent rows from pellier.tool_audit
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import re
import runpy
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-trace", tags=["agent-trace-observatory"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AgentTraceSessionSummary(BaseModel):
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


class AgentTraceToolDiscoverRequest(BaseModel):
    """Request body for the tool discovery endpoint."""
    query: str = Field(
        default="show me something for long summer walks",
        min_length=1,
        description="Natural-language query for semantic tool discovery",
    )
    limit: int = Field(default=5, ge=1, le=9)


class AgentTraceToolDiscoverResult(BaseModel):
    """A single tool discovery result with similarity score."""
    rank: int
    tool_id: str
    name: str
    description: str
    similarity: float
    status: str


class AgentTraceToolDiscoverResponse(BaseModel):
    """Response from the tool discovery endpoint."""
    query: str
    results: list[AgentTraceToolDiscoverResult]
    duration_ms: int
    sql: str
    total_count: int


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "src"
    / "agent-trace"
    / "fixtures"
)

_fixture_cache: dict[str, Any] = {}
_fixture_paths = {
    path.stem: path
    for path in _FIXTURE_DIR.iterdir()
    if path.is_file()
    and path.suffix == ".json"
    and re.fullmatch(r"[a-z0-9-]{1,128}", path.stem)
}


def _load_fixture(name: str) -> Any:
    """Load a fixture JSON file from the frontend fixtures directory.

    Results are cached in memory after first load. Returns None if the
    file doesn't exist or can't be parsed.
    """
    if not re.fullmatch(r"[a-z0-9-]{1,128}", name):
        logger.warning("Rejected invalid fixture name")
        return None
    if name in _fixture_cache:
        return _fixture_cache[name]
    path = _fixture_paths.get(name)
    if path is None:
        logger.warning("Fixture file not found: %s", name)
        return None
    try:
        data = json.loads(path.read_text())
        _fixture_cache[name] = data
        return data
    except json.JSONDecodeError as exc:
        logger.warning("Fixture file malformed: %s — %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Tool / build state helpers (fixtures + workshop live overlay)
# ---------------------------------------------------------------------------


def _fixture_tool_status_map() -> dict[str, str]:
    """functionName → shipped | exercise from tools.json fixtures."""
    tools = _load_fixture("tools") or []
    out: dict[str, str] = {}
    for t in tools:
        fn = t.get("functionName")
        st = t.get("status")
        if isinstance(fn, str) and isinstance(st, str):
            out[fn] = st
    return out


def _tool_discovery_status(tool_name: str) -> str:
    """Status for discovery rows — matches Pellier Labs Tools surface / fixtures."""
    return _fixture_tool_status_map().get(tool_name, "shipped")


def _floor_check_is_workshop_stub() -> bool:
    """Check the tool wrapper and the participant's warehouse query."""
    try:
        from services import agent_tools
        from services.inventory_sql import warehouse_inventory_query

        src = inspect.getsource(agent_tools.floor_check)
        query_src = inspect.getsource(warehouse_inventory_query)
    except Exception:
        return True
    if "floor_check is in stub state" in src:
        return True
    if "received_product_query" in src:
        return True
    if "WORKSHOP_INVENTORY_SQL_STUB" in query_src:
        return True
    return False


def _stock_keeper_has_floor_check_grant() -> bool:
    """Read the live Stock Keeper tool list without trusting fixture status."""
    try:
        from agents import stock_keeper

        source_path = Path(inspect.getsourcefile(stock_keeper) or "")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, TypeError):
        return False

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "INVENTORY_AGENT_TOOLS"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            return False
        return any(
            isinstance(item, ast.Name) and item.id == "floor_check"
            for item in node.value.elts
        )
    return False


def _configured(value: Any) -> bool:
    """True when an env/config value is present and non-empty."""
    return bool(str(value or "").strip())


def _readiness_check(
    *,
    check_id: str,
    label: str,
    state: str,
    detail: str,
    required: bool = True,
    href: str | None = None,
) -> dict[str, Any]:
    """Small serializable readiness row used by Pellier Labs and tests."""
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
        logger.warning("Pellier Labs readiness counts unavailable: %s", exc)
        return None


async def _latest_audit_row(
    *,
    tool: str | None = None,
    caller: str | None = None,
) -> dict[str, Any] | None:
    """Return the latest tool_audit row for a tool/caller filter."""
    clauses: list[str] = []
    params: list[Any] = []
    if tool:
        clauses.append("tool = %s")
        params.append(tool)
    if caller:
        clauses.append("caller = %s")
        params.append(caller)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        from app import db_service
        if db_service is None:
            return None
        row = await db_service.fetch_one(
            f"""
            SELECT audit_id,
                   session_id,
                   tool,
                   caller,
                   args,
                   result,
                   latency_ms,
                   created_at
              FROM pellier.tool_audit
              {where}
             ORDER BY audit_id DESC
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
        logger.warning("Pellier Labs latest audit row unavailable: %s", exc)
        return None


def _latest_managed_receipt(session_id: str | None = None) -> dict[str, Any]:
    """Return the latest managed Runtime/Gateway receipt, if one exists."""
    try:
        from services.agentcore_runtime import get_latest_trace

        trace = get_latest_trace(session_id)
    except Exception as exc:
        logger.debug("Managed receipt unavailable: %s", exc)
        return {
            "present": False,
            "traceKind": "",
            "runtime": "",
            "rail": "",
            "jwtPassthrough": False,
            "gatewayPassthrough": False,
        }
    return {
        "present": trace.get("traceKind") == "managed-runtime-receipt",
        "traceKind": trace.get("traceKind", ""),
        "runtime": trace.get("runtime", ""),
        "rail": trace.get("rail", ""),
        "jwtPassthrough": bool(trace.get("jwtPassthrough")),
        "gatewayPassthrough": bool(trace.get("gatewayPassthrough")),
    }


async def _collect_readiness() -> dict[str, Any]:
    """Collect cheap workshop readiness checks without calling Bedrock."""
    from config import settings

    counts = await _workshop_counts()
    checks: list[dict[str, Any]] = []

    if counts is None:
        checks.append(_readiness_check(
            check_id="aurora",
            label="Aurora PostgreSQL",
            state="fail",
            detail="Database unavailable to the backend.",  # copy-allow: agent-trace-readiness-detail
            href="/pellier-labs/search",
        ))
    else:
        catalog_count = counts["catalog_count"]
        warehouse_count = counts["warehouse_count"]
        audit_count = counts["audit_count"]
        checks.append(_readiness_check(
            check_id="aurora",
            label="Aurora PostgreSQL",
            state="pass" if catalog_count >= 40 and warehouse_count > 0 else "fail",
            detail=(
                f"Catalog {catalog_count} products, warehouse "
                f"{warehouse_count} rows, audit ledger {audit_count} rows."
            ),
            href="/pellier-labs/search",
        ))

    cognito_ready = all([
        _configured(settings.cognito_pool_id_resolved),
        _configured(settings.COGNITO_CLIENT_ID),
        _configured(settings.COGNITO_DOMAIN),
    ])
    checks.append(_readiness_check(
        check_id="identity",
        label="Cognito identity",
        state="pass" if cognito_ready else "fail",
        detail=(
            "User pool, app client, and domain configured for JWT passthrough."  # copy-allow: agent-trace-readiness-detail
            if cognito_ready
            else "Missing Cognito pool/client/domain; managed Runtime and Gateway JWT paths cannot run."
        ),
        href="/pellier-labs/production-patterns",
    ))

    checks.append(_readiness_check(
        check_id="memory",
        label="AgentCore Memory",
        state="pass" if _configured(settings.AGENTCORE_MEMORY_ID) else "fail",
        detail=(
            "AGENTCORE_MEMORY_ID set for working and semantic memory."
            if _configured(settings.AGENTCORE_MEMORY_ID)
            else "AGENTCORE_MEMORY_ID empty; memory surfaces fall back where possible."
        ),
        href="/pellier-labs/memory",
    ))

    checks.append(_readiness_check(
        check_id="runtime",
        label="AgentCore Runtime",
        state="pass" if _configured(settings.AGENTCORE_RUNTIME_ENDPOINT) else "fail",
        detail=(
            "Runtime endpoint configured; chat can use the managed rail when USE_AGENTCORE_RUNTIME=true."
            if _configured(settings.AGENTCORE_RUNTIME_ENDPOINT)
            else "AGENTCORE_RUNTIME_ENDPOINT empty; managed runtime invoke cannot be demonstrated."
        ),
        href="/pellier-labs/proof-board#runtime-gateway-policy",
    ))

    checks.append(_readiness_check(
        check_id="gateway",
        label="AgentCore Gateway",
        state="pass" if _configured(settings.AGENTCORE_GATEWAY_URL) else "fail",
        detail=(
            "Gateway URL configured; MCP tool calls can receive the caller JWT."
            if _configured(settings.AGENTCORE_GATEWAY_URL)
            else "AGENTCORE_GATEWAY_URL empty; Gateway/JWT tool calls cannot run."
        ),
        href="/pellier-labs/proof-board#runtime-gateway-policy",
    ))

    policy_engine_id = getattr(settings, "AGENTCORE_POLICY_ENGINE_ID", None)
    checks.append(_readiness_check(
        check_id="policy",
        label="AgentCore Policy",
        state="pass" if _configured(policy_engine_id) else "warn",
        detail=(
            "Managed Cedar policy engine configured for Gateway enforcement."  # copy-allow: agent-trace-readiness-detail
            if _configured(policy_engine_id)
            else "Policy engine id empty; guided policy reads still work, but live Gateway ENFORCE is not visible."
        ),
        required=False,
        href="/pellier-labs/write-path",
    ))

    model_ids = {
        "opus": settings.BEDROCK_OPUS_MODEL,
        "sonnet": settings.BEDROCK_SONNET_MODEL,
        "router": settings.BEDROCK_ROUTER_MODEL,
        "reporting": settings.BEDROCK_REPORTING_MODEL,
        "embedding": settings.BEDROCK_EMBEDDING_MODEL,
        "rerank": settings.BEDROCK_RERANK_MODEL,
    }
    model_ready = all(_configured(v) for v in model_ids.values())
    checks.append(_readiness_check(
        check_id="models",
        label="Bedrock models",
        state="pass" if model_ready else "fail",
        detail=(
            "Opus, Sonnet, Cohere Embed, and Cohere Rerank model ids are configured."  # copy-allow: agent-trace-readiness-detail
            if model_ready
            else "One or more model ids are empty; run the model-access preflight."
        ),
        href="/pellier-labs/settings",
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


def _card_status(condition: bool, fallback: str = "pending") -> str:
    return "complete" if condition else fallback


async def _collect_proof_board(session_id: str | None = None) -> dict[str, Any]:
    """Build Pellier Labs proof-card payload.

    The Proof Board is deliberately a read model. It reports evidence
    from source files, env/config, recent traces, and ``tool_audit``.
    It never calls Bedrock, Gateway, or the Runtime.
    """
    from config import settings

    readiness = await _collect_readiness()
    counts = readiness.get("counts") or {}
    floor_check_wired = not _floor_check_is_workshop_stub()
    latest_floor_check = await _latest_audit_row(tool="floor_check")
    # Retrieval completion needs a retrieval that actually ran. Seeded
    # catalog rows are a precondition for the exercise, not evidence that
    # anyone performed it.
    retrieval_rows = [
        row
        for row in [
            await _latest_audit_row(tool="find_pieces_hybrid"),
            await _latest_audit_row(tool="find_pieces"),
        ]
        if row
    ]
    latest_retrieval = (
        max(retrieval_rows, key=lambda row: row.get("audit_id") or 0)
        if retrieval_rows
        else None
    )
    latest_process_return = await _latest_audit_row(tool="process_return")
    latest_audit = await _latest_audit_row()
    latest_gateway = await _latest_audit_row(caller="gateway")
    managed_receipt = _latest_managed_receipt(session_id)
    policy_engine_id = getattr(settings, "AGENTCORE_POLICY_ENGINE_ID", None)

    runtime_configured = _configured(settings.AGENTCORE_RUNTIME_ENDPOINT)
    gateway_configured = _configured(settings.AGENTCORE_GATEWAY_URL)
    policy_configured = _configured(policy_engine_id)
    identity_configured = all([
        _configured(settings.cognito_pool_id_resolved),
        _configured(settings.COGNITO_CLIENT_ID),
        _configured(settings.COGNITO_DOMAIN),
    ])
    managed_receipt.update({
        "policyConfigured": policy_configured,
        "gatewayAuditPresent": bool(latest_gateway),
        "latestGatewayAuditId": latest_gateway.get("audit_id") if latest_gateway else None,
        "latestGatewayAuditAt": latest_gateway.get("created_at") if latest_gateway else "",
    })

    cards = [
        {
            "id": "marco-floor-check",
            "group": "Agent and tool evidence",
            "title": "Wire Marco to floor_check",
            "status": _card_status(floor_check_wired and bool(latest_floor_check), "needs_run" if floor_check_wired else "needs_build"),
            "required": True,
            "surface": "Code Editor + Pellier",
            "summary": "The Stock Keeper tool is wired and Marco's warehouse turn leaves a floor_check audit row.",
            "evidenceSource": "services.agent_tools.floor_check + pellier.tool_audit",
            "lastUpdated": latest_floor_check.get("created_at") if latest_floor_check else None,
            "evidence": [
                "floor_check source no longer returns the workshop stub" if floor_check_wired else "floor_check still looks like the workshop stub",
                (
                    f"Latest floor_check row: audit_id {latest_floor_check.get('audit_id')}"
                    if latest_floor_check
                    else "No floor_check row found yet"
                ),
            ],
            "fallback": {
                "label": "Terminal fallback",
                "command": (
                    "curl -s http://localhost:8000/api/agent/chat "
                    "-H 'Content-Type: application/json' "
                    "-d '{\"message\":\"Marco needs the floor count for the Kyoto Linen Overshirt in cedar, size M\",\"session_id\":\"marco-proof\"}'"
                ),
            },
            "links": [
                {"label": "Tools", "to": "/pellier-labs/tools"},
                {"label": "Sessions", "to": "/pellier-labs/sessions"},
            ],
        },
        {
            "id": "retrieval-comparison",
            "group": "Retrieval evidence",
            "title": "Compare retrieval strategies",
            "status": _card_status(
                bool(latest_retrieval),
                "needs_run"
                if int(counts.get("catalog_count") or 0) >= 40
                else "needs_data",
            ),
            "required": True,
            "surface": "Pellier + Aurora",
            "summary": "Hybrid search, pgvector, full-text search, and rerank are visible for one shopper query.",
            "evidenceSource": "pellier.tool_audit + pellier.product_catalog",
            "lastUpdated": (
                latest_retrieval.get("created_at") if latest_retrieval else None
            ),
            "evidence": [
                (
                    "Latest retrieval row: "
                    f"{latest_retrieval.get('tool')} "
                    f"audit_id {latest_retrieval.get('audit_id')}"
                    if latest_retrieval
                    else "No retrieval tool call recorded yet — run a shopper "
                    "query so a retrieval row exists"
                ),
                f"Catalog rows: {counts.get('catalog_count', 0)}",
                f"Embedding model: {settings.BEDROCK_EMBEDDING_MODEL}",
                f"Rerank model: {settings.BEDROCK_RERANK_MODEL}",
            ],
            "fallback": {
                "label": "Terminal fallback",
                "command": (
                    "curl -s 'http://localhost:8000/api/search/explain?q=linen%20travel%20shirt&limit=5'"
                ),
            },
            "links": [
                {"label": "Search", "to": "/pellier-labs/search"},
                {"label": "Performance", "to": "/pellier-labs/performance"},
            ],
        },
        {
            "id": "audit-ledger",
            "group": "Operational evidence",
            "title": "Prove the tool_audit ledger",
            "status": _card_status(bool(latest_process_return), "needs_run" if latest_audit else "pending"),
            "required": True,
            "surface": "Aurora SQL",
            "summary": "A write-path action is reconstructible from pellier.tool_audit without depending on a UI panel.",
            "evidenceSource": "pellier.tool_audit",
            "lastUpdated": (
                latest_process_return.get("created_at")
                if latest_process_return
                else latest_audit.get("created_at") if latest_audit else None
            ),
            "evidence": [
                (
                    f"Latest process_return row: audit_id {latest_process_return.get('audit_id')}"
                    if latest_process_return
                    else "No process_return row found yet"
                ),
                (
                    f"Latest audit row: {latest_audit.get('tool')} by {latest_audit.get('caller')}"
                    if latest_audit
                    else "No audit rows found yet"
                ),
            ],
            "fallback": {
                "label": "SQL fallback",
                "command": (
                    "psql \"$DATABASE_URL\" -c \"SELECT audit_id, session_id, tool, caller, args, result "
                    "FROM pellier.tool_audit WHERE tool = 'process_return' ORDER BY audit_id DESC LIMIT 3;\""
                ),
            },
            "links": [
                {"label": "Write-path", "to": "/pellier-labs/write-path"},
            ],
        },
        {
            "id": "runtime-gateway-policy",
            "group": "Managed boundaries",
            "title": "Inspect Runtime, Gateway, and Policy",
            "status": _card_status(runtime_configured and gateway_configured and identity_configured, "needs_config"),
            "required": False,
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
                "label": "Config check",
                "command": "grep -E 'COGNITO|AGENTCORE_(RUNTIME|GATEWAY|POLICY)' pellier/backend/.env",
            },
            "links": [
                {"label": "Write-path", "to": "/pellier-labs/write-path"},
                {"label": "Production patterns", "to": "/pellier-labs/production-patterns"},
            ],
        },
        {
            "id": "managed-rail",
            "group": "Managed boundaries",
            "title": "Inspect the managed rail",
            "status": _card_status(bool(managed_receipt.get("present")), "available"),
            "required": False,
            "surface": "Runtime receipt",
            "summary": "After a managed Runtime turn, the receipt shows whether the request used JWT passthrough and Gateway/MCP.",
            "evidenceSource": "AgentCore Runtime trace + pellier.tool_audit caller=gateway",
            "lastUpdated": latest_gateway.get("created_at") if latest_gateway else None,
            "evidence": [
                (
                    f"Managed receipt rail: {managed_receipt.get('rail')}"
                    if managed_receipt.get("present")
                    else "No managed Runtime receipt yet"
                ),
                f"JWT passthrough: {managed_receipt.get('jwtPassthrough')}",
                f"Gateway passthrough: {managed_receipt.get('gatewayPassthrough')}",
                (
                    f"Latest gateway audit row: audit_id {latest_gateway.get('audit_id')}"
                    if latest_gateway
                    else "No caller='gateway' audit row found yet"
                ),
            ],
            "fallback": {
                "label": "Terminal fallback",
                "command": (
                    "curl -N http://localhost:8000/api/agent/chat "
                    "-H 'Content-Type: application/json' "
                    "-H \"Authorization: Bearer $ACCESS_TOKEN\" "
                    "-d '{\"message\":\"Check floor inventory for BK-01\",\"session_id\":\"managed-proof\"}'"
                ),
            },
            "links": [
                {"label": "Proof Board", "to": "/pellier-labs/proof-board#managed-rail"},
                {"label": "Sessions", "to": "/pellier-labs/sessions"},
            ],
        },
    ]

    return {
        "status": readiness["status"],
        "readiness": readiness,
        "managedReceipt": managed_receipt,
        "cards": cards,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    persona: Optional[str] = Query(default=None, description="Filter by persona ID"),
):
    """Return session list for the active persona.

    Returns fixture data. When a persona filter is provided, only
    sessions matching that persona are returned.
    """
    try:
        data = _load_fixture("sessions")
        if data is None:
            return []
        if persona:
            data = [s for s in data if s.get("personaId") == persona]
        return data
    except Exception as exc:
        logger.error("Failed to load sessions: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load sessions")  # copy-allow: agent-trace-error-detail


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Return full session detail for a given session ID, or 404.

    Checks for a dedicated fixture file first (e.g., session-7f5a.json),
    then falls back to the sessions list for summary-only data.
    """
    try:
        # Try dedicated session detail fixture
        detail = _load_fixture(f"session-{session_id.lower()}")
        if detail is not None:
            return detail

        # Fall back to sessions list for summary data
        sessions = _load_fixture("sessions")
        if sessions:
            for s in sessions:
                if s.get("id", "").upper() == session_id.upper():
                    return s

        raise HTTPException(status_code=404, detail="Session not found")  # copy-allow: agent-trace-error-detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to load session")  # copy-allow: agent-trace-error-detail


@router.get("/agents")
async def list_agents():
    """Return 5 agents with status, tools, and model configuration.

    Returns fixture data matching the frontend agents.json shape.
    """
    try:
        data = _load_fixture("agents")
        if data is None:
            return []
        return data
    except Exception as exc:
        logger.error("Failed to load agents: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load agents")  # copy-allow: agent-trace-error-detail


@router.get("/tools/list")
async def list_tools():
    """Return tools with signatures, status, and metadata (fixture-backed).

    Path is ``/tools/list`` to avoid conflict with the existing
    ``/api/tools`` endpoint on the main app. Returns fixture data
    matching the frontend tools.json shape.
    """
    try:
        data = _load_fixture("tools")
        if data is None:
            return []
        return data
    except Exception as exc:
        logger.error("Failed to load tools: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load tools")  # copy-allow: agent-trace-error-detail


@router.post("/tools/discover", response_model=AgentTraceToolDiscoverResponse)
async def discover_tools_endpoint(payload: AgentTraceToolDiscoverRequest):
    """Semantic tool discovery via pgvector.

    Attempts to use the real database for live pgvector similarity
    search. Falls back to fixture data when the database is unavailable.
    """
    start = time.time()

    # Try real pgvector discovery
    try:
        from app import db_service
        if db_service is not None:
            from services.embeddings import EmbeddingService
            from services.tool_registry import discover_tools

            emb_service = EmbeddingService()
            query_embedding = emb_service.embed_query(payload.query)
            result = await discover_tools(
                db_service, query_embedding, limit=payload.limit
            )

            if result.get("rows"):
                duration_ms = result.get("duration_ms", 0)
                results = []
                for i, row in enumerate(result["rows"], start=1):
                    results.append(AgentTraceToolDiscoverResult(
                        rank=i,
                        tool_id=row.get("tool_id", row.get("name", "")),
                        name=row.get("name", ""),
                        description=row.get("description", ""),
                        similarity=round(row.get("similarity", 0.0), 4),
                        status=_tool_discovery_status(row.get("name", "")),
                    ))
                return AgentTraceToolDiscoverResponse(
                    query=payload.query,
                    results=results,
                    duration_ms=duration_ms,
                    sql=result.get("sql", ""),
                    total_count=result.get("total_count", len(results)),
                )
    except Exception as exc:
        logger.warning("Live tool discovery failed, falling back to fixture: %s", exc)

    # Fallback: return fixture-based results
    duration_ms = int((time.time() - start) * 1000)
    tools_fixture = _load_fixture("tools")
    if tools_fixture is None:
        return AgentTraceToolDiscoverResponse(
            query=payload.query,
            results=[],
            duration_ms=duration_ms,
            sql="-- fixture fallback (no tools fixture found)",
            total_count=0,
        )

    # Simulate discovery by returning tools sorted by relevance to query
    # (simple keyword overlap heuristic for fixture mode)
    query_lower = payload.query.lower()
    scored: list[tuple[float, dict]] = []
    for tool in tools_fixture:
        name = tool.get("functionName", "")
        desc = tool.get("description", "")
        # Simple keyword overlap score
        words = set(query_lower.split())
        tool_words = set((name + " " + desc).lower().split())
        overlap = len(words & tool_words)
        score = 0.95 - (0.08 * (len(scored))) + (0.02 * overlap)
        scored.append((min(score, 0.99), tool))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for i, (score, tool) in enumerate(scored[: payload.limit], start=1):
        results.append(AgentTraceToolDiscoverResult(
            rank=i,
            tool_id=tool.get("functionName", ""),
            name=tool.get("functionName", ""),
            description=tool.get("description", ""),
            similarity=round(score, 4),
            status=tool.get("status", "shipped"),
        ))

    fixture_sql = (
        "-- fixture fallback\n"
        "WITH q AS (SELECT $1::vector AS emb)\n"
        "SELECT tool_id, name, description,\n"
        "       1 - (description_emb <=> (SELECT emb FROM q)) AS similarity\n"
        "FROM pellier.tools WHERE enabled = true\n"
        "ORDER BY description_emb <=> (SELECT emb FROM q)\n"
        f"LIMIT {payload.limit}"
    )

    return AgentTraceToolDiscoverResponse(
        query=payload.query,
        results=results,
        duration_ms=duration_ms,
        sql=fixture_sql,
        total_count=len(tools_fixture),
    )


@router.get("/routing")
async def list_routing():
    """Return 3 routing patterns with active indicator.

    Returns fixture data matching the frontend routing.json shape.
    """
    try:
        data = _load_fixture("routing")
        if data is None:
            return []
        return data
    except Exception as exc:
        logger.error("Failed to load routing patterns: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load routing patterns")  # copy-allow: agent-trace-error-detail


_PERSONA_TO_CUSTOMER_ID = {
    "marco": "CUST-MARCO",
    "anna": "CUST-ANNA",
    "theo": "CUST-THEO",
    "fresh": "CUST-FRESH",
}


async def _load_live_episodic(persona: str) -> Optional[list]:
    """Read the persona's episodic seed rows from Aurora.

    Returns a list of episodic items in the 4-substrate shape, or None
    when the database is unavailable / no rows exist for the persona.
    """
    customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower())
    if not customer_id:
        return None
    try:
        from app import db_service
        if db_service is None:
            return None
        rows = await db_service.fetch_all(
            """
            SELECT id, summary_text, ts_offset_days
              FROM pellier.customer_episodic_seed
             WHERE customer_id = %s
             ORDER BY ts_offset_days DESC NULLS LAST, id DESC
             LIMIT 20
            """,
            customer_id,
        )
        if not rows:
            return None
        items = []
        for r in rows:
            d = dict(r)
            items.append({
                "id": f"ep-live-{d.get('id')}",
                "content": d.get("summary_text", ""),
                "substrate": "episodic",
                "tsOffsetDays": d.get("ts_offset_days"),
            })
        return items
    except Exception as exc:
        logger.warning("Live episodic read failed for %s: %s", persona, exc)
        return None


async def _load_live_procedural() -> Optional[list]:
    """Read procedural knowledge from runtime skills and MCP schemas."""
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
                "content": f"MCP {surface} contract: {', '.join(tool_names)}",
                "substrate": "procedural",
            })
    except Exception as exc:
        logger.warning("Canonical MCP schema read failed from %s: %s", schema_path, exc)

    return items or None


async def _load_live_operational_history() -> Optional[list]:
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
            return None
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
            return None
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
        return None


async def _load_live_working(persona: str) -> Optional[list]:
    """Read the persona's most recent storefront working-memory turns.

    This panel is persona-scoped and carries no session id, so we
    resolve the persona's latest Pellier session the same way the
    lab's section-3 readback does: every allowed tool call stamps its
    ``session_id`` in ``pellier.tool_audit`` (shaped
    ``persona-{persona}-{uuid}``), so we take the most recent one for
    this persona, rebuild the anonymous namespace the storefront wrote
    under (``anon-{session_id}``), and read it back through
    ``AgentCoreMemory.get_session_history`` — which transparently serves
    the live AgentCore SDK on a provisioned box and the in-memory
    fallback otherwise. This is the SAME data ``GET
    /api/agent/session/{id}`` returns, so the panel and that API agree.

    Returns ``None`` (panel falls back to its fixture) when the persona
    has no storefront session yet or the read comes back empty — an
    honest ``fixture`` pill, never a fabricated ``live`` one.
    """
    if persona.lower() not in _PERSONA_TO_CUSTOMER_ID:
        return None
    try:
        from app import db_service
        if db_service is None:
            return None
        # Scope to this persona so a different persona's later tool call
        # (e.g. Anna carrying over) can't shadow Marco's session — the
        # same guard the section-3 psql query uses.
        row = await db_service.fetch_one(
            """
            SELECT session_id
              FROM pellier.tool_audit
             WHERE session_id LIKE %s
             ORDER BY audit_id DESC
             LIMIT 1
            """,
            f"persona-{persona.lower()}-%",
        )
        if not row:
            return None
        session_id = dict(row).get("session_id")
        if not session_id:
            return None

        from services.agentcore_identity import AgentCoreIdentityService
        from services.agentcore_memory import AgentCoreMemory

        # Storefront turns are anonymous, so they live under
        # anon-{session_id} — the exact namespace an unauthenticated
        # GET /api/agent/session/{id} reads.
        namespace = AgentCoreIdentityService.build_namespace(None, session_id)
        memory = AgentCoreMemory()
        turns = await memory.get_session_history(namespace)
    except Exception as exc:
        logger.warning("Live working read failed for %s: %s", persona, exc)
        return None
    if not turns:
        return None
    items = []
    for i, t in enumerate(turns[-6:]):
        items.append({
            "id": f"wk-live-{i}",
            "content": str(t.get("content", ""))[:160],
            "substrate": "working",
            "timestamp": t.get("timestamp"),
        })
    return items


async def _load_live_semantic(persona: str) -> Optional[list]:
    """Read durable, *extracted* preferences from AgentCore Memory.

    These are the semantic records a ``USER_PREFERENCE`` extraction
    strategy learns from conversation and writes under
    ``/pellier/preferences/{customer_id}/`` — learned prose, not the
    typed onboarding ``Preferences`` blob. We read them with the
    dedicated ``get_semantic_memories`` method (NOT
    ``get_user_preferences``, which serves storefront personalization).

    Returns one item per extracted preference string, or None when the
    strategy has not produced records yet (SDK absent, extraction still
    settling, or memory unprovisioned). The route falls back to the
    fixture on None, so the panel reads ``fixture`` — never a fake
    ``live`` — until real extraction lands.
    """
    customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower())
    if not customer_id:
        return None
    try:
        from services.agentcore_memory import AgentCoreMemory
        memory = AgentCoreMemory()
        preferences = await memory.get_semantic_memories(customer_id)
    except Exception as exc:
        logger.warning("Live semantic read failed for %s: %s", persona, exc)
        return None
    if not preferences:
        return None
    items = []
    for idx, pref in enumerate(preferences):
        text = str(pref).strip()
        if not text:
            continue
        items.append({
            "id": f"sem-live-{idx}",
            "content": text[:200],
            "substrate": "semantic",
        })
    return items or None


def _empty_substrate(label: str, store: str) -> dict:
    return {
        "label": label,
        "store": store,
        "source": "fixture",
        "items": [],
    }


@router.get("/memory/{persona}")
async def get_memory(persona: str):
    """Return four memory types plus operational history for a persona.

    Each substrate is sourced honestly:
      working    — AgentCore Memory session turns for the persona's
                   latest storefront session (resolved from
                   pellier.tool_audit, read back under anon-{sid} via
                   the same path as GET /api/agent/session/{id}); live
                   when that session has turns, otherwise the fixture.
      semantic   — AgentCore Memory long-term records under
                   /pellier/preferences/{customer_id}/, extracted by a
                   USER_PREFERENCE strategy; live when the strategy has
                   produced records, otherwise the fixture.
      episodic   — pellier.customer_episodic_seed rows; live when the
                   DB is reachable and the persona has rows, otherwise
                   the fixture (used by personas with no seed data).
      procedural — checked-in runtime skills plus canonical MCP tool
                   schemas; these are instructions and contracts.
      operational— pellier.tool_audit aggregate (calls + average
                   latency per tool). This is execution evidence.

    Read-only.
    """
    try:
        # Real semantic namespace = the USER_PREFERENCE strategy's
        # custom template resolved for this persona's customer_id
        # (e.g. /pellier/preferences/CUST-MARCO/). Falls back to the
        # raw persona for unknown personas so the store string is never
        # blank.
        _sem_customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower(), persona)
        _sem_store = f"/pellier/preferences/{_sem_customer_id}/"

        data = _load_fixture(f"memory-{persona.lower()}")
        if data is None:
            data = {
                "persona": persona,
                "working": _empty_substrate(
                    "Working - AgentCore Memory",
                    f"anon-persona-{persona}-{{sid}}",
                ),
                "semantic": _empty_substrate(
                    "Semantic - AgentCore Memory",
                    _sem_store,
                ),
                "episodic": _empty_substrate(
                    "Episodic - Aurora",
                    "pellier.customer_episodic_seed",
                ),
                "procedural": _empty_substrate(
                    "Procedural - source controlled",
                    "skills/*/SKILL.md + scripts/deploy/gateway_tool_schemas.py",
                ),
                "operational": _empty_substrate(
                    "Operational History - Aurora",
                    "pellier.tool_audit (aggregate)",
                ),
            }
        else:
            # Hand-edited fixtures may still be on the legacy stm/ltm
            # shape during the migration. Normalize to a safe empty
            # four-type-plus-history shell so overlays don't KeyError.
            for key, label, store in (
                ("working", "Working - AgentCore Memory",
                 f"anon-persona-{persona}-{{sid}}"),
                ("semantic", "Semantic - AgentCore Memory",
                 _sem_store),
                ("episodic", "Episodic - Aurora",
                 "pellier.customer_episodic_seed"),
                ("procedural", "Procedural - source controlled",
                 "skills/*/SKILL.md + scripts/deploy/gateway_tool_schemas.py"),
                ("operational", "Operational History - Aurora",
                 "pellier.tool_audit (aggregate)"),
            ):
                if key not in data or not isinstance(data.get(key), dict):
                    data[key] = _empty_substrate(label, store)

        # Never serve the legacy fixture that mislabeled tool activity as
        # procedural memory. These two sources are rebuilt explicitly.
        data["procedural"] = _empty_substrate(
            "Procedural - source controlled",
            "skills/*/SKILL.md + scripts/deploy/gateway_tool_schemas.py",
        )
        data["operational"] = _empty_substrate(
            "Operational History - Aurora",
            "pellier.tool_audit (aggregate)",
        )

        # Live overlays - each promotes source to 'live' on success.
        #
        # The label is promoted with it. Previously only ``items`` and
        # ``source`` were replaced, so a substrate that read successfully from
        # Aurora or AgentCore kept whatever label the seed fixture carried:
        # working memory served ``source: "live"`` under the label
        # "Working - fixture transcript", and the dashboard told attendees the
        # data was seeded when it was not. Promoting both together is what stops
        # the two from disagreeing again.
        _CANONICAL_LABELS = {
            "working": "Working - AgentCore Memory",
            "semantic": "Semantic - AgentCore Memory",
            "episodic": "Episodic - Aurora",
            "procedural": "Procedural - source controlled",
            "operational": "Operational History - Aurora",
        }

        def _promote(key: str, items: list) -> None:
            """Mark one substrate live: its items, its source, and its label."""
            data[key]["items"] = items
            data[key]["source"] = "live"
            data[key]["label"] = _CANONICAL_LABELS[key]

        ep_live = await _load_live_episodic(persona)
        if ep_live:
            _promote("episodic", ep_live)

        proc_live = await _load_live_procedural()
        if proc_live:
            _promote("procedural", proc_live)

        operational_live = await _load_live_operational_history()
        if operational_live:
            _promote("operational", operational_live)

        wk_live = await _load_live_working(persona)
        if wk_live:
            _promote("working", wk_live)

        sem_live = await _load_live_semantic(persona)
        if sem_live:
            _promote("semantic", sem_live)

        return data
    except Exception as exc:
        logger.error("Failed to load memory for %s: %s", persona, exc)
        raise HTTPException(status_code=500, detail="Failed to load memory state")  # copy-allow: agent-trace-error-detail


@router.get("/performance")
async def get_performance():
    """Return performance metrics and benchmarks.

    Returns fixture data matching the frontend performance.json shape.
    """
    try:
        data = _load_fixture("performance")
        if data is None:
            return {
                "coldStartP50": 0,
                "warmReuseP50": 0,
                "sampleCount": 0,
                "histogram": [],
                "latencyBudget": [],
                "pgvectorComparison": [],
                "storageUsage": [],
            }
        return data
    except Exception as exc:
        logger.error("Failed to load performance data: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load performance data")  # copy-allow: agent-trace-error-detail


@router.get("/evaluations")
async def get_evaluations():
    """Return agent evaluation scorecards.

    Returns fixture data matching the frontend evaluations.json shape.
    """
    try:
        data = _load_fixture("evaluations")
        if data is None:
            return []
        return data
    except Exception as exc:
        logger.error("Failed to load evaluations: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load evaluations")  # copy-allow: agent-trace-error-detail


@router.get("/observatory")
async def get_observatory():
    """Return dashboard summary for the Observatory wide-angle view.

    Returns fixture data matching the frontend observatory.json shape.
    """
    try:
        data = _load_fixture("observatory")
        if data is None:
            return {
                "activeSessions": 0,
                "totalSessions": 0,
                "agentStatus": [],
                "toolInvocations": 0,
                "memoryItems": {"stm": 0, "ltm": 0},
                "performanceHeadlines": [],
                "lastUpdated": "",
            }
        return data
    except Exception as exc:
        logger.error("Failed to load observatory data: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load observatory data")  # copy-allow: agent-trace-error-detail


@router.get("/architecture")
async def get_architecture():
    """Return the architecture diagram payload for Pellier Labs Understand surface."""
    try:
        data = _load_fixture("architecture")
        if data is None:
            return {}
        return data
    except Exception as exc:
        logger.error("Failed to load architecture: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load architecture")  # copy-allow: agent-trace-error-detail


@router.get("/build-state")
async def get_build_state():
    """Report the tool implementation and Stock Keeper grant independently.

    Exercise 1 replaces the ``floor_check`` starter body. The later agent step
    grants that tool to Stock Keeper. Reporting the states separately prevents
    a completed function from being mistaken for a completed agent path.

    Shape matches ``BuildStateApiResponse`` in the frontend ``useBuildState`` hook.
    """
    try:
        agents = _load_fixture("agents") or []
        tools = _load_fixture("tools") or []
        agent_map: dict[str, str] = {}
        tool_map: dict[str, str] = {}
        for agent in agents:
            name = agent.get("name")
            status = agent.get("status")
            if isinstance(name, str) and isinstance(status, str):
                agent_map[name] = status
        for tool in tools:
            fn = tool.get("functionName")
            status = tool.get("status")
            if isinstance(fn, str) and isinstance(status, str):
                tool_map[fn] = status

        floor_check_wired = not _floor_check_is_workshop_stub()
        if floor_check_wired:
            tool_map["floor_check"] = "shipped"
        if floor_check_wired and _stock_keeper_has_floor_check_grant():
            agent_map["Stock Keeper"] = "shipped"

        return {"agents": agent_map, "tools": tool_map}
    except Exception as exc:
        logger.error("Failed to build build-state: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load build state")  # copy-allow: agent-trace-error-detail


@router.get("/tools/floor-check/run")
async def run_floor_check(
    product_query: str = Query(
        default="Hadley shirt",
        min_length=1,
        max_length=160,
    ),
):
    """Run the participant's tool implementation before it is agent-granted."""
    if _floor_check_is_workshop_stub():
        raise HTTPException(
            status_code=409,
            detail="floor_check is still in the workshop starter state",
        )

    from services import agent_tools

    floor_check = getattr(
        agent_tools.floor_check,
        "__wrapped__",
        agent_tools.floor_check,
    )
    try:
        raw = await asyncio.to_thread(floor_check, product_query)
        payload = json.loads(raw)
    except Exception as exc:
        logger.error("Participant floor_check verification failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="floor_check did not return its JSON contract",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=500,
            detail="floor_check returned a non-object JSON value",
        )
    return payload


@router.get("/readiness")
async def get_workshop_readiness():
    """Return cheap readiness checks for the live workshop pillars.

    This is the API version of ``scripts/health-gate.sh`` for the
    Pellier Labs. It does not call Bedrock, Runtime, Gateway, or Policy; it
    only reads config and small Aurora counts so participants can open
    the panel without triggering managed services.
    """
    try:
        return await _collect_readiness()
    except Exception as exc:
        logger.error("Failed to build readiness payload: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load readiness")  # copy-allow: agent-trace-error-detail


@router.get("/proof-board")
async def get_proof_board(
    session_id: Optional[str] = Query(
        default=None,
        description="Optional session id for the latest managed Runtime receipt",
    ),
):
    """Return required-path proof cards plus terminal fallbacks.

    The payload is intentionally operational: each card has a stable
    ``id`` for URL anchors, a status, short evidence lines, and a
    curl/SQL fallback. The frontend renders it at
    ``/pellier-labs/proof-board`` and Pellier trace chips deep-link to
    individual anchors.
    """
    try:
        return await _collect_proof_board(session_id=session_id)
    except Exception as exc:
        logger.error("Failed to build proof-board payload: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load proof board")  # copy-allow: agent-trace-error-detail


class AgentTraceSkillRouteRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


@router.post("/skills/route")
async def route_skills_endpoint(payload: AgentTraceSkillRouteRequest):
    """Live skill-router demo for Pellier Labs Skills surface.

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
        logger.warning("Pellier Labs skill route failed: %s", exc)
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
    engine (Gateway-enforced, ENFORCE mode). Used by Pellier Labs'
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
        raise HTTPException(status_code=500, detail="Failed to load policies")  # copy-allow: agent-trace-error-detail


@router.get("/tool-audit/recent")
async def get_recent_tool_audit(
    limit: int = Query(default=10, ge=1, le=50),
    tool: str | None = Query(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
    session_id: str | None = Query(default=None, min_length=1, max_length=128),
    within_minutes: int | None = Query(default=None, ge=1, le=1440),
):
    """Return the most recent rows from pellier.tool_audit, in reverse
    chronological order. Used by the Write-path surface to demonstrate
    that every ALLOWed tool call (read or write) is reconstructible
    from a single row (args + result + latency_ms).

    Args:
        limit: Maximum rows to return.
        tool: Restrict to one tool name.
        session_id: Restrict to one session. Required to prove that a row
            belongs to *this* participant's run rather than to a rehearsal
            or a neighbour's turn.
        within_minutes: Restrict to rows created in the last N minutes.
            The cheap freshness guard for the same problem when the caller
            cannot know the browser-generated session id.

    Read-only. Aggregate against the live DB; falls back to empty list
    when the database is unavailable.
    """
    filters = {
        "tool": tool,
        "sessionId": session_id,
        "withinMinutes": within_minutes,
    }
    try:
        from app import db_service
        if db_service is None:
            return {
                "source": "pellier.tool_audit",
                "filters": filters,
                "count": 0,
                "rows": [],
            }

        clauses: list[str] = []
        params: list[Any] = []
        if tool:
            clauses.append("tool = %s")
            params.append(tool)
        if session_id:
            clauses.append("session_id = %s")
            params.append(session_id)
        if within_minutes:
            clauses.append(
                "created_at >= NOW() - (%s * INTERVAL '1 minute')"
            )
            params.append(within_minutes)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = await db_service.fetch_all(
            f"""
            SELECT audit_id,
                   session_id,
                   tool,
                   caller,
                   args,
                   result,
                   latency_ms,
                   created_at
              FROM pellier.tool_audit
              {where}
             ORDER BY audit_id DESC
             LIMIT %s
            """,
            *params,
        )
        normalized = []
        for r in rows:
            d = dict(r)
            # JSON columns come back as Python dicts already, but normalize
            # created_at to an ISO string for the JSON response.
            if d.get("created_at") is not None:
                d["created_at"] = d["created_at"].isoformat()
            normalized.append(d)
        return {
            "source": "pellier.tool_audit",
            "filters": filters,
            "count": len(normalized),
            "rows": normalized,
        }
    except Exception as exc:
        logger.error("Failed to load tool_audit: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load tool audit")  # copy-allow: agent-trace-error-detail
