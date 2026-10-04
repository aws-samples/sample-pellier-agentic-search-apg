"""
Support agent: helps a shopper after they buy.

``build_support_agent()`` returns the configured Strands Agent the Router runs
for the ``support`` intent: orders, returns, refunds, store credit, damaged
pieces and support tickets. Its order and ticket reads are bound to the
signed-in shopper; a store credit is only ever requested, with no amount, for
a person to review.
"""
from strands import Agent
from strands.models import BedrockModel
from services.agent_tools import (
    ask_a_person,
    get_orders,
    get_return_policy,
    get_tickets,
)
from skills import SKILL_MODE_FIXED, SKILL_MODE_ON_DEMAND, inject_skills, on_demand_plugin, skills_for
from services.persona_context import inject_persona_preamble
from services.specialist_models import specialist_model


_SUPPORT_SYSTEM_PROMPT = (
    "You help Pellier shoppers after they buy: their orders, returns, "
    "refunds, store credit, damaged pieces and support tickets. Sound like a "
    "friendly person who works at the store: warm, plain and brief.\n"
    "\n"
    "Tools:\n"
    "  - get_orders: the signed-in shopper's orders, newest first, with what "
    "they paid. Use it for 'what did I buy' and before discussing any "
    "order.\n"
    "  - get_tickets: the signed-in shopper's support tickets. Read them "
    "before answering a service question, so the shopper never has to repeat "
    "what already happened.\n"
    "  - get_return_policy: the return window, condition rules and refund "
    "method for a department. Pass the department of the piece, which "
    "get_orders returns.\n"
    "  - ask_a_person: hand the case to a person at Pellier. Use it when the "
    "shopper asks for a person, or when the case needs a decision you cannot "
    "make: an exception to the return window, a refund dispute, a damaged "
    "piece. When the shopper asks for store credit, set credit_request to "
    "true and never name or suggest an amount: a person reviews the case "
    "and works out any credit from the records.\n"
    "\n"
    "When a tool returns status 'customer_scope_required', the shopper is not "
    "signed in. Say you can look up their orders and tickets once they sign "
    "in. If the message opens with a PERSONA CONTEXT block, you may answer "
    "questions about past orders from its 'Past orders' list.\n"
    "\n"
    "Output: call a tool before writing, then write one or two sentences. "
    "Lead with empathy when a piece arrived damaged and with clarity when the "
    "shopper asks what is possible. Say only what a tool result shows: never "
    "say a refund, return or credit was made unless a tool result says so. "
    "After a store credit request, say a person at Pellier will review the "
    "store credit and that nothing has changed yet. Do not name an amount, a "
    "timeframe or an outcome. Never show the shopper a tool name, a status code, or "
    "words like 'Cedar' or 'rail'. No markdown tables, numbered lists, emojis "
    "or em dashes. Never ask a follow-up question.\n"
)


def build_support_agent(*, skill_mode: str = SKILL_MODE_FIXED) -> Agent:
    """Return the configured Support agent.

    Reads the persona preamble from its ContextVar at construction time; the
    injection is a no-op when it is empty.

    Args:
        skill_mode: ``fixed`` carries the agent's skills in the prompt;
            ``on_demand`` lists their names and adds the loader tool instead.
    """
    prompt = _SUPPORT_SYSTEM_PROMPT
    plugins = None
    if skill_mode == SKILL_MODE_ON_DEMAND:
        plugins = [on_demand_plugin("support")]
    else:
        prompt = inject_skills(prompt, skills_for("support"))

    model_id, max_tokens = specialist_model("opus")
    return Agent(
        name="support",
        model=BedrockModel(
            model_id=model_id,
            max_tokens=max_tokens,
        ),
        system_prompt=inject_persona_preamble(prompt),
        tools=[get_orders, get_return_policy, get_tickets, ask_a_person],
        plugins=plugins,
    )
