"""
AgentCore Gateway — MCP tool discovery via Bedrock AgentCore Gateway.

AgentCore Gateway (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
is a managed MCP front-door for tool catalogs. It enforces Cognito JWT
auth on every tool call, then proxies to registered Lambda or HTTP
targets. From the orchestrator's perspective, "having a Gateway" means
tool definitions stop living in Python imports and start being
discovered dynamically over the wire.

This module has two sides:

1. **Server side (local MCP adapter)** — exposes the complete 17-tool
   application catalog via MCP streamable HTTP for local development and
   contract tests. The managed AgentCore Gateway deliberately publishes the
   15-tool workshop subset from ``gateway_tool_schemas.workshop_published_tools``;
   it is not derived from this local catalog.

2. **Client side** — creates a Strands `Agent` that connects *back* to
   a Gateway URL and pulls its tool list at agent-construction time
   via `MCPClient.list_tools_sync()`. This is the production wiring:
   the agent prompt no longer carries a hard-coded tool list; the
   Gateway is the source of truth.

MCP (Model Context Protocol) docs: https://modelcontextprotocol.io
"""
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Sequence

from services.product_envelope import ProductExtractor

logger = logging.getLogger(__name__)


# === REFERENCE: START ===
# Expose the local 17-tool application catalog via MCP streamable HTTP so an
# external agent client can discover and invoke the same signatures and JSON
# envelopes used by the in-process orchestrator.
#
# The managed Gateway publishes a separate 15-tool workshop subset. This local
# catalog also contains ``issue_credit`` and ``get_ticket_history`` so the
# in-process application can model deferred operator capabilities without
# claiming that the managed Gateway serves them.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_gateway.py pellier/backend/services/agentcore_gateway.py

# Local MCP server catalog, in stable order. Tests assert discovery returns
# exactly this 17-tool set by exact name.
LOCAL_MCP_TOOL_NAMES: List[str] = [
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
]

# Published for the operator desk, never for a shopper-facing specialist. The
# Gateway serves these to any caller it lists them for, and Cedar decides per
# call, so the boundary that matters here is the binding: a specialist that
# names one of these would hand the model a money-moving tool and rely on a
# policy denial to catch it. The dispatcher refuses to build such a specialist.
GATEWAY_ONLY_OPERATOR_TOOLS: frozenset[str] = frozenset({"replace_damaged_item"})
STAFF_ONLY_GATEWAY_TOOLS: frozenset[str] = frozenset({"issue_credit"}) | GATEWAY_ONLY_OPERATOR_TOOLS


def assert_no_staff_only_binding(specialist: str, allowed_tools: Sequence[str]) -> None:
    """Refuse a shopper specialist that names a staff-only Gateway tool."""
    staff_only = sorted(set(allowed_tools) & STAFF_ONLY_GATEWAY_TOOLS)
    if staff_only:
        raise RuntimeError(
            f"{specialist} names staff-only Gateway tools: {', '.join(staff_only)}"
        )


# === WORKSHOP · Managed catalogue · support reconcile: START ===
# WORKSHOP_EXERCISE_STUB
#
# Task 3A. Theo's support-ticket request routes to the support specialist.
# On the managed rail the
# dispatcher asks the Gateway for exactly the tools named here and raises
# "Gateway is missing support tools: ..." when the Gateway does not publish one
# of them, so this tuple and the Gateway's published catalogue have to agree.
#
# Two decisions, both governance rather than plumbing:
#
#   1. SUPPORT_MANAGED_TOOLS must name only tools the Gateway publishes to a
#      shopper. Published is not the same as shopper-safe: compare this tuple
#      with the catalogue and with STAFF_ONLY_GATEWAY_TOOLS above. The
#      dispatcher refuses to build a specialist that names a staff-only tool.
#   2. SUPPORT_CALLER_BOUND_TOOLS names the tools whose `customer_id` the server
#      overwrites with the authenticated caller's id before execution. Which
#      support tool would otherwise let the model choose whose records to read?
#
# Verify in Task 3B: deploy, ask for Theo's support-ticket history in a new
# session, and inspect the bound customer and executed build. Direct Gateway
# probes separately check owned and foreign requests against Cedar.
SUPPORT_MANAGED_TOOLS: tuple[str, ...] = (
    "get_return_policy",
    "search_products",
    "initiate_return",
    "get_ticket_history",
    "issue_credit",
    "get_audit_trail",
    "escalate_to_human",
)
SUPPORT_CALLER_BOUND_TOOLS: frozenset[str] = frozenset()
# === WORKSHOP · Managed catalogue · support reconcile: END ===

