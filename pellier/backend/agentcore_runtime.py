"""
AgentCore Runtime — deployment entrypoint (Builder's Session + Workshop C5).

Wraps the pre-applied Strands orchestrator for execution in an AgentCore
Runtime container. Bootstrap renders ``agentcore.json`` from
``agentcore.json.template`` and runs ``agentcore deploy`` (the new
@aws/agentcore Node CLI — https://github.com/aws/agentcore-cli) before
participants arrive; in-room they read this file and invoke via
``POST /api/agent/chat`` with ``USE_AGENTCORE_RUNTIME=true``.

Deploy (bootstrap / instructor):
    cd pellier/backend
    envsubst < agentcore.json.template > agentcore.json
    envsubst < aws-targets.json.template > aws-targets.json
    agentcore deploy -y --json
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
        """AgentCore Runtime entrypoint — orchestrator in a managed microVM."""
        prompt = (payload or {}).get("prompt", "")
        session_id = (payload or {}).get("session_id", "runtime-session")
        user_id = (payload or {}).get("user_id", "anonymous")

        from agents.orchestrator import create_orchestrator

        orchestrator = create_orchestrator()
        if orchestrator is None:
            return {
                "response": (
                    "The orchestrator isn't wired up yet. Complete the "
                    "orchestrator challenge or use the solutions copy."
                ),
                "products": [],
            }

        try:
            orchestrator.trace_attributes = {
                "session.id": session_id,
                "user.id": user_id or "anonymous",
                "runtime": "agentcore-managed",
                "workshop": "pellier",
            }
        except Exception:  # pragma: no cover
            pass

        response = orchestrator(prompt)
        return {"response": str(response), "products": []}

except ImportError:
    logger.info("bedrock-agentcore not installed — Runtime entrypoint disabled")
    app = None  # type: ignore[misc, assignment]


if __name__ == "__main__":
    if app:
        app.run()
    else:
        print("Install bedrock-agentcore to run: pip install bedrock-agentcore")
