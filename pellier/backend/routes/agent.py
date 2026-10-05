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
* **Anonymous identity.** ``AgentCoreIdentityService`` still assigns
  ``anon-{session_id}`` when no valid token is present. The builders
  in-process path can use that namespace; when managed Runtime is enabled,
  the request fails closed with ``authentication_required``.
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
    - ``memory``   — managed read/write evidence for this completed turn
    - ``done``     — final event, carries the extracted OTel trace
    - ``error``    — emitted instead of ``done`` when a pre-execution read
                     or the agent call fails; stream ends immediately after
* **Runtime dispatch.** ``services.agentcore_runtime.run_agent`` branches
  on ``settings.USE_AGENTCORE_RUNTIME`` so this route handles both in-process
  (in-process Strands) and runtime (managed runtime) without branching here.
  Since ``run_agent`` returns a single string rather than an async
  iterator, we emit the full response as a single ``chunk`` event plus
  a ``done`` trailer. The wire shape is ready for a streamed
  implementation — swapping to an async iterator in
  ``agentcore_runtime`` only touches ``_stream_agent_response`` below.
* **Memory writes.** The turn pair (user + assistant) is appended to
  ``AgentCoreMemory`` under the identity-service namespace after the
  agent response completes. A managed read fails before invocation. A
  post-invocation write failure is emitted as partial evidence and never
  turns a potentially completed action into a retryable failure.

