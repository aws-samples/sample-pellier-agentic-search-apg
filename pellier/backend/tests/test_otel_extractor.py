"""Trace-extraction tests for Challenge 8.

Validates Requirement 2.5.4 and 5.4.1 from
`.kiro/specs/pellier-storefront/requirements.md`:

  2.5.4  The C8 challenge block in ``services/otel_trace_extractor.py``
         SHALL extract OpenTelemetry spans produced by the agent run
         and format them for the ``/inspector`` view as
         ``{ spans, totalMs, specialistRoute }`` where every span has
         ``{ name, kind, startMs, durationMs, attributes }``.
  5.4.1  Every orchestrator run SHALL produce at least one
         ``orchestrator`` span, one ``specialist`` span and one
         ``tool`` span extractable by ``otel_trace_extractor``.

The orchestrator is exercised through the same stub pattern as
``tests/test_orchestrator_routing.py``: Strands ``Agent`` and
``BedrockModel`` are swapped for recorders, specialists are swapped for
closures that emit OTEL spans themselves so the extractor sees the
orchestrator → specialist → tool hand-off without any live Bedrock or
DB round-trip.

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_otel_extractor.py -v
"""

from __future__ import annotations

from typing import Any, Iterable

import pytest
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


# ---------------------------------------------------------------------------
# OTEL setup — per-test tracer provider with an in-memory exporter
# ---------------------------------------------------------------------------


@pytest.fixture
def otel_spans(monkeypatch: pytest.MonkeyPatch) -> Iterable[InMemorySpanExporter]:
    """Install a fresh ``TracerProvider`` + ``InMemorySpanExporter`` as
    the global tracer so ``services.otel_trace_extractor`` can read
    back every span emitted during the test.
    """
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # ``trace.set_tracer_provider`` only takes once per process. Patch
    # the backing global directly so each test gets an isolated
    # provider without relying on module-reload tricks.
    monkeypatch.setattr(otel_trace, "_TRACER_PROVIDER", provider, raising=False)
    monkeypatch.setattr(
        otel_trace,
        "_TRACER_PROVIDER_SET_ONCE",
        otel_trace.Once(),
        raising=False,
    )

    import services.otel_trace_extractor as extractor

    monkeypatch.setattr(extractor, "_span_exporter", exporter)
    # Bug 3 fix: extractor now gates reads on OTEL_WORKING so a broken
    # TracerProvider surfaces a banner instead of silently returning
    # empty spans. Tests bypass init_span_capture() by wiring the
    # exporter directly, so flip the flag too.
    monkeypatch.setattr(extractor, "OTEL_WORKING", True)
    monkeypatch.setattr(extractor, "OTEL_FAILURE_REASON", "")
    try:
        yield exporter
    finally:
        exporter.clear()


# ---------------------------------------------------------------------------
# Orchestrator + specialist stubs (mirrors test_orchestrator_routing.py)
# ---------------------------------------------------------------------------