MANAGED_SPECIALIST_TOOLS: Dict[str, tuple[str, ...]] = {
    "search": (
        "search_products",
        "browse_category",
        "compare_products",
        "get_related_products",
        "escalate_to_human",
    ),
    "recommendation": (
        "search_products_hybrid",
        "get_trending_products",
        "get_customer_preferences",
        "get_audit_trail",
        "compare_products",
        "browse_category",
        "escalate_to_human",
    ),
    "pricing": ("get_price_analysis", "browse_category", "search_products"),
    "inventory": ("check_inventory", "get_low_stock"),
    "support": SUPPORT_MANAGED_TOOLS,
}

_MANAGED_SPECIALIST_LABELS = {
    "search": "Search Agent",
    "recommendation": "Personalization Agent",
    "pricing": "Pricing Agent",
    "inventory": "Inventory Agent",
    "support": "Customer Service Agent",
}


def _runtime_or_app_setting(name: str, default: str = "") -> str:
    """Read Runtime env directly, loading full app settings only as fallback.

    AgentCore CodeZip excludes ``.env`` files, and the managed dispatcher does
    not connect to Aurora directly. Runtime-provided values must therefore be
    sufficient without constructing the database-bound application Settings.
    """
    if name in os.environ:
        return os.environ[name]

    from config import settings

    return str(getattr(settings, name, default) or default)


def _managed_specialist_prompt(
    specialist: str,
    *,
    turn_id: str = "",
    customer_id: str = "",
) -> str:
    """Return transport-neutral instructions for a Gateway-backed specialist."""
    label = _MANAGED_SPECIALIST_LABELS[specialist]
    prompt = (
        f"You are Pellier's {label}. "
        "Use at least one of the AgentCore Gateway tools available to you "
        "before answering. Treat tool output as the only source of catalog, "
        "inventory, pricing, customer, and execution facts. Never claim that "
        "an action succeeded unless the tool result reports success. Answer "
        "in 1-3 concise sentences without markdown tables or invented details."
    )
    if turn_id:
        prompt += (
            " For every Gateway tool call, include the exact audit correlation "
            f"argument turn_id={turn_id!r}. Do not invent, shorten, or reuse it."
        )
    if customer_id:
        prompt += (
            " The Runtime supplied the active workshop profile "
            f"customer_id={customer_id!r}. Use exactly this value when a "
            "customer-scoped read tool requires customer_id; do not infer or "
            "substitute another customer."
        )
    return prompt


# Capability tiers over the same 17 tools.
#
# One flat catalog publishes read, recommendation, inventory, escalation,
# restock, and return capabilities through a single discovery surface.
# Cedar still governs *execution*, but least-privilege becomes hard to
# teach and harder to verify when every tool is one undifferentiated list:
# "which of these can move money or stock?" has no structural answer.
#
# These tiers give that answer. They are the vocabulary the Policy lab and
# the fail-closed rule in ``services.execution_rail`` share, so a tool
# cannot be treated as a read in one place and a mutation in another.
#
# Tiers are declarative here rather than enforced as separate Gateway
# targets: splitting targets changes the provisioned topology, which the
# workshop's deploy scripts and readiness gates assert against. Semantic
# tool discovery over many targets stays an advanced scaling pattern, not
# the required path.
TIER_READ = "read"
TIER_CUSTOMER_MUTATION = "customer-mutation"
TIER_OPERATOR_MUTATION = "operator-mutation"
TIER_ESCALATION = "escalation"

