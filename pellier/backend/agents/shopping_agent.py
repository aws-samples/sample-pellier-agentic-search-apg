"""
Shopping agent: helps a shopper find, browse and compare products.

``build_shopping_agent()`` returns the configured Strands Agent the Router runs
for the ``shopping`` intent: price, compare, browse, gifts, and anything that
is not a stock count or an after-purchase question.
"""
from strands import Agent
from strands.models import BedrockModel
from services.agent_tools import (
    ask_a_person,
    browse_department,
    compare_products,
    search_products,
)
from pellier_copy import SHOPPING_SYSTEM_PROMPT
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from services.specialist_models import specialist_model

# Appended when the shopper did not ask for a person, so an ordinary catalog
# turn cannot end in a handoff.
_CATALOG_TURN_POLICY = (
    "\n<turn-policy>This is an ordinary catalog turn. Use the catalog tools, "
    "return the closest relevant pieces, and stop. A partial catalog match is "
    "still an answer; do not hand the shopper to a person.</turn-policy>"
)


def build_shopping_agent(*, allow_handoff: bool = True) -> Agent:
    """Return the configured Shopping agent.

    Reads the persona preamble and loaded skills from their ContextVars at
    construction time; both injections are no-ops when they are empty.

    Args:
        allow_handoff: Grant ``ask_a_person``. The Router passes False for an
            ordinary catalog turn, so a small result never becomes a handoff.
    """
    tools = [search_products, browse_department, compare_products]
    prompt = SHOPPING_SYSTEM_PROMPT
    if allow_handoff:
        tools.append(ask_a_person)
    else:
        prompt += _CATALOG_TURN_POLICY

    model_id, max_tokens = specialist_model("opus")
    return Agent(
        name="shopping",
        model=BedrockModel(
            model_id=model_id,
            max_tokens=max_tokens,
        ),
        system_prompt=inject_persona_preamble(inject_skills(prompt)),
        tools=tools,
    )
