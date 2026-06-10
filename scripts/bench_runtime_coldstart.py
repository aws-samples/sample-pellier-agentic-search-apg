#!/usr/bin/env python3
"""bench_runtime_coldstart.py — Measure AgentCore Runtime cold-start latency.

Cold-start for AgentCore Runtime is bimodal: fresh containers take
2-4s, warm containers ~50ms. A representative measurement forces a
cold container on every sample by waiting longer than the warm-idle
window between invocations.

Usage:
    AGENTCORE_RUNTIME_ENDPOINT=arn:... \\
    python scripts/bench_runtime_coldstart.py \\
        --samples 20 \\
        --cooldown-seconds 60 \\
        --output docs/perf-baselines/cold-start-$(date +%Y-%m-%d).json

Hard requirement: ``AGENTCORE_RUNTIME_ENDPOINT`` must be set. Running
against the in-process fallback measures Python function call
overhead, not Runtime cold-start — the script refuses to run without
the endpoint so the output is never silently meaningless.

Output:
    JSON file with per-sample timings + summary stats (median, p95,
    min, max, and histogram buckets for the bimodal distribution).
    Console summary table for quick inspection.

Exit codes:
    0 — benchmark completed, all samples succeeded
    1 — config/environment failure before benchmark started
    2 — some samples failed (partial result still written)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
logger = logging.getLogger("bench_coldstart")


# Histogram buckets (ms). Shaped for the expected bimodal distribution:
# a narrow warm-path cluster (<200ms) vs a wide cold-path cluster
# (1500-4000ms). Edges chosen so the two clusters land in distinct
# buckets even with tail variance.
HISTOGRAM_BUCKETS_MS = [0, 100, 250, 500, 1000, 1500, 2000, 3000, 4000, 6000]


def _invoke_runtime(
    client: Any,
    endpoint: str,
    prompt: str,
    session_id: str,
) -> float:
    """Invoke Runtime, return elapsed wall-clock ms. Raises on error."""
    payload = {
        "prompt": prompt,
        "session_id": session_id,
        "user_id": "bench-coldstart",
    }
    start = time.time()
    client.invoke_agent_runtime(
        agentRuntimeArn=endpoint,
        payload=json.dumps(payload).encode("utf-8"),
        runtimeSessionId=session_id,
    )
    return (time.time() - start) * 1000.0


def _bucket_index(value_ms: float, buckets: List[int]) -> int:
    """Return the bucket index for ``value_ms``.

    Bucket ``i`` covers ``[buckets[i], buckets[i+1])``; values >= the
    last edge land in the final bucket.
    """
    for i in range(len(buckets) - 1):
        if value_ms < buckets[i + 1]:
            return i
    return len(buckets) - 1


def summarize(
    samples: List[float],
    buckets: List[int] = HISTOGRAM_BUCKETS_MS,
) -> Dict[str, Any]:
    """Compute summary stats for a list of sample latencies (ms)."""
    if not samples:
        return {
            "count": 0,
            "median_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
            "histogram": [],
        }
    sorted_samples = sorted(samples)
    p95_index = max(0, int(len(sorted_samples) * 0.95) - 1)
    histogram = [0] * (len(buckets) - 1 + 1)
    for v in samples:
        histogram[_bucket_index(v, buckets)] += 1

    return {
        "count": len(samples),
        "median_ms": round(statistics.median(samples), 1),
        "p95_ms": round(sorted_samples[p95_index], 1),
        "min_ms": round(min(samples), 1),
        "max_ms": round(max(samples), 1),
        "histogram": [
            {
                "bucket_ms": f"{buckets[i]}-{buckets[i + 1]}"
                if i < len(buckets) - 1
                else f">{buckets[-1]}",
                "count": count,
            }
            for i, count in enumerate(histogram)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--samples",
        type=int,
        default=20,
        help="Number of cold-start samples (default: 20)",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=int,
        default=60,
        help="Sleep between samples to force a fresh container (default: 60)",
    )
    parser.add_argument(
        "--prompt",
        default="ping",
        help="Prompt text for each invocation. Short on purpose — this "
        "measures startup not generation. (default: 'ping')",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON report to this path (default: stdout only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the invocations and print the would-be plan",
    )
    args = parser.parse_args()

    endpoint = os.environ.get("AGENTCORE_RUNTIME_ENDPOINT")
    if not endpoint:
        logger.error(
            "AGENTCORE_RUNTIME_ENDPOINT is not set. Cold-start benchmark "
            "needs a real Runtime endpoint — in-process fallback measures "
            "Python call overhead, not container startup. Aborting."
        )
        return 1

    region = os.environ.get("AWS_REGION", "us-east-1")
    plan = {
        "samples": args.samples,
        "cooldown_seconds": args.cooldown_seconds,
        "prompt": args.prompt,
        "endpoint": endpoint,
        "region": region,
    }
    logger.info("Plan: %s", json.dumps(plan))

    if args.dry_run:
        logger.info("--dry-run: skipping invocations")
        return 0

    try:
        import boto3  # noqa: WPS433
    except ImportError:
        logger.error("boto3 is not installed; install requirements first")
        return 1

    client = boto3.client("bedrock-agentcore", region_name=region)

    samples: List[float] = []
    errors: List[Dict[str, Any]] = []
    for i in range(args.samples):
        session_id = f"bench-coldstart-{int(time.time())}-{i}"
        try:
            elapsed_ms = _invoke_runtime(client, endpoint, args.prompt, session_id)
            samples.append(elapsed_ms)
            logger.info(
                "sample %02d/%02d | %7.1f ms",
                i + 1,
                args.samples,
                elapsed_ms,
            )
        except Exception as exc:
            errors.append({"sample_index": i, "error": str(exc)})
            logger.warning(
                "sample %02d/%02d | FAILED: %s",
                i + 1,
                args.samples,
                exc,
            )

        if i < args.samples - 1:
            logger.info("cooldown %ds…", args.cooldown_seconds)
            time.sleep(args.cooldown_seconds)

    summary = summarize(samples)
    report = {
        "plan": plan,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples_ms": [round(s, 1) for s in samples],
        "summary": summary,
        "errors": errors,
    }

    _print_summary(summary, errors)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        logger.info("Wrote %s", args.output)

    if errors:
        return 2
    return 0


def _print_summary(summary: Dict[str, Any], errors: List[Dict[str, Any]]) -> None:
    print()
    print("=" * 60)
    print(f"  Cold-start baseline — n={summary['count']}")
    print("=" * 60)
    print(f"  median : {summary['median_ms']} ms")
    print(f"  p95    : {summary['p95_ms']} ms")
    print(f"  min    : {summary['min_ms']} ms")
    print(f"  max    : {summary['max_ms']} ms")
    print()
    print("  histogram:")
    for row in summary["histogram"]:
        bar = "█" * row["count"]
        print(f"    {row['bucket_ms']:>12}  {row['count']:>3}  {bar}")
    if errors:
        print()
        print(f"  errors : {len(errors)}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
