"""
AgentCore Gateway — MCP tool discovery via Bedrock AgentCore Gateway.

AgentCore Gateway (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
is a managed MCP front-door for tool catalogs. It enforces Cognito JWT
auth on every tool call, then proxies to registered Lambda or HTTP
targets. From the orchestrator's perspective, "having a Gateway" means
tool definitions stop living in Python imports and start being
discovered dynamically over the wire.

The Gateway publishes Pellier's nine store tools on one target,
``pellier-store-tools`` (``scripts/deploy/gateway_tool_schemas.py``). This
module is the client side: the managed Router builds the routed agent over the
tools it discovers through ``MCPClient.list_tools_sync()``, so the Gateway, not
a Python import, is the source of the agent's tools.

MCP (Model Context Protocol) docs: https://modelcontextprotocol.io
"""
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Sequence

from services.product_envelope import ProductExtractor, select_products_for_reply

logger = logging.getLogger(__name__)


# === REFERENCE: START ===
# The managed Router: one agent per routed intent, over the tools the Gateway
# publishes to the caller.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_gateway.py pellier/backend/services/agentcore_gateway.py

# Published for the Operator, never for a shopper-facing agent. The Gateway
# serves it to any caller it lists it for, and Cedar decides per call, so the
# boundary that matters here is the binding: an agent that named it would hand
# the model a money-moving tool and rely on a policy denial to catch it. The
# Router refuses to build such an agent.
STAFF_ONLY_GATEWAY_TOOLS: frozenset[str] = frozenset({"give_store_credit"})


def assert_no_staff_only_binding(specialist: str, allowed_tools: Sequence[str]) -> None:
    """Refuse a shopper agent that names a staff-only Gateway tool."""
    staff_only = sorted(set(allowed_tools) & STAFF_ONLY_GATEWAY_TOOLS)
    if staff_only:
        raise RuntimeError(
            f"{specialist} names staff-only Gateway tools: {', '.join(staff_only)}"
        )


# === WORKSHOP - Managed catalogue - support reconcile: START ===
# WORKSHOP_EXERCISE_STUB
#
# Task 3A. Theo's support-ticket request routes to the Support agent. On the
# managed rail the Router asks the Gateway for exactly the tools named here.
# A tool the Gateway does not publish is left out: the agent tells Theo it
# can't look up his support tickets here, and the Builder view names the tool
# as not published. This tuple and the Gateway's published catalogue have to
# agree.
#
# SUPPORT_CALLER_BOUND_TOOLS names the tools whose `customer_id` the server
# overwrites with the authenticated caller's id before execution. `get_orders`
# is bound below, outside this region. Which other support tool would let the
# model choose whose records to read?
#
# Verify in Task 3B: deploy, ask for Theo's support-ticket history in a new
# session, and inspect the bound customer and executed build. Direct Gateway
# probes separately check owned and foreign requests against Cedar.
SUPPORT_MANAGED_TOOLS: tuple[str, ...] = (
    "get_orders",
    "get_return_policy",
    "get_tickets",
    "ask_a_person",
)
SUPPORT_CALLER_BOUND_TOOLS: frozenset[str] = frozenset()
# === WORKSHOP - Managed catalogue - support reconcile: END ===

MANAGED_SPECIALIST_TOOLS: Dict[str, tuple[str, ...]] = {
    "shopping": (
        "search_products",
        "browse_department",
        "compare_products",
        "ask_a_person",
    ),
    "stock": ("check_stock",),
    "support": SUPPORT_MANAGED_TOOLS,
}


# What each managed tool looks up, in the words an agent says when the
# Gateway does not publish it.
_TOOL_LOOKUPS: Dict[str, str] = {
    "search_products": "products",
    "browse_department": "a department's products",
    "compare_products": "product comparisons",
    "check_stock": "warehouse stock",
    "get_orders": "orders",
    "get_return_policy": "return policies",
    "get_tickets": "support tickets",
    "ask_a_person": "a person to hand this to",
}


def unpublished_tools_prompt(unpublished: Sequence[str]) -> str:
    """The instruction an agent gets for the tools the Gateway does not publish.

    The agent must say plainly that it cannot look the thing up here, never
    guess it and never claim a look-up it did not make.
    """
    lookups = ", ".join(_TOOL_LOOKUPS.get(name, name) for name in unpublished)
    return (
        " The Gateway does not publish these tools, so they are not available to "
        f"you: {', '.join(unpublished)}. If the shopper asks for {lookups}, say "
        f"plainly that you can't look up {lookups} here. Do not guess or invent them. "
        "Offer ask_a_person if it is available."
    )


