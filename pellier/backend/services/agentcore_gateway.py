"""
AgentCore Gateway — MCP tool discovery via Bedrock AgentCore Gateway.

AgentCore Gateway (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
is a managed MCP front-door for tool catalogs. It enforces Cognito JWT
auth on every tool call, then proxies to registered Lambda or HTTP
targets. From the orchestrator's perspective, "having a Gateway" means
tool definitions stop living in Python imports and start being
discovered dynamically over the wire.

This module has two sides:

1. **Server side (Challenge 7)** — exposes the 13 `agent_tools.py`
   tools via the MCP streamable HTTP transport so external agent
   clients (or AgentCore Gateway itself) can discover and invoke them.
   Signatures and JSON envelopes are identical to the in-process
   `@tool` functions, so the orchestrator can switch between the two
   transports without changing how it calls them.

2. **Client side** — creates a Strands `Agent` that connects *back* to
   a Gateway URL and pulls its tool list at agent-construction time
   via `MCPClient.list_tools_sync()`. This is the production wiring:
   the agent prompt no longer carries a hard-coded tool list; the
   Gateway is the source of truth.

MCP (Model Context Protocol) docs: https://modelcontextprotocol.io
"""
import logging
from typing import Optional, List, Dict, Any

from config import settings

logger = logging.getLogger(__name__)


# === CHALLENGE 7: START ===
# Expose the 13 Strands @tool functions via MCP streamable HTTP so an external
# agent client (or the AgentCore Gateway) can discover and invoke them with
# the same signatures and JSON envelopes used by the in-process orchestrator.
#
# The 13 tools come from workshop-content.md steering and MUST be registered
# under these exact names (Req 2.2.3):
#   find_pieces, find_pieces_hybrid, whats_trending, price_intelligence,
#   explore_collection, floor_check, running_low, restock_shelf,
#   side_by_side, returns_and_care, style_match, process_return,
#   escalate_to_stylist
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_gateway.py pellier/backend/services/agentcore_gateway.py

# The 13 tool names exposed by the gateway, in stable order. Tests assert
# discovery returns exactly this set by exact name (workshop-content.md).
GATEWAY_TOOL_NAMES: List[str] = [
    "find_pieces",
    "find_pieces_hybrid",
    "whats_trending",
    "price_intelligence",
    "explore_collection",
    "floor_check",
    "running_low",
    "restock_shelf",
    "side_by_side",
    "returns_and_care",
    "style_match",
    "process_return",
    "escalate_to_stylist",
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
    """Build a FastMCP server registering the 13 agent tools.

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

    # Register each of the 13 tools by name. We pass the unwrapped function
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


def _gateway_headers(access_token: Optional[str] = None) -> Dict[str, str]:
    """Build the auth headers for an MCP call to the AgentCore Gateway.

    The Gateway is deployed with a Cognito CUSTOM_JWT authorizer, so the
    production path is **JWT passthrough**: the caller's raw Cognito access
    token is sent as ``Authorization: Bearer <token>`` and the Gateway
    validates it against the Cognito discovery URL, so every tool call
    carries the user's identity end to end.

    When no token is provided (anonymous/Fresh turns, or local dev against a
    Gateway deployed with ``authorizerType=NONE``), we fall back to the
    placeholder ``x-api-key`` header. A JWT-protected Gateway will reject
    that with 401, which the caller treats as "fall back to in-process".
    """
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    return {"x-api-key": settings.AGENTCORE_GATEWAY_API_KEY}


def create_gateway_orchestrator(access_token: Optional[str] = None):
    """Create a Strands Agent that discovers tools via an MCP Gateway URL.

    When `settings.AGENTCORE_GATEWAY_URL` is unset, returns None so callers
    can fall back to the in-process tool imports. When set, the returned
    agent pulls tools from the remote Gateway using streamable HTTP, which
    is how the orchestrator migrates from hard-coded tool lists to
    managed, discoverable tools.

    ``access_token`` is the caller's raw Cognito JWT. When supplied it is
    forwarded to the Gateway as a Bearer token (identity passthrough); the
    tool calls then run under the user's identity, not a shared service key.
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
                headers=_gateway_headers(access_token),
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


def create_gateway_orchestrator_with_semantic_search(access_token: Optional[str] = None):
    """
    Create an orchestrator that discovers tools via Gateway semantic search.

    Instead of loading all tools into the agent's context (list_tools),
    this uses the x_amz_bedrock_agentcore_search tool to find relevant
    tools by natural language description at query time. This scales to
    hundreds or thousands of tools without bloating the agent's prompt.

    ``access_token`` is forwarded as a Bearer token (JWT passthrough) when
    supplied, so semantic discovery also runs under the caller's identity.

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
                headers=_gateway_headers(access_token),
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


def list_gateway_tools(access_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all tools registered in the AgentCore Gateway MCP server.

    ``access_token`` is forwarded as a Bearer token (JWT passthrough) when
    supplied. Against a JWT-protected Gateway, calling without a token returns
    [] (the call is rejected with 401) — which the Atelier panel renders as a
    "skipped / needs identity" state rather than failing the turn.

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
                headers=_gateway_headers(access_token),
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
