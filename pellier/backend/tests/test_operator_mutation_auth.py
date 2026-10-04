"""Tests for the operator mutation boundary (``require_operator``).

The governed-workshop audit's B5 finding: an operator handler depended on the
*optional* ``get_current_user``, which returns ``None`` both for an anonymous
caller and for a presented-but-invalid token. Because the handler never rejected
``None``, a mutation could run with no attributable principal.

Three properties are pinned here:

  1. Anonymous callers are rejected with ``authentication_required``.
  2. A presented-but-invalid token is rejected with ``invalid_credentials``
     — a *different* detail, because "no credentials" and "bad
     credentials" are different operational problems. Neither is a Cedar
     DENY.
  3. A verified operator's ``sub`` reaches the audit record.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import services.auth as auth_module
import services.cognito_auth as cognito_module


class _VerifiedUser:
    """A verified caller. `groups` defaults to membership, so the existing tests keep
    testing what they were about; the shopper case passes `groups=()` explicitly.

    Group membership is now part of the identity, not a separate lookup: an authenticated
    caller outside `auth.OPERATOR_GROUP` is a 403, and this class is how a test says which
    kind of caller it means.
    """

    def __init__(
        self,
        user_id: str = "sub-operator-1",
        groups: tuple[str, ...] = (auth_module.OPERATOR_GROUP,),
    ) -> None:
        self.user_id = user_id
        self.email = "operator@example.com"
        self.given_name = "Operator"
        self.access_token = "token-abc"
        self.username = "operator"
        self.groups = groups


class _Service:
    """Stands in for CognitoAuthService.

    ``mode`` mirrors the real service's contract: ``extract_user`` returns
    ``None`` when a token is absent *or* fails validation, which is exactly
    the ambiguity ``require_operator`` has to resolve.
    """

    def __init__(self, mode: str = "valid") -> None:
        self.mode = mode

    async def extract_user(self, request: Any) -> Optional[_VerifiedUser]:
        if self.mode == "valid":
            return _VerifiedUser()
        if self.mode == "no_subject":
            return _VerifiedUser(user_id="   ")
        if self.mode == "raises":
            raise RuntimeError("JWKS unavailable")
        return None


@pytest.fixture
def app_with_operator_route(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Minimal app exercising only the require_operator dependency."""
    app = FastAPI()

    @app.post("/protected")
    async def protected(  # pyright: ignore[reportUnusedFunction]
        operator: Dict[str, Any] = Depends(auth_module.require_operator),
    ) -> Dict[str, Any]:
        return {"sub": operator["sub"]}

    return app


def _set_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setattr(
        cognito_module, "get_cognito_auth_service", lambda: _Service(mode)
    )


