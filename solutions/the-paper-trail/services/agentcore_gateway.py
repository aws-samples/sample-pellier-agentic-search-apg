"""
AgentCore Gateway — MCP Tool Discovery via Bedrock AgentCore Gateway.

This module has two sides:

1. **Server side (Challenge 7)** — exposes the 9 `agent_tools.py` tools via
   the MCP streamable HTTP transport so external agent clients can discover
   and invoke them over the wire. Signatures and JSON envelopes are
   identical to the in-process `@tool` functions.

2. **Client side** — creates a Strands `Agent` that connects *back* to a
   Gateway URL and discovers tools dynamically via `MCPClient`. Used when
   migrating the orchestrator from hard-coded tool imports to MCP-based
   discovery.
"""
import logging
from typing import Optional, List, Dict, Any

from config import settings

logger = logging.getLogger(__name__)


# === CHALLENGE 7: START ===
# Expose the 9 Strands @tool functions via MCP streamable HTTP so an external
# agent client (or the AgentCore Gateway) can discover and invoke them with
# the same signatures and JSON envelopes used by the in-process orchestrator.
#
# The 9 tools come from the boutique agent_tools module and MUST be registered
# under these exact names (matching the @tool function names):
#   find_pieces, whats_trending, price_intelligence,
#   explore_collection, floor_check, running_low,
#   restock_shelf, side_by_side, returns_and_care
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-paper-trail/services/agentcore_gateway.py pellier/backend/services/agentcore_gateway.py

# The 9 tool names exposed by the gateway, in stable order. Tests assert
# discovery returns exactly this set by exact name (workshop-content.md).
GATEWAY_TOOL_NAMES: List[str] = [
    "find_pieces",
    "whats_trending",
    "price_intelligence",
    "explore_collection",
    "floor_check",
    "running_low",
    "restock_shelf",
    "side_by_side",
    "returns_and_care",
]


def _unwrap_strands_tool(strands_tool: Any) -> Any:
    """Return the plain Python callable underneath a Strands `@tool` wrapper.

    Strands' `@tool` produces a `DecoratedFunctionTool` whose original
    callable is exposed via the standard `__wrapped__` attribute. FastMCP
    needs the underlying function (with its signature and docstring) to
    derive the MCP input schema, so we reach through the decorator here.
    """
    return getattr(strands_tool, "__wrapped__", strands_tool)


def build_mcp_server(name: str = "pellier-gateway") -> Any:
    """Build a FastMCP server registering the 9 agent tools.

    Each registered MCP tool is a thin wrapper that delegates to the
    corresponding `@tool` function in `services.agent_tools`. Wrappers
    return the same JSON-serialized string the in-process tool returns so
    MCP clients observe an identical envelope.

    Raises:
        ImportError: if the `mcp` package is not installed.
    """
    from mcp.server.fastmcp import FastMCP
    import services.agent_tools as agent_tools

    mcp_server = FastMCP(name=name)

    # Register each of the 9 tools by name. We pass the unwrapped function
    # (not the Strands DecoratedFunctionTool) so FastMCP can introspect the
    # signature and docstring to generate the MCP input schema.
    for tool_name in GATEWAY_TOOL_NAMES:
        strands_tool = getattr(agent_tools, tool_name)
        fn = _unwrap_strands_tool(strands_tool)
        # Preserve the exact public tool name — FastMCP defaults to the
        # function's __name__ but we pin it explicitly for Req 2.2.3.
        mcp_server.add_tool(fn, name=tool_name, description=fn.__doc__ or "")

    return mcp_server


def get_streamable_http_app(name: str = "pellier-gateway") -> Any:
    """Return the Starlette ASGI app that serves the MCP streamable HTTP
    transport. Mount under `/mcp` in FastAPI (or run standalone with uvicorn)
    so external clients can discover tools via POST /mcp and invoke them.

    Raises:
        ImportError: if the `mcp` package is not installed.
    """
    mcp_server = build_mcp_server(name=name)
    return mcp_server.streamable_http_app()


