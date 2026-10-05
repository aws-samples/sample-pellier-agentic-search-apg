"""
Tests for the evidence-span vocabulary (governed-search design, Stage 1).

These assert the participant-facing contract, not implementation detail:

* the canonical attribute names, because CLI reconstruction queries filter
  on those literal strings;
* that absent values are omitted rather than stringified as "None";
* that a missing or non-SDK tracer degrades to a no-op instead of raising,
  because observability must never fail a turn.
"""
from __future__ import annotations

import pytest

from services import evidence_spans as ev


# ---------------------------------------------------------------------------
# Attribute vocabulary
# ---------------------------------------------------------------------------

def test_attribute_names_are_namespaced_and_stable():
    """These strings are quoted in participant CLI queries. Pin them."""
    assert ev.ATTR_TURN_ID == "pellier.turn_id"
    assert ev.ATTR_PRINCIPAL_SUB == "pellier.principal_sub"
    assert ev.ATTR_CALLER == "pellier.caller"
    assert ev.ATTR_EXECUTION_OUTCOME == "pellier.execution_outcome"


def test_span_names_are_the_teaching_boundaries():
    assert ev.SPAN_ROUTING == "routing"
    assert ev.tool_span_name("give_store_credit") == "tool.give_store_credit"


def test_tool_span_name_without_a_tool_degrades_to_the_prefix():
    assert ev.tool_span_name("") == "tool"


def test_absent_values_are_omitted_not_stringified():
    """`pellier.principal_sub="None"` would read as an identity named None."""
    attrs = ev.evidence_attributes(turn_id="turn-1", principal_sub=None)
    assert attrs == {ev.ATTR_TURN_ID: "turn-1"}
    assert ev.ATTR_PRINCIPAL_SUB not in attrs


def test_false_and_zero_are_preserved():
    """`authenticated=False` is a real, load-bearing value, not an absence."""
    attrs = ev.evidence_attributes(authenticated=False, persona_is_simulated=True)
    assert attrs[ev.ATTR_AUTHENTICATED] is False
    assert attrs[ev.ATTR_PERSONA_SIMULATED] is True


def test_full_attribute_set_maps_every_reconstruction_field():
    attrs = ev.evidence_attributes(
        turn_id="turn-1",
        principal_sub="sub-abc",
        authenticated=True,
        persona_is_simulated=False,
        caller="in-process",
        execution_outcome="denied",
        tool="give_store_credit",
    )
    assert attrs == {
        ev.ATTR_TURN_ID: "turn-1",
        ev.ATTR_PRINCIPAL_SUB: "sub-abc",
        ev.ATTR_AUTHENTICATED: True,
        ev.ATTR_PERSONA_SIMULATED: False,
        ev.ATTR_CALLER: "in-process",
        ev.ATTR_EXECUTION_OUTCOME: "denied",
        ev.ATTR_TOOL: "give_store_credit",
    }


# ---------------------------------------------------------------------------
# Degraded path: observability must never fail a turn
# ---------------------------------------------------------------------------

def test_spans_are_no_ops_when_tracing_is_unavailable(monkeypatch):
    monkeypatch.setattr(ev, "_tracer", lambda: None)

    with ev.routing_span(turn_id="t") as span:
        assert span is None
    with ev.tool_span("check_stock", turn_id="t") as span:
        assert span is None


def test_set_execution_outcome_tolerates_absent_span():
    ev.set_execution_outcome(None, "denied")  # must not raise


def test_a_failing_tracer_does_not_propagate(monkeypatch):
    """A tracing bug mid-turn must not surface as a turn failure."""

    class Boom:
        def start_as_current_span(self, *_args, **_kwargs):
            raise RuntimeError("exporter exploded")

    monkeypatch.setattr(ev, "_tracer", lambda: Boom())

    with ev.tool_span("give_store_credit", turn_id="t") as span:
        assert span is None


def test_a_caller_body_exception_propagates_unchanged(monkeypatch, recorded_spans):
    """An error INSIDE the span body is the caller's, not the span's.

    The earlier implementation caught it and yielded a second time, so the
    caller saw contextlib's "generator didn't stop after throw()" instead of
    the real error. The span must still be ended and exported.
    """
    tracer, exporter = recorded_spans
    monkeypatch.setattr(ev, "_tracer", lambda: tracer)

    with pytest.raises(ValueError, match="classification failed"):
        with ev.routing_span(turn_id="t"):
            raise ValueError("classification failed")

    finished = exporter.get_finished_spans()
    assert [span.name for span in finished] == [ev.SPAN_ROUTING]


