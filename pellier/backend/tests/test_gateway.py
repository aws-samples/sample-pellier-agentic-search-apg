"""Tests for `services.agentcore_gateway` (Module 3 — Challenge 7).

Covers Requirement 2.5.3 and 2.2.3 from
`.kiro/specs/pellier-storefront/requirements.md`:

  * 2.5.3 — The Gateway challenge block exposes the agent tools via MCP
    streamable HTTP transport so an external client can discover and
    invoke them.
  * 2.2.3 — Tool names match `workshop-content.md` steering exactly.

No live Gateway, no Bedrock, no network. The MCP server is driven
in-process through FastMCP's `list_tools` / `call_tool` surface (same
code path a streamable-HTTP client hits on the server side) and
`BusinessLogic` is stubbed so `whats_trending` returns a
deterministic payload.

Run from the repo root per `pytest.ini`:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_gateway.py -v
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

import pytest

import services.agent_tools as agent_tools
import services.agentcore_gateway as gateway
import services.business_logic as business_logic_module


# ---------------------------------------------------------------------------
# Exact 13-tool list from `.kiro/steering/coding-standards.md` and
# `workshop-content.md` (Req 2.2.3). The gateway MUST discover exactly
# these names.
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = {
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
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _SentinelDB:
    """Opaque placeholder — the stubbed BusinessLogic ignores it."""


@pytest.fixture
def trending_payload() -> Dict[str, Any]:
    """Same shape `agent_tools.whats_trending` would emit."""
    return {
        "status": "success",
        "count": 3,
        "products": [
            {
                "productId": 1,
                "product_description": "Italian Linen Camp Shirt — Sand",
                "price": 128.0,
                "stars": 4.8,
                "reviews": 420,
                "category_name": "Linen",
                "quantity": 12,
                "trending_score": 2016.0,
            },
            {
                "productId": 2,
                "product_description": "Sundress in Washed Linen — Golden Ochre",
                "price": 148.0,
                "stars": 4.9,
                "reviews": 310,
                "category_name": "Dresses",
                "quantity": 8,
                "trending_score": 1519.0,
            },
            {
                "productId": 3,
                "product_description": "Signature Straw Tote — Natural",
                "price": 68.0,
                "stars": 4.7,
                "reviews": 280,
                "category_name": "Accessories",
                "quantity": 15,
                "trending_score": 1316.0,
            },
        ],
        "metadata": {
            "criteria": "reviews * stars, min 4.0 stars, min 50 reviews",
            "limit": 5,
            "category_filter": None,
        },
    }


@pytest.fixture(autouse=True)
def reset_agent_tools_globals():
    """Snapshot and restore agent_tools module globals per test."""
    saved_db = agent_tools._db_service
    saved_loop = agent_tools._main_loop
    yield
    agent_tools._db_service = saved_db
    agent_tools._main_loop = saved_loop


class _StubBusinessLogic:
    """Drop-in replacement that returns a canned trending payload."""

    def __init__(self, db_service: Any, *, payload: Optional[Dict[str, Any]] = None) -> None:
        self._db = db_service
        self._payload = payload

    async def whats_trending(
        self, limit: int = 5, category: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = dict(self._payload or {})
        metadata = dict(payload.get("metadata", {}))
        metadata["limit"] = limit
        metadata["category_filter"] = category
        payload["metadata"] = metadata
        return payload


def _install_stub_business_logic(
    monkeypatch: pytest.MonkeyPatch, payload: Dict[str, Any]
) -> None:
    def factory(db_service: Any) -> _StubBusinessLogic:
        return _StubBusinessLogic(db_service, payload=payload)

    monkeypatch.setattr(business_logic_module, "BusinessLogic", factory)


def _run(coro):
    """Run a coroutine to completion on a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Req 2.2.3 + 2.5.3 — Discovery returns all 13 tools by exact name
# ---------------------------------------------------------------------------


def test_build_mcp_server_returns_fastmcp_with_streamable_http_app() -> None:
    """The gateway SHALL build an MCP server with a streamable HTTP app."""
    server = gateway.build_mcp_server()

    # The returned object is FastMCP and must expose the streamable_http_app
    # entry point (the transport required by Req 2.5.3).
    assert hasattr(server, "list_tools")
    assert hasattr(server, "call_tool")
    assert hasattr(server, "streamable_http_app")

    # The ASGI app must be constructible so external clients can mount it.
    app = gateway.get_streamable_http_app()
    assert callable(app)  # Starlette apps are ASGI callables


def test_discovery_returns_exactly_the_thirteen_tools_by_exact_name() -> None:
    """Discovery SHALL return the 13 tools the Atelier Tools surface ships."""
    server = gateway.build_mcp_server()

    tools = _run(server.list_tools())

    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES, (
        f"Gateway discovery drift. "
        f"Missing: {EXPECTED_TOOL_NAMES - names}. "
        f"Unexpected: {names - EXPECTED_TOOL_NAMES}."
    )
    # Exactly 13 — five Style Advisor, two Curator, one Value Analyst,
    # three Stock Keeper, two Experience Guide.
    assert len(tools) == 13


