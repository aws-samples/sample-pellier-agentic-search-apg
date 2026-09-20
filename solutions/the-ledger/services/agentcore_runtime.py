"""
AgentCore Runtime bridge.

Migrates the orchestrator from in-process Strands execution to AgentCore
Runtime. When ``settings.USE_AGENTCORE_RUNTIME`` is ``False`` (the
default), every request stays on the local Strands orchestrator. When
flipped to ``True``, the same request is forwarded to the AgentCore
Runtime via ``run_agent_on_runtime`` with no other code changes — the
route handler calls :func:`run_agent` which routes based on the flag.

Two public entry points:

    run_agent(message, session_id, user_id, auth_token, history)
        Dispatcher called by the ``/api/agent/chat`` route (Task 3.5).
        Branches on ``settings.USE_AGENTCORE_RUNTIME``.

    run_agent_on_runtime(message, session_id, user_id, auth_token, history)
        Managed-runtime implementation. Invokes the CUSTOM_JWT AgentCore
        Runtime over the raw HTTPS data plane with the Cognito token as a
        Bearer header (there is no ``bedrock-agentcore-runtime`` boto3
        client) and returns the response.

The in-process path stays routed through ``agents.orchestrator`` and its
``create_orchestrator`` so participants can watch the request move
from local execution to managed runtime by flipping one env var.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
import json
from pathlib import Path
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import settings
from services.conversation_context import build_conversation_prompt

logger = logging.getLogger(__name__)


# Latest trace extracted on the in-process streaming path. The scalar
# value preserves backwards compatibility for older callers; the keyed
# map lets the SSE route return the trace for the session it just served
# instead of whatever request finished most recently in this process.
_latest_trace: Dict[str, Any] = {"spans": [], "totalMs": 0, "specialistRoute": ""}
_LATEST_TRACES_BY_SESSION_MAX = 32
# Cached digest of this checkout's packaged runtime sources; see
# _local_runtime_fingerprint().
_local_fingerprint_cache: Optional[str] = None
_latest_traces_by_session: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_managed_traces_by_principal_session: (
    "OrderedDict[tuple[str, str], Dict[str, Any]]"
) = OrderedDict()

class ManagedRuntimeError(RuntimeError):
    """Stable failure code for a configured managed Runtime path."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ManagedRuntimeResult:
    """Typed evidence returned by the managed Runtime invocation."""

    response: str
    products: List[Dict[str, Any]] = field(default_factory=list)
    rail: str = ""
    intent: str = ""
    specialist: str = ""
    response_mode: str = "balanced"
    model: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    orchestration: str = "dispatcher"


def _store_latest_trace(session_id: str, trace: Dict[str, Any]) -> None:
    """Keep a bounded per-session trace cache for recent SSE turns."""
    _latest_traces_by_session[session_id] = trace
    _latest_traces_by_session.move_to_end(session_id)
    while len(_latest_traces_by_session) > _LATEST_TRACES_BY_SESSION_MAX:
        _latest_traces_by_session.popitem(last=False)


def _empty_trace() -> Dict[str, Any]:
    return {"spans": [], "totalMs": 0, "specialistRoute": ""}


def _store_managed_trace(
    session_id: str, principal_sub: str, trace: Dict[str, Any]
) -> None:
    """Keep managed receipts keyed by both verified principal and session."""
    key = (principal_sub, session_id)
    _managed_traces_by_principal_session[key] = trace
    _managed_traces_by_principal_session.move_to_end(key)
    while len(_managed_traces_by_principal_session) > _LATEST_TRACES_BY_SESSION_MAX:
        _managed_traces_by_principal_session.popitem(last=False)


def get_latest_trace(
    session_id: Optional[str] = None, *, principal_sub: Optional[str] = None
) -> Dict[str, Any]:
    """Return the most recent ``{spans, totalMs, specialistRoute}``
    captured by ``_run_orchestrator_inprocess``.

    The ``/inspector`` view and the SSE trailer event call this after
    the orchestrator finishes so the frontend can render the waterfall
    without a second round-trip to the extractor.
    """
    if session_id and principal_sub:
        key = (principal_sub, session_id)
        trace = _managed_traces_by_principal_session.get(key)
        if trace is not None:
            _managed_traces_by_principal_session.move_to_end(key)
            return trace
        # A request with a verified principal must never fall back to a
        # session-only entry, which could belong to another participant.
        return _empty_trace()
    if session_id and session_id in _latest_traces_by_session:
        _latest_traces_by_session.move_to_end(session_id)
        return _latest_traces_by_session[session_id]
    if session_id:
        return _empty_trace()
    return _latest_trace


