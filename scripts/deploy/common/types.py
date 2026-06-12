"""
Shared types + invocation helpers for Pellier MCP servers.
Packaged into every MCP Lambda zip by deploy_lambda.py.
"""
from typing import Any, Optional, Tuple


class IdentityContext:
    """User identity from Cognito JWT."""
    def __init__(self, username: str = "", sub: str = "", email: str = None):
        self.username = username
        self.sub = sub
        self.email = email


def resolve_invocation(event: dict, context: Any) -> Tuple[str, dict]:
    """Return (tool_name, arguments) for BOTH MCP Lambda invocation paths.

    AgentCore Gateway and a direct/test invoke pass tools differently, and
    getting this wrong silently breaks EVERY Gateway-routed tool call:

    * Gateway path: the tool name arrives in
      ``context.client_context.custom['bedrockAgentCoreToolName']`` PREFIXED with
      ``<gateway-TARGET-name>___`` (triple underscore — e.g.
      ``pellier-concierge-experience-target___process_return``), and the tool
      arguments ARE the event dict itself. The bare ``event['name']`` is NOT set
      here, so a naive ``event.get('name')`` returns "" and the call falls
      through to "Unknown tool". NOTE the prefix is the Gateway target name,
      NOT the Lambda function name — dat403's electrify server stripped
      ``<function>___`` and got away with it only because its target and
      function shared a name; ours differ, so a function-name guess misses and
      the full prefixed string leaks through (box-verified 2026-06-12).
    * Direct / test invoke (and the ``list_tools`` probe): ``{"name","arguments"}``.

    Strategy: check the Gateway client_context first, strip everything up to
    the last ``___`` (robust to whatever prefix convention the Gateway uses),
    treat the event as the argument payload; otherwise fall back to the flat
    ``{name, arguments}`` shape.
    """
    if getattr(context, "client_context", None):
        custom = getattr(context.client_context, "custom", {}) or {}
        prefixed = custom.get("bedrockAgentCoreToolName")
        if prefixed:
            tool = prefixed.rsplit("___", 1)[-1]
            args = {k: v for k, v in event.items() if k not in ("name", "arguments")}
            if not args and isinstance(event.get("arguments"), dict):
                args = event["arguments"]
            return tool, args
    return event.get("name", ""), (event.get("arguments", {}) or {})