GATEWAY_TOOL_TIERS: Dict[str, str] = {
    # Search and catalog reads. Safe for any authenticated shopper.
    "search_products": TIER_READ,
    "search_products_hybrid": TIER_READ,
    "get_trending_products": TIER_READ,
    "get_price_analysis": TIER_READ,
    "browse_category": TIER_READ,
    "compare_products": TIER_READ,
    "get_related_products": TIER_READ,
    "get_return_policy": TIER_READ,
    "get_customer_preferences": TIER_READ,
    "get_audit_trail": TIER_READ,
    # Inventory reads expose only the bounded workshop availability contract;
    # the stock mutation remains a separately denied operator capability.
    "check_inventory": TIER_READ,
    "get_low_stock": TIER_READ,
    # Writes the customer owns: a return against their own order.
    "initiate_return": TIER_CUSTOMER_MUTATION,
    # Writes only an operator may perform.
    "restock_inventory": TIER_OPERATOR_MUTATION,
    # Customer-scoped handoff instruction; no external ticket is created in
    # this workshop implementation.
    "escalate_to_human": TIER_ESCALATION,
    # Money movement. Most restrictive write tier.
    "issue_credit": TIER_OPERATOR_MUTATION,
    "get_ticket_history": TIER_READ,
}

# Tiers whose tools mutate state and therefore must travel the managed
# rail in the governed format. Kept as a derived value so adding a tool to
# a mutation tier automatically brings the fail-closed rule with it.
# TIER_ESCALATION is deliberately absent: escalate_to_human writes nothing
# (no products, no audit row, no external ticket — a pure UI handoff), and
# degraded storefront turns keep it as the honest fallback when a mutation
# is refused. Gating it would make degraded receipts claim a withheld
# capability that never mutates state.
MUTATION_TIERS = frozenset({TIER_CUSTOMER_MUTATION, TIER_OPERATOR_MUTATION})


# Which Gateway target publishes each tool.
#
# Cedar action ids embed this exact string: a policy naming
# ``pellier-concierge-experience-target___initiate_return`` matches only that
# target's tool. The provisioning source is ``scripts/deploy/
# gateway_tool_schemas.py``, which cannot be imported from the backend at
# runtime, so the map is stated here and
# ``tests/test_governed_execution.py`` asserts the two agree exactly. A silent
# copy would let a policy point at a target that no longer publishes the tool.
GATEWAY_TARGET_FOR_TOOL: Dict[str, str] = {
    "search_products": "pellier-discovery-search-target",
    "search_products_hybrid": "pellier-discovery-search-target",
    "browse_category": "pellier-discovery-search-target",
    "check_inventory": "pellier-discovery-search-target",
    "get_low_stock": "pellier-discovery-search-target",
    "restock_inventory": "pellier-discovery-search-target",
    "get_price_analysis": "pellier-value-pricing-target",
    "compare_products": "pellier-value-pricing-target",
    "get_customer_preferences": "pellier-curation-recommendation-target",
    "get_audit_trail": "pellier-curation-recommendation-target",
    "get_trending_products": "pellier-curation-recommendation-target",
    "get_return_policy": "pellier-curation-recommendation-target",
    "get_related_products": "pellier-curation-recommendation-target",
    "initiate_return": "pellier-concierge-experience-target",
    "issue_credit": "pellier-concierge-experience-target",
    "replace_damaged_item": "pellier-concierge-experience-target",
    "get_ticket_history": "pellier-concierge-experience-target",
    "escalate_to_human": "pellier-concierge-experience-target",
}


