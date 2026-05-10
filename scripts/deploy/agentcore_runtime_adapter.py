"""
AgentCore Runtime Adapter — Production entrypoint for Blaize Bazaar orchestrator.

Runs inside an AgentCore Lambda microVM. Discovers tools via MCP Gateway
and routes queries through the orchestrator agent.

Deploy with:
    agentcore configure --name blaize_orchestrator ...
    agentcore launch --agent blaize_orchestrator ...
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from strands import Agent
    from strands.models import BedrockModel
    from strands.tools.mcp.mcp_client import MCPClient
    from mcp.client.streamable_http import streamablehttp_client

    app = BedrockAgentCoreApp()

    GATEWAY_URL = os.environ.get("MCP_GATEWAY_URL", "")
    MODEL_ID = os.environ.get("AGENT_MODEL_ID", "global.anthropic.claude-opus-4-7")

    ORCHESTRATOR_PROMPT = """You are the Blaize Bazaar shopping assistant deployed on AgentCore.

You have access to tools discovered via MCP Gateway:
- Search tools: semantic_search, inventory_health, low_stock, restock_product
- Pricing tools: find_deals, price_analysis, compare_products
- Recommendation tools: get_recommendations, trending_products

RULES:
1. Call the right tool for the user's query, then return results directly.
2. Write 1 short sentence before the products — answer the user's question.
3. NEVER mention tool names, agent names, or internal routing to the user.
4. When the user mentions a price limit, ALWAYS pass max_price to the tool.
5. If results include a JSON block, include it UNCHANGED in your response.
"""

    @app.entrypoint
    def invoke(payload):
        """AgentCore Runtime entrypoint."""
        prompt = payload.get("prompt", "Hello")
        session_id = payload.get("session_id", "runtime-session")

        if not GATEWAY_URL:
            return {"response": "MCP_GATEWAY_URL not configured", "products": []}

        # Create MCP transport to Gateway
        def _transport():
            return streamablehttp_client(GATEWAY_URL)

        mcp_client = MCPClient(_transport)

        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, max_tokens=4096, temperature=0.0),
            system_prompt=ORCHESTRATOR_PROMPT,
            tools=[mcp_client],
        )
        agent.trace_attributes = {
            "session.id": session_id,
            "runtime": "agentcore-lambda",
            "workshop": "blaize-bazaar",
        }

        response = agent(prompt)
        return {"response": str(response), "products": []}

except ImportError as e:
    logger.info(f"AgentCore dependencies not installed: {e}")
    app = None


if __name__ == "__main__":
    if app:
        app.run()
    else:
        print("Install dependencies: pip install bedrock-agentcore strands-agents mcp")
