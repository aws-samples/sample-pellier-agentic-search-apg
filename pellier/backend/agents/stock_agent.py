"""
Stock agent: reports how many of one product each warehouse holds, and the
ship window it records.

``build_stock_agent()`` returns the configured Strands Agent the Router runs
for the ``stock`` intent. The tools it is granted are the Lab 2B build: only
``check_stock`` reads the warehouse rows a stock answer must come from.
"""
from strands import Agent
from strands.models import BedrockModel
from config import settings
from services import agent_tools
from skills import SKILL_MODE_FIXED, SKILL_MODE_ON_DEMAND, inject_skills, on_demand_plugin, skills_for
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
    "warehouses: [{warehouse_code, warehouse_name, city, ship_window_min, "
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
# Task 2B: grant the tools a stock answer may come from.
# Prompt and model configuration are supplied.

# Provided: Stock agent system instructions.
_STOCK_SYSTEM_PROMPT_FOR_AGENT = _STOCK_SYSTEM_PROMPT

# Provided: reporting model.
_STOCK_MODEL_ID = settings.BEDROCK_REPORTING_MODEL

# Provided: token ceiling.
_STOCK_MAX_TOKENS = settings.AGENT_MAX_TOKENS_SONNET

# The tools the Stock agent may call.
_STOCK_TOOLS = [
    agent_tools.search_products,
    agent_tools.browse_department,
    agent_tools.compare_products,
    agent_tools.check_stock,
]
#
# Source delta: the Stock agent has no temperature field. Sonnet 5 rejects the
# deprecated temperature kwarg, so the correct definition omits it.
# === WORKSHOP - Stock agent - definition: END ===


def build_stock_agent(*, skill_mode: str = SKILL_MODE_FIXED) -> Agent:
    """Return the configured Stock agent.

    Reads the persona preamble from its ContextVar at construction time; the
    injection is a no-op when it is empty.

    Args:
        skill_mode: ``fixed`` carries the agent's skills in the prompt;
            ``on_demand`` lists their names and adds the loader tool instead.
    """
    prompt = _STOCK_SYSTEM_PROMPT_FOR_AGENT
    plugins = None
    if skill_mode == SKILL_MODE_ON_DEMAND:
        plugins = [on_demand_plugin("stock")]
    else:
        prompt = inject_skills(prompt, skills_for("stock"))

    return Agent(
        name="stock",
        model=BedrockModel(
            model_id=_STOCK_MODEL_ID,
            max_tokens=_STOCK_MAX_TOKENS,
        ),
        system_prompt=inject_persona_preamble(prompt),
        tools=_STOCK_TOOLS,
        plugins=plugins,
    )
