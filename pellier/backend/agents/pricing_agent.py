"""
Pricing Agent — Pellier's pricing agent. Analyzes pricing and
surfaces deals.

Exposes two surfaces that share one agent construction path:

1. ``build_pricing_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Observatory Graph pattern.
2. ``pricing(query)`` — ``@tool`` wrapper used by the Observatory's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: the factory and tool keep generic names because the
Storefront dispatcher's intent classifier emits 'pricing' as a keyword.
"""
import json
from strands import Agent, tool
from strands.models import BedrockModel
from services.agent_tools import (
    get_price_analysis,
    browse_category,
    search_products,
    compare_products,
    get_trending_products,
)
from pellier_copy import PRODUCT_REQUIREMENTS_PROMPT
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.response_mode import resolve_specialist_model


_PRICING_SYSTEM_PROMPT = (
    "You are Pellier's pricing specialist. "
    "<tools>"
    "- get_price_analysis: Use for category-level pricing statistics (average, min, max, distribution). "
    "- search_products: Use when the user describes specific products with price constraints "
    "(e.g. 'linen shirts under $250'). "
    "- browse_category: Use to browse products in a category when the user wants to see "
    "what is available at various price points. "
    "- compare_products: Use when the user weighs two specific pieces against each other "
    "('is the cashmere worth the extra $90 over the merino'). This tool requires product "
    "IDs, so resolve each piece with search_products first, then pass the two IDs. Lead "
    "your answer with what the price difference buys, not with the numbers alone. "
    "- get_trending_products: Use when the user asks what is worth buying at a price "
    "point, or what other clients choose in this range, rather than asking for a "
    "statistic. Pair it with get_price_analysis when they want both the range and the "
    "pieces that sit in it. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. Do NOT write any text before calling a tool. "
    "Call at most 2 tools per query. "
    "When product results are returned, select two or three pieces (or every "
    "piece when fewer than two qualify). Write one compact sentence for each "
    "selected piece, naming it exactly as returned and explaining the price fit "
    "with returned facts. Do not name unselected results. "
    "The named pieces render as visual cards automatically. "
    + PRODUCT_REQUIREMENTS_PROMPT
    + "If the tool returns zero products or an error, say what went wrong briefly "
    "(e.g. 'No pricing data available for that category right now.'). "
    "Never use markdown tables, numbered lists, headers, emojis, or em dashes. Never ask follow-up questions."
    "</output-rules>"
)


def _ensure_products_in_output(text: str, tool_results: list) -> str:
    """If the LLM output lacks a JSON products block, extract from tool results and append."""
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
        from agents.specialist_hooks import forward_or_append_products
        return forward_or_append_products(text, all_products)
    return text


def build_pricing_agent() -> Agent:
    """Return a configured Pricing specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. The pricing specialist didn't read these in
    earlier revisions; adding them in the factory keeps behavior
    consistent across all five specialists without changing anonymous
    observatory output (both injections are no-ops when their
    ContextVars are empty).
    """
    # Pricing Agent — Sonnet 4.6 reporting profile. Reports numbers and
    # ranges with no temperature override. The only thing worse than a
    # slow price check is a wrong one.
    model_id, max_tokens, _ = resolve_specialist_model("sonnet")
    return Agent(
        name="pricing",
        model=BedrockModel(
            model_id=model_id,
            max_tokens=max_tokens,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_PRICING_SYSTEM_PROMPT)
        ),
        tools=[
            get_price_analysis,
            browse_category,
            search_products,
            compare_products,
            get_trending_products,
        ],
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

        result = agent(query)
        text = str(result)
        return _ensure_products_in_output(text, tool_results)
    except Exception as e:
        return json.dumps({"error": f"Pricing agent error: {str(e)}"})
