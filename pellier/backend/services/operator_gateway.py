"""Staff tools bound to a verified actor and one selected case.

The model sees only the graph's five existing tools. The other two operations
load the case and close its shopper requests in application code. None can
approve a review or execute a credit. The Gateway independently checks the
staff claim and binds operator_sub to the signed subject on every call.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from services.runtime_identity import RuntimeIdentity

OPERATOR_TOOLS = frozenset({
    "get_case", "get_orders", "get_tickets", "get_store_credits", "get_return_policy",
    "propose_store_credit", "finish_investigation",
})


@dataclass(frozen=True)
class BoundOperatorTools:
    client: Any
    identity: RuntimeIdentity
    turn_id: str
    build_fingerprint: str

    def __call__(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in OPERATOR_TOOLS:
            raise ValueError("operator_tool_not_granted")
        result = self.client.call_tool_sync(
            tool_use_id=str(uuid.uuid4()),
            name=f"pellier-operator-tools___operator_{name}",
            arguments={**arguments, "customer_id": self.identity.customer_id,
                       "operator_sub": self.identity.subject, "turn_id": self.turn_id,
                       "build_fingerprint": self.build_fingerprint},
        )
        if result.get("status") != "success" or result.get("isError"):
            raise RuntimeError("operator_gateway_rejected")
        for block in result.get("content", []):
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                try:
                    value = json.loads(block["text"])
                except ValueError:
                    continue
                if isinstance(value, dict):
                    if value.get("customer_id") != self.identity.customer_id:
                        raise ValueError("operator_case_mismatch")
                    if value.get("status") == "error":
                        raise RuntimeError("operator_tool_failed")
                    return value
        raise RuntimeError("operator_gateway_invalid_result")


@contextmanager
def operator_tools(*, token: str, identity: RuntimeIdentity, turn_id: str,
                   build_fingerprint: str) -> Iterator[BoundOperatorTools]:
    from strands.tools.mcp.mcp_client import MCPClient
    from services.agentcore_gateway import (
        _gateway_streamable_http_transport, _runtime_or_app_setting, _stop_mcp_client,
    )

    url = _runtime_or_app_setting("AGENTCORE_GATEWAY_URL")
    if not url or not token:
        raise RuntimeError("operator_gateway_not_configured")
    client = MCPClient(lambda: _gateway_streamable_http_transport(url, token))
    client.start()
    try:
        names = {tool.tool_name for tool in client.list_tools_sync()}
        expected = {f"pellier-operator-tools___operator_{name}" for name in OPERATOR_TOOLS}
        if not expected.issubset(names):
            raise RuntimeError("operator_gateway_tools_missing")
        yield BoundOperatorTools(client, identity, turn_id, build_fingerprint)
    finally:
        _stop_mcp_client(client)
