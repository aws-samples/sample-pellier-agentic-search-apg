"""
AgentCore Runtime — deployment entrypoint (Builder's Session + Workshop C5).

Wraps the orchestrator for execution in an AgentCore Runtime container. This
file is the BYO entrypoint deployed by the new @aws/agentcore Node CLI (0.18,
CDK-based — https://github.com/aws/agentcore-cli): bootstrap scaffolds a
project, registers this file as a BYO agent, patches in the execution role +
env vars, and `agentcore deploy`s it before participants arrive; in-room they
read this file and invoke via ``POST /api/agent/chat`` with
``USE_AGENTCORE_RUNTIME=true``.

Inside the container the orchestrator's tools run over the managed AgentCore
GATEWAY (MCP over streamable HTTP, JWT passthrough) — NOT in-process. The
in-process specialists in ``agents/`` call ``services.agent_tools``, whose
database service is injected only by the FastAPI startup hook
(``app.py:set_db_service``); that hook never runs here, so every in-process
tool would fail with "Database service not initialized" (box-verified
2026-06-12 — the smoke's only symptom was the LLM apologizing about a
"temporary database issue"). The caller's Cognito access token reaches this
handler because provisioning allowlists the ``Authorization`` header on the
runtime (``requestHeaderAllowlist`` patch), so identity passes through:
shopper → Runtime → Gateway → Cedar → MCP Lambda, one JWT end to end.

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
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# The container's envVars carry MCP_GATEWAY_URL (the name deploy_all.sh and
# the provisioner patch into agentcore.json) but config.py reads
# AGENTCORE_GATEWAY_URL. Bridge BEFORE the first `config` import below —
# `settings` is built once at config import time and would otherwise never
# see the Gateway URL (the exact silent failure this entrypoint shipped with).
if os.environ.get("MCP_GATEWAY_URL") and not os.environ.get("AGENTCORE_GATEWAY_URL"):
    os.environ["AGENTCORE_GATEWAY_URL"] = os.environ["MCP_GATEWAY_URL"]

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    def _bearer_token_from(context: Any) -> Optional[str]:
        """Extract the caller's raw Cognito access token, if forwarded.

        The runtime data plane forwards only allowlisted headers; provisioning
        allowlists ``Authorization``, and the SDK surfaces it on the
        ``RequestContext`` passed as the handler's second argument (and in
        ``BedrockAgentCoreContext`` as a fallback for older call shapes).
        """
        headers: Dict[str, str] = {}
        if context is not None and getattr(context, "request_headers", None):
            headers = context.request_headers or {}
        if not headers:
            try:
                from bedrock_agentcore.runtime import BedrockAgentCoreContext

                headers = BedrockAgentCoreContext.get_request_headers() or {}
            except Exception:  # pragma: no cover - SDK surface drift
                headers = {}
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip() or None
        return None

    @app.entrypoint
    def invoke(payload: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """AgentCore Runtime entrypoint — orchestrator in a managed microVM."""
        prompt = (payload or {}).get("prompt", "")
        session_id = (payload or {}).get("session_id", "runtime-session")
        user_id = (payload or {}).get("user_id", "anonymous")

        # Gateway rail first: tools execute in the MCP Lambdas under the
        # caller's identity (JWT passthrough). The in-process orchestrator is
        # a conversational fallback only — its catalog tools have no database
        # service in this container.
        rail = "in-process"
        orchestrator = None
        access_token = _bearer_token_from(context)
        if access_token:
            from services.agentcore_gateway import create_gateway_orchestrator

            orchestrator = create_gateway_orchestrator(access_token=access_token)
            if orchestrator is not None:
                rail = "gateway-mcp"
        if orchestrator is None:
            logger.warning(
                "Gateway rail unavailable (token=%s, gateway_url=%s) — "
                "falling back to in-process orchestrator",
                "present" if access_token else "missing",
                os.environ.get("AGENTCORE_GATEWAY_URL", ""),
            )
            from agents.orchestrator import create_orchestrator

            orchestrator = create_orchestrator()

        if orchestrator is None:
            return {
                "response": (
                    "The orchestrator isn't wired up yet. Complete the "
                    "orchestrator challenge or use the solutions copy."
                ),
                "products": [],
                "rail": rail,
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
        return {"response": str(response), "products": [], "rail": rail}

except ImportError:
    logger.info("bedrock-agentcore not installed — Runtime entrypoint disabled")
    app = None  # type: ignore[misc, assignment]


if __name__ == "__main__":
    if app:
        app.run()
    else:
        print("Install bedrock-agentcore to run: pip install bedrock-agentcore")
