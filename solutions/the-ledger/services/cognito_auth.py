"""
CognitoAuthService — JWT validation middleware for the storefront backend.

Challenge 9.1 (Requirements 4.2.1–4.2.4, 5.3.1–5.3.3). Verifies Amazon
Cognito access tokens against the pool's JWKS endpoint and exposes a
FastAPI dependency ``require_user`` that populates ``request.state.user``
with a ``VerifiedUser``.

This is the backend half of Challenge 9's four-file capstone:

    9.1  services/cognito_auth.py          ← this file
    9.2  services/agentcore_identity.py
    9.3  frontend/src/utils/auth.ts
    9.4  frontend/src/components/{AuthModal,PreferencesModal}.tsx

Key design choices (Req 4.2):

  * JWKS is fetched once per ``CognitoAuthService`` instance and cached
    for 1 hour. A single ``asyncio.Lock`` guards the refresh so N
    concurrent validations trigger exactly one HTTP fetch (Req 4.2.1).
  * The validator enforces signature (RS256), ``iss``, ``aud``, ``exp``,
    and ``token_use == "access"`` per Req 4.2.2 and 2.6.3.
  * ``extract_user`` checks the ``Authorization: Bearer`` header first
    and only falls back to the ``access_token`` cookie (spec priority).
  * Tokens never appear in logs (Req 5.3.3). The service logs validation
    failures with the exception class only.

The workshop ``solutions/the-ledger/services/cognito_auth.py`` file mirrors
the CHALLENGE 9.1 block here byte-for-byte (enforced by Task 7.4).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import jwt
import requests
from fastapi import Depends, HTTPException, Request
from jwt.algorithms import RSAAlgorithm

from config import settings
from models import VerifiedUser

logger = logging.getLogger(__name__)


# === CHALLENGE 9.1: Cognito JWT validation — START ===
# Requirements 4.2.1–4.2.4, 5.3.1–5.3.3 and Design "services/cognito_auth.py".
#
# Participants delete this block and reimplement ``CognitoAuthService``
# + ``require_user`` using PyJWT + the Cognito JWKS endpoint. The tests
# at ``tests/test_cognito_auth.py`` mint synthetic JWTs signed by a
# locally generated RSA key and patch ``_fetch_jwks`` so no live Cognito
# call is required.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/cognito_auth.py pellier/backend/services/cognito_auth.py

JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour per Req 4.2.1
ACCESS_TOKEN_COOKIE = "access_token"


class CognitoAuthService:
    """Validate Cognito JWTs against a cached JWKS.

    One instance per application is expected. The JWKS cache and its
    refresh lock live on the instance so tests can construct isolated
    services without global state bleed.
    """

    def __init__(
        self,
        pool_id: Optional[str] = None,
        region: Optional[str] = None,
        client_id: Optional[str] = None,
        jwks_ttl_seconds: int = JWKS_CACHE_TTL_SECONDS,
    ) -> None:
        self._pool_id = pool_id if pool_id is not None else settings.cognito_pool_id_resolved
        self._region = region if region is not None else settings.cognito_region_resolved
        self._client_id = client_id if client_id is not None else settings.COGNITO_CLIENT_ID
        self._jwks_ttl = jwks_ttl_seconds

        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0.0
        self._jwks_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # JWKS cache
    # ------------------------------------------------------------------

    @property
    def issuer(self) -> str:
        if not self._pool_id:
            raise RuntimeError("COGNITO_POOL_ID (or COGNITO_USER_POOL_ID) is not configured")
        return f"https://cognito-idp.{self._region}.amazonaws.com/{self._pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"

    def _fetch_jwks(self) -> Dict[str, Any]:
        """Blocking HTTP fetch of the Cognito JWKS document.

        Split out as an overridable method so tests can patch it with a
        synthetic JWKS without monkey-patching ``requests``.
        """
        resp = requests.get(self.jwks_url, timeout=5)
        resp.raise_for_status()
        return resp.json()

    async def get_jwks(self) -> Dict[str, Any]:
        """Return the cached JWKS, fetching once if the TTL has lapsed.

        The lock makes N concurrent ``validate_jwt`` calls during a cold
        cache collapse into a single ``_fetch_jwks`` invocation (Req 4.2.1
        cache-hit property under load).
        """
        now = time.time()
        if self._jwks_cache is not None and (now - self._jwks_cache_time) < self._jwks_ttl:
            return self._jwks_cache

        async with self._jwks_lock:
            # Re-check after acquiring the lock — another coroutine may
            # have populated the cache while we were waiting.
            now = time.time()
            if self._jwks_cache is not None and (now - self._jwks_cache_time) < self._jwks_ttl:
                return self._jwks_cache

            jwks = await asyncio.to_thread(self._fetch_jwks)
            self._jwks_cache = jwks
            self._jwks_cache_time = time.time()
            return jwks

    async def _resolve_signing_key(self, token: str) -> Any:
        """Return the RSA public key that signed ``token``.

        Raises ``jwt.InvalidTokenError`` when the token's ``kid`` is not
        present in the JWKS so unsigned-by-JWKS tokens fail the same way
        a malformed token does.
        """
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise jwt.InvalidTokenError("Token missing 'kid' header")

        jwks = await self.get_jwks()
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                return RSAAlgorithm.from_jwk(jwk)

        raise jwt.InvalidTokenError("Token 'kid' not found in JWKS")

    # ------------------------------------------------------------------
    # JWT validation
    # ------------------------------------------------------------------

    async def validate_jwt(self, token: str) -> VerifiedUser:
        """Validate an access token and return a ``VerifiedUser``.

        Enforces (Req 4.2.2, 2.6.3):
          * RS256 signature via JWKS
          * ``iss`` matches the pool issuer URL
          * ``aud`` matches ``COGNITO_CLIENT_ID`` (access tokens emit
            ``client_id`` rather than ``aud``; both are accepted)
          * ``exp`` not in the past
          * ``token_use == 'access'``
        """
        if not self._client_id:
            raise HTTPException(status_code=503, detail="auth_not_configured")

        try:
            key = await self._resolve_signing_key(token)
            # Cognito access tokens put the app-client id in the ``client_id``
            # claim, not ``aud``. Decode without audience verification first,
            # then assert the client_id manually so id-tokens (which use
            # ``aud``) and access-tokens (which use ``client_id``) both
            # validate through the same code path.
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False, "require": ["exp", "iss"]},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="auth_failed")
        except jwt.InvalidIssuerError:
            raise HTTPException(status_code=401, detail="auth_failed")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="auth_failed")
        except requests.RequestException as exc:
            logger.error("JWKS fetch failed: %s", exc.__class__.__name__)
            raise HTTPException(status_code=503, detail="auth_unavailable")

        if claims.get("token_use") != "access":
            raise HTTPException(status_code=401, detail="auth_failed")

        audience = claims.get("aud") or claims.get("client_id")
        if audience != self._client_id:
            raise HTTPException(status_code=401, detail="auth_failed")

        return VerifiedUser(
            user_id=claims.get("sub", ""),
            email=claims.get("email", ""),
            given_name=claims.get("given_name") or claims.get("username", ""),
            # Preserve the raw bearer token so the request path can pass the
            # caller's identity through to the AgentCore Gateway (JWT
            # passthrough). Excluded from serialization in the model.
            access_token=token,
        )

    # ------------------------------------------------------------------
    # Request extraction
    # ------------------------------------------------------------------

    async def extract_user(self, request: Request) -> Optional[VerifiedUser]:
        """Return the verified user for ``request`` or ``None``.

        Priority per Req 4.2.2:
          1. ``Authorization: Bearer <token>`` header
          2. ``access_token`` cookie
        """
        token: Optional[str] = None

        authorization = request.headers.get("Authorization") or request.headers.get(
            "authorization"
        )
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()

        if not token:
            token = request.cookies.get(ACCESS_TOKEN_COOKIE)

        if not token:
            return None

        try:
            return await self.validate_jwt(token)
        except HTTPException:
            # Callers of extract_user treat absence of a verified user as
            # "anonymous". Only the ``require_user`` dependency below
            # escalates that to a 401.
            return None


# Process-wide service instance. Kept module-level so the JWKS cache is
# shared across the FastAPI app. Tests construct their own instance to
# stay isolated.
_default_service: Optional[CognitoAuthService] = None


def get_cognito_auth_service() -> CognitoAuthService:
    """FastAPI-friendly accessor for the shared ``CognitoAuthService``."""
    global _default_service
    if _default_service is None:
        _default_service = CognitoAuthService()
    return _default_service


async def require_user(
    request: Request,
    service: CognitoAuthService = Depends(get_cognito_auth_service),
) -> VerifiedUser:
    """FastAPI dependency that enforces authentication.

    Populates ``request.state.user`` with the verified user so downstream
    handlers can read it without re-validating. Raises ``401 auth_failed``
    when no valid token is present (Req 4.2.2, "Done when").
    """
    user = await service.extract_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="auth_failed")
    request.state.user = user
    return user
# === CHALLENGE 9.1: Cognito JWT validation — END ===