class _StubBedrockModel:
    """Swap for ``BedrockModel``. Captures kwargs so the test can assert
    the Haiku 4.5 model id is still wired."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _StubOrchestratorAgent:
    """Swap for ``strands.Agent`` as used by ``create_orchestrator``.

    On call it opens an ``invoke_agent orchestrator`` span tagged with
    the orchestrator's trace_attributes, then invokes exactly one
    specialist from its tools list (the recommendation agent is a safe
    default — the test asserts kind-by-kind, not routing identity).
    """

    last_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs
        # Mirror Strands' ``Agent.trace_attributes`` so the dispatcher's
        # ``orchestrator.trace_attributes = {...}`` assignment lands.
        self.trace_attributes: dict[str, Any] = {}

    def add_hook(self, _hook: Any) -> None:  # pragma: no cover - unused
        pass

    def __call__(self, query: str) -> str:
        tracer = otel_trace.get_tracer("test-orchestrator")
        with tracer.start_as_current_span("invoke_agent orchestrator") as span:
            span.set_attribute("gen_ai.agent.name", "orchestrator")
            for k, v in self.trace_attributes.items():
                if isinstance(v, (str, int, float, bool)):
                    span.set_attribute(k, v)
            # Route to the recommendation specialist (the default) —
            # the test does not assert routing identity, only that an
            # orchestrator / specialist / tool span triple is present.
            tools = type(self).last_kwargs.get("tools", [])
            target_name = "recommendation"
            for t in tools:
                name = getattr(t, "tool_name", None) or getattr(
                    getattr(t, "__wrapped__", t), "__name__", repr(t)
                )
                if name == target_name:
                    inner = getattr(t, "__wrapped__", t)
                    inner(query=query)
                    break
            return f"[stub-orchestrator] {query}"


@pytest.fixture
def stubbed_specialists(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Replace each specialist @tool's wrapped callable with a closure
    that emits an ``execute_tool {specialist}`` span containing a
    nested ``invoke_agent {specialist}`` span (Strands' real shape)
    and a child ``execute_tool find_pieces`` span so the extractor
    sees a full orchestrator → specialist → tool trace.
    """
    import agents.orchestrator as orch

    calls: dict[str, list[str]] = {
        "search": [],
        "recommendation": [],
        "pricing": [],
        "inventory": [],
        "support": [],
    }

    def _patch(tool_obj: Any, name: str) -> None:
        def _recorder(query: str) -> str:
            calls[name].append(query)
            tracer = otel_trace.get_tracer(f"test-{name}")
            # execute_tool span — Strands' DecoratedFunctionTool wraps
            # each @tool specialist in this span when the orchestrator
            # invokes it.
            with tracer.start_as_current_span(f"execute_tool {name}") as tspan:
                tspan.set_attribute("gen_ai.tool.name", name)
                tspan.set_attribute("gen_ai.tool.call.id", f"call-{name}")
                # Nested invoke_agent span — the specialist internally
                # constructs its own Strands Agent (see
                # curator.py).
                with tracer.start_as_current_span(
                    f"invoke_agent {name}"
                ) as aspan:
                    aspan.set_attribute("gen_ai.agent.name", name)
                    # Leaf tool call — the specialist calls one of its
                    # own tools (e.g. find_pieces, side_by_side).
                    with tracer.start_as_current_span(
                        "execute_tool find_pieces"
                    ) as leaf:
                        leaf.set_attribute(
                            "gen_ai.tool.name", "find_pieces"
                        )
                        leaf.set_attribute(
                            "gen_ai.tool.call.id", "call-search-products"
                        )
            return f"[stub-{name}] ok"

        monkeypatch.setattr(tool_obj, "__wrapped__", _recorder, raising=False)
        monkeypatch.setattr(tool_obj, "_tool_func", _recorder, raising=False)

    _patch(orch.search, "search")
    _patch(orch.recommendation, "recommendation")
    _patch(orch.pricing, "pricing")
    _patch(orch.inventory, "inventory")
    _patch(orch.support, "support")

    return calls


@pytest.fixture
def stubbed_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    stubbed_specialists: dict[str, list[str]],
):
    """Return ``create_orchestrator`` with ``Agent`` and ``BedrockModel``
    swapped for OTEL-emitting stubs."""
    import agents.orchestrator as orch

    monkeypatch.setattr(orch, "Agent", _StubOrchestratorAgent)
    monkeypatch.setattr(orch, "BedrockModel", _StubBedrockModel)
    return orch.create_orchestrator


# ---------------------------------------------------------------------------
# Requirement 5.4.1 — orchestrator run produces a three-kind trace
# ---------------------------------------------------------------------------


