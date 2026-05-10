"""``/api/agent/*`` routes — SSE chat + session history (Task 3.5).

Implements Requirements 3.4.1–3.4.4 and the Design "Error Handling" row
"JWT expires mid-SSE stream" (Sequence Diagram #2 note):

  * ``POST /api/agent/chat``         stream orchestrator output over SSE.
  * ``GET  /api/agent/session/{id}`` return multi-turn history scoped to
                                     the verified user.

Design notes
------------

* **One-shot JWT validation.** The JWT is validated EXACTLY ONCE at
  stream start via ``CognitoAuthService.extract_user`` + the
  ``AgentCoreIdentityService.get_verified_user_context`` resolver. We
  deliberately do NOT re-check the token per chunk — mid-stream token
  expiry must not abort an already-running response (per Design
  "Error Handling" row and Sequence Diagram #2 note). Silent refresh
  fires on the next request.
* **Anonymous fallback.** Requests without a valid token still stream.
  ``AgentCoreIdentityService`` returns an ``anon:{session_id}``
  namespace and the orchestrator runs with ``user_id=None``. Session
  history for these shoppers is keyed by ``anon:{session_id}`` and is
  never merged into a user namespace later (Req 4.3.3).
* **Session continuity.** ``session_id`` is resolved by the identity
  service in this priority:
    1. ``X-Session-Id`` header (subsequent turns from the SPA)
    2. ``session_id`` cookie (browser page reload path)
    3. auto-generated uuid4 (first-ever turn)
  The first SSE event always carries the resolved ``session_id`` so the
  client can persist it and pass it back on the next call (Req 3.4.3).
* **SSE event format.** We use the standard ``text/event-stream``
  format: each event is ``event: <type>\\ndata: <json>\\n\\n``. Three
  event types:
    - ``session``  — first event, carries the resolved session_id
                     (and, when present, the anonymous namespace key)
    - ``chunk``    — incremental response text
    - ``done``     — final event, carries the extracted OTel trace
    - ``error``    — emitted instead of ``done`` when the agent call
                     raises; stream ends immediately after
* **Runtime dispatch.** ``services.agentcore_runtime.run_agent`` branches
  on ``settings.USE_AGENTCORE_RUNTIME`` so this route handles both C4
  (in-process Strands) and C5 (managed runtime) without branching here.
  Since ``run_agent`` returns a single string rather than an async
  iterator, we emit the full response as a single ``chunk`` event plus
  a ``done`` trailer. The wire shape is ready for a streamed
  implementation — swapping to an async iterator in
  ``agentcore_runtime`` only touches ``_stream_agent_response`` below.
* **Memory writes.** The turn pair (user + assistant) is appended to
  ``AgentCoreMemory`` under the identity-service namespace after the
  agent response completes. A failed write does not fail the stream —
  it is logged and the user-visible stream still closes cleanly.

Routes are NOT part of any workshop challenge block. This file ships
without ``# === CHALLENGE ... ===`` markers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from services.agentcore_identity import (
    AgentCoreIdentityService,
    UserContext,
    get_agentcore_identity_service,
)
from services.agentcore_memory import AgentCoreMemory
from services.agentcore_runtime import get_latest_trace, run_agent
from routes.user import get_agentcore_memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Incoming chat payload.

    ``session_id`` is optional: when omitted, the identity service
    resolves it from the ``X-Session-Id`` header / ``session_id`` cookie
    and falls back to a fresh uuid4. The body field takes precedence
    over the header/cookie when supplied so clients that keep session
    state purely in memory still work.
    """

    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# SSE framing helpers
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, payload: Dict[str, Any]) -> str:
    """Format one Server-Sent Event frame.

    Using explicit ``event:`` + ``data:`` lines (not just ``data:``)
    lets the client dispatch on event type via the EventSource
    ``addEventListener`` API without parsing every payload.
    """
    return f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"


