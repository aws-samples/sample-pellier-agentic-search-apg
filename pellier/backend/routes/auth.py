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

* **State + PKCE.** ``state`` is a URL-safe HMAC token built from a random
  nonce + an expiry and is also stored in an httpOnly browser cookie. The
  callback requires both copies to match, consumes the cookie, and supplies
  the browser-bound PKCE verifier during the code exchange.
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

Routes are not participant-edit surfaces. They ship as reference runtime code.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

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
OAUTH_STATE_COOKIE = "oauth_state"
PKCE_VERIFIER_COOKIE = "oauth_pkce"
OAUTH_RETURN_TO_COOKIE = "oauth_return_to"

# Refresh tokens are long-lived (30 days by default in Cognito). Access/id
# tokens expire in an hour; we let the browser hold them for their full
# lifetime and rely on the silent-refresh path for rotation.
ACCESS_COOKIE_MAX_AGE = 60 * 60          # 1 hour
ID_COOKIE_MAX_AGE = 60 * 60              # 1 hour
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
JUST_SIGNED_IN_MAX_AGE = 60              # 60s single-use flag

# State token lifetime (Req 5.3.4 guards the mismatch path, not TTL).
STATE_TTL_SECONDS = 5 * 60               # 5 minutes
OAUTH_COOKIE_MAX_AGE = STATE_TTL_SECONDS

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

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_origin(request: Request) -> str:
    """Return the validated public origin forwarded by CloudFront/nginx."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = scheme.split(",", 1)[0].strip().lower()
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    host = host.split(",", 1)[0].strip()
    if scheme not in {"http", "https"} or not re.fullmatch(
        r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", host
    ):
        raise HTTPException(status_code=400, detail="invalid_forwarded_origin")
    return f"{scheme}://{host}"


def _redirect_uri(request: Request) -> str:
    """Return the configured OAuth callback URI.

    Uses ``OAUTH_REDIRECT_URI`` when set; falls back to
    the configured base URL or the origin supplied by nginx. Include the
    deployed application prefix because nginx removes it before forwarding.
    CloudFormation registers this same path after CloudFront is created.
    """
    if settings.OAUTH_REDIRECT_URI:
        return settings.OAUTH_REDIRECT_URI
    origin = settings.APP_BASE_URL.rstrip("/") if settings.APP_BASE_URL else _request_origin(request)
    prefix = "/" + settings.APP_BASE_PATH.strip("/") if settings.APP_BASE_PATH else ""
    return f"{origin}{prefix}/api/auth/callback"


def _safe_return_to(value: Optional[str]) -> Optional[str]:
    """Accept only an origin-relative SPA path.

    The browser supplies this value before leaving for Cognito. It must never
    become an open redirect, even if a caller forges the flow cookie.
    """
    if not value or "\\" in value or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        return None
    return urlunsplit(("", "", parsed.path, parsed.query, ""))


def _post_signin_redirect(
    request: Request, return_to: Optional[str] = None
) -> str:
    """Return the SPA URL to redirect to after a successful sign-in."""
    origin = (
        settings.APP_BASE_URL.rstrip("/")
        if settings.APP_BASE_URL
        else _request_origin(request)
    )
    safe_return_to = _safe_return_to(return_to)
    if safe_return_to:
        return f"{origin}{safe_return_to}"
    path = "/" + settings.APP_BASE_PATH.strip("/") if settings.APP_BASE_PATH else ""
    return f"{origin}{path}/"


def _canonical_loopback_signin_url(
    request: Request,
    *,
    provider: str,
    return_to: Optional[str],
) -> Optional[str]:
    """Converge local host aliases before creating browser-bound OAuth state.

    Cognito exact-matches the configured callback URI. If a participant opens
    the Vite app at ``127.0.0.1`` while ``APP_BASE_URL`` is ``localhost``,
    starting OAuth immediately would bind the state/PKCE cookies to
    ``127.0.0.1`` and send the callback to ``localhost``. The callback could
    never read those cookies. Redirect the browser to the configured loopback
    origin first so the entire transaction stays on one cookie host.
    """
    configured_base = settings.APP_BASE_URL
    if not configured_base and settings.OAUTH_REDIRECT_URI:
        callback = urlsplit(settings.OAUTH_REDIRECT_URI)
        configured_base = urlunsplit(
            (callback.scheme, callback.netloc, "", "", "")
        )
    if not configured_base:
        return None

    request_origin = urlsplit(_request_origin(request))
    configured_origin = urlsplit(configured_base)
    if (
        request_origin.hostname not in _LOOPBACK_HOSTS
        or configured_origin.hostname not in _LOOPBACK_HOSTS
        or request_origin.netloc == configured_origin.netloc
    ):
        return None

    params = {"provider": provider}
    safe_return_to = _safe_return_to(return_to)
    if safe_return_to:
        params["returnTo"] = safe_return_to
    canonical_base = urlunsplit(
        (
            configured_origin.scheme,
            configured_origin.netloc,
            configured_origin.path.rstrip("/"),
            "",
            "",
        )
    )
    return f"{canonical_base}/api/auth/signin?{urlencode(params)}"


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


def _build_pkce_verifier() -> str:
    """Return an RFC 7636 verifier with enough entropy for S256."""
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    return _b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())


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
        value=quote(access_token, safe=""),
        max_age=ACCESS_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    if id_token:
        response.set_cookie(
            key=ID_TOKEN_COOKIE,
            value=quote(id_token, safe=""),
            max_age=ID_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    if refresh_token:
        response.set_cookie(
            key=REFRESH_TOKEN_COOKIE,
            value=quote(refresh_token, safe=""),
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


def _set_oauth_cookies(
    response: Response,
    *,
    state: str,
    verifier: str,
    return_to: Optional[str] = None,
) -> None:
    """Bind the OAuth transaction to the initiating browser."""
    for key, value in (
        (OAUTH_STATE_COOKIE, state),
        (PKCE_VERIFIER_COOKIE, verifier),
    ):
        response.set_cookie(
            key=key,
            value=value,
            max_age=OAUTH_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/api/auth",
        )
    safe_return_to = _safe_return_to(return_to)
    if safe_return_to:
        response.set_cookie(
            key=OAUTH_RETURN_TO_COOKIE,
            value=quote(safe_return_to, safe=""),
            max_age=OAUTH_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/api/auth",
        )
    else:
        response.delete_cookie(
            OAUTH_RETURN_TO_COOKIE,
            path="/api/auth",
            secure=True,
            samesite="lax",
        )


def _clear_oauth_cookies(response: Response) -> None:
    for cookie in (
        OAUTH_STATE_COOKIE,
        PKCE_VERIFIER_COOKIE,
        OAUTH_RETURN_TO_COOKIE,
    ):
        response.delete_cookie(
            cookie,
            path="/api/auth",
            secure=True,
            samesite="lax",
        )


def _oauth_failure_response(
    status_code: int = 502, detail: str = "auth_failed"
) -> JSONResponse:
    """Return the non-leaking OAuth failure envelope and consume browser state."""
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"Cache-Control": "no-store"},
    )
    _clear_oauth_cookies(response)
    return response


def _clear_session_cookies(response: Response) -> None:
    for cookie in (
        ACCESS_TOKEN_COOKIE,
        ID_TOKEN_COOKIE,
        REFRESH_TOKEN_COOKIE,
        JUST_SIGNED_IN_COOKIE,
    ):
        # Match the attributes used at set_cookie time; some browsers retain
        # cookies whose deletion attributes don't match the originals.
        response.delete_cookie(cookie, path="/", secure=True, samesite="lax")


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

    Only an explicit ``invalid_grant`` rejects the caller's grant. Network,
    throttling, configuration and malformed-response failures must preserve
    existing session cookies. Never echo Cognito's error body or tokens.
    """
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    basic = _basic_auth_header()
    if basic:
        headers.update(basic)

    try:
        resp = requests.post(_token_url(), data=body, headers=headers, timeout=10)
    except requests.RequestException as exc:
        logger.error("Cognito token endpoint unreachable: %s", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="auth_unavailable") from exc

    try:
        payload = resp.json()
    except ValueError:
        logger.error("Cognito token response was not JSON")
        raise HTTPException(status_code=503, detail="auth_unavailable")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=503, detail="auth_unavailable")
    if resp.status_code == 400 and payload.get("error") == "invalid_grant":
        raise HTTPException(status_code=401, detail="auth_failed")
    if not 200 <= resp.status_code < 300:
        logger.error("Cognito token exchange failed: status=%s", resp.status_code)
        raise HTTPException(status_code=503, detail="auth_unavailable")
    return payload


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/signin")
async def signin(
    request: Request,
    provider: str = Query("email", pattern="^(google|apple|email)$"),
    return_to: Optional[str] = Query(None, alias="returnTo"),
) -> RedirectResponse:
    """Redirect the browser to Cognito's Hosted UI (Req 3.1.1).

    Maps the ``provider`` query param to Cognito's ``identity_provider``
    value and generates a signed ``state`` round-tripped through Cognito
    back to the callback handler. The state carries no session data;
    its only job is CSRF protection and replay window enforcement.
    """
    provider_key = provider.lower()
    canonical_signin_url = _canonical_loopback_signin_url(
        request,
        provider=provider_key,
        return_to=return_to,
    )
    if canonical_signin_url:
        return RedirectResponse(url=canonical_signin_url, status_code=302)

    identity_provider = PROVIDER_MAP.get(provider_key)

    state = _build_state()
    verifier = _build_pkce_verifier()
    params: Dict[str, str] = {
        "client_id": _client_id(),
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": _redirect_uri(request),
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if identity_provider:
        params["identity_provider"] = identity_provider

    url = f"{_authorize_url()}?{urlencode(params)}"
    response = RedirectResponse(url=url, status_code=302)
    _set_oauth_cookies(
        response,
        state=state,
        verifier=verifier,
        return_to=return_to,
    )
    return response


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
        response = JSONResponse(
            status_code=400,
            content={"error": "auth_failed"},
        )
        _clear_oauth_cookies(response)
        return response

    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE, "")
    verifier = request.cookies.get(PKCE_VERIFIER_COOKIE, "")
    return_to = unquote(request.cookies.get(OAUTH_RETURN_TO_COOKIE, ""))
    state_matches = bool(
        state
        and cookie_state
        and hmac.compare_digest(state, cookie_state)
    )
    if not code or not state_matches or not verifier:
        response = JSONResponse(
            status_code=400,
            content={"error": "invalid_state"},
        )
        _clear_oauth_cookies(response)
        return response

    # Req 5.3.4: state mismatch or tamper → 400 invalid_state.
    if not _verify_state(state):
        response = JSONResponse(
            status_code=400,
            content={"error": "invalid_state"},
        )
        _clear_oauth_cookies(response)
        return response

    # Exchange the authorization code for tokens.
    try:
        token_response = await asyncio.to_thread(
            _token_exchange,
            {
                "grant_type": "authorization_code",
                "client_id": _client_id(),
                "code": code,
                "redirect_uri": _redirect_uri(request),
                "code_verifier": verifier,
            }
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            return _oauth_failure_response(503, "auth_unavailable")
        return _oauth_failure_response()

    access_token = token_response.get("access_token")
    id_token = token_response.get("id_token")
    refresh_token = token_response.get("refresh_token")

    if not access_token:
        logger.error("Cognito token response missing access_token")
        return _oauth_failure_response()

    # Verify the access token against JWKS before trusting it. Any failure
    # here bubbles up as 401 from ``validate_jwt``; surface it as 502
    # auth_failed to avoid leaking JWKS internals to the caller.
    try:
        await service.validate_jwt(access_token)
    except HTTPException as exc:
        logger.error("Token validation after exchange failed: %s", exc.detail)
        if exc.status_code == 503:
            return _oauth_failure_response(503, "auth_unavailable")
        return _oauth_failure_response()

    response = RedirectResponse(
        url=_post_signin_redirect(request, return_to),
        status_code=302,
    )
    _clear_oauth_cookies(response)
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
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        status_code=200,
        content={
            "user_id": user.user_id,
            "email": user.email,
            "given_name": user.given_name,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/logout")
async def logout(request: Request) -> Response:
    """Clear the session cookies and revoke the refresh token (Req 3.1.4)."""
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    refresh_token = unquote(raw_refresh_token) if raw_refresh_token else None

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
            await asyncio.to_thread(
                requests.post, _revoke_url(), data=body, headers=headers, timeout=5
            )
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
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    refresh_token = unquote(raw_refresh_token) if raw_refresh_token else None
    if not refresh_token:
        return JSONResponse(
            status_code=401,
            content={"error": "refresh_failed"},
        )

    try:
        token_response = await asyncio.to_thread(
            _token_exchange,
            {
                "grant_type": "refresh_token",
                "client_id": _client_id(),
                "refresh_token": refresh_token,
            }
        )
    except HTTPException as exc:
        if exc.status_code != 401:
            return JSONResponse(
                status_code=503,
                content={"error": "auth_unavailable"},
                headers={"Cache-Control": "no-store"},
            )
        # Only a rejected grant proves the browser's refresh token unusable.
        response = JSONResponse(
            status_code=401,
            content={"error": "refresh_failed"},
        )
        _clear_session_cookies(response)
        return response

    access_token = token_response.get("access_token")
    id_token = token_response.get("id_token")
    # Only issue refresh cookies from the trusted token response. Without a
    # replacement, the browser keeps its existing cookie and original expiry.
    new_refresh_token = token_response.get("refresh_token")

    if not access_token:
        return JSONResponse(
            status_code=502,
            content={"error": "auth_unavailable"},
            headers={"Cache-Control": "no-store"},
        )

    try:
        await service.validate_jwt(access_token)
    except HTTPException as exc:
        # Do not trust or set a token we cannot verify, and do not discard
        # the existing refresh cookie because a signing-key lookup failed.
        return JSONResponse(
            status_code=503 if exc.status_code == 503 else 502,
            content={"error": "auth_unavailable"},
            headers={"Cache-Control": "no-store"},
        )

    response = JSONResponse(status_code=200, content={"ok": True})
    _set_session_cookies(
        response,
        access_token=access_token,
        id_token=id_token,
        refresh_token=new_refresh_token,
    )
    return response
