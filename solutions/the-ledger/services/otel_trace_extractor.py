"""
OpenTelemetry Trace Extractor for Agent Execution Visualization

Captures real Strands SDK spans via InMemorySpanExporter and extracts
them into the shape the frontend `/inspector` view consumes:

    { spans: Span[], totalMs: number, specialistRoute: string }

Each browser-visible ``Span`` carries ``name``, ``kind`` (``orchestrator`` |
``specialist`` | ``tool``), ``startMs``, ``durationMs`` and an allow-listed
attribute subset so the waterfall can render the orchestrator → specialist →
tool hand-off without exposing prompts, shopper context, or session identifiers.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Module-level exporter reference. Set by ``init_span_capture`` when the
# OpenTelemetry SDK is present and the active ``TracerProvider`` is
# SDK-backed; remains ``None`` otherwise so the inspector surfaces an
# explicit failure banner instead of silently synthesizing spans.
_span_exporter: Any = None

# Tri-state flag inspected by callers (endpoint, chat service, tests).
# ``True`` — in-memory span capture is attached and reading will work.
# ``False`` — init ran but the active provider is not SDK-backed, or the
# OpenTelemetry SDK is missing. Callers MUST NOT fall back to synthetic
# spans; they MUST surface ``otel_enabled: False`` with the ``reason``.
OTEL_WORKING: bool = False

# Safe initialization failure reason for the UI. Internal exception details
# remain in the server logs.
OTEL_FAILURE_REASON: str = (
    "Telemetry not initialized yet — init_span_capture() has not run."
)

_INIT_ORDER_HINT = (
    "Check StrandsTelemetry initialization order in app.py lifespan. "
    "See docs/troubleshooting-otel.md for debugging steps."
)

# Specialist tool names match the @tool decorated symbols in
# backend/agents/*.py. They are used to tag the execute_tool / invoke_agent
# spans that surface specialist routing on the inspector waterfall.
_SPECIALIST_TOOL_NAMES = frozenset(
    {
        "search",
        "recommendation",
        "pricing",
        "inventory",
        "support",
    }
)

_PUBLIC_SPAN_ATTRIBUTE_KEYS = frozenset(
    {
        "gen_ai.operation.name",
        "gen_ai.agent.name",
        "gen_ai.tool.name",
        "gen_ai.tool.status",
        "gen_ai.request.model",
        "gen_ai.usage.prompt_tokens",
        "gen_ai.usage.completion_tokens",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.total_tokens",
        "service",
        "pattern",
        "workshop",
    }
)


# === REFERENCE: Observability — START ===
# Requirement 2.5.4 and 5.4.1. The orchestrator streaming path attaches
# ``trace_attributes`` (session.id, user.id, runtime, workshop) to the
# Strands Agent before invocation — see ``services.agentcore_runtime.
# _run_orchestrator_inprocess``. Strands may only copy those attributes
# onto spans owned by that Agent, so session filtering first finds the
# tagged span's trace id, then keeps every span in that OTEL trace.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/otel_trace_extractor.py pellier/backend/services/otel_trace_extractor.py


def init_span_capture() -> None:
    """Attach an in-memory exporter so finished spans can be read back.

    Uses a ``SimpleSpanProcessor`` so spans surface synchronously. Safe
    to call multiple times — a second call replaces the exporter so the
    inspector always reads from a single source of truth.

    Logs at ERROR and leaves ``OTEL_WORKING=False`` on any failure so
    ``/api/traces/waterfall`` and the ``agent_execution`` payload can
    surface an actionable banner instead of silently synthesizing spans.
    """
    global _span_exporter, OTEL_WORKING, OTEL_FAILURE_REASON
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider_type = type(provider).__name__
            reason = (
                f"Telemetry unavailable: Strands' TracerProvider is not "
                f"SDK-backed (got {provider_type}). {_INIT_ORDER_HINT}"
            )
            logger.error(reason)
            OTEL_WORKING = False
            OTEL_FAILURE_REASON = reason
            _span_exporter = None
            return

        _span_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_span_exporter))
        OTEL_WORKING = True
        OTEL_FAILURE_REASON = ""
        logger.info("✅ In-memory span capture initialized for trace extraction")

    except ImportError:
        reason = (
            "Telemetry unavailable: OpenTelemetry SDK not installed. "
            "Install with: pip install 'strands-agents[otel]'"
        )
        logger.error(reason)
        OTEL_WORKING = False
        OTEL_FAILURE_REASON = reason
        _span_exporter = None
    except Exception:
        reason = f"Telemetry unavailable: failed to initialize span capture. {_INIT_ORDER_HINT}"
        logger.exception("Failed to initialize span capture")
        OTEL_WORKING = False
        OTEL_FAILURE_REASON = reason
        _span_exporter = None


def _classify_span(name: str, attrs: Dict[str, Any]) -> str:
    """Return ``'orchestrator'`` | ``'specialist'`` | ``'tool'`` for
    a Strands-emitted span.

    Strands emits two span families:

      - ``invoke_agent {agent_name}`` with attribute ``gen_ai.agent.name``
      - ``execute_tool {tool_name}`` with attribute ``gen_ai.tool.name``

    A specialist (``recommendation``, etc.) is itself a
    Strands ``@tool`` that internally constructs an inner ``Agent``, so
    it shows up on both sides. Either form classifies as
    ``'specialist'``. Every other ``execute_tool`` span is a leaf
    ``'tool'`` call. The top-level agent span (not a known specialist)
    is the orchestrator.
    """
    tool_name = str(attrs.get("gen_ai.tool.name") or "")
    agent_name = str(attrs.get("gen_ai.agent.name") or "")

    if tool_name in _SPECIALIST_TOOL_NAMES:
        return "specialist"
    if agent_name in _SPECIALIST_TOOL_NAMES:
        return "specialist"
    if name.startswith("execute_tool"):
        return "tool"
    # invoke_agent, chat, and any other top-level Strands span belongs
    # to the orchestrator turn.
    return "orchestrator"


def _span_to_dict(span: Any, base_ms: int) -> Dict[str, Any]:
    """Convert a ``ReadableSpan`` to the inspector's span shape."""
    attrs = dict(span.attributes) if span.attributes else {}
    name = span.name or ""
    start_ns = span.start_time or 0
    end_ns = span.end_time or start_ns
    duration_ms = max(int((end_ns - start_ns) / 1_000_000), 0)
    start_ms = max(int(start_ns / 1_000_000) - base_ms, 0)
    return {
        "name": name,
        "kind": _classify_span(name, attrs),
        "startMs": start_ms,
        "durationMs": duration_ms,
        "attributes": attrs,
        # Mirror keys kept for the existing AgentReasoningTraces
        # waterfall component which reads ``start_ms`` / ``duration_ms``
        # and the optional ``agent`` / ``tool`` fields.
        "start_ms": start_ms,
        "duration_ms": duration_ms,
        "agent": attrs.get("gen_ai.agent.name") or None,
        "tool": attrs.get("gen_ai.tool.name") or None,
    }