def _trace_id_from(headers: Dict[str, str]) -> Optional[str]:
    """Extract a trace id from the data plane's response headers.

    Two header families appear depending on how tracing is configured:
    X-Ray's ``X-Amzn-Trace-Id`` (``Root=1-abc-def;Sampled=1``) and W3C
    ``traceparent`` (``00-<trace-id>-<span-id>-01``). Both are parsed to
    the bare trace id so one field can correlate either way.

    Args:
        headers: Response headers, lowercased keys.

    Returns:
        The trace id, or ``None`` when the invocation reported none.
    """
    xray = headers.get("x-amzn-trace-id") or ""
    if xray:
        for part in xray.split(";"):
            key, _, value = part.strip().partition("=")
            if key.lower() == "root" and value:
                return value
        return xray.strip() or None

    traceparent = headers.get("traceparent") or ""
    segments = traceparent.split("-")
    if len(segments) >= 3 and segments[1]:
        return segments[1]
    return None


def _cloudwatch_trace_links(
    *, session_id: str, trace_id: Optional[str], request_id: Optional[str]
) -> Dict[str, Any]:
    """Build the console links and query needed to find the real trace.

    The backend deliberately does not proxy the managed OTEL trace: doing
    so would mean this process re-reporting telemetry it did not produce,
    which is exactly the blurring between application spans and service
    telemetry the audit warns about. Instead the receipt carries the
    correlation IDs plus a ready-to-run Logs Insights query, so an
    attendee reaches the authoritative AgentCore/CloudWatch record rather
    than a summary of it.

    Returns a dict of link material. Values are ``None`` when the
    corresponding ID was not returned by the data plane — an absent trace
    id is honest evidence that the invocation did not report one.
    """
    region = settings.aws_region_resolved
    log_group = "/aws/bedrock-agentcore/runtimes"
    filters = [f'@message like "{session_id}"']
    if trace_id:
        filters.append(f'@message like "{trace_id}"')
    query = (
        "fields @timestamp, @message"
        f" | filter {' or '.join(filters)}"
        " | sort @timestamp desc"
        " | limit 100"
    )
    return {
        "region": region,
        "logGroupPrefix": log_group,
        "traceId": trace_id,
        "runtimeRequestId": request_id,
        "sessionId": session_id,
        "logsInsightsQuery": query,
        "xrayConsoleUrl": (
            f"https://{region}.console.aws.amazon.com/cloudwatch/home"
            f"?region={region}#xray:traces/{trace_id}"
            if trace_id
            else None
        ),
        "logsConsoleUrl": (
            f"https://{region}.console.aws.amazon.com/cloudwatch/home"
            f"?region={region}#logsV2:logs-insights"
        ),
    }


def _local_runtime_fingerprint() -> str:
    """Digest this checkout's copy of the packaged runtime sources.

    Cached because it reads several files and cannot change within a process:
    the backend restarts when its source changes. Returns an empty string if
    the digest cannot be computed, so a packaging question never becomes a
    failed shopper turn.
    """
    global _local_fingerprint_cache
    if _local_fingerprint_cache is None:
        try:
            from services.build_fingerprint import compute_fingerprint

            _local_fingerprint_cache = compute_fingerprint(
                Path(__file__).resolve().parents[1]
            )
        except Exception:  # noqa: BLE001 - provenance is never load-bearing
            logger.debug("Local runtime fingerprint unavailable", exc_info=True)
            _local_fingerprint_cache = ""
    return _local_fingerprint_cache


def _build_state(deployed: str, local: str) -> str:
    """Classify the deployed revision against this checkout.

    Three states, deliberately, because two would lie. ``unknown`` is not a
    soft ``stale``: a runtime deployed before the fingerprint existed reports
    nothing, and absence of evidence is not evidence of stale code.
    """
    if not deployed or not local:
        return "unknown"
    return "current" if deployed == local else "stale"