def unpublished_tools_note(agent: str, unpublished: Sequence[str]) -> str:
    """The Builder view's line for tools the routed agent asked for and was not given."""
    names = ", ".join(unpublished)
    one = len(unpublished) == 1
    return (f"{names} {'is' if one else 'are'} not published on the Gateway, "
            f"so the {agent} ran without {'it' if one else 'them'}")


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
    skills: Sequence[Any] = (),
) -> str:
    """Return transport-neutral instructions for a Gateway-backed agent.

    ``skills`` are the agent's fixed skills, appended to the prompt exactly as
    the in-process agent carries them: the deployed agent is the same agent.
    """
    from services.specialist_models import agent_name
    from skills import inject_skills

    prompt = (
        f"You are Pellier's {agent_name(specialist)}. "
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
            "customer-scoped tool requires customer_id; do not infer or "
            "substitute another customer."
        )
    if specialist == "shopping":
        prompt += (
            " Pass the shopper's requirements to search_products and "
            "browse_department as arguments, never as words in the query: a "
            "budget as max_price in dollars, a request for what is available as "
            "in_stock_only=true, and anything they ruled out as exclusions, a "
            "list of those words, including limits the shopper stated earlier "
            "in this conversation. The database enforces them as filters."
        )
    return inject_skills(prompt, skills)


# Capability tiers over the nine published tools.
#
# These tiers answer "which of these can move money?" structurally. They are
# the vocabulary the Policy lab and the fail-closed rule in
# ``services.execution_rail`` share, so a tool cannot be treated as a read in
# one place and a mutation in another.
TIER_READ = "read"
TIER_OPERATOR_MUTATION = "operator-mutation"
TIER_ESCALATION = "escalation"

GATEWAY_TOOL_TIERS: Dict[str, str] = {
    "search_products": TIER_READ,
    "browse_department": TIER_READ,
    "compare_products": TIER_READ,
    "check_stock": TIER_READ,
    "get_orders": TIER_READ,
    "get_return_policy": TIER_READ,
    "get_tickets": TIER_READ,
    # Money movement, written only for a review a person approved.
    "give_store_credit": TIER_OPERATOR_MUTATION,
    # A handoff. It changes no business data; a credit request opens a request
    # with no amount for a person, which is workflow state, not a write the
    # shopper owns.
    "ask_a_person": TIER_ESCALATION,
}

# Tiers whose tools mutate state and therefore must travel the managed rail in
# the governed format. Derived, so adding a tool to a mutation tier brings the
# fail-closed rule with it.
MUTATION_TIERS = frozenset({TIER_OPERATOR_MUTATION})

# The one Gateway target that publishes every tool. Cedar action ids embed it:
# a policy naming ``pellier-store-tools___give_store_credit`` matches only that
# target's tool. The provisioning source is ``scripts/deploy/
# gateway_tool_schemas.py``, which the backend cannot import at runtime, so the
# map is stated here and the Gateway catalogue tests assert the two agree.
GATEWAY_TARGET = "pellier-store-tools"
GATEWAY_TARGET_FOR_TOOL: Dict[str, str] = {name: GATEWAY_TARGET for name in GATEWAY_TOOL_TIERS}


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
    return [name for name in GATEWAY_TOOL_TIERS if tool_tier(name) == tier]


def mutation_tool_names() -> List[str]:
    """Return every published tool that mutates state, in catalog order."""
    return [name for name in GATEWAY_TOOL_TIERS if tool_tier(name) in MUTATION_TIERS]


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
        "amount_cents",
        "build_fingerprint",
        "category",
        "credit_request",
        "customer_id",
        "department",
        "exclusions",
        "idempotency_key",
        "in_stock_only",
        "limit",
        "max_price",
        "min_rating",
        "product_id_1",
        "product_id_2",
        "product_query",
        "query",
        "reason",
        "turn_id",
    }
)
# Tools whose `customer_id` the server binds to the verified caller before
# execution, and that cannot run without one. Lab 3A adds the support read the
# starter leaves unbound.
_CUSTOMER_SCOPED_TOOL_NAMES = frozenset({"get_orders"}) | SUPPORT_CALLER_BOUND_TOOLS
# The handoff is bound to the caller when the caller is known and still runs
# when nobody is signed in: anyone may ask for a person. The local rail does the
# same (`store_tools.ask_a_person` completes the handoff and withholds only the
# credit review), so a model-chosen customer is dropped rather than trusted.
_CUSTOMER_BOUND_WHEN_KNOWN_TOOL_NAMES = frozenset({"ask_a_person"})


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
    # The build that makes the call, from the package's own fingerprint. The
    # server sets it; a value the model supplied is never kept.
    tool_input.pop("build_fingerprint", None)
    build = os.environ.get("PELLIER_BUILD_FINGERPRINT", "").strip()
    if build:
        tool_input["build_fingerprint"] = build
    if logical_name in _CUSTOMER_SCOPED_TOOL_NAMES:
        if not customer_id:
            raise ValueError(
                f"{logical_name} requires verified Aurora customer context"
            )
        tool_input["customer_id"] = customer_id
    elif logical_name in _CUSTOMER_BOUND_WHEN_KNOWN_TOOL_NAMES:
        if customer_id:
            tool_input["customer_id"] = customer_id
        else:
            tool_input.pop("customer_id", None)

    bound["input"] = tool_input
    return bound


