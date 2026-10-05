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

Evidence is keyed by the tool use, not only the tool name: an agent can run
the same tool twice at once, and each call's evidence belongs to its own
step. Strands runs each tool use in its own asyncio task, calls the
before-tool hook inside that task, and runs the tool body in a thread that
copies the task's context. So the hook binds the tool-use id here
(``bind_call``), every ``publish`` inside that call records it, and the
after-tool hook takes exactly that call's evidence. No tool signature changes.
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable, Dict, List, Optional, Tuple

# One published item: the tool, the tool use it ran in, and the payload.
_Entry = Tuple[str, Optional[str], Dict[str, Any]]

_channel: contextvars.ContextVar[Optional[List[_Entry]]] = contextvars.ContextVar(
    "pellier_tool_evidence", default=None
)
_call: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "pellier_tool_evidence_call", default=None
)


def open_channel() -> contextvars.Token:
    """Start collecting evidence for the current turn; reset with ``close_channel``."""
    return _channel.set([])


def close_channel(token: contextvars.Token) -> None:
    """Stop collecting and drop anything a tool published after its hook ran."""
    _channel.reset(token)


def is_open() -> bool:
    """True inside a turn that collects evidence, so a tool can skip work nobody reads."""
    return _channel.get() is not None


def bind_call(call_id: Optional[str]) -> None:
    """Mark the current context as running tool use ``call_id``.

    Called by the before-tool hook, inside the task Strands runs that one
    tool use in, so the tool body's ``publish`` calls carry the id.
    """
    _call.set(call_id or None)


def publish(tool: str, payload: Dict[str, Any]) -> None:
    """Record evidence for ``tool`` in the bound tool use; ignored when no turn is open."""
    channel = _channel.get()
    if channel is None:
        return
    channel.append((tool, _call.get(), dict(payload)))


def publisher(tool: str) -> Callable[[Dict[str, Any]], None]:
    """A sink bound to one tool, for code that must not know about the channel."""
    return lambda payload: publish(tool, payload)


def take(tool: str, call_id: Optional[str] = None) -> Dict[str, Any]:
    """Remove and merge what tool use ``call_id`` of ``tool`` published, oldest first.

    Another call of the same tool keeps its own evidence. ``call_id`` is
    ``None`` only where no hook bound one, such as a test that calls a tool
    directly; it then matches only what was published unbound.
    """
    channel = _channel.get()
    if not channel:
        return {}
    wanted = call_id or None
    merged: Dict[str, Any] = {}
    kept: List[_Entry] = []
    for name, call, payload in channel:
        if name == tool and call == wanted:
            merged.update(payload)
        else:
            kept.append((name, call, payload))
    channel[:] = kept
    return merged
