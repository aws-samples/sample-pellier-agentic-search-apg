#!/usr/bin/env python3
"""Show Theo's live indigo message and any matching preference in the namespace Runtime reads.

Run this optional, read-only demonstration on the workshop box after Task 3B.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402

THEO = "CUST-THEO"
PREFERENCES = f"/pellier/preferences/{THEO}/"


def _pages(call: Callable[..., Dict[str, Any]], key: str, **params: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        page = call(**params, **({"nextToken": token} if token else {}))
        items += page.get(key, [])
        token = page.get("nextToken")
        if not token:
            return items


def report(client: Any, memory_id: str) -> List[str]:
    """Show the event and record separately. Either can be absent on an early read."""
    lines = [f"Theo's preference records: {PREFERENCES}"]
    sessions = _pages(client.list_sessions, "sessionSummaries", memoryId=memory_id, actorId=THEO)
    messages = []
    for session in sessions:
        session_id = session["sessionId"]
        if not session_id.startswith("user-"):
            continue
        events = _pages(client.list_events, "events", memoryId=memory_id, actorId=THEO,
                        sessionId=session_id, includePayloads=True)
        for event in events:
            for item in event.get("payload", []):
                message = item.get("conversational", {})
                text = message.get("content", {}).get("text", "")
                if message.get("role") == "USER" and "indigo" in text.casefold():
                    messages.append(f"Shopper message {event['eventId']} in {session_id}: {check.short(text, 90)}")
    lines.extend(messages or ["No matching shopper message yet. Send the indigo message as Theo in Ask Pellier."])

    matches = []
    records = _pages(client.list_memory_records, "memoryRecordSummaries",
                     memoryId=memory_id, namespace=PREFERENCES)
    for record in records:
        if PREFERENCES not in record.get("namespaces", []) or not record.get("memoryRecordId"):
            continue
        try:
            content = json.loads(record.get("content", {}).get("text", ""))
        except (TypeError, ValueError):
            continue
        preference = content.get("preference") if isinstance(content, dict) else None
        if isinstance(preference, str) and "indigo" in preference.casefold():
            matches.append(f"Preference record {record['memoryRecordId']}: {check.short(preference, 90)}")
    lines.extend(matches or ["No matching preference record yet. Memory extracts preferences in the background."])
    return lines


def _connect() -> tuple[Any, str]:
    for path in (SCRIPTS / "deploy", check.REPO / "pellier" / "backend"):
        sys.path.insert(0, str(path))
    from gateway_client import _load_env
    _load_env()

    import boto3
    from config import settings
    from services.memory_showcase import AWS_CONFIG

    if not settings.AGENTCORE_MEMORY_ID:
        raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
    client = boto3.client("bedrock-agentcore", region_name=settings.aws_region_resolved, config=AWS_CONFIG)
    return client, settings.AGENTCORE_MEMORY_ID


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        lines = report(*_connect())
    except (Exception, SystemExit) as exc:
        print(check.wrapped("", f"Could not read AgentCore Memory on this box: {exc}"))
        return 1
    for line in lines:
        print(check.wrapped("", line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
