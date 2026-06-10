"""Unit tests for ``routes.user`` — the ``/api/user/preferences`` surface (Task 3.4).

Validates Requirements 3.2.1–3.2.4 and 4.4.1–4.4.3 without any live
Cognito traffic or AgentCore Memory resource. Tests mint access tokens
via a synthetic RSA signer (mirroring ``test_auth_routes.py`` /
``test_cognito_auth.py``), override the shared ``CognitoAuthService``
dependency so JWKS resolution uses the in-test key, and reset the
module-level ``_PREFS_STORE`` between tests (per
``test_agentcore_memory.py``) so the in-memory fallback is
deterministic.

Covered assertions (from tasks.md Task 3.4 "Test verification"):

  * GET returns ``{"preferences": null}`` when no prefs are stored
  * POST round-trip: saved payload matches what GET returns next
  * POST with an unknown tag value returns 422 with the offending field
    names in ``detail[*].loc``

Plus the guard cases Req 4.2.2 mandates:

  * GET/POST without a valid token 401 ``auth_failed``
  * Preferences are scoped by Cognito ``sub``: user A cannot read user B's

Runnable from the repo root per ``pytest.ini``:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_preferences_api.py -v
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

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
import services.agentcore_memory as memory_module
from services.agentcore_memory import AgentCoreMemory
from routes.user import get_agentcore_memory, router as user_router


# ---------------------------------------------------------------------------
# Test pool identity — matches test_auth_routes.py / test_cognito_auth.py
# ---------------------------------------------------------------------------

POOL_ID = "us-east-1_TESTPOOL"
REGION = "us-east-1"
CLIENT_ID = "test-client-id"
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
    sub: str = "cognito-sub-prefs",
    email: str = "shopper@example.com",
    given_name: str = "Avery",
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


@pytest.fixture(autouse=True)
def _reset_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level fallback dicts between tests and force the
    SDK-unavailable path so every test runs deterministically against
    the in-memory fallback. Mirrors ``test_agentcore_memory.py``.
    """
    monkeypatch.setattr(memory_module, "_SESSION_STORE", {})
    monkeypatch.setattr(memory_module, "_PREFS_STORE", {})
    monkeypatch.setattr(memory_module.settings, "AGENTCORE_MEMORY_ID", None)


@pytest.fixture
def signer() -> _Signer:
    return _Signer(kid="prefs-api-kid")


@pytest.fixture
def auth_service(signer: _Signer) -> CognitoAuthService:
    """JWKS-backed service wired to the synthetic signer."""
    svc = CognitoAuthService(pool_id=POOL_ID, region=REGION, client_id=CLIENT_ID)
    svc._fetch_jwks = lambda: {"keys": [signer.public_jwk()]}  # type: ignore[assignment]
    return svc


@pytest.fixture
def memory() -> AgentCoreMemory:
    """Fresh ``AgentCoreMemory`` instance shared across the request cycle."""
    return AgentCoreMemory()


@pytest.fixture
def client(auth_service: CognitoAuthService, memory: AgentCoreMemory) -> TestClient:
    """FastAPI test app with only the user router mounted.

    Isolates the router from ``app.py`` so the tests don't need the full
    lifespan (database, embeddings, Bedrock). Both the Cognito service
    and the AgentCore Memory instance are overridden so the handler
    sees the synthetic JWKS and an isolated prefs store.
    """
    app = FastAPI()
    app.include_router(user_router)
    app.dependency_overrides[get_cognito_auth_service] = lambda: auth_service
    app.dependency_overrides[get_agentcore_memory] = lambda: memory
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/user/preferences
# ---------------------------------------------------------------------------


def test_get_preferences_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/user/preferences")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "auth_failed"}


def test_get_preferences_returns_null_when_unseen(
    client: TestClient, signer: _Signer
) -> None:
    """Req 3.2.1: a user with no saved prefs SHALL return ``null``
    explicitly so the SPA can distinguish "never onboarded" from
    "onboarded with no selections" (Req 1.4.4)."""
    token = signer.sign(_access_claims(sub="unseen-user"))
    resp = client.get(
        "/api/user/preferences",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"preferences": None}


# ---------------------------------------------------------------------------
# POST /api/user/preferences — round-trip
# ---------------------------------------------------------------------------


def test_post_preferences_without_token_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/user/preferences",
        json={"vibe": [], "colors": [], "occasions": [], "categories": []},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "auth_failed"}


