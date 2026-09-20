"""The MCP invocation contract, shared by surface servers that need no extra wiring.

Two of the four surface servers had byte-identical handlers. That duplication is
riskier than it looks, because the part most likely to be edited is the part
that must never diverge: `resolve_invocation` exists to accept BOTH shapes the
Gateway sends (a `client_context`-prefixed event and a direct
`{name, arguments}`), and a surface that lost one shape would fail only for the
caller that used it.

Not every surface can use this. The search and experience servers wrap tool
execution in an Aurora transaction and write an audit row inside it, so their
handlers keep their own execution branch on purpose. Forcing all four through
one function would mean a hook parameter existing solely to describe how they
differ, which is a worse abstraction than two honest handlers.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict

from common.types import resolve_invocation

logger = logging.getLogger(__name__)


def audit_read_call(tool: str, arguments: dict, result: Any, started: float) -> None:
    """Correlate a completed managed read with the route's immutable turn.

    Mutation tools already write their own receipts. This helper records only
    reads carrying a turn id; an instructor's uncorrelated call cannot establish
    a shopper turn's evidence. Failed audit writes remain visible in service logs.
    """
    turn_id = arguments.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id.startswith("turn-"):
        return
    from common.dataapi import write_tool_audit_independently

    write_tool_audit_independently(
        tool=tool, args=arguments, result=result,
        latency_ms=int((time.monotonic() - started) * 1000), session_id=turn_id,
    )


def tool_catalog(tools: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Return the `list_tools` response for a surface's registry.

    Args:
        tools: The surface's ``TOOLS`` mapping, name to spec.

    Returns:
        The MCP tool listing the Gateway reads during discovery.
    """
    return {
        "tools": [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            }
            for name, spec in tools.items()
        ]
    }


def build_handler(tools: Dict[str, Dict[str, Any]]) -> Callable[[dict, Any], dict]:
    """Return a Lambda handler that dispatches straight to a tool.

    For surfaces whose tools need no transaction or audit wiring.

    Args:
        tools: The surface's ``TOOLS`` mapping.

    Returns:
        A ``lambda_handler(event, context)`` callable.
    """

    def lambda_handler(event: dict, context: Any) -> dict:
        """Dispatch one MCP tool invocation from the Gateway."""
        tool_name, arguments = resolve_invocation(event, context)

        if tool_name == "list_tools":
            return tool_catalog(tools)

        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            started = time.monotonic()
            # `turn_id` is correlation metadata the Gateway may attach; it is
            # not a tool parameter, and passing it through would be a
            # TypeError on every tool that does not declare it.
            execution_arguments = {
                key: value for key, value in arguments.items() if key != "turn_id"
            }
            result = tools[tool_name]["fn"](**execution_arguments)
            audit_read_call(tool_name, arguments, result, started)
            return {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}]
            }
        except Exception as exc:
            logger.error(f"Tool {tool_name} failed: {exc}")
            return {
                "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                "isError": True,
            }

    return lambda_handler
