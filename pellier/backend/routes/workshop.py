"""``/api/atelier/*`` — telemetry-replay endpoint for the DAT406 /atelier route.

This router is the backend half of the PostgresConf Builders Session
(DAT406) telemetry surface. Unlike ``/api/agent/chat`` — which streams
storefront-shaped SSE events (product cards, cart ops, badges) for
``ConciergeModal`` — this endpoint returns a single flat replay payload:

    POST /api/atelier/query
    → {
        "session_id": "...",
        "events": [
          {"type": "plan",  "steps": [...], ...},
          {"type": "step",  "index": 0, "state": "active"},
          {"type": "panel", "tag": "LLM · HAIKU · INTENT", ...},
          ...
          {"type": "response", "text": "...", "citations": [...]}
        ]
      }

The frontend's ``WorkshopChat`` + ``TelemetryStream`` components iterate
the events list with per-type animation beats (see
``conferences/2026-postgresconf-agentic-ai/static/index.html`` playEvents()).

**Not an SSE stream.** Returns one consolidated JSON blob at
end-of-turn. The frontend replays events with variable cadence delays
(LLM panels slow, Postgres panels fast) to sell the streaming illusion.
Promote to SSE when per-turn time exceeds ~6s or multiplayer replay is
needed — the event dict shape is already SSE-compatible.

**Session continuity.** The caller may pass ``session_id`` or let the
endpoint mint one. The value round-trips to ``AgentContext.session_id``
and is echoed back in the response so the SPA can persist it to
localStorage (same key the other chat surfaces use).

Week 1 scope: the endpoint wires up the AgentContext + orchestrator hand-off
and returns a minimally populated events list (a canned PLAN card + the
orchestrator's final text as a ``response`` event). Panels #1-11 arrive
as the specialists and orchestrator get instrumented in Weeks 2-6.
"""

from __future__ import annotations

import asyncio
import json as json_mod
import logging
import uuid
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.agent_context import AgentContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/atelier", tags=["atelier"])


def _build_citations(ctx: AgentContext) -> list[dict]:
    """Build citation dicts from emitted panels.

    Each panel that returned real data (non-empty rows) gets a citation
    so the chat column renders clickable "trace N" pills that scroll
    the telemetry tab to the source panel.

    Skipped/error panels (empty rows + error in meta) are excluded —
    citing a panel that says "no data" is misleading.
    """
    citations = []
    for ev in ctx.events:
        if ev.get("type") != "panel":
            continue
        rows = ev.get("rows") or []
        meta = ev.get("meta", "")
        # Skip panels with no data or error states
        if not rows and ("error" in meta.lower() or "skipped" in meta.lower() or "not set" in meta.lower()):
            continue
        trace_idx = ev.get("trace_index")
        if trace_idx is None:
            continue
        citations.append({
            "k": ev.get("tag", ""),
            "ref": f"trace {trace_idx}",
        })
    return citations


# ----- /api/workshop/tool-registry ---------------------------------------
# Card 7 dual-ranking fetch. The frontend opens Card 7, passes a demo
# query (defaulted if omitted), and gets back { pgvector_rows, gateway }
# so the modal renders Aurora and Gateway side-by-side. Gateway-unset is
# a first-class response shape — ``gateway.configured = false`` — rather
# than a quiet empty list, because the teaching point is *seeing* the
# single-source fallback, not guessing why it's empty.


class ToolRegistryQuery(BaseModel):
    query: str = Field(
        default="show me something for long summer walks",
        description="Demo query for the Card 7 dual-ranking fetch. Workshop "
        "attendees can override via the Card 7 input field.",
        min_length=1,
    )
    limit: int = Field(default=3, ge=1, le=9)


