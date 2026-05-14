"""
Orchestrator Agent - Routes queries to specialized agents with interleaved thinking
"""
from strands import Agent
from strands.models import BedrockModel
from .stock_keeper import inventory
from .curator import recommendation
from .value_analyst import pricing
from .experience_guide import support
from .style_advisor import search
from boutique_copy import ORCHESTRATOR_SYSTEM_PROMPT


# === CHALLENGE 4: Multi-Agent Orchestrator — START ===
# Requirements 2.4.6-2.4.8, 4.3.1. Routes every shopper query to exactly
# one specialist using the Strands "Agents as Tools" pattern. Uses Haiku
# 4.5 at temperature 0.0 for deterministic routing. Priority order
# (pricing > inventory > support > search > recommendation) is enforced
# by the system prompt in boutique_copy.ORCHESTRATOR_SYSTEM_PROMPT.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/closing-marcos-gap/agents/orchestrator.py pellier/backend/agents/orchestrator.py

ORCHESTRATOR_PROMPT = ORCHESTRATOR_SYSTEM_PROMPT


def create_orchestrator():
    """Create the orchestrator agent with all specialized agents as tools"""
    return Agent(
        model=BedrockModel(
            model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=4096,
            temperature=0.0,
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
# === CHALLENGE 4: Multi-Agent Orchestrator — END ===


# === WIRE IT LIVE (Lab 3) ===
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
            model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=4096,
            temperature=0.0,
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
# === END WIRE IT LIVE ===
