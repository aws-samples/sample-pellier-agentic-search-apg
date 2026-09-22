"""
Inventory Agent — Pellier's inventory specialist agent. Monitors stock
levels, surfaces restock recommendations, and answers warehouse
questions.

Exposes two surfaces that share one agent construction path:

1. ``build_inventory_agent()`` — factory returning a configured Agent,
   used by the Storefront dispatcher and the Observatory Graph pattern.
2. ``inventory(query)`` — ``@tool`` wrapper used by the Observatory's
   Agents-as-Tools orchestrator. Delegates to the factory.

Note on naming: this module is the home of the Inventory Agent persona.
The internal factory name ``build_inventory_agent`` and ``@tool``
``inventory`` are kept generic because the Storefront dispatcher's
intent classifier emits 'inventory' as a keyword (see
services/chat.py classify_intent). Renaming those would couple to
the dispatcher's intent contract; rename them as a follow-up if /
when the dispatcher's intent space is reshaped.
"""
import json
from strands import Agent, tool
from strands.models import BedrockModel
from config import settings
from services.agent_tools import check_inventory, get_low_stock
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.response_mode import resolve_specialist_model


_INVENTORY_SYSTEM_PROMPT = (
    "You are Pellier's inventory specialist. "
    "Three warehouses ship the catalog: BK-01 (Brooklyn), ATX-02 (Austin), "
    "PDX-01 (Portland). "
    "<critical-rule>"
    "If the customer's message contains ANY product noun (shirt, bowl, "
    "candle, scarf, vase, tunic, etc.) — even a partial name — you MUST "
    "call check_inventory with the product_query argument set to the noun "
    "phrase the customer used. Examples:\n"
    "  Customer: 'How many Hadley Linen Shirts are available at the Brooklyn "
    "warehouse, and what ship window is recorded?'\n"
    "  → check_inventory(product_query='Hadley Linen Shirt')\n"
    "    One call answers both halves: the warehouse breakdown carries the "
    "quantity AND the recorded ship window. This describes dispatch, not a "
    "guaranteed arrival date. Never promise delivery without destination, "
    "deadline, and carrier evidence.\n"
    "  Customer: 'Do you have the Wabi-Sabi Bowl in stock?'\n"
    "  → check_inventory(product_query='Wabi-Sabi Bowl')\n"
    "  Customer: 'how is overall inventory looking?'\n"
    "  → check_inventory()  (no argument — aggregate mode)\n"
    "Calling check_inventory() with no argument when the customer named a "
    "specific product is a bug. The aggregate-mode response will not "
    "tell you whether the named product is in stock; you would have to "
    "report 'I don't have that product' incorrectly. ALWAYS pass "
    "product_query when a product is named."
    "</critical-rule>"
    "<tools>"
    "- check_inventory(product_query: str = ''): Inventory check.\n"
    "  - WITH product_query: per-warehouse breakdown — returns "
    "{status, product, total_units, warehouses: [{warehouse_id, "
    "warehouse_name, city, ship_window_min, ship_window_max, quantity}]}.\n"
    "  - WITHOUT argument: aggregate health (totals, low-stock alerts).\n"
    "- get_low_stock: items needing restock, prioritized by rating. "
    "Restocking is an operator action on the desk, not something you can do: "
    "if a customer asks you to restock, say so and offer the current count instead. "
    "</tools>"
    "<output-rules>"
    "ALWAYS call a tool first. No text before the tool call. "
    "When the tool returns a per-warehouse breakdown (status='success' "
    "with a 'warehouses' field), answer in 2-4 sentences with quiet "
    "editorial confidence — this is a concierge confirming a piece is "
    "ready, not a database dump. Structure it like a reveal:\n"
    "  1. OPEN with a direct yes/no on the warehouse the customer named, "
    "by its city, with the exact count and what it means — lead, don't "
    "bury (e.g. 'Yes, Brooklyn has it: 8 of the Pellier Linen Shirt in "
    "ivory on the floor right now').\n"
    "  2. WIDEN to the rest of the network in one flowing sentence — the "
    "other cities and their counts, and the total_units across all three "
    "warehouses so the customer feels the full inventory behind the piece "
    "(e.g. '21 in all, with Austin and Portland holding the balance').\n"
    "  3. CLOSE on the ship window from the customer's warehouse, framed "
    "as time to dispatch (e.g. 'Brooklyn's recorded dispatch window is "
    "1-2 days'). A dispatch window does not establish an arrival date.\n"
    "Weave in the product's color and name naturally; use warehouse CITY "
    "names (Brooklyn, Austin, Portland), not codes like BK-01. Vary your "
    "phrasing — never read back a template. "
    "When the tool returns status='ambiguous', list the candidate names "
    "and ask which one the customer means. "
    "When the tool returns status='not_found', say so plainly. "
    "Products render as visual cards automatically — do not list them in text. "
    "Never use markdown tables, numbered lists, headers, emojis, or em "
    "dashes — keep it to flowing prose punctuated with periods, commas, "
    "and colons. "
    "Never ask follow-up questions when stock data was successfully returned."
    "</output-rules>"
)

