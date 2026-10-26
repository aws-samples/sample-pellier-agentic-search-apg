"""Exercise the real MCP adapter's model-name and wire-name boundary."""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import Tool
from strands.tools.mcp.mcp_agent_tool import MCPAgentTool

from services import agentcore_gateway as gateway

DEPLOY_DIR = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

import gateway_tool_schemas as schemas  # noqa: E402


def tool(name: str, client=None) -> MCPAgentTool:
    return MCPAgentTool(
        Tool(name=name, inputSchema={"type": "object"}, description="Read orders"),
        client or MagicMock(),
        timeout=timedelta(seconds=30),
    )


def test_long_gateway_name_is_short_in_bedrock_but_unchanged_on_the_wire():
    # The store target's own prefix is short; a longer deployment prefix is what
    # pushed a name past Bedrock's limit (the observed managed ConverseStream failure).
    original = "long-deployment-prefix-" * 3 + "pellier-store-tools___get_orders"
    assert len(original) > 64
    client = MagicMock()
    client.call_tool_async = AsyncMock(return_value={
        "toolUseId": "call-1",
        "status": "success",
        "content": [{"text": "Recorded preferences"}],
    })
    source = tool(original, client)
    adapted, = gateway._model_gateway_tools([source])
    assert adapted.tool_name == adapted.tool_spec["name"] == "get_orders"
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


def test_the_store_target_names_stay_inside_the_bedrock_limit():
    assert all(len(gateway.gateway_action_id(name)) <= 64
               for name in gateway.GATEWAY_TARGET_FOR_TOOL)


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


def test_short_alias_still_binds_server_owned_customer_and_correlation(monkeypatch):
    """Task 3A done (get_orders bound): a model-facing alias still reaches the binding."""
    monkeypatch.setattr(gateway, "_CUSTOMER_SCOPED_TOOL_NAMES",
                        frozenset({"get_orders", "get_tickets"}))
    adapted, = gateway._model_gateway_tools([tool(
        gateway.gateway_action_id("get_orders"),
    )])
    bound = gateway._bind_server_tool_context({
        "name": adapted.tool_name,
        "toolUseId": "call-1",
        "input": {"customer_id": "CUST-MARCO"},
    }, customer_id="CUST-THEO", turn_id="turn-owned")
    assert bound["input"] == {"customer_id": "CUST-THEO", "turn_id": "turn-owned"}


SERVER_SET = {"turn_id", "build_fingerprint"}


def published_tools() -> list[MCPAgentTool]:
    """Every tool the Gateway publishes, as discovery returns it: the real input schemas."""
    return [MCPAgentTool(Tool(name=gateway.gateway_action_id(spec["name"]),
                              description=spec["description"], inputSchema=spec["inputSchema"]),
                         MagicMock(), timeout=timedelta(seconds=30))
            for target in schemas.TOOL_SCHEMAS.values() for spec in target["tools"]]


def test_the_model_never_sees_the_arguments_the_server_sets(monkeypatch):
    """The Gateway publishes turn_id and build_fingerprint on every tool so a direct call stays
    valid, but on a managed call the server sets both. Shown to the model, they invited it to fill
    one in: on test event 17 the Stock agent told Marco it had filled in build_fingerprint itself.
    The model now sees neither, and the call still carries both."""
    monkeypatch.setenv("PELLIER_BUILD_FINGERPRINT", "build-abc")
    sources = published_tools()
    assert all(SERVER_SET <= set(t.mcp_tool.inputSchema["properties"]) for t in sources)

    adapted = gateway._model_gateway_tools(sources)

    for before, after in zip(sources, adapted):
        shown = after.tool_spec["inputSchema"]["json"]
        assert not SERVER_SET & set(shown["properties"]), after.tool_name
        published = set(before.mcp_tool.inputSchema["properties"])
        assert set(shown["properties"]) == published - SERVER_SET
        assert shown.get("required", []) == before.mcp_tool.inputSchema.get("required", [])
        assert SERVER_SET <= set(before.mcp_tool.inputSchema["properties"])  # Gateway copy kept
    check_stock = next(t for t in adapted if t.tool_name == "check_stock")
    bound = gateway._bind_server_tool_context(
        {"name": check_stock.tool_name, "toolUseId": "call-1",
         "input": {"product_query": "Velvet Opera Cape"}},
        customer_id="CUST-MARCO", turn_id="turn-owned")
    assert bound["input"] == {"product_query": "Velvet Opera Cape", "turn_id": "turn-owned",
                              "build_fingerprint": "build-abc"}



def test_the_filter_works_whatever_the_mcp_package_names_the_schema(monkeypatch):
    """The Runtime's packages are newer than this lock: its MCP Tool has `input_schema`, not
    `inputSchema` (test event 17: reading `inputSchema` there failed every managed turn with an
    AttributeError). The filter works on the spec Strands builds, never on the MCP Tool."""

    class NewerTool:
        def __init__(self, name, input_schema):
            self.name, self.input_schema, self.description = name, input_schema, "Check stock"
            self.outputSchema = None

        def __getattr__(self, item):
            raise AttributeError(f"'Tool' object has no attribute {item!r}")

    def newer_spec(self):
        return {"inputSchema": {"json": self.mcp_tool.input_schema}, "name": self.tool_name,
                "description": self.mcp_tool.description}

    monkeypatch.setattr(MCPAgentTool, "tool_spec", property(newer_spec))
    schema = {"type": "object", "required": ["product_query"],
              "properties": {"product_query": {"type": "string"},
                             "turn_id": {"type": "string"},
                             "build_fingerprint": {"type": "string"}}}
    source = MCPAgentTool(NewerTool(gateway.gateway_action_id("check_stock"), schema), MagicMock(),
                          timeout=timedelta(seconds=30))
    adapted, = gateway._model_gateway_tools([source])
    assert adapted.tool_spec["inputSchema"]["json"] == {
        "type": "object", "required": ["product_query"],
        "properties": {"product_query": {"type": "string"}}}
    assert adapted.mcp_tool.input_schema == schema
