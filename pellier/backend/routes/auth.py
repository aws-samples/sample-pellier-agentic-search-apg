"""``/api/auth/*`` routes — Cognito Hosted UI sign-in loop (Task 3.3).

Implements Requirements 3.1.1–3.1.5 and 4.1.3:

  * ``GET  /api/auth/signin``   redirect to Cognito ``/oauth2/authorize``
  * ``GET  /api/auth/callback`` exchange the authorization code, set
                                session cookies, redirect to the SPA
  * ``GET  /api/auth/me``       return the verified ``{user_id, email,
                                given_name}`` triple for the logged-in
                                shopper
  * ``POST /api/auth/logout``   clear the session cookies and revoke the
                                refresh token at Cognito
  * ``POST /api/auth/refresh``  rotate tokens from the ``refresh_token``
                                cookie (used by the frontend interceptor
                                in Task 3.7 on the frontend).

Design notes
------------

* **State signing.** ``state`` is a URL-safe HMAC token built from a
  random nonce + an expiry. The signing key is derived from
  ``COGNITO_CLIENT_SECRET`` so no extra dependency (``itsdangerous``) is
  needed and the state survives a restart-less round trip. If the
  secret is not configured the signer falls back to a stable
  per-process key so local dev still works. Replay protection is the
  5-minute expiry — single-use tracking is left to the TTL.
* **Cookies.** Session cookies follow Req 5.3.1: ``httpOnly`` +
  ``Secure`` + ``SameSite=Lax`` + ``Path=/``. The ``just_signed_in``
  flag is explicitly ``httpOnly=False`` so the SPA can read and delete
  it on first mount (Design decision #2); it carries no authentication
  value, only the "callback just happened" signal that drives the
  preferences modal.
* **Token validation.** Access tokens coming back from
  ``/oauth2/token`` are validated via the existing
  ``CognitoAuthService`` JWKS client so the issuer/audience/``token_use``
  rules apply here exactly as they do for every other protected
  endpoint.
* **Error envelopes.** Per Req 3.1.5, Cognito errors return a
  non-leaking envelope ``{"error": "auth_failed"}`` (or
  ``"invalid_state"`` / ``"refresh_failed"``) with an appropriate
  status. Token fragments are never logged (Req 5.3.3).

Routes are NOT part of any workshop challenge block. This file ships
without ``# === CHALLENGE ... ===`` markers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from config import settings
from services.cognito_auth import (
    ACCESS_TOKEN_COOKIE,
    CognitoAuthService,
    get_cognito_auth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Cookie names + lifetimes
# ---------------------------------------------------------------------------

ID_TOKEN_COOKIE = "id_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
JUST_SIGNED_IN_COOKIE = "just_signed_in"

# Refresh tokens are long-lived (30 days by default in Cognito). Access/id
# tokens expire in an hour; we let the browser hold them for their full
# lifetime and rely on the silent-refresh path for rotation.
ACCESS_COOKIE_MAX_AGE = 60 * 60          # 1 hour
ID_COOKIE_MAX_AGE = 60 * 60              # 1 hour
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
JUST_SIGNED_IN_MAX_AGE = 60              # 60s single-use flag

# State token lifetime (Req 5.3.4 guards the mismatch path, not TTL).
STATE_TTL_SECONDS = 5 * 60               # 5 minutes

# Provider values mapped through to the Cognito ``identity_provider`` query
# string parameter. ``email`` is omitted entirely so the Hosted UI falls
# through to native email/password. Kept lowercase on the way in (matches
# the frontend ``redirectToSignIn`` helper) and mapped to the exact
# strings Cognito expects on the way out.
PROVIDER_MAP: Dict[str, Optional[str]] = {
    "google": "Google",
    "apple": "SignInWithApple",
    "email": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redirect_uri() -> str:
    """Return the configured OAuth callback URI.

    Uses ``OAUTH_REDIRECT_URI`` when set; falls back to
    ``APP_BASE_URL + /api/auth/callback`` so local dev with only
    ``APP_BASE_URL`` configured still works. Raises 503 if neither is
    present — the sign-in flow cannot function without a registered
    redirect.
    """
    if settings.OAUTH_REDIRECT_URI:
        return settings.OAUTH_REDIRECT_URI
    if settings.APP_BASE_URL:
        return f"{settings.APP_BASE_URL.rstrip('/')}/api/auth/callback"
    raise HTTPException(status_code=503, detail="auth_not_configured")


def _post_signin_redirect() -> str:
    """Return the SPA URL to redirect to after a successful sign-in."""
    return settings.APP_BASE_URL.rstrip("/") + "/" if settings.APP_BASE_URL else "/"


def _cognito_domain() -> str:
    if not settings.COGNITO_DOMAIN:
        raise HTTPException(status_code=503, detail="auth_not_configured")
    return settings.COGNITO_DOMAIN.rstrip("/")


def _client_id() -> str:
    if not settings.COGNITO_CLIENT_ID:
        raise HTTPException(status_code=503, detail="auth_not_configured")
    return settings.COGNITO_CLIENT_ID


def _authorize_url() -> str:
    return f"https://{_cognito_domain()}/oauth2/authorize"


def _token_url() -> str:
    return f"https://{_cognito_domain()}/oauth2/token"


def _revoke_url() -> str:
    return f"https://{_cognito_domain()}/oauth2/revoke"


# ---- State signing ---------------------------------------------------------

# Fallback signing key used only when COGNITO_CLIENT_SECRET is unset (local
# dev against a public app client). Kept module-local so the key is stable
# for the life of the process but rotates across restarts.
_FALLBACK_SIGNING_KEY = secrets.token_bytes(32)


def _state_signing_key() -> bytes:
    secret = settings.COGNITO_CLIENT_SECRET
    if secret:
        return hashlib.sha256(secret.encode("utf-8")).digest()
    return _FALLBACK_SIGNING_KEY


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _build_state(expiry: Optional[int] = None) -> str:
    """Return a signed opaque ``state`` token.

    Format: ``<b64url(nonce)>.<expiry>.<b64url(hmac)>``. The expiry is a
    unix timestamp; the HMAC is computed over ``nonce + "." + expiry``
    so swapping either field invalidates the signature.
    """
    nonce = secrets.token_bytes(16)
    expiry_ts = expiry if expiry is not None else int(time.time()) + STATE_TTL_SECONDS
    payload = f"{_b64url_encode(nonce)}.{expiry_ts}"
    signature = hmac.new(
        _state_signing_key(), payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload}.{_b64url_encode(signature)}"


def _verify_state(state: str) -> bool:
    """Return True iff ``state`` is a well-formed, unexpired, signed token.

    Uses ``hmac.compare_digest`` to blunt timing attacks. Expiry is
    checked after signature verification so a malformed state never
    leaks information about the signing key.
    """
    try:
        nonce_b64, expiry_str, signature_b64 = state.split(".")
    except ValueError:
        return False

    payload = f"{nonce_b64}.{expiry_str}"
    expected = hmac.new(
        _state_signing_key(), payload.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        provided = _b64url_decode(signature_b64)
    except Exception:
        return False

    if not hmac.compare_digest(expected, provided):
        return False

    try:
        expiry_ts = int(expiry_str)
    except ValueError:
        return False
    if expiry_ts < int(time.time()):
        return False

    return True


# ---- Cookie helpers --------------------------------------------------------


def _set_session_cookies(
    response: Response,
    *,
    access_token: str,
    id_token: Optional[str],
    refresh_token: Optional[str],
) -> None:
    """Write the three session cookies per Req 3.1.2 / 5.3.1.

    ``id_token`` and ``refresh_token`` are optional because the refresh
    flow may not re-issue a refresh token and Cognito occasionally omits
    the id-token when the client requests ``scope=openid`` without the
    ``profile`` + ``email`` combination (we do request both; the guard
    exists for robustness).
    """
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        max_age=ACCESS_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    if id_token:
        response.set_cookie(
            key=ID_TOKEN_COOKIE,
            value=id_token,
            max_age=ID_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    if refresh_token:
        response.set_cookie(
            key=REFRESH_TOKEN_COOKIE,
            value=refresh_token,
            max_age=REFRESH_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )


def _set_just_signed_in_cookie(response: Response) -> None:
    """Write the single-use ``just_signed_in`` flag (Design decision #2).

    Explicitly NOT httpOnly so the SPA can read and delete it on first
    mount. Secure + SameSite=Lax to block cross-origin leakage. No
    session data or token fragment is stored in the value.
    """
    response.set_cookie(
        key=JUST_SIGNED_IN_COOKIE,
        value="1",
        max_age=JUST_SIGNED_IN_MAX_AGE,
        httponly=False,
        secure=True,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    for cookie in (
        ACCESS_TOKEN_COOKIE,
        ID_TOKEN_COOKIE,
        REFRESH_TOKEN_COOKIE,
        JUST_SIGNED_IN_COOKIE,
    ):
        response.delete_cookie(cookie, path="/")


# ---- Cognito token exchange -----------------------------------------------


def _basic_auth_header() -> Optional[Dict[str, str]]:
    """Return an HTTP Basic header if the client has a secret configured.

    Public Cognito clients omit the secret — in that case the request
    is sent unauthenticated and ``client_id`` is included in the form
    body instead.
    """
    client_id = _client_id()
    client_secret = settings.COGNITO_CLIENT_SECRET
    if not client_secret:
        return None
    creds = f"{client_id}:{client_secret}".encode("utf-8")
    return {
        "Authorization": "Basic " + base64.b64encode(creds).decode("ascii"),
    }


def _token_exchange(body: Dict[str, str]) -> Dict[str, Any]:
    """POST to Cognito's ``/oauth2/token`` endpoint and return JSON.

    Raises an HTTP 502 on any non-2xx response without echoing the
    Cognito error body back to the caller (Req 3.1.5, 5.3.3).
    """
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    basic = _basic_auth_header()
    if basic:
        headers.update(basic)

    try:
        resp = requests.post(_token_url(), data=body, headers=headers, timeout=10)
    except requests.RequestException as exc:
        logger.error("Cognito token endpoint unreachable: %s", exc.__class__.__name__)
        raise HTTPException(status_code=502, detail="auth_failed")

    if resp.status_code >= 400:
        logger.error(
            "Cognito token exchange failed: status=%s", resp.status_code
        )
        raise HTTPException(status_code=502, detail="auth_failed")

    try:
        return resp.json()
    except ValueError:
        logger.error("Cognito token response was not JSON")
        raise HTTPException(status_code=502, detail="auth_failed")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/signin")
async def signin(
    provider: str = Query("email", pattern="^(google|apple|email)$"),
) -> RedirectResponse:
    """Redirect the browser to Cognito's Hosted UI (Req 3.1.1).

    Maps the ``provider`` query param to Cognito's ``identity_provider``
    value and generates a signed ``state`` round-tripped through Cognito
    back to the callback handler. The state carries no session data;
    its only job is CSRF protection and replay window enforcement.
    """
    provider_key = provider.lower()
    identity_provider = PROVIDER_MAP.get(provider_key)

    state = _build_state()
    params: Dict[str, str] = {
        "client_id": _client_id(),
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": _redirect_uri(),
        "state": state,
    }
    if identity_provider:
        params["identity_provider"] = identity_provider

    url = f"{_authorize_url()}?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    service: CognitoAuthService = Depends(get_cognito_auth_service),
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> Response:
    """Handle the Cognito Hosted UI redirect (Req 3.1.2, 5.3.4).

    Validates ``state``, exchanges ``code`` for tokens at
    ``/oauth2/token``, verifies the returned access token through the
    JWKS client, writes the four cookies, and 302s back to the SPA.
    """
    # Cognito surfaces IdP errors as ``?error=...&error_description=...``.
    # We treat them the same as any other sign-in interruption per Req 3.1.5.
    if error:
        logger.info("Cognito returned OAuth error: %s", error)
        return JSONResponse(
            status_code=400,
            content={"error": "auth_failed"},
        )

    if not code or not state:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_state"},
        )

    # Req 5.3.4: state mismatch or tamper → 400 invalid_state.
    if not _verify_state(state):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_state"},
        )

    # Exchange the authorization code for tokens.
    token_response = _token_exchange(
        {
            "grant_type": "authorization_code",
            "client_id": _client_id(),
            "code": code,
            "redirect_uri": _redirect_uri(),
        }
    )

    access_token = token_response.get("access_token")
    id_token = token_response.get("id_token")
    refresh_token = token_response.get("refresh_token")

    if not access_token:
        logger.error("Cognito token response missing access_token")
        raise HTTPException(status_code=502, detail="auth_failed")

    # Verify the access token against JWKS before trusting it. Any failure
    # here bubbles up as 401 from ``validate_jwt``; surface it as 502
    # auth_failed to avoid leaking JWKS internals to the caller.
    try:
        await service.validate_jwt(access_token)
    except HTTPException as exc:
        logger.error("Token validation after exchange failed: %s", exc.detail)
        raise HTTPException(status_code=502, detail="auth_failed")

    response = RedirectResponse(url=_post_signin_redirect(), status_code=302)
    _set_session_cookies(
        response,
        access_token=access_token,
        id_token=id_token,
        refresh_token=refresh_token,
    )
    _set_just_signed_in_cookie(response)
    return response


@router.get("/me")
async def me(
    request: Request,
    service: CognitoAuthService = Depends(get_cognito_auth_service),
) -> JSONResponse:
    """Return the verified shopper's profile (Req 3.1.3).

    Uses the shared ``CognitoAuthService.extract_user`` so both the
    ``Authorization: Bearer`` header and the ``access_token`` cookie
    paths work with identical semantics. Returns 401 ``auth_failed``
    when no valid token is present.
    """
    user = await service.extract_user(request)
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"error": "auth_failed"},
        )
    return JSONResponse(
        status_code=200,
        content={
            "user_id": user.user_id,
            "email": user.email,
            "given_name": user.given_name,
        },
    )


@router.post("/logout")
async def logout(request: Request) -> Response:
    """Clear the session cookies and revoke the refresh token (Req 3.1.4)."""
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)

    # Best-effort revoke. Network failures here must not block the user
    # from clearing their local session — cookies are cleared unconditionally.
    if refresh_token and settings.COGNITO_DOMAIN and settings.COGNITO_CLIENT_ID:
        try:
            body = {
                "token": refresh_token,
                "client_id": _client_id(),
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            basic = _basic_auth_header()
            if basic:
                headers.update(basic)
            requests.post(_revoke_url(), data=body, headers=headers, timeout=5)
        except requests.RequestException as exc:
            logger.warning(
                "Cognito revoke call failed: %s", exc.__class__.__name__
            )

    response = JSONResponse(status_code=200, content={"ok": True})
    _clear_session_cookies(response)
    return response


@router.post("/refresh")
async def refresh(
    request: Request,
    service: CognitoAuthService = Depends(get_cognito_auth_service),
) -> Response:
    """Rotate tokens using the ``refresh_token`` cookie (Req 4.2.4).

    Used by the frontend interceptor (Task 3.7 on the frontend) on any
    401 from a protected endpoint. Returns ``{"ok": true}`` and rewrites
    the access/id-token cookies on success; returns 401
    ``refresh_failed`` when the cookie is missing or the token has
    been revoked so the SPA can route the user back to ``/signin``.
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token:
        return JSONResponse(
            status_code=401,
            content={"error": "refresh_failed"},
        )

    try:
        token_response = _token_exchange(
            {
                "grant_type": "refresh_token",
                "client_id": _client_id(),
                "refresh_token": refresh_token,
            }
        )
    except HTTPException:
        # Cognito refused the refresh token (revoked, expired, or the app
        # client was rotated). Clear cookies so the SPA stops retrying.
        response = JSONResponse(
            status_code=401,
            content={"error": "refresh_failed"},
        )
        _clear_session_cookies(response)
        return response

    access_token = token_response.get("access_token")
    id_token = token_response.get("id_token")
    # Cognito rotates the refresh token only when "Refresh token rotation"
    # is enabled on the app client. When absent, keep the existing one.
    new_refresh_token = token_response.get("refresh_token") or refresh_token

    if not access_token:
        return JSONResponse(
            status_code=401,
            content={"error": "refresh_failed"},
        )

    try:
        await service.validate_jwt(access_token)
    except HTTPException:
        response = JSONResponse(
            status_code=401,
            content={"error": "refresh_failed"},
        )
        _clear_session_cookies(response)
        return response

    response = JSONResponse(status_code=200, content={"ok": True})
    _set_session_cookies(
        response,
        access_token=access_token,
        id_token=id_token,
        refresh_token=new_refresh_token,
    )
    return response
