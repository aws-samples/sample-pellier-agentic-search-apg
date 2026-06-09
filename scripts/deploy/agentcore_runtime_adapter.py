"""
AgentCore Runtime Adapter — production entrypoint for the Pellier orchestrator.

This file is what AgentCore Runtime *invokes* on every user turn. When a
client calls `bedrock-agentcore:InvokeAgentRuntime`, AgentCore spins up
(or reuses) a microVM, imports this module, and calls `invoke(payload)`.
Our job here is to:

  1. Connect to the MCP Gateway (created in step 4 of `deploy_all.sh`).
  2. Discover the registered tools dynamically — no hard-coded imports.
  3. Hand them to a Strands `Agent` that runs the orchestrator prompt.
  4. Return a JSON response the client can render.

NOTE: This Gateway-aware adapter is the ALTERNATE entrypoint. The path that
bootstrap actually deploys is the in-process orchestrator at
`pellier/backend/agentcore_runtime.py` (it runs tools in-process, so it does not
need to authenticate to the Gateway). This adapter remains for the advanced
"managed Gateway egress" track; if you deploy it, note that it currently calls
the Gateway over plain HTTP and would need a bearer token to satisfy the
Gateway's CUSTOM_JWT authorizer.

To deploy a BYO agent with the @aws/agentcore 0.18 CLI (CDK-based) — see
`scripts/deploy/deploy_all.sh` steps 6-7:

    npx -y @aws/agentcore@0.18.0 create --project-name pellier --no-agent ...
    agentcore add agent --name pellier_orchestrator --type byo \
        --code-location <dir> --entrypoint <this_file> \
        --authorizer-type CUSTOM_JWT --discovery-url <cognito> --allowed-clients <client>
    agentcore deploy -y --json   # from the project root (dir containing agentcore/)

The end-to-end bootstrap (Lambdas + Gateway + Runtime) is in
`scripts/deploy/deploy_all.sh`.

Reference docs:
    AgentCore Runtime overview:
        https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html
    InvokeAgentRuntime API:
        https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_runtime_InvokeAgentRuntime.html
    Strands Agents (open source):
        https://github.com/strands-agents/strands
    @aws/agentcore CLI:
        https://github.com/aws/agentcore-cli
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

# Imports are wrapped in try/except so this file stays *importable* on
# the workshop laptop where SDK extras may not be installed. Inside the
# AgentCore microVM the imports always succeed (requirements.txt pulls
# bedrock-agentcore + strands-agents + mcp). The module-level `app =
# None` fallback lets `python agentcore_runtime_adapter.py` print a
# friendly "install deps" message instead of a stack trace.
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from strands import Agent
    from strands.models import BedrockModel
    from strands.tools.mcp.mcp_client import MCPClient
    from mcp.client.streamable_http import streamablehttp_client

    # `BedrockAgentCoreApp` is the runtime SDK's WSGI-shaped wrapper —
    # `@app.entrypoint` registers a function as the invocation handler
    # and `app.run()` starts the local dev server.
    app = BedrockAgentCoreApp()

    # Both env vars are patched into the runtime's `envVars` in
    # agentcore/agentcore.json (deploy_all.sh step 6c). If GATEWAY_URL
    # is empty we surface a clear error rather than letting MCPClient
    # crash on an empty URL.
    GATEWAY_URL = os.environ.get("MCP_GATEWAY_URL", "")
    MODEL_ID = os.environ.get("AGENT_MODEL_ID", "global.anthropic.claude-opus-4-6-v1")

    # The orchestrator prompt is intentionally compact: AgentCore Runtime
    # bills on token usage, and the heavy lifting (search, pricing,
    # recommendations) happens inside the tools — not the model. We give
    # the agent just enough context to pick the right tool and shape the
    # final answer.
    ORCHESTRATOR_PROMPT = """You are the Pellier shopping assistant deployed on AgentCore.

You have access to tools discovered via MCP Gateway:
- Search tools: semantic_search, find_pieces_hybrid, inventory_health, low_stock, restock_product
- Pricing tools: find_deals, price_analysis, compare_products
- Recommendation tools: get_recommendations, trending_products
- Experience tools: process_return, escalate_to_stylist

RULES:
1. Call the right tool for the user's query, then return results directly.
2. Prefer find_pieces_hybrid when the shopper describes the piece in
   natural language; reach for semantic_search when speed matters more
   than rerank quality.
3. Write 1 short sentence before the products — answer the user's question.
4. NEVER mention tool names, agent names, or internal routing to the user.
5. When the user mentions a price limit, ALWAYS pass max_price to the tool.
6. If results include a JSON block, include it UNCHANGED in your response.
7. Call escalate_to_stylist only when no other tool can honestly answer
   (cultural dressing norms, body-image fit, out-of-policy returns).
"""

    @app.entrypoint
    def invoke(payload):
        """AgentCore Runtime entrypoint — invoked once per user turn.

        AgentCore calls this with whatever JSON the client sent in the
        `payload` field of `InvokeAgentRuntime`. We expect:
            {
                "prompt":    "<user message>",
                "session_id": "<stable id for the conversation>"
            }

        The session id flows into the agent's `trace_attributes` so every
        downstream call (Bedrock model invocation, Gateway tool call,
        Lambda execution) shows up under the same OpenTelemetry trace in
        CloudWatch — invaluable when debugging multi-step turns.

        Returns a dict that AgentCore serialises to JSON for the client.
        """
        prompt = payload.get("prompt", "Hello")
        session_id = payload.get("session_id", "runtime-session")

        # Hard fail with a clear message if the Gateway URL never made
        # it into our env. This is a config error, not a runtime error,
        # and surfacing it early saves participants from chasing ghosts.
        if not GATEWAY_URL:
            return {"response": "MCP_GATEWAY_URL not configured", "products": []}

        # MCPClient uses streamable HTTP transport (the production
        # transport for MCP — long-lived, supports server-sent events).
        # The transport factory is a callable so MCPClient can reconnect
        # on its own if the Gateway connection drops mid-turn.
        def _transport():
            return streamablehttp_client(GATEWAY_URL)

        mcp_client = MCPClient(_transport)

        # Building the agent inside `invoke` is intentional: each turn
        # gets a fresh MCPClient and a fresh tool list, so a Gateway
        # config change (a new tool, a renamed schema) takes effect on
        # the next invocation without redeploying the Runtime.
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID, max_tokens=4096, temperature=0.0),
            system_prompt=ORCHESTRATOR_PROMPT,
            tools=[mcp_client],
        )

        # OpenTelemetry attributes — these flow into the Bedrock and
        # Lambda spans and become searchable in the CloudWatch log
        # group `/aws/bedrock-agentcore/runtimes/<runtime-id>`.
        agent.trace_attributes = {
            "session.id": session_id,
            "runtime": "agentcore-lambda",
            "workshop": "pellier",
        }

        response = agent(prompt)
        return {"response": str(response), "products": []}

except ImportError as e:
    # Importable but non-functional outside the AgentCore microVM. The
    # `__main__` block below prints a hint so a developer running this
    # file locally without the SDK installed sees the actual fix.
    logger.info(f"AgentCore dependencies not installed: {e}")
    app = None


if __name__ == "__main__":
    # Local dev convenience — `app.run()` starts a development server
    # that mimics the AgentCore microVM, so you can curl the endpoint
    # before deploying. Inside AgentCore this branch is never reached;
    # the platform imports the module and calls `invoke` directly.
    if app:
        app.run()
    else:
        print("Install dependencies: pip install bedrock-agentcore strands-agents mcp")
