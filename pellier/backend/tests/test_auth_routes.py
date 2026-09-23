"""Unit tests for ``routes.auth`` — the ``/api/auth/*`` surface (Task 3.3).

Validates Requirements 3.1.1–3.1.5, 4.1.3, 5.3.1, 5.3.4 without any live
Cognito traffic. Tests mint access tokens via a synthetic RSA signer
(mirroring ``test_cognito_auth.py``), stub ``requests.post`` for the
``/oauth2/token`` and ``/oauth2/revoke`` calls, and override the shared
``CognitoAuthService`` dependency so JWKS resolution uses the in-test
key.

Covered assertions (from tasks.md Task 3.3 "Test verification"):

  * state mismatch returns 400 ``invalid_state``
  * callback happy path sets all four cookies
  * ``/api/auth/me`` 401s without a valid token
  * logout clears cookies (plus revoke call semantics)

Additional coverage keeps the route contract honest:

  * signin returns a 302 to Cognito's ``/oauth2/authorize`` with the
    right ``identity_provider`` mapping, ``client_id``, scope, and
    a signed ``state`` parameter
  * ``/api/auth/me`` returns the verified user payload when the cookie
    is valid
  * ``/api/auth/refresh`` 401s without a ``refresh_token`` cookie

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_auth_routes.py -v
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from config import settings
from services.cognito_auth import (
    ACCESS_TOKEN_COOKIE,
    CognitoAuthService,
    get_cognito_auth_service,
)
from routes import auth as auth_module
from routes.auth import (
    ID_TOKEN_COOKIE,
    JUST_SIGNED_IN_COOKIE,
    OAUTH_RETURN_TO_COOKIE,
    OAUTH_STATE_COOKIE,
    PKCE_VERIFIER_COOKIE,
    REFRESH_TOKEN_COOKIE,
    _build_state,
    router as auth_router,
)


# ---------------------------------------------------------------------------
# Test pool identity — mirrors test_cognito_auth.py
# ---------------------------------------------------------------------------

POOL_ID = "us-east-1_TESTPOOL"
REGION = "us-east-1"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
COGNITO_DOMAIN = "test.auth.us-east-1.amazoncognito.com"
APP_BASE_URL = "https://storefront.test"
OAUTH_REDIRECT_URI = "https://api.test/api/auth/callback"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"


# ---------------------------------------------------------------------------
# Synthetic RSA signer + JWKS (same pattern as test_cognito_auth.py)
# ---------------------------------------------------------------------------


class _Signer:
    def __init__(self, kid: Optional[str] = None) -> None:
        self.kid = kid or f"kid-{uuid.uuid4().hex[:8]}"
        self._private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._pem = self._private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_jwk(self) -> Dict[str, Any]:
        public_pem = self._private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_key = serialization.load_pem_public_key(public_pem)
        jwk: Dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = self.kid
        jwk["use"] = "sig"
        jwk["alg"] = "RS256"
        return jwk

    def sign(self, claims: Dict[str, Any]) -> str:
        return jwt.encode(
            claims,
            self._pem,
            algorithm="RS256",
            headers={"kid": self.kid},
        )


def _access_claims(
    *,
    sub: str = "cognito-sub-789",
    email: str = "shopper@example.com",
    given_name: str = "Rowan",
    exp_offset: int = 3600,
) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "sub": sub,
        "email": email,
        "given_name": given_name,
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + exp_offset,
        "auth_time": now,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wire_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the router at our synthetic Cognito pool for the test run."""
    monkeypatch.setattr(settings, "COGNITO_POOL_ID", POOL_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION, raising=False)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_SECRET", CLIENT_SECRET, raising=False)
    monkeypatch.setattr(settings, "COGNITO_DOMAIN", COGNITO_DOMAIN, raising=False)
    monkeypatch.setattr(settings, "APP_BASE_PATH", "", raising=False)
    monkeypatch.setattr(settings, "APP_BASE_URL", APP_BASE_URL, raising=False)
    monkeypatch.setattr(settings, "OAUTH_REDIRECT_URI", OAUTH_REDIRECT_URI, raising=False)