def _public_span(span: Dict[str, Any]) -> Dict[str, Any]:
    """Return the browser-safe subset of an extracted span."""
    attrs = span.get("attributes") or {}
    return {
        **span,
        "attributes": {
            key: attrs[key]
            for key in _PUBLIC_SPAN_ATTRIBUTE_KEYS
            if key in attrs
        },
    }


def _public_spans(spans: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_public_span(span) for span in spans]


def extract_trace(spans: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
    """Extract the current trace in the inspector's expected shape.

    Args:
        spans: Optional iterable of ``ReadableSpan`` objects. When
            ``None`` (the default) the spans captured by
            :func:`init_span_capture` are read and the exporter is
            cleared so the next request starts with a fresh buffer.

    Returns:
        A dict with three keys:

        - ``spans``: ordered list of ``{ name, kind, startMs,
          durationMs, attributes }`` entries.
        - ``totalMs``: end-to-end duration in milliseconds, measured
          from the earliest span start to the latest span end.
        - ``specialistRoute``: the specialist tool name the
          orchestrator routed to (e.g. ``"product_recommendation_
          agent"``), or the empty string when no specialist fired.
    """
    finished: List[Any]
    if spans is None:
        if not OTEL_WORKING or _span_exporter is None:
            return {
                "spans": [],
                "totalMs": 0,
                "specialistRoute": "",
                "otel_enabled": False,
                "reason": OTEL_FAILURE_REASON,
            }
        try:
            finished = list(_span_exporter.get_finished_spans())
        except Exception:
            logger.exception("Failed to read finished spans")
            return {
                "spans": [],
                "totalMs": 0,
                "specialistRoute": "",
                "otel_enabled": False,
                "reason": f"Failed to read finished spans. {_INIT_ORDER_HINT}",
            }
    else:
        finished = list(spans)

    if not finished:
        return {
            "spans": [],
            "totalMs": 0,
            "specialistRoute": "",
            "otel_enabled": OTEL_WORKING,
        }

    # Order by start time so the waterfall renders in causal order.
    finished.sort(key=lambda s: s.start_time or 0)
    base_ns = finished[0].start_time or 0
    end_ns = max((s.end_time or s.start_time or 0) for s in finished)
    base_ms = int(base_ns / 1_000_000)
    total_ms = max(int((end_ns - base_ns) / 1_000_000), 0)

    out_spans = [_span_to_dict(s, base_ms) for s in finished]

    # Pick the first specialist span as the routing signal. Falls back
    # to the specialist nested agent span if no execute_tool span
    # surfaced (e.g. direct specialist invocation without the
    # orchestrator).
    specialist_route = ""
    for s in out_spans:
        if s["kind"] == "specialist":
            specialist_route = (
                s["attributes"].get("gen_ai.tool.name")
                or s["attributes"].get("gen_ai.agent.name")
                or ""
            )
            if specialist_route:
                break

    # Clear only when reading from the module-level exporter so callers
    # passing their own span list remain idempotent.
    if spans is None and _span_exporter is not None:
        try:
            _span_exporter.clear()
        except Exception:  # pragma: no cover - defensive
            pass

    return {
        "spans": out_spans,
        "totalMs": total_ms,
        "specialistRoute": specialist_route,
        "otel_enabled": True,
    }


def _span_trace_id(span: Any) -> Optional[int]:
    """Return the OpenTelemetry trace id for ``span`` when available."""
    context = getattr(span, "context", None)
    trace_id = getattr(context, "trace_id", None)
    if trace_id:
        return trace_id
    return None


def _filter_spans_for_session(
    spans: List[Any],
    session_id: Optional[str],
    user_id: Optional[str] = None,
) -> List[Any]:
    """Return spans in traces tagged for the requested owned session."""
    if not session_id:
        return spans

    wanted = str(session_id)
    directly_tagged = [
        span
        for span in spans
        if str((getattr(span, "attributes", None) or {}).get("session.id") or "")
        == wanted
    ]
    if user_id is not None:
        owner = str(user_id)
        owned = [
            span
            for span in directly_tagged
            if str(
                (getattr(span, "attributes", None) or {}).get("session.user")
                or ""
            )
            == owner
        ]
        if not owned:
            return []
        directly_tagged = owned

    directly_tagged_ids = {id(span) for span in directly_tagged}
    tagged_trace_ids = {
        trace_id
        for span in directly_tagged
        for trace_id in [_span_trace_id(span)]
        if trace_id is not None
    }
    if not tagged_trace_ids:
        return directly_tagged

    return [
        span
        for span in spans
        if _span_trace_id(span) in tagged_trace_ids or id(span) in directly_tagged_ids
    ]


def extract_agent_execution_from_otel(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible bridge used by ``services.chat`` and the
    existing ``AgentReasoningTraces`` frontend component.

    Returns the same structure as :func:`extract_trace` plus the legacy
    ``agent_steps`` / ``tool_calls`` / ``waterfall`` keys so the older
    SSE payload stays intact while the inspector consumes the new
    ``spans`` / ``totalMs`` / ``specialistRoute`` fields.

    When OTEL is not working, returns ``otel_enabled=False`` with a
    ``reason`` string. Callers MUST NOT synthesize replacement spans —
    the frontend banner depends on seeing this payload verbatim.
    """
    if not OTEL_WORKING or _span_exporter is None:
        return _failed_execution(OTEL_FAILURE_REASON)

    try:
        spans = list(_span_exporter.get_finished_spans())
    except Exception:
        reason = f"Failed to read finished spans. {_INIT_ORDER_HINT}"
        logger.exception("Failed to read finished spans")
        return _failed_execution(reason)

    spans = _filter_spans_for_session(spans, session_id)

    if not spans:
        return _empty_execution()

    trace = extract_trace(spans)

    agent_steps: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    waterfall: List[Dict[str, Any]] = []

    for s in trace["spans"]:
        attrs = s["attributes"]
        agent_name = attrs.get("gen_ai.agent.name") or ""
        tool_name = attrs.get("gen_ai.tool.name") or ""
        waterfall.append(
            {
                "name": s["name"],
                "agent": agent_name or None,
                "tool": tool_name or None,
                "start_ms": s["startMs"],
                "duration_ms": s["durationMs"],
                "tokens": attrs.get("gen_ai.usage.total_tokens", 0),
            }
        )
        if s["name"].startswith("invoke_agent"):
            agent_steps.append(
                {
                    "agent": agent_name or "Agent",
                    "action": f"Processing ({s['name']})",
                    "status": "completed",
                    "timestamp": s["startMs"] / 1000.0,
                    "duration_ms": s["durationMs"],
                }
            )
        if tool_name:
            tool_calls.append(
                {
                    "tool": tool_name,
                    "params": f"via {agent_name}" if agent_name else "",
                    "result": f"{s['durationMs']}ms",
                    "timestamp": s["startMs"] / 1000.0,
                    "duration_ms": s["durationMs"],
                    "status": "success",
                }
            )

    return {
        "agent_steps": agent_steps,
        "tool_calls": tool_calls,
        "reasoning_steps": [],
        "waterfall": waterfall,
        "spans": _public_spans(trace["spans"]),
        "totalMs": trace["totalMs"],
        "specialistRoute": trace["specialistRoute"],
        "total_duration_ms": trace["totalMs"],
        "success_rate": 1.0,
        "otel_enabled": True,
        "span_count": len(spans),
    }


def get_waterfall_data(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the current trace in the shape
    ``{ spans, totalMs, specialistRoute, waterfall, span_count, otel_enabled }``
    for the ``/api/traces/waterfall`` endpoint and the ``/inspector`` view.

    When OTEL is not working, returns ``otel_enabled=False`` + ``reason``
    so the frontend can render the "telemetry unavailable" banner.
    """
    if not OTEL_WORKING or _span_exporter is None:
        return {
            "spans": [],
            "totalMs": 0,
            "specialistRoute": "",
            "waterfall": [],
            "span_count": 0,
            "otel_enabled": False,
            "reason": OTEL_FAILURE_REASON,
        }

    try:
        finished = list(_span_exporter.get_finished_spans())
    except Exception:
        reason = f"Failed to read spans for waterfall. {_INIT_ORDER_HINT}"
        logger.exception("Failed to read spans for waterfall")
        return {
            "spans": [],
            "totalMs": 0,
            "specialistRoute": "",
            "waterfall": [],
            "span_count": 0,
            "otel_enabled": False,
            "reason": reason,
        }

    finished = _filter_spans_for_session(finished, session_id, user_id)
    trace = extract_trace(finished)
    # Legacy waterfall shape for AgentReasoningTraces keeps the same
    # start/duration fields as the new spans list.
    waterfall = [
        {
            "name": s["name"],
            "agent": s["attributes"].get("gen_ai.agent.name") or None,
            "tool": s["attributes"].get("gen_ai.tool.name") or None,
            "start_ms": s["startMs"],
            "duration_ms": s["durationMs"],
            "tokens": s["attributes"].get("gen_ai.usage.total_tokens", 0),
        }
        for s in trace["spans"]
    ]
    return {
        "spans": _public_spans(trace["spans"]),
        "totalMs": trace["totalMs"],
        "specialistRoute": trace["specialistRoute"],
        "waterfall": waterfall,
        "span_count": len(finished),
        "otel_enabled": True,
    }


def _empty_execution() -> Dict[str, Any]:
    """Return an empty execution payload for the pre-first-request state
    when OTEL is correctly initialized but no spans have been captured
    yet. Distinct from :func:`_failed_execution`."""
    return {
        "agent_steps": [],
        "tool_calls": [],
        "reasoning_steps": [],
        "waterfall": [],
        "spans": [],
        "totalMs": 0,
        "specialistRoute": "",
        "total_duration_ms": 0,
        "success_rate": 0,
        "otel_enabled": True,
    }


def _failed_execution(reason: str) -> Dict[str, Any]:
    """Return a structured failure payload for callers that need to
    distinguish "no spans yet" from "OTEL is broken". The frontend
    renders the banner iff ``otel_enabled`` is False AND ``reason`` is
    set — do NOT synthesize ``agent_steps`` or ``tool_calls``."""
    return {
        "agent_steps": [],
        "tool_calls": [],
        "reasoning_steps": [],
        "waterfall": [],
        "spans": [],
        "totalMs": 0,
        "specialistRoute": "",
        "total_duration_ms": 0,
        "success_rate": 0,
        "otel_enabled": False,
        "reason": reason,
    }
# === REFERENCE: Observability — END ===
