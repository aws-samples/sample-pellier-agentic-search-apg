"""
Orchestrator — Pellier's Pattern I (Agents-as-Tools) routing agent.

This is **not** the Dispatcher. The codebase has two routing patterns:

  * **Dispatcher (Pattern III)** — Pellier's production path.
    Implemented inline in ``services/chat.py`` as a deterministic
    intent-keyword classifier that picks one specialist directly.
    No separate Agent object — the Dispatcher *is* the routing
    function, so *routing* costs no model call. The turn still makes
    two Bedrock calls: the skill router (Sonnet, ``skills/router.py``)
    picks which skills to inject, then the specialist runs. Triage
    short-circuits (greetings, meta, thanks) make zero.

  * **Orchestrator (Pattern I)** — Pellier Labs' "Agents as Tools"
    teaching surface (this file). A Sonnet 5 Agent that sees each
    specialist as a ``@tool`` (search, recommendation, pricing,
    inventory, support) and picks one to call. That routing agent is
    an extra model call on top of the skill router and the specialist.
    Useful for teaching the AaT pattern; intentionally NOT Pellier's
    path because the routing call adds latency and a paraphrase cycle
    the production storefront doesn't want.

If you're looking for Pellier's routing logic, see
``services/chat.py``'s ``_run_dispatcher_pattern`` branch and the
intent classifier at ``classify_intent``.
"""
from strands import Agent
from strands.models import BedrockModel
from .stock_keeper import inventory
from .curator import recommendation
from .value_analyst import pricing
from .experience_guide import support
from .style_advisor import search
from pellier_copy import ORCHESTRATOR_SYSTEM_PROMPT
from config import settings


# === REFERENCE: Multi-Agent Orchestrator — START ===
# Requirements 2.4.6-2.4.8, 4.3.1. Routes every shopper query to exactly
# one specialist using the Strands "Agents as Tools" pattern. Uses the Sonnet
# router profile without a temperature override. Priority order
# (pricing > inventory > support > search > recommendation) is enforced
# by the system prompt in pellier_copy.ORCHESTRATOR_SYSTEM_PROMPT.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/closing-marcos-gap/agents/orchestrator.py pellier/backend/agents/orchestrator.py

ORCHESTRATOR_PROMPT = ORCHESTRATOR_SYSTEM_PROMPT


def create_orchestrator():
    """Create the orchestrator agent with all specialized agents as tools"""
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_ROUTER_MODEL,
            max_tokens=settings.ROUTER_MAX_TOKENS_SONNET,
        ),
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            search,
            recommendation,
            pricing,
            inventory,
            support,
        ],
    )
# === REFERENCE: Multi-Agent Orchestrator — END ===


GUARDRAILS_PROMPT_SUFFIX = """

GUARDRAILS (ACTIVE):
- Do NOT recommend products related to weapons, alcohol, or tobacco
- Do NOT provide medical, legal, or financial advice
- Flag inappropriate requests politely
- Keep all responses family-friendly
- If a user asks for restricted content, respond: "I can't help with that, but I'd love to help you find something else!"
"""


def create_guarded_orchestrator():
    """Create a guardrails-aware orchestrator that adds content moderation
    rules to the system prompt and can filter responses through Bedrock Guardrails."""
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_ROUTER_MODEL,
            max_tokens=settings.ROUTER_MAX_TOKENS_SONNET,
        ),
        system_prompt=ORCHESTRATOR_PROMPT + GUARDRAILS_PROMPT_SUFFIX,
        tools=[
            search,
            recommendation,
            pricing,
            inventory,
            support,
        ],
    )
