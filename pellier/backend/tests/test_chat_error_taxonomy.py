import pytest

from services.chat_error_taxonomy import classify_chat_error


def test_policy_denial_requires_an_explicit_policy_marker() -> None:
    denied = classify_chat_error(
        RuntimeError("Tool call not allowed due to policy enforcement [Policy")
    )
    assert denied["code"] == "policy_denied"
    assert denied["retryable"] is False

    auth = classify_chat_error(
        RuntimeError("HTTP 401 Unauthorized: invalid bearer token")
    )
    assert auth["code"] == "authentication_required"
    assert auth["code"] != "policy_denied"


def test_transient_failures_are_retryable_and_sanitized() -> None:
    timeout = classify_chat_error(RuntimeError("Agent execution timed out"))
    throttled = classify_chat_error(
        RuntimeError("ThrottlingException: secret provider response")
    )
    unavailable = classify_chat_error(
        RuntimeError("Connection refused at internal-host.example:443")
    )

    assert timeout["code"] == "request_timeout"
    assert throttled["code"] == "rate_limited"
    assert unavailable["code"] == "service_unavailable"
    assert all(item["retryable"] for item in (timeout, throttled, unavailable))
    assert "internal-host" not in unavailable["message"]
    assert unavailable["error"] == unavailable["message"]


def test_exception_groups_are_classified_from_their_children() -> None:
    grouped = ExceptionGroup(
        "request failed",
        [RuntimeError("transport issue"), RuntimeError("AccessDeniedException")],
    )
    assert classify_chat_error(grouped)["code"] == "policy_denied"


def test_unmapped_verified_customer_is_an_authentication_error() -> None:
    result = classify_chat_error("customer_identity_unmapped")

    assert result["code"] == "authentication_required"
    assert result["retryable"] is False


@pytest.mark.parametrize(
    "code",
    [
        "authentication_failed",
        "authentication_required",
        "customer_identity_unmapped",
        "customer_scope_mismatch",
    ],
)
def test_runtime_identity_refusals_ask_for_sign_in_not_a_retry(code: str) -> None:
    result = classify_chat_error(code)

    assert result["code"] == "authentication_required"
    assert result["retryable"] is False


@pytest.mark.parametrize("code", ["auth_unavailable", "auth_not_configured"])
def test_runtime_verifier_outages_are_service_unavailable(code: str) -> None:
    result = classify_chat_error(code)

    assert result["code"] == "service_unavailable"
    assert result["retryable"] is True
