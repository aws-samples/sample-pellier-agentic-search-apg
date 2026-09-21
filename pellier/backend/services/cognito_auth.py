"""
CognitoAuthService — JWT validation middleware for the storefront backend.

Cognito JWT validation (Requirements 4.2.1–4.2.4, 5.3.1–5.3.3). Verifies Amazon
Cognito access tokens against the pool's JWKS endpoint and exposes a
FastAPI dependency ``require_user`` that populates ``request.state.user``
with a ``VerifiedUser``.

This is the backend half of the governed auth and identity path:

    services/cognito_auth.py          ← this file
    services/agentcore_identity.py
    frontend/src/utils/auth.ts
    frontend/src/components/{AuthModal,PreferencesModal}.tsx

Key design choices (Req 4.2):

  * JWKS is fetched once per ``CognitoAuthService`` instance and cached
    for 1 hour. A single ``asyncio.Lock`` guards the refresh so N
    concurrent validations trigger exactly one HTTP fetch (Req 4.2.1).
  * The validator enforces signature (RS256), ``iss``, ``client_id``, ``sub``,
    ``exp``, and ``token_use == "access"`` per Req 4.2.2 and 2.6.3.
  * An unknown ``kid`` forces one guarded JWKS refresh so Cognito signing-key
    rotation does not reject valid users for the cache TTL.
  * ``extract_user`` checks the ``Authorization: Bearer`` header first
    and only falls back to the ``access_token`` cookie (spec priority).
  * Tokens never appear in logs (Req 5.3.3). The service logs validation
    failures with the exception class only.

The workshop ``solutions/the-ledger/services/cognito_auth.py`` file mirrors
the reference block here byte-for-byte (enforced by solution parity tests).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import unquote

import jwt
import requests
from fastapi import Depends, HTTPException, Request
from jwt.algorithms import RSAAlgorithm

from config import settings
from models import VerifiedUser

logger = logging.getLogger(__name__)


# === REFERENCE: Cognito JWT validation — START ===
# Requirements 4.2.1–4.2.4, 5.3.1–5.3.3 and Design "services/cognito_auth.py".
#
# Reference implementation for ``CognitoAuthService`` + ``require_user``.
# Tests at ``tests/test_cognito_auth.py`` mint synthetic JWTs signed by a
# locally generated RSA key and patch ``_fetch_jwks`` so no live Cognito
# call is required.
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/cognito_auth.py pellier/backend/services/cognito_auth.py

JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour per Req 4.2.1
# Cognito and the verifier can straddle a clock tick. Keep the allowance small
# and fixed; signature, issuer, client and token-use validation remain required.
JWT_CLOCK_SKEW_SECONDS = 5
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

        # Cognito rotates signing keys. If the cache predates the rotation,
        # refresh exactly once under the same lock used by the normal cache
        # path. The identity check prevents concurrent misses from stampeding
        # the JWKS endpoint after the first caller has refreshed it.
        async with self._jwks_lock:
            if self._jwks_cache is jwks:
                refreshed = await asyncio.to_thread(self._fetch_jwks)
                self._jwks_cache = refreshed
                self._jwks_cache_time = time.time()
            else:
                refreshed = self._jwks_cache or {}

        for jwk in refreshed.get("keys", []):
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
          * ``client_id`` matches ``COGNITO_CLIENT_ID``
          * non-empty ``sub`` identifies the authenticated principal
          * ``iat``, ``nbf`` and ``exp`` within the fixed five-second clock allowance
          * ``token_use == 'access'``
        """
        if not self._client_id:
            raise HTTPException(status_code=503, detail="auth_not_configured")

        try:
            key = await self._resolve_signing_key(token)
            # Cognito access tokens put the app-client id in ``client_id``.
            # ID tokens use ``aud`` and are rejected by the token_use check;
            # accepting ``aud`` here would blur those two token contracts.
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.issuer,
                leeway=JWT_CLOCK_SKEW_SECONDS,
                options={
                    "verify_aud": False,
                    "require": ["exp", "iss", "sub", "client_id", "token_use"],
                },
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

        if claims.get("client_id") != self._client_id:
            raise HTTPException(status_code=401, detail="auth_failed")

        subject = str(claims.get("sub") or "").strip()
        if not subject:
            raise HTTPException(status_code=401, detail="auth_failed")

        # `cognito:groups` is a JSON array in an access token, but a single-group pool
        # can serialize it as a bare string. Normalize both, casefolded, so an
        # authorization check never depends on which shape Cognito produced.
        raw_groups = claims.get("cognito:groups") or []
        if isinstance(raw_groups, str):
            raw_groups = [raw_groups]
        groups = tuple(
            str(group).strip().casefold() for group in raw_groups if str(group).strip()
        )

        return VerifiedUser(
            user_id=subject,
            email=claims.get("email", ""),
            given_name=claims.get("given_name") or claims.get("username", ""),
            username=str(claims.get("username") or "").strip().casefold(),
            groups=groups,
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
            cookie_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
            token = unquote(cookie_token) if cookie_token else None

        if not token:
            return None

        try:
            return await self.validate_jwt(token)
        except HTTPException as exc:
            if exc.status_code == 401:
                return None
            # An unavailable verifier has not rejected the credentials. Keep
            # that failure distinct so callers fail closed without signing
            # the person out or replacing their session with an anonymous one.
            raise


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
# === REFERENCE: Cognito JWT validation — END ===
