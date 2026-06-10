"""Unit tests for ``services.cognito_auth.CognitoAuthService`` (Task 3.1).

Validates Requirement 4.2 (JWT verification middleware) and 5.3 (security)
without any live Cognito call. Tests mint JWTs signed by a locally
generated RSA key, expose that key as a synthetic JWKS, and patch the
service's ``_fetch_jwks`` to return it.

Covered assertions (from tasks.md Task 3.1 "Test verification"):

  * valid access token passes
  * expired token fails
  * wrong ``iss`` fails
  * wrong ``aud``/``client_id`` fails
  * wrong ``token_use`` fails
  * token signed by a key not in the JWKS fails
  * JWKS fetch is called once for N concurrent validations (cache hit)

Plus the "Done when" checks:

  * protected endpoint returns 401 without a token
  * protected endpoint populates ``request.state.user`` with a valid one

Async methods are dispatched via ``asyncio.run`` per the repo convention in
``test_runtime_switch.py`` and ``test_vector_search.py`` (no pytest-asyncio
plugin is installed in the backend venv).

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_cognito_auth.py -v
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Coroutine, Dict, List, Optional, TypeVar

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from services.cognito_auth import (
    ACCESS_TOKEN_COOKIE,
    CognitoAuthService,
    require_user,
)


T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a sync test without needing a plugin."""
    return asyncio.run(coro)


POOL_ID = "us-east-1_TESTPOOL"
REGION = "us-east-1"
CLIENT_ID = "test-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"


# ---------------------------------------------------------------------------
# Crypto + JWKS helpers
# ---------------------------------------------------------------------------


class _Signer:
    """Self-contained RSA keypair that can mint JWTs and publish its JWK.

    Each instance gets a unique ``kid`` so tests can build multi-key JWKS
    documents (one trusted, one unknown) and prove the validator picks
    the right entry.
    """

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


def _build_jwks(signers: List[_Signer]) -> Dict[str, Any]:
    return {"keys": [s.public_jwk() for s in signers]}


def _valid_access_claims(
    *,
    sub: str = "cognito-sub-123",
    email: str = "shopper@example.com",
    given_name: str = "Avery",
    exp_offset: int = 3600,
    issuer: str = ISSUER,
    client_id: str = CLIENT_ID,
    token_use: str = "access",
) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "sub": sub,
        "email": email,
        "given_name": given_name,
        "iss": issuer,
        "client_id": client_id,
        "token_use": token_use,
        "iat": now,
        "exp": now + exp_offset,
        "auth_time": now,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def signer() -> _Signer:
    return _Signer(kid="test-kid-main")


@pytest.fixture
def jwks_call_count() -> Dict[str, int]:
    return {"n": 0}


@pytest.fixture
def auth_service(signer: _Signer, jwks_call_count: Dict[str, int]) -> CognitoAuthService:
    """A ``CognitoAuthService`` wired to a synthetic JWKS.

    ``_fetch_jwks`` is patched to count invocations so the concurrent-fetch
    property test can assert a single underlying fetch for N callers.
    """
    svc = CognitoAuthService(pool_id=POOL_ID, region=REGION, client_id=CLIENT_ID)

    def _fake_fetch() -> Dict[str, Any]:
        jwks_call_count["n"] += 1
        return _build_jwks([signer])

    svc._fetch_jwks = _fake_fetch  # type: ignore[assignment]
    return svc


# ---------------------------------------------------------------------------
# validate_jwt — success paths
# ---------------------------------------------------------------------------


def test_valid_access_token_passes(auth_service: CognitoAuthService, signer: _Signer) -> None:
    token = signer.sign(_valid_access_claims())
    user = _run(auth_service.validate_jwt(token))
    assert user.user_id == "cognito-sub-123"
    assert user.email == "shopper@example.com"
    assert user.given_name == "Avery"


