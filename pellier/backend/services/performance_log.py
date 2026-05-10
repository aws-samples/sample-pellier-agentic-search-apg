"""Performance metrics log — per-turn latency + rolling aggregates.

The Atelier Performance tab used to hardcode numbers (3779ms LLM
synthesize, 4ms HNSW, etc.) lifted from an offline benchmark. That
worked for screenshots but lied once attendees started running real
queries. This module captures the real per-turn timing the chat
stream already emits (``runtime_timing`` event: ``layers`` +
``ttft_ms`` + ``total_ms``) into a rolling in-memory buffer, and
exposes aggregates so the Performance tab's bar chart + cold-start
histogram can render measured numbers.

Process-local by design. Multi-worker deployments would want a shared
store (Aurora, Valkey), but the Workshop Studio backend runs a single
container per attendee so the in-memory ring is sufficient and
avoids a new dependency for the workshop.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List

_MAX_TURNS = 500
_lock = threading.Lock()
_turns: Deque[Dict[str, Any]] = deque(maxlen=_MAX_TURNS)


def record_turn(
    session_id: str | None,
    layers: Dict[str, float],
    ttft_ms: int,
    total_ms: int,
    tool_trace: List[Dict[str, Any]] | None = None,
    pattern: str | None = None,
) -> None:
    """Record one turn's latency breakdown.

    ``layers`` mirrors chat.py's ``timing`` dict (fastpath, intent,
    skill_router, orchestrator, specialist, tools, stream).
    ``tool_trace`` is the list of ``{tool, ms, results}`` entries
    emitted during the turn — used to compute per-tool p50/p95.
    """
    entry = {
        "timestamp_ms": int(time.time() * 1000),
        "session_id": session_id or "_anonymous",
        "layers": dict(layers),
        "ttft_ms": int(ttft_ms),
        "total_ms": int(total_ms),
        "tool_trace": list(tool_trace or []),
        "pattern": pattern,
    }
    with _lock:
        _turns.append(entry)


def get_recent_turns(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent turns, newest first. Bounded by ``_MAX_TURNS``."""
    with _lock:
        all_turns = list(_turns)
    return list(reversed(all_turns[-limit:]))


def get_aggregates() -> Dict[str, Any]:
    """Return rolling p50 / p95 aggregates over the buffer.

    The Performance tab's bar chart renders ``layers`` percentiles
    directly. The cold-start histogram uses ``ttft_ms`` buckets. If
    the buffer is empty (no turns yet), callers see an explicit empty
    marker and render the illustrative placeholder — the UI doesn't
    fake numbers it doesn't have.
    """
    with _lock:
        turns = list(_turns)

    if not turns:
        return {
            "turn_count": 0,
            "empty": True,
            "layers_p50": {},
            "layers_p95": {},
            "total_p50": 0,
            "total_p95": 0,
            "ttft_p50": 0,
            "ttft_p95": 0,
        }

    layer_names = set()
    for t in turns:
        layer_names.update(t["layers"].keys())

    def _pct(values: List[float], pct: float) -> float:
        """Classic nearest-rank percentile. Deterministic on small N
        and avoids numpy for a dep we otherwise don't need in this
        module."""
        if not values:
            return 0.0
        s = sorted(values)
        idx = min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1))))
        return s[idx]

    layers_p50: Dict[str, float] = {}
    layers_p95: Dict[str, float] = {}
    for name in layer_names:
        vals = [float(t["layers"].get(name, 0.0)) for t in turns]
        layers_p50[name] = round(_pct(vals, 50), 1)
        layers_p95[name] = round(_pct(vals, 95), 1)

    totals = [float(t["total_ms"]) for t in turns]
    ttfts = [float(t["ttft_ms"]) for t in turns]

    # Histogram buckets for the cold-start chart. Fixed 20 buckets
    # 0-3500ms (100ms each) so the Performance tab can render a stable
    # bar layout regardless of the observed range.
    hist = [0] * 20
    for v in totals:
        bucket = min(19, max(0, int(v // 175)))
        hist[bucket] += 1

    # Per-tool p50 latency from the tool_trace entries.
    tool_latencies: Dict[str, List[float]] = {}
    for t in turns:
        for tt in t.get("tool_trace", []):
            name = tt.get("tool", "")
            ms = tt.get("ms")
            if name and isinstance(ms, (int, float)):
                tool_latencies.setdefault(name, []).append(float(ms))
    tools_p50 = {k: round(_pct(v, 50), 1) for k, v in tool_latencies.items()}

    return {
        "turn_count": len(turns),
        "empty": False,
        "layers_p50": layers_p50,
        "layers_p95": layers_p95,
        "total_p50": round(_pct(totals, 50), 1),
        "total_p95": round(_pct(totals, 95), 1),
        "ttft_p50": round(_pct(ttfts, 50), 1),
        "ttft_p95": round(_pct(ttfts, 95), 1),
        "histogram": hist,
        "tools_p50": tools_p50,
    }
