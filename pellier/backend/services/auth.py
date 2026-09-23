"""AgentCore Identity — Cognito user extraction, optional and required.

Route dependencies use ``get_current_user()``, which delegates to the
cookie-aware ``CognitoAuthService`` so code-flow httpOnly cookies and
legacy ``Authorization: Bearer`` headers share one validation path.

Two dependencies, and the difference is a security boundary:

  * :func:`get_current_user` is **optional**. It returns ``None`` for an
    anonymous shopper so read paths and the demo storefront work without
    a login. Read paths only.
  * :func:`require_operator` is **required**. Every mutation and operator
    route must depend on it. It rejects anonymous callers, rejects a
    presented-but-invalid token with a *different* status than a missing
    one, and guarantees a non-empty ``sub`` claim so the audit row can
    name a real principal.

Why the split matters: the optional dependency returns ``None`` both when
no credentials were supplied and when supplied credentials failed to
verify. A mutation handler that accepts the optional dependency and does
not reject ``None`` is therefore an unauthenticated write path that reads
as an authenticated one.
"""
import logging
from typing import Optional, Dict, Any

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency: extract and verify the optional Cognito user.

    Returns None for anonymous users (demo mode).
    Returns {sub, username, email, given_name, access_token} for authenticated users.
    """
    try:
        from services.cognito_auth import get_cognito_auth_service

        user = await get_cognito_auth_service().extract_user(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Cognito verification unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="auth_unavailable") from exc

    if user is None:
        return None

    # Include the raw token so chat can pass the caller's identity through to
    # AgentCore Gateway/Runtime. This dict remains server-side.
    payload = {
        "sub": user.user_id,
        "email": user.email or "anonymous",
        "given_name": user.given_name,
        "access_token": user.access_token,
    }
    username = getattr(user, "username", None)
    if username:
        payload["username"] = username
    return payload


# The Cognito group that authorizes the operator desk.
#
# Operator authority is enforced twice, and the two layers read the same fact.
# Here, `require_operator` checks group membership on every desk route. At the
# Gateway, the pre-token trigger stamps `custom:staff_scope` on the access
# token of a group member, and the `initiate_return_staff_scope` permit in
# `scripts/deploy/render_agentcore_project.py` requires that claim, so the
# desk's confirmed return is authorized as a person, with the operator's own
# token, rather than as a service. `issue_credit` is also published, with its
# own staff-scope permit and no shopper permit. Human confirmation is enforced
# by the Operator workflow; a direct staff Gateway call does not prove review.
OPERATOR_GROUP = "pellier-operators"


def authorize_customer_read(user: Optional[Dict[str, Any]], customer_id: str) -> str:
    """Authorize customer content from a verified caller, never a persona picker."""
    from services.turn_identity import customer_id_for_verified_username

    subject = str((user or {}).get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="authentication_required")
    if customer_id_for_verified_username(user.get("username")) != customer_id:
        raise HTTPException(status_code=403, detail="customer_scope_required")
    return subject


async def require_operator(request: Request) -> Dict[str, Any]:
    """FastAPI dependency: require a verified operator identity.

    Use this on every ``/api/operator`` route, read and write alike. Unlike
    :func:`get_current_user`, it never returns ``None`` — the handler is
    guaranteed a principal it can write into the audit record.

    **Authentication is not authorization.** This function used to stop at "the token
    verifies and carries a subject", which made every shopper an operator: `marco` could
    confirm, decline and execute any review, and call ``issue_credit`` directly. The
    module docstring in ``routes/operator.py`` even explained why a shopper-facing agent
    must never issue itself store credit, while this dependency handed the same capability
    to the same shopper through the desk. A workshop whose subject is governance cannot
    ship that.

    Membership in ``OPERATOR_GROUP`` is now required, and the two failure modes are
    deliberately different status codes:

      * **401** ``authentication_required`` / ``invalid_credentials`` — who are you?
      * **403** ``operator_group_required`` — you are known, and not permitted.

    Collapsing 403 into 401 would tell an authenticated shopper to log in again, which is
    both useless and misleading. Neither is a Cedar DENY; that distinction is
    load-bearing in this workshop.

    Args:
        request: The inbound request, carrying either an
            ``Authorization: Bearer`` header or an ``access_token`` cookie.

    Returns:
        ``{sub, username, email, given_name, access_token}`` for the verified caller.
        ``sub`` is guaranteed non-empty.

    Raises:
        HTTPException: ``401 authentication_required`` when no credentials
            were supplied at all; ``401 invalid_credentials`` when a token
            was presented but did not verify; ``403 operator_group_required``
            when the caller verified but is not in ``OPERATOR_GROUP``.
    """
    from services.cognito_auth import get_cognito_auth_service

    service = get_cognito_auth_service()
    if not _has_presented_credentials(request):
        raise HTTPException(status_code=401, detail="authentication_required")

    try:
        user = await service.extract_user(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Operator verification unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="auth_unavailable") from exc

    if user is None:
        # Credentials were presented (checked above) but did not verify.
        raise HTTPException(status_code=401, detail="invalid_credentials")

    subject = (user.user_id or "").strip()
    if not subject:
        # A token that verifies but carries no subject cannot be audited.
        raise HTTPException(status_code=401, detail="invalid_credentials")

    groups = tuple(getattr(user, "groups", ()) or ())
    if OPERATOR_GROUP not in groups:
        # Authenticated and not permitted. Log the username, never the token, so an
        # operator debugging a locked-out desk can see whose membership is missing.
        logger.warning(
            "Operator route refused: %s is not in %s",
            getattr(user, "username", None) or subject,
            OPERATOR_GROUP,
        )
        raise HTTPException(status_code=403, detail="operator_group_required")

    payload = {
        "sub": subject,
        "email": user.email or "anonymous",
        "given_name": user.given_name,
        "access_token": user.access_token,
        "groups": groups,
    }
    username = getattr(user, "username", None)
    if username:
        payload["username"] = username
    return payload


def _has_presented_credentials(request: Request) -> bool:
    """Return True when the caller supplied a bearer token or auth cookie."""
    from services.cognito_auth import ACCESS_TOKEN_COOKIE

    authorization = request.headers.get("Authorization") or request.headers.get(
        "authorization"
    )
    if authorization and authorization.lower().startswith("bearer "):
        return bool(authorization.split(" ", 1)[1].strip())
    return bool(request.cookies.get(ACCESS_TOKEN_COOKIE))
