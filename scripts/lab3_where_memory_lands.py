#!/usr/bin/env python3
"""Lab 3, Go deeper: where a live turn's preference lands, beside the namespace the agent reads.

The agent reads a shopper's preferences from one namespace,
``/pellier/preferences/<customer id>/`` (``AgentCoreMemory.get_semantic_memories``).
Provisioning writes Theo's first conversation with the actor ``CUST-THEO``, so the
record extracted from it lands there. A live turn is written with its session
namespace as the actor (``append_session_turns``, actor
``user-<sub>-session-<session id>``), so a preference stated in a live turn is
extracted under ``/pellier/preferences/user-<sub>-session-<session id>/``, which the
agent never reads.

This prints both for Theo, side by side: the customer namespace and its records,
then every session actor of his and the records extracted under each. Extraction
is asynchronous; in our runs a stated preference became readable after about two
to two and a half minutes. When Theo's newest turn is younger than that and nothing
has been extracted from it yet, the command waits for it under a progress bar, up to
four minutes after the turn, then prints again. It only reads.

    uv run scripts/lab3_where_memory_lands.py
"""

from __future__ import annotations

import base64
import json
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import workshop_check as check  # noqa: E402  (sibling module)
from wait_progress import clock, waiting  # noqa: E402  (sibling module)

BACKEND = check.REPO / "pellier" / "backend"
DEPLOY = SCRIPTS / "deploy"

THEO, USERNAME = "CUST-THEO", "theo"
DELAY = "about two to two and a half minutes in our runs (116.8 s, 138.0 s and 148.8 s)"
EXTRACTION_TYPICAL_SECONDS = 150
# A turn older than this with nothing extracted stated no preference; waiting longer finds none.
EXTRACTION_LIMIT_SECONDS = 240
POLL_SECONDS = 10


def namespace(actor: str) -> str:
    """The USER_PREFERENCE namespace AgentCore Memory extracts an actor's records into."""
    return f"/pellier/preferences/{actor}/"


def token_subject(token: str) -> str:
    """The ``sub`` claim of a Cognito access token, read without verifying it."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return str(json.loads(base64.urlsafe_b64decode(payload))["sub"])


def _pages(call: Callable[..., Dict[str, Any]], key: str, **params: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        page = call(**params, **({"nextToken": token} if token else {}))
        items += page.get(key, [])
        token = page.get("nextToken")
        if not token:
            return items


def session_actors(client: Any, memory_id: str, sub: str) -> List[str]:
    """Every actor a live turn of this Cognito subject wrote under, oldest name first."""
    prefix = f"user-{sub}-session-"
    actors = _pages(client.list_actors, "actorSummaries", memoryId=memory_id)
    return sorted(a["actorId"] for a in actors if str(a.get("actorId", "")).startswith(prefix))


def _preference(text: str) -> str:
    try:
        return str(json.loads(text).get("preference") or text)
    except (ValueError, AttributeError):
        return text


def records(client: Any, memory_id: str, actor: str) -> List[Tuple[str, str]]:
    """``(record id, preference)`` for every record extracted under the actor's namespace."""
    found = _pages(client.list_memory_records, "memoryRecordSummaries",
                   memoryId=memory_id, namespace=namespace(actor))
    return [(str(r.get("memoryRecordId")), _preference((r.get("content") or {}).get("text", "")))
            for r in found]


def turn_age(client: Any, memory_id: str, actor: str, now: datetime) -> Optional[float]:
    """Seconds since the actor's newest event, or ``None`` when it has none.

    A live turn writes its events with the session namespace as both actor and session.
    """
    events = _pages(client.list_events, "events", memoryId=memory_id, actorId=actor,
                    sessionId=actor, includePayloads=False)
    stamps = [event["eventTimestamp"] for event in events if event.get("eventTimestamp")]
    return (now - max(stamps)).total_seconds() if stamps else None


