"""One browser, two sessions: Jessica on the storefront and Nadia on the Operator.

Lab 4 needs both at once: Jessica asks for her credit in the storefront while
Nadia, signed in on the Operator, answers it. The sessions live in separate
httpOnly cookie sets on the same client here, as they do in one browser, and
every test drives the real routes and the real JWT verifier. Cognito,
Secrets Manager and the token endpoint are stand-ins; no AWS call is made.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import Mock
from urllib.parse import parse_qs, quote, urlparse

import boto3
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

import app as app_module
import services.cognito_auth as cognito_module
from config import settings
from routes import auth as auth_module
from routes import operator as operator_module
from routes import password_auth as password_module
from routes.user import get_agentcore_memory
from services.agentcore_identity import AgentCoreIdentityService, get_agentcore_identity_service
from services.auth import OPERATOR_GROUP, session_cookie_names
from services.cognito_auth import CognitoAuthService, get_cognito_auth_service
from tests.test_operator_review import JESSICA_HASH, FakeReviewDb

POOL_ID = "us-east-1_TWOSESSIONS"
REGION = "us-east-1"
CLIENT_ID = "two-sessions-client"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
HOST = "pellier.test"
SHOPPER = session_cookie_names("shopper")
STAFF = session_cookie_names("staff")
ALL_COOKIES = {
    SHOPPER.access, SHOPPER.id, SHOPPER.refresh, SHOPPER.sign_in_method,
    STAFF.access, STAFF.id, STAFF.refresh, STAFF.sign_in_method,
}
SECRET_USERS = [
    {"username": name, "password": f"{name}-secret"}
    for name in ("anna", "marco", "theo", "jessica", "nadia")
]


class _Signer:
    """Mints Cognito-shaped access tokens the verifier accepts."""

    def __init__(self) -> None:
        self.kid = f"kid-{uuid.uuid4().hex[:8]}"
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwks(self) -> Dict[str, Any]:
        jwk: Dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(self._key.public_key()))
        jwk.update(kid=self.kid, use="sig", alg="RS256")
        return {"keys": [jwk]}

    def token(self, username: str) -> str:
        now = int(time.time())
        claims: Dict[str, Any] = {
            "sub": f"sub-{username}", "username": username, "iss": ISSUER,
            "client_id": CLIENT_ID, "token_use": "access", "iat": now, "exp": now + 3600,
        }
        if username == "nadia":
            claims["cognito:groups"] = [OPERATOR_GROUP]
        pem = self._key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": self.kid})


class _TokenEndpoint:
    """``/oauth2/token`` and ``/oauth2/revoke``: records revocations, mints refreshed tokens."""

    def __init__(self, signer: _Signer) -> None:
        self.signer = signer
        self.revoked: List[str] = []
        self.refreshed_with: List[str] = []
        self.rotate = False
        self.exchange_for: Optional[str] = None

    def post(self, url: str, data: Optional[Dict[str, str]] = None, **_kwargs: Any) -> Any:
        body = dict(data or {})
        if url.endswith("/oauth2/revoke"):
            self.revoked.append(body["token"])
            return SimpleNamespace(status_code=200, json=lambda: {})
        if body.get("grant_type") == "authorization_code":
            user = self.exchange_for or "jessica"
            payload = {"access_token": self.signer.token(user), "id_token": f"id-{user}",
                       "refresh_token": f"refresh-{user}-hosted"}
            return SimpleNamespace(status_code=200, json=lambda: payload)
        token = body["refresh_token"]
        self.refreshed_with.append(token)
        user = token.split("-")[1]
        payload = {"access_token": self.signer.token(user), "id_token": f"id-{user}-2"}
        if self.rotate:
            payload["refresh_token"] = f"refresh-{user}-rotated"
        return SimpleNamespace(status_code=200, json=lambda: payload)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """The real app with synthetic Cognito, one client for one browser."""
    for name, value in {
        "COGNITO_POOL_ID": POOL_ID, "COGNITO_USER_POOL_ID": POOL_ID, "COGNITO_REGION": REGION,
        "COGNITO_CLIENT_ID": CLIENT_ID, "COGNITO_CLIENT_SECRET": None,
        "COGNITO_DOMAIN": "pellier-test.auth.example.com", "APP_BASE_PATH": "",
        "APP_BASE_URL": f"https://{HOST}",
        "OAUTH_REDIRECT_URI": f"https://{HOST}/api/auth/callback",
        "COGNITO_TEST_CREDENTIALS_SECRET_ARN": "arn:secret:test-users",
        "USE_AGENTCORE_RUNTIME": False,
    }.items():
        monkeypatch.setattr(settings, name, value, raising=False)

    signer = _Signer()
    verifier = CognitoAuthService(pool_id=POOL_ID, region=REGION, client_id=CLIENT_ID)
    verifier._fetch_jwks = signer.jwks  # type: ignore[method-assign]
    monkeypatch.setattr(cognito_module, "get_cognito_auth_service", lambda: verifier)

    cognito = Mock()
    cognito.exceptions = boto3.client(
        "cognito-idp", region_name=REGION, aws_access_key_id="test", aws_secret_access_key="test",
    ).exceptions

    def initiate_auth(**params: Any) -> Dict[str, Any]:
        user = params["AuthParameters"]["USERNAME"]
        return {"AuthenticationResult": {
            "AccessToken": signer.token(user), "IdToken": f"id-{user}",
            "RefreshToken": f"refresh-{user}",
        }}

    cognito.initiate_auth.side_effect = initiate_auth
    monkeypatch.setattr(password_module, "_client", lambda: cognito)
    secrets = Mock()
    secrets.get_secret_value.return_value = {"SecretString": json.dumps({"users": SECRET_USERS})}
    monkeypatch.setattr(password_module, "_secrets_client", lambda: secrets)
    password_module._credentials_cache.update(read_at=0.0, users=[])

    endpoint = _TokenEndpoint(signer)
    monkeypatch.setattr(auth_module.requests, "post", endpoint.post)

    async def _reply(**_kwargs: Any):
        reply = {"response": "hello", "products": [], "suggestions": []}
        yield {"type": "complete", "response": reply}

    monkeypatch.setattr(app_module, "chat_service", SimpleNamespace(chat_stream=_reply))
    db = FakeReviewDb()
    app = app_module.app
    memory = SimpleNamespace(get_session_history=_nothing, get_user_preferences=_nothing)
    overrides = {
        get_cognito_auth_service: lambda: verifier,
        get_agentcore_identity_service: lambda: AgentCoreIdentityService(verifier),
        get_agentcore_memory: lambda: memory,
        operator_module.get_db_service: lambda: db,
    }
    app.dependency_overrides.update(overrides)
    try:
        client = TestClient(app, base_url=f"https://{HOST}", follow_redirects=False)
        yield SimpleNamespace(client=client, signer=signer, endpoint=endpoint, db=db)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


async def _nothing(_key: str) -> None:
    """A stand-in memory read: no history and no saved preferences."""
    return None


def _csrf(client: TestClient) -> str:
    return client.get("/api/auth/password/csrf").json()["csrfToken"]


def sign_in_staff(client: TestClient, username: str = "nadia", **extra: Any) -> Any:
    """Nadia types her password on the Operator's sign-in page."""
    return client.post(
        "/api/auth/password/sign-in", headers={"x-csrf-token": _csrf(client)},
        json={"username": username, "password": "typed", "surface": "staff",
              "returnTo": "/operator", **extra},
    )


