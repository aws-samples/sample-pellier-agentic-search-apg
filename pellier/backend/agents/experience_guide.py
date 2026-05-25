"""
Experience Guide — Pellier's customer support agent. Handles return
policies, troubleshooting, and general post-purchase questions.

Exposes two surfaces that share one agent construction path:

1. ``build_support_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Atelier Graph pattern.
2. ``support(query)`` — ``@tool`` wrapper used by the Atelier's
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
import re
from strands import Agent, tool
from strands.models import BedrockModel
from config import settings
from services.agent_tools import (
    escalate_to_stylist,
    find_pieces,
    process_return,
    returns_and_care,
)
from skills import inject_skills
from services.persona_context import inject_persona_preamble

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
    "  - returns_and_care: return window + care guidance by category. "
    "Use for 'how long do I have to return X' or 'how do I take care of Y'.\n"
    "  - process_return: actually write the return. Required args: "
    "customer_id, product_id (integer), reason (one of 'damaged', "
    "'wrong_size', 'not_as_described', 'changed_mind', 'other'). The "
    "Cedar policy enforces that exact set; SQL enforces that the customer "
    "must have ordered the product. If reason='damaged', the catalog "
    "quantity decrements by 1 in the same transaction.\n"
    "  - escalate_to_stylist: the honest escape hatch. Use ONLY when "
    "process_return cannot handle the case — Cedar rejected the reason, "
    "the customer doesn't own the product, the window has closed, or the "
    "shopper is in distress and deserves a real person. Always try "
    "returns_and_care + process_return first. Pass a one-sentence reason "
    "explaining what's being routed and why.\n"
    "\n"
    "Output discipline:\n"
    "  - ALWAYS call a tool before writing prose. No greeting, no preamble.\n"
    "  - After the tool returns, write 1–2 sentences. Conversational, not "
    "transactional. Empathy first when a piece arrived damaged; clarity "
    "when a customer is asking what's possible.\n"
    "  - No markdown tables, no numbered lists, no emojis, no follow-up "
    "questions to the customer.\n"
    "  - When process_return succeeds, name the action concretely "
    "('I've filed the return for the Wabi-Sabi Bowl') so the customer "
    "knows the write actually happened.\n"
)

# ``_SUPPORT_AGENT_STUBBED`` — legacy flag still read by chat routing; Atelier
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
    if re.search(r'```json\s*\[', text):
        return text

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
        text += f"\n\n```json\n{json.dumps(all_products)}\n```"
    return text


def build_support_agent() -> Agent:
    """Return a configured Customer Support specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. A persona-aware preamble lets queries like
    "can I return the camp shirt I bought?" ground in the shopper's
    actual order history; both injections are no-ops for anonymous
    sessions.
    """
    # Experience Guide — Claude Opus 4.6 at 0.2. Empathy + concrete policy.
    # Opus for tone when handling a return; steady temperature because
    # policy is policy.
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_OPUS_MODEL,
            max_tokens=settings.AGENT_MAX_TOKENS_OPUS,
            temperature=0.2,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_SUPPORT_SYSTEM_PROMPT)
        ),
        tools=[returns_and_care, find_pieces, process_return, escalate_to_stylist],
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
            attach_policy_hook,
            extract_escalation_payload,
        )
        attach_policy_hook(agent)

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
