"""A side channel for evidence a tool computes beside its result.

The model reads a tool's result. The Builder view reads what a tool publishes
here: the ranking detail behind a search, the retrieval receipt id, and the
identity-binding facts of a customer-scoped read. Keeping them off the result
costs the model no tokens and gives it nothing to recite.

The channel is a ``ContextVar`` holding one list per turn. ``chat_stream``
opens it before the agent runs; ``asyncio.to_thread`` copies the context into
the Strands worker, so the tool and the after-tool hook share the same list
object and the hook can take what the tool published. Outside a turn the
channel is closed and ``publish`` is a no-op, which is what the Gateway Lambda
and the scripts see.
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable, Dict, List, Optional, Tuple

_channel: contextvars.ContextVar[Optional[List[Tuple[str, Dict[str, Any]]]]] = (
    contextvars.ContextVar("pellier_tool_evidence", default=None)
)


def open_channel() -> contextvars.Token:
    """Start collecting evidence for the current turn; reset with ``close_channel``."""
    return _channel.set([])


def close_channel(token: contextvars.Token) -> None:
    """Stop collecting and drop anything a tool published after its hook ran."""
    _channel.reset(token)


def publish(tool: str, payload: Dict[str, Any]) -> None:
    """Record evidence for ``tool``; silently ignored when no turn is open."""
    channel = _channel.get()
    if channel is None:
        return
    channel.append((tool, dict(payload)))


def publisher(tool: str) -> Callable[[Dict[str, Any]], None]:
    """A sink bound to one tool, for code that must not know about the channel."""
    return lambda payload: publish(tool, payload)


def take(tool: str) -> Dict[str, Any]:
    """Remove and merge everything published for ``tool``, oldest first."""
    channel = _channel.get()
    if not channel:
        return {}
    merged: Dict[str, Any] = {}
    kept: List[Tuple[str, Dict[str, Any]]] = []
    for name, payload in channel:
        if name == tool:
            merged.update(payload)
        else:
            kept.append((name, payload))
    channel[:] = kept
    return merged
