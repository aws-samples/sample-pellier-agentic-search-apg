"""The policy boundary span records the decision Pellier resolved.

Cedar is evaluated by AgentCore Gateway, out of process, before the target
runs. Pellier never makes the decision — it resolves what the decision *was*
from the `pellier.governed_receipts` rows the Gateway rail wrote. This span is
that resolution, and it completes the reconstruction CLI's four legs:
identity, policy, execution, and the Aurora effect.

The property that carries the most risk is the absence case. An ordinary
in-process turn has no Cedar decision, and the honest verdict is
`NOT_EVALUATED`. Emitting nothing would let a reader infer "policy allowed
it" from "no policy span", which is the exact conflation the workshop exists
to prevent. So the span is emitted for every turn, including that one.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from services import evidence_spans as ev
from services.governed_turn_receipt import _record_policy_span


@pytest.fixture
def recorded_spans(monkeypatch):
    """Isolated SDK provider whose finished spans can be inspected."""
    sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
    export = pytest.importorskip("opentelemetry.sdk.trace.export")
    in_memory = pytest.importorskip(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter"
    )

    provider = sdk_trace.TracerProvider()
    exporter = in_memory.InMemorySpanExporter()
    provider.add_span_processor(export.SimpleSpanProcessor(exporter))
    monkeypatch.setattr(ev, "_tracer", lambda: provider.get_tracer("test"))
    return exporter


def _events(decision: Any, source: str = "governed_receipts") -> List[Dict[str, Any]]:
    return [{"decision": decision, "source": source, "tool": "give_store_credit"}]


# ---------------------------------------------------------------------------
# Governed decisions
# ---------------------------------------------------------------------------


def test_allow_is_recorded_with_the_service_verdict(recorded_spans):
    _record_policy_span(_events("ALLOW"), turn_id="turn-1", principal_sub="sub-a")

    span = recorded_spans.get_finished_spans()[0]
    assert span.name == ev.SPAN_POLICY
    assert span.attributes[ev.ATTR_POLICY_VERDICT] == "ALLOW"
    assert span.attributes[ev.ATTR_TURN_ID] == "turn-1"
    assert span.attributes[ev.ATTR_PRINCIPAL_SUB] == "sub-a"


def test_deny_is_recorded_and_attributed_to_the_gateway(recorded_spans):
    """A DENY is the authoritative artifact: no execution row should exist."""
    _record_policy_span(_events("DENY"), turn_id="turn-2", principal_sub="sub-a")

    span = recorded_spans.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_POLICY_VERDICT] == "DENY"
    assert span.attributes[ev.ATTR_CALLER] == "gateway"


# ---------------------------------------------------------------------------
# Absence — the case that must not be silent
# ---------------------------------------------------------------------------


def test_not_evaluated_is_emitted_rather_than_skipped(recorded_spans):
    """"No policy ran" must be stated, not inferred from a missing span."""
    _record_policy_span(
        _events("NOT_EVALUATED", source="absence"),
        turn_id="turn-3",
        principal_sub=None,
    )

    spans = recorded_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes[ev.ATTR_POLICY_VERDICT] == "NOT_EVALUATED"
    # An unevaluated turn is not a Gateway turn.
    assert spans[0].attributes[ev.ATTR_CALLER] == "in-process"


def test_anonymous_turn_omits_the_principal(recorded_spans):
    _record_policy_span(
        _events("NOT_EVALUATED", source="absence"),
        turn_id="turn-4",
        principal_sub=None,
    )

    span = recorded_spans.get_finished_spans()[0]
    assert ev.ATTR_PRINCIPAL_SUB not in span.attributes


def test_policy_mode_is_absent_rather_than_guessed(recorded_spans):
    """Gateway mode is engine config, not turn data. A guess would mislead."""
    _record_policy_span(_events("ALLOW"), turn_id="turn-5", principal_sub="sub-a")

    span = recorded_spans.get_finished_spans()[0]
    assert ev.ATTR_POLICY_MODE not in span.attributes


def test_empty_event_list_still_emits_a_span_without_a_verdict(recorded_spans):
    """Defensive: a caller with no events gets a locatable span, not a claim."""
    _record_policy_span([], turn_id="turn-6", principal_sub="sub-a")

    span = recorded_spans.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_TURN_ID] == "turn-6"
    assert ev.ATTR_POLICY_VERDICT not in span.attributes


def test_first_recorded_decision_wins_over_later_events(recorded_spans):
    """Receipt rows are ordered; the turn's decision is the first one."""
    events = [
        {"decision": None, "source": "governed_receipts"},
        {"decision": "DENY", "source": "governed_receipts"},
        {"decision": "ALLOW", "source": "governed_receipts"},
    ]

    _record_policy_span(events, turn_id="turn-7", principal_sub="sub-a")

    span = recorded_spans.get_finished_spans()[0]
    assert span.attributes[ev.ATTR_POLICY_VERDICT] == "DENY"


