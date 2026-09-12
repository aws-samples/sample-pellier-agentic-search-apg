"""Tests for `services.agentcore_gateway`.

  * The Gateway challenge block exposes the agent tools via MCP
    streamable HTTP transport so an external client can discover and
    invoke them.
  * Tool names match the application registry exactly.

No live Gateway, no Bedrock, no network. The MCP server is driven
in-process through FastMCP's `list_tools` / `call_tool` surface (same
code path a streamable-HTTP client hits on the server side) and
`BusinessLogic` is stubbed so `get_trending_products` returns a
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
# Exact 15-tool application contract. The gateway MUST discover exactly these
# names.
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = {
    "search_products",
    "search_products_hybrid",
    "get_trending_products",
    "get_price_analysis",
    "browse_category",
    "check_inventory",
    "get_low_stock",
    "restock_inventory",
    "compare_products",
    "get_return_policy",
    "get_related_products",
    "initiate_return",
    "get_customer_preferences",
    "get_audit_trail",
    "escalate_to_human",
    "issue_credit",
    "get_ticket_history",
}


def test_managed_specialists_partition_the_gateway_catalog() -> None:
    expected = {
        "search",
        "recommendation",
        "pricing",
        "inventory",
        "support",
    }
    assert set(gateway.MANAGED_SPECIALIST_TOOLS) == expected
    for specialist, names in gateway.MANAGED_SPECIALIST_TOOLS.items():
        assert names, f"{specialist} has no managed Gateway tools"
        assert set(names) <= EXPECTED_TOOL_NAMES


@pytest.mark.parametrize(
    ("published", "logical"),
    [
        ("initiate_return", "initiate_return"),
        ("experience-target__initiate_return", "initiate_return"),
        ("experience-target___initiate_return", "initiate_return"),
    ],
)
def test_logical_gateway_tool_name_strips_target_prefix(
    published: str, logical: str
) -> None:
    assert gateway._logical_gateway_tool_name(published) == logical


@pytest.mark.parametrize(
    ("name", "model_input", "expected_input"),
    [
        (
            "recommendation-target___get_customer_preferences",
            {
                "customer_id": "CUST-THEO",
                "persona": "theo",
                "turn_id": "turn-model-value",
                "limit": 3,
            },
            {"limit": 3},
        ),
        (
            "recommendation-target___get_audit_trail",
            {
                "customer_id": "CUST-THEO",
                "turn_id": "turn-model-value",
                "session_id": "session-theo",
                "tool_name": "initiate_return",
            },
            {"session_id": "session-theo", "tool_name": "initiate_return"},
        ),
    ],
)
def test_server_context_overrides_model_identity_and_correlation(
    name: str, model_input: Dict[str, Any], expected_input: Dict[str, Any]
) -> None:
    bound = gateway._bind_server_tool_context(
        {
            "name": name,
            "toolUseId": "call-1",
            "input": model_input,
        },
        customer_id="CUST-MARCO",
        turn_id="turn-" + ("a" * 32),
    )

    assert bound["input"] == {
        "customer_id": "CUST-MARCO",
        "turn_id": "turn-" + ("a" * 32),
        **expected_input,
    }


def test_customer_scoped_tool_requires_verified_customer_context() -> None:
    with pytest.raises(ValueError, match="verified Aurora customer context"):
        gateway._bind_server_tool_context(
            {
                "name": "experience-target___initiate_return",
                "toolUseId": "call-2",
                "input": {"product_id": 21, "reason": "damaged"},
            },
            customer_id="",
            turn_id="turn-" + ("b" * 32),
        )


def test_non_customer_tool_still_receives_server_turn_id() -> None:
    bound = gateway._bind_server_tool_context(
        {
            "name": "search-target___search_products_hybrid",
            "toolUseId": "call-3",
            "input": {"query": "linen", "turn_id": "untrusted"},
        },
        customer_id="CUST-MARCO",
        turn_id="turn-" + ("c" * 32),
    )

    assert bound["input"] == {
        "query": "linen",
        "turn_id": "turn-" + ("c" * 32),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _SentinelDB:
    """Opaque placeholder — the stubbed BusinessLogic ignores it."""


@pytest.fixture
def trending_payload() -> Dict[str, Any]:
    """Same shape `agent_tools.get_trending_products` would emit."""
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

    async def get_trending_products(
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
# Req 2.2.3 + 2.5.3 — Discovery returns all 17 tools by exact name
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


def test_discovery_returns_exactly_the_published_tools_by_exact_name() -> None:
    """Discovery SHALL return the 17 tools the Observatory Tools surface ships."""
    server = gateway.build_mcp_server()

    tools = _run(server.list_tools())

    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES, (
        f"Gateway discovery drift. "
        f"Missing: {EXPECTED_TOOL_NAMES - names}. "
        f"Unexpected: {names - EXPECTED_TOOL_NAMES}."
    )
    # Exactly 15 — the original shopper/tool surface plus two read-only
    # proof tools.
    assert len(tools) == 17


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
# Req 2.5.3 — MCP invocation of get_trending_products returns the same
# JSON envelope as the in-process @tool call.
# ---------------------------------------------------------------------------


def _invoke_in_process(**kwargs: Any) -> str:
    """Invoke the Strands @tool directly (bypassing the decorator wrapper)."""
    fn = getattr(
        agent_tools.get_trending_products, "__wrapped__",
        agent_tools.get_trending_products,
    )
    return fn(**kwargs)


def test_mcp_invocation_matches_in_process_tool_envelope(
    monkeypatch: pytest.MonkeyPatch, trending_payload: Dict[str, Any]
) -> None:
    """Invoking get_trending_products via the gateway SHALL produce the
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
    tool = server._tool_manager.get_tool("get_trending_products")
    assert tool is not None, "get_trending_products was not registered"

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
                "get_trending_products",
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
# expected set. Keeps the constant in sync with the application contract so any
# drift is caught at the contract layer, not just behaviourally.
# ---------------------------------------------------------------------------


