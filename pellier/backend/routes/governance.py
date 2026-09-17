"""Caller-scoped identity and control-plane observations. No mutation endpoints."""
from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
import jwt

from services.auth import OPERATOR_GROUP, _has_presented_credentials, require_operator
from services.cognito_auth import CognitoAuthService, get_cognito_auth_service
from services.governance_snapshot import observed_at, policy_snapshot

router = APIRouter(prefix="/api/observatory/governance", tags=["governance"])
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/outcomes")
async def outcomes(response: Response, _operator=Depends(require_operator)):
    """Read bounded CLI observations; never run a proof from a page request."""
    from routes.observatory import _live_db
    from services.governance_boundaries import summarize

    response.headers.update(NO_STORE)
    try:
        db = await _live_db()
        rows = await db.fetch_all("""
            WITH recent_runs AS (
                SELECT proof_run_id FROM pellier.governance_boundary_observations
                GROUP BY proof_run_id ORDER BY max(observation_id) DESC LIMIT 5
            )
            SELECT observation_id AS "observationId", proof_run_id AS "proofRunId",
                   case_name AS "caseName", invocation_id AS "invocationId",
                   operation_key AS "operationKey", tool, verified_username AS "verifiedUsername",
                   observation, created_at AS "createdAt"
              FROM pellier.governance_boundary_observations
             WHERE proof_run_id IN (SELECT proof_run_id FROM recent_runs)
             ORDER BY observation_id DESC
        """)
        return summarize([dict(row) for row in rows])
    except Exception as exc:
        raise HTTPException(status_code=503, detail="boundary_evidence_unavailable", headers=NO_STORE) from exc


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
