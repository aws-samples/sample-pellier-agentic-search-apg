#!/usr/bin/env python3
"""Seed scenario conversations and prove all four managed Memory strategies."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from verify_memory_readiness import verify_memory_readiness


SEED_TURNS = {
    "CUST-MARCO": [
        (
            "I'm heading to Goa for ten days and want lightweight linen I can layer.",
            "I'll focus on breathable natural fibers in warm neutrals.",
        ),
        (
            "I prefer earthy tones: sand, olive, and terracotta.",
            "Noted: warm muted neutrals in natural fibers.",
        ),
    ],
    "CUST-ANNA": [
        (
            "I'm shopping for a thoughtful handmade gift for my sister.",
            "I'll look for artisan pieces with a personal feel.",
        ),
        (
            "Keep it under $150; special matters more than expensive.",
            "Noted: a considered artisan gift under $150.",
        ),
    ],
    "CUST-THEO": [
        (
            "I'm building a home with hand-thrown ceramics and linen throws.",
            "I'll focus on slow-craft home pieces and natural textiles.",
        ),
        (
            "I'd rather buy one quiet tactile piece I'll keep.",
            "Noted: quality over quantity and muted, tactile objects.",
        ),
    ],
}

AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=60,
)


def _memory(control: Any, memory_id: str) -> dict[str, Any]:
    return control.get_memory(memoryId=memory_id)["memory"]


def _wait_for_memory(control: Any, memory_id: str, timeout: int = 300) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        memory = _memory(control, memory_id)
        status = memory.get("status")
        if status == "ACTIVE":
            return memory
        if status == "FAILED":
            raise RuntimeError(
                f"AgentCore Memory failed: {memory.get('failureReason', 'unknown')}"
            )
        time.sleep(5)
    raise RuntimeError(f"AgentCore Memory {memory_id} did not become ACTIVE")


def seed(memory_id: str, region: str, *, timeout: int = 1200) -> dict[str, Any]:
    control = boto3.client(
        "bedrock-agentcore-control",
        region_name=region,
        config=AWS_CONFIG,
    )
    data = boto3.client(
        "bedrock-agentcore",
        region_name=region,
        config=AWS_CONFIG,
    )
    memory = _wait_for_memory(control, memory_id)
    acceptance = verify_memory_readiness(control, data, memory_id, timeout=timeout)

    created = 0
    duplicates = 0
    for actor_id, pairs in SEED_TURNS.items():
        for index, (user_message, assistant_message) in enumerate(pairs):
            try:
                data.create_event(
                    memoryId=memory_id,
                    actorId=actor_id,
                    sessionId="prefseed",
                    eventTimestamp=datetime.now(timezone.utc),
                    clientToken=f"pellier-prefseed-{actor_id}-{index}",
                    payload=[
                        {
                            "conversational": {
                                "content": {"text": user_message},
                                "role": "USER",
                            }
                        },
                        {
                            "conversational": {
                                "content": {"text": assistant_message},
                                "role": "ASSISTANT",
                            }
                        },
                    ],
                )
                created += 1
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code in {"ConflictException", "IdempotentParameterMismatch"}:
                    duplicates += 1
                    continue
                raise

    return {
        "status": "ready",
        "memory_id": memory_id,
        "resource_status": memory.get("status"),
        "strategies": [item["type"] for item in acceptance["strategies"].values()],
        "acceptance": acceptance,
        "events_created": created,
        "events_already_present": duplicates,
        "actors": sorted(SEED_TURNS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--timeout", type=int, default=1200, help="Maximum seconds for managed extraction and retrieval")
    args = parser.parse_args()
    try:
        print(json.dumps(seed(args.memory_id, args.region, timeout=args.timeout)))
        return 0
    except (ClientError, RuntimeError) as exc:
        print(f"Memory seed failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
