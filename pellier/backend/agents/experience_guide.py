"""
Experience Guide — Pellier's customer support agent. Handles return
policies, troubleshooting, and general post-purchase questions.

Exposes two surfaces that share one agent construction path:

1. ``build_support_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and Pellier Labs Graph pattern.
2. ``support(query)`` — ``@tool`` wrapper used by Pellier Labs'
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
    escalate_to_stylist,
    find_pieces,
    process_return,
    returns_and_care,
    trace_receipt,
)
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.response_mode import resolve_specialist_model

logger = logging.getLogger(__name__)


_SUPPORT_SYSTEM_PROMPT = (
    "You are Pellier's Experience Guide. You handle post-purchase "
    "questions: return policies, care instructions, and processing actual "
    "returns when a customer's piece arrived damaged or wasn't right.\n"
    "\n"
    "Tools, in order of typical use:\n"
    "  - find_pieces: when the customer names a product, call this first "
    "to get the integer productId and category. Returns are keyed on "
    "productId and care guidance is keyed on category, so you need both "
    "before the next tool.\n"
    "  - returns_and_care: return window + supported care guidance. After "
    "find_pieces resolves a named item, pass both its category and exact name "
    "to this tool. Use for 'how long do I have to return X' or 'how do I "
    "take care of Y'.\n"
    "  - process_return: actually write the return. Required args: "
    "customer_id, product_id (integer), reason (one of 'damaged', "
    "'wrong_size', 'not_as_described', 'changed_mind', 'other'). The "
    "tool accepts that canonical set; SQL enforces that the customer "
    "must have ordered the product. If reason='damaged', the catalog "
    "quantity decrements by 1 in the same transaction.\n"
    "  - trace_receipt: read the latest pellier.tool_audit receipt when "
    "the shopper or operator asks whether the return/write was recorded, "
    "which caller rail ran, or how to inspect the governed proof. This is "
    "read-only; it does not process a return.\n"
    "  - escalate_to_stylist: the honest escape hatch. Use ONLY when "
    "process_return cannot handle the case — Cedar rejected the reason, "
    "the customer doesn't own the product, the window has closed, or the "
    "shopper is in distress and deserves a real person. If the shopper "
    "explicitly says the return window has closed and asks for an exception, "
    "call escalate_to_stylist directly rather than attempting a write that "
    "cannot succeed. Otherwise, try returns_and_care + process_return first. "
    "Pass a one-sentence reason explaining what's being routed and why.\n"
    "\n"
    "Output discipline:\n"
    "  - ALWAYS call a tool before writing prose. No greeting, no preamble.\n"
    "  - After the tool returns, write 1–2 sentences. Conversational, not "
    "transactional. Empathy first when a piece arrived damaged; clarity "
    "when a customer is asking what's possible.\n"
    "  - State care, refund, repair, and timing details only when the tool "
    "result supplies them. Do not supplement policy with general product "
    "knowledge. For care, restate only the returned policy or "
    "product-specific care guidance; never infer softening, patina, or "
    "long-term performance. For a stylist escalation, say only that a "
    "pre-addressed note is ready in the handoff card below the response. Do "
    "not claim a message was sent, a stylist was assigned, a reply window, "
    "a repair, a refund, or attached order history.\n"
    "  - No markdown tables, no numbered lists, no emojis, no follow-up "
    "questions to the customer.\n"
    "  - When process_return succeeds, name the action concretely "
    "('I've filed the return for the Wabi-Sabi Bowl') so the customer "
    "knows the write actually happened.\n"
)

# ``_SUPPORT_AGENT_STUBBED`` — legacy flag still read by chat routing; Pellier Labs
# lists Experience Guide as shipped in ``agents.json``.
_SUPPORT_AGENT_STUBBED = False


def _ensure_products_in_output(text: str, tool_results: list) -> str:
    """If the LLM output lacks a JSON products block, extract from tool results and append.

    Suppression rule: if any tool result has the shape of a successful
    ``process_return`` (status == "success" with a "return_id" field),
    do NOT attach product cards. Experience Guide chains
    ``find_pieces`` upstream of ``process_return`` solely to resolve
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
    # Experience Guide — Claude Opus 5. Opus for tone when handling a
    # return. Bedrock rejects the deprecated temperature field for this
    # model, so we rely on the model default.
    model_id, max_tokens, _ = resolve_specialist_model("opus")
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
            returns_and_care,
            find_pieces,
            process_return,
            trace_receipt,
            escalate_to_stylist,
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
        # Surface any inner escalate_to_stylist payload back to the
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
