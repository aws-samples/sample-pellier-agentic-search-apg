"""``/api/atelier/*`` — Atelier Observatory read-only API endpoints.

This router provides the backend data layer for the Atelier Observatory
frontend surfaces. All endpoints are read-only and return fixture data
initially, with graceful degradation when the database is unavailable.

Endpoints are additive to the existing ``routes/workshop.py`` router
(which also mounts at ``/api/atelier/``). No path conflicts — workshop
owns ``/query``, ``/resume``, ``/tool-registry``; this router owns the
observatory surface endpoints listed below.

Endpoints:
    GET  /sessions             — session list for persona
    GET  /sessions/{id}        — full session detail or 404
    GET  /agents               — 5 agents with status, tools, model config
    GET  /tools                — tools with signatures, status, metadata
    POST /tools/discover       — pgvector semantic search
    GET  /routing              — 3 routing patterns with active indicator
    GET  /memory/{persona}     — four-substrate memory state (working / semantic / episodic / procedural) for persona
    GET  /performance          — metrics and benchmarks
    GET  /evaluations          — agent scorecards
    GET  /observatory          — dashboard summary
    GET  /architecture         — system architecture diagram payload
    GET  /build-state          — shipped vs exercise maps for agents and tools
    POST /skills/route         — Live skill router demo (Haiku 4.5 @ 0.0)
    GET  /policies             — Cedar policies for the Write-path surface
    GET  /tool-audit/recent    — Recent rows from pellier.tool_audit
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/atelier", tags=["atelier-observatory"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AtelierSessionSummary(BaseModel):
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


class AtelierToolDiscoverRequest(BaseModel):
    """Request body for the tool discovery endpoint."""
    query: str = Field(
        default="show me something for long summer walks",
        min_length=1,
        description="Natural-language query for semantic tool discovery",
    )
    limit: int = Field(default=5, ge=1, le=9)


class AtelierToolDiscoverResult(BaseModel):
    """A single tool discovery result with similarity score."""
    rank: int
    tool_id: str
    name: str
    description: str
    similarity: float
    status: str


class AtelierToolDiscoverResponse(BaseModel):
    """Response from the tool discovery endpoint."""
    query: str
    results: list[AtelierToolDiscoverResult]
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
    / "atelier"
    / "fixtures"
)

_fixture_cache: dict[str, Any] = {}


def _load_fixture(name: str) -> Any:
    """Load a fixture JSON file from the frontend fixtures directory.

    Results are cached in memory after first load. Returns None if the
    file doesn't exist or can't be parsed.
    """
    if name in _fixture_cache:
        return _fixture_cache[name]
    path = _FIXTURE_DIR / f"{name}.json"
    try:
        data = json.loads(path.read_text())
        _fixture_cache[name] = data
        return data
    except FileNotFoundError:
        logger.warning("Fixture file not found: %s", path)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("Fixture file malformed: %s — %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Tool / build state helpers (fixtures + Builder's Session live overlay)
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
    """Status for discovery rows — matches Atelier Tools surface / fixtures."""
    return _fixture_tool_status_map().get(tool_name, "shipped")


def _floor_check_is_workshop_stub() -> bool:
    """True when the live ``floor_check`` body still returns the starter stub."""
    try:
        import inspect
        from services import agent_tools

        src = inspect.getsource(agent_tools.floor_check)
    except Exception:
        return True
    if "floor_check is in stub state" in src:
        return True
    if "received_product_query" in src:
        return True
    return False


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
        raise HTTPException(status_code=500, detail="Failed to load sessions")  # copy-allow: atelier-error-detail


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

        raise HTTPException(status_code=404, detail="Session not found")  # copy-allow: atelier-error-detail
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to load session")  # copy-allow: atelier-error-detail


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
        raise HTTPException(status_code=500, detail="Failed to load agents")  # copy-allow: atelier-error-detail


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
        raise HTTPException(status_code=500, detail="Failed to load tools")  # copy-allow: atelier-error-detail


@router.post("/tools/discover", response_model=AtelierToolDiscoverResponse)
async def discover_tools_endpoint(payload: AtelierToolDiscoverRequest):
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
                    results.append(AtelierToolDiscoverResult(
                        rank=i,
                        tool_id=row.get("tool_id", row.get("name", "")),
                        name=row.get("name", ""),
                        description=row.get("description", ""),
                        similarity=round(row.get("similarity", 0.0), 4),
                        status=_tool_discovery_status(row.get("name", "")),
                    ))
                return AtelierToolDiscoverResponse(
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
        return AtelierToolDiscoverResponse(
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
        results.append(AtelierToolDiscoverResult(
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

    return AtelierToolDiscoverResponse(
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
        raise HTTPException(status_code=500, detail="Failed to load routing patterns")  # copy-allow: atelier-error-detail


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
    """Aggregate live tool_audit rows into procedural patterns.

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
                "id": f"proc-live-{i}",
                "content": (
                    f"{d.get('tool')} - fired {d.get('calls')}x, "
                    f"avg {d.get('avg_ms')}ms"
                ),
                "substrate": "procedural",
            })
        return items
    except Exception as exc:
        logger.warning("Live procedural read failed: %s", exc)
        return None


