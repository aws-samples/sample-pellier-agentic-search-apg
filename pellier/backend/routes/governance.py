"""Caller-scoped identity and control-plane observations. No mutation endpoints."""
from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
import jwt

from services.auth import OPERATOR_GROUP, _has_presented_credentials
from services.cognito_auth import CognitoAuthService, get_cognito_auth_service
from services.governance_snapshot import observed_at, policy_snapshot

router = APIRouter(prefix="/api/observatory/governance", tags=["governance"])
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/identity")
async def identity(
    request: Request,
    response: Response,
    service: CognitoAuthService = Depends(get_cognito_auth_service),
):
    """Only display claims from the caller's already validated access token."""
    response.headers.update(NO_STORE)
    if not _has_presented_credentials(request):
        return {"state": "anonymous", "observedAt": observed_at(), "caller": None}
    try:
        user = await service.extract_user(request)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail="identity_unavailable" if exc.status_code >= 500 else "invalid_credentials",
            headers=NO_STORE,
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="identity_unavailable", headers=NO_STORE) from exc
    if user is None:
        raise HTTPException(status_code=401, detail="invalid_credentials", headers=NO_STORE)

    # extract_user above verifies the exact token's signature, issuer, expiry,
    # client_id and token_use. Decode only to project additional signed claims;
    # this decode is never an alternate authentication path.
    claims = jwt.decode(user.access_token, options={"verify_signature": False})
    return {
        "state": "verified",
        "observedAt": observed_at(),
        "caller": {
            "username": user.username or user.given_name or "Authenticated caller",
            "subjectFingerprint": hashlib.sha256(user.user_id.encode()).hexdigest()[:12],
            "tokenFingerprint": hashlib.sha256(user.access_token.encode()).hexdigest()[:12],
            "tokenUse": claims["token_use"],
            "expiresAt": claims["exp"],
            "issuer": claims["iss"],
            "clientId": claims["client_id"],
            "customerClaim": claims.get("custom:customer_id") or None,
            "staffScope": claims.get("custom:staff_scope") or None,
            "operatorGroup": OPERATOR_GROUP in user.groups,
        },
    }


@router.get("/policies")
async def policies(response: Response):
    response.headers.update(NO_STORE)
    try:
        return await asyncio.wait_for(asyncio.to_thread(policy_snapshot), timeout=18)
    except Exception as exc:
        # No raw AWS error, credentials, or partial success disguised as an empty list.
        raise HTTPException(status_code=503, detail="policy_snapshot_unavailable", headers=NO_STORE) from exc