def test_local_mcp_tool_names_constant_matches_expected() -> None:
    assert set(gateway.LOCAL_MCP_TOOL_NAMES) == EXPECTED_TOOL_NAMES
    assert len(gateway.LOCAL_MCP_TOOL_NAMES) == 17


def test_gateway_tool_names_are_read_through_the_strands_tool_interface() -> None:
    """Strands 1.48's ``MCPAgentTool`` exposes ``tool_name`` and ``tool_spec``, not ``name``.

    The venv tests never build a real ``MCPAgentTool``, so a ``tool.name`` read
    passes every local test and raises ``AttributeError`` on the first managed
    turn. Both the live dispatcher and the Lab 3b twin are pinned to the
    interface the installed SDK actually has.
    """
    from pathlib import Path

    from strands.tools.mcp.mcp_agent_tool import MCPAgentTool

    assert hasattr(MCPAgentTool, "tool_name") and hasattr(MCPAgentTool, "tool_spec")
    assert not hasattr(MCPAgentTool, "name")
    backend = Path(__file__).resolve().parents[1]
    for path in (
        backend / "services" / "agentcore_gateway.py",
        backend.parents[1] / "solutions" / "the-ledger" / "services" / "agentcore_gateway.py",
    ):
        source = path.read_text()
        assert "tool.name" not in source, f"{path.name} reads MCPAgentTool.name"
        assert "tool.tool_name" in source


@pytest.mark.parametrize("staff_tool", ["issue_credit", "replace_damaged_item"])
def test_a_shopper_specialist_may_not_bind_a_staff_only_gateway_tool(staff_tool: str) -> None:
    """A tool published for human-approved remedies cannot be bound to a shopper agent."""
    from services import agentcore_gateway as gateway_module

    gateway_module.assert_no_staff_only_binding("search", ["search_products", "compare_products"])
    with pytest.raises(RuntimeError, match=f"staff-only Gateway tools: {staff_tool}"):
        gateway_module.assert_no_staff_only_binding("support", ["get_return_policy", staff_tool])
    assert staff_tool not in gateway_module.SUPPORT_CALLER_BOUND_TOOLS
    assert gateway_module.STAFF_ONLY_GATEWAY_TOOLS == frozenset({"issue_credit", "replace_damaged_item"})