def choose_shopper(client: TestClient, username: str) -> Any:
    """A shopper's card on the home page: the one-click workshop sign-in."""
    return client.post(
        "/api/auth/password/workshop-sign-in", headers={"x-csrf-token": _csrf(client)},
        json={"username": username},
    )


def me(client: TestClient, surface: Optional[str] = None, **kwargs: Any) -> Any:
    params = {"surface": surface} if surface else None
    return client.get("/api/auth/me", params=params, **kwargs)


def principal_of_a_turn(client: TestClient) -> Dict[str, Any]:
    response = client.post("/api/chat/stream", json={
        "message": "I sent two things back. Can I have a store credit?",
        "conversation_history": [], "session_id": "sess-two", "customer_id": "CUST-JESSICA",
    })
    assert response.status_code == 200, response.text
    events = [json.loads(m) for m in re.findall(r"^data: (.*)$", response.text, re.M)]
    return next(e for e in events if e.get("type") == "turn_start")["principal"]


def set_cookie_names(response: Any, *, cleared: bool) -> set[str]:
    names = set()
    for header in response.headers.get_list("set-cookie"):
        lower = header.lower()
        is_cleared = "max-age=0" in lower or "1970" in lower
        if is_cleared is cleared:
            names.add(header.split("=", 1)[0])
    return names