def _store_managed_runtime_receipt(
    session_id: str,
    *,
    principal_sub: str,
    rail: str,
    auth_token_present: bool,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    build_fingerprint: Optional[str] = None,
    runtime_session_id: Optional[str] = None,
) -> None:
    """Expose a truthful managed-runtime receipt without synthesizing OTEL spans.

    ``spans`` stays empty on purpose. The managed Runtime emits its own
    service telemetry to CloudWatch; fabricating local spans here would
    present reconstructed data as observed data. What the receipt adds
    instead is correlation: the trace and request IDs, and the query that
    retrieves the authoritative record.
    """
    global _latest_trace
    _latest_trace = {
        "spans": [],
        "totalMs": 0,
        "specialistRoute": "",
        "otel_enabled": False,
        "traceKind": "managed-runtime-receipt",
        "runtime": "agentcore-managed",
        "rail": rail,
        "jwtPassthrough": auth_token_present,
        "gatewayPassthrough": rail == "gateway-mcp",
        # Provenance vocabulary shared with the Observatory surfaces: this is
        # service telemetry, not application-generated spans.
        "evidenceProvenance": "agentcore-service-telemetry",
        "traceId": trace_id,
        "runtimeRequestId": request_id,
        "runtimeSessionId": runtime_session_id,
        "sessionId": session_id,
        # Which revision answered. The invoke response carries no version of
        # its own and `qualifier=DEFAULT` reads identically for yesterday's
        # baseline, so the deployed package carries its own content digest and
        # we compare it against this checkout. `buildState` is the participant
        # -facing answer to "did Runtime run the code I just packaged?".
        "buildFingerprint": (build_fingerprint or "").strip(),
        "localBuildFingerprint": _local_runtime_fingerprint(),
        "buildState": _build_state(
            (build_fingerprint or "").strip(), _local_runtime_fingerprint()
        ),
        "managedTrace": _cloudwatch_trace_links(
            session_id=runtime_session_id or session_id, trace_id=trace_id, request_id=request_id
        ),
    }
    _store_managed_trace(session_id, principal_sub, _latest_trace)


