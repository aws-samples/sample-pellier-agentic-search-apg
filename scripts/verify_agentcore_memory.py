#!/usr/bin/env python3
"""Read one AgentCore Memory session from a fresh Python process."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "pellier" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.agentcore_memory import AgentCoreMemory, ManagedMemoryError


async def verify(
    namespace: str,
    expected: list[str],
    *,
    timeout: int = 30,
    customer_id: str | None = None,
    memory_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Poll managed Memory until every expected fragment is read."""
    memory = (
        memory_factory()
        if memory_factory is not None
        else AgentCoreMemory(strict=True)
    )
    deadline = time.monotonic() + timeout
    history: list[dict[str, Any]] = []
    while True:
        history = await memory.get_session_history(namespace, customer_id=customer_id)
        joined = "\n".join(str(turn.get("content", "")) for turn in history)
        if all(fragment in joined for fragment in expected):
            return {
                "source": "agentcore-memory",
                "process": "fresh",
                "namespace": namespace,
                "turn_count": len(history),
                "matched": expected,
            }
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "managed session did not contain every expected fragment "
                f"within {timeout} seconds"
            )
        await asyncio.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--customer-id", help="Mapped customer actor for a signed-in shopper conversation")
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    try:
        result = asyncio.run(
            verify(
                args.namespace,
                args.expect,
                customer_id=args.customer_id,
                timeout=max(1, args.timeout),
            )
        )
        print(json.dumps(result))
        return 0
    except (ManagedMemoryError, RuntimeError) as exc:
        print(f"AgentCore Memory verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
