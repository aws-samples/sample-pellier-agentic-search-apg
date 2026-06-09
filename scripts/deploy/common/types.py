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
      ``<lambda-function-name>___`` (triple underscore), and the tool arguments
      ARE the event dict itself. The bare ``event['name']`` is NOT set here, so a
      naive ``event.get('name')`` returns "" and the call falls through to
      "Unknown tool". (dat403-proven contract:
      modules/05/strands/electrify_server.py:368-395.)
    * Direct / test invoke (and the ``list_tools`` probe): ``{"name","arguments"}``.

    Strategy: check the Gateway client_context first, strip the ``<function>___``
    prefix, treat the event as the argument payload; otherwise fall back to the
    flat ``{name, arguments}`` shape.
    """
    if getattr(context, "client_context", None):
        custom = getattr(context.client_context, "custom", {}) or {}
        prefixed = custom.get("bedrockAgentCoreToolName")
        if prefixed:
            fn = getattr(context, "function_name", "") or ""
            prefix = f"{fn}___"
            tool = prefixed[len(prefix):] if prefixed.startswith(prefix) else prefixed
            args = {k: v for k, v in event.items() if k not in ("name", "arguments")}
            if not args and isinstance(event.get("arguments"), dict):
                args = event["arguments"]
            return tool, args
    return event.get("name", ""), (event.get("arguments", {}) or {})