def both_signed_in(world: SimpleNamespace) -> TestClient:
    client = world.client
    assert sign_in_staff(client).status_code == 200
    assert choose_shopper(client, "jessica").status_code == 200
    return client


# ---------------------------------------------------------------------------
# Both sessions in one browser
# ---------------------------------------------------------------------------


def test_jessica_and_nadia_are_signed_in_at_once(world) -> None:
    client = both_signed_in(world)

    assert me(client, "shopper").json()["username"] == "jessica"
    assert me(client, "staff").json()["username"] == "nadia"
    assert me(client).json()["username"] == "jessica", "the default surface is the shopper"
    for name in ALL_COOKIES - {STAFF.sign_in_method}:
        assert client.cookies.get(name), f"{name} is missing"


def test_the_staff_sign_in_writes_only_the_staff_set(world) -> None:
    response = sign_in_staff(world.client)

    assert response.json() == {"status": "signed_in", "returnTo": "/operator"}
    written = set_cookie_names(response, cleared=False)
    assert {STAFF.access, STAFF.id, STAFF.refresh} <= written
    assert not written & {SHOPPER.access, SHOPPER.id, SHOPPER.refresh, SHOPPER.sign_in_method}
    for name in (STAFF.access, STAFF.id, STAFF.refresh):
        headers = response.headers.get_list("set-cookie")
        header = next(h for h in headers if h.startswith(f"{name}="))
        assert "HttpOnly" in header and "Secure" in header and "SameSite=lax" in header
    assert me(world.client, "shopper").status_code == 401


