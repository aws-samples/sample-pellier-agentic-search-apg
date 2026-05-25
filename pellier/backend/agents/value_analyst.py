"""
Value Analyst — Pellier's pricing agent. Analyzes pricing and
surfaces deals.

Exposes two surfaces that share one agent construction path:

1. ``build_pricing_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Atelier Graph pattern.
2. ``pricing(query)`` — ``@tool`` wrapper used by the Atelier's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: the factory and tool keep generic names because the
Storefront dispatcher's intent classifier emits 'pricing' as a keyword.
"""
import json
import re
from strands import Agent, tool
from strands.models import BedrockModel
from config import settings
from services.agent_tools import price_intelligence, explore_collection, find_pieces
from skills import inject_skills
from services.persona_context import inject_persona_preamble


_PRICING_SYSTEM_PROMPT = (
    "You are Pellier's Value Analyst. "
    "<tools>"
    "- price_intelligence: Use for category-level pricing statistics (average, min, max, distribution). "
    "- find_pieces: Use when the user describes specific products with price constraints "
    "(e.g. 'laptops under $500'). "
    "- explore_collection: Use to browse products in a category when the user wants to see "
    "what is available at various price points. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. Do NOT write any text before calling a tool. "
    "Call at most 2 tools per query. "
    "After receiving tool results, write 1-2 short sentences as a conversational intro. "
    "Products render as visual cards automatically — do not list them in text. "
    "If the tool returns zero products or an error, say what went wrong briefly "
    "(e.g. 'No pricing data available for that category right now.'). "
    "Never use markdown tables, numbered lists, headers, or emojis. Never ask follow-up questions."
    "</output-rules>"
)


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


def build_pricing_agent() -> Agent:
    """Return a configured Pricing specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. The pricing specialist didn't read these in
    earlier revisions; adding them in the factory keeps behavior
    consistent across all five specialists without changing anonymous
    atelier output (both injections are no-ops when their
    ContextVars are empty).
    """
    # Value Analyst — Haiku 4.5 at 0.1. Reports numbers and ranges.
    # Fast + deterministic. The only thing worse than a slow price
    # check is a wrong one.
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_HAIKU_MODEL,
            max_tokens=settings.AGENT_MAX_TOKENS_HAIKU,
            temperature=0.1,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_PRICING_SYSTEM_PROMPT)
        ),
        tools=[price_intelligence, explore_collection, find_pieces],
    )


@tool
def pricing(query: str) -> str:
    """
    Analyze product pricing and suggest optimal deals.
    Finds best-value products, compares prices across categories,
    and helps users find products within budget constraints.

    Args:
        query: Pricing-related question or request

    Returns:
        JSON array of products with pricing analysis
    """
    try:
        tool_results = []
        agent = build_pricing_agent()

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

        from agents.specialist_hooks import attach_policy_hook
        attach_policy_hook(agent)

        result = agent(query)
        text = str(result)
        return _ensure_products_in_output(text, tool_results)
    except Exception as e:
        return json.dumps({"error": f"Pricing agent error: {str(e)}"})