def gateway_action_id(tool_name: str) -> str:
    """The Gateway-qualified Cedar action id for a published tool."""
    target = GATEWAY_TARGET_FOR_TOOL.get(tool_name)
    if not target:
        raise KeyError(f"{tool_name} is not published through the Gateway")
    return f"{target}___{tool_name}"


def tool_tier(tool_name: str) -> str:
    """Return the capability tier for ``tool_name``.

    Args:
        tool_name: A published gateway tool name.

    Returns:
        The tier string. Unknown tools are treated as the most restrictive
        tier rather than the least: an unclassified tool is more likely a
        new mutation someone forgot to classify than a new read.
    """
    return GATEWAY_TOOL_TIERS.get(tool_name, TIER_OPERATOR_MUTATION)


def tools_in_tier(tier: str) -> List[str]:
    """Return the published tools in ``tier``, in catalog order."""
    return [name for name in LOCAL_MCP_TOOL_NAMES if tool_tier(name) == tier]


def mutation_tool_names() -> List[str]:
    """Return every published tool that mutates state, in catalog order."""
    return [
        name for name in LOCAL_MCP_TOOL_NAMES if tool_tier(name) in MUTATION_TIERS
    ]


def _logical_gateway_tool_name(name: str) -> str:
    """Strip the Gateway target prefix from a discovered MCP tool name."""
    if "___" in name:
        return name.rsplit("___", 1)[-1]
    if "__" in name:
        return name.rsplit("__", 1)[-1]
    return name


def _model_gateway_tools(tools: Sequence[Any]) -> list[Any]:
    """Give Bedrock short names while preserving Gateway execution identities.

    Gateway prefixes can push a name past Bedrock's 64-character limit.
    Strands' public name_override changes the model schema only; its MCP
    adapter still calls the original qualified name under the same JWT.
    Ambiguous aliases fail closed instead of selecting a different target.
    """
    from strands.tools.mcp.mcp_agent_tool import MCPAgentTool

    aliases: set[str] = set()
    adapted: list[Any] = []
    for tool in tools:
        name = _logical_gateway_tool_name(tool.mcp_tool.name)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise RuntimeError("Gateway tool cannot be represented by a valid Bedrock name")
        if name in aliases:
            raise RuntimeError(f"Gateway exposes an ambiguous logical tool: {name}")
        aliases.add(name)
        adapted.append(MCPAgentTool(
            tool.mcp_tool,
            tool.mcp_client,
            name_override=name,
            timeout=tool.timeout,
        ))
    return adapted


_SAFE_TOOL_INPUT_FIELDS = frozenset(
    {
        "category",
        "customer_id",
        "idempotency_key",
        "limit",
        "max_price",
        "min_rating",
        "persona",
        "product_id",
        "product_id_1",
        "product_id_2",
        "product_query",
        "quantity",
        "query",
        "reason",
        "turn_id",
        "warehouse_id",
    }
)
_CUSTOMER_SCOPED_TOOL_NAMES = frozenset(
    {
        "get_customer_preferences",
        "get_audit_trail",
        "initiate_return",
        "escalate_to_human",
    }
) | SUPPORT_CALLER_BOUND_TOOLS


def _bind_server_tool_context(
    tool_use: Dict[str, Any],
    *,
    customer_id: str,
    turn_id: str,
) -> Dict[str, Any]:
    """Bind server-owned identity and correlation arguments before execution."""
    bound = dict(tool_use)
    tool_input = dict(bound.get("input") or {})
    logical_name = _logical_gateway_tool_name(str(bound.get("name") or ""))

    if turn_id:
        tool_input["turn_id"] = turn_id
    if logical_name in _CUSTOMER_SCOPED_TOOL_NAMES:
        if not customer_id:
            raise ValueError(
                f"{logical_name} requires verified Aurora customer context"
            )
        tool_input["customer_id"] = customer_id
        tool_input.pop("persona", None)

    bound["input"] = tool_input
    return bound