@router.post("/tool-registry")
async def tool_registry(payload: ToolRegistryQuery) -> dict[str, Any]:
    """Dual-rank tool discovery for Card 7.

    Returns:
        {
          "query": str,
          "pgvector": {
            "rows": [ {name, description, similarity}, ... ],
            "duration_ms": int,
            "total_count": int,
            "error": str | None,
          },
          "gateway": {
            "configured": bool,
            "url": str | None,
            "tools": [ {name, description, input_schema}, ... ],
            "error": str | None,
          }
        }
    """
    from services.embeddings import EmbeddingService
    from services.tool_registry import discover_tools
    from app import db_service  # lifespan-initialised

    if db_service is None:
        raise HTTPException(status_code=503, detail="Database not ready")  # copy-allow: http-error-detail

    # Aurora side — always runs.
    pgvector_block: dict[str, Any]
    try:
        emb = EmbeddingService().embed_query(payload.query)
        pgv = await discover_tools(db_service, emb, limit=payload.limit)
        pgvector_block = {
            "rows": pgv["rows"],
            "duration_ms": pgv["duration_ms"],
            "total_count": pgv["total_count"],
            "error": pgv.get("error"),
        }
    except Exception as exc:
        logger.warning("Card 7 pgvector fetch failed: %s", exc)
        pgvector_block = {
            "rows": [],
            "duration_ms": 0,
            "total_count": 0,
            "error": str(exc),
        }

    # Gateway side — reports "not configured" as a first-class state.
    from config import settings

    gateway_block: dict[str, Any] = {
        "configured": bool(settings.AGENTCORE_GATEWAY_URL),
        "url": settings.AGENTCORE_GATEWAY_URL,
        "tools": [],
        "error": None,
    }
    if gateway_block["configured"]:
        try:
            from services.agentcore_gateway import list_gateway_tools

            gateway_block["tools"] = list_gateway_tools()
        except Exception as exc:
            gateway_block["error"] = str(exc)
            logger.warning("Card 7 gateway list failed: %s", exc)

    return {
        "query": payload.query,
        "pgvector": pgvector_block,
        "gateway": gateway_block,
    }


class WorkshopQueryRequest(BaseModel):
    """Body of ``POST /api/atelier/query``.

    ``customer_id`` is optional — the workshop chat starts as anonymous.
    When a demo customer is picked from the user dropdown (Week 1 UI),
    it's passed here so the recommendation agent's ``MEMORY · PROCEDURAL``
    query excludes that customer from the cohort-overlap result.
    """

    query: str = Field(..., min_length=1, description="Shopper / operator question")
    session_id: Optional[str] = Field(
        default=None,
        description="Stable across turns. Omit on first turn; echo back from the previous response.",
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="Seeded demo customer id (e.g. 'CUST-MARCO'). None ⇒ anonymous.",
    )


class WorkshopQueryResponse(BaseModel):
    """Flat replay payload. Keep the shape identical to Coffee Roastery's
    ``/api/query`` so the frontend renderer is a straight port."""

    session_id: str
    events: list[dict[str, Any]]


