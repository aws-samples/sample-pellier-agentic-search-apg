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


# === CHALLENGE · Stock Keeper · system prompt: START ===
# WORKSHOP_EXERCISE_STUB
#
# Stock Keeper's voice. Haiku 4.5 at 0.0 — the model doesn't need
# ornament, it needs direction. Write a system prompt that:
#
#   1. Names the agent ("You are Pellier's Stock Keeper.")
#   2. Lists the three tools and when to use each:
#        - floor_check     → overall stock + warehouse health
#        - running_low     → items needing restock, ranked by rating
#        - restock_shelf   → only when user provides product_id + quantity
#   3. Sets output discipline (Haiku at 0.0 respects it):
#        - ALWAYS call a tool first, never write text before tool call
#        - After tool results: 1–2 short sentences, no markdown tables,
#          no numbered lists, no emojis
#        - Products render as cards — don't list them in text
#        - If a tool returns zero/error, say what went wrong briefly
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/module2/agents/inventory_agent.py pellier/backend/agents/inventory_agent.py
#
# Verify locally:
#    cd pellier/backend
#    pytest tests/test_inventory_agent.py -v
#
# Verify live:
#    Click Marco's Turn 4 pill. Stock Keeper answers with the
#    warehouse breakdown (assuming floor_check is also wired).

_INVENTORY_SYSTEM_PROMPT = (
    "You are Pellier's Stock Keeper — in stub state. "
    "Replace this system prompt with the full voice (see the CHALLENGE "
    "block above in this file, or copy the solution)."
)

# Atelier reads this flag to render the "Your turn" pill on the
# Stock Keeper agent card and the dashed-border state on the three
# inventory tools. Flip to False once the system prompt is authored
# (or, equivalently, once the cp solution command has been run and
# the real prompt replaces the stub above).
_INVENTORY_AGENT_STUBBED = True

# === CHALLENGE · Stock Keeper · system prompt: END ===


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
