"""The one-click shopper sign-in: a real Cognito session for four users and nobody else.

Synthetic Cognito and Secrets Manager stand-ins; no live AWS call. The
verifier is a Mock whose ``validate_jwt`` returns what a verified access token
would carry, so the tests can say what claims each chip must produce and what
the endpoint must refuse.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from config import settings
from routes import auth as auth_module
from routes import password_auth as module
from services.cognito_auth import get_cognito_auth_service
from services.turn_identity import customer_id_for_verified_username

SECRET_USERS = [
    {"username": "Marco", "password": "marco-secret"},
    {"username": "Anna", "password": "anna-secret"},
    {"username": "Theo", "password": "theo-secret"},
    {"username": "Jessica", "password": "jessica-secret"},
    {"username": "nadia", "password": "nadia-secret"},
]


def _verified(username: str, groups: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=f"sub-{username}", email=f"{username}@pellier.example.com",
        given_name=username, username=username, groups=groups, access_token="verified-access",
    )


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "COGNITO_TEST_CREDENTIALS_SECRET_ARN", "arn:secret:test-users")
    module._credentials_cache.update(read_at=0.0, users=[])
    cognito = Mock()
    cognito.exceptions = boto3.client(
        "cognito-idp", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test",
    ).exceptions
    cognito.initiate_auth.return_value = {"AuthenticationResult": {
        "AccessToken": "verified-access", "IdToken": "id", "RefreshToken": "refresh",
    }}
    monkeypatch.setattr(module, "_client", lambda: cognito)
    secrets = Mock()
    secrets.get_secret_value.return_value = {"SecretString": __import__("json").dumps({"users": SECRET_USERS})}
    monkeypatch.setattr(module, "_secrets_client", lambda: secrets)
    validator = Mock(validate_jwt=AsyncMock())
    app = FastAPI()
    app.include_router(module.router)
    app.include_router(auth_module.router)
    app.dependency_overrides[get_cognito_auth_service] = lambda: validator
    with TestClient(app, base_url="https://pellier.test") as client:
        yield client, cognito, secrets, validator


def post(client, body):
    csrf = client.get("/api/auth/password/csrf")
    return client.post(
        "/api/auth/password/workshop-sign-in",
        headers={"x-csrf-token": csrf.json()["csrfToken"]},
        json=body,
    )


@pytest.mark.parametrize("username", ["anna", "marco", "theo", "jessica"])
def test_each_shopper_chip_yields_a_token_whose_claims_match_that_user(setup, username):
    client, cognito, secrets, validator = setup
    validator.validate_jwt.return_value = _verified(username)

    response = post(client, {"username": username})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "signed_in", "returnTo": "/", "username": username, "signInMethod": "workshop",
    }
    # The sign-in is the real one: the provisioned password, never one the browser sent.
    params = cognito.initiate_auth.call_args.kwargs
    assert params["AuthFlow"] == "USER_PASSWORD_AUTH"
    assert params["AuthParameters"] == {"USERNAME": username, "PASSWORD": f"{username}-secret"}
    secrets.get_secret_value.assert_called_once_with(SecretId="arn:secret:test-users")
    validator.validate_jwt.assert_awaited_once_with("verified-access")
    cookies = response.headers.get_list("set-cookie")
    access = next(value for value in cookies if value.startswith("access_token="))
    assert "HttpOnly" in access and "Secure" in access
    method = next(value for value in cookies if value.startswith("signin_method="))
    assert "signin_method=workshop" in method and "HttpOnly" in method
    assert "verified-access" not in response.text and "-secret" not in response.text


def test_the_signed_in_session_reports_the_workshop_method(setup):
    client, _cognito, _secrets, validator = setup
    validator.validate_jwt.return_value = _verified("anna")
    validator.extract_user = AsyncMock(return_value=_verified("anna"))
    post(client, {"username": "anna"})

    me = client.get("/api/auth/me")

    assert me.status_code == 200
    assert me.json()["username"] == "anna"
    assert me.json()["sign_in_method"] == "workshop"


@pytest.mark.parametrize("username", ["nadia", "operator", "someone-else", ""])
def test_nadia_an_operator_and_an_unknown_user_are_refused(setup, username):
    client, cognito, _secrets, _validator = setup

    response = post(client, {"username": username})

    assert response.status_code in (400, 403), response.text
    if username:
        assert response.json()["detail"] == "workshop_user_not_allowed"
    cognito.initiate_auth.assert_not_called()
    assert "access_token" not in client.cookies


def test_a_shopper_who_is_in_the_operator_group_gets_no_session(setup):
    """Even a listed shopper is refused the moment the token carries staff membership."""
    client, _cognito, _secrets, validator = setup
    validator.validate_jwt.return_value = _verified("anna", groups=("pellier-operators",))

    response = post(client, {"username": "anna"})

    assert response.status_code == 403
    assert response.json()["detail"] == "workshop_user_not_allowed"
    assert "access_token" not in client.cookies


def test_the_endpoint_never_takes_a_password_from_the_browser(setup):
    client, cognito, _secrets, _validator = setup

    response = post(client, {"username": "anna", "password": "anything"})

    assert response.status_code == 400
    cognito.initiate_auth.assert_not_called()


def test_theos_chip_cannot_produce_jessicas_scope(setup):
    client, cognito, _secrets, validator = setup
    # The token Cognito mints is Theo's, because Theo's password was used.
    validator.validate_jwt.return_value = _verified("theo")

    response = post(client, {"username": "theo"})

    assert response.status_code == 200
    assert cognito.initiate_auth.call_args.kwargs["AuthParameters"]["USERNAME"] == "theo"
    assert customer_id_for_verified_username("theo") == "CUST-THEO"
    assert customer_id_for_verified_username("theo") != customer_id_for_verified_username("jessica")
    # And a token that verifies as someone else is refused rather than used.
    validator.validate_jwt.return_value = _verified("jessica")
    crossed = post(client, {"username": "theo"})
    assert crossed.status_code == 502
    assert "signin_method" not in crossed.headers.get("set-cookie", "")


def test_a_missing_secret_is_unavailable_not_a_bypass(setup, monkeypatch):
    client, cognito, _secrets, _validator = setup
    monkeypatch.setattr(settings, "COGNITO_TEST_CREDENTIALS_SECRET_ARN", None)

    response = post(client, {"username": "anna"})

    assert response.status_code == 503
    assert response.json()["detail"] == "workshop_sign_in_unavailable"
    cognito.initiate_auth.assert_not_called()


def test_an_unverified_token_never_becomes_a_session(setup):
    client, _cognito, _secrets, validator = setup
    validator.validate_jwt.side_effect = HTTPException(401, "invalid_jwt")

    response = post(client, {"username": "marco"})

    assert response.status_code == 502
    assert "access_token" not in client.cookies


def test_a_typed_password_sign_in_clears_the_workshop_marker(setup):
    """The marker never outlives the session it described."""
    client, _cognito, _secrets, validator = setup
    validator.validate_jwt.return_value = _verified("anna")
    post(client, {"username": "anna"})
    assert client.cookies.get("signin_method") == "workshop"
    csrf = client.get("/api/auth/password/csrf")
    client.post(
        "/api/auth/password/sign-in", headers={"x-csrf-token": csrf.json()["csrfToken"]},
        json={"username": "nadia", "password": "typed"},
    )
    assert client.cookies.get("signin_method") is None


@pytest.fixture
def revocations(monkeypatch):
    """Every refresh token the server asked Cognito to revoke, with no network call."""
    revoked: list[str] = []
    monkeypatch.setattr(settings, "COGNITO_DOMAIN", "pellier-test.auth.example.com")
    monkeypatch.setattr(
        auth_module.requests, "post",
        lambda _url, data=None, **_kwargs: revoked.append(data["token"]) or SimpleNamespace(status_code=200),
    )
    return revoked


def test_switching_shopper_signs_the_previous_one_out(setup, revocations):
    """Choosing Anna while Theo is signed in revokes Theo's session, then signs Anna in."""
    client, _cognito, _secrets, validator = setup
    validator.validate_jwt.return_value = _verified("theo")
    post(client, {"username": "theo"})
    assert revocations == []
    client.cookies.set("refresh_token", "theos-refresh-token", domain="pellier.test")

    validator.validate_jwt.return_value = _verified("anna")
    response = post(client, {"username": "anna"})

    assert response.status_code == 200 and response.json()["username"] == "anna"
    assert revocations == ["theos-refresh-token"]
    cookies = response.headers.get_list("set-cookie")
    assert any(value.startswith("refresh_token=refresh") for value in cookies)


def test_a_refused_switch_leaves_the_previous_shopper_signed_in(setup, revocations):
    client, _cognito, _secrets, validator = setup
    client.cookies.set("refresh_token", "theos-refresh-token", domain="pellier.test")
    validator.validate_jwt.return_value = _verified("anna", groups=("pellier-operators",))

    assert post(client, {"username": "anna"}).status_code == 403
    assert post(client, {"username": "nadia"}).status_code == 403
    assert revocations == []
