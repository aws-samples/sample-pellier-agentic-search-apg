"""Shared pieces of the MCP invocation contract for the store-tools Lambda.

`resolve_invocation` in ``common/types.py`` accepts BOTH shapes the Gateway
sends (a `client_context`-prefixed event and a direct `{name, arguments}`).
The two helpers here are the read-audit rule and the `list_tools` listing,
which the Lambda's own handler composes with its per-tool dispatch.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

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
