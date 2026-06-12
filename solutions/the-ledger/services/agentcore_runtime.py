"""
AgentCore Runtime migration — Challenge 5.

Migrates the orchestrator from in-process Strands execution to AgentCore
Runtime. When ``settings.USE_AGENTCORE_RUNTIME`` is ``False`` (the
default), every request stays on the local Strands orchestrator from
Challenge 4. When flipped to ``True``, the same request is forwarded to
the AgentCore Runtime via ``run_agent_on_runtime`` with no other code
changes — the route handler calls :func:`run_agent` which routes based
on the flag (see Design "Runtime selection switch").

Two public entry points:

    run_agent(message, session_id, user_id, auth_token)
        Dispatcher called by the ``/api/agent/chat`` route (Task 3.5).
        Branches on ``settings.USE_AGENTCORE_RUNTIME``.

    run_agent_on_runtime(message, session_id, user_id, auth_token)
        Challenge 5 implementation. Invokes AgentCore Runtime via the
        ``bedrock-agentcore-runtime`` SDK and streams/returns the response.

The in-process path stays routed through Challenge 4's
``create_orchestrator`` so participants can watch the request move
from local execution to managed runtime by flipping one env var.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)


# Latest trace extracted on the in-process streaming path. The SSE
# handler (Task 3.5) and the ``/inspector`` view read this after each
# orchestrator run so the waterfall shows the just-finished request.
_latest_trace: Dict[str, Any] = {"spans": [], "totalMs": 0, "specialistRoute": ""}


def get_latest_trace() -> Dict[str, Any]:
    """Return the most recent ``{spans, totalMs, specialistRoute}``
    captured by ``_run_orchestrator_inprocess``.

    The ``/inspector`` view and the SSE trailer event call this after
    the orchestrator finishes so the frontend can render the waterfall
    without a second round-trip to the extractor.
    """
    return _latest_trace


async def _run_orchestrator_inprocess(
    message: str,
    session_id: str,
    user_id: Optional[str],
) -> str:
    """Run the Challenge 4 orchestrator in-process (the pre-C5 path).

    ``create_orchestrator`` builds a Strands :class:`Agent` whose
    ``__call__`` is blocking, so the invocation is offloaded to a
    worker thread to avoid stalling the event loop.
    """
    from agents.orchestrator import create_orchestrator

    orchestrator = create_orchestrator()
    if orchestrator is None:
        return (
            "The orchestrator isn't wired up yet. Complete Challenge 4 "
            "to enable multi-agent routing."
        )

    # Attach trace attributes so the otel_trace_extractor (C8) can tag
    # spans with session + user context from the same dispatcher the
    # runtime path uses.
    try:
        orchestrator.trace_attributes = {
            "session.id": session_id,
            "user.id": user_id or "anonymous",
            "runtime": "in-process",
            "workshop": "pellier",
        }
    except Exception:  # pragma: no cover - defensive
        pass

    response = await asyncio.to_thread(orchestrator, message)

    # Drain the captured OpenTelemetry spans into the latest-trace slot
    # so the ``/inspector`` view can render this run's waterfall
    # immediately. Importing lazily keeps the dispatcher self-contained
    # and avoids a hard dependency on the OTEL SDK at module load.
    try:
        from services.otel_trace_extractor import extract_trace

        global _latest_trace
        _latest_trace = extract_trace()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("trace extraction skipped: %s", exc)

    return str(response)


# === CHALLENGE 5: AgentCore Runtime — START ===
# Requirement 2.5.1 and Design "Runtime selection switch". Participants
# replace this body to invoke the AgentCore Runtime SDK. When the
# feature flag ``USE_AGENTCORE_RUNTIME`` is ``True``, the ``/api/agent/
# chat`` route (Task 3.5) forwards every request here instead of
# running Strands locally.
#
# The runtime contract is a JSON payload ``{"prompt", "session_id",
# "user_id"}``; the Runtime container unpacks it in the ``@app.entry
# point`` handler at ``pellier/backend/agentcore_runtime.py``.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_runtime.py pellier/backend/services/agentcore_runtime.py
async def run_agent_on_runtime(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> str:
    """Invoke the AgentCore Runtime with ``message`` and return the
    response text.

    Args:
        message: Shopper prompt (one turn).
        session_id: Session identifier for STM continuity (C6).
        user_id: Verified Cognito ``sub`` when the caller is signed
            in; ``None`` for anonymous shoppers.
        auth_token: Raw Cognito access token forwarded to the Runtime
            authorizer. Anonymous requests fall back to the in-process
            orchestrator because the managed Runtime is JWT-protected.

    Returns:
        The orchestrator's reply as a string. Errors are logged and
        returned as a user-safe envelope.
    """
    endpoint = settings.AGENTCORE_RUNTIME_ENDPOINT
    if not endpoint:
        logger.warning(
            "USE_AGENTCORE_RUNTIME=true but AGENTCORE_RUNTIME_ENDPOINT is "
            "unset; falling back to in-process orchestrator"
        )
        return await _run_orchestrator_inprocess(message, session_id, user_id)

    if not auth_token:
        logger.warning(
            "USE_AGENTCORE_RUNTIME=true but no Cognito access token was "
            "available; falling back to in-process orchestrator"
        )
        return await _run_orchestrator_inprocess(message, session_id, user_id)

    payload = {
        "prompt": message,
        "session_id": session_id,
        "user_id": user_id or "anonymous",
    }

    try:
        import boto3

        client = boto3.client(
            "bedrock-agentcore-runtime",
            region_name=settings.aws_region_resolved,
        )
        runtime_id = endpoint.rsplit("/", 1)[-1] if endpoint.startswith("arn:") else endpoint

        def _invoke() -> dict[str, Any]:
            return client.invoke_agent_runtime(
                agentRuntimeId=runtime_id,
                payload=json.dumps(payload),
                authToken=auth_token,
            )

        response = await asyncio.to_thread(_invoke)

        body = response.get("body") or response.get("response") or response.get("payload")
        if hasattr(body, "read"):
            body = body.read()
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        if isinstance(body, str):
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and "response" in parsed:
                    return str(parsed["response"])
                return body
            except json.JSONDecodeError:
                return body
        return str(body)

    except ImportError:
        logger.warning(
            "bedrock-agentcore-runtime / boto3 not installed — falling back to "
            "in-process orchestrator"
        )
        return await _run_orchestrator_inprocess(message, session_id, user_id)
    except Exception as exc:  # pragma: no cover - SDK error path
        logger.error("AgentCore Runtime invocation failed: %s", exc)
        return json.dumps({"error": "runtime_unavailable"})
# === CHALLENGE 5: AgentCore Runtime — END ===


async def run_agent(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> str:
    """Route a chat request through either the in-process Strands
    orchestrator or the AgentCore Runtime, based on
    ``settings.USE_AGENTCORE_RUNTIME``.

    This is the single entry point used by the route handler for
    ``/api/agent/chat`` (Task 3.5). Flipping ``USE_AGENTCORE_RUNTIME=true``
    in ``backend/.env`` and restarting is the only change participants
    need to make to migrate from local execution to managed runtime.
    """
    if settings.USE_AGENTCORE_RUNTIME:
        return await run_agent_on_runtime(message, session_id, user_id, auth_token)
    return await _run_orchestrator_inprocess(message, session_id, user_id)
