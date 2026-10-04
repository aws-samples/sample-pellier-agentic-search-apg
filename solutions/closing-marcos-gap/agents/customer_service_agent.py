"""
Customer Service Agent — Pellier's customer support agent. Handles return
policies, troubleshooting, and general post-purchase questions.

Exposes two surfaces that share one agent construction path:

1. ``build_support_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Observatory Graph pattern.
2. ``support(query)`` — ``@tool`` wrapper used by the Observatory's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: the factory and tool keep generic names because the
Storefront dispatcher's intent classifier emits 'support' as a keyword.

Exa MCP integration was removed in the three-patterns refactor. It
was unset in every workshop environment (EXA_API_KEY blank in
``.env.example``), forced the factory pattern to be inconsistent,
and isn't part of the workshop's teaching surface. The specialist
now runs purely against the local tool set.
"""
import json
import logging
from strands import Agent, tool
from strands.models import BedrockModel
from services.agent_tools import (
    escalate_to_human,
    search_products,
    initiate_return,
    get_return_policy,
    get_audit_trail,
    get_ticket_history,
    get_customer_preferences,
)
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.specialist_models import specialist_model

logger = logging.getLogger(__name__)


_SUPPORT_SYSTEM_PROMPT = (
    "You are Pellier's customer service specialist. You handle post-purchase "
    "questions: return policies, care instructions, and processing actual "
    "returns when a customer's piece arrived damaged or wasn't right.\n"
    "\n"
    "Tools, in order of typical use:\n"
    "  - search_products: when the customer names a product, call this first "
    "to get the integer productId and category. Returns are keyed on "
    "productId and care guidance is keyed on category, so you need both "
    "before the next tool.\n"
    "  - get_return_policy: return window + care guidance by category. "
    "Use for 'how long do I have to return X' or 'how do I take care of Y'.\n"
    "  - initiate_return: actually write the return. Required args: "
    "customer_id, product_id (integer), reason (one of 'damaged', "
    "'wrong_size', 'not_as_described', 'changed_mind', 'other'). The "
    "call also requires a stable idempotency_key for the intended return. The "
    "tool accepts that canonical set; SQL enforces that the customer "
    "must have ordered the product. If reason='damaged', the catalog "
    "quantity decrements by 1 in the same transaction.\n"
    "  - get_ticket_history: read the customer's past support tickets before "
    "answering, so a returning client is never asked to repeat what already "
    "happened. Use it when the message refers to a previous issue ('this "
    "happened last time too', 'I wrote in about this'), or before proposing a "
    "second remedy for the same piece. Read-only.\n"
    "  - get_customer_preferences: read the client's saved sizes, fits, and "
    "material preferences when an exchange or replacement only makes sense if "
    "it matches what they actually wear. Read-only, and never a substitute for "
    "asking about the damaged piece itself.\n"
    "  - get_audit_trail: read the latest pellier.tool_audit receipt when "
    "the shopper or operator asks whether the return/write was recorded, "
    "which caller rail ran, or how to inspect the governed proof. This is "
    "read-only; it does not process a return.\n"
    "  - escalate_to_human: the honest escape hatch, routed to a human "
    "stylist. Use ONLY when initiate_return cannot handle the case at all — "
    "Cedar rejected the reason, the customer doesn't own the product, the "
    "window has closed, or the shopper is in distress and deserves a real "
    "person. Always try get_return_policy + initiate_return first. Pass a "
    "one-sentence reason explaining what's being routed and why.\n"
    "    Do NOT use escalate_to_human for a return that simply needs operator "
    "confirmation. That is a different situation, handled below, and the "
    "stylist channel is the wrong destination for it.\n"
    "\n"
    "Output discipline:\n"
    "  - ALWAYS call a tool before writing prose. No greeting, no preamble.\n"
    "  - After the tool returns, write 1–2 sentences. Conversational, not "
    "transactional. Empathy first when a piece arrived damaged; clarity "
    "when a customer is asking what's possible.\n"
    "  - No markdown tables, no numbered lists, no emojis, no follow-up "
    "questions to the customer.\n"
    "  - When initiate_return succeeds, name the action concretely "
    "('I've filed the return for the Wabi-Sabi Bowl') so the customer "
    "knows the write actually happened.\n"
    "\n"
    "<operator-review-boundary>"
    "Some returns cannot be completed from this conversation. When "
    "initiate_return comes back with error='managed_rail_required', the "
    "return needs a Pellier operator to confirm it before anything changes. "
    "This is NOT a failure, NOT a policy refusal, and NOT your mistake — it "
    "is the boundary working as designed.\n"
    "\n"
    "In that case, say two things and nothing more:\n"
    "  1. that you found the specific order and prepared the request, naming "
    "the piece;\n"
    "  2. that a Pellier operator will confirm it before anything is "
    "changed.\n"
    "\n"
    "For example: 'I found your Wabi-Sabi Bowl order and prepared the "
    "damaged-return request. A Pellier operator will confirm the return "
    "before anything is changed.'\n"
    "\n"
    "You must NOT say, imply, or hedge toward any of these, because none of "
    "them has happened: the return was filed, created, or processed; a refund "
    "or credit was issued; a replacement was sent; a policy approved it; an "
    "operator already confirmed it. Do not promise a timeframe you cannot "
    "know. Do not offer to complete it yourself if the shopper asks again.\n"
    "\n"
    "Never show the shopper the words 'managed_rail_required', 'gateway-mcp', "
    "'Cedar', 'policy mode', 'rail', or a tool name. They are internal. The "
    "shopper hears that their request is prepared and a person will confirm "
    "it.\n"
    "</operator-review-boundary>"
)

