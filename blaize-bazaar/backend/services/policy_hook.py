"""
Policy Hook — Strands ``BeforeToolCallEvent`` enforcement layer.

This module hangs the existing ``PolicyService`` (Cedar local engine,
``services/agentcore_policy.py``) off the Strands event loop so every
agent tool call is inspected BEFORE it runs. A DENY decision cancels
the tool via ``event.cancel_tool = "..."`` — Strands then injects a
synthetic tool result containing the denial message, which the agent
reads and paraphrases back to the user.

Why a hook and not a wrapper per tool:

* Zero per-tool plumbing. Every new @tool in ``services/agent_tools``
  is covered the moment the hook is attached — no need to remember
  to add a decorator.
* Uniform telemetry. Every enforcement decision flows through the
  same spot, so the Atelier Policy panel can show an honest,
  complete audit trail keyed on ``toolUseId``.
* Single source of truth. ``PolicyService.evaluate()`` is the one
  place policies live; the hook just plumbs tool_use → evaluate and
  translates the decision into the Strands control-flow primitive
  (``cancel_tool``).

We also capture each decision in a per-turn decision log (in-memory,
bounded) so the routes in ``routes/atelier.py`` can surface live
enforcement data to the Atelier Policy tab without needing a
backend-agnostic store.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent

from services.agentcore_policy import get_policy_service
from services import tool_audit_writer

logger = logging.getLogger(__name__)


# Map Strands tool names → PolicyService action keys. PolicyService's
# ``applies_to`` field uses a smaller vocabulary than the tool set
# (e.g., ``set_price`` covers pricing-changing tools collectively).
# Tools not in this map simply bypass the policy engine — they're
# read-only catalog queries with no risk surface worth enforcing.
_TOOL_TO_POLICY_ACTION: Dict[str, str] = {
    # Restock gates on quantity.
    "restock_shelf": "restock_shelf",
    # Search gates on restricted categories/keywords.
    "find_pieces": "find_pieces",
    "find_pieces_hybrid": "find_pieces",
    "explore_collection": "find_pieces",
    # Pricing-changing tools gate on ceiling. (The current tool set
    # doesn't have a direct ``set_price`` tool — the mapping exists
    # so a future pricing-write tool inherits enforcement automatically.)
    "set_price": "set_price",
    # Process Return gates on the reason value (Theo's anchor write).
    # The reason field drives the workflow branch in
    # BusinessLogic.process_return — only 'damaged' decrements
    # quantity — so a free-form reason would silently skip the
    # inventory adjustment. Cedar enforces the canonical set.
    "process_return": "process_return",
}

# Tools that mutate Aurora state. Audited unconditionally on ALLOW so
# Theo's "agents that write state with a paper trail" story has a
# real paper trail. Read-only tools skip the audit because the
# Atelier already shows their tool calls via the spans surface; no
# need to double-write.
_MUTATING_TOOLS = {"restock_shelf", "process_return"}


# Bounded in-memory buffer of recent enforcement decisions, keyed by
# session_id so the Atelier Policy tab can show "this turn's
# decisions" without mixing sessions. Each entry is a plain dict so
# routes can serialize it to JSON directly. 1000 entries per session
# is far more than a workshop needs; the oldest are evicted in FIFO
# order when the cap is hit.
_DECISIONS_MAX = 1000
_decisions_lock = threading.Lock()
_decisions: Dict[str, Deque[Dict[str, Any]]] = {}


def record_decision(session_id: Optional[str], decision: Dict[str, Any]) -> None:
    """Append a decision to the per-session buffer. Public so the
    Atelier routes can read without importing the deque directly."""
    if not session_id:
        session_id = "_anonymous"
    with _decisions_lock:
        buf = _decisions.get(session_id)
        if buf is None:
            buf = deque(maxlen=_DECISIONS_MAX)
            _decisions[session_id] = buf
        buf.append(decision)


def get_decisions(session_id: Optional[str], limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent ``limit`` decisions for a session.
    Newest first. Empty list if session has no recorded decisions."""
    if not session_id:
        session_id = "_anonymous"
    with _decisions_lock:
        buf = _decisions.get(session_id)
        if not buf:
            return []
        # deque is oldest-first; reverse to return newest-first.
        entries = list(buf)
    return list(reversed(entries[-limit:]))