def create_gateway_orchestrator():
    """Create a Strands Agent that discovers tools via an MCP Gateway URL.

    When `settings.AGENTCORE_GATEWAY_URL` is unset, returns None so callers
    can fall back to the in-process tool imports. When set, the returned
    agent pulls tools from the remote Gateway using streamable HTTP, which
    is how the orchestrator migrates from hard-coded tool lists to
    managed, discoverable tools.
    """
    if not settings.AGENTCORE_GATEWAY_URL:
        logger.info("AGENTCORE_GATEWAY_URL not set — gateway disabled")
        return None

    try:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.tools.mcp.mcp_client import MCPClient
        from mcp.client.streamable_http import streamablehttp_client

        def _create_transport():
            return streamablehttp_client(
                settings.AGENTCORE_GATEWAY_URL,
                headers={"x-api-key": settings.AGENTCORE_GATEWAY_API_KEY},
            )

        mcp_client = MCPClient(_create_transport)

        orchestrator = Agent(
            model=BedrockModel(
                model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
                max_tokens=4096,
                temperature=0.0,
            ),
            system_prompt=(
                "You are the Pellier shopping assistant. "
                "Use the available tools to help users find products, "
                "check prices, and get recommendations. "
                "Always be helpful and concise."
            ),
            tools=[mcp_client],
        )

        logger.info(
            "✅ Gateway orchestrator created (url=%s)",
            settings.AGENTCORE_GATEWAY_URL,
        )
        return orchestrator

    except ImportError as e:
        logger.warning("MCP dependencies not installed: %s", e)
        return None
    except Exception as e:
        logger.warning("Gateway orchestrator setup failed: %s", e)
        return None
# === CHALLENGE 7: END ===


def create_gateway_orchestrator_with_semantic_search():
    """
    Create an orchestrator that discovers tools via Gateway semantic search.

    Instead of loading all tools into the agent's context (list_tools),
    this uses the x_amz_bedrock_agentcore_search tool to find relevant
    tools by natural language description at query time. This scales to
    hundreds or thousands of tools without bloating the agent's prompt.

    Returns:
        Strands Agent with semantic tool discovery, or None if not configured
    """
    if not settings.AGENTCORE_GATEWAY_URL:
        logger.info("AGENTCORE_GATEWAY_URL not set — semantic search disabled")
        return None

    try:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.tools.mcp.mcp_client import MCPClient
        from mcp.client.streamable_http import streamablehttp_client

        def _create_transport():
            return streamablehttp_client(
                settings.AGENTCORE_GATEWAY_URL,
                headers={"x-api-key": settings.AGENTCORE_GATEWAY_API_KEY},
            )

        mcp_client = MCPClient(_create_transport)

        # The agent uses x_amz_bedrock_agentcore_search to find tools
        # by description rather than loading all tools into its prompt.
        # This is the production pattern for large tool catalogs.
        orchestrator = Agent(
            model=BedrockModel(
                model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
                max_tokens=4096,
                temperature=0.0,
            ),
            system_prompt=(
                "You are the Pellier shopping assistant. "
                "Use the x_amz_bedrock_agentcore_search tool to find "
                "relevant tools for the user's query, then invoke them. "
                "For product searches, search for 'product search' tools. "
                "For inventory questions, search for 'inventory' tools. "
                "For pricing, search for 'pricing' tools. "
                "For return policies and support, search for 'return policy' or 'customer support' tools. "
                "For category browsing, search for 'category' tools. "
                "For product comparisons, search for 'compare products' tools."
            ),
            tools=[mcp_client],
        )

        logger.info(f"✅ Gateway orchestrator with semantic search created")
        return orchestrator

    except ImportError as e:
        logger.warning(f"MCP dependencies not installed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Gateway semantic search setup failed: {e}")
        return None


def list_gateway_tools() -> List[Dict[str, Any]]:
    """
    List all tools registered in the AgentCore Gateway MCP server.

    Returns a list of tool descriptors with name, description, and input schema.
    """
    if not settings.AGENTCORE_GATEWAY_URL:
        return []

    try:
        from strands.tools.mcp.mcp_client import MCPClient
        from mcp.client.streamable_http import streamablehttp_client

        def _create_transport():
            return streamablehttp_client(
                settings.AGENTCORE_GATEWAY_URL,
                headers={"x-api-key": settings.AGENTCORE_GATEWAY_API_KEY},
            )

        mcp_client = MCPClient(_create_transport)
        mcp_client.start()

        try:
            tools = []
            for tool in mcp_client.list_tools_sync():
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                })
            return tools
        finally:
            mcp_client.stop()

    except ImportError:
        logger.warning("MCP dependencies not installed")
        return []
    except Exception as e:
        logger.warning(f"Failed to list gateway tools: {e}")
        return []
