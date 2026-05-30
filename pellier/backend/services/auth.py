"""
AgentCore Identity — Cognito JWT verification.

verify_cognito_token() decodes and validates JWTs from Amazon Cognito;
get_current_user() is the FastAPI dependency that extracts the bearer
token. In the Builder's Session the app runs in demo auth mode
(AUTH_MODE=demo), so this path is dormant but fully functional.
"""
import logging
import time
from typing import Optional, Dict, Any

import jwt
import requests
from fastapi import Header, HTTPException

from config import settings

logger = logging.getLogger(__name__)

# Cached JWKS (JSON Web Key Set) from Cognito
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_time: float = 0
JWKS_CACHE_TTL = 3600  # 1 hour


def _get_jwks(user_pool_id: str, region: str) -> Dict[str, Any]:
    """Fetch and cache Cognito JWKS for token verification."""
    global _jwks_cache, _jwks_cache_time

    if _jwks_cache and (time.time() - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache

    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        "/.well-known/jwks.json"
    )
    resp = requests.get(jwks_url, timeout=5)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cache_time = time.time()
    return _jwks_cache


def verify_cognito_token(token: str) -> Dict[str, Any]:
    """
    Verify a Cognito JWT and return its claims.

    Steps:
    1. Decode the JWT header to get the key ID (kid)
    2. Fetch the JWKS from Cognito and find the matching public key
    3. Verify the token signature, expiration, and audience
    4. Return the decoded claims (sub, email, etc.)

    Returns:
        dict with keys: sub, email, token_use, etc.
    """
    user_pool_id = settings.cognito_pool_id_resolved or ""
    client_id = settings.COGNITO_CLIENT_ID or ""
    region = settings.cognito_region_resolved

    if not user_pool_id or not client_id:
        raise HTTPException(status_code=503, detail="Cognito not configured")

    try:
        # 1. Decode header to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # 2. Fetch JWKS and find matching key
        jwks = _get_jwks(user_pool_id, region)
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                break

        if not key:
            raise HTTPException(status_code=401, detail="Token key not found in JWKS")

        # 3. Verify and decode
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=client_id,
            options={"verify_exp": True},
        )

        return claims

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except requests.RequestException as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise HTTPException(status_code=503, detail="Cannot verify token")


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency: extract and verify the Bearer token.

    Returns None for anonymous users (demo mode).
    Returns {sub, email} for authenticated users.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None  # Anonymous — demo mode default

    token = authorization.split(" ", 1)[1]
    claims = verify_cognito_token(token)
    # Include the raw bearer token so the chat path can pass the caller's
    # identity through to the AgentCore Gateway (JWT passthrough). This dict
    # stays server-side; it is never returned to the client as-is.
    return {
        "sub": claims.get("sub"),
        "email": claims.get("email", "anonymous"),
        "access_token": token,
    }
