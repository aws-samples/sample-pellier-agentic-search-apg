"""
AgentCore Runtime - deployment entrypoint for the managed execution path.

Wraps the dispatcher for execution in an AgentCore Runtime container. This
file is the BYO entrypoint deployed by the pinned @aws/agentcore Node CLI
(CDK-based — https://github.com/aws/agentcore-cli). Bootstrap renders one
declarative project containing Runtime, Memory, Gateway, targets, and Policy,
then runs ``agentcore validate`` and ``agentcore deploy`` before participants
arrive. In-room they inspect the project and invoke via
``POST /api/agent/chat`` with ``USE_AGENTCORE_RUNTIME=true``.

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

Deploy (bootstrap / instructor):
    python3 scripts/provision_agentcore_end_to_end.py --repo-path "$PWD"

The provisioner renders ``.agentcore-project/pellier/agentcore/agentcore.json``
and invokes the pinned CLI. AgentCore CDK injects discovery variables for
project resources into this Runtime.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Bridge CLI-injected resource discovery names BEFORE the first `config`
# import. Settings are built once at import time. The CLI names the variables
# after the project's resources, so they are resolved by shape: a deployment
# with suffixed names injects different variables than the default one.
from services.runtime_env import bridge_cli_injected_names

os.environ.update(bridge_cli_injected_names(os.environ))

# The content digest of the sources packaged into THIS deployment, injected by
# scripts/deploy/render_agentcore_project.py. Echoed on every response so the
# caller can compare it against a digest of their own working tree and prove
# which revision Runtime actually executed -- the invoke response carries no
# version of its own, and `qualifier=DEFAULT` is an alias that reads the same
# for yesterday's baseline as for today's package.
#
# Empty when a runtime was deployed before this mechanism existed. Callers must
# render that as unknown, never as a mismatch.
_build_fingerprint = os.environ.get("PELLIER_BUILD_FINGERPRINT", "").strip()


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _answered(
    dispatcher: Any, response: Any, *, rail: str, stop_reason: str, remembered: list,
) -> Dict[str, Any]:
    """The Runtime's reply for a completed turn: the answer and what the agent was given."""
    return {
        "response": str(response),
        "products": list(dispatcher.last_products or []),
        "rail": rail,
        "intent": dispatcher.last_intent,
        "specialist": dispatcher.last_specialist,
        "model": dispatcher.last_model_id,
        "gateway_tools": list(dispatcher.last_tool_names),
        # Tools the routed agent asked for that the Gateway does not list for
        # this caller. The agent ran without them; the Builder view names them.
        "unpublished_tools": list(dispatcher.last_unpublished_tools),
        "tool_calls": list(dispatcher.last_tool_events or []),
        # The skills the routed agent's prompt carried, reported from the
        # source. The app renders this list and asserts nothing of its own.
        "skills": list(dispatcher.last_skills or []),
        # The AgentCore Memory records whose preferences went ahead of the
        # prompt, reported the same way.
        "remembered": list(remembered),
        # How the agent's turn ended, for the receipt. A truncated turn
        # never reaches here; it is rejected before.
        "stop_reason": stop_reason,
        "orchestration": "dispatcher",
        "build_fingerprint": _build_fingerprint,
    }


# Withhold prompts, completions, and tool results from every span this
# container exports. Strands' tracer reads OTEL_SEMCONV_STABILITY_OPT_IN once,
# when it is constructed, so the token must be in place before any module that
# can build one is imported. app.py does this in its lifespan; the Runtime never
# runs that lifespan, and the platform's own instrumentation would otherwise
# ship the shopper's words in clear text.
from services.otel_content_redaction import apply_model_content_redaction

apply_model_content_redaction(
    enabled=_env_flag("OTEL_REDACT_MODEL_CONTENT", default=True)
)

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
        """Handle the prompt, identity/session ids, and prior Memory history.

        ``preferences`` are the user-preference records the app read from
        AgentCore Memory for the signed-in customer, each a ``record_id`` and a
        ``preference``. They go ahead of the prompt as labelled context, and
        the ids of the ones sent come back as ``remembered``. The Runtime reads
        no customer record from Aurora.
        """
        prompt = (payload or {}).get("prompt", "")
        session_id = (
            getattr(context, "session_id", None)
            or (payload or {}).get("session_id")
            or "runtime-session"
        )
        user_id = (payload or {}).get("user_id", "anonymous")
        history = (payload or {}).get("history", [])
        turn_id = (payload or {}).get("turn_id")
        customer_id = (payload or {}).get("customer_id")
        from services.conversation_context import (
            build_conversation_prompt,
            build_remembered_prompt,
            remembered_preferences,
        )

        remembered = remembered_preferences((payload or {}).get("preferences"))

        # Tools execute only through Gateway MCP under the caller's identity.
        # A managed Runtime invocation must never degrade into local tools.
        rail = "runtime"
        access_token = _bearer_token_from(context)
        if not access_token:
            logger.warning(
                "Managed Runtime invocation rejected: Cognito bearer token missing"
            )
            return {
                "error": "authentication_required",
                "products": [],
                "rail": rail,
            }

        if not os.environ.get("AGENTCORE_GATEWAY_URL"):
            logger.error("Managed Runtime invocation rejected: Gateway URL missing")
            return {
                "error": "managed_gateway_unavailable",
                "products": [],
                "rail": rail,
            }

        from services.agentcore_gateway import create_gateway_dispatcher

        dispatcher = create_gateway_dispatcher(
            access_token=access_token,
            customer_id=customer_id,
            routing_query=prompt,
        )
        if dispatcher is None:
            return {
                "error": "managed_gateway_unavailable",
                "products": [],
                "rail": rail,
            }
        rail = "gateway-mcp"

        try:
            dispatcher.trace_attributes = {
                "session.id": session_id,
                "turn.id": str(turn_id or ""),
                "user.id": user_id or "anonymous",
                "runtime": "agentcore-managed",
                "workshop": "pellier",
            }
        except Exception:  # pragma: no cover
            pass

        response = dispatcher(
            build_remembered_prompt(build_conversation_prompt(prompt, history), remembered)
        )
        stop_reason = str(getattr(response, "stop_reason", "") or "")
        if stop_reason == "max_tokens":
            logger.warning(
                "Managed Runtime output rejected because the model reached max_tokens"
            )
            return {
                "error": "runtime_output_truncated",
                "products": list(dispatcher.last_products or []),
                "rail": rail,
                "tool_calls": list(dispatcher.last_tool_events or []),
                "build_fingerprint": _build_fingerprint,
            }
        return _answered(dispatcher, response, rail=rail, stop_reason=stop_reason,
                         remembered=[item["record_id"] for item in remembered])

except ImportError:
    logger.info("bedrock-agentcore not installed — Runtime entrypoint disabled")
    app = None  # type: ignore[misc, assignment]


if __name__ == "__main__":
    if app:
        app.run()
    else:
        print("Install bedrock-agentcore to run: pip install bedrock-agentcore")
