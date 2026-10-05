"""
Evidence spans — the teaching boundaries of one governed turn.

Stage 1 of the governed-search design. This module owns the canonical span
vocabulary so the observability spine has exactly one definition of it. See
`docs/superpowers/specs/2026-08-18-governed-agentic-search-design.md`
sections 8.3 through 8.5.

Why a separate module rather than inline `tracer.start_as_current_span`
calls in `chat.py`:

* **One vocabulary.** Attribute names are a participant-facing contract. A
  workshop CLI query filters on `pellier.turn_id`; if two call sites spell
  that differently the reconstruction exercise silently returns nothing.
  Defining the names once makes that impossible.
* **Two boundaries, not a call graph.** Spans teach architecture (`routing`
  and `tool`), not the Python call stack. Exposing only these helpers makes
  the wrong thing hard to do. Authorization has no span here: AgentCore
  Policy decides at the Gateway, the desk stores its answer on the review
  (`approvals.last_attempt`), and the tables hold what ran.
* **Observability must never fail a turn.** Same rule the tool-audit writer
  follows: failing to observe cannot fail the thing being observed. Every
  helper degrades to a no-op when the OpenTelemetry SDK is absent or the
  active provider is not SDK-backed.

What does NOT belong on a span (spec 8.5, Invariant 11): tool arguments,
generated SQL, customer payloads, or tool results. Spans locate and
correlate; Aurora artifacts prove. Generated SQL lives in the governed-query
receipt.
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical attribute names.
#
# Namespaced under `pellier.` so they cannot collide with OpenTelemetry
# semantic conventions or the GenAI conventions Strands emits. These strings
# are quoted verbatim in participant CLI queries — treat them as an API.
# ---------------------------------------------------------------------------
ATTR_TURN_ID = "pellier.turn_id"
ATTR_PRINCIPAL_SUB = "pellier.principal_sub"
ATTR_AUTHENTICATED = "pellier.authenticated"
ATTR_PERSONA_SIMULATED = "pellier.persona_is_simulated"
ATTR_CALLER = "pellier.caller"
ATTR_EXECUTION_OUTCOME = "pellier.execution_outcome"
ATTR_TOOL = "pellier.tool"

# The teaching boundaries. Span names are also a participant contract.
SPAN_ROUTING = "routing"
SPAN_TOOL_PREFIX = "tool"

_TRACER_NAME = "pellier.evidence"


def _tracer() -> Optional[Any]:
    """Return a tracer, or None when tracing is unavailable.

    Returns None rather than raising so callers stay branch-free. A missing
    SDK is a degraded observability state, never a turn failure.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        provider = trace.get_tracer_provider()
        # A non-SDK provider (the default no-op) accepts spans and discards
        # them. Reporting that as working would make the workshop's
        # "spans exist" proof a lie, so treat it as unavailable.
        if not isinstance(provider, TracerProvider):
            return None
        return trace.get_tracer(_TRACER_NAME)
    except Exception:  # pragma: no cover - absence of SDK is the degraded path
        return None