async def _run_orchestrator_inprocess(
    message: str,
    session_id: str,
    user_id: Optional[str],
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Run the local Strands orchestrator in-process.

    ``create_orchestrator`` builds a Strands :class:`Agent` whose
    ``__call__`` is blocking, so the invocation is offloaded to a
    worker thread to avoid stalling the event loop.
    """
    from agents.orchestrator import create_orchestrator

    orchestrator = create_orchestrator()
    if orchestrator is None:
        return (
            "The orchestrator isn't wired up yet. Wire the orchestrator "
            "to enable multi-agent routing."
        )

    # Attach trace attributes so the otel_trace_extractor (OTEL) can tag
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

    response = await asyncio.to_thread(
        orchestrator,
        build_conversation_prompt(message, history),
    )

    # Drain the captured OpenTelemetry spans into the latest-trace slot
    # so the ``/inspector`` view can render this run's waterfall
    # immediately. Importing lazily keeps the dispatcher self-contained
    # and avoids a hard dependency on the OTEL SDK at module load.
    try:
        from services.otel_trace_extractor import extract_trace

        global _latest_trace
        _latest_trace = extract_trace()
        _store_latest_trace(session_id, _latest_trace)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("trace extraction skipped: %s", exc)

    return str(response)


def _runtime_session_id_for(session_id: Optional[str], user_id: Optional[str] = None) -> str:
    """Bind managed session reuse to the verified principal and conversation.

    Hash every input, including long IDs: passing long IDs through would let a
    caller submit the encoded form of somebody else's short ID. The fixed ASCII
    header also obeys the Runtime length contract for arbitrary application IDs.
    A missing conversation ID starts a new session instead of sharing a default.
    """
    identity = json.dumps([user_id or "", session_id or str(uuid.uuid4())])
    return "pellier-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


# === REFERENCE: AgentCore Runtime — START ===
# Runtime selection reference. When the feature flag
# ``USE_AGENTCORE_RUNTIME`` is ``True``, the ``/api/agent/chat`` route
# forwards every request here instead of running Strands locally.
#
# The runtime contract is a JSON payload ``{"prompt", "session_id",
# "user_id", "history"}``; the Runtime container unpacks it in the ``@app.entry
# point`` handler at ``pellier/backend/agentcore_runtime.py``.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_runtime.py pellier/backend/services/agentcore_runtime.py
async def run_agent_on_runtime_result(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    turn_id: Optional[str] = None,
    response_mode: str = "balanced",
    customer_id: Optional[str] = None,
) -> ManagedRuntimeResult:
    """Invoke AgentCore Runtime and return its observed execution envelope.

    Args:
        message: Shopper prompt (one turn).
        session_id: Session identifier for STM continuity (STM).
        user_id: Verified Cognito ``sub`` when the caller is signed
            in; ``None`` for anonymous shoppers.
        auth_token: Raw Cognito access token forwarded to the Runtime
            authorizer. The managed Runtime rejects anonymous requests.
        history: Prior user/assistant turns read from the identity-scoped
            AgentCore Memory namespace and forwarded as bounded context.

    Returns:
        Response text plus observed Gateway calls, products, and routing data.

    Raises:
        ManagedRuntimeError: If the managed rail is incomplete or unavailable.
    """
    endpoint = settings.AGENTCORE_RUNTIME_ENDPOINT
    if not endpoint:
        logger.error(
            "USE_AGENTCORE_RUNTIME=true but AGENTCORE_RUNTIME_ENDPOINT is unset"
        )
        raise ManagedRuntimeError("runtime_not_configured")

    if not auth_token:
        logger.warning(
            "USE_AGENTCORE_RUNTIME=true but no Cognito access token was available"
        )
        raise ManagedRuntimeError("authentication_required")

    logger.info(
        "agentcore.invoke session=%s user=%s prompt_len=%d endpoint=%s",
        session_id,
        user_id or "anonymous",
        len(message),
        endpoint.rsplit("/", 1)[-1],
    )

    from services.response_mode import normalize_response_mode

    payload_data: Dict[str, Any] = {
        "prompt": message,
        "session_id": session_id,
        "user_id": user_id or "anonymous",
        "history": history or [],
        "response_mode": normalize_response_mode(response_mode),
        "customer_id": customer_id or None,
    }
    if turn_id:
        # This is minted by the storefront route, not supplied by the model.
        # The Runtime passes it to the Gateway dispatcher, which asks each
        # tool call to carry it into its audit arguments.
        payload_data["turn_id"] = turn_id
    payload = json.dumps(payload_data)

    # CUSTOM_JWT runtimes are invoked over the RAW HTTPS data plane with the
    # Cognito token as a Bearer header - NOT via boto3. There is no
    # "bedrock-agentcore-runtime" service name, and the real SDK's
    # invoke_agent_runtime has no authToken param (it SigV4-signs, which a
    # JWT-gated runtime rejects). This mirrors the provisioner's proven
    # `_authenticated_runtime_smoke` transport (provision_agentcore_end_to_end.py)
    # and the dat403 `agentcore invoke --bearer-token` path.
    import urllib.error
    import urllib.parse
    import urllib.request

    runtime_arn = endpoint
    escaped_arn = urllib.parse.quote(runtime_arn, safe="")
    url = (
        f"https://bedrock-agentcore.{settings.aws_region_resolved}.amazonaws.com"
        f"/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
    )
    runtime_session_id = _runtime_session_id_for(session_id, user_id)

    def _invoke() -> tuple[str, Dict[str, str]]:
        """Return the body and the response headers.

        The headers carry the correlation IDs the evidence view needs to
        reach the authoritative CloudWatch/X-Ray record: the data plane's
        request id and, when tracing is enabled, the trace id. Dropping
        them is what forced the receipt to be a summary instead of a link.
        """
        request = urllib.request.Request(
            url,
            data=payload.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": runtime_session_id,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in dict(resp.headers).items()}
            return body, headers

    try:
        raw, response_headers = await asyncio.to_thread(_invoke)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ManagedRuntimeError("runtime_invalid_response") from exc

        if not isinstance(parsed, dict):
            raise ManagedRuntimeError("runtime_invalid_response")
        if parsed.get("error"):
            raise ManagedRuntimeError(str(parsed["error"]))

        rail = str(parsed.get("rail") or "")
        if rail != "gateway-mcp":
            raise ManagedRuntimeError("managed_gateway_unavailable")
        if not str(parsed.get("response") or "").strip():
            raise ManagedRuntimeError("runtime_invalid_response")
        orchestration = str(parsed.get("orchestration") or "dispatcher")
        if orchestration != "dispatcher":
            raise ManagedRuntimeError("runtime_invalid_response")

        _store_managed_runtime_receipt(
            session_id,
            principal_sub=user_id or "anonymous",
            rail=rail,
            auth_token_present=bool(auth_token),
            trace_id=_trace_id_from(response_headers),
            request_id=response_headers.get("x-amzn-requestid"),
            build_fingerprint=str(parsed.get("build_fingerprint") or ""),
            runtime_session_id=runtime_session_id,
        )
        products = parsed.get("products")
        tool_calls = parsed.get("tool_calls")
        return ManagedRuntimeResult(
            response=str(parsed["response"]),
            products=(
                [dict(product) for product in products if isinstance(product, dict)]
                if isinstance(products, list)
                else []
            ),
            rail=rail,
            intent=str(parsed.get("intent") or ""),
            specialist=str(parsed.get("specialist") or ""),
            response_mode=str(parsed.get("response_mode") or "balanced"),
            model=str(parsed.get("model") or ""),
            tool_calls=(
                [dict(call) for call in tool_calls if isinstance(call, dict)]
                if isinstance(tool_calls, list)
                else []
            ),
            orchestration="dispatcher",
        )
    except ManagedRuntimeError:
        raise
    except urllib.error.HTTPError as exc:  # pragma: no cover - SDK error path
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("AgentCore Runtime invoke HTTP %s: %s", exc.code, detail)
        raise ManagedRuntimeError("runtime_unavailable") from exc
    except Exception as exc:  # pragma: no cover - SDK error path
        logger.error("AgentCore Runtime invocation failed: %s", exc)
        raise ManagedRuntimeError("runtime_unavailable") from exc
# === REFERENCE: AgentCore Runtime — END ===


async def run_agent_on_runtime(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    turn_id: Optional[str] = None,
    response_mode: str = "balanced",
    customer_id: Optional[str] = None,
) -> str:
    """Compatibility wrapper returning only the managed response text."""
    result = await run_agent_on_runtime_result(
        message=message,
        session_id=session_id,
        user_id=user_id,
        auth_token=auth_token,
        history=history,
        turn_id=turn_id,
        response_mode=response_mode,
        customer_id=customer_id,
    )
    return result.response


async def run_agent(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    turn_id: Optional[str] = None,
    response_mode: str = "balanced",
    customer_id: Optional[str] = None,
) -> str:
    """Route a chat request through either the in-process Strands
    orchestrator or the AgentCore Runtime, based on
    ``settings.USE_AGENTCORE_RUNTIME``.

    This is the single entry point used by the route handler for
    ``/api/agent/chat`` (Task 3.5). Flipping ``USE_AGENTCORE_RUNTIME=true``
    in ``backend/.env`` and restarting is the only change participants
    need to make to migrate from local execution to managed runtime.

    Rail selection is delegated to ``services.execution_rail`` so this
    route and the storefront's ``/api/chat/stream`` resolve the rail the
    same way. When the managed rail is requested but unusable, this entry
    point fails closed with a ``ManagedRuntimeError`` rather than quietly
    serving an in-process turn: the caller asked for the governed path,
    and an ungoverned answer that looks identical is the failure mode
    worth preventing.

    Raises:
        ManagedRuntimeError: When the managed rail was requested but is
            unavailable, or when the managed invocation itself fails.
    """
    from services.execution_rail import resolve_rail
    from services.turn_identity import authorized_customer_id_var, principal_sub_var

    # The in-process fallback also reaches deterministic customer tools. Bind
    # only an authenticated, server-resolved scope before its worker thread
    # starts; a runtime caller cannot turn a supplied customer_id into scope.
    principal_sub_var.set(user_id or None)
    authorized_customer_id_var.set(customer_id if user_id and customer_id else None)

    decision = resolve_rail(auth_token=auth_token)
    if decision.managed_requested and not decision.available:
        raise ManagedRuntimeError(decision.reason or "runtime_unavailable")
    if decision.is_managed:
        runtime_kwargs: Dict[str, Any] = {
            "message": message,
            "session_id": session_id,
            "user_id": user_id,
            "auth_token": auth_token,
            "history": history,
            "response_mode": response_mode,
        }
        if turn_id:
            runtime_kwargs["turn_id"] = turn_id
        if customer_id:
            runtime_kwargs["customer_id"] = customer_id
        return await run_agent_on_runtime(**runtime_kwargs)
    return await _run_orchestrator_inprocess(
        message, session_id, user_id, history
    )
