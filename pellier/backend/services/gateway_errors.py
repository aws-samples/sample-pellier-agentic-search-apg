"""Preserve explicit Gateway protocol errors without request headers or tokens."""
from __future__ import annotations


async def read_gateway_error_response(response) -> None:
    # MCP raises for a streamed 403 before consuming its JSON-RPC body. Read it
    # while the response is open so the request/response policy phases survive.
    if response.is_error:
        await response.aread()


def gateway_error_text(error: BaseException | str) -> str:
    children = getattr(error, "exceptions", None)
    if children:
        return " ".join(gateway_error_text(child) for child in children)
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
            message = (payload.get("error") or {}).get("message")
            if isinstance(message, str):
                return message
        except (ValueError, TypeError, AttributeError, RuntimeError):
            pass
    return str(error)
