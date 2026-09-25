"""
Search Agent — Pellier's product search agent. Handles product
search, category browsing, and side-by-side comparisons.

Exposes two surfaces that share one agent construction path:

1. ``build_search_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Observatory Graph pattern.
2. ``search(query)`` — ``@tool`` wrapper used by the Observatory's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: the factory and tool keep generic names because the
Storefront dispatcher's intent classifier emits 'search' as a keyword.
"""
import json
from strands import Agent, tool
from strands.models import BedrockModel
from services.agent_tools import (
    escalate_to_human,
    browse_category,
    search_products,
    compare_products,
    get_related_products,
    get_trending_products,
)
from pellier_copy import PRODUCT_REQUIREMENTS_PROMPT
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.response_mode import resolve_specialist_model


_SEARCH_SYSTEM_PROMPT = (
    "You are Pellier's catalog specialist. "
    "<tools>"
    "- search_products: Use for natural language or intent-based product queries "
    "(e.g. 'linen pieces for 10 days in Goa', 'something under $150'). "
    "Extract price limits from the query and pass as max_price. "
    "Extract category hints and pass as category. "
    "- browse_category: Use when the user wants to browse a specific category "
    "(e.g. 'show me linen', 'browse home decor'). "
    "- compare_products: Use when the user wants a side-by-side comparison of two products. "
    "This tool requires product IDs. If the user mentions product names instead of IDs, "
    "first use search_products to find each product's productId, then call compare_products "
    "with the two IDs. "
    "- get_related_products: Use when the user asks what pairs with, goes with, or complements "
    "a specific product. Always pass source_product_name using the named product from the "
    "shopper's request. Never invent or guess a product_id. You may include product_id only "
    "after search_products returns that exact named product; the tool verifies the two agree. "
    "- get_trending_products: Use when the user asks what is popular, what others are "
    "buying, what is new, or what the house is known for right now, without naming a "
    "piece or a category. Do not use it to answer a specific product query. "
    "- escalate_to_human: ONLY use when the ask is genuinely outside what the "
    "catalog tools can answer — body-image or fit-for-pregnancy questions, cultural "
    "dressing norms the agent doesn't know, deep personal-style coaching beyond the "
    "boutique's 60 curated pieces, or shopper distress that deserves a real person. "
    "Always try search_products / get_related_products first; calling escalate_to_human is the "
    "honest fallback, never a way to skip the work. Pass a one-sentence reason. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. Do NOT write any text before calling a tool. "
    "After receiving tool results, select two or three returned pieces (or every "
    "returned piece when fewer than two qualify). Write one compact sentence for "
    "each selected piece, naming it exactly as returned and grounding the reason "
    "in a returned attribute. Do not name unselected results. "
    "The named pieces render as visual cards automatically. "
    + PRODUCT_REQUIREMENTS_PROMPT
    + "If the tool returns zero products or an error, say what went wrong briefly "
    "(e.g. 'No results found — try broadening your search.'). "
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


def build_search_agent(
    *,
    model_id: str | None = None,
    max_tokens: int | None = None,
    allow_escalation: bool = True,
) -> Agent:
    """Return a configured Search specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. Callers set those ContextVars before invoking.
    """
    # Search Agent — Claude Opus 4.6. Editorial voice + fit/fabric
    # description. Bedrock rejects the deprecated temperature field for
    # this model, so we rely on the model default.
    tools = [
        search_products,
        browse_category,
        compare_products,
        get_related_products,
        get_trending_products,
    ]
    if allow_escalation:
        tools.append(escalate_to_human)

    prompt = _SEARCH_SYSTEM_PROMPT
    if not allow_escalation:
        prompt += (
            "<turn-policy>This is an ordinary catalog turn. Use one retrieval "
            "tool, return the closest relevant pieces, and stop. Do not broaden "
            "into pairing tools unless the shopper explicitly asks what goes "
            "with a named product. A partial catalog match is still an answer; "
            "do not attempt a human handoff.</turn-policy>"
        )

    selected_model_id, selected_max_tokens, _ = resolve_specialist_model(
        "opus",
        balanced_model_id=model_id,
        balanced_max_tokens=max_tokens,
    )
    return Agent(
        name="search",
        model=BedrockModel(
            model_id=selected_model_id,
            max_tokens=selected_max_tokens,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(prompt)
        ),
        tools=tools,
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

        # Audit hook: inner specialist tool calls (search_products,
        # get_related_products, ...) reach pellier.tool_audit so operational history
        # sees them. Outer @tool wrapper already audits at the
        # orchestrator level; this surfaces the layer below.
        from agents.specialist_hooks import (
            append_escalation_marker,
            extract_escalation_payload,
        )

        result = agent(query)
        text = str(result)
        # Forward any inner escalate_to_human payload up through the
        # wrapper output. chat.py only sees this wrapper's return value;
        # without the marker the stylist handoff card never renders.
        escalation = extract_escalation_payload(tool_results)
        if escalation is not None:
            return append_escalation_marker(text, escalation)
        return _ensure_products_in_output(text, tool_results)
    except Exception as e:
        return json.dumps({"error": f"Search agent error: {str(e)}"})
