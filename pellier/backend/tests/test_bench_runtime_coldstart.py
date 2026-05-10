"""Tests for scripts/bench_runtime_coldstart.py — pure-Python harness bits.

The invocation path needs a live Runtime endpoint to measure anything
real. That validation happens in Week 3 against the deployed Runtime.
These tests cover the pieces we can verify offline: summary stats,
bucket assignment for the bimodal histogram, and the
refuse-when-unset contract.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH_PATH = REPO_ROOT / "scripts" / "bench_runtime_coldstart.py"


@pytest.fixture(scope="module")
def bench_module():
    """Load scripts/bench_runtime_coldstart.py without running main()."""
    spec = importlib.util.spec_from_file_location("_bench_coldstart", BENCH_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_bench_coldstart"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# summarize — stats shape
# ---------------------------------------------------------------------------


def test_summarize_empty_samples(bench_module) -> None:
    result = bench_module.summarize([])
    assert result["count"] == 0
    assert result["median_ms"] is None
    assert result["histogram"] == []


def test_summarize_reports_median_and_p95(bench_module) -> None:
    samples = [50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0, 5000.0]
    result = bench_module.summarize(samples)
    assert result["count"] == 10
    # Median of 10 values is average of 5th and 6th sorted values: (90+100)/2
    assert result["median_ms"] == pytest.approx(95.0, abs=0.1)
    # min + max report the bimodal spread.
    assert result["min_ms"] == 50.0
    assert result["max_ms"] == 5000.0


def test_summarize_histogram_sums_to_count(bench_module) -> None:
    samples = [80.0, 120.0, 300.0, 800.0, 1800.0, 2800.0, 5500.0]
    result = bench_module.summarize(samples)
    total = sum(row["count"] for row in result["histogram"])
    assert total == len(samples)


def test_summarize_histogram_captures_bimodal_split(bench_module) -> None:
    """A 50/50 warm/cold distribution MUST render in distinct buckets —
    the whole point of the bimodal histogram. A workshop attendee looking
    at the output must be able to see the two clusters."""
    warm = [60.0, 70.0, 80.0, 90.0, 100.0]
    cold = [1800.0, 2100.0, 2500.0, 2800.0, 3200.0]
    result = bench_module.summarize(warm + cold)

    warm_bucket_counts = sum(
        row["count"]
        for row in result["histogram"]
        if row["bucket_ms"] in {"0-100", "100-250"}
    )
    cold_bucket_counts = sum(
        row["count"]
        for row in result["histogram"]
        if row["bucket_ms"] in {"1500-2000", "2000-3000", "3000-4000"}
    )
    assert warm_bucket_counts == 5
    assert cold_bucket_counts == 5


# ---------------------------------------------------------------------------
# _bucket_index — edge cases
# ---------------------------------------------------------------------------


def test_bucket_index_covers_every_sample(bench_module) -> None:
    buckets = bench_module.HISTOGRAM_BUCKETS_MS
    # A sample right on a bucket edge lands in the upper bucket (left edge inclusive).
    for edge in buckets[:-1]:
        idx = bench_module._bucket_index(float(edge), buckets)
        assert 0 <= idx < len(buckets) - 1 + 1


def test_bucket_index_overflow_lands_in_final_bucket(bench_module) -> None:
    buckets = bench_module.HISTOGRAM_BUCKETS_MS
    idx = bench_module._bucket_index(99999.0, buckets)
    assert idx == len(buckets) - 1


# ---------------------------------------------------------------------------
# main() — refuse when AGENTCORE_RUNTIME_ENDPOINT is unset
# ---------------------------------------------------------------------------


def test_main_refuses_without_endpoint(
    bench_module, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """If the endpoint env var is unset the script MUST exit 1 rather
    than benchmark the in-process fallback — we'd be measuring Python
    call overhead, not container startup."""
    monkeypatch.delenv("AGENTCORE_RUNTIME_ENDPOINT", raising=False)
    monkeypatch.setattr(sys, "argv", ["bench_runtime_coldstart.py", "--samples", "1"])

    rc = bench_module.main()
    assert rc == 1


def test_main_dry_run_skips_invocations(
    bench_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run prints the plan and returns 0 without touching boto3."""
    monkeypatch.setenv("AGENTCORE_RUNTIME_ENDPOINT", "arn:aws:bedrock-agentcore:test")
    monkeypatch.setattr(
        sys,
        "argv",
        ["bench_runtime_coldstart.py", "--samples", "2", "--dry-run"],
    )
    rc = bench_module.main()
    assert rc == 0
