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

import json
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
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
    # TestClient sends requests over http:// by default; cookies marked
    # ``secure`` are still serialised in the response headers, which is
    # what the tests inspect. follow_redirects=False keeps 302s visible
    # so the signin/callback redirect URLs can be asserted.
    return TestClient(app, follow_redirects=False)


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


def test_signin_rejects_unknown_provider(client: TestClient) -> None:
    resp = client.get("/api/auth/signin", params={"provider": "facebook"})
    # FastAPI's query-param regex guard surfaces as a 422 validation error.
    assert resp.status_code == 422


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
    resp = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": tampered},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "invalid_state"}


def test_callback_expired_state_returns_invalid_state(client: TestClient) -> None:
    expired = _build_state(expiry=int(time.time()) - 60)
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
    state = _build_state()
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
    # Basic auth header present because a client secret is configured.
    assert call["headers"].get("Authorization", "").startswith("Basic ")

    # All four cookies appear in the Set-Cookie headers.
    set_cookies = resp.headers.get_list("set-cookie")
    cookie_names = {sc.split("=", 1)[0] for sc in set_cookies}
    assert ACCESS_TOKEN_COOKIE in cookie_names
    assert ID_TOKEN_COOKIE in cookie_names
    assert REFRESH_TOKEN_COOKIE in cookie_names
    assert JUST_SIGNED_IN_COOKIE in cookie_names

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


def test_callback_invalid_access_token_returns_502(
    client: TestClient,
    token_post_recorder: Dict[str, Any],
) -> None:
    """A token that doesn't validate via JWKS surfaces as auth_failed."""
    state = _build_state()
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


def test_callback_cognito_token_endpoint_5xx_returns_auth_failed(
    client: TestClient,
    token_post_recorder: Dict[str, Any],
) -> None:
    state = _build_state()
    token_post_recorder["responses"].append(
        _FakeTokenResponse({"error": "invalid_grant"}, status_code=400)
    )
    resp = client.get(
        "/api/auth/callback",
        params={"code": "c", "state": state},
    )
    assert resp.status_code == 502
    assert resp.json() == {"detail": "auth_failed"}


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


def test_refresh_happy_path_rotates_cookies(
    client: TestClient,
    signer: _Signer,
    token_post_recorder: Dict[str, Any],
) -> None:
    new_access = signer.sign(_access_claims(sub="rotated-sub"))
    token_post_recorder["responses"].append(
        _FakeTokenResponse(
            {
                "access_token": new_access,
                "id_token": "new-id",
                # No refresh_token in response — Cognito only rotates when
                # rotation is enabled; router should keep the existing one.
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )
    )

    resp = client.post(
        "/api/auth/refresh",
        cookies={REFRESH_TOKEN_COOKIE: "existing-refresh-token"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    call = token_post_recorder["invocations"][0]
    assert call["data"]["grant_type"] == "refresh_token"
    assert call["data"]["refresh_token"] == "existing-refresh-token"

    set_cookies = resp.headers.get_list("set-cookie")
    cookie_names = {sc.split("=", 1)[0] for sc in set_cookies}
    assert ACCESS_TOKEN_COOKIE in cookie_names
    assert ID_TOKEN_COOKIE in cookie_names
    assert REFRESH_TOKEN_COOKIE in cookie_names

    # Access cookie carries the freshly minted token.
    access_cookie = next(sc for sc in set_cookies if sc.startswith(f"{ACCESS_TOKEN_COOKIE}="))
    assert new_access in access_cookie
    # Refresh cookie falls back to the incoming value (rotation disabled).
    refresh_cookie = next(
        sc for sc in set_cookies if sc.startswith(f"{REFRESH_TOKEN_COOKIE}=")
    )
    assert "existing-refresh-token" in refresh_cookie


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
