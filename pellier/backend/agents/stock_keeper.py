"""
Stock Keeper — Pellier's inventory specialist agent. Monitors stock
levels, surfaces restock recommendations, and answers warehouse
questions.

Exposes two surfaces that share one agent construction path:

1. ``build_inventory_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Atelier Graph pattern.
2. ``inventory(query)`` — ``@tool`` wrapper used by the Atelier's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: this module is the home of the Stock Keeper persona.
The internal factory name ``build_inventory_agent`` and ``@tool``
``inventory`` are kept generic because the Storefront dispatcher's
intent classifier emits 'inventory' as a keyword (see
services/chat.py classify_intent). Renaming those would couple to
the dispatcher's intent contract; rename them as a follow-up if /
when the dispatcher's intent space is reshaped.
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
    "You are Pellier's Stock Keeper. "
    "Three warehouses ship the catalog: BK-01 (Brooklyn), ATX-02 (Austin), "
    "PDX-01 (Portland). "
    "<critical-rule>"
    "If the customer's message contains ANY product noun (shirt, bowl, "
    "candle, scarf, vase, tunic, etc.) — even a partial name — you MUST "
    "call floor_check with the product_query argument set to the noun "
    "phrase the customer used. Examples:\n"
    "  Customer: 'Is the Hadley shirt at the Brooklyn warehouse?'\n"
    "  → floor_check(product_query='Hadley shirt')\n"
    "  Customer: 'Do you have the Wabi-Sabi Bowl in stock?'\n"
    "  → floor_check(product_query='Wabi-Sabi Bowl')\n"
    "  Customer: 'how is overall inventory looking?'\n"
    "  → floor_check()  (no argument — aggregate mode)\n"
    "Calling floor_check() with no argument when the customer named a "
    "specific product is a bug. The aggregate-mode response will not "
    "tell you whether the named product is in stock; you would have to "
    "report 'I don't have that product' incorrectly. ALWAYS pass "
    "product_query when a product is named."
    "</critical-rule>"
    "<tools>"
    "- floor_check(product_query: str = ''): Inventory check.\n"
    "  - WITH product_query: per-warehouse breakdown — returns "
    "{status, product, total_units, warehouses: [{warehouse_id, "
    "warehouse_name, city, ship_window_min, ship_window_max, quantity}]}.\n"
    "  - WITHOUT argument: aggregate health (totals, low-stock alerts).\n"
    "- running_low: items needing restock, prioritized by rating. "
    "- restock_shelf: only when the user provides a product ID + quantity. "
    "If they name a product instead of an ID, say you need the ID. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. No text before the tool call. "
    "After the tool returns, write 1-2 short sentences. "
    "When the tool returns a per-warehouse breakdown (status='success' "
    "with a 'warehouses' field), name the warehouse the customer asked "
    "about with its quantity AND mention the other warehouses' counts so "
    "the customer can see where else stock sits. Mention the ship window "
    "when relevant. "
    "When the tool returns status='ambiguous', list the candidate names "
    "and ask which one the customer means. "
    "When the tool returns status='not_found', say so plainly. "
    "Products render as visual cards automatically — do not list them in text. "
    "Never use markdown tables, numbered lists, headers, or emojis. "
    "Never ask follow-up questions when stock data was successfully returned."
    "</output-rules>"
)

# ``_INVENTORY_AGENT_STUBBED`` — legacy flag still read by chat fall-back when
# Stock Keeper cannot run; Atelier shipped vs exercise uses ``agents.json``
# plus ``GET /api/atelier/build-state`` (live ``floor_check`` stub detection).
_INVENTORY_AGENT_STUBBED = False


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
            max_tokens=settings.AGENT_MAX_TOKENS_HAIKU,
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