def test_post_then_get_preferences_round_trip(
    client: TestClient, signer: _Signer
) -> None:
    """Req 3.2.2: POST persists the payload, and the next GET returns
    exactly what was saved under the same JWT ``sub``."""
    token = signer.sign(_access_claims(sub="round-trip-user"))
    payload = {
        "vibe": ["minimal", "serene"],
        "colors": ["warm", "neutral"],
        "occasions": ["everyday", "slow"],
        "categories": ["linen"],
    }

    post_resp = client.post(
        "/api/user/preferences",
        json=payload,
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert post_resp.status_code == 200
    assert post_resp.json() == {"preferences": payload}

    get_resp = client.get(
        "/api/user/preferences",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert get_resp.status_code == 200
    assert get_resp.json() == {"preferences": payload}


def test_post_preferences_accepts_empty_groups(
    client: TestClient, signer: _Signer
) -> None:
    """Empty lists are valid — the preferences modal allows a user to
    save without selecting any tags in a given group."""
    token = signer.sign(_access_claims(sub="empty-groups-user"))
    payload = {"vibe": [], "colors": [], "occasions": [], "categories": []}

    resp = client.post(
        "/api/user/preferences",
        json=payload,
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"preferences": payload}


def test_preferences_scoped_per_cognito_sub(
    client: TestClient, signer: _Signer
) -> None:
    """Req 4.4.2: two users SHALL NOT see each other's preferences.

    Stored at ``user:{sub}:preferences`` — swapping the JWT returns a
    different entry even over the same session cookie.
    """
    alice_token = signer.sign(_access_claims(sub="alice-sub"))
    bob_token = signer.sign(_access_claims(sub="bob-sub"))

    alice_prefs = {
        "vibe": ["minimal"],
        "colors": ["neutral"],
        "occasions": ["everyday"],
        "categories": ["linen"],
    }
    bob_prefs = {
        "vibe": ["bold"],
        "colors": ["moody"],
        "occasions": ["evening"],
        "categories": ["dresses"],
    }

    client.post(
        "/api/user/preferences",
        json=alice_prefs,
        cookies={ACCESS_TOKEN_COOKIE: alice_token},
    )
    client.post(
        "/api/user/preferences",
        json=bob_prefs,
        cookies={ACCESS_TOKEN_COOKIE: bob_token},
    )

    alice_get = client.get(
        "/api/user/preferences",
        cookies={ACCESS_TOKEN_COOKIE: alice_token},
    )
    bob_get = client.get(
        "/api/user/preferences",
        cookies={ACCESS_TOKEN_COOKIE: bob_token},
    )
    assert alice_get.json() == {"preferences": alice_prefs}
    assert bob_get.json() == {"preferences": bob_prefs}


# ---------------------------------------------------------------------------
# POST /api/user/preferences — validation (422 on unknown tag values)
# ---------------------------------------------------------------------------


def _error_locs(detail: Any) -> list[tuple]:
    """Return the ``loc`` tuples from a FastAPI 422 ``detail`` array.

    Pydantic reports each invalid field as ``{"loc": [...], "msg": ...,
    "type": ...}``; the route test below uses this to assert the
    offending group name shows up in the loc path.
    """
    assert isinstance(detail, list)
    return [tuple(entry["loc"]) for entry in detail]


def test_post_preferences_unknown_vibe_returns_422_with_offending_field(
    client: TestClient, signer: _Signer
) -> None:
    """Req 3.2.3: an unknown tag value SHALL surface as 422 with the
    offending field name in the error ``loc`` path.

    Pydantic emits one error per invalid list entry with a loc path like
    ``("body", "vibe", 0)`` — this test asserts both the field group
    and the 422 status without locking the error ``type`` string (which
    varies across Pydantic minor versions).
    """
    token = signer.sign(_access_claims(sub="validation-user"))
    bad_payload = {
        "vibe": ["wild"],          # not in VibeTag Literal
        "colors": [],
        "occasions": [],
        "categories": [],
    }

    resp = client.post(
        "/api/user/preferences",
        json=bad_payload,
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body

    locs = _error_locs(body["detail"])
    # The offending field path must mention "vibe" so the frontend can
    # shake the right preference group (Error Handling table row).
    assert any("vibe" in loc for loc in locs), f"expected 'vibe' in {locs}"


def test_post_preferences_unknown_color_returns_422(
    client: TestClient, signer: _Signer
) -> None:
    token = signer.sign(_access_claims(sub="validation-user"))
    bad_payload = {
        "vibe": [],
        "colors": ["ultraviolet"],  # not in ColorTag Literal
        "occasions": [],
        "categories": [],
    }

    resp = client.post(
        "/api/user/preferences",
        json=bad_payload,
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 422
    locs = _error_locs(resp.json()["detail"])
    assert any("colors" in loc for loc in locs), f"expected 'colors' in {locs}"


def test_post_preferences_multiple_unknown_values_surface_all_offending_fields(
    client: TestClient, signer: _Signer
) -> None:
    """Every invalid tag group SHALL be reported in a single 422 so the
    SPA can highlight all offending chips at once, not one at a time."""
    token = signer.sign(_access_claims(sub="validation-user"))
    bad_payload = {
        "vibe": ["wild"],
        "colors": ["ultraviolet"],
        "occasions": ["nighttime"],
        "categories": ["jewelry"],
    }

    resp = client.post(
        "/api/user/preferences",
        json=bad_payload,
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 422
    locs = _error_locs(resp.json()["detail"])
    # Flatten every loc tuple and assert all four group names show up.
    flat = {item for loc in locs for item in loc}
    for expected in ("vibe", "colors", "occasions", "categories"):
        assert expected in flat, f"expected '{expected}' in {flat}"


def test_post_preferences_persistence_survives_new_token_for_same_sub(
    client: TestClient, signer: _Signer
) -> None:
    """"Done when" check from tasks.md: preferences persist across
    sign-out/sign-in with the same IdP subject.

    Simulated here by minting a fresh JWT with the same ``sub`` and
    asserting the stored prefs come back — the namespace key is built
    from ``sub``, not from the token itself.
    """
    sub = "persistent-user"
    first_token = signer.sign(_access_claims(sub=sub, given_name="Avery"))
    prefs = {
        "vibe": ["classic"],
        "colors": ["earth"],
        "occasions": ["travel"],
        "categories": ["outerwear"],
    }
    client.post(
        "/api/user/preferences",
        json=prefs,
        cookies={ACCESS_TOKEN_COOKIE: first_token},
    )

    # A "sign out / sign back in" cycle mints a new JWT for the same
    # ``sub``. The JWT body is identical here (same ``iat``/``exp``)
    # because the clock hasn't advanced, but the namespace derivation
    # only touches the ``sub`` claim, so this still exercises the
    # "persist across sessions" path end-to-end.
    second_token = signer.sign(_access_claims(sub=sub, given_name="Avery"))

    resp = client.get(
        "/api/user/preferences",
        cookies={ACCESS_TOKEN_COOKIE: second_token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"preferences": prefs}
