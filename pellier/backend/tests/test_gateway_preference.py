"""Gateway preference tests.

Scope:
  * Without ``AGENTCORE_GATEWAY_URL`` or a caller token there is no managed
    dispatcher, and the Gateway is never contacted.
  * The Gateway transport forwards the caller's bearer token.

We don't stand up a real MCP server here; this test covers selection and
transport headers.
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


def test_managed_dispatcher_is_absent_without_a_gateway_url():
    """With no AGENTCORE_GATEWAY_URL there is no managed dispatcher."""
    from services import agentcore_gateway
    from config import settings

    with patch.object(settings, "AGENTCORE_GATEWAY_URL", ""):
        assert agentcore_gateway.create_gateway_dispatcher(access_token="jwt") is None


def test_tokenless_managed_dispatcher_skips_network():
    """A CUSTOM_JWT Gateway is never contacted without caller identity."""
    from services import agentcore_gateway
    from config import settings

    with patch.object(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example/mcp"), \
         patch("strands.tools.mcp.mcp_client.MCPClient") as client_factory:
        result = agentcore_gateway.create_gateway_dispatcher()

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