def test_extract_trace_returns_orchestrator_specialist_and_tool_spans(
    otel_spans: InMemorySpanExporter,
    stubbed_orchestrator,
    stubbed_specialists,
) -> None:
    """The extractor SHALL return at least one orchestrator span, one
    specialist span, and one tool span for a single orchestrator run
    (Req 5.4.1)."""
    import asyncio

    import services.agentcore_runtime as rt
    from services.otel_trace_extractor import extract_trace

    # Drive the run through the dispatcher the streaming path uses so
    # trace_attributes are attached exactly the way the SSE handler
    # does in production.
    asyncio.run(
        rt.run_agent(
            message="something for warm evenings out",
            session_id="sess-otel-1",
            user_id="user-otel-1",
        )
    )

    # The dispatcher drained the exporter into ``_latest_trace`` on the
    # in-process path; read it back for the assertion.
    trace = rt.get_latest_trace()

    assert {"spans", "totalMs", "specialistRoute"} <= set(trace.keys()), (
        f"extract_trace SHALL return at least the inspector shape; got {sorted(trace)!r}"
    )

    kinds = [s["kind"] for s in trace["spans"]]
    assert kinds.count("orchestrator") >= 1, (
        f"extract_trace SHALL surface ≥1 orchestrator span per run; "
        f"kinds seen: {kinds!r}"
    )
    assert kinds.count("specialist") >= 1, (
        f"extract_trace SHALL surface ≥1 specialist span per run; "
        f"kinds seen: {kinds!r}"
    )
    assert kinds.count("tool") >= 1, (
        f"extract_trace SHALL surface ≥1 tool span per run; "
        f"kinds seen: {kinds!r}"
    )

    # Every span carries the inspector fields, not a raw OTEL dump.
    for s in trace["spans"]:
        assert set(s.keys()) >= {
            "name",
            "kind",
            "startMs",
            "durationMs",
            "attributes",
        }, f"span missing inspector fields: {sorted(s)!r}"
        assert isinstance(s["startMs"], int) and s["startMs"] >= 0
        assert isinstance(s["durationMs"], int) and s["durationMs"] >= 0

    # totalMs bounds every span's completion time (Req 2.5.4).
    assert trace["totalMs"] >= 0
    for s in trace["spans"]:
        assert s["startMs"] + s["durationMs"] <= trace["totalMs"] + 1, (
            f"span {s['name']!r} end ({s['startMs'] + s['durationMs']}ms) "
            f"exceeds trace totalMs ({trace['totalMs']}ms)"
        )

    # specialistRoute points at the specialist the orchestrator called.
    assert trace["specialistRoute"] == "recommendation", (
        f"specialistRoute SHALL name the routed specialist; got "
        f"{trace['specialistRoute']!r}"
    )


# ---------------------------------------------------------------------------
# Requirement 2.5.4 — explicit shape sanity check
# ---------------------------------------------------------------------------


def test_extract_trace_span_kind_classification(
    otel_spans: InMemorySpanExporter,
) -> None:
    """Given hand-emitted Strands-shaped spans, ``extract_trace`` SHALL
    classify them by kind per the design in
    ``services.otel_trace_extractor._classify_span``."""
    from services.otel_trace_extractor import extract_trace

    tracer = otel_trace.get_tracer("test-classification")
    with tracer.start_as_current_span("invoke_agent orchestrator") as root:
        root.set_attribute("gen_ai.agent.name", "orchestrator")
        with tracer.start_as_current_span(
            "execute_tool search"
        ) as specialist:
            specialist.set_attribute("gen_ai.tool.name", "search")
            with tracer.start_as_current_span(
                "execute_tool whats_trending"
            ) as tool:
                tool.set_attribute("gen_ai.tool.name", "whats_trending")

    trace = extract_trace()

    kinds = {s["attributes"].get("gen_ai.tool.name") or s["attributes"].get(
        "gen_ai.agent.name"
    ): s["kind"] for s in trace["spans"]}

    assert kinds["orchestrator"] == "orchestrator"
    assert kinds["search"] == "specialist"
    assert kinds["whats_trending"] == "tool"
    assert trace["specialistRoute"] == "search"


def test_extract_trace_returns_empty_shape_when_no_spans(
    otel_spans: InMemorySpanExporter,
) -> None:
    """Before the first orchestrator call, the inspector SHALL see an
    empty but well-formed trace payload."""
    from services.otel_trace_extractor import extract_trace

    trace = extract_trace()
    # Bug 3: payload now carries otel_enabled so the frontend can
    # distinguish "OTEL working but no spans yet" from "OTEL broken".
    assert trace["spans"] == []
    assert trace["totalMs"] == 0
    assert trace["specialistRoute"] == ""
    assert trace["otel_enabled"] is True


def test_agentcore_runtime_drains_trace_after_inprocess_run(
    otel_spans: InMemorySpanExporter,
    stubbed_orchestrator,
    stubbed_specialists,
) -> None:
    """The streaming path (``_run_orchestrator_inprocess``) SHALL push
    the extracted trace into ``get_latest_trace()`` so the ``/inspector``
    view can fetch it without a second round-trip to the extractor."""
    import asyncio

    import services.agentcore_runtime as rt

    asyncio.run(
        rt.run_agent(
            message="pieces that travel well",
            session_id="sess-otel-2",
            user_id=None,
        )
    )

    trace = rt.get_latest_trace()
    assert trace["spans"], "latest trace SHALL be populated after a run"
    assert any(s["kind"] == "orchestrator" for s in trace["spans"])
    assert any(s["kind"] == "specialist" for s in trace["spans"])
    assert any(s["kind"] == "tool" for s in trace["spans"])