Routes are not participant-edit surfaces. They ship as reference runtime code.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from pellier_copy import MEMORY_READ_WARNING, MEMORY_WRITE_WARNING
from services.agentcore_identity import (
    AgentCoreIdentityService,
    UserContext,
    get_agentcore_identity_service,
)
from services.agentcore_memory import BACKEND_AGENTCORE, AgentCoreMemory, ManagedMemoryError
from services.agentcore_runtime import (
    AgentTurnError,
    ManagedRuntimeError,
    get_latest_trace,
    run_agent,
)
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
      2. ``memory``   with read/write persistence evidence
      3. ``chunk``    with the full response text
      4. ``done``     with the extracted OTel trace
    On failure, ``error`` is emitted instead of ``done`` so the client
    can distinguish a clean close from an interrupted one.
    """
    # --- 0. Turn identity ------------------------------------------------
    # Every turn carries the one correlation identifier, on THIS path too.
    #
    # `services/chat.py` mints it in both of its entry points and its comment
    # explains exactly why: without it, "a governed-boundary refusal produced an
    # operator review with no source turn". That fix never reached this route — the
    # one the SPA actually calls — so a real shopper return handoff landed in
    # `pellier.approvals` with `source_turn_id = NULL`, breaking the
    # shopper -> review -> execution lineage at its first link.
    #
    # Minted from the same function rather than a second format, and emitted so a
    # client can deep-link the turn it just produced.
    from services.turn_identity import new_turn_id, turn_id_var

    turn_id = turn_id_var.get() or new_turn_id()
    turn_id_var.set(turn_id)

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
            "turn_id": turn_id,
        },
    )

    # --- 2. Agent invocation --------------------------------------------
    # ``run_agent`` branches on ``USE_AGENTCORE_RUNTIME`` (runtime) so this
    # handler stays single-path. Any exception raised by the
    # orchestrator is caught and surfaced as an ``error`` event — we
    # never leak a stack trace to the client (Req 3.1.5 style envelope).
    memory_read_failed = False
    try:
        history = await memory.get_session_history(context.namespace)
    except ManagedMemoryError as exc:
        logger.warning(
            "Managed Memory rejected session %s before invocation",
            context.session_id,
        )
        yield _sse_event("error", {"code": exc.code})
        return
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Session history read failed for %s: %s",
            context.namespace,
            exc.__class__.__name__,
        )
        history = []
        memory_read_failed = True

    try:
        response_text = await run_agent(
            message=message,
            session_id=context.session_id,
            user_id=context.user_id,
            auth_token=context.access_token,
            history=history,
            customer_id=context.customer_id,
            principal_username=context.principal_username,
        )
    except (ManagedRuntimeError, AgentTurnError) as exc:
        # A failed turn is a failed turn: no Memory write, no chunk, no done.
        logger.warning(
            "Agent turn rejected for session %s: %s",
            context.session_id,
            exc.code,
        )
        yield _sse_event("error", {"code": exc.code})
        return
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Agent invocation failed for session %s: %s",
            context.session_id,
            exc.__class__.__name__,
        )
        yield _sse_event("error", {"code": "agent_failed"})
        return

    # --- 3. Memory persistence ------------------------------------------
    memory_receipt: Dict[str, Any] = {
        "source": "agentcore-memory",
        "turns_loaded": len(history),
        "turns_persisted": 0,
        "read_status": "failed" if memory_read_failed else "succeeded",
        "write_status": "pending",
        "action_status": "completed",
        "retry_recommended": memory_read_failed,
    }
    if memory_read_failed:
        memory_receipt["error_code"] = "memory_read_failed"
    try:
        write_backend = await memory.append_session_turns(
            context.namespace,
            [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text},
            ],
        )
        memory_receipt["turns_persisted"] = 2
        memory_receipt["write_status"] = "succeeded"
        # ``agentcore-memory`` is reserved for a write the SDK confirmed. The
        # non-strict rail falls back to a process-local dict and returns
        # normally; a reader would take that source for managed
        # persistence unless the receipt says otherwise.
        if write_backend != BACKEND_AGENTCORE:
            memory_receipt["source"] = "process-local"
    except ManagedMemoryError as exc:
        logger.warning(
            "Managed Memory rejected session %s after invocation",
            context.session_id,
        )
        memory_receipt["write_status"] = "failed"
        memory_receipt["error_code"] = exc.code
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Session history append failed for %s: %s",
            context.namespace,
            exc.__class__.__name__,
        )
        memory_receipt["source"] = "unavailable"
        memory_receipt["write_status"] = "failed"
        memory_receipt["error_code"] = "memory_write_failed"

    yield _sse_event("memory", memory_receipt)

    # --- 4. Chunk event --------------------------------------------------
    # ``run_agent`` currently returns the full response as one chunk.
    yield _sse_event("chunk", {"content": response_text})

    # --- 5. Done event (with trace) -------------------------------------
    # The in-process Strands path populates OTEL spans via
    # ``otel_trace_extractor.extract_trace`` inside
    # ``_run_orchestrator_inprocess``. For the managed Runtime path the
    # backend cannot see inside the Runtime's OTEL collector, so
    # ``run_agent_on_runtime`` stores a small receipt instead: runtime
    # rail, JWT passthrough, and whether the container reported
    # Gateway/MCP execution.
    trace = get_latest_trace(
        context.session_id,
        principal_sub=context.user_id,
    )
    yield _sse_event(
        "done",
        {
            "session_id": context.session_id,
            # The correlation id for everything this turn produced, so a client can
            # deep-link the evidence without guessing which turn was newest.
            "turn_id": turn_id,
            "trace": trace,
            "memory": memory_receipt,
            "warnings": [
                *(
                    [
                        {
                            "code": "memory_read_failed",
                            "message": MEMORY_READ_WARNING,
                            "retry_recommended": True,
                        }
                    ]
                    if memory_receipt["read_status"] == "failed"
                    else []
                ),
                *(
                    [
                        {
                            "code": memory_receipt.get("error_code"),
                            "message": MEMORY_WRITE_WARNING,
                            "retry_recommended": False,
                        }
                    ]
                    if memory_receipt["write_status"] == "failed"
                    else []
                ),
            ],
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

    Anonymous callers are accepted and routed to the ``anon-{session_id}``
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
            access_token=context.access_token,
            customer_id=context.customer_id,
            principal_username=context.principal_username,
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
        from ``user-{user_id}-session-{session_id}``. Another user's
        JWT over the same ``session_id`` sees an empty list — the
        namespace is keyed per-user (Req 4.3.2).
      * When the request is anonymous, the history is read from
        ``anon-{session_id}``. The route does not allow an anonymous
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