# The only shape a customer id takes. A model string that does not match it is
# never emitted as evidence; the verdict still records that another customer
# was asked for.
_CUSTOMER_ID_PATTERN = re.compile(r"^CUST-[A-Z0-9-]{1,40}$")


def _requested_customer_id(value: Any) -> Optional[str]:
    """The model's requested customer id when it has the ``CUST-`` shape, else None."""
    candidate = str(value or "").strip().upper()
    return candidate if _CUSTOMER_ID_PATTERN.fullmatch(candidate) else None


def _customer_scope(tool_use: Dict[str, Any], customer_id: str) -> Dict[str, Any]:
    """Record who chose a call's customer, read before the server binds it.

    A caller-bound tool's ``customer_id`` is overwritten by the server, so the
    executed call alone cannot show whether the server or the model chose it.
    The verdict travels on the tool event with the customer the model asked
    for and the one the server bound, so the Builder view can show both.
    ``binding`` on this rail is ``overwritten`` (the model named another
    customer and the server replaced it), ``matched`` (it named the verified
    one) or ``bound`` (it named none). This rail never refuses a mismatch; it
    corrects it before the Gateway sees the call.
    """
    logical_name = _logical_gateway_tool_name(str(tool_use.get("name") or ""))
    requested = (tool_use.get("input") or {}).get("customer_id")
    if logical_name in _CUSTOMER_SCOPED_TOOL_NAMES | _CUSTOMER_BOUND_WHEN_KNOWN_TOOL_NAMES:
        scope = "server"
    elif requested:
        scope = "model"
    else:
        return {}
    requested_id = _requested_customer_id(requested)
    other = bool(requested) and requested_id != customer_id
    if scope == "server":
        binding = "overwritten" if other else ("matched" if requested else "bound")
        bound = customer_id or None
    else:
        binding = "unbound"
        bound = None
    return {
        "customer_scope": scope,
        "requested_other_customer": other,
        "requested_customer": requested_id,
        "bound_customer": bound,
        "binding": binding,
    }


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _safe_tool_input(tool_use: Dict[str, Any]) -> Dict[str, Any]:
    """Return only documented tool arguments for inspection: scalars, and lists of them.

    ``exclusions`` is a list, so a browse or search step would otherwise show
    its budget and stock limits but never what the shopper ruled out.
    """
    raw = tool_use.get("input")
    if not isinstance(raw, dict):
        return {}
    safe: Dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _SAFE_TOOL_INPUT_FIELDS:
            continue
        if _is_scalar(value):
            safe[key] = value
        elif isinstance(value, list) and all(_is_scalar(item) for item in value):
            safe[key] = list(value)
    return safe


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


def _finding_for(tool_name: str, result: Any, status: str) -> str:
    """One plain line from the full tool result, by the shared template."""
    from services.turn_steps import ERROR_FINDINGS, finding_for, parse_result

    if status == "error":
        return ERROR_FINDINGS.get(tool_name, "This check did not complete")
    for value in _tool_result_values(result):
        return finding_for(tool_name, parse_result(value))
    return finding_for(tool_name, {})


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
) -> tuple[str, str, tuple[str, ...], list[Dict[str, Any]]]:
    """Return the routed agent's intent, prompt, allowed logical tools and skills.

    The skills are the fixed set the prompt was built with, as the receipt the
    Runtime reports, so what the Builder view shows is what the prompt carried.
    An older bundle with no skill files reports an empty list.
    """
    from skills import skill_receipt, skills_for

    if intent not in MANAGED_SPECIALIST_TOOLS:
        raise ValueError(f"The Router returned an unknown intent: {intent!r}")

    skills = skills_for(intent)
    return (
        intent,
        _managed_specialist_prompt(
            intent,
            turn_id=turn_id,
            customer_id=customer_id,
            skills=skills,
        ),
        MANAGED_SPECIALIST_TOOLS[intent],
        skill_receipt(intent, "fixed") if skills else [],
    )


