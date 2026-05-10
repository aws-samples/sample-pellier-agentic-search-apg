"""Phase 2 live smoke — exercises the four storefront scenarios
against the real chat_stream() with Bedrock in the loop.

Scenarios (per the prompt's verification requirements):

  1. Marco signed in → "a linen piece for slow Sundays"
     Expect: one Opus call (search specialist), references his past
     Maren purchase, voice preserved.

  2. Same query, signed out
     Expect: still works, editorial fallback (no persona preamble),
     still one specialist call.

  3. Weird query that doesn't match the classifier's patterns
     Expect: dispatcher falls back to a sensible default (search or
     recommendation), doesn't 500.

  4. Workaround audit: scan the event stream + log line for evidence
     that the deleted workarounds aren't firing.
       - No "[ROUTING DIRECTIVE:" in any event prompt
       - No "Preferring specialist prose" log line
       - No "chat_stream recovered" log line
       - Exactly one "🎯 Dispatcher" log line per turn (confirming the
         dispatcher branch, not the orchestrator branch, fired)

Run with the backend's venv python from the backend root:
    .venv/bin/python scripts/smoke_phase2_dispatcher.py
"""
from __future__ import annotations

import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import Any

# Add the backend root to sys.path (scripts/ isn't a package)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
DIM = "\033[2m"
RESET = "\033[0m"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = OK if ok else FAIL
    print(f"    {mark} {label}" + (f" {DIM}· {detail}{RESET}" if detail else ""))
    return ok


async def _collect_events(
    service,
    message: str,
    pattern: str,
    customer_id: str | None,
) -> dict:
    """Run one chat_stream turn and return the collected events,
    accumulated text, and the chat_stream log line buffer.
    """
    # Capture the chat_stream logger output so we can audit for the
    # deleted log lines ("Preferring specialist prose", etc.).
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    chat_logger = logging.getLogger("services.chat")
    chat_logger.addHandler(handler)
    try:
        events: list[dict] = []
        text_chunks: list[str] = []
        user = {"customer_id": customer_id} if customer_id else None
        async for event in service.chat_stream(
            message=message,
            conversation_history=[],
            session_id=f"smoke-{pattern}-{customer_id or 'anon'}",
            workshop_mode=None,
            guardrails_enabled=False,
            user=user,
            pattern=pattern,
        ):
            events.append(event)
            if event.get("type") == "content_delta":
                text_chunks.append(event.get("delta", ""))
            elif event.get("type") == "content":
                text_chunks.append(event.get("content", ""))
        return {
            "events": events,
            "text": "".join(text_chunks).strip(),
            "log": buf.getvalue(),
        }
    finally:
        chat_logger.removeHandler(handler)


async def main() -> int:
    # Initialize the chat service with a live DB connection so persona
    # LTM reads work. Mirrors the FastAPI startup path.
    from services.database import DatabaseService
    from services.chat import EnhancedChatService

    db = DatabaseService()
    await db.connect()
    service = EnhancedChatService(db_service=db)

    passed = True

    # -----------------------------------------------------------------
    print("\nScenario 1 · Marco signed in · 'a linen piece for slow Sundays'")
    print("─" * 72)
    r1 = await _collect_events(
        service,
        "a linen piece for slow Sundays",
        pattern="dispatcher",
        customer_id="CUST-MARCO",
    )
    passed &= _check("reply text ≥ 80 chars",
                      len(r1["text"]) >= 80,
                      f"{len(r1['text'])} chars")
    passed &= _check("dispatcher log line fired",
                      "🎯 Dispatcher" in r1["log"])
    passed &= _check("persona LTM loaded",
                      "👤 Persona LTM | CUST-MARCO" in r1["log"])
    passed &= _check("no [ROUTING DIRECTIVE:] in any event payload",
                      not any("ROUTING DIRECTIVE" in str(e) for e in r1["events"]))
    passed &= _check("no 'Preferring specialist prose' log line",
                      "Preferring specialist prose" not in r1["log"])
    passed &= _check("no 'chat_stream recovered' log line",
                      "chat_stream recovered" not in r1["log"])

    # -----------------------------------------------------------------
    print("\nScenario 2 · Signed out · 'a linen piece for slow Sundays'")
    print("─" * 72)
    r2 = await _collect_events(
        service,
        "a linen piece for slow Sundays",
        pattern="dispatcher",
        customer_id=None,
    )
    passed &= _check("reply text ≥ 80 chars",
                      len(r2["text"]) >= 80,
                      f"{len(r2['text'])} chars")
    passed &= _check("dispatcher log line fired",
                      "🎯 Dispatcher" in r2["log"])
    passed &= _check("no persona LTM load (anonymous)",
                      "👤 Persona LTM" not in r2["log"])
    passed &= _check("no [ROUTING DIRECTIVE:] injection",
                      not any("ROUTING DIRECTIVE" in str(e) for e in r2["events"]))
    passed &= _check("no specialist-prose promotion",
                      "Preferring specialist prose" not in r2["log"])

    # -----------------------------------------------------------------
    print("\nScenario 3 · Weird query · classifier falls back gracefully")
    print("─" * 72)
    # "hmmm yes xyzzy" matches no keywords — classify_intent returns
    # 'recommendation' as the default. Dispatcher routes accordingly.
    r3 = await _collect_events(
        service,
        "hmmm yes xyzzy",
        pattern="dispatcher",
        customer_id=None,
    )
    passed &= _check("no error event in stream",
                      not any(e.get("type") == "error" for e in r3["events"]))
    passed &= _check("dispatcher log line fired",
                      "🎯 Dispatcher" in r3["log"])
    # Any of the five specialists is a valid fall-back; just not orchestrator
    passed &= _check("no orchestrator log line (dispatcher path, not Pattern I)",
                      "Creating agent orchestrator" not in r3["log"])

    # -----------------------------------------------------------------
    print("\nScenario 4 · Workaround audit (cross-scenario)")
    print("─" * 72)
    all_logs = r1["log"] + r2["log"] + r3["log"]
    all_events_str = str(r1["events"]) + str(r2["events"]) + str(r3["events"])
    passed &= _check(
        "no [ROUTING DIRECTIVE:] across any turn's events",
        "ROUTING DIRECTIVE" not in all_events_str,
    )
    passed &= _check(
        "no 'Preferring specialist prose' across any turn",
        "Preferring specialist prose" not in all_logs,
    )
    passed &= _check(
        "no 'chat_stream recovered' across any turn",
        "chat_stream recovered" not in all_logs,
    )
    passed &= _check(
        "no 'empty-response fallback' across any turn",
        "empty-response fallback" not in all_logs,
    )
    # Exactly three dispatcher log lines (one per scenario)
    dispatcher_count = all_logs.count("🎯 Dispatcher")
    passed &= _check(
        "exactly three '🎯 Dispatcher' log lines (one per turn)",
        dispatcher_count == 3,
        f"count={dispatcher_count}",
    )

    await db.disconnect()

    # -----------------------------------------------------------------
    print()
    if passed:
        print(f"{OK} Phase 2 live smoke passed — dispatcher works, workarounds are gone")
        return 0
    print(f"{FAIL} Phase 2 live smoke had failures — see above")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