def test_a_shopper_turn_runs_as_jessica_and_an_approval_is_decided_by_nadia(world) -> None:
    client = both_signed_in(world)

    assert principal_of_a_turn(client) == {
        "authenticated": True, "customerId": "CUST-JESSICA", "signInMethod": "workshop",
    }
    review = world.db.add_pending()
    decided = client.post(
        f"/api/operator/reviews/{review['review_id']}/confirm", json={"actionHash": JESSICA_HASH},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["decidedBy"] == "sub-nadia"
    assert decided.json()["decidedByName"] == "nadia"


# ---------------------------------------------------------------------------
# Neither session falls back to the other
# ---------------------------------------------------------------------------


def test_a_shopper_session_alone_is_refused_by_the_operator(world) -> None:
    client = world.client
    choose_shopper(client, "jessica")

    for path in ("/api/operator/reviews", "/api/operator/clients"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["detail"] == "authentication_required"
    assert me(client, "staff").status_code == 401


def test_a_staff_session_alone_is_signed_out_on_the_storefront(world) -> None:
    client = world.client
    sign_in_staff(client)

    assert me(client, "shopper").status_code == 401
    assert principal_of_a_turn(client) == {
        "authenticated": False, "customerId": None, "signInMethod": None,
    }
    assert client.get("/api/operator/reviews").status_code == 200


def test_a_staff_token_in_the_shopper_set_reads_as_signed_out(world) -> None:
    """A cookie from before the sets were split: staff are never the storefront's shopper."""
    client = world.client
    client.cookies.set(SHOPPER.access, quote(world.signer.token("nadia"), safe=""), domain=HOST)

    assert me(client, "shopper").status_code == 401
    assert principal_of_a_turn(client)["authenticated"] is False
    assert client.get("/api/operator/reviews").status_code == 401


def storefront_reads(client: TestClient) -> Dict[str, Any]:
    """What each shopper-cookie reader makes of the session: ``require_user`` and Identity."""
    return {
        "preferences": client.get("/api/user/preferences").status_code,
        "agent_session": client.get("/api/agent/session/sess-two").json()["authenticated"],
    }


def test_a_staff_token_in_the_shopper_set_is_signed_out_everywhere_on_the_storefront(
    world,
) -> None:
    """Preferences, cart, products and agent chat read it like ``/me`` does: signed out."""
    client = world.client
    client.cookies.set(SHOPPER.access, quote(world.signer.token("nadia"), safe=""), domain=HOST)

    assert storefront_reads(client) == {"preferences": 401, "agent_session": False}
    assert client.post("/api/commerce/quotes", json={}).status_code == 401

    client.cookies.set(SHOPPER.access, quote(world.signer.token("jessica"), safe=""), domain=HOST)
    assert storefront_reads(client) == {"preferences": 200, "agent_session": True}


def test_a_staff_refresh_token_in_the_shopper_set_is_cleared_not_re_minted(world) -> None:
    """The pre-split cookies heal on the first storefront load; Nadia's own session stays."""
    client = world.client
    sign_in_staff(client)
    client.cookies.set(SHOPPER.access, quote(world.signer.token("nadia"), safe=""), domain=HOST)
    client.cookies.set(SHOPPER.refresh, "refresh-nadia", domain=HOST)

    response = client.post("/api/auth/refresh", params={"surface": "shopper"})

    assert response.status_code == 401
    assert response.json() == {"error": "refresh_failed"}
    assert set_cookie_names(response, cleared=True) == {
        SHOPPER.access, SHOPPER.id, SHOPPER.refresh, SHOPPER.sign_in_method,
    }
    assert not set_cookie_names(response, cleared=False) & ALL_COOKIES
    assert client.cookies.get(SHOPPER.refresh) is None
    assert me(client, "shopper").status_code == 401
    assert me(client, "staff").json()["username"] == "nadia"


def test_a_bearer_header_works_exactly_as_before(world) -> None:
    """curl, Gateway and Runtime callers present a bearer token, and it wins over any cookie."""
    client = world.client
    nadia = {"Authorization": f"Bearer {world.signer.token('nadia')}"}
    jessica = {"Authorization": f"Bearer {world.signer.token('jessica')}"}

    assert client.get("/api/operator/reviews", headers=nadia).status_code == 200
    assert client.get("/api/operator/reviews", headers=jessica).status_code == 403
    assert me(client, headers=jessica).json()["username"] == "jessica"
    assert me(client, "staff", headers=nadia).json()["username"] == "nadia"
    assert me(client, "shopper", headers=nadia).json()["username"] == "nadia"
    choose_shopper(client, "jessica")
    assert client.get("/api/operator/reviews", headers=nadia).status_code == 200


def test_an_unknown_surface_is_refused(world) -> None:
    client = world.client
    assert me(client, "admin").status_code == 422
    assert client.post("/api/auth/logout", params={"surface": "admin"}).status_code == 422
    response = client.post(
        "/api/auth/password/sign-in", headers={"x-csrf-token": _csrf(client)},
        json={"username": "nadia", "password": "typed", "surface": "admin"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_input"


# ---------------------------------------------------------------------------
# Writing: each sign-in, sign-out and refresh touches only its own set
# ---------------------------------------------------------------------------


def test_choosing_another_shopper_leaves_nadia_signed_in(world) -> None:
    client = world.client
    sign_in_staff(client)
    choose_shopper(client, "theo")

    response = choose_shopper(client, "jessica")

    assert response.status_code == 200
    assert world.endpoint.revoked == ["refresh-theo"], "only the previous shopper is revoked"
    assert not set_cookie_names(response, cleared=False) & {STAFF.access, STAFF.id, STAFF.refresh}
    assert me(client, "shopper").json()["username"] == "jessica"
    assert me(client, "staff").json()["username"] == "nadia"


def test_staff_signing_out_leaves_jessica_signed_in(world) -> None:
    client = both_signed_in(world)

    response = client.post("/api/auth/logout", params={"surface": "staff"})

    assert response.status_code == 200
    assert world.endpoint.revoked == ["refresh-nadia"]
    assert set_cookie_names(response, cleared=True) == {
        STAFF.access, STAFF.id, STAFF.refresh, STAFF.sign_in_method,
    }
    assert me(client, "staff").status_code == 401
    assert me(client, "shopper").json()["username"] == "jessica"


def test_the_shopper_signing_out_leaves_nadia_signed_in(world) -> None:
    client = both_signed_in(world)

    response = client.post("/api/auth/logout", params={"surface": "shopper"})

    assert world.endpoint.revoked == ["refresh-jessica"]
    cleared = set_cookie_names(response, cleared=True)
    assert {SHOPPER.access, SHOPPER.id, SHOPPER.refresh, SHOPPER.sign_in_method} <= cleared
    assert not cleared & {STAFF.access, STAFF.id, STAFF.refresh, STAFF.sign_in_method}
    assert me(client, "shopper").status_code == 401
    assert me(client, "staff").json()["username"] == "nadia"


@pytest.mark.parametrize(
    "surface, user, other", [("staff", "nadia", "jessica"), ("shopper", "jessica", "nadia")],
)
def test_a_refresh_rotates_only_its_own_set(world, surface: str, user: str, other: str) -> None:
    client = both_signed_in(world)
    names, others = (STAFF, SHOPPER) if surface == "staff" else (SHOPPER, STAFF)

    response = client.post("/api/auth/refresh", params={"surface": surface})

    assert response.status_code == 200, response.text
    assert world.endpoint.refreshed_with == [f"refresh-{user}"]
    written = set_cookie_names(response, cleared=False)
    assert {names.access, names.id} <= written
    assert not written & {others.access, others.id, others.refresh, others.sign_in_method}
    assert me(client, "staff" if surface == "shopper" else "shopper").json()["username"] == other


def test_a_rejected_refresh_clears_only_its_own_set(world, monkeypatch) -> None:
    client = both_signed_in(world)
    monkeypatch.setattr(auth_module.requests, "post", lambda *_a, **_k: SimpleNamespace(
        status_code=400, json=lambda: {"error": "invalid_grant"},
    ))

    response = client.post("/api/auth/refresh", params={"surface": "staff"})

    assert response.status_code == 401
    assert set_cookie_names(response, cleared=True) == {
        STAFF.access, STAFF.id, STAFF.refresh, STAFF.sign_in_method,
    }
    assert me(client, "shopper").json()["username"] == "jessica"


def test_the_workshop_marker_lives_as_long_as_the_session(world) -> None:
    """The Builder line keeps "Workshop sign-in" past the access token's hour."""
    client = world.client
    response = choose_shopper(client, "jessica")

    marker = next(h for h in response.headers.get_list("set-cookie")
                  if h.startswith(f"{SHOPPER.sign_in_method}="))
    assert f"Max-Age={auth_module.REFRESH_COOKIE_MAX_AGE}" in marker
    assert "HttpOnly" in marker

    world.endpoint.rotate = True
    rotated = client.post("/api/auth/refresh", params={"surface": "shopper"})
    assert f"{SHOPPER.sign_in_method}=workshop" in rotated.headers.get("set-cookie", "")
    assert me(client, "shopper").json()["sign_in_method"] == "workshop"
    assert me(client, "staff").status_code == 401


# ---------------------------------------------------------------------------
# A staff account never becomes the storefront's shopper
# ---------------------------------------------------------------------------


def test_a_staff_password_on_the_storefront_sign_in_is_refused(world) -> None:
    client = world.client
    response = client.post(
        "/api/auth/password/sign-in", headers={"x-csrf-token": _csrf(client)},
        json={"username": "nadia", "password": "typed"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "staff_use_operator"
    assert not set_cookie_names(response, cleared=False) & ALL_COOKIES


def test_a_shopper_on_the_operator_sign_in_gets_a_staff_session_the_desk_refuses(world) -> None:
    """The group check is unchanged: a shopper in the staff set is known and not permitted."""
    client = world.client
    assert sign_in_staff(client, username="jessica").status_code == 200

    response = client.get("/api/operator/reviews")

    assert response.status_code == 403
    assert response.json()["detail"] == "operator_group_required"
    # The staff set never stands in for the storefront's shopper.
    assert me(client, "shopper").status_code == 401
    assert principal_of_a_turn(client)["authenticated"] is False


# ---------------------------------------------------------------------------
# Hosted UI: the surface travels inside the signed OAuth state
# ---------------------------------------------------------------------------


def _begin_hosted(client: TestClient, surface: Optional[str] = None) -> str:
    params = {"provider": "email", "returnTo": "/operator"}
    if surface:
        params["surface"] = surface
    response = client.get("/api/auth/signin", params=params)
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_the_oauth_state_carries_the_surface_and_the_callback_writes_that_set(world) -> None:
    client = world.client
    choose_shopper(client, "jessica")
    state = _begin_hosted(client, "staff")
    assert state.split(".")[2] == "staff"
    world.endpoint.exchange_for = "nadia"

    response = client.get("/api/auth/callback", params={"code": "code", "state": state})

    assert response.status_code == 302, response.text
    written = set_cookie_names(response, cleared=False)
    assert {STAFF.access, STAFF.id, STAFF.refresh} <= written
    assert not written & {SHOPPER.access, SHOPPER.id, SHOPPER.refresh}
    assert me(client, "staff").json()["username"] == "nadia"
    assert me(client, "shopper").json()["username"] == "jessica"
    assert me(client, "shopper").json()["sign_in_method"] == "workshop"


def test_a_tampered_surface_in_the_state_is_refused(world) -> None:
    client = world.client
    state = _begin_hosted(client)
    nonce, expiry, surface, signature = state.split(".")
    assert surface == "shopper"
    forged = f"{nonce}.{expiry}.staff.{signature}"
    staff_state = auth_module.oauth_cookie_names("staff").state
    client.cookies.set(staff_state, forged, domain=HOST, path="/api/auth")

    response = client.get("/api/auth/callback", params={"code": "code", "state": forged})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_state"}
    assert not set_cookie_names(response, cleared=False) & ALL_COOKIES


def test_a_hosted_staff_sign_in_on_the_storefront_lands_on_the_operator_sign_in(world) -> None:
    """Not a JSON page: the Operator's sign-in, which says why, and no session written."""
    client = world.client
    choose_shopper(client, "jessica")
    state = _begin_hosted(client)
    world.endpoint.exchange_for = "nadia"

    response = client.get("/api/auth/callback", params={"code": "code", "state": state})

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"https://{HOST}/signin?error=staff_use_operator&workspace=operator"
    )
    assert not set_cookie_names(response, cleared=False) & ALL_COOKIES
    assert not set_cookie_names(response, cleared=True) & ALL_COOKIES
    assert auth_module.oauth_cookie_names("shopper").state not in client.cookies
    assert me(client, "shopper").json()["username"] == "jessica"
    assert me(client, "staff").status_code == 401


def test_two_hosted_sign_ins_in_two_tabs_both_complete(world) -> None:
    """Each surface keeps its own state, PKCE and return-to cookies, so neither overwrites."""
    client = world.client
    shopper_state = _begin_hosted(client)
    staff_state = _begin_hosted(client, "staff")
    staff_cookies = auth_module.oauth_cookie_names("staff")

    world.endpoint.exchange_for = "jessica"
    shopper = client.get("/api/auth/callback", params={"code": "c1", "state": shopper_state})
    assert shopper.status_code == 302, shopper.text
    assert client.cookies.get(staff_cookies.state) == staff_state, "the staff tab is in flight"

    world.endpoint.exchange_for = "nadia"
    staff = client.get("/api/auth/callback", params={"code": "c2", "state": staff_state})
    assert staff.status_code == 302, staff.text
    assert me(client, "shopper").json()["username"] == "jessica"
    assert me(client, "staff").json()["username"] == "nadia"