def evidence_attributes(
    *,
    turn_id: Optional[str] = None,
    principal_sub: Optional[str] = None,
    authenticated: Optional[bool] = None,
    persona_is_simulated: Optional[bool] = None,
    caller: Optional[str] = None,
    execution_outcome: Optional[str] = None,
    tool: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the canonical attribute dict, omitting anything absent.

    `None` is dropped rather than serialized. A span carrying
    `pellier.principal_sub="None"` would read as an identity named "None" in
    a CLI query, which is worse than an absent attribute: the participant
    cannot distinguish "anonymous" from "we forgot to set it".
    """
    candidates = {
        ATTR_TURN_ID: turn_id,
        ATTR_PRINCIPAL_SUB: principal_sub,
        ATTR_AUTHENTICATED: authenticated,
        ATTR_PERSONA_SIMULATED: persona_is_simulated,
        ATTR_CALLER: caller,
        ATTR_EXECUTION_OUTCOME: execution_outcome,
        ATTR_TOOL: tool,
    }
    return {key: value for key, value in candidates.items() if value is not None}


@contextmanager
def evidence_span(name: str, **attributes: Any) -> Iterator[Optional[Any]]:
    """Open one teaching span, or yield None when tracing is unavailable.

    Callers may set further attributes on the yielded span, but must respect
    the payload prohibition in the module docstring.
    """
    tracer = _tracer()
    if tracer is None:
        yield None
        return

    resolved = evidence_attributes(**attributes)
    # Enter the span outside the yield so a TRACING failure degrades to
    # untraced, while an exception raised by the caller's body propagates
    # unchanged. Wrapping the yield itself in try/except would yield a
    # second time after a body exception, and contextlib would replace the
    # original error with "generator didn't stop after throw()".
    try:
        span_cm = tracer.start_as_current_span(name, attributes=resolved)
        span = span_cm.__enter__()
    except Exception:
        logger.warning(
            "evidence span %s failed to open; continuing untraced", name, exc_info=True
        )
        yield None
        return

    try:
        yield span
    except BaseException:
        exc_info = sys.exc_info()
        try:
            span_cm.__exit__(*exc_info)
        except Exception:
            logger.warning(
                "evidence span %s failed to close; continuing", name, exc_info=True
            )
        raise
    else:
        try:
            span_cm.__exit__(None, None, None)
        except Exception:
            logger.warning(
                "evidence span %s failed to close; continuing", name, exc_info=True
            )


@contextmanager
def routing_span(
    *,
    turn_id: Optional[str] = None,
    principal_sub: Optional[str] = None,
    authenticated: Optional[bool] = None,
    persona_is_simulated: Optional[bool] = None,
) -> Iterator[Optional[Any]]:
    """The intent-classification boundary."""
    with evidence_span(
        SPAN_ROUTING,
        turn_id=turn_id,
        principal_sub=principal_sub,
        authenticated=authenticated,
        persona_is_simulated=persona_is_simulated,
    ) as span:
        yield span


def tool_span_name(tool: str) -> str:
    """Return the canonical span name for a tool boundary."""
    return f"{SPAN_TOOL_PREFIX}.{tool}" if tool else SPAN_TOOL_PREFIX


@contextmanager
def tool_span(
    tool: str,
    *,
    turn_id: Optional[str] = None,
    principal_sub: Optional[str] = None,
    caller: Optional[str] = None,
    execution_outcome: Optional[str] = None,
) -> Iterator[Optional[Any]]:
    """The tool-execution boundary.

    Aurora remains authoritative for what actually changed. This span exists
    so an operator can locate the turn and join it to the durable receipt on
    `turn_id`.
    """
    with evidence_span(
        tool_span_name(tool),
        turn_id=turn_id,
        principal_sub=principal_sub,
        caller=caller,
        execution_outcome=execution_outcome,
        tool=tool,
    ) as span:
        yield span


def annotate_current_span(**attributes: Any) -> bool:
    """Add canonical attributes to the span already in context.

    This is the right tool for the **tool boundary**. Strands' `[otel]`
    integration already emits a span per tool call following the GenAI
    semantic conventions, so creating another one here would put two spans on
    every tool call and produce exactly the parallel ontology spec 8.4
    forbids. Instead we enrich the span that exists with the correlation and
    identity attributes the workshop reconstruction needs.

    Returns True when attributes were applied, False when there was no
    recording span to annotate. The boolean exists so a caller can log the
    degraded case; it must not change turn behavior.
    """
    resolved = evidence_attributes(**attributes)
    if not resolved:
        return False
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        # A non-recording span is the no-op default. Writing to it silently
        # discards the attributes, so report that as not-applied rather than
        # letting a caller believe the turn is traced.
        if span is None or not span.is_recording():
            return False
        for key, value in resolved.items():
            span.set_attribute(key, value)
        return True
    except Exception:  # pragma: no cover - defensive
        logger.debug("could not annotate current span", exc_info=True)
        return False


def set_execution_outcome(span: Optional[Any], outcome: str) -> None:
    """Record the outcome on an open span, tolerating an absent span."""
    if span is None:
        return
    try:
        span.set_attribute(ATTR_EXECUTION_OUTCOME, outcome)
    except Exception:  # pragma: no cover - defensive
        logger.debug("could not set execution outcome on span", exc_info=True)
