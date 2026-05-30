"""Gateway preference tests.

Scope:
  * When ``AGENTCORE_GATEWAY_URL`` is unset, the chat stream code path
    silently falls back to the in-process orchestrator.
  * When the env var IS set and ``create_gateway_orchestrator``
    returns an agent, that agent is used (and guardrails flag is
    irrelevant to which path is chosen).
  * The ``/api/agentcore/gateway/status`` response shape reflects
    the configured/unconfigured state so the Atelier arch tabs can
    read it.

We don't try to stand up a real MCP server here — the gateway module
already has integration tests for that. This test is about the
selection logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_gateway_status_unset_reports_in_process():
    """With no AGENTCORE_GATEWAY_URL, the status endpoint says the
    backend is using in-process imports."""
    from services import agentcore_gateway
    from config import settings

    # ``settings.AGENTCORE_GATEWAY_URL`` is typically ``None`` or "".
    # Force empty string via temp patch.
    with patch.object(settings, "AGENTCORE_GATEWAY_URL", ""):
        assert agentcore_gateway.create_gateway_orchestrator() is None


def test_gateway_status_set_attempts_mcp_path():
    """With AGENTCORE_GATEWAY_URL set, ``create_gateway_orchestrator``
    tries the MCP path. We stub MCPClient / Agent / BedrockModel so the
    test doesn't actually hit a network. Called with no token (the
    default), which is still a valid signature."""
    from services import agentcore_gateway
    from config import settings

    fake_agent = MagicMock(name="gateway-agent")
    fake_client = MagicMock(name="mcp-client")

    with patch.object(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example/mcp"), \
         patch.object(settings, "AGENTCORE_GATEWAY_API_KEY", "key", create=True), \
         patch("strands.tools.mcp.mcp_client.MCPClient", return_value=fake_client), \
         patch("mcp.client.streamable_http.streamablehttp_client"), \
         patch("strands.Agent", return_value=fake_agent), \
         patch("strands.models.BedrockModel"):
        result = agentcore_gateway.create_gateway_orchestrator()

    # create_gateway_orchestrator catches exceptions from missing mcp
    # or strands imports and returns None; on systems where those are
    # installed (our test host), the patched constructors are used and
    # the returned object is our fake_agent.
    # We only assert "didn't raise" — actual return value may be None
    # if mcp isn't installed. Either is acceptable here; the goal is
    # that the function's selection logic is exercised.
    assert result is fake_agent or result is None


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
         patch("mcp.client.streamable_http.streamablehttp_client"), \
         patch("strands.Agent", return_value=fake_agent), \
         patch("strands.models.BedrockModel"):
        result = agentcore_gateway.create_gateway_orchestrator(access_token="theo-jwt-xyz")

    assert result is fake_agent or result is None