async def _load_live_working(persona: str) -> Optional[list]:
    """Read recent working-memory turns from AgentCore Memory.

    Atelier doesn't carry a session_ns into this read-only endpoint,
    so we probe the in-memory fallback store for any namespace whose
    user_id matches the persona's customer_id. When AgentCore is
    provisioned the SDK path is queried with the same actor_id; both
    return [] for a fresh persona, in which case we fall back to the
    fixture so the panel always has something to teach.
    """
    customer_id = _PERSONA_TO_CUSTOMER_ID.get(persona.lower())
    if not customer_id:
        return None
    try:
        from services.agentcore_memory import _SESSION_STORE  # type: ignore[attr-defined]
    except Exception:
        return None
    prefix = f"user-{customer_id}-session-"
    turns: list[dict] = []
    for ns, ns_turns in _SESSION_STORE.items():
        if not ns.startswith(prefix):
            continue
        turns.extend(ns_turns)
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
    """Return the 4-substrate memory state for a persona.

    Each substrate is sourced honestly:
      working    — AgentCore Memory session turns under
                   user-{customer_id}-session-{sid}; live when any
                   namespace exists, otherwise the fixture.
      semantic   — AgentCore Memory long-term records under
                   /pellier/preferences/{customer_id}/, extracted by a
                   USER_PREFERENCE strategy; live when the strategy has
                   produced records, otherwise the fixture.
      episodic   — pellier.customer_episodic_seed rows; live when the
                   DB is reachable and the persona has rows, otherwise
                   the fixture (used by personas with no seed data).
      procedural — pellier.tool_audit aggregate (calls + avg latency
                   per tool, every ALLOWed call - reads and writes
                   alike). Promotes to 'live' when the aggregate
                   succeeds; the caveat persists because the schema
                   still lacks intent/persona_id/success columns.

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
                    f"user-{persona}-session-{{sid}}",
                ),
                "semantic": _empty_substrate(
                    "Semantic - AgentCore Memory",
                    _sem_store,
                ),
                "episodic": _empty_substrate(
                    "Episodic - Aurora",
                    "pellier.customer_episodic_seed",
                ),
                "procedural": {
                    **_empty_substrate(
                        "Procedural - Aurora",
                        "pellier.tool_audit (aggregate)",
                    ),
                    "source": "sketch",
                    "caveat": (
                        "tool_audit records every ALLOWed tool call but "
                        "lacks intent / persona_id / success columns "
                        "today - this panel sketches the shape the "
                        "aggregate will take once they land."
                    ),
                },
            }
        else:
            # Hand-edited fixtures may still be on the legacy stm/ltm
            # shape during the migration. Normalize to a safe empty
            # 4-substrate shell so downstream overlays don't KeyError.
            for key, label, store in (
                ("working", "Working - AgentCore Memory",
                 f"user-{persona}-session-{{sid}}"),
                ("semantic", "Semantic - AgentCore Memory",
                 _sem_store),
                ("episodic", "Episodic - Aurora",
                 "pellier.customer_episodic_seed"),
                ("procedural", "Procedural - Aurora",
                 "pellier.tool_audit (aggregate)"),
            ):
                if key not in data or not isinstance(data.get(key), dict):
                    data[key] = _empty_substrate(label, store)

        # Live overlays - each promotes source to 'live' on success.
        ep_live = await _load_live_episodic(persona)
        if ep_live:
            data["episodic"]["items"] = ep_live
            data["episodic"]["source"] = "live"

        proc_live = await _load_live_procedural()
        if proc_live:
            data["procedural"]["items"] = proc_live
            data["procedural"]["source"] = "live"
            # Caveat persists even when source flips to 'live' - the
            # items are real aggregates from tool_audit, but the
            # schema gap (no intent/persona/success columns) is real
            # too and worth teaching.

        wk_live = await _load_live_working(persona)
        if wk_live:
            data["working"]["items"] = wk_live
            data["working"]["source"] = "live"

        sem_live = await _load_live_semantic(persona)
        if sem_live:
            data["semantic"]["items"] = sem_live
            data["semantic"]["source"] = "live"

        return data
    except Exception as exc:
        logger.error("Failed to load memory for %s: %s", persona, exc)
        raise HTTPException(status_code=500, detail="Failed to load memory state")  # copy-allow: atelier-error-detail


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
        raise HTTPException(status_code=500, detail="Failed to load performance data")  # copy-allow: atelier-error-detail


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
        raise HTTPException(status_code=500, detail="Failed to load evaluations")  # copy-allow: atelier-error-detail


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
        raise HTTPException(status_code=500, detail="Failed to load observatory data")  # copy-allow: atelier-error-detail


@router.get("/architecture")
async def get_architecture():
    """Return the architecture diagram payload for the Atelier Understand surface."""
    try:
        data = _load_fixture("architecture")
        if data is None:
            return {}
        return data
    except Exception as exc:
        logger.error("Failed to load architecture: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load architecture")  # copy-allow: atelier-error-detail


@router.get("/build-state")
async def get_build_state():
    """Shipped vs exercise for agents and tools (fixtures + live lab overlay).

    Loads ``agents.json`` / ``tools.json`` then, when ``floor_check`` in
    ``services.agent_tools`` is no longer the Builder's Session stub,
    marks ``floor_check`` and **Stock Keeper** as shipped so the Atelier
    progress strip matches a completed Part I exercise.

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

        if not _floor_check_is_workshop_stub():
            tool_map["floor_check"] = "shipped"
            agent_map["Stock Keeper"] = "shipped"

        return {"agents": agent_map, "tools": tool_map}
    except Exception as exc:
        logger.error("Failed to build build-state: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load build state")  # copy-allow: atelier-error-detail


class AtelierSkillRouteRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


@router.post("/skills/route")
async def route_skills_endpoint(payload: AtelierSkillRouteRequest):
    """Live skill-router demo for the Atelier Skills surface.

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
        logger.warning("Atelier skill route failed: %s", exc)
        return {
            "loaded_skills": [],
            "considered": [],
            "elapsed_ms": 0,
            "user_message": payload.query[:500],
            "error": str(exc),
        }


@router.get("/policies")
async def get_cedar_policies():
    """Return the Cedar policies attached to the managed AgentCore Policy
    engine (Gateway-enforced, ENFORCE mode). Used by the Atelier's
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
        raise HTTPException(status_code=500, detail="Failed to load policies")  # copy-allow: atelier-error-detail


@router.get("/tool-audit/recent")
async def get_recent_tool_audit(limit: int = Query(default=10, ge=1, le=50)):
    """Return the most recent rows from pellier.tool_audit, in reverse
    chronological order. Used by the Write-path surface to demonstrate
    that every ALLOWed tool call (read or write) is reconstructible
    from a single row (args + result + latency_ms).

    Read-only. Aggregate against the live DB; falls back to empty list
    when the database is unavailable.
    """
    try:
        from app import db_service
        if db_service is None:
            return {"count": 0, "rows": []}

        rows = await db_service.fetch_all(
            """
            SELECT audit_id,
                   session_id,
                   tool,
                   caller,
                   args,
                   result,
                   latency_ms,
                   created_at
              FROM pellier.tool_audit
             ORDER BY audit_id DESC
             LIMIT %s
            """,
            limit,
        )
        normalized = []
        for r in rows:
            d = dict(r)
            # JSON columns come back as Python dicts already, but normalize
            # created_at to an ISO string for the JSON response.
            if d.get("created_at") is not None:
                d["created_at"] = d["created_at"].isoformat()
            normalized.append(d)
        return {"count": len(normalized), "rows": normalized}
    except Exception as exc:
        logger.error("Failed to load tool_audit: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load tool audit")  # copy-allow: atelier-error-detail