def extracting(client: Any, memory_id: str, sub: str,
               now: Optional[datetime] = None) -> List[Tuple[str, float]]:
    """Theo's session actors with no record yet, from a turn recent enough to still yield one."""
    now = now or datetime.now(timezone.utc)
    pending = []
    for actor in session_actors(client, memory_id, sub):
        if records(client, memory_id, actor):
            continue
        age = turn_age(client, memory_id, actor, now)
        if age is not None and age < EXTRACTION_LIMIT_SECONDS:
            pending.append((actor, age))
    return pending


def wait_for_extraction(client: Any, memory_id: str, pending: List[Tuple[str, float]],
                        sleep: Callable[[float], None] = time.sleep,
                        now: Callable[[], float] = time.monotonic) -> bool:
    """Poll the pending actors until one holds a record; ``False`` once none still can."""
    youngest = min(age for _, age in pending)
    started = now()
    deadline = started + EXTRACTION_LIMIT_SECONDS - youngest
    with waiting("Waiting for AgentCore Memory to extract Theo's newest turn",
                 typical=max(POLL_SECONDS, EXTRACTION_TYPICAL_SECONDS - youngest),
                 limit=EXTRACTION_LIMIT_SECONDS - youngest, now=now):
        while True:
            if any(records(client, memory_id, actor) for actor, _ in pending):
                return True
            if now() >= deadline:
                return False
            sleep(min(POLL_SECONDS, max(0.0, deadline - now())))


def _block(actor: str, writer: str, found: List[Tuple[str, str]]) -> List[str]:
    lines = [namespace(actor), f"  written by {writer}"]
    lines += [f"  {record_id}  {check.short(preference, 70)}" for record_id, preference in found]
    return lines + ([] if found else ["  no record yet"])


def report(client: Any, memory_id: str, sub: str) -> List[str]:
    """The customer's namespace and its records, then each session actor that holds one.

    Every live turn leaves a session actor, most with nothing extracted, so the empty
    ones are counted on one line rather than listed.
    """
    lines = _block(THEO, "provisioning, actor CUST-THEO; the agent reads this one",
                   records(client, memory_id, THEO))
    empty = 0
    for actor in session_actors(client, memory_id, sub):
        found = records(client, memory_id, actor)
        if found:
            lines += _block(actor, "a live turn, actor = its session; the agent never reads "
                                   "this one", found)
        else:
            empty += 1
    if empty:
        lines.append(f"{empty} more session actor(s) of Theo's hold no record yet")
    return lines


def _connect() -> Tuple[Any, str, str]:
    """A bedrock-agentcore client, the Memory id, and Theo's Cognito subject."""
    for path in (DEPLOY, BACKEND):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from gateway_client import _load_env, _token_from_cognito

    _load_env()
    import boto3
    from config import settings
    from services.memory_showcase import AWS_CONFIG

    memory_id = settings.AGENTCORE_MEMORY_ID
    if not memory_id:
        raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
    client = boto3.client("bedrock-agentcore", region_name=settings.aws_region_resolved,
                          config=AWS_CONFIG)
    return client, memory_id, token_subject(_token_from_cognito(USERNAME))


def main(argv: Optional[Sequence[str]] = None) -> int:
    del argv
    print("Lab 3, Go deeper: where Theo's preferences land, beside where the agent reads them")
    try:
        client, memory_id, sub = _connect()
        pending = extracting(client, memory_id, sub)
        if pending:
            print(f"Theo's newest turn is {clock(min(age for _, age in pending))} old and "
                  "nothing is extracted from it yet. Waiting for it; Ctrl-C stops the wait.")
            try:
                if not wait_for_extraction(client, memory_id, pending):
                    print("Nothing was extracted from it. A turn that states no preference "
                          "leaves no record to extract.")
            except KeyboardInterrupt:
                print("Stopped waiting; here is what has landed so far.")
        lines = report(client, memory_id, sub)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - say why it could not look
        print(f"Could not read AgentCore Memory here: {type(exc).__name__}: {str(exc)[:200]}")
        print("Run this on the workshop box, where pellier/backend/.env names the Memory.")
        return 1
    print(f"AgentCore Memory {memory_id}")
    print("\n".join(lines))
    print("A preference stated in a live turn lands under that turn's session actor, not under")
    print(f"CUST-THEO, and extraction took {DELAY}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