def test_valid_token_with_aud_instead_of_client_id_passes(
    auth_service: CognitoAuthService, signer: _Signer
) -> None:
    """id-tokens (and some access-token variants) carry ``aud`` instead."""
    claims = _valid_access_claims()
    claims.pop("client_id")
    claims["aud"] = CLIENT_ID
    token = signer.sign(claims)
    user = _run(auth_service.validate_jwt(token))
    assert user.user_id == "cognito-sub-123"


# ---------------------------------------------------------------------------
# validate_jwt — failure paths
# ---------------------------------------------------------------------------


def test_expired_token_fails(auth_service: CognitoAuthService, signer: _Signer) -> None:
    token = signer.sign(_valid_access_claims(exp_offset=-60))
    with pytest.raises(Exception) as exc:
        _run(auth_service.validate_jwt(token))
    assert getattr(exc.value, "status_code", None) == 401


def test_wrong_iss_fails(auth_service: CognitoAuthService, signer: _Signer) -> None:
    claims = _valid_access_claims(issuer="https://evil.example.com/poolX")
    token = signer.sign(claims)
    with pytest.raises(Exception) as exc:
        _run(auth_service.validate_jwt(token))
    assert getattr(exc.value, "status_code", None) == 401


def test_wrong_aud_fails(auth_service: CognitoAuthService, signer: _Signer) -> None:
    claims = _valid_access_claims(client_id="someone-else")
    token = signer.sign(claims)
    with pytest.raises(Exception) as exc:
        _run(auth_service.validate_jwt(token))
    assert getattr(exc.value, "status_code", None) == 401


def test_wrong_token_use_fails(auth_service: CognitoAuthService, signer: _Signer) -> None:
    claims = _valid_access_claims(token_use="id")  # id-token where an access token is required
    token = signer.sign(claims)
    with pytest.raises(Exception) as exc:
        _run(auth_service.validate_jwt(token))
    assert getattr(exc.value, "status_code", None) == 401


def test_unsigned_by_jwks_fails(auth_service: CognitoAuthService) -> None:
    """A token signed by a key absent from the JWKS is rejected."""
    rogue = _Signer(kid="rogue-kid")
    token = rogue.sign(_valid_access_claims())
    with pytest.raises(Exception) as exc:
        _run(auth_service.validate_jwt(token))
    assert getattr(exc.value, "status_code", None) == 401


def test_tampered_signature_fails(auth_service: CognitoAuthService, signer: _Signer) -> None:
    token = signer.sign(_valid_access_claims())
    # JWTs are ``header.payload.signature``. Replace the signature block
    # entirely with a same-length but definitely-wrong base64url string
    # so RS256 verification must fail deterministically (flipping a
    # single character isn't reliable because base64 has redundancy).
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{'A' * len(signature)}"
    with pytest.raises(Exception) as exc:
        _run(auth_service.validate_jwt(tampered))
    assert getattr(exc.value, "status_code", None) == 401


# ---------------------------------------------------------------------------
# JWKS cache — concurrent fetch collapses to one
# ---------------------------------------------------------------------------


def test_jwks_fetched_once_for_concurrent_validations(
    auth_service: CognitoAuthService,
    signer: _Signer,
    jwks_call_count: Dict[str, int],
) -> None:
    """N concurrent ``validate_jwt`` calls collapse to a single fetch.

    This is the core Req 4.2.1 cache-hit assertion: a cold cache + 20
    simultaneous validations must not stampede the JWKS endpoint.
    """
    tokens = [signer.sign(_valid_access_claims(sub=f"user-{i}")) for i in range(20)]

    async def _run_all() -> List[Any]:
        return await asyncio.gather(*(auth_service.validate_jwt(t) for t in tokens))

    results = _run(_run_all())

    assert len(results) == 20
    assert jwks_call_count["n"] == 1