def _safe_tool_input(tool_use: Dict[str, Any]) -> Dict[str, Any]:
    """Return only documented scalar tool arguments for inspection."""
    raw = tool_use.get("input")
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in _SAFE_TOOL_INPUT_FIELDS
        and isinstance(value, (str, int, float, bool))
    }


def _tool_result_values(result: Any) -> list[Any]:
    """Extract text or JSON values from a Strands ToolResult."""
    if not isinstance(result, dict):
        return []
    values: list[Any] = []
    for block in result.get("content", []):
        if isinstance(block, dict):
            if "text" in block:
                values.append(block["text"])
            elif "json" in block:
                values.append(block["json"])
        elif isinstance(block, str):
            values.append(block)
    return values


def _result_summary(result: Any, products: list[dict[str, Any]]) -> Dict[str, Any]:
    """Build a bounded observed-result summary without copying free-form output."""
    summary: Dict[str, Any] = {
        "product_count": len(products),
        "product_ids": [
            product["productId"]
            for product in products
            if product.get("productId") not in (None, "")
        ][:12],
    }
    for value in _tool_result_values(result):
        parsed = value
        if isinstance(value, str):
            try:
                import json

                parsed = json.loads(value)
            except (TypeError, ValueError):
                continue
        if not isinstance(parsed, dict):
            continue
        for key in ("status", "count", "success", "denied", "type"):
            if key in parsed and isinstance(parsed[key], (str, int, float, bool)):
                summary[key] = parsed[key]
        if "error" in parsed:
            summary["error"] = True
        break
    return summary


def _managed_specialist_spec(
    intent: str,
    *,
    turn_id: str = "",
    customer_id: str = "",
) -> tuple[str, str, tuple[str, ...]]:
    """Return specialist name, prompt, and allowed logical tools."""
    if intent == "customer_support":
        intent = "support"
    if intent not in MANAGED_SPECIALIST_TOOLS:
        intent = "support"

    return (
        intent,
        _managed_specialist_prompt(
            intent,
            turn_id=turn_id,
            customer_id=customer_id,
        ),
        MANAGED_SPECIALIST_TOOLS[intent],
    )


