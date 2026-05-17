"""
Style Advisor — Pellier's product search agent. Handles product
search, category browsing, and side-by-side comparisons.

Exposes two surfaces that share one agent construction path:

1. ``build_search_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Atelier Graph pattern.
2. ``search(query)`` — ``@tool`` wrapper used by the Atelier's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: the factory and tool keep generic names because the
Storefront dispatcher's intent classifier emits 'search' as a keyword.
"""
import json
import re
from strands import Agent, tool
from strands.models import BedrockModel
from config import settings
from services.agent_tools import find_pieces, explore_collection, side_by_side, style_match
from skills import inject_skills
from services.persona_context import inject_persona_preamble


_SEARCH_SYSTEM_PROMPT = (
    "You are Pellier's Style Advisor. "
    "<tools>"
    "- find_pieces: Use for natural language or intent-based product queries "
    "(e.g. 'gift for a cook', 'noise-canceling headphones under $200'). "
    "Extract price limits from the query and pass as max_price. "
    "Extract category hints and pass as category. "
    "- explore_collection: Use when the user wants to browse a specific category "
    "(e.g. 'show me all laptops'). "
    "- side_by_side: Use when the user wants a side-by-side comparison of two products. "
    "This tool requires product IDs. If the user mentions product names instead of IDs, "
    "first use find_pieces to find each product's productId, then call side_by_side "
    "with the two IDs. "
    "- style_match: Use when the user asks what pairs with, goes with, or complements "
    "a specific product. First resolve the product with find_pieces if you need its "
    "productId, then call style_match with that productId. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. Do NOT write any text before calling a tool. "
    "After receiving tool results, write 1-2 short sentences as a conversational intro. "
    "Products render as visual cards automatically — do not list them in text. "
    "If the tool returns zero products or an error, say what went wrong briefly "
    "(e.g. 'No results found — try broadening your search.'). "
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


def build_search_agent() -> Agent:
    """Return a configured Search specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. Callers set those ContextVars before invoking.
    """
    # Style Advisor — Claude Opus 4.6 at 0.4. Editorial voice + fit/fabric
    # description. Model choice is an architectural decision; see
    # lab-content/shared/model-mix-sidebar.en.md.
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_OPUS_MODEL,
            max_tokens=4096,
            temperature=0.4,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_SEARCH_SYSTEM_PROMPT)
        ),
        tools=[find_pieces, explore_collection, side_by_side, style_match],
    )


@tool
def search(query: str) -> str:
    """
    Search for products using natural language, browse categories, or compare products.

    Args:
        query: Product search query or comparison request

    Returns:
        Agent response with product search results
    """
    try:
        tool_results = []
        agent = build_search_agent()

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
        return json.dumps({"error": f"Search agent error: {str(e)}"})