async def _stream_agent_response(
    *,
    message: str,
    context: UserContext,
    memory: AgentCoreMemory,
) -> AsyncIterator[str]:
    """Run the orchestrator and yield SSE frames.

    Emits (in order):
      1. ``session``  with the resolved ``session_id`` (+ namespace)
      2. ``chunk``    with the full response text
      3. ``done``     with the extracted OTel trace
    On failure, ``error`` is emitted instead of ``done`` so the client
    can distinguish a clean close from an interrupted one.
    """
    # --- 1. Session event ------------------------------------------------
    # Emit the session id first so the SPA can persist it before the
    # response body arrives. ``ensure_ascii=False`` is unnecessary here
    # because the payload is ASCII-safe.
    yield _sse_event(
        "session",
        {
            "session_id": context.session_id,
            "namespace": context.namespace,
            "authenticated": context.user_id is not None,
        },
    )

    # --- 2. Agent invocation --------------------------------------------
    # ``run_agent`` branches on ``USE_AGENTCORE_RUNTIME`` (C5) so this
    # handler stays single-path. Any exception raised by the
    # orchestrator is caught and surfaced as an ``error`` event — we
    # never leak a stack trace to the client (Req 3.1.5 style envelope).
    try:
        response_text = await run_agent(
            message=message,
            session_id=context.session_id,
            user_id=context.user_id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Agent invocation failed for session %s: %s",
            context.session_id,
            exc.__class__.__name__,
        )
        yield _sse_event("error", {"code": "agent_failed"})
        return

    # --- 3. Chunk event --------------------------------------------------
    # ``run_agent`` currently returns the full response as a single
    # string. Emitting it as one ``chunk`` keeps the wire shape
    # identical to a future streamed implementation that yields
    # incremental pieces. The client concatenates whatever arrives.
    yield _sse_event("chunk", {"content": response_text})

    # --- 4. Memory persistence ------------------------------------------
    # Append the turn pair after the agent completes so a failed memory
    # write doesn't block the user from seeing the response. Failures
    # are logged only — the stream still closes cleanly.
    try:
        await memory.append_session_turn(
            context.namespace,
            {"role": "user", "content": message},
        )
        await memory.append_session_turn(
            context.namespace,
            {"role": "assistant", "content": response_text},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Session history append failed for %s: %s",
            context.namespace,
            exc.__class__.__name__,
        )

    # --- 5. Done event (with trace) -------------------------------------
    # The in-process Strands path populates the trace via
    # ``otel_trace_extractor.extract_trace`` inside
    # ``_run_orchestrator_inprocess``. For the managed runtime path the
    # trace is empty (the runtime owns its own trace pipeline) and the
    # client's inspector simply shows nothing.
    trace = get_latest_trace()
    yield _sse_event(
        "done",
        {
            "session_id": context.session_id,
            "trace": trace,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(
    request: Request,
    payload: ChatRequest,
    identity: AgentCoreIdentityService = Depends(get_agentcore_identity_service),
    memory: AgentCoreMemory = Depends(get_agentcore_memory),
) -> StreamingResponse:
    """Stream orchestrator output over SSE.

    Implements Req 3.4.1–3.4.3. The JWT is validated exactly once by
    ``AgentCoreIdentityService.get_verified_user_context`` — which
    internally calls ``CognitoAuthService.extract_user`` — before the
    stream starts. No per-chunk re-check happens during streaming, so
    a token that expires mid-response does not abort the stream (Design
    "Error Handling" row, Sequence Diagram #2 note).

    Anonymous callers are accepted and routed to the ``anon:{session_id}``
    namespace (Req 4.3.3).
    """
    # Resolve the verified user + session namespace. This is the ONE
    # AND ONLY JWT check for the duration of the stream. Any token
    # expiry, revocation, or JWKS failure after this point is handled
    # by the next request, not this one.
    context = await identity.get_verified_user_context(request)

    # Honour an explicit ``session_id`` in the body (Req 3.4.1): when
    # the client has a known session, use it verbatim and rebuild the
    # namespace around it. The identity service's header/cookie
    # resolution is only the fallback path.
    if payload.session_id:
        context = UserContext(
            user_id=context.user_id,
            session_id=payload.session_id,
            namespace=AgentCoreIdentityService.build_namespace(
                context.user_id, payload.session_id
            ),
        )

    return StreamingResponse(
        _stream_agent_response(
            message=payload.message,
            context=context,
            memory=memory,
        ),
        media_type="text/event-stream",
        headers={
            # Hint upstream proxies to not buffer the stream so chunks
            # reach the browser in near-real-time even when ``run_agent``
            # becomes a true async iterator.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    identity: AgentCoreIdentityService = Depends(get_agentcore_identity_service),
    memory: AgentCoreMemory = Depends(get_agentcore_memory),
) -> JSONResponse:
    """Return the multi-turn history for ``session_id`` (Req 3.4.4).

    Scoping rules:
      * When the request carries a verified JWT, the history is read
        from ``user:{user_id}:session:{session_id}``. Another user's
        JWT over the same ``session_id`` sees an empty list — the
        namespace is keyed per-user (Req 4.3.2).
      * When the request is anonymous, the history is read from
        ``anon:{session_id}``. The route does not allow an anonymous
        caller to read another user's history because the namespace
        string never matches.
    """
    # Same one-shot identity resolution as ``/chat``. No JWT check
    # happens after this line.
    context = await identity.get_verified_user_context(request)

    # Override the session_id from the path param — the identity
    # service may have picked a different one off the X-Session-Id
    # header, but the caller explicitly asked for this thread.
    namespace = AgentCoreIdentityService.build_namespace(context.user_id, session_id)
    history = await memory.get_session_history(namespace)

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session_id,
            "namespace": namespace,
            "turns": history,
            "authenticated": context.user_id is not None,
        },
    )
