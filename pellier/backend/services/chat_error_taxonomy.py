"""Safe error envelopes for Pellier streaming chat surface."""

from __future__ import annotations

from typing import Any, Dict


_POLICY_DENIAL_MARKERS = (
    "authorizeactionexception",
    "accessdeniedexception",
    "explicit deny",
    "not authorized",
    "authorization failed",
    "not allowed due to policy",
    "policy enforcement",
    "access denied by policy",
)
_AUTH_MARKERS = (
    "expiredtoken",
    "token expired",
    "expired token",
    "invalid bearer",
    "invalid token",
    "jwt authorizer",
    "http 401",
    "401 unauthorized",
    "authentication failed",
    "authentication_failed",
    "authentication_required",
    "customer_identity_unmapped",
    "customer_scope_mismatch",
)
_RATE_LIMIT_MARKERS = (
    "throttlingexception",
    "throttled",
    "too many requests",
    "rate limit",
    "http 429",
)
_TIMEOUT_MARKERS = (
    "execution timed out",
    "timeout",
    "timed out",
    "modeltimeoutexception",
)
_UNAVAILABLE_MARKERS = (
    "serviceunavailableexception",
    "service unavailable",
    "runtime_not_configured",
    "runtime_unavailable",
    "managed_gateway_unavailable",
    "auth_unavailable",
    "auth_not_configured",
    "connection refused",
    "connection reset",
    "endpointconnectionerror",
    "could not connect",
    "temporarily unavailable",
)


def _error_text(error: object) -> str:
    if isinstance(error, BaseException):
        children = getattr(error, "exceptions", None)
        if children:
            return "; ".join(_error_text(child) for child in children)
        return f"{error.__class__.__name__}: {error}"
    return str(error or "")


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(marker in normalized for marker in markers)


def classify_chat_error(error: object) -> Dict[str, Any]:
    """Classify an internal failure without exposing provider details."""

    text = _error_text(error)
    if _contains_any(text, _POLICY_DENIAL_MARKERS):
        code, message, retryable = (
            "policy_denied",
            "Request blocked by the active policy.",
            False,
        )
    elif _contains_any(text, _AUTH_MARKERS):
        code, message, retryable = (
            "authentication_required",
            "Authentication must be refreshed before this request can continue.",
            False,
        )
    elif _contains_any(text, _RATE_LIMIT_MARKERS):
        code, message, retryable = (
            "rate_limited",
            "The service is receiving too many requests.",
            True,
        )
    elif _contains_any(text, _TIMEOUT_MARKERS):
        code, message, retryable = (
            "request_timeout",
            "The request exceeded its processing window.",
            True,
        )
    elif _contains_any(text, _UNAVAILABLE_MARKERS):
        code, message, retryable = (
            "service_unavailable",
            "A required service is temporarily unavailable.",
            True,
        )
    else:
        code, message, retryable = (
            "request_failed",
            "The request could not be completed.",
            True,
        )

    return {
        "type": "error",
        "code": code,
        "message": message,
        # Keep the legacy field while older clients are still in circulation.
        "error": message,
        "retryable": retryable,
    }
