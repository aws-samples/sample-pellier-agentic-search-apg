"""
AgentCore Runtime — deployment entrypoint (Builder's Session + Workshop C5).

Wraps the pre-applied Strands orchestrator for execution in an AgentCore
Runtime container. This file is the BYO entrypoint deployed by the new
@aws/agentcore Node CLI (0.18, CDK-based — https://github.com/aws/agentcore-cli):
bootstrap scaffolds a project, registers this file as a BYO agent, patches in
the execution role + env vars, and `agentcore deploy`s it before participants
arrive; in-room they read this file and invoke via ``POST /api/agent/chat``
with ``USE_AGENTCORE_RUNTIME=true``.

Deploy (bootstrap / instructor) — see scripts/deploy/deploy_all.sh steps 6-7
and scripts/provision_agentcore_end_to_end.py:_deploy_runtime_via_cli:
    npx -y @aws/agentcore@0.18.0 create --project-name pellier --no-agent ...
    agentcore add agent --name pellier_orchestrator --type byo \\
        --code-location pellier/backend --entrypoint agentcore_runtime.py \\
        --authorizer-type CUSTOM_JWT --discovery-url <cognito> --allowed-clients <client>
    # patch executionRoleArn + envVars into agentcore/agentcore.json, then:
    agentcore deploy -y --json   # from the project root (dir containing agentcore/)
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
