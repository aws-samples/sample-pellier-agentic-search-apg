"""
Customer Support Agent — return policies, troubleshooting, and
general post-purchase questions.

Exposes two surfaces that share one agent construction path:

1. ``build_support_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Atelier Graph pattern.
2. ``support(query)`` — ``@tool`` wrapper used by the Atelier's
   Agents-as-Tools orchestrator. Delegates to the factory.

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
from services.agent_tools import returns_and_care, find_pieces
from skills import inject_skills
from services.persona_context import inject_persona_preamble

logger = logging.getLogger(__name__)


# === CHALLENGE · Experience Guide · system prompt: START ===
# WORKSHOP_EXERCISE_STUB (Workshop format only.)
#
# Experience Guide's voice. Sonnet 4.6 at 0.2 — capable model for tone
# when handling a return; steady temperature because policy is policy.
# Write a system prompt that:
#
#   1. Names the agent ("You are Blaize Bazaar's Experience Guide.")
#   2. Lists the three tools and when to use each:
#        - returns_and_care → return window + care by product category
#        - find_pieces      → resolve product mentions to productId + category
#        - process_return   → write the return row (Cedar-gated on reason,
#                             SQL-gated on ownership, transactional adjust
#                             of product_catalog.quantity if reason='damaged')
#   3. Teaches the chaining pattern: customer mentions a product →
#      find_pieces first → returns_and_care or process_return next.
#   4. Sets the empathy/discipline balance:
#        - ALWAYS call a tool first, no text before tool call
#        - After tool: 1–2 short sentences, conversational
#        - No markdown tables, numbered lists, emojis, or follow-up Q's
#        - When process_return succeeds, name the action concretely
#          ("I've filed the return for the Wabi-Sabi Bowl")
#
# Then add ``process_return`` to the tools list in build_support_agent.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/module2/agents/customer_support_agent.py \
#       blaize-bazaar/backend/agents/customer_support_agent.py

_SUPPORT_SYSTEM_PROMPT = (
    "You are Blaize Bazaar's Experience Guide — in stub state. "
    "Replace this system prompt with the full voice (see the CHALLENGE "
    "block above in this file, or copy the solution)."
)

# Atelier reads this flag to render the "Your turn" pill on the
# Experience Guide agent card. Flip to False once the real prompt
# lands (or the cp command runs).
_SUPPORT_AGENT_STUBBED = True

# === CHALLENGE · Experience Guide · system prompt: END ===


def _ensure_products_in_output(text: str, tool_results: list) -> str:
    """If the LLM output lacks a JSON products block, extract from tool results and append."""
    if re.search(r'```json\s*\[', text):
        return text

    all_products = []
    for result_str in tool_results:
        try:
            data = json.loads(result_str)
            if isinstance(data, dict) and "products" in data:
                all_products.extend(data["products"])
            elif isinstance(data, list):
                all_products.extend(data)
        except (json.JSONDecodeError, TypeError):
            pass

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
    # Experience Guide — Sonnet 4.6 at 0.2. Empathy + concrete policy.
    # Sonnet for tone when handling a return; steady temperature because
    # policy is policy.
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_SONNET_MODEL,
            max_tokens=4096,
            temperature=0.2,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_SUPPORT_SYSTEM_PROMPT)
        ),
        tools=[returns_and_care, find_pieces],
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

        result = agent(query)
        text = str(result)
        return _ensure_products_in_output(text, tool_results)
    except Exception as e:
        return json.dumps({"error": f"Support agent error: {str(e)}"})