@dataclass
class ManagedGatewayDispatcher:
    """Run Pellier's deterministic Router over managed Gateway tools."""

    access_token: str
    customer_id: str = ""
    routing_query: str = ""
    trace_attributes: Dict[str, str] | None = None
    last_intent: str = ""
    last_specialist: str = ""
    last_model_id: str = ""
    last_tool_names: tuple[str, ...] = ()
    # Tools the routed agent asked the Gateway for and was not given.
    last_unpublished_tools: tuple[str, ...] = ()
    last_tool_events: list[Dict[str, Any]] | None = None
    last_products: list[dict[str, Any]] | None = None
    # The skills the routed agent's prompt carried, as the Runtime reports them.
    last_skills: list[Dict[str, Any]] | None = None

    def __call__(self, prompt: str) -> Any:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent
        from strands.tools.mcp.mcp_client import MCPClient
        from services.intent_router import classify_intent
        from services.specialist_models import model_for_intent

        # Route on the current shopper request, not the bounded conversation
        # prompt. Prior turns can contain unrelated keywords and must not
        # change the current turn's deterministic intent.
        intent = classify_intent(self.routing_query or prompt)
        turn_id = str((self.trace_attributes or {}).get("turn.id") or "").strip()
        specialist, system_prompt, allowed_tools, skills = _managed_specialist_spec(
            intent,
            turn_id=turn_id,
            customer_id=self.customer_id,
        )
        gateway_url = _runtime_or_app_setting("AGENTCORE_GATEWAY_URL")
        model_id, max_tokens = model_for_intent(intent)
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
            # A tool the Gateway does not publish is not an error: the agent
            # runs without it, says plainly what it cannot look up, and the
            # Builder view names the tool (Lab 3's starter shows this).
            unpublished = tuple(sorted(set(allowed_tools) - set(selected_names)))
            if unpublished:
                logger.warning(
                    "Gateway does not publish %s tools: %s", specialist, ", ".join(unpublished)
                )
                system_prompt += unpublished_tools_prompt(unpublished)
            self.last_unpublished_tools = unpublished

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
            owned_products: list[dict[str, Any]] = []
            started_by_id: Dict[str, float] = {}
            scope_by_id: Dict[str, Dict[str, Any]] = {}

            def before_tool(event: BeforeToolCallEvent) -> None:
                tool_use = event.tool_use
                scope = _customer_scope(tool_use, self.customer_id)
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
                    if scope:
                        scope_by_id[tool_use_id] = scope

            def after_tool(event: AfterToolCallEvent) -> None:
                tool_use = event.tool_use
                tool_use_id = str(tool_use.get("toolUseId") or "")
                tool_name = _logical_gateway_tool_name(
                    str(tool_use.get("name") or "unknown")
                )
                observed_products: list[dict[str, Any]] = []
                for value in _tool_result_values(event.result):
                    observed_products.extend(ProductExtractor.extract(value))
                    if tool_name == "get_orders" and event.exception is None:
                        if isinstance(value, str):
                            import json

                            try:
                                value = json.loads(value)
                            except (TypeError, ValueError):
                                continue
                        if (
                            isinstance(value, dict)
                            and value.get("status") == "success"
                            and value.get("customer_id") == self.customer_id
                            and isinstance(value.get("orders"), list)
                        ):
                            owned_products.extend(
                                order for order in value["orders"]
                                if isinstance(order, dict)
                            )
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
                safe_input = _safe_tool_input(tool_use)
                tool_events.append(
                    {
                        "id": tool_use_id,
                        "tool": tool_name,
                        "status": status,
                        "duration_ms": duration_ms,
                        "input": safe_input,
                        "result": _result_summary(event.result, observed_products),
                        # The same template the in-process rail uses, computed
                        # here beside the Gateway from the full result the
                        # Runtime never sends back.
                        "finding": _finding_for(tool_name, event.result, status),
                        **scope_by_id.pop(tool_use_id, {}),
                    }
                )

            agent.add_hook(before_tool)
            agent.add_hook(after_tool)
            if self.trace_attributes:
                agent.trace_attributes = {
                    **self.trace_attributes,
                    "pellier.intent": intent,
                    "pellier.specialist": specialist,
                    "gen_ai.request.model": model_id,
                    "shopper.customer_id": self.customer_id or "anonymous",
                }

            self.last_intent = intent
            self.last_specialist = specialist
            self.last_model_id = model_id
            self.last_tool_names = selected_names
            self.last_skills = skills
            response = agent(prompt)
            self.last_tool_events = tool_events
            self.last_products = select_products_for_reply(
                str(response), products, owned_products=owned_products,
            )
            return response
        finally:
            _stop_mcp_client(mcp_client)


def create_gateway_dispatcher(
    access_token: Optional[str] = None,
    customer_id: Optional[str] = None,
    routing_query: str = "",
) -> ManagedGatewayDispatcher | None:
    """Create the managed equivalent of Pellier's Router."""
    if not _runtime_or_app_setting("AGENTCORE_GATEWAY_URL") or not access_token:
        return None
    return ManagedGatewayDispatcher(
        access_token=access_token,
        customer_id=str(customer_id or "").strip(),
        routing_query=routing_query,
    )


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


# === REFERENCE: END ===



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