# ---------------------------------------------------------------------------
# require_operator
# ---------------------------------------------------------------------------
def test_anonymous_caller_is_rejected(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_mode(monkeypatch, "anonymous")
    client = TestClient(app_with_operator_route)

    response = client.post("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_invalid_token_is_distinct_from_missing_credentials(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected token must not be reported as "please log in"."""
    _set_mode(monkeypatch, "anonymous")  # extract_user returns None
    client = TestClient(app_with_operator_route)

    response = client.post(
        "/protected", headers={"Authorization": "Bearer expired-token"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


def test_verification_outage_fails_closed_without_rejecting_credentials(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_mode(monkeypatch, "raises")
    client = TestClient(app_with_operator_route)

    response = client.post(
        "/protected", headers={"Authorization": "Bearer whatever"}
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "auth_unavailable"


def test_token_without_a_subject_is_rejected(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verified token with no sub cannot be audited, so it cannot write."""
    _set_mode(monkeypatch, "no_subject")
    client = TestClient(app_with_operator_route)

    response = client.post("/protected", headers={"Authorization": "Bearer t"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


def test_verified_operator_reaches_the_handler(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_mode(monkeypatch, "valid")
    client = TestClient(app_with_operator_route)

    response = client.post("/protected", headers={"Authorization": "Bearer good"})

    assert response.status_code == 200
    assert response.json()["sub"] == "sub-operator-1"


def test_cookie_credentials_are_recognised(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The code-flow httpOnly cookie is a credential, not an absence."""
    _set_mode(monkeypatch, "valid")
    client = TestClient(app_with_operator_route)
    client.cookies.set(cognito_module.ACCESS_TOKEN_COOKIE, "cookie-token")

    response = client.post("/protected")

    assert response.status_code == 200


def test_bearer_prefix_with_empty_token_counts_as_missing(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_mode(monkeypatch, "anonymous")
    client = TestClient(app_with_operator_route)

    response = client.post("/protected", headers={"Authorization": "Bearer "})

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


# ---------------------------------------------------------------------------
# Audit attribution
# ---------------------------------------------------------------------------
def test_operator_mutation_audit_records_the_verified_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``args->>'principal_sub'`` must answer "who acted on this?"."""
    import services.tool_audit_writer as writer

    captured: List[tuple[Any, ...]] = []

    class _DB:
        async def execute_query(self, *args: Any) -> None:
            captured.append(args)

    monkeypatch.setattr(writer, "_db_service", _DB())
    monkeypatch.setattr(writer, "_run_async", asyncio.run)

    writer.record_operator_mutation(
        tool_name="give_store_credit",
        caller="operator-desk",
        principal_sub="sub-operator-1",
        args={"customer_id": "CUST-THEO", "amount_cents": 2500, "reason": "courtesy"},
        result={"status": "success"},
    )

    assert len(captured) == 1
    params = captured[0]
    assert "INSERT INTO pellier.tool_audit" in params[0]
    assert params[1] == "operator-sub-operator-1"
    assert params[2] == "give_store_credit"
    assert params[3] == "operator-desk"
    assert '"principal_sub": "sub-operator-1"' in params[4]


def test_operator_mutation_audit_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed audit write must not fail a mutation that already ran."""
    import services.tool_audit_writer as writer

    class _DB:
        async def execute_query(self, *args: Any) -> None:
            raise RuntimeError("connection reset")

    monkeypatch.setattr(writer, "_db_service", _DB())
    monkeypatch.setattr(writer, "_run_async", asyncio.run)

    writer.record_operator_mutation(
        tool_name="give_store_credit",
        caller="operator-desk",
        principal_sub="sub-1",
        args={"customer_id": "CUST-THEO", "amount_cents": 100, "reason": "courtesy"},
        result={"status": "success"},
    )  # must not raise


def test_operator_mutation_audit_is_a_noop_without_a_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.tool_audit_writer as writer

    monkeypatch.setattr(writer, "_db_service", None)

    writer.record_operator_mutation(
        tool_name="give_store_credit",
        caller="operator-desk",
        principal_sub="sub-1",
        args={},
        result={},
    )  # must not raise


def test_an_authenticated_caller_outside_the_group_is_403(
    app_with_operator_route: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """401 says "who are you", 403 says "you are known and not permitted".

    Collapsing them would tell an authenticated shopper to log in again, which is both
    useless and misleading. Before the group check existed this case returned 200.
    """
    _set_mode(monkeypatch, "valid")
    client = TestClient(app_with_operator_route)

    # Rebind the fake service to produce a caller in no group.
    original = cognito_module.get_cognito_auth_service

    class _ShopperService:
        async def extract_user(self, request):  # noqa: ANN001
            return _VerifiedUser(user_id="sub-marco", groups=())

    cognito_module.get_cognito_auth_service = lambda: _ShopperService()
    try:
        response = client.post("/protected", headers={"Authorization": "Bearer good"})
    finally:
        cognito_module.get_cognito_auth_service = original

    assert response.status_code == 403
    assert response.json()["detail"] == "operator_group_required"