@dataclass
class ManagedGatewayDispatcher:
    """Run Pellier's deterministic dispatcher over managed Gateway tools."""

    access_token: str
    response_mode: str = "balanced"
    customer_id: str = ""
    routing_query: str = ""
    trace_attributes: Dict[str, str] | None = None
    last_intent: str = ""
    last_specialist: str = ""
    last_model_id: str = ""
    last_tool_names: tuple[str, ...] = ()
    last_tool_events: list[Dict[str, Any]] | None = None
    last_products: list[dict[str, Any]] | None = None

    def __call__(self, prompt: str) -> Any:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent
        from strands.tools.mcp.mcp_client import MCPClient
        from services.intent_router import classify_intent
        from services.response_mode import response_model_for_intent

        # Route on the current shopper request, not the bounded conversation
        # prompt. Prior turns can contain unrelated keywords and must not
        # change the current turn's deterministic intent.
        intent = classify_intent(self.routing_query or prompt)
        turn_id = str((self.trace_attributes or {}).get("turn.id") or "").strip()
        specialist, system_prompt, allowed_tools = _managed_specialist_spec(
            intent,
            turn_id=turn_id,
            customer_id=self.customer_id,
        )
        gateway_url = _runtime_or_app_setting("AGENTCORE_GATEWAY_URL")
        model_id, max_tokens, _ = response_model_for_intent(
            intent,
            self.response_mode,
        )
        if not gateway_url or not model_id:
            raise RuntimeError(
                "Managed dispatcher requires AGENTCORE_GATEWAY_URL and a "
                "configured specialist model"
            )

        # Captured on this thread: the transport factory runs on Strands'
        # background thread, where no span is current.
        trace_context = _current_trace_context()

        def _create_transport():
            return _gateway_streamable_http_transport(
                gateway_url,
                self.access_token,
                trace_context=trace_context,
            )

        assert_no_staff_only_binding(specialist, allowed_tools)
        mcp_client = MCPClient(_create_transport)
        mcp_client.start()
        try:
            discovered = mcp_client.list_tools_sync()
            selected = [
                tool
                for tool in discovered
                if _logical_gateway_tool_name(tool.tool_name) in allowed_tools
            ]
            selected_names = tuple(
                _logical_gateway_tool_name(tool.tool_name) for tool in selected
            )
            missing = sorted(set(allowed_tools) - set(selected_names))
            if missing:
                raise RuntimeError(
                    f"Gateway is missing {specialist} tools: {', '.join(missing)}"
                )

            agent = Agent(
                name=specialist,
                model=BedrockModel(
                    model_id=model_id,
                    max_tokens=max_tokens,
                ),
                system_prompt=system_prompt,
                tools=_model_gateway_tools(selected),
            )
            tool_events: list[Dict[str, Any]] = []
            products: list[dict[str, Any]] = []
            started_by_id: Dict[str, float] = {}

            def before_tool(event: BeforeToolCallEvent) -> None:
                tool_use = event.tool_use
                try:
                    bound_tool_use = _bind_server_tool_context(
                        tool_use,
                        customer_id=self.customer_id,
                        turn_id=turn_id,
                    )
                except ValueError as exc:
                    event.cancel_tool = str(exc)
                    return
                # Strands retains the original dict after the hook returns, so
                # update it in place instead of replacing only event.tool_use.
                tool_use.clear()
                tool_use.update(bound_tool_use)
                tool_use_id = str(tool_use.get("toolUseId") or "")
                if tool_use_id:
                    started_by_id[tool_use_id] = time.monotonic()

            def after_tool(event: AfterToolCallEvent) -> None:
                tool_use = event.tool_use
                tool_use_id = str(tool_use.get("toolUseId") or "")
                tool_name = _logical_gateway_tool_name(
                    str(tool_use.get("name") or "unknown")
                )
                observed_products: list[dict[str, Any]] = []
                for value in _tool_result_values(event.result):
                    observed_products.extend(ProductExtractor.extract(value))
                existing = {
                    str(product.get("productId") or product.get("name"))
                    for product in products
                }
                for product in observed_products:
                    identity = str(product.get("productId") or product.get("name"))
                    if identity and identity not in existing:
                        products.append(product)
                        existing.add(identity)
                started = started_by_id.pop(tool_use_id, None)
                duration_ms = (
                    int((time.monotonic() - started) * 1000)
                    if started is not None
                    else None
                )
                status = (
                    "error"
                    if event.exception is not None
                    else str((event.result or {}).get("status") or "success")
                )
                tool_events.append(
                    {
                        "id": tool_use_id,
                        "tool": tool_name,
                        "status": status,
                        "duration_ms": duration_ms,
                        "input": _safe_tool_input(tool_use),
                        "result": _result_summary(event.result, observed_products),
                    }
                )

            agent.add_hook(before_tool)
            agent.add_hook(after_tool)
            if self.trace_attributes:
                agent.trace_attributes = {
                    **self.trace_attributes,
                    "pellier.intent": intent,
                    "pellier.specialist": specialist,
                    "pellier.response_mode": self.response_mode,
                    "gen_ai.request.model": model_id,
                    "shopper.customer_id": self.customer_id or "anonymous",
                }

            self.last_intent = intent
            self.last_specialist = specialist
            self.last_model_id = model_id
            self.last_tool_names = selected_names
            response = agent(prompt)
            self.last_tool_events = tool_events
            self.last_products = products
            return response
        finally:
            _stop_mcp_client(mcp_client)


