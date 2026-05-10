"""Guardrails decision log — per-session ring buffer.

Mirrors ``policy_hook``'s recording shape so the Atelier Grounding
page can plot guardrail outcomes alongside Cedar policy decisions with
the same row format.

Populated from two places:

  1. ``routes/chat.py`` / ``services/chat.py`` — when a turn invokes
     ``GuardrailsService.check_input`` or ``check_output``, the result
     is recorded here so the Atelier Guardrails lane shows live status.
  2. ``chat.py`` fast-path — declines and empty-response fallbacks
     also record a synthetic PASS entry so the lane shows activity
     even on turns that didn't trip a filter.

Keeping this separate from ``policy_hook`` so the two lanes (Cedar
policy vs. Bedrock Guardrails) stay independently observable. A joint
buffer would conflate very different check types and make later
drift-debugging harder.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

_GUARDRAILS_MAX = 1000
_lock = threading.Lock()
_decisions: Dict[str, Deque[Dict[str, Any]]] = {}


def record_guardrail(
    session_id: Optional[str],
    source: str,
    action: str,
    allowed: bool,
    violations: List[Dict[str, Any]],
    latency_ms: Optional[int] = None,
    text_preview: Optional[str] = None,
    mode: Optional[str] = None,
) -> None:
    """Append a guardrail outcome to the per-session buffer.

    ``source`` is "INPUT" or "OUTPUT" (Bedrock's own vocabulary).
    ``action`` is the raw Bedrock action string ("NONE" / "GUARDRAIL_INTERVENED"
    / "ERROR") — preserved verbatim so the Atelier can surface exact
    Bedrock semantics without reinterpretation.
    ``mode`` is "pass-through" when the guardrail isn't configured so
    the Atelier can label those rows honestly.
    """
    key = session_id or "_anonymous"
    entry: Dict[str, Any] = {
        "timestamp_ms": int(time.time() * 1000),
        "source": source,
        "action": action,
        "allowed": allowed,
        "violations": violations,
        "latency_ms": latency_ms,
        "text_preview": _truncate(text_preview, 120) if text_preview else None,
        "mode": mode,
    }
    with _lock:
        buf = _decisions.get(key)
        if buf is None:
            buf = deque(maxlen=_GUARDRAILS_MAX)
            _decisions[key] = buf
        buf.append(entry)


def get_guardrails(
    session_id: Optional[str], limit: int = 50
) -> List[Dict[str, Any]]:
    """Return the most recent ``limit`` entries for a session.
    Newest first."""
    key = session_id or "_anonymous"
    with _lock:
        buf = _decisions.get(key)
        if not buf:
            return []
        entries = list(buf)
    return list(reversed(entries[-limit:]))


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"