# ---------------------------------------------------------------------------
# Never break evidence collection
# ---------------------------------------------------------------------------


def test_a_tracing_failure_does_not_propagate(monkeypatch):
    """The receipt insert is the durable artifact; the span is a locator."""
    def _boom(**_kwargs):
        raise RuntimeError("tracer exploded")

    monkeypatch.setattr(ev, "policy_span", _boom)

    # Must not raise.
    _record_policy_span(_events("ALLOW"), turn_id="turn-8", principal_sub="sub-a")


async def _persist(db, **kwargs):
    from services.governed_turn_receipt import persist_turn_receipt

    return await persist_turn_receipt(
        db,
        turn_id=kwargs.get("turn_id", "turn-x"),
        session_id="sess-1",
        principal_sub=kwargs.get("principal_sub"),
        rail="in-process",
        terminal_status="completed",
        latency_ms=12,
    )


class _PartialDb:
    """Answers the policy read, then fails like a cluster missing a table."""

    def __init__(self, policy_rows):
        self._policy_rows = policy_rows
        self.queries: List[str] = []

    async def fetch_all(self, query, *params):
        self.queries.append(query)
        if "governed_receipts" in query:
            return list(self._policy_rows)
        raise RuntimeError('relation "pellier.retrieval_receipts" does not exist')

    async def fetch_one(self, query, *params):
        self.queries.append(query)
        raise RuntimeError('relation "pellier.retrieval_receipts" does not exist')

    async def execute_query(self, query, *params):  # pragma: no cover
        raise AssertionError("insert should not be reached in this test")


@pytest.mark.asyncio
async def test_policy_leg_survives_a_missing_retrieval_table(recorded_spans):
    """Regression: the policy span used to be lost to an unrelated failure.

    It sat after the retrieval and citation reads, so on a cluster without
    `pellier.retrieval_receipts` the whole block aborted first and the turn
    reported no policy evidence at all — which reads as "policy was never
    resolved" rather than "an unrelated table is missing". Found live.
    """
    db = _PartialDb([{"decision": "ALLOW", "tool": "search_products"}])

    result = await _persist(db, turn_id="turn-partial", principal_sub="sub-a")

    # The receipt itself legitimately fails on this cluster...
    assert result is None
    # ...but the policy evidence was still emitted.
    spans = recorded_spans.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes[ev.ATTR_TURN_ID] == "turn-partial"
    assert spans[0].attributes[ev.ATTR_POLICY_VERDICT] == "ALLOW"


def test_no_payload_reaches_the_policy_span(recorded_spans):
    """Tool names and reasons are ledger data, not span data."""
    events = [
        {
            "decision": "DENY",
            "tool": "give_store_credit",
            "reason": "customer 1 did not order product 1",
            "policy_name": "deny-cross-customer-returns",
        }
    ]

    _record_policy_span(events, turn_id="turn-9", principal_sub="sub-a")

    span = recorded_spans.get_finished_spans()[0]
    serialized = " ".join(f"{k}={v}" for k, v in span.attributes.items())
    assert "did not order" not in serialized
    assert "give_store_credit" not in serialized