def create_gateway_dispatcher(
    access_token: Optional[str] = None,
    response_mode: str = "balanced",
    customer_id: Optional[str] = None,
    routing_query: str = "",
) -> ManagedGatewayDispatcher | None:
    """Create the managed equivalent of Pellier dispatcher."""
    if not _runtime_or_app_setting("AGENTCORE_GATEWAY_URL") or not access_token:
        return None
    from services.response_mode import normalize_response_mode

    return ManagedGatewayDispatcher(
        access_token=access_token,
        response_mode=normalize_response_mode(response_mode),
        customer_id=str(customer_id or "").strip(),
        routing_query=routing_query,
    )


def _unwrap_strands_tool(strands_tool: Any) -> Any:
    """Return the plain Python callable underneath a Strands `@tool` wrapper.

    Strands' `@tool` produces a `DecoratedFunctionTool` whose original
    callable is exposed via the standard `__wrapped__` attribute. FastMCP
    needs the underlying function (with its signature and docstring) to
    derive the MCP input schema, so we reach through the decorator here.
    """
    return getattr(strands_tool, "__wrapped__", strands_tool)


def build_mcp_server(name: str = "pellier-gateway") -> Any:
    """Build a FastMCP server registering the local 17-tool catalog.

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

    # Register each of the 17 tools by name. We pass the unwrapped function
    # (not the Strands DecoratedFunctionTool) so FastMCP can introspect the
    # signature and docstring to generate the MCP input schema.
    for tool_name in LOCAL_MCP_TOOL_NAMES:
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


def _current_trace_context() -> Any:
    """The OpenTelemetry context on the calling thread, or ``None``.

    Strands runs the MCP transport on a background thread where no span is
    current, so the context has to be captured here, on the thread that owns
    the turn, and handed to the transport explicitly.
    """
    try:
        from opentelemetry import context as otel_context

        return otel_context.get_current()
    except Exception:  # pragma: no cover - OTEL API absent
        return None


def _inject_trace_context(headers: Dict[str, str], trace_context: Any) -> None:
    """Add a W3C ``traceparent`` for the captured context, if it holds a span.

    This is what lets a Gateway or Lambda span join the same trace as the
    Runtime invocation instead of starting a fresh one. Without a span the
    propagator writes nothing, so the headers stay exactly as before.
    """
    if trace_context is None:
        return
    try:
        from opentelemetry import propagate

        propagate.inject(headers, context=trace_context)
    except Exception as exc:  # pragma: no cover - propagation is best effort
        logger.debug("Gateway trace context not injected: %s", exc)


def _gateway_headers(
    access_token: Optional[str] = None,
    *,
    trace_context: Any = None,
) -> Dict[str, str]:
    """Build the auth headers for an MCP call to the AgentCore Gateway.

    The Gateway is deployed with a Cognito CUSTOM_JWT authorizer, so the
    production path is **JWT passthrough**: the caller's raw Cognito access
    token is sent as ``Authorization: Bearer <token>`` and the Gateway
    validates it against the Cognito discovery URL, so every tool call
    carries the user's identity end to end.

    When no token is provided (anonymous turns or local development against a
    Gateway deployed with ``authorizerType=NONE``), this returns the legacy
    placeholder ``x-api-key`` header. The governed Runtime never uses that
    path: it requires a bearer token before constructing this client.
    """
    if access_token:
        headers = {"Authorization": f"Bearer {access_token}"}
    else:
        headers = {
            "x-api-key": _runtime_or_app_setting("AGENTCORE_GATEWAY_API_KEY")
        }
    _inject_trace_context(headers, trace_context)
    return headers


@asynccontextmanager
async def _gateway_streamable_http_transport(
    gateway_url: str,
    access_token: Optional[str] = None,
    trace_context: Any = None,
):
    """Open the current MCP streamable-HTTP transport with caller identity."""
    import httpx
    from mcp.client.streamable_http import streamable_http_client

    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(
        headers=_gateway_headers(access_token, trace_context=trace_context),
        timeout=timeout,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            gateway_url,
            http_client=http_client,
        ) as transport:
            yield transport


def _stop_mcp_client(mcp_client: Any) -> None:
    """Close the pinned Strands MCP client with its context-exit contract."""
    mcp_client.stop(None, None, None)


def create_gateway_orchestrator(access_token: Optional[str] = None):
    """Create a Strands Agent that discovers tools via an MCP Gateway URL.

    When `settings.AGENTCORE_GATEWAY_URL` is unset, returns None. Builders
    callers may retain local execution; the governed Runtime treats None as
    ``managed_gateway_unavailable`` and fails closed. When set, the returned
    agent pulls tools from the remote Gateway using streamable HTTP.

    ``access_token`` is the caller's raw Cognito JWT. When supplied it is
    forwarded to the Gateway as a Bearer token (identity passthrough); the
    tool calls then run under the user's identity, not a shared service key.
    """
    gateway_url = _runtime_or_app_setting("AGENTCORE_GATEWAY_URL")
    if not gateway_url:
        logger.info("AGENTCORE_GATEWAY_URL not set — gateway disabled")
        return None
    if not access_token:
        logger.info("Gateway orchestrator requires verified caller identity")
        return None

    try:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.tools.mcp.mcp_client import MCPClient
        model_id = _runtime_or_app_setting("BEDROCK_ROUTER_MODEL")

        def _create_transport():
            return _gateway_streamable_http_transport(
                gateway_url,
                access_token,
            )

        mcp_client = MCPClient(_create_transport)

        orchestrator = Agent(
            model=BedrockModel(
                model_id=model_id,
                max_tokens=4096,
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
            gateway_url,
        )
        return orchestrator

    except ImportError as e:
        logger.warning("MCP dependencies not installed: %s", e)
        return None
    except Exception as e:
        logger.warning("Gateway orchestrator setup failed: %s", e)
        return None
# === REFERENCE: END ===


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
    gateway_url = _runtime_or_app_setting("AGENTCORE_GATEWAY_URL")
    if not gateway_url:
        logger.info("AGENTCORE_GATEWAY_URL not set — semantic search disabled")
        return None
    if not access_token:
        logger.info(
            "Gateway semantic search requires verified caller identity"
        )
        return None

    try:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.tools.mcp.mcp_client import MCPClient
        model_id = _runtime_or_app_setting("BEDROCK_ROUTER_MODEL")

        def _create_transport():
            return _gateway_streamable_http_transport(
                gateway_url,
                access_token,
            )

        mcp_client = MCPClient(_create_transport)

        # The agent uses x_amz_bedrock_agentcore_search to find tools
        # by description rather than loading all tools into its prompt.
        # This is the production pattern for large tool catalogs.
        orchestrator = Agent(
            model=BedrockModel(
                model_id=model_id,
                max_tokens=4096,
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
    [] (the call is rejected with 401) — which the Observatory panel renders as a
    "skipped / needs identity" state rather than failing the turn.

    Returns a list of tool descriptors with name, description, and input schema.
    """
    gateway_url = _runtime_or_app_setting("AGENTCORE_GATEWAY_URL")
    if not gateway_url or not access_token:
        return []

    try:
        from strands.tools.mcp.mcp_client import MCPClient

        def _create_transport():
            return _gateway_streamable_http_transport(
                gateway_url,
                access_token,
            )

        mcp_client = MCPClient(_create_transport)
        mcp_client.start()

        try:
            tools = []
            for tool in mcp_client.list_tools_sync():
                tools.append({
                    "name": tool.tool_name,
                    "description": tool.tool_spec.get("description", ""),
                    "input_schema": tool.tool_spec.get("inputSchema", {}).get("json", {}),
                })
            return tools
        finally:
            _stop_mcp_client(mcp_client)

    except ImportError:
        logger.warning("MCP dependencies not installed")
        return []
    except Exception as e:
        logger.warning(f"Failed to list gateway tools: {e}")
        return []
