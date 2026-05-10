"""
AgentCore Runtime — Lambda deployment entrypoint for Lab 4e.

Wire It Live: Participants create the @app.entrypoint handler that wraps
the orchestrator for execution in an AgentCore Runtime Lambda microVM.

Deploy with:
    agentcore configure
    agentcore launch
"""
import logging

logger = logging.getLogger(__name__)


# === CHALLENGE 5: AgentCore Runtime — START ===
# TODO: Implement AgentCore Runtime entrypoint
#
# Steps:
#   1. Import BedrockAgentCoreApp from bedrock_agentcore.runtime
#   2. Create app = BedrockAgentCoreApp()
#   3. Define @app.entrypoint handler that:
#      - Extracts prompt and session_id from payload
#      - Creates orchestrator via create_orchestrator()
#      - Invokes orchestrator with the prompt
#      - Returns {"response": str(response), "products": []}
#   4. Handle ImportError (bedrock-agentcore not installed)
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/module3/services/agentcore_runtime.py pellier/backend/agentcore_runtime.py
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    app = BedrockAgentCoreApp()
    # TODO: Add @app.entrypoint handler here
except ImportError:
    logger.info("bedrock-agentcore not installed — Runtime entrypoint disabled")
    app = None
# === CHALLENGE 5: AgentCore Runtime — END ===


if __name__ == "__main__":
    if app:
        app.run()
    else:
        print("Install bedrock-agentcore to run: pip install bedrock-agentcore")
