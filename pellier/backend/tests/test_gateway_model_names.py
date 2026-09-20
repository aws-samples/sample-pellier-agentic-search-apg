"""Exercise the real MCP adapter's model-name and wire-name boundary."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import Tool
from strands.tools.mcp.mcp_agent_tool import MCPAgentTool

from services import agentcore_gateway as gateway


def tool(name: str, client=None) -> MCPAgentTool:
    return MCPAgentTool(
        Tool(name=name, inputSchema={"type": "object"}, description="Read preferences"),
        client or MagicMock(),
        timeout=timedelta(seconds=30),
    )


def test_long_gateway_name_is_short_in_bedrock_but_unchanged_on_the_wire():
    original = gateway.gateway_action_id("get_customer_preferences")
    assert len(original) > 64  # The observed managed ConverseStream failure.
    client = MagicMock()
    client.call_tool_async = AsyncMock(return_value={
        "toolUseId": "call-1",
        "status": "success",
        "content": [{"text": "Recorded preferences"}],
    })
    source = tool(original, client)
    adapted, = gateway._model_gateway_tools([source])
    assert adapted.tool_name == adapted.tool_spec["name"] == "get_customer_preferences"
    assert adapted.tool_spec["inputSchema"] == source.tool_spec["inputSchema"]
    assert adapted.mcp_tool.name == original
    assert source.tool_name == original

    async def invoke():
        return [event async for event in adapted.stream({
            "name": adapted.tool_name,
            "toolUseId": "call-1",
            "input": {"customer_id": "CUST-THEO"},
        }, {})]

    assert asyncio.run(invoke())
    client.call_tool_async.assert_awaited_once_with(
        tool_use_id="call-1",
        name=original,
        arguments={"customer_id": "CUST-THEO"},
        read_timeout_seconds=timedelta(seconds=30),
    )


def test_every_current_catalog_tool_has_a_unique_bedrock_compatible_name():
    originals = [tool(gateway.gateway_action_id(name)) for name in gateway.GATEWAY_TARGET_FOR_TOOL]
    adapted = gateway._model_gateway_tools(originals)
    assert len({item.tool_name for item in adapted}) == len(originals)
    assert all(0 < len(item.tool_spec["name"]) <= 64 for item in adapted)
    assert [item.mcp_tool.name for item in adapted] == [item.tool_name for item in originals]


def test_two_targets_with_the_same_logical_name_cannot_silently_replace_each_other():
    with pytest.raises(RuntimeError, match="ambiguous logical tool"):
        gateway._model_gateway_tools([
            tool("first-target___search_products"),
            tool("second-target___search_products"),
        ])


@pytest.mark.parametrize("name", ["target___" + "x" * 65, "target___bad.name", "target___"])
def test_invalid_model_name_fails_before_agent_construction(name):
    with pytest.raises(RuntimeError, match="valid Bedrock name"):
        gateway._model_gateway_tools([tool(name)])


def test_short_alias_still_binds_server_owned_customer_and_correlation():
    adapted, = gateway._model_gateway_tools([tool(
        gateway.gateway_action_id("get_customer_preferences"),
    )])
    bound = gateway._bind_server_tool_context({
        "name": adapted.tool_name,
        "toolUseId": "call-1",
        "input": {"customer_id": "CUST-MARCO", "persona": "marco"},
    }, customer_id="CUST-THEO", turn_id="turn-owned")
    assert bound["input"] == {"customer_id": "CUST-THEO", "turn_id": "turn-owned"}