def test_jwks_cache_hit_avoids_second_fetch(
    auth_service: CognitoAuthService,
    signer: _Signer,
    jwks_call_count: Dict[str, int],
) -> None:
    token = signer.sign(_valid_access_claims())

    async def _three() -> None:
        await auth_service.validate_jwt(token)
        await auth_service.validate_jwt(token)
        await auth_service.validate_jwt(token)

    _run(_three())
    assert jwks_call_count["n"] == 1


# ---------------------------------------------------------------------------
# extract_user — header vs cookie priority
# ---------------------------------------------------------------------------


def _make_request(
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
) -> Request:
    raw_headers: List[tuple[bytes, bytes]] = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "query_string": b"",
        "client": ("test", 0),
    }
    return Request(scope)


def test_extract_user_reads_bearer_header(
    auth_service: CognitoAuthService, signer: _Signer
) -> None:
    token = signer.sign(_valid_access_claims())
    req = _make_request(headers={"Authorization": f"Bearer {token}"})
    user = _run(auth_service.extract_user(req))
    assert user is not None
    assert user.user_id == "cognito-sub-123"


def test_extract_user_falls_back_to_cookie(
    auth_service: CognitoAuthService, signer: _Signer
) -> None:
    token = signer.sign(_valid_access_claims())
    req = _make_request(cookies={ACCESS_TOKEN_COOKIE: token})
    user = _run(auth_service.extract_user(req))
    assert user is not None
    assert user.user_id == "cognito-sub-123"


def test_extract_user_prefers_header_over_cookie(
    auth_service: CognitoAuthService, signer: _Signer
) -> None:
    good = signer.sign(_valid_access_claims(sub="header-user"))
    bad = signer.sign(_valid_access_claims(sub="cookie-user", exp_offset=-60))
    req = _make_request(
        headers={"Authorization": f"Bearer {good}"},
        cookies={ACCESS_TOKEN_COOKIE: bad},
    )
    user = _run(auth_service.extract_user(req))
    assert user is not None
    assert user.user_id == "header-user"


def test_extract_user_returns_none_without_credentials(
    auth_service: CognitoAuthService,
) -> None:
    req = _make_request()
    assert _run(auth_service.extract_user(req)) is None


def test_extract_user_returns_none_on_invalid_token(
    auth_service: CognitoAuthService,
) -> None:
    req = _make_request(headers={"Authorization": "Bearer not-a-jwt"})
    assert _run(auth_service.extract_user(req)) is None


# ---------------------------------------------------------------------------
# require_user — FastAPI dependency integration ("Done when")
# ---------------------------------------------------------------------------


def _protected_app(service: CognitoAuthService) -> FastAPI:
    app = FastAPI()

    # Override the module-level service accessor so require_user uses our
    # synthetic JWKS-backed instance.
    from services import cognito_auth as mod

    app.dependency_overrides[mod.get_cognito_auth_service] = lambda: service

    @app.get("/api/protected")
    async def protected(request: Request, user=Depends(require_user)) -> Dict[str, str]:
        # request.state.user must be populated by require_user
        assert request.state.user.user_id == user.user_id
        return {"user_id": user.user_id, "given_name": user.given_name}

    return app


def test_protected_endpoint_401_without_token(auth_service: CognitoAuthService) -> None:
    client = TestClient(_protected_app(auth_service))
    resp = client.get("/api/protected")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "auth_failed"}


def test_protected_endpoint_populates_request_state_user(
    auth_service: CognitoAuthService, signer: _Signer
) -> None:
    token = signer.sign(_valid_access_claims())
    client = TestClient(_protected_app(auth_service))
    resp = client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "cognito-sub-123", "given_name": "Avery"}


def test_protected_endpoint_accepts_cookie(
    auth_service: CognitoAuthService, signer: _Signer
) -> None:
    token = signer.sign(_valid_access_claims(sub="cookie-user", given_name="Rowan"))
    client = TestClient(_protected_app(auth_service))
    resp = client.get("/api/protected", cookies={ACCESS_TOKEN_COOKIE: token})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "cookie-user", "given_name": "Rowan"}
