"""
AgentCore Identity — Cognito JWT verification for Lab 4a.

Wire It Live: Participants implement verify_cognito_token() to decode and
validate JWTs from Amazon Cognito, then wire get_current_user() as a
FastAPI dependency.
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


# === WIRE IT LIVE (Lab 4a) ===
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
# === END WIRE IT LIVE ===


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency: extract and verify the Bearer token.

    Returns None for anonymous users (Labs 1-3).
    Returns {sub, email} for authenticated users (Lab 4).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None  # Anonymous — backward-compatible with Labs 1-3

    token = authorization.split(" ", 1)[1]
    claims = verify_cognito_token(token)
    return {"sub": claims.get("sub"), "email": claims.get("email", "anonymous")}
