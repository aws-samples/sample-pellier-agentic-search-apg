"""Tests for the per-turn performance log + aggregates."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_buffer():
    from services import performance_log
    with performance_log._lock:
        performance_log._turns.clear()
    yield


def test_empty_buffer_returns_empty_marker():
    """No turns yet → aggregates reports empty:true so the UI can
    show the illustrative placeholder honestly."""
    from services.performance_log import get_aggregates
    agg = get_aggregates()
    assert agg["empty"] is True
    assert agg["turn_count"] == 0
    assert agg["layers_p50"] == {}


def test_record_and_aggregate_single_turn():
    """One turn → p50 and p95 both reduce to the single value."""
    from services.performance_log import record_turn, get_aggregates
    record_turn(
        session_id="s1",
        layers={"orchestrator": 120.0, "tools": 450.0, "stream": 300.0},
        ttft_ms=250,
        total_ms=900,
        tool_trace=[{"tool": "find_pieces", "ms": 300, "results": 5}],
        pattern="dispatcher",
    )
    agg = get_aggregates()
    assert agg["empty"] is False
    assert agg["turn_count"] == 1
    assert agg["total_p50"] == 900.0
    assert agg["total_p95"] == 900.0
    assert agg["layers_p50"]["tools"] == 450.0
    assert agg["tools_p50"]["find_pieces"] == 300.0


def test_aggregate_multiple_turns():
    """Several turns → p50 picks the median, p95 trails the top."""
    from services.performance_log import record_turn, get_aggregates
    for i, total in enumerate([500, 800, 1000, 1200, 1500]):
        record_turn(
            session_id="s1",
            layers={"orchestrator": total * 0.4, "tools": total * 0.3, "stream": total * 0.3},
            ttft_ms=total // 3,
            total_ms=total,
            tool_trace=[],
            pattern="graph" if i % 2 == 0 else "dispatcher",
        )
    agg = get_aggregates()
    assert agg["turn_count"] == 5
    # nearest-rank p50 on 5 sorted values picks index 2 → 1000.
    assert agg["total_p50"] == 1000.0
    # p95 on 5 values picks index min(4, round(0.95 * 4)) = 4 → 1500.
    assert agg["total_p95"] == 1500.0


def test_histogram_shape_is_twenty_buckets():
    """Histogram always reports 20 buckets so the UI layout stays
    stable regardless of observed totals."""
    from services.performance_log import record_turn, get_aggregates
    record_turn("s1", {"orchestrator": 10}, ttft_ms=10, total_ms=350)
    agg = get_aggregates()
    assert len(agg["histogram"]) == 20
    assert sum(agg["histogram"]) == 1


def test_buffer_bounded_by_maxlen():
    """The deque caps at _MAX_TURNS; very old entries drop off."""
    from services import performance_log
    # Fake a small max via monkey-patching the deque.
    original = performance_log._turns
    performance_log._turns.clear()
    for i in range(performance_log._MAX_TURNS + 10):
        performance_log.record_turn(
            session_id="s",
            layers={"orchestrator": float(i)},
            ttft_ms=i,
            total_ms=i,
        )
    agg = performance_log.get_aggregates()
    assert agg["turn_count"] == performance_log._MAX_TURNS
    assert performance_log._turns is original  # same deque, not replaced
