"""Prove all four strategies with an isolated conversation in the real service.

Only CreateEvent writes are used. Long-term records must be extracted by AWS,
listed, read by ID, and retrieved in the configured namespace before readiness.
The readiness actor is separate from every participant and every earlier run.
"""
from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pellier" / "backend"))
from services.memory_contract import STRATEGIES, configuration_errors, namespace, record_matches
from services.memory_records import record_view


def verify_memory_readiness(
    control: Any, data: Any, memory_id: str, *, timeout: int = 1200,
) -> dict[str, Any]:
    """Fail closed on wrong configuration, missing extraction, or failed recall."""
    started = time.monotonic()
    deadline = started + timeout
    while True:
        resource = control.get_memory(memoryId=memory_id)["memory"]
        errors = configuration_errors(resource)
        if not errors:
            break
        if resource.get("status") == "FAILED" or any(s.get("status") == "FAILED" for s in resource.get("strategies", [])):
            raise RuntimeError("Memory configuration failed: " + "; ".join(errors))
        if time.monotonic() >= deadline:
            raise RuntimeError("Memory configuration did not become ready: " + "; ".join(errors))
        time.sleep(10)

    run_id = uuid.uuid4().hex
    actor = "readiness-" + run_id
    session = "learn-" + run_id
    recall_session = "recall-" + run_id
    strategies = {
        kind: next(s for s in resource["strategies"] if s["name"] == spec[1])
        for kind, spec in STRATEGIES.items()
    }
    conversations = [
        [("USER", "I'm furnishing a reading corner in my new apartment this October. I prefer linen, natural materials and muted earth tones. My budget is $200. Today, please record this brief for next time; I am not asking you to buy anything."),
         ("ASSISTANT", "I've recorded your October reading-corner brief: linen, natural materials, muted earth tones and a $200 budget.")],
        [("USER", "Thank you. Recording that brief was the whole task and you have completed it. This conversation is finished."),
         ("ASSISTANT", "You're welcome. Your brief is recorded for the next conversation.")],
    ]
    event_ids = []
    for turns in conversations:
        event = data.create_event(
            memoryId=memory_id, actorId=actor, sessionId=session,
            eventTimestamp=datetime.now(timezone.utc), clientToken=str(uuid.uuid4()),
            payload=[{"conversational": {"role": role, "content": {"text": text}}} for role, text in turns],
        )["event"]
        event_ids.append(event["eventId"])

    def pages(operation: str, key: str, **kwargs: Any) -> list[dict[str, Any]]:
        rows = []
        for page in data.get_paginator(operation).paginate(memoryId=memory_id, **kwargs):
            rows.extend(page.get(key, []))
        return rows

    evidence: dict[str, Any] = {}
    while True:
        # Observe configuration again: a deleted or failed strategy cannot pass
        # because records from an earlier polling attempt were cached locally.
        resource = control.get_memory(memoryId=memory_id)["memory"]
        errors = configuration_errors(resource)
        if errors:
            raise RuntimeError("Memory changed during acceptance: " + "; ".join(errors))
        source_events = pages("list_events", "events", actorId=actor, sessionId=session, includePayloads=True)
        source_ids = {event.get("eventId") for event in source_events}
        evidence = {}
        for kind, strategy in strategies.items():
            path = namespace(kind, actor, session)
            listed = pages("list_memory_records", "memoryRecordSummaries",
                           namespace=path, memoryStrategyId=strategy["strategyId"])
            records = []
            for item in listed:
                if not record_matches(item, strategy["strategyId"], path):
                    continue
                record = data.get_memory_record(memoryId=memory_id, memoryRecordId=item["memoryRecordId"])["memoryRecord"]
                if record.get("memoryRecordId") == item["memoryRecordId"] and record_matches(record, strategy["strategyId"], path):
                    view = record_view(record, kind)
                    if kind != "episodic" or view["episode"]:
                        records.append(view)
            if not records:
                continue
            retrieved = pages("retrieve_memory_records", "memoryRecordSummaries", namespace=path,
                              searchCriteria={"searchQuery": "October reading corner linen natural materials budget completed shopping brief", "topK": 10})
            read_ids = {record["id"] for record in records}
            matched = [r["memoryRecordId"] for r in retrieved
                       if record_matches(r, strategy["strategyId"], path) and r["memoryRecordId"] in read_ids]
            if matched:
                evidence[kind] = {
                    "type": strategy["type"], "strategyId": strategy["strategyId"],
                    "namespace": path, "records": records, "retrievedRecordIds": matched,
                }
        if len(evidence) == len(STRATEGIES) and set(event_ids) <= source_ids:
            break
        if time.monotonic() >= deadline:
            missing = [kind for kind in STRATEGIES if kind not in evidence]
            if not set(event_ids) <= source_ids:
                missing.append("source events")
            raise RuntimeError(
                f"Memory extraction/retrieval timed out for {actor}/{session}; missing: {', '.join(missing)}"
            )
        print("Memory extraction pending: " + ", ".join(k for k in STRATEGIES if k not in evidence), file=sys.stderr)
        time.sleep(15)

    if pages("list_events", "events", actorId=actor, sessionId=recall_session):
        raise RuntimeError("Readiness recall session unexpectedly contains chat history")
    # A different fresh actor must not see this run through a namespace prefix.
    other_actor = "readiness-control-" + uuid.uuid4().hex
    for kind in STRATEGIES:
        if pages("retrieve_memory_records", "memoryRecordSummaries",
                 namespace=namespace(kind, other_actor, session),
                 searchCriteria={"searchQuery": "October reading corner linen budget", "topK": 5}):
            raise RuntimeError("Memory namespace isolation check returned foreign records")
    return {
        "status": "ready", "source": "agentcore-service", "memoryId": memory_id,
        "actorId": actor, "sourceSessionId": session, "sourceEventIds": event_ids,
        "recallSessionId": recall_session, "historyEventsLoaded": 0,
        "namespaceIsolation": True, "eventExpiryDuration": resource["eventExpiryDuration"],
        "strategies": evidence, "elapsedSeconds": round(time.monotonic() - started, 2),
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
    }
