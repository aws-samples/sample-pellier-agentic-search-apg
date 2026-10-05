#!/usr/bin/env python3
"""Seed scenario conversations and prove all four managed Memory strategies.

Theo's first conversation is one of them: he tells Pellier his taste
(ceramics, stoneware, slow craft) at provisioning, so Lab 3 starts with the
user-preference record AgentCore extracted from it. The seed waits, within its
time budget, for that record and reports its id beside the source event ids.
``scripts/showcase_agentcore_memory.py provisioned --persona theo`` prints the
same pair in the lab.
"""

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

# The session every provisioning conversation is written in.
SEED_SESSION = "prefseed"
# The actor whose extracted preferences Lab 3 shows, and how long the seed
# waits for them after writing his conversation.
LAB3_ACTOR = "CUST-THEO"
PREFERENCE_WAIT_SECONDS = 300


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
            "I'm building a home slowly, with hand-thrown ceramics, stoneware and linen throws.",
            "I'll focus on slow-craft home pieces, stoneware and natural textiles.",
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
                    sessionId=SEED_SESSION,
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

    deadline = time.monotonic() + min(PREFERENCE_WAIT_SECONDS, timeout)
    theo = seeded_memory(control, data, memory_id, LAB3_ACTOR)
    while not theo["records"] and time.monotonic() < deadline:
        time.sleep(15)
        theo = seeded_memory(control, data, memory_id, LAB3_ACTOR)

    return {
        "status": "ready",
        "memory_id": memory_id,
        # Not a gate: extraction is asynchronous and Lab 3 starts later. The
        # lab's command reads the same pair again.
        "lab3_theo": {
            "source_event_ids": [event["eventId"] for event in theo["events"]],
            "preference_record_ids": [record["memoryRecordId"] for record in theo["records"]],
        },
        "resource_status": memory.get("status"),
        "strategies": [item["type"] for item in acceptance["strategies"].values()],
        "acceptance": acceptance,
        "events_created": created,
        "events_already_present": duplicates,
        "actors": sorted(SEED_TURNS),
    }


def seeded_memory(control: Any, data: Any, memory_id: str, actor: str) -> dict[str, Any]:
    """One actor's provisioning conversation and the preferences extracted from it.

    Returns the source events (actor ``actor``, session ``prefseed``) and the
    user-preference records in ``/pellier/preferences/{actor}/``, each listed
    by the service. Nothing here writes.
    """
    from services.memory_contract import STRATEGIES, namespace, record_matches

    _type, name, _union, _template = STRATEGIES["preferences"]
    resource = control.get_memory(memoryId=memory_id)["memory"]
    strategy = next((s for s in resource.get("strategies", []) if s.get("name") == name), None)
    events: list[dict[str, Any]] = []
    for page in data.get_paginator("list_events").paginate(
        memoryId=memory_id, actorId=actor, sessionId=SEED_SESSION, includePayloads=True,
    ):
        events.extend(page.get("events", []))
    records: list[dict[str, Any]] = []
    path = namespace("preferences", actor, SEED_SESSION)
    if strategy and strategy.get("strategyId"):
        for page in data.get_paginator("list_memory_records").paginate(
            memoryId=memory_id, namespace=path, memoryStrategyId=strategy["strategyId"],
        ):
            records.extend(r for r in page.get("memoryRecordSummaries", [])
                           if record_matches(r, strategy["strategyId"], path))
    return {"actor": actor, "session": SEED_SESSION, "namespace": path,
            "strategy": name, "strategy_id": (strategy or {}).get("strategyId"),
            "events": events, "records": records}


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