@pytest.fixture
def signer() -> _Signer:
    return _Signer(kid="auth-route-kid")


@pytest.fixture
def auth_service(signer: _Signer) -> CognitoAuthService:
    """JWKS-backed service wired to the synthetic signer."""
    svc = CognitoAuthService(pool_id=POOL_ID, region=REGION, client_id=CLIENT_ID)
    svc._fetch_jwks = lambda: {"keys": [signer.public_jwk()]}  # type: ignore[assignment]
    return svc


@pytest.fixture
def client(auth_service: CognitoAuthService) -> TestClient:
    """FastAPI test app with just the auth router mounted.

    Isolates the router from the rest of ``app.py`` so the tests don't
    need the full lifespan (database, embeddings, Bedrock).
    """
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_cognito_auth_service] = lambda: auth_service
    return TestClient(
        app,
        base_url="https://api.test",
        follow_redirects=False,
    )


class _FakeTokenResponse:
    """Minimal stand-in for ``requests.Response`` used by the token stub."""

    def __init__(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Dict[str, Any]:
        return self._payload


@pytest.fixture
def token_post_recorder(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Patch ``requests.post`` inside the routes module to a recorder."""
    calls: Dict[str, Any] = {"invocations": []}
    response_queue: List[_FakeTokenResponse] = []
    calls["responses"] = response_queue

    def _fake_post(url: str, data=None, headers=None, timeout=None, **kwargs):
        calls["invocations"].append(
            {"url": url, "data": data or {}, "headers": dict(headers or {})}
        )
        if response_queue:
            return response_queue.pop(0)
        return _FakeTokenResponse(
            {
                "access_token": "unused",
                "id_token": "unused",
                "refresh_token": "unused",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(auth_module.requests, "post", _fake_post)
    return calls


# ---------------------------------------------------------------------------
# /api/auth/signin
# ---------------------------------------------------------------------------


def _begin_oauth(
    client: TestClient, *, return_to: Optional[str] = None
) -> tuple[str, str]:
    params = {"returnTo": return_to} if return_to else None
    response = client.get("/api/auth/signin", params=params)
    params = {
        key: values[0]
        for key, values in parse_qs(urlparse(response.headers["location"]).query).items()
    }
    return params["state"], client.cookies[PKCE_VERIFIER_COOKIE]


def test_signin_google_redirects_to_cognito(client: TestClient) -> None:
    resp = client.get("/api/auth/signin", params={"provider": "google"})
    assert resp.status_code == 302

    parsed = urlparse(resp.headers["location"])
    assert parsed.netloc == COGNITO_DOMAIN
    assert parsed.path == "/oauth2/authorize"

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert params["client_id"] == CLIENT_ID
    assert params["response_type"] == "code"
    assert params["scope"] == "openid email profile"
    assert params["redirect_uri"] == OAUTH_REDIRECT_URI
    assert params["identity_provider"] == "Google"
    assert "state" in params and params["state"]
    assert params["code_challenge_method"] == "S256"
    verifier = client.cookies[PKCE_VERIFIER_COOKIE]
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert params["code_challenge"] == expected_challenge
    assert client.cookies[OAUTH_STATE_COOKIE] == params["state"]


def test_signin_apple_maps_to_signinwithapple(client: TestClient) -> None:
    resp = client.get("/api/auth/signin", params={"provider": "apple"})
    assert resp.status_code == 302
    params = {k: v[0] for k, v in parse_qs(urlparse(resp.headers["location"]).query).items()}
    assert params["identity_provider"] == "SignInWithApple"


def test_signin_email_omits_identity_provider(client: TestClient) -> None:
    resp = client.get("/api/auth/signin", params={"provider": "email"})
    assert resp.status_code == 302
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert "identity_provider" not in query


def test_signin_converges_loopback_aliases_before_setting_oauth_cookies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_URL", None, raising=False)
    monkeypatch.setattr(
        settings,
        "OAUTH_REDIRECT_URI",
        "http://localhost:5173/api/auth/callback",
        raising=False,
    )

    resp = client.get(
        "/api/auth/signin",
        params={
            "provider": "email",
            "returnTo": "/operator/clients/CUST-JESSICA?view=request",
        },
        headers={
            "host": "127.0.0.1:5173",
            "x-forwarded-proto": "http",
        },
    )

    assert resp.status_code == 302
    parsed = urlparse(resp.headers["location"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:5173"
    assert parsed.path == "/api/auth/signin"
    assert parse_qs(parsed.query) == {
        "provider": ["email"],
        "returnTo": ["/operator/clients/CUST-JESSICA?view=request"],
    }
    assert OAUTH_STATE_COOKIE not in client.cookies
    assert PKCE_VERIFIER_COOKIE not in client.cookies


def test_signin_binds_a_safe_return_path_to_the_oauth_transaction(
    client: TestClient,
) -> None:
    resp = client.get(
        "/api/auth/signin",
        params={"returnTo": "/operator/clients/CUST-JESSICA?view=request"},
    )
    assert resp.status_code == 302
    assert (
        unquote(client.cookies[OAUTH_RETURN_TO_COOKIE])
        == "/operator/clients/CUST-JESSICA?view=request"
    )


@pytest.mark.parametrize(
    "return_to",
    [
        "https://evil.example/operator",
        "//evil.example/operator",
        r"/\\evil.example/operator",
    ],
)
def test_signin_rejects_cross_origin_return_paths(
    client: TestClient, return_to: str
) -> None:
    client.cookies.set(
        OAUTH_RETURN_TO_COOKIE,
        quote("/operator", safe=""),
        domain="api.test",
        path="/api/auth",
    )
    resp = client.get("/api/auth/signin", params={"returnTo": return_to})
    assert resp.status_code == 302
    assert OAUTH_RETURN_TO_COOKIE not in client.cookies


def test_signin_rejects_unknown_provider(client: TestClient) -> None:
    resp = client.get("/api/auth/signin", params={"provider": "facebook"})
    # FastAPI's query-param regex guard surfaces as a 422 validation error.
    assert resp.status_code == 422


@pytest.mark.parametrize("prefix", ["", "/ports/8000", "/ports/8000/"])
def test_signin_derives_cloudfront_callback_when_base_url_is_unset(
    prefix: str,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_BASE_PATH", prefix, raising=False)
    monkeypatch.setattr(settings, "APP_BASE_URL", None, raising=False)
    monkeypatch.setattr(settings, "OAUTH_REDIRECT_URI", None, raising=False)
    resp = client.get(
        "/api/auth/signin",
        headers={
            "host": "d111111abcdef8.cloudfront.net",
            "x-forwarded-proto": "https",
        },
    )
    params = {
        key: values[0]
        for key, values in parse_qs(urlparse(resp.headers["location"]).query).items()
    }
    assert (
        params["redirect_uri"]
        == "https://d111111abcdef8.cloudfront.net" + prefix.rstrip("/") + "/api/auth/callback"
    )


# ---------------------------------------------------------------------------
# /api/auth/callback — state handling
# ---------------------------------------------------------------------------


def test_callback_missing_state_returns_invalid_state(client: TestClient) -> None:
    resp = client.get("/api/auth/callback", params={"code": "abc"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_state"}


def test_callback_tampered_state_returns_invalid_state(client: TestClient) -> None:
    good = _build_state()
    nonce, expiry, _signature = good.split(".")
    tampered = f"{nonce}.{expiry}.AAAA"  # wrong signature
    client.cookies.set(OAUTH_STATE_COOKIE, tampered, path="/api/auth")
    client.cookies.set(PKCE_VERIFIER_COOKIE, "test-verifier", path="/api/auth")
    resp = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": tampered},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_state"}


def test_callback_expired_state_returns_invalid_state(client: TestClient) -> None:
    expired = _build_state(expiry=int(time.time()) - 60)
    client.cookies.set(OAUTH_STATE_COOKIE, expired, path="/api/auth")
    client.cookies.set(PKCE_VERIFIER_COOKIE, "test-verifier", path="/api/auth")
    resp = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": expired},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_state"}


def test_callback_cognito_error_param_returns_auth_failed(client: TestClient) -> None:
    resp = client.get(
        "/api/auth/callback",
        params={"error": "access_denied", "error_description": "user_cancelled"},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "auth_failed"}


# ---------------------------------------------------------------------------
# /api/auth/callback — happy path
# ---------------------------------------------------------------------------


def test_callback_happy_path_sets_four_cookies_and_redirects_home(
    client: TestClient,
    signer: _Signer,
    token_post_recorder: Dict[str, Any],
) -> None:
    state, verifier = _begin_oauth(client)
    access_token = signer.sign(_access_claims())
    token_post_recorder["responses"].append(
        _FakeTokenResponse(
            {
                "access_token": access_token,
                "id_token": "synthetic-id-token",
                "refresh_token": "synthetic-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )
    )

    resp = client.get(
        "/api/auth/callback",
        params={"code": "auth-code-from-cognito", "state": state},
    )

    # 302 back to the SPA root (Req 3.1.2 final step).
    assert resp.status_code == 302
    assert resp.headers["location"] == f"{APP_BASE_URL}/"

    # Token endpoint was called with the authorization_code grant.
    assert len(token_post_recorder["invocations"]) == 1
    call = token_post_recorder["invocations"][0]
    assert call["url"] == f"https://{COGNITO_DOMAIN}/oauth2/token"
    assert call["data"]["grant_type"] == "authorization_code"
    assert call["data"]["code"] == "auth-code-from-cognito"
    assert call["data"]["redirect_uri"] == OAUTH_REDIRECT_URI
    assert call["data"]["code_verifier"] == verifier
    # Basic auth header present because a client secret is configured.
    assert call["headers"].get("Authorization", "").startswith("Basic ")

    # All four cookies appear in the Set-Cookie headers.
    set_cookies = resp.headers.get_list("set-cookie")
    cookie_names = {sc.split("=", 1)[0] for sc in set_cookies}
    assert ACCESS_TOKEN_COOKIE in cookie_names
    assert ID_TOKEN_COOKIE in cookie_names
    assert REFRESH_TOKEN_COOKIE in cookie_names
    assert JUST_SIGNED_IN_COOKIE in cookie_names
    assert OAUTH_STATE_COOKIE in cookie_names
    assert PKCE_VERIFIER_COOKIE in cookie_names
    assert OAUTH_STATE_COOKIE not in client.cookies
    assert PKCE_VERIFIER_COOKIE not in client.cookies

    # Session cookies are httpOnly + Secure + SameSite=Lax per Req 5.3.1.
    for cookie_name in (ACCESS_TOKEN_COOKIE, ID_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE):
        header = next(sc for sc in set_cookies if sc.startswith(f"{cookie_name}="))
        lower = header.lower()
        assert "httponly" in lower
        assert "secure" in lower
        assert "samesite=lax" in lower

    # just_signed_in explicitly NOT httpOnly (Design decision #2) so the
    # SPA can read and delete it on first mount.
    jsi_header = next(sc for sc in set_cookies if sc.startswith(f"{JUST_SIGNED_IN_COOKIE}="))
    jsi_lower = jsi_header.lower()
    assert "httponly" not in jsi_lower
    assert "secure" in jsi_lower
    assert "samesite=lax" in jsi_lower
    assert "max-age=60" in jsi_lower

    # Request state cookies also surface the access token verbatim (so
    # ``/api/auth/me`` can read it on subsequent requests).
    assert f"{ACCESS_TOKEN_COOKIE}={access_token}" in set_cookies[0] or any(
        access_token in sc for sc in set_cookies
    )


def test_callback_returns_to_the_originating_spa_route(
    client: TestClient,
    signer: _Signer,
    token_post_recorder: Dict[str, Any],
) -> None:
    state, _verifier = _begin_oauth(
        client,
        return_to="/operator/clients/CUST-JESSICA?view=request",
    )
    token_post_recorder["responses"].append(
        _FakeTokenResponse(
            {
                "access_token": signer.sign(_access_claims()),
                "id_token": "synthetic-id-token",
                "refresh_token": "synthetic-refresh-token",
            }
        )
    )

    resp = client.get(
        "/api/auth/callback",
        params={"code": "auth-code-from-cognito", "state": state},
    )

    assert resp.status_code == 302
    assert (
        resp.headers["location"]
        == f"{APP_BASE_URL}/operator/clients/CUST-JESSICA?view=request"
    )
    assert OAUTH_RETURN_TO_COOKIE not in client.cookies


def test_callback_invalid_access_token_returns_502(
    client: TestClient,
    token_post_recorder: Dict[str, Any],
) -> None:
    """A token that doesn't validate via JWKS surfaces as auth_failed."""
    state, _verifier = _begin_oauth(client)
    # Sign with a key NOT in the JWKS — mimics Cognito handing back a
    # token with a rotated key the service hasn't cached yet.
    rogue = _Signer(kid="rogue")
    bad_token = rogue.sign(_access_claims())
    token_post_recorder["responses"].append(
        _FakeTokenResponse(
            {
                "access_token": bad_token,
                "id_token": "x",
                "refresh_token": "y",
            }
        )
    )

    resp = client.get(
        "/api/auth/callback",
        params={"code": "c", "state": state},
    )
    assert resp.status_code == 502
    assert resp.json() == {"detail": "auth_failed"}
    assert OAUTH_STATE_COOKIE not in client.cookies
    assert PKCE_VERIFIER_COOKIE not in client.cookies


def test_callback_cognito_rejection_returns_auth_failed(
    client: TestClient,
    token_post_recorder: Dict[str, Any],
) -> None:
    state, _verifier = _begin_oauth(client)
    token_post_recorder["responses"].append(
        _FakeTokenResponse({"error": "invalid_grant"}, status_code=400)
    )
    resp = client.get(
        "/api/auth/callback",
        params={"code": "c", "state": state},
    )
    assert resp.status_code == 502
    assert resp.json() == {"detail": "auth_failed"}
    assert OAUTH_STATE_COOKIE not in client.cookies
    assert PKCE_VERIFIER_COOKIE not in client.cookies


@pytest.mark.parametrize("status", [429, 500, 503])
def test_callback_provider_outage_is_not_a_rejected_signin(
    client: TestClient, token_post_recorder: Dict[str, Any], status: int
) -> None:
    state, _ = _begin_oauth(client)
    token_post_recorder["responses"].append(
        _FakeTokenResponse({"error": "temporarily_unavailable"}, status_code=status)
    )
    response = client.get("/api/auth/callback", params={"code": "c", "state": state})
    assert response.status_code == 503
    assert response.json() == {"detail": "auth_unavailable"}
    assert OAUTH_STATE_COOKIE not in client.cookies


@pytest.mark.parametrize("status", [400, 429, 500, 503])
def test_refresh_provider_failure_preserves_existing_session(
    client: TestClient, token_post_recorder: Dict[str, Any], status: int
) -> None:
    token_post_recorder["responses"].append(
        _FakeTokenResponse({"error": "invalid_client"}, status_code=status)
    )
    client.cookies.set(REFRESH_TOKEN_COOKIE, "existing-refresh", domain="api.test")
    client.cookies.set(ACCESS_TOKEN_COOKIE, "existing-access", domain="api.test")
    response = client.post("/api/auth/refresh")
    assert response.status_code == 503
    assert response.json() == {"error": "auth_unavailable"}
    assert "set-cookie" not in response.headers
    assert client.cookies[REFRESH_TOKEN_COOKIE] == "existing-refresh"


def test_network_timeout_preserves_refresh_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*args, **kwargs):
        raise requests.Timeout("provider timeout")
    monkeypatch.setattr(auth_module.requests, "post", unavailable)
    client.cookies.set(REFRESH_TOKEN_COOKIE, "existing-refresh", domain="api.test")
    response = client.post("/api/auth/refresh")
    assert response.status_code == 503
    assert "set-cookie" not in response.headers


def test_jwks_outage_preserves_session_and_fails_closed(
    client: TestClient, auth_service: CognitoAuthService, signer: _Signer,
    token_post_recorder: Dict[str, Any],
) -> None:
    def unavailable():
        raise requests.Timeout("key endpoint timeout")
    auth_service._fetch_jwks = unavailable
    token = signer.sign(_access_claims())
    client.cookies.set(ACCESS_TOKEN_COOKIE, token, domain="api.test")
    response = client.get("/api/auth/me")
    assert response.status_code == 503
    assert response.json() == {"detail": "auth_unavailable"}
    client.cookies.set(REFRESH_TOKEN_COOKIE, "existing-refresh", domain="api.test")
    token_post_recorder["responses"].append(_FakeTokenResponse({"access_token": token}))
    response = client.post("/api/auth/refresh")
    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert client.cookies[REFRESH_TOKEN_COOKIE] == "existing-refresh"


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------


def test_me_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json() == {"error": "auth_failed"}


def test_me_with_invalid_cookie_returns_401(client: TestClient) -> None:
    resp = client.get(
        "/api/auth/me",
        cookies={ACCESS_TOKEN_COOKIE: "not-a-jwt"},
    )
    assert resp.status_code == 401


def test_me_with_valid_cookie_returns_profile(
    client: TestClient, signer: _Signer
) -> None:
    token = signer.sign(
        _access_claims(sub="sub-42", email="avery@example.com", given_name="Avery")
    )
    resp = client.get(
        "/api/auth/me",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": "sub-42",
        "email": "avery@example.com",
        "given_name": "Avery",
    }


def test_me_with_valid_bearer_header_returns_profile(
    client: TestClient, signer: _Signer
) -> None:
    token = signer.sign(_access_claims(sub="bearer-sub"))
    resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "bearer-sub"


# ---------------------------------------------------------------------------
# /api/auth/logout
# ---------------------------------------------------------------------------


def test_logout_clears_cookies_and_returns_ok(
    client: TestClient, token_post_recorder: Dict[str, Any]
) -> None:
    # A 2xx response from /oauth2/revoke keeps the test moving forward.
    token_post_recorder["responses"].append(_FakeTokenResponse({}))

    resp = client.post(
        "/api/auth/logout",
        cookies={
            ACCESS_TOKEN_COOKIE: "access",
            ID_TOKEN_COOKIE: "id",
            REFRESH_TOKEN_COOKIE: "refresh",
            JUST_SIGNED_IN_COOKIE: "1",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # delete_cookie works by writing a cookie with an empty value and
    # Max-Age=0 / expires=Thu, 01 Jan 1970. Assert each cookie shows up
    # in the Set-Cookie list with one of those markers.
    set_cookies = resp.headers.get_list("set-cookie")
    cleared_names = set()
    for raw in set_cookies:
        lower = raw.lower()
        name = raw.split("=", 1)[0]
        if "max-age=0" in lower or "1970" in lower:
            cleared_names.add(name)
    assert {
        ACCESS_TOKEN_COOKIE,
        ID_TOKEN_COOKIE,
        REFRESH_TOKEN_COOKIE,
        JUST_SIGNED_IN_COOKIE,
    }.issubset(cleared_names)

    # Revoke endpoint was called with the refresh token cookie value.
    revoke_calls = [
        c for c in token_post_recorder["invocations"]
        if c["url"].endswith("/oauth2/revoke")
    ]
    assert len(revoke_calls) == 1
    assert revoke_calls[0]["data"]["token"] == "refresh"
    assert revoke_calls[0]["data"]["client_id"] == CLIENT_ID


def test_logout_without_refresh_cookie_still_clears(
    client: TestClient, token_post_recorder: Dict[str, Any]
) -> None:
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    # No revoke call when the refresh cookie is absent.
    assert not any(
        c["url"].endswith("/oauth2/revoke") for c in token_post_recorder["invocations"]
    )


# ---------------------------------------------------------------------------
# /api/auth/refresh
# ---------------------------------------------------------------------------


def test_refresh_without_cookie_returns_401(client: TestClient) -> None:
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401
    assert resp.json() == {"error": "refresh_failed"}


@pytest.mark.parametrize("rotated_refresh", [None, "provider-issued-refresh"])
def test_refresh_sets_only_provider_issued_cookies(
    client: TestClient,
    signer: _Signer,
    token_post_recorder: Dict[str, Any],
    rotated_refresh: Optional[str],
) -> None:
    new_access = signer.sign(_access_claims(sub="rotated-sub"))
    token_post_recorder["responses"].append(
        _FakeTokenResponse(
            {
                "access_token": new_access,
                "id_token": "new-id",
                "refresh_token": rotated_refresh,
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )
    )

    client.base_url = "https://storefront.test"
    client.cookies.set(
        REFRESH_TOKEN_COOKIE,
        quote("existing-refresh-token", safe=""),
        domain="storefront.test",
        path="/",
    )
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    call = token_post_recorder["invocations"][0]
    assert call["data"]["grant_type"] == "refresh_token"
    assert call["data"]["refresh_token"] == "existing-refresh-token"

    set_cookies = resp.headers.get_list("set-cookie")
    cookie_names = {sc.split("=", 1)[0] for sc in set_cookies}
    assert ACCESS_TOKEN_COOKIE in cookie_names
    assert ID_TOKEN_COOKIE in cookie_names
    assert (REFRESH_TOKEN_COOKIE in cookie_names) is bool(rotated_refresh)

    # Access cookie carries the freshly minted token.
    access_cookie = next(sc for sc in set_cookies if sc.startswith(f"{ACCESS_TOKEN_COOKIE}="))
    assert new_access in access_cookie
    # Without rotation, no Set-Cookie reflects the request or extends expiry;
    # the browser still retains its original usable refresh cookie.
    expected_refresh = rotated_refresh or "existing-refresh-token"
    assert unquote(client.cookies[REFRESH_TOKEN_COOKIE]) == expected_refresh


def test_refresh_cognito_rejection_clears_cookies(
    client: TestClient,
    token_post_recorder: Dict[str, Any],
) -> None:
    token_post_recorder["responses"].append(
        _FakeTokenResponse({"error": "invalid_grant"}, status_code=400)
    )
    resp = client.post(
        "/api/auth/refresh",
        cookies={REFRESH_TOKEN_COOKIE: "revoked-token"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"error": "refresh_failed"}
    set_cookies = resp.headers.get_list("set-cookie")
    # Every session cookie is cleared so the SPA stops retrying.
    cleared_names = {
        sc.split("=", 1)[0]
        for sc in set_cookies
        if "max-age=0" in sc.lower() or "1970" in sc.lower()
    }
    assert {
        ACCESS_TOKEN_COOKIE,
        ID_TOKEN_COOKIE,
        REFRESH_TOKEN_COOKIE,
    }.issubset(cleared_names)
