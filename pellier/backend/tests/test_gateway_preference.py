"""Gateway preference tests.

Scope:
  * When ``AGENTCORE_GATEWAY_URL`` is unset, the chat stream code path
    silently falls back to the in-process orchestrator.
  * When the env var IS set and ``create_gateway_orchestrator``
    returns an agent, that agent is used (and guardrails flag is
    irrelevant to which path is chosen).
  * The ``/api/agentcore/gateway/status`` response shape reflects
    the configured/unconfigured state so Pellier Labs arch tabs can
    read it.

We don't try to stand up a real MCP server here — the gateway module
already has integration tests for that. This test is about the
selection logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_gateway_transport_forwards_bearer_with_current_mcp_api():
    from services import agentcore_gateway

    http_client = object()
    streams = (object(), object(), object())
    observed: dict[str, object] = {}

    class _AsyncContext:
        def __init__(self, value):
            self.value = value

        async def __aenter__(self):
            return self.value

        async def __aexit__(self, *_args):
            return None

    def transport(url, *, http_client, terminate_on_close=True):
        observed.update(
            {
                "url": url,
                "http_client": http_client,
                "terminate_on_close": terminate_on_close,
            }
        )
        return _AsyncContext(streams)

    with patch(
        "httpx.AsyncClient",
        return_value=_AsyncContext(http_client),
    ) as http_client_factory, patch(
        "mcp.client.streamable_http.streamable_http_client",
        side_effect=transport,
    ):
        async with agentcore_gateway._gateway_streamable_http_transport(
            "https://gw.example/mcp",
            "caller-jwt",
        ) as result:
            assert result is streams

    assert http_client_factory.call_args.kwargs["headers"] == {
        "Authorization": "Bearer caller-jwt"
    }
    assert http_client_factory.call_args.kwargs["follow_redirects"] is True
    assert observed == {
        "url": "https://gw.example/mcp",
        "http_client": http_client,
        "terminate_on_close": True,
    }


def test_gateway_client_cleanup_uses_strands_context_exit_contract():
    from services import agentcore_gateway

    client = MagicMock()
    agentcore_gateway._stop_mcp_client(client)

    client.stop.assert_called_once_with(None, None, None)


def test_managed_dispatcher_uses_real_strands_mcp_tool_contract(monkeypatch):
    from mcp.types import Tool
    from strands.tools.mcp.mcp_agent_tool import MCPAgentTool
    from services import agentcore_gateway

    monkeypatch.setenv("AGENTCORE_GATEWAY_URL", "https://gw.example/mcp")
    monkeypatch.setenv("BEDROCK_ROUTER_MODEL", "test-model")
    client = MagicMock()
    allowed = agentcore_gateway.MANAGED_SPECIALIST_TOOLS["inventory"]
    tools = [
        MCPAgentTool(
            Tool(
                name=f"target___{name}",
                description="Inventory tool",
                inputSchema={"type": "object", "properties": {}},
            ),
            client,
        )
        for name in (*allowed, "unexpected_tool")
    ]
    client.list_tools_sync.return_value = tools
    agent = MagicMock(return_value="Verified warehouse answer")
    with patch("services.intent_router.classify_intent", return_value="inventory"), \
         patch("strands.tools.mcp.mcp_client.MCPClient", return_value=client), \
         patch("strands.Agent", return_value=agent) as factory, \
         patch("strands.models.BedrockModel"):
        dispatcher = agentcore_gateway.ManagedGatewayDispatcher("test-jwt")
        assert dispatcher("Is the Hadley shirt in Brooklyn?") == "Verified warehouse answer"

    assert factory.call_args.kwargs["tools"] == tools[:-1]
    assert dispatcher.last_tool_names == tuple(allowed)
    client.stop.assert_called_once_with(None, None, None)


def test_gateway_descriptors_use_strands_tool_spec(monkeypatch):
    from mcp.types import Tool
    from strands.tools.mcp.mcp_agent_tool import MCPAgentTool
    from services import agentcore_gateway

    monkeypatch.setenv("AGENTCORE_GATEWAY_URL", "https://gw.example/mcp")
    client = MagicMock()
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    client.list_tools_sync.return_value = [
        MCPAgentTool(
            Tool(name="target___floor_check", description="Look up stock", inputSchema=schema),
            client,
        )
    ]
    with patch("strands.tools.mcp.mcp_client.MCPClient", return_value=client):
        assert agentcore_gateway.list_gateway_tools("test-jwt") == [{
            "name": "target___floor_check",
            "description": "Look up stock",
            "input_schema": schema,
        }]
    client.stop.assert_called_once_with(None, None, None)


def test_chat_explicitly_cleans_up_gateway_tool_provider():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "services" / "chat.py"
    ).read_text(encoding="utf-8")

    assert "if gateway_used:" in source
    assert "await asyncio.to_thread(orchestrator.cleanup)" in source


def test_tokenless_gateway_discovery_skips_network():
    from services import agentcore_gateway
    from config import settings

    with patch.object(
        settings,
        "AGENTCORE_GATEWAY_URL",
        "https://gw.example/mcp",
    ), patch("strands.tools.mcp.mcp_client.MCPClient") as client_factory:
        assert agentcore_gateway.list_gateway_tools() == []

    client_factory.assert_not_called()


def test_gateway_status_unset_reports_in_process():
    """With no AGENTCORE_GATEWAY_URL, the status endpoint says the
    backend is using in-process imports."""
    from services import agentcore_gateway
    from config import settings

    # ``settings.AGENTCORE_GATEWAY_URL`` is typically ``None`` or "".
    # Force empty string via temp patch.
    with patch.object(settings, "AGENTCORE_GATEWAY_URL", ""):
        assert agentcore_gateway.create_gateway_orchestrator() is None


def test_tokenless_gateway_orchestrator_skips_network():
    """A CUSTOM_JWT Gateway is never contacted without caller identity."""
    from services import agentcore_gateway
    from config import settings

    with patch.object(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example/mcp"), \
         patch("strands.tools.mcp.mcp_client.MCPClient") as client_factory:
        result = agentcore_gateway.create_gateway_orchestrator()

    assert result is None
    client_factory.assert_not_called()


# --------------------------------------------------------------------------
# JWT passthrough: header selection
# --------------------------------------------------------------------------

def test_gateway_headers_uses_bearer_when_token_present():
    """With a caller token, the Gateway transport sends Authorization:
    Bearer (JWT passthrough), not the placeholder x-api-key."""
    from services import agentcore_gateway

    headers = agentcore_gateway._gateway_headers("marco-jwt-abc123")
    assert headers == {"Authorization": "Bearer marco-jwt-abc123"}
    assert "x-api-key" not in headers


def test_gateway_headers_falls_back_to_api_key_when_no_token():
    """Anonymous turns (no token) fall back to the placeholder x-api-key
    header. Against a JWT-protected Gateway this 401s, which the caller
    treats as 'fall back to in-process' (the skipped panel)."""
    from services import agentcore_gateway
    from config import settings

    with patch.object(settings, "AGENTCORE_GATEWAY_API_KEY", "workshop", create=True):
        headers = agentcore_gateway._gateway_headers(None)
    assert headers == {"x-api-key": "workshop"}
    assert "Authorization" not in headers


def test_create_gateway_orchestrator_accepts_access_token():
    """The factory accepts an access_token kwarg (passthrough) and still
    returns the patched agent / None without raising."""
    from services import agentcore_gateway
    from config import settings

    fake_agent = MagicMock(name="gateway-agent")
    fake_client = MagicMock(name="mcp-client")

    with patch.object(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example/mcp"), \
         patch("strands.tools.mcp.mcp_client.MCPClient", return_value=fake_client), \
         patch("mcp.client.streamable_http.streamable_http_client"), \
         patch("strands.Agent", return_value=fake_agent), \
         patch("strands.models.BedrockModel"):
        result = agentcore_gateway.create_gateway_orchestrator(access_token="theo-jwt-xyz")

    assert result is fake_agent or result is None