# ``_SUPPORT_AGENT_STUBBED`` — legacy flag still read by chat routing; Observatory
# lists Customer Service Agent as shipped in ``agents.json``.
_SUPPORT_AGENT_STUBBED = False


def _ensure_products_in_output(text: str, tool_results: list) -> str:
    """If the LLM output lacks a JSON products block, extract from tool results and append.

    Suppression rule: if any tool result has the shape of a successful
    ``initiate_return`` (status == "success" with a "return_id" field),
    do NOT attach product cards. Customer Service Agent chains
    ``search_products`` upstream of ``initiate_return`` solely to resolve
    "Wabi-Sabi Bowl" → integer product_id; the products it finds are
    plumbing for the write, not recommendations the customer wants
    rendered as cards alongside a damage-return confirmation.
    """
    all_products = []
    return_completed = False
    for result_str in tool_results:
        try:
            data = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            if data.get("status") == "success" and "return_id" in data:
                return_completed = True
                continue
            if "products" in data:
                all_products.extend(data["products"])
        elif isinstance(data, list):
            all_products.extend(data)

    if return_completed:
        return text

    if all_products:
        from agents.specialist_hooks import forward_or_append_products
        return forward_or_append_products(text, all_products)
    return text


def build_support_agent() -> Agent:
    """Return a configured Customer Support specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. A persona-aware preamble lets queries like
    "can I return the camp shirt I bought?" ground in the shopper's
    actual order history; both injections are no-ops for anonymous
    sessions.
    """
    # Customer Service Agent — Claude Opus 5. Opus for tone when handling a
    # return. Bedrock rejects the deprecated temperature field for this
    # model, so we rely on the model default.
    model_id, max_tokens = specialist_model("opus")
    return Agent(
        name="support",
        model=BedrockModel(
            model_id=model_id,
            max_tokens=max_tokens,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_SUPPORT_SYSTEM_PROMPT)
        ),
        tools=[
            get_return_policy,
            search_products,
            initiate_return,
            get_ticket_history,
            get_customer_preferences,
            get_audit_trail,
            escalate_to_human,
        ],
    )


@tool
def support(query: str) -> str:
    """
    Handle customer support queries including return policies and troubleshooting.

    Args:
        query: Customer support question or request

    Returns:
        Agent response with support information and optional product data
    """
    try:
        tool_results = []
        agent = build_support_agent()

        # Capture inner tool results so we can guarantee product data in output
        try:
            from strands.hooks.events import AfterToolCallEvent

            def capture_result(event: AfterToolCallEvent):
                if hasattr(event, 'result') and event.result:
                    raw = event.result
                    if isinstance(raw, dict) and 'content' in raw:
                        for block in raw.get('content', []):
                            if isinstance(block, dict) and 'text' in block:
                                tool_results.append(block['text'])

            agent.add_hook(capture_result)
        except ImportError:
            pass

        from agents.specialist_hooks import (
            append_escalation_marker,
            extract_escalation_payload,
        )

        result = agent(query)
        text = str(result)
        # Surface any inner escalate_to_human payload back to the
        # orchestrator-facing string so chat.py can render the stylist
        # handoff card. Without this the inner tool result gets buried
        # inside the inner Agent and the outer SSE stream never sees
        # the {"type": "escalation"} envelope.
        escalation = extract_escalation_payload(tool_results)
        if escalation is not None:
            return append_escalation_marker(text, escalation)
        return _ensure_products_in_output(text, tool_results)
    except Exception as e:
        return json.dumps({"error": f"Support agent error: {str(e)}"})