# === WORKSHOP · Inventory Agent · definition: START ===
# WORKSHOP_EXERCISE_STUB
#
# Task 1B: choose the read tools that can establish the inventory facts.
# Prompt and model configuration are supplied. Clear the stub after the grant.
_INVENTORY_AGENT_STUBBED = True

# Provided: Inventory Agent system instructions.
_INVENTORY_SYSTEM_PROMPT_FOR_AGENT = _INVENTORY_SYSTEM_PROMPT

# Provided: reporting model.
_INVENTORY_MODEL_ID = settings.BEDROCK_REPORTING_MODEL

# Provided: token ceiling.
_INVENTORY_MAX_TOKENS = settings.AGENT_MAX_TOKENS_SONNET

# Participant: permitted inventory reads.
_INVENTORY_TOOLS = []
#
# Source delta: Inventory Agent has no temperature field. Sonnet 4.6 rejects the
# deprecated temperature kwarg, so the correct definition omits it.
# === WORKSHOP · Inventory Agent · definition: END ===


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


def build_inventory_agent() -> Agent:
    """Return a configured Inventory specialist Agent.

    Reads persona preamble + loaded skills from ContextVars at
    construction time. Both injections are no-ops when their
    ContextVars are empty, so anonymous observatory behavior is
    unchanged by consolidating the five factories onto the same
    substrate.
    """
    if _INVENTORY_AGENT_STUBBED:
        raise RuntimeError(
            "Inventory Agent definition is still scaffolded for the governed workshop"
        )

    # Inventory Agent — Sonnet 4.6 reporting profile. Pure factual lookups
    # (warehouse, count, ETA), with no temperature override.
    model_id, max_tokens, _ = resolve_specialist_model(
        "sonnet",
        balanced_model_id=_INVENTORY_MODEL_ID,
        balanced_max_tokens=_INVENTORY_MAX_TOKENS,
    )
    return Agent(
        name="inventory",
        model=BedrockModel(
            model_id=model_id,
            max_tokens=max_tokens,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_INVENTORY_SYSTEM_PROMPT_FOR_AGENT)
        ),
        tools=_INVENTORY_TOOLS,
    )


@tool
def inventory(query: str) -> str:
    """
    Analyze inventory levels and provide restocking recommendations.

    Args:
        query: Inventory-related question

    Returns:
        Stock levels and restocking recommendations with product details
    """
    # The other orchestration patterns carry their own scaffold seams
    # (graph_pattern's _UnavailableSpecialistNode, the dispatcher
    # short-circuit in chat.py). Without this one, a scaffolded Stock
    # Keeper surfaces here as build_inventory_agent()'s RuntimeError
    # wrapped in a generic error envelope, and the orchestrator
    # improvises around a tool that looks broken rather than unbuilt.
    if _INVENTORY_AGENT_STUBBED:
        return json.dumps({
            "status": "unavailable",
            "message": (
                "Inventory is the governed workshop build in this "
                "environment. Complete the Inventory Agent exercise, "
                "then rerun this request."
            ),
        })
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