@router.post("/query")
async def query(payload: WorkshopQueryRequest) -> StreamingResponse:
    """Run one workshop turn, streaming events via SSE as they're emitted.

    Each SSE message is ``data: <json>\\n\\n`` where json is the same
    event dict shape the blob endpoint used to return. The final message
    is ``data: [DONE]\\n\\n`` so the client knows the stream is complete.

    The frontend reads via ``fetch()`` + ``ReadableStream`` (POST body,
    so EventSource won't work). Events push into the same state array
    the buffered replay used — minimal frontend change.

    Promote to full mid-orchestrator streaming when AgentContext is
    threaded through the specialist agents. For now, pre-orchestrator
    events (plan, text, panels) yield immediately, the orchestrator
    blocks, then post-orchestrator events (steps, response) yield.
    """
    session_id = payload.session_id or f"ws-{uuid.uuid4().hex[:12]}"
    customer_id = payload.customer_id or "anonymous"

    async def event_stream() -> AsyncGenerator[str, None]:
        ctx = AgentContext(
            session_id=session_id,
            customer_id=customer_id,
            query=payload.query.strip(),
        )
        # Track how many events we've yielded so we can send new ones
        # as they're emitted by the sync helpers.
        yielded = 0

        def flush() -> str:
            """Yield all new events since last flush as SSE messages."""
            nonlocal yielded
            out = ""
            while yielded < len(ctx.events):
                ev = ctx.events[yielded]
                out += f"data: {json_mod.dumps(ev)}\n\n"
                yielded += 1
            return out

        # --- Triage fast-path ---------------------------------------------
        # Same deterministic short-circuit as /api/chat/stream. Ensures
        # "hi" / "what can you do" / "thanks" demos don't route through
        # recommendation and risk the empty-LLM failure
        # mode. Panel emission is skipped entirely; one TRIAGE panel
        # gives the telemetry tab something to render.
        from services.chat import classify_triage, _TRIAGE_REPLIES

        triage_bucket = classify_triage(ctx.query)
        if triage_bucket:
            logger.info(
                "🎯 Triage (workshop) | %s | msg=%r", triage_bucket, ctx.query[:60]
            )
            ctx.emit_plan(
                steps=["Classify", "Reply"],
                duration_ms=0,
                title="Triage",
            )
            ctx.step_active(0)
            yield flush()
            ctx.emit_panel(
                agent="triage",
                tag="LLM · TRIAGE",
                tag_class="amber",
                title=f"Classified as {triage_bucket}",
                sql="",
                columns=["bucket", "reason"],
                rows=[[triage_bucket, "deterministic keyword match"]],
                meta="orchestrator skipped — small-talk short-circuit",
                duration_ms=0,
            )
            ctx.step_done(0)
            ctx.step_active(1)
            yield flush()
            ctx.emit_response(
                text=_TRIAGE_REPLIES[triage_bucket],
                citations=[],
                confidence=None,
            )
            ctx.step_done(1)
            yield flush()
            yield "data: [DONE]\n\n"
            return

        # --- Phase 1: Plan + pre-orchestrator panels (immediate) ---------
        ctx.emit_plan(
            steps=["Parse intent", "Route to specialist", "Compose response"],
            duration_ms=0,
            title="Plan",
        )
        ctx.step_active(0)
        yield flush()

        try:
            from services.chat import EnhancedChatService as ChatService
            from app import db_service

            if db_service is None:
                raise RuntimeError("Database service not initialised")

            try:
                from services.embeddings import EmbeddingService
                from services.episodic_memory import emit_memory_episodic_panel
                from services.workshop_panels import (
                    emit_gateway_panel,
                    emit_tool_registry_panel,
                )

                emb_service = EmbeddingService()
                turn_embedding = emb_service.embed_query(ctx.query)

                ctx.emit_text("Looking through your history and our catalog...")
                yield flush()

                await emit_memory_episodic_panel(ctx, db_service=db_service)
                yield flush()

                await emit_tool_registry_panel(
                    ctx, db_service=db_service, query_embedding=turn_embedding
                )
                yield flush()

                ctx.emit_text("Cross-referencing what matches...")
                yield flush()

                emit_gateway_panel(ctx, query_text=ctx.query)
                yield flush()

            except Exception as panel_exc:
                logger.warning("Panel emission failed: %s", panel_exc)

            # --- Phase 2: Orchestrator (blocking) ----------------------------
            chat_service = ChatService(db_service=db_service)

            ctx.emit_text("Routing to the right specialist...")
            yield flush()

            result = await chat_service.chat(
                message=ctx.query,
                conversation_history=None,
                session_id=ctx.session_id,
                guardrails_enabled=False,
            )

            # --- Phase 3: Post-orchestrator (immediate) ----------------------
            ctx.step_done(0)
            ctx.step_active(1)
            ctx.step_done(1)
            ctx.step_active(2)
            yield flush()

            response_text = result.get("response") or "(no response)"
            citations = _build_citations(ctx)
            ctx.emit_response(
                text=response_text, citations=citations, confidence=None
            )
            ctx.step_done(2)
            yield flush()

        except Exception as exc:
            logger.exception("Workshop turn failed: %s", exc)
            ctx.emit_response(
                text=f"Workshop turn failed: {exc.__class__.__name__}: {exc}",
                confidence=None,
            )
            yield flush()

        # Session id as a meta event so the client can persist it.
        yield f"data: {json_mod.dumps({'type': 'meta', 'session_id': session_id})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ----- /api/workshop/resume ---------------------------------------------
# The "welcome-back" turn. Fired by the Atelier chat when the user
# picks a seeded demo customer and no session_id exists yet. Emits
# three cohesive panels — MEMORY · EPISODIC, MEMORY · PREFERENCES,
# MEMORY · PROCEDURAL — plus a composed response text the chat
# column renders as the first assistant reply.
#
# Separate from /query so the frontend can auto-fire it on customer
# change without the user typing a pseudo-query, and so the backend
# doesn't have to branch on a sentinel query string. Same response
# shape as /query, so the frontend renderer is shared.


