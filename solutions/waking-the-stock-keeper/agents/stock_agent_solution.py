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
from pellier_copy import STOCK_OUTPUT_RULES
from services import agent_tools
# Named so the Lab 2B grant may list the tool by its bare name as well.
from services.agent_tools import check_stock  # noqa: F401
from skills import (
    SKILL_MODE_FIXED, SKILL_MODE_ON_DEMAND, inject_skills, on_demand_plugin, skills_for,
)
from services.persona_context import inject_persona_preamble


# The prompt's one rule for where a stock answer comes from. The Builder view
# prints it beside the tools the running agent may call (Lab 2B).
STOCK_PROMPT_RULE = "Every stock answer starts from check_stock"

_STOCK_SYSTEM_PROMPT = (
    "You report stock for Pellier. "
    "Three warehouses ship the catalog: BK-01 (Brooklyn), ATX-02 (Austin), "
    "PDX-01 (Portland). "
    "<critical-rule>"
    + STOCK_PROMPT_RULE
    + ", called with the product "
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
    + STOCK_OUTPUT_RULES
)

# === WORKSHOP - Stock agent - definition: START ===
# SOLUTION - the Stock agent reads stock from one place.

# Provided: Stock agent system instructions.
_STOCK_SYSTEM_PROMPT_FOR_AGENT = _STOCK_SYSTEM_PROMPT

# Provided: reporting model.
_STOCK_MODEL_ID = settings.BEDROCK_REPORTING_MODEL

# Provided: token ceiling.
_STOCK_MAX_TOKENS = settings.AGENT_MAX_TOKENS_SONNET

# Only check_stock reads warehouse_inventory. A catalog tool would let the
# agent answer a stock question from a product listing instead.
_STOCK_TOOLS = [agent_tools.check_stock]
#
# The Stock agent sets no temperature: Sonnet 5 rejects that argument.
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
