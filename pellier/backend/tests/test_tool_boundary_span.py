"""The tool boundary enriches the framework's span rather than adding one.

`services/chat.py`'s audit hooks are the join point between the two evidence
systems: they write the `pellier.tool_audit` row *and* stamp the correlation
and identity attributes onto the span Strands already opened for the tool
call. Both must carry the same `turn_id`, or a CloudWatch span query and a
SQL audit query resolve different turns and the reconstruction exercise
produces a contradiction.

The properties pinned here:

  1. Enrich, never duplicate — the hooks add attributes to the span in
     context and do not open a second one (spec 8.4).
  2. `turn_id` lands on both the span and the audit row's `args`.
  3. `principal_sub` reaches the span when verified, and is *absent* rather
     than "None" when anonymous.
  4. The recorded outcome distinguishes success from a tool error.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from services import evidence_spans as ev


pytest.importorskip("strands.hooks.events")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def recording_tracer():
    """An isolated SDK provider whose finished spans can be inspected."""
    sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
    export = pytest.importorskip("opentelemetry.sdk.trace.export")
    in_memory = pytest.importorskip(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter"
    )

    provider = sdk_trace.TracerProvider()
    exporter = in_memory.InMemorySpanExporter()
    provider.add_span_processor(export.SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class _FakeWriter:
    """Captures what the hooks would have written to Aurora."""

    def __init__(self) -> None:
        self.allows: List[Dict[str, Any]] = []
        self.afters: List[Dict[str, Any]] = []

    def record_allow(self, **kwargs: Any) -> None:
        self.allows.append(kwargs)

    def record_after(self, **kwargs: Any) -> None:
        self.afters.append(kwargs)


class _ToolUse(dict):
    """The Strands tool_use shape the hooks read."""


class _Event:
    def __init__(self, tool_use: Dict[str, Any], result: Any = None) -> None:
        self.tool_use = tool_use
        self.result = result


@pytest.fixture
def hooks(monkeypatch, recording_tracer):
    """Build the audit hooks with the writer faked and tracing captured."""
    tracer, exporter = recording_tracer
    monkeypatch.setattr(ev, "_tracer", lambda: tracer)

    writer = _FakeWriter()
    import services.tool_audit_writer as writer_module

    monkeypatch.setattr(writer_module, "record_allow", writer.record_allow)
    monkeypatch.setattr(writer_module, "record_after", writer.record_after)

    from services.chat import make_tool_audit_hooks

    def build(principal_sub: Optional[str] = None):
        return make_tool_audit_hooks(
            session_id="sess-1",
            turn_id="turn-abc",
            principal_sub=principal_sub,
        )

    return build, writer, tracer, exporter


def _run_tool(build, tracer, principal_sub=None, result="ok"):
    """Drive one tool call inside a span, the way Strands does."""
    before, after = build(principal_sub)
    event = _Event(
        _ToolUse({"toolUseId": "tu-1", "name": "check_stock", "input": {"product_query": "shirt"}}),
        result=result,
    )
    # Strands opens the tool span; the hooks run inside it.
    with tracer.start_as_current_span("execute_tool check_stock"):
        before(event)
        after(event)


# ---------------------------------------------------------------------------
# Enrich, never duplicate
# ---------------------------------------------------------------------------


def test_hooks_do_not_open_a_second_span(hooks):
    """Two spans per tool call is the parallel ontology spec 8.4 forbids."""
    build, _writer, tracer, exporter = hooks

    _run_tool(build, tracer)

    finished = exporter.get_finished_spans()
    assert len(finished) == 1, "the framework's span is the only tool span"
    assert finished[0].name == "execute_tool check_stock"


def test_turn_id_lands_on_both_the_span_and_the_audit_row(hooks):
    """The join key must be identical on both sides or they disagree."""
    build, writer, tracer, exporter = hooks

    _run_tool(build, tracer)

    span = exporter.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_TURN_ID] == "turn-abc"
    assert writer.allows[0]["args"]["turn_id"] == "turn-abc"


def test_span_names_the_tool_and_the_caller(hooks):
    build, _writer, tracer, exporter = hooks

    _run_tool(build, tracer)

    span = exporter.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_TOOL] == "check_stock"
    assert span.attributes[ev.ATTR_CALLER] == "agent"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_verified_principal_reaches_the_span(hooks):
    build, _writer, tracer, exporter = hooks

    _run_tool(build, tracer, principal_sub="sub-marco")

    span = exporter.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_PRINCIPAL_SUB] == "sub-marco"


def test_anonymous_turn_omits_the_principal_rather_than_writing_none(hooks):
    """`pellier.principal_sub="None"` would read as an identity named None.

    Absent and anonymous must be distinguishable from a forgotten attribute.
    """
    build, _writer, tracer, exporter = hooks

    _run_tool(build, tracer, principal_sub=None)

    span = exporter.get_finished_spans()[0]
    assert ev.ATTR_PRINCIPAL_SUB not in span.attributes


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------


def test_successful_execution_is_recorded_as_success(hooks):
    build, _writer, tracer, exporter = hooks

    _run_tool(build, tracer, result="ok")

    span = exporter.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_EXECUTION_OUTCOME] == "success"


def test_tool_error_is_not_reported_as_success(hooks):
    """An errored tool call that reads as success would misstate the turn."""
    build, _writer, tracer, exporter = hooks

    _run_tool(build, tracer, result={"status": "error", "content": [{"text": "boom"}]})

    span = exporter.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_EXECUTION_OUTCOME] != "success"


# ---------------------------------------------------------------------------
# Payload prohibition
# ---------------------------------------------------------------------------


def test_tool_arguments_never_reach_the_span(hooks):
    """Args belong in the audit row, not on a span (spec 8.5, invariant 11).

    The audit row is access-controlled Aurora data; a span is broadly
    readable telemetry. The tool's input travelled here in `tool_use.input`,
    so this asserts it stopped at the ledger.
    """
    build, writer, tracer, exporter = hooks

    _run_tool(build, tracer)

    span = exporter.get_finished_spans()[0]
    serialized = " ".join(f"{k}={v}" for k, v in span.attributes.items())
    assert "product_query" not in serialized
    assert "shirt" not in serialized
    # ...and it did reach the ledger, so this is a boundary, not a drop.
    assert writer.allows[0]["args"]["product_query"] == "shirt"
