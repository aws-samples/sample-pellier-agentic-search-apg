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

Two sessions in one browser
---------------------------

A browser holds a shopper session and a staff session at the same time:
Jessica on the storefront and Nadia on the Operator, which Lab 4 needs. Each
session has its own httpOnly cookie set, named by
:func:`session_cookie_names`. :func:`get_current_user` reads only the
shopper's set and :func:`require_operator` only the staff set; neither falls
back to the other, so signing a shopper in never replaces the staff member,
and the reverse. A bearer ``Authorization`` header still wins over either
cookie, exactly as before, for curl, Gateway and Runtime callers.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

from fastapi import HTTPException, Request

from models import VerifiedUser
from services.cognito_auth import ACCESS_TOKEN_COOKIE, CognitoAuthService

logger = logging.getLogger(__name__)

SHOPPER_SURFACE = "shopper"
STAFF_SURFACE = "staff"
SESSION_SURFACES = (SHOPPER_SURFACE, STAFF_SURFACE)
SessionSurface = Literal["shopper", "staff"]


@dataclass(frozen=True)
class SessionCookieNames:
    """The httpOnly cookies that hold one surface's session.

    ``sign_in_method`` records how the session began (``workshop`` for the
    one-click shopper sign-in) and lives as long as the refresh token does.
    """

    access: str
    id: str
    refresh: str
    sign_in_method: str


_SESSION_COOKIES: Dict[str, SessionCookieNames] = {
    SHOPPER_SURFACE: SessionCookieNames(
        access=ACCESS_TOKEN_COOKIE,
        id="id_token",
        refresh="refresh_token",
        sign_in_method="signin_method",
    ),
    STAFF_SURFACE: SessionCookieNames(
        access="staff_access_token",
        id="staff_id_token",
        refresh="staff_refresh_token",
        sign_in_method="staff_signin_method",
    ),
}


def session_cookie_names(surface: str) -> SessionCookieNames:
    """Return the cookie names of the ``shopper`` or the ``staff`` session.

    Raises:
        ValueError: For any other surface, so a typo can never read or write a
            third cookie set.
    """
    names = _SESSION_COOKIES.get(surface)
    if names is None:
        raise ValueError(f"Unknown session surface {surface!r}: use 'shopper' or 'staff'.")
    return names


def staff_on_shopper_surface(user: Any, surface: str) -> bool:
    """True when a staff token would stand in the storefront's shopper session.

    Staff are not shoppers. The one-click sign-in refuses them, the password
    and Hosted UI sign-ins refuse to write a staff token into the shopper set,
    and a staff token found there anyway (a cookie from before the sets were
    split) reads as signed out on the storefront.
    """
    groups = tuple(getattr(user, "groups", ()) or ())
    return surface == SHOPPER_SURFACE and OPERATOR_GROUP in groups


async def session_user(
    service: CognitoAuthService, request: Request, surface: str
) -> Optional[VerifiedUser]:
    """Return the verified user of one surface's session, or ``None``.

    A bearer header wins, as before. Otherwise only ``surface``'s access cookie
    is read, never the other session's.

    Raises:
        HTTPException: ``503`` when the verifier is unavailable; an outage has
            not rejected the credentials.
    """
    user = await service.extract_user(
        request, cookie_name=session_cookie_names(surface).access
    )
    if user is not None and not _bearer_token(request) and staff_on_shopper_surface(user, surface):
        logger.info("A staff token in the shopper session reads as signed out")
        return None
    return user


async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency: extract and verify the optional shopper.

    Reads a bearer header or the shopper session, never the staff session.
    Returns None for anonymous users (demo mode).
    Returns {sub, username, email, given_name, access_token} for authenticated users.
    """
    try:
        from services.cognito_auth import get_cognito_auth_service

        user = await session_user(get_cognito_auth_service(), request, SHOPPER_SURFACE)
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
# token of a group member, and the `give_store_credit_staff_scope` permit in
# `scripts/deploy/render_agentcore_project.py` requires that claim, so the
# desk's confirmed credit is authorized as a person, with the operator's own
# token, rather than as a service. No shopper permit names `give_store_credit`.
# Human confirmation is enforced by the Operator workflow; a direct staff
# Gateway call does not prove review.
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
    confirm, decline and execute any review, and call ``give_store_credit`` directly. The
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

    It reads a bearer header or the staff session's ``staff_access_token``
    cookie, never the shopper's, so a shopper signed in on the storefront in
    the same browser is not a caller here.

    Args:
        request: The inbound request, carrying either an
            ``Authorization: Bearer`` header or the staff session cookie.

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
    if not _has_presented_credentials(request, STAFF_SURFACE):
        raise HTTPException(status_code=401, detail="authentication_required")

    try:
        user = await session_user(service, request, STAFF_SURFACE)
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


def _bearer_token(request: Request) -> Optional[str]:
    """The presented bearer token: ``None`` without a bearer header, else its value."""
    authorization = request.headers.get("Authorization") or request.headers.get(
        "authorization"
    )
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _has_presented_credentials(request: Request, surface: str) -> bool:
    """Return True when the caller supplied a bearer token or ``surface``'s cookie."""
    bearer = _bearer_token(request)
    if bearer is not None:
        return bool(bearer)
    return bool(request.cookies.get(session_cookie_names(surface).access))
