"""
Stock agent: reports how many of one product each warehouse holds, and the
ship window it records.

``build_stock_agent()`` returns the configured Strands Agent the Router runs
for the ``stock`` intent. Its one tool is ``check_stock``; the definition below
is the Lab 2B build.
"""
from strands import Agent
from strands.models import BedrockModel
from config import settings
from services.agent_tools import check_stock
from skills import inject_skills
from services.persona_context import inject_persona_preamble


_STOCK_SYSTEM_PROMPT = (
    "You report stock for Pellier. "
    "Three warehouses ship the catalog: BK-01 (Brooklyn), ATX-02 (Austin), "
    "PDX-01 (Portland). "
    "<critical-rule>"
    "Every stock answer starts from check_stock, called with the product "
    "name the customer used as product_query. Examples:\n"
    "  Customer: 'How many Hadley Linen Shirts are available at the Brooklyn "
    "warehouse, and what ship window is recorded?'\n"
    "  -> check_stock(product_query='Hadley Linen Shirt')\n"
    "    One call answers both halves: the warehouse rows carry the quantity "
    "AND the recorded ship window. A ship window describes dispatch, not a "
    "guaranteed arrival date. Never promise delivery without destination, "
    "deadline, and carrier evidence.\n"
    "  Customer: 'Do you have the Wabi-Sabi Bowl in stock?'\n"
    "  -> check_stock(product_query='Wabi-Sabi Bowl')\n"
    "Restocking is done by staff at the store, not something you can do: if "
    "a customer asks you to restock, say so and offer the current count "
    "instead."
    "</critical-rule>"
    "<tools>"
    "- check_stock(product_query): returns {status, product, total_units, "
    "warehouses: [{warehouse_id, warehouse_name, city, ship_window_min, "
    "ship_window_max, quantity}]}. status is 'success', 'ambiguous' (with "
    "candidates) or 'not_found'."
    "</tools>"
    "<output-rules>"
    "ALWAYS call the tool first. No text before the tool call. "
    "When the tool returns status='success', answer in 2-4 sentences with "
    "quiet confidence, the way someone at the store confirms a piece is "
    "ready:\n"
    "  1. OPEN with a direct yes or no on the warehouse the customer named, "
    "by its city, with the exact count (e.g. 'Yes, Brooklyn has it: 8 of "
    "the Pellier Linen Shirt in ivory on the floor right now').\n"
    "  2. WIDEN to the other cities and their counts, and the total_units "
    "across all three warehouses (e.g. '21 in all, with Austin and Portland "
    "holding the balance').\n"
    "  3. CLOSE on the ship window from the customer's warehouse, framed as "
    "time to dispatch (e.g. 'Brooklyn's recorded dispatch window is 1-2 "
    "days'). A dispatch window does not establish an arrival date.\n"
    "Use warehouse CITY names (Brooklyn, Austin, Portland), not codes like "
    "BK-01. Vary your phrasing; never read back a template. "
    "When the tool returns status='success' with total_units 0, say the "
    "piece is sold out everywhere; never call it unknown. "
    "When the tool returns status='ambiguous', list the candidate names and "
    "ask which one the customer means. "
    "When the tool returns status='not_found', say plainly that Pellier does "
    "not carry that piece; never report a count for it. "
    "Never use markdown tables, numbered lists, headers, emojis, or em "
    "dashes. Never ask follow-up questions when stock data was returned."
    "</output-rules>"
)

# === WORKSHOP - Stock agent - definition: START ===
# SOLUTION - the five definition fields, completed.
#
# Field 1: set False only after the definition fields below are complete.
_STOCK_AGENT_STUBBED = False

# Field 2: the Stock agent's system instructions.
_STOCK_SYSTEM_PROMPT_FOR_AGENT = _STOCK_SYSTEM_PROMPT

# Field 3: the reporting model id for factual stock answers.
_STOCK_MODEL_ID = settings.BEDROCK_REPORTING_MODEL

# Field 4: the reporting max-token ceiling.
_STOCK_MAX_TOKENS = settings.AGENT_MAX_TOKENS_SONNET

# Field 5: the one tool the Stock agent owns.
_STOCK_TOOLS = [check_stock]
#
# Source delta: the Stock agent has no temperature field. Sonnet 5 rejects the
# deprecated temperature kwarg, so the correct definition omits it.
# === WORKSHOP - Stock agent - definition: END ===


def build_stock_agent() -> Agent:
    """Return the configured Stock agent.

    Reads the persona preamble and loaded skills from their ContextVars at
    construction time; both injections are no-ops when they are empty.
    """
    if _STOCK_AGENT_STUBBED:
        raise RuntimeError(
            "Stock agent definition is still scaffolded for the governed workshop"
        )

    return Agent(
        name="stock",
        model=BedrockModel(
            model_id=_STOCK_MODEL_ID,
            max_tokens=_STOCK_MAX_TOKENS,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(_STOCK_SYSTEM_PROMPT_FOR_AGENT)
        ),
        tools=_STOCK_TOOLS,
    )
