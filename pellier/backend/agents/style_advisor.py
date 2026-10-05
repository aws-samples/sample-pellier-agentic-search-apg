"""
Style Advisor — Pellier's product search agent. Handles product
search, category browsing, and side-by-side comparisons.

Exposes two surfaces that share one agent construction path:

1. ``build_search_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and Pellier Labs Graph pattern.
2. ``search(query)`` — ``@tool`` wrapper used by Pellier Labs'
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: the factory and tool keep generic names because the
Storefront dispatcher's intent classifier emits 'search' as a keyword.
"""
import json
from strands import Agent, tool
from strands.models import BedrockModel
from services.agent_tools import (
    escalate_to_stylist,
    explore_collection,
    find_pieces,
    side_by_side,
    style_match,
)
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.response_mode import resolve_specialist_model


_SEARCH_SYSTEM_PROMPT = (
    "You are Pellier's Style Advisor. "
    "<tools>"
    "- find_pieces: Use for natural language or intent-based product queries "
    "(e.g. 'linen pieces for 10 days in Goa', 'something under $150'). "
    "Extract price limits from the query and pass as max_price. "
    "Extract category hints and pass as category. "
    "- explore_collection: Use when the user wants to browse a category, material, "
    "or collection theme (e.g. 'show me linen', 'browse home decor'). Pass the "
    "shopper's collection term verbatim; this tool matches catalog categories, "
    "product copy, and tags. For a travel or carry-on browse, set context to "
    "'travel' to prioritize the pieces built for the trip. A request that starts with 'browse' MUST use "
    "explore_collection rather than find_pieces. "
    "- side_by_side: Use when the user wants a side-by-side comparison of two products. "
    "This tool requires product IDs. If the user mentions product names instead of IDs, "
    "first use find_pieces to resolve both productIds, then call side_by_side "
    "with the two IDs. Do not substitute style_match for an explicit comparison. "
    "- style_match: Use when the user asks what pairs with, goes with, or complements "
    "a specific product. First resolve the product with find_pieces if you need its "
    "productId, then call style_match with that productId. "
    "- escalate_to_stylist: ONLY use when the ask is genuinely outside what the "
    "catalog tools can answer — body-image or fit-for-pregnancy questions, cultural "
    "dressing norms the agent doesn't know, deep personal-style coaching beyond "
    "Pellier's catalog, or shopper distress that deserves a real person. "
    "Always try find_pieces / style_match first; calling escalate_to_stylist is the "
    "honest fallback, never a way to skip the work. Pass a one-sentence reason. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. Do NOT write any text before calling a tool. "
    "For a direct discovery request with no named product, make exactly one "
    "retrieval call: find_pieces for an intent-shaped request, or "
    "explore_collection for a request beginning with 'browse'. Do not make a "
    "second retrieval call to pad the result. The only normal multi-tool "
    "sequences are named pairing (find_pieces then style_match) and explicit "
    "comparison (resolve the named products, then side_by_side). "
    "After receiving tool results, write 1-2 short sentences that answer the "
    "shopper's brief directly. Lead with the finished edit or recommendation, "
    "not an explanation of how the catalog is organized. Never mention categories, "
    "tags, tools, retrieval, or a catalog mismatch unless the shopper explicitly asks. "
    "Use persona preferences silently: do not address the shopper by a persona "
    "name or imply a prior exchange unless their message supplies that context. "
    "State only attributes, provenance, care, or performance claims that the "
    "returned product details support, and name only products returned by a tool. "
    "Do not use longevity, patina, softening, aging, or 'deepens with use' "
    "language unless that exact product's returned details explicitly support "
    "it; never generalize such a claim across a group of pieces. "
    "Never use persona preferences as shopper-facing facts: no claims about "
    "saved pieces, prior orders, a home setup, a personal palette, travel plans, "
    "or packing unless the current request explicitly supplies that context. "
    "Do not say a piece is already on the shopper's shelf, part of their "
    "rotation, or a natural next purchase unless the current request explicitly "
    "asks about a named prior order. "
    "Products render as visual cards automatically — do not list them in text. "
    "If the tool returns zero products or an error, say what went wrong briefly "
    "(e.g. 'No results found — try broadening your search.'). "
    "Never use markdown tables, numbered lists, headers, or emojis. Never ask follow-up questions."
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


def build_search_agent() -> Agent:
    """Return a configured Search specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. Callers set those ContextVars before invoking.
    """
    # Style Advisor — Claude Opus 5. Editorial voice + fit/fabric
    # description. Bedrock rejects the deprecated temperature field for
    # this model, so we rely on the model default.
    model_id, max_tokens, _ = resolve_specialist_model("opus")
    return Agent(
        name="search",
        model=BedrockModel(
            model_id=model_id,
            max_tokens=max_tokens,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_SEARCH_SYSTEM_PROMPT)
        ),
        tools=[
            find_pieces,
            explore_collection,
            side_by_side,
            style_match,
            escalate_to_stylist,
        ],
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

        # Audit hook: inner specialist tool calls (find_pieces,
        # style_match, ...) reach pellier.tool_audit so operational history
        # sees them. Outer @tool wrapper already audits at the
        # orchestrator level; this surfaces the layer below.
        from agents.specialist_hooks import (
            append_escalation_marker,
            extract_escalation_payload,
        )

        result = agent(query)
        text = str(result)
        # Forward any inner escalate_to_stylist payload up through the
        # wrapper output. chat.py only sees this wrapper's return value;
        # without the marker the stylist handoff card never renders.
        escalation = extract_escalation_payload(tool_results)
        if escalation is not None:
            return append_escalation_marker(text, escalation)
        return _ensure_products_in_output(text, tool_results)
    except Exception as e:
        return json.dumps({"error": f"Search agent error: {str(e)}"})