class PolicyEnforcementHook(HookProvider):
    """Strands hook provider that consults ``PolicyService`` before
    every tool call and cancels DENY outcomes.

    One instance per agent turn. ``session_id`` is stashed on the
    hook so every decision gets tagged with the right session, and
    the Atelier Policy tab can filter by the current session.

    We deliberately DON'T intercept the agent's prose — attackers
    could phrase a restricted query conversationally. Tools are the
    chokepoint because the specialist has to call one to act on the
    catalog. A Bedrock Guardrail can layer in on the prose side
    later (Commit 11).
    """

    def __init__(self, session_id: Optional[str] = None) -> None:
        self.session_id = session_id
        self._policy = get_policy_service()
        # tool_use_id → wall-clock start time, used to compute latency
        # in the After event. Bounded by the same eviction the audit
        # writer uses so a runaway agent can't grow this map forever.
        self._allow_starts: Dict[str, float] = {}

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        """Strands HookProvider contract — register our callbacks.

        BeforeToolCallEvent  — Cedar enforcement + audit INSERT on ALLOW
        AfterToolCallEvent   — audit UPDATE with result + latency
        """
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool)

    def _on_before_tool(self, event: BeforeToolCallEvent) -> None:
        """Evaluate the pending tool call against PolicyService and
        cancel it with a human-readable message on DENY."""
        tool_use = event.tool_use
        if not isinstance(tool_use, dict):
            return
        tool_name = tool_use.get("name", "")
        action = _TOOL_TO_POLICY_ACTION.get(tool_name)
        if action is None:
            return  # Not a policy-gated tool; let it run.

        # Strands stores tool args under ``input`` for v1 tool_use.
        # Fall back to ``parameters`` and the top-level dict for
        # compatibility with older shapes.
        params = tool_use.get("input")
        if not isinstance(params, dict):
            params = tool_use.get("parameters")
        if not isinstance(params, dict):
            params = {}

        try:
            result = self._policy.evaluate(action, params)
        except Exception as exc:
            logger.warning(
                "PolicyService.evaluate raised for tool=%s: %s — fail-open",
                tool_name, exc,
            )
            return

        decision_record = {
            "timestamp_ms": int(time.time() * 1000),
            "tool_name": tool_name,
            "action": action,
            "decision": result.get("decision", "ALLOW"),
            "violations": result.get("violations", []),
            "matching_policies": result.get("matching_policies", []),
            "parameters": params,
            "tool_use_id": tool_use.get("toolUseId"),
        }
        record_decision(self.session_id, decision_record)

        if result.get("decision") == "ALLOW" and tool_name in _MUTATING_TOOLS:
            # ALLOW + mutating tool → audit it. We INSERT a placeholder
            # row now (latency_ms NULL, result NULL); the AfterToolCallEvent
            # below will UPDATE it once the tool returns. If the tool
            # raises, the placeholder row remains — itself a real signal
            # ("started but didn't finish").
            tool_use_id = tool_use.get("toolUseId")
            if tool_use_id:
                self._allow_starts[tool_use_id] = time.time()
                tool_audit_writer.record_allow(
                    tool_use_id=tool_use_id,
                    tool_name=tool_name,
                    caller="agent",  # Strands doesn't expose the agent
                                       # name on the event; we tag generically.
                    args=params,
                    session_id=self.session_id,
                )

        if result.get("decision") == "DENY":
            violations = result.get("violations", [])
            # Compose a user-facing reason. If multiple violations,
            # join them with semicolons — the agent will paraphrase
            # the whole thing into its own reply.
            reasons = [v.get("reason", "") for v in violations if v.get("reason")]
            reason_text = "; ".join(reasons) if reasons else "Policy denied this action"
            cancel_msg = (
                f"Policy denied: {reason_text}. "
                "Explain to the user that this request conflicts with an active "
                "store policy and offer a compliant alternative if possible."
            )
            # Strands interprets a string here as both a cancellation
            # AND the synthetic tool-result payload the agent sees.
            event.cancel_tool = cancel_msg
            logger.info(
                "🚫 policy_deny | tool=%s | %s",
                tool_name, reason_text[:80],
            )

    def _on_after_tool(self, event: AfterToolCallEvent) -> None:
        """UPDATE the audit row with the tool's result + latency.

        Only fires for mutating tools whose ALLOW path INSERTed a
        placeholder row in ``_on_before_tool``. For everything else
        this is a no-op (no _allow_starts entry).

        Strands' AfterToolCallEvent attribute names vary across versions
        (``result``, ``output``, ``tool_result``); we duck-type so we
        survive the upgrade path without coupling to a single shape.
        """
        tool_use = getattr(event, "tool_use", None)
        if not isinstance(tool_use, dict):
            return
        tool_use_id = tool_use.get("toolUseId")
        if not tool_use_id:
            return
        start = self._allow_starts.pop(tool_use_id, None)
        if start is None:
            return
        latency_ms = int((time.time() - start) * 1000)
        # Try the most common attribute names in order. If none expose
        # the result, we still UPDATE latency + leave result NULL.
        result_payload: Any = None
        for attr in ("result", "output", "tool_result"):
            r = getattr(event, attr, None)
            if r is not None:
                result_payload = r
                break
        tool_audit_writer.record_after(
            tool_use_id=tool_use_id,
            result=result_payload,
            latency_ms=latency_ms,
        )