def test_each_discovered_tool_exposes_an_input_schema() -> None:
    """Each MCP tool must carry a JSON input schema for client invocation."""
    server = gateway.build_mcp_server()

    tools = _run(server.list_tools())

    for tool in tools:
        # FastMCP derives the schema from the wrapped Python signature; the
        # MCP spec names the field `inputSchema`.
        schema = getattr(tool, "inputSchema", None)
        assert schema is not None, f"Tool {tool.name} missing inputSchema"
        assert schema.get("type") == "object", (
            f"Tool {tool.name} inputSchema is not an object: {schema}"
        )


# ---------------------------------------------------------------------------
# Req 2.5.3 — MCP invocation of whats_trending returns the same
# JSON envelope as the in-process @tool call.
# ---------------------------------------------------------------------------


def _invoke_in_process(**kwargs: Any) -> str:
    """Invoke the Strands @tool directly (bypassing the decorator wrapper)."""
    fn = getattr(
        agent_tools.whats_trending, "__wrapped__",
        agent_tools.whats_trending,
    )
    return fn(**kwargs)


def test_mcp_invocation_matches_in_process_tool_envelope(
    monkeypatch: pytest.MonkeyPatch, trending_payload: Dict[str, Any]
) -> None:
    """Invoking whats_trending via the gateway SHALL produce the
    same JSON envelope as calling the in-process @tool directly.
    """
    agent_tools._db_service = _SentinelDB()
    agent_tools._main_loop = None  # force the asyncio.new_event_loop fallback
    _install_stub_business_logic(monkeypatch, trending_payload)

    # Baseline: the in-process @tool response
    in_process_json = _invoke_in_process(limit=5, category=None)
    in_process_parsed = json.loads(in_process_json)

    # Gateway build + invoke via FastMCP (the same object served over
    # streamable HTTP; an external client would get the identical result).
    server = gateway.build_mcp_server()
    tool = server._tool_manager.get_tool("whats_trending")
    assert tool is not None, "whats_trending was not registered"

    # Call the registered function the way FastMCP would, without MCP
    # content-block conversion, so we can compare JSON envelopes directly.
    mcp_result = tool.fn(limit=5, category=None)
    mcp_parsed = json.loads(mcp_result)

    # Same JSON shape (Req 2.5.3 / task 2.7 "same JSON shape as the
    # in-process call").
    assert mcp_parsed == in_process_parsed
    assert mcp_parsed["status"] == "success"
    assert len(mcp_parsed["products"]) == 3


def test_mcp_invocation_through_call_tool_returns_valid_json_envelope(
    monkeypatch: pytest.MonkeyPatch, trending_payload: Dict[str, Any]
) -> None:
    """Invoking via FastMCP's call_tool (the streamable-HTTP code path)
    SHALL surface the same JSON envelope the in-process tool produces.
    """
    import threading

    agent_tools._db_service = _SentinelDB()
    _install_stub_business_logic(monkeypatch, trending_payload)

    server = gateway.build_mcp_server()

    # Production layout: uvicorn owns a "main" loop where DB coroutines
    # live. The Strands @tool bridges sync→async via `_run_async`, which
    # submits its coroutine back to that main loop via
    # `run_coroutine_threadsafe`. Mirror the layout with a dedicated
    # background-thread loop registered as the main loop so the bridge has
    # somewhere to dispatch work while FastMCP's sync invocation runs on
    # the test's foreground loop.
    main_loop = asyncio.new_event_loop()
    loop_ready = threading.Event()

    def _run_main_loop() -> None:
        asyncio.set_event_loop(main_loop)
        loop_ready.set()
        main_loop.run_forever()

    thread = threading.Thread(target=_run_main_loop, daemon=True)
    thread.start()
    loop_ready.wait()

    try:
        agent_tools._main_loop = main_loop
        raw = _run(
            server._tool_manager.call_tool(
                "whats_trending",
                {"limit": 5},
                context=None,
                convert_result=False,
            )
        )
    finally:
        main_loop.call_soon_threadsafe(main_loop.stop)
        thread.join(timeout=5)
        main_loop.close()

    assert isinstance(raw, str)
    parsed = json.loads(raw)
    # FastMCP may double-encode the JSON string when the Python function
    # returns `str`; tolerate one extra round of decoding so the assertion
    # targets the same envelope the in-process @tool emits.
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    assert parsed["status"] == "success"
    assert parsed["count"] == 3
    # Limit and category flow through to BusinessLogic unchanged, just like
    # the in-process tool asserts in test_agent_tools.py.
    assert parsed["metadata"]["limit"] == 5
    assert parsed["metadata"]["category_filter"] is None


# ---------------------------------------------------------------------------
# Sanity: the public tool-name constant exported by the gateway matches the
# expected set. Keeps the constant in sync with `workshop-content.md` so any
# drift is caught at the contract layer, not just behaviourally.
# ---------------------------------------------------------------------------


def test_gateway_tool_names_constant_matches_expected() -> None:
    assert set(gateway.GATEWAY_TOOL_NAMES) == EXPECTED_TOOL_NAMES
    assert len(gateway.GATEWAY_TOOL_NAMES) == 13