# ---------------------------------------------------------------------------
# Recording path, with a real in-memory SDK provider
# ---------------------------------------------------------------------------

@pytest.fixture
def recorded_spans():
    """Give this module its own SDK provider and capture finished spans.

    Deliberately does not touch the global provider the app configures: the
    fixture builds a tracer directly and patches `_tracer`, so these tests
    never depend on app startup order.
    """
    sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
    export = pytest.importorskip("opentelemetry.sdk.trace.export")
    in_memory = pytest.importorskip(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter"
    )

    provider = sdk_trace.TracerProvider()
    exporter = in_memory.InMemorySpanExporter()
    provider.add_span_processor(export.SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_tool_span_records_name_and_canonical_attributes(monkeypatch, recorded_spans):
    tracer, exporter = recorded_spans
    monkeypatch.setattr(ev, "_tracer", lambda: tracer)

    with ev.tool_span(
        "give_store_credit",
        turn_id="turn-42",
        principal_sub="sub-abc",
        caller="in-process",
    ) as span:
        ev.set_execution_outcome(span, "denied")

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    recorded = finished[0]
    assert recorded.name == "tool.give_store_credit"
    assert recorded.attributes[ev.ATTR_TURN_ID] == "turn-42"
    assert recorded.attributes[ev.ATTR_PRINCIPAL_SUB] == "sub-abc"
    assert recorded.attributes[ev.ATTR_CALLER] == "in-process"
    assert recorded.attributes[ev.ATTR_TOOL] == "give_store_credit"
    assert recorded.attributes[ev.ATTR_EXECUTION_OUTCOME] == "denied"


def test_anonymous_turn_omits_principal_but_states_it_is_unauthenticated(
    monkeypatch, recorded_spans
):
    """An anonymous turn must be distinguishable from an instrumentation gap."""
    tracer, exporter = recorded_spans
    monkeypatch.setattr(ev, "_tracer", lambda: tracer)

    with ev.routing_span(turn_id="turn-9", principal_sub=None, authenticated=False):
        pass

    recorded = exporter.get_finished_spans()[0]
    assert ev.ATTR_PRINCIPAL_SUB not in recorded.attributes
    assert recorded.attributes[ev.ATTR_AUTHENTICATED] is False


def test_annotate_current_span_enriches_rather_than_duplicating(recorded_spans):
    """The tool boundary must add attributes to Strands' span, not add a span."""
    tracer, exporter = recorded_spans

    # Stand in for the span Strands' [otel] integration already opens.
    with tracer.start_as_current_span("execute_tool give_store_credit"):
        applied = ev.annotate_current_span(
            turn_id="turn-11",
            principal_sub="sub-abc",
            caller="agent",
            tool="give_store_credit",
        )

    assert applied is True
    finished = exporter.get_finished_spans()
    # Exactly one span: we enriched, we did not create a second.
    assert len(finished) == 1
    recorded = finished[0]
    assert recorded.name == "execute_tool give_store_credit"
    assert recorded.attributes[ev.ATTR_TURN_ID] == "turn-11"
    assert recorded.attributes[ev.ATTR_CALLER] == "agent"


def test_annotate_current_span_reports_false_with_no_recording_span():
    """No active span is a degraded state the caller may log, not a crash."""
    assert ev.annotate_current_span(turn_id="turn-1") is False


def test_annotate_current_span_is_a_no_op_with_nothing_to_apply(recorded_spans):
    tracer, _ = recorded_spans
    with tracer.start_as_current_span("x"):
        assert ev.annotate_current_span() is False


def test_spans_do_not_carry_payloads(monkeypatch, recorded_spans):
    """Guard the spec 8.5 prohibition: no args, SQL, payloads, or results."""
    tracer, exporter = recorded_spans
    monkeypatch.setattr(ev, "_tracer", lambda: tracer)

    with ev.tool_span("search_products", turn_id="turn-1"):
        pass

    recorded = exporter.get_finished_spans()[0]
    forbidden = {"args", "sql", "result", "payload", "query", "customer"}
    for key in recorded.attributes:
        suffix = key.rsplit(".", 1)[-1].lower()
        assert suffix not in forbidden, f"payload-shaped attribute leaked: {key}"