class WorkshopResumeRequest(BaseModel):
    """Body of ``POST /api/atelier/resume``.

    Anonymous callers get a 400 — the resume turn is specifically the
    "welcome-back for a known demo customer" surface. The chat column
    never fires this for anonymous.
    """

    customer_id: str = Field(
        ...,
        min_length=1,
        description="Seeded demo customer id (e.g. 'CUST-MARCO').",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional — resume into an existing session if the chat already has one.",
    )


def _compose_resume_text(
    customer_name: str,
    preferences_summary: Optional[str],
    latest_episode: Optional[str],
    cohort_top_product: Optional[str],
) -> str:
    """Build the welcome-back assistant text deterministically.

    No LLM call — this is the teaching moment about continuity, not
    about generation. The text quotes the three memory reads so the
    attendee can map each clause to the panel that sourced it.
    """
    first_name = customer_name.split(" ", 1)[0] if customer_name else "there"
    parts = [f"Welcome back, {first_name}."]
    if latest_episode:
        parts.append(f"Last time: {latest_episode}")
    if preferences_summary:
        parts.append(f"Your preferences on file: {preferences_summary}")
    if cohort_top_product:
        parts.append(
            f"Customers with a similar history recently picked up {cohort_top_product}."
        )
    parts.append("Want to pick that thread up, or start somewhere new?")
    return " ".join(parts)


@router.post("/resume", response_model=WorkshopQueryResponse)
async def resume(payload: WorkshopResumeRequest) -> WorkshopQueryResponse:
    """Replay the three MEMORY panels + emit a welcome-back response.

    Panel order mirrors the teaching flow — EPISODIC first ("who are
    you?"), PREFERENCES next ("what do we know?"), PROCEDURAL last
    ("what might we suggest?"). The composed response text references
    all three so the trace reads end-to-end.
    """
    customer_id = payload.customer_id.strip()
    if customer_id == "anonymous" or not customer_id:
        raise HTTPException(  # copy-allow: http-error-detail
            status_code=400,
            detail="resume requires a seeded customer_id",
        )

    session_id = payload.session_id or f"ws-{uuid.uuid4().hex[:12]}"
    ctx = AgentContext(
        session_id=session_id,
        customer_id=customer_id,
        query="(resumed session)",
    )

    ctx.emit_plan(
        steps=["Recall", "Summarize", "Offer"],
        duration_ms=0,
        title="Resume",
    )
    ctx.step_active(0)

    try:
        from services.episodic_memory import (
            emit_memory_episodic_panel,
            emit_memory_preferences_panel,
            emit_memory_procedural_panel,
        )
        from app import db_service  # populated by lifespan startup

        if db_service is None:
            raise RuntimeError("Database service not initialised")

        episodes = await emit_memory_episodic_panel(ctx, db_service=db_service)
        ctx.step_done(0)
        ctx.step_active(1)

        prefs_row = await emit_memory_preferences_panel(ctx, db_service=db_service)
        cohort = await emit_memory_procedural_panel(ctx, db_service=db_service)
        ctx.step_done(1)
        ctx.step_active(2)

        latest_episode = (
            episodes[0]["summary_text"].rstrip(".") if episodes else None
        )
        preferences_summary = (
            (prefs_row or {}).get("preferences_summary") if prefs_row else None
        )
        customer_name = (prefs_row or {}).get("name", customer_id) if prefs_row else customer_id
        cohort_top_product = cohort[0].get("name") if cohort else None

        text = _compose_resume_text(
            customer_name=customer_name,
            preferences_summary=preferences_summary,
            latest_episode=latest_episode,
            cohort_top_product=cohort_top_product,
        )
        ctx.emit_response(text=text, confidence=None)
        ctx.step_done(2)

    except Exception as exc:
        logger.exception("Workshop resume failed: %s", exc)
        ctx.emit_response(
            text=f"Workshop resume failed: {exc.__class__.__name__}: {exc}",
            confidence=None,
        )

    return WorkshopQueryResponse(
        session_id=ctx.session_id,
        events=ctx.events,
    )
