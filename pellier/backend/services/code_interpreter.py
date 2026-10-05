"""
AgentCore Code Interpreter — Dynamic Python analytics via sandboxed execution.

Creates an analytics agent that can write and execute Python code against
live product data. The agent uses AgentCore Code Interpreter for secure,
sandboxed code execution — no local Python process, no security risks.

Use cases:
  - "Show me a price distribution chart for home decor"
  - "What's the average rating by category?"
  - "Calculate the correlation between price and reviews"
  - "Generate a CSV export of trending products"
"""
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def create_analytics_agent():
    """
    Create an analytics agent with Code Interpreter capabilities.

    The agent combines:
    - AgentCore Code Interpreter for sandboxed Python execution
    - Product search tools for data retrieval
    - The configured Bedrock editorial model for data-analysis reasoning

    The agent can write Python code that uses pandas, matplotlib, and
    standard libraries to analyze product data, generate charts, and
    compute statistics — all executed in a secure AgentCore sandbox.

    Returns:
        Strands Agent with Code Interpreter, or None if not available
    """
    if not getattr(settings, 'AGENTCORE_RUNTIME_ENDPOINT', None):
        logger.info("AGENTCORE_RUNTIME_ENDPOINT not set — Code Interpreter unavailable")
        return None

    try:
        from strands import Agent
        from strands.models import BedrockModel
        from strands_tools.code_interpreter import AgentCoreCodeInterpreter
        from services.agent_tools import (
            find_pieces,
            whats_trending,
            price_intelligence,
            floor_check,
        )

        # Initialize Code Interpreter with sandboxed execution
        code_interpreter = AgentCoreCodeInterpreter(
            region_name=settings.aws_region_resolved,
        )

        agent = Agent(
            model=BedrockModel(
                model_id=settings.BEDROCK_CHAT_MODEL,
                # Opus 5 thinks by default and max_tokens caps thinking +
                # answer together; 16000 keeps this tool-using agent from
                # truncating a reply mid-turn.
                max_tokens=16000,
            ),
            system_prompt=(
                "You are Pellier's Data Analyst. You help users understand "
                "product data through analysis, visualization, and computation.\n\n"
                "WORKFLOW:\n"
                "1. Use product tools (find_pieces, whats_trending, "
                "price_intelligence) to retrieve data\n"
                "2. Use the code_interpreter tool to write and execute Python code "
                "for analysis, charts, and calculations\n"
                "3. Available libraries: pandas, matplotlib, numpy, statistics\n\n"
                "RULES:\n"
                "- Always retrieve real data first, then analyze it with code\n"
                "- For charts, use matplotlib and return the figure\n"
                "- For statistics, show the computation and result\n"
                "- Keep code clean and well-commented"
            ),
            tools=[
                code_interpreter,
                find_pieces,
                whats_trending,
                price_intelligence,
                floor_check,
            ],
        )

        logger.info("✅ Analytics agent with Code Interpreter created")
        return agent

    except ImportError as e:
        logger.warning(f"Code Interpreter dependencies not available: {e}")
        logger.warning("Install with: pip install strands-agents-tools")
        return None
    except Exception as e:
        logger.warning(f"Analytics agent creation failed: {e}")
        return None
