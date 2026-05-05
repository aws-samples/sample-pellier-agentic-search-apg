"""
Inventory Restock Agent — monitors stock levels and surfaces restock
recommendations.

Exposes two surfaces that share one agent construction path:

1. ``build_inventory_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Atelier Graph pattern.
2. ``inventory(query)`` — ``@tool`` wrapper used by the Atelier's
   Agents-as-Tools orchestrator. Delegates to the factory.
"""
import json
import re
from strands import Agent, tool
from strands.models import BedrockModel
from config import settings
from services.agent_tools import floor_check, restock_shelf, running_low
from skills import inject_skills
from services.persona_context import inject_persona_preamble


_INVENTORY_SYSTEM_PROMPT = (
    "You are Blaize Bazaar's Inventory Specialist. "
    "<tools>"
    "- floor_check: Use for overall stock statistics and warehouse health overview. "
    "- running_low: Use to find items that need restocking, prioritized by demand. "
    "- restock_shelf: Use when the user provides a specific product ID and quantity to restock. "
    "If the user mentions a product by name instead of ID, inform them you need the product ID. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. Do NOT write any text before calling a tool. "
    "After receiving tool results, write 1-2 short sentences summarizing stock status. "
    "Products render as visual cards automatically — do not list them in text. "
    "If the tool returns zero products or an error, say what went wrong briefly "
    "(e.g. 'Could not retrieve inventory data right now.'). "
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


def build_inventory_agent() -> Agent:
    """Return a configured Inventory specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. Both injections are no-ops when their
    ContextVars are empty, so anonymous atelier behavior is
    unchanged by consolidating the five factories onto the same
    substrate.
    """
    # Stock Keeper — Haiku 4.5 at 0.0. Pure factual lookups (warehouse,
    # count, ETA). Zero variance. Fastest config in the system.
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_HAIKU_MODEL,
            max_tokens=2048,
            temperature=0.0,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_INVENTORY_SYSTEM_PROMPT)
        ),
        tools=[floor_check, restock_shelf, running_low],
    )


@tool
def inventory(query: str) -> str:
    """
    Analyze inventory levels and provide restocking recommendations.
    Can also execute restock actions when user provides product ID and quantity.

    Args:
        query: Inventory-related question or restock command

    Returns:
        Restocking recommendations or restock confirmation with product details
    """
    try:
        tool_results = []
        agent = build_inventory_agent()

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
        return json.dumps({"error": f"Inventory agent error: {str(e)}"})
