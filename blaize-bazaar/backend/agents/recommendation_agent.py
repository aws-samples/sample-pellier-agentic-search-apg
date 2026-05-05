"""
Product Recommendation Agent — suggests pieces based on the shopper's
preferences and, when a persona is active, their LTM + past orders.

Exposes two surfaces that share one agent construction path:

1. ``build_recommendation_agent()`` — factory returning a configured
   ``Agent`` instance. Used by the Storefront dispatcher (Pattern III)
   and the Atelier Graph pattern (Pattern II). Reads the persona
   preamble and skill ContextVars at construction time, same as the
   ``@tool`` path does.

2. ``recommendation(query)`` — ``@tool``-decorated wrapper used by the
   Atelier's Agents-as-Tools orchestrator (Pattern I). Delegates to
   the factory so both surfaces produce identical agents.
"""
import json
import re

from strands import Agent, tool
from strands.models import BedrockModel
from config import settings
from services.agent_tools import (
    find_pieces,
    whats_trending,
    side_by_side,
    explore_collection,
)
from skills import inject_skills
from services.persona_context import inject_persona_preamble
from boutique_copy import RECOMMENDATION_SYSTEM_PROMPT


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


def build_recommendation_agent() -> Agent:
    """Return a configured Recommendation specialist Agent.

    Reads the current turn's persona preamble and loaded skills from
    their ContextVars at construction time. Callers are responsible
    for setting those ContextVars before invoking this factory — the
    chat pipeline in ``services/chat.py`` does so on every turn.

    === CHALLENGE 3: START ===
    inject_skills() and inject_persona_preamble() are no-ops when
    their ContextVars are empty (the common case in atelier smoke
    tests and anonymous sessions), so this factory produces the same
    agent as before in those scenarios.
    === CHALLENGE 3: END ===
    """
    # Curator — Sonnet 4.6 at 0.4. Recommendations carry "taste";
    # skills shape voice. Warm model, warm temperature.
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_SONNET_MODEL,
            max_tokens=4096,
            temperature=0.4,
        ),
        system_prompt=inject_persona_preamble(
            inject_skills(RECOMMENDATION_SYSTEM_PROMPT)
        ),
        tools=[
            find_pieces,
            whats_trending,
            side_by_side,
            explore_collection,
        ],
    )


@tool
def recommendation(query: str) -> str:
    """
    Provide personalized product recommendations based on user preferences.

    Args:
        query: User's product inquiry

    Returns:
        Agent response with product recommendations

    ⏩ SHORT ON TIME? Run:
       cp solutions/module2/agents/recommendation_agent.py blaize-bazaar/backend/agents/recommendation_agent.py
    """
    try:
        tool_results = []
        agent = build_recommendation_agent()

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
        return json.dumps({"error": f"Recommendation agent error: {str(e)}"})
