#!/usr/bin/env python3
"""Confirm, after handout, the Memory records the appendix's deep dive shows.

Provisioning proves the strategies a shopper turn and Lab 3 read
(REQUIRED_STRATEGIES). Facts, the session summary and the episode form later; an
episode can take many minutes after its conversation, longer than a box should take
to provision. This reads, and never writes, Theo's provisioning conversation until
every strategy holds a record, then writes the result where the facilitator's
readiness check reports it:

    python3.14 scripts/deploy/check_memory_deep_dive.py --memory-id ID --region us-east-1 \\
        --status-file /var/lib/pellier/memory-deep-dive.json

Exit 0 when every strategy holds a record, 1 when the wait ran out or Memory refused.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "pellier" / "backend"), str(ROOT / "scripts" / "deploy"),
                str(ROOT / "scripts")]

from services.memory_contract import STRATEGIES  # noqa: E402

ACTOR = "CUST-THEO"
POLL_SECONDS = 30
DEFAULT_TIMEOUT_SECONDS = 3600


def missing_strategies(found: dict[str, Any]) -> list[str]:
    """The strategies with no record yet in the actor's provisioning conversation."""
    return [kind for kind in STRATEGIES if not found["strategies"][kind]["records"]]


def wait_for_deep_dive(
    read: Callable[[], dict[str, Any]], *, timeout: float, poll: float = POLL_SECONDS,
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Read until every strategy holds a record or ``timeout`` seconds pass."""
    started = clock()
    while True:
        missing = missing_strategies(read())
        elapsed = clock() - started
        if not missing or elapsed >= timeout:
            return {"status": "ready" if not missing else "incomplete", "missing": missing,
                    "elapsedSeconds": round(elapsed, 1)}
        sleep(poll)


def write_status(path: Path, payload: dict[str, Any]) -> None:
    """Replace the status file in one step, readable by the participant's tools."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(json.dumps(payload, indent=2) + "\n")
    os.chmod(partial, 0o644)
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--memory-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
                        help="Seconds to wait for every strategy's first record")
    args = parser.parse_args()

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    from seed_agentcore_memory import AWS_CONFIG
    from showcase_agentcore_memory import strategy_records

    control = boto3.client("bedrock-agentcore-control", region_name=args.region, config=AWS_CONFIG)
    data = boto3.client("bedrock-agentcore", region_name=args.region, config=AWS_CONFIG)
    base = {"memoryId": args.memory_id, "actor": ACTOR}
    write_status(args.status_file, {**base, "status": "checking",
                                    "startedAt": datetime.now(timezone.utc).isoformat()})
    try:
        result = wait_for_deep_dive(
            lambda: strategy_records(control, data, args.memory_id, ACTOR), timeout=args.timeout)
    except (BotoCoreError, ClientError) as exc:
        result = {"status": "error", "error": str(exc)}
    payload = {**base, **result, "checkedAt": datetime.now(timezone.utc).isoformat()}
    write_status(args.status_file, payload)
    print(json.dumps(payload))
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
