"""Pellier-owned password UI backed by Cognito's public authentication APIs.

Credentials are transient request data. No tokens or Cognito challenge sessions
are returned to JavaScript. A browser-bound signed CSRF nonce protects every
POST; only independently verified JWTs become existing secure session cookies.
Additional authentication challenges continue through the hosted sign-in flow.

The workshop sign-in
--------------------

``POST /workshop-sign-in`` signs one of the four provisioned shoppers in with
one click. It is a workshop convenience, not a production pattern: the browser
names a shopper and nothing else, the password comes from the provisioning
secret on the server, and Cognito mints the same signed token a typed password
would. There is no ambient identity and no faked claim. Staff never get a
chip: a member of ``pellier-operators`` is refused here, because a one-click
staff button would let anyone who opens the app approve store credits, and
that is the action Lab 4 says only staff can take. Choosing another shopper
revokes the previous shopper's refresh token before the new cookies replace
it, so a switch is a sign-out and a sign-in. It writes only the shopper
session: a staff member signed in on the Operator in the same browser stays
signed in.

The typed password sign-in
--------------------------

``POST /sign-in`` writes the session of the surface it was opened from: the
browser sends ``surface`` (``shopper`` by default, ``staff`` from the
Operator), and the server accepts only those two values. A staff account is
refused the shopper session; staff sign in on the Operator.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from services.auth import (
    OPERATOR_GROUP, SESSION_SURFACES, SHOPPER_SURFACE, staff_on_shopper_surface,
)
from services.cognito_auth import CognitoAuthService, get_cognito_auth_service
from routes.auth import (
    SIGN_IN_METHOD_WORKSHOP, STAFF_USE_OPERATOR, _build_state, _clear_sign_in_method_cookie,
    _client_id, _safe_return_to, _set_session_cookies, _set_sign_in_method_cookie,
    _verify_state, revoke_refresh_token,
)

router = APIRouter(prefix="/api/auth/password", tags=["auth"])
CSRF_COOKIE = "password_csrf"
logger = logging.getLogger(__name__)

# The only users the one-click sign-in will ever mint a session for. Nadia is
# deliberately absent: staff type a password.
WORKSHOP_SHOPPERS = ("anna", "marco", "theo", "jessica")
_CREDENTIALS_TTL_SECONDS = 60


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "cognito-idp", region_name=settings.cognito_region_resolved,
        config=Config(connect_timeout=5, read_timeout=10,
                      retries={"total_max_attempts": 1, "mode": "standard"}),
    )


def _response(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _secret_hash(username: str) -> str | None:
    if not settings.COGNITO_CLIENT_SECRET:
        return None
    message = (username + _client_id()).encode()
    digest = hmac.new(settings.COGNITO_CLIENT_SECRET.encode(), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


async def _payload(request: Request, required: tuple[str, ...]) -> dict[str, str]:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    nonce = request.headers.get("x-csrf-token", "")
    if (request.headers.get("sec-fetch-site") == "cross-site"
            or not 0 < len(cookie) <= 1024 or not 0 < len(nonce) <= 1024
            or not cookie.isascii() or not nonce.isascii()
            or not hmac.compare_digest(cookie, nonce) or not _verify_state(nonce)):
        raise HTTPException(403, "invalid_state")
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise HTTPException(415, "invalid_input")
    # Validate without reflecting password values through framework error payloads.
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise HTTPException(413, "invalid_input")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "invalid_input") from None
    limits = {"username": 128, "password": 256, "code": 2048}
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid_input")
    for key in required:
        value = body.get(key)
        if not isinstance(value, str) or not 0 < len(value) <= limits[key]:
            raise HTTPException(400, "invalid_input")
    body["username"] = body["username"].strip()
    if not body["username"]:
        raise HTTPException(400, "invalid_input")
    return body


async def _call(operation: str, **params) -> dict:
    client = _client()
    try:
        return await asyncio.to_thread(getattr(client, operation), **params)
    except (client.exceptions.TooManyRequestsException, client.exceptions.LimitExceededException):
        raise HTTPException(429, "try_later") from None
    except (client.exceptions.UserNotFoundException, client.exceptions.NotAuthorizedException):
        if operation == "forgot_password":
            return {}
        raise HTTPException(401, "invalid_credentials") from None
    except client.exceptions.PasswordResetRequiredException:
        raise HTTPException(409, "password_reset_required") from None
    except client.exceptions.UserNotConfirmedException:
        raise HTTPException(409, "verification_required") from None
    except (client.exceptions.CodeMismatchException, client.exceptions.ExpiredCodeException):
        raise HTTPException(400, "invalid_reset_code") from None
    except (client.exceptions.InvalidPasswordException, client.exceptions.PasswordHistoryPolicyViolationException):
        raise HTTPException(400, "password_requirements") from None
    except client.exceptions.InvalidParameterException:
        if operation == "forgot_password":
            # Do not disclose whether this username has a verified recovery contact.
            return {}
        raise HTTPException(503, "password_signin_unavailable") from None
    except (BotoCoreError, ClientError):
        # At the HTTP boundary, suppress SDK response details and credentials.
        raise HTTPException(503, "auth_unavailable") from None


@lru_cache(maxsize=1)
def _secrets_client():
    return boto3.client(
        "secretsmanager", region_name=settings.aws_region_resolved,
        config=Config(connect_timeout=5, read_timeout=10,
                      retries={"total_max_attempts": 1, "mode": "standard"}),
    )


_credentials_cache: Dict[str, Any] = {"read_at": 0.0, "users": []}


def _read_workshop_users() -> List[Dict[str, Any]]:
    """The provisioned test users, from the secret the deployment wrote.

    Cached briefly so four chips do not cost four Secrets Manager reads. The
    secret holds the staff entry too; the allowlist above is what keeps it out.
    """
    now = time.monotonic()
    if _credentials_cache["users"] and now - _credentials_cache["read_at"] < _CREDENTIALS_TTL_SECONDS:
        return list(_credentials_cache["users"])
    secret_arn = str(settings.COGNITO_TEST_CREDENTIALS_SECRET_ARN or "").strip()
    if not secret_arn:
        raise HTTPException(503, "workshop_sign_in_unavailable")
    try:
        raw = _secrets_client().get_secret_value(SecretId=secret_arn).get("SecretString") or "{}"
        parsed = json.loads(raw)
    except (BotoCoreError, ClientError, ValueError):
        raise HTTPException(503, "workshop_sign_in_unavailable") from None
    users = parsed.get("users") if isinstance(parsed, dict) else None
    if not isinstance(users, list):
        raise HTTPException(503, "workshop_sign_in_unavailable")
    _credentials_cache.update(read_at=now, users=list(users))
    return list(users)


def _shopper_password(username: str) -> str:
    matches = [
        user for user in _read_workshop_users()
        if isinstance(user, dict) and str(user.get("username") or "").casefold() == username
    ]
    if len(matches) != 1 or not str(matches[0].get("password") or ""):
        raise HTTPException(503, "workshop_sign_in_unavailable")
    return str(matches[0]["password"])


@router.get("/csrf")
async def csrf() -> JSONResponse:
    _client_id()
    nonce = _build_state()
    response = _response({"csrfToken": nonce})
    response.set_cookie(CSRF_COOKIE, nonce, max_age=300, httponly=True,
                        secure=True, samesite="strict", path="/api/auth/password")
    return response


def _surface(body: dict) -> str:
    """The session this sign-in writes, from the page it was opened on."""
    surface = body.get("surface", SHOPPER_SURFACE)
    if surface not in SESSION_SURFACES:
        raise HTTPException(400, "invalid_input")
    return surface


@router.post("/sign-in")
async def sign_in(request: Request, service: CognitoAuthService = Depends(get_cognito_auth_service)):
    body = await _payload(request, ("username", "password"))
    surface = _surface(body)
    parameters = {"USERNAME": body["username"], "PASSWORD": body["password"]}
    secret_hash = _secret_hash(body["username"])
    if secret_hash:
        parameters["SECRET_HASH"] = secret_hash
    result = await _call("initiate_auth", ClientId=_client_id(),
                         AuthFlow="USER_PASSWORD_AUTH", AuthParameters=parameters)
    if result.get("ChallengeName"):
        return _response({"status": "verification_required"})
    tokens = result.get("AuthenticationResult") or {}
    access_token = tokens.get("AccessToken")
    if not access_token:
        logger.warning("Cognito sign-in returned no access token")
        raise HTTPException(502, "auth_unavailable")
    try:
        user = await service.validate_jwt(access_token)
    except HTTPException as exc:
        # Keep the provider/verifier failure diagnosable without logging the
        # credentials, returned JWT, claims, or an exception's message.
        cause = exc.__cause__ or exc.__context__ or exc
        logger.warning("Cognito sign-in verification failed: %s", type(cause).__name__)
        status = 503 if exc.status_code == 503 else 502
        raise HTTPException(status, "auth_unavailable") from None
    if staff_on_shopper_surface(user, surface):
        logger.info("Password sign-in refused: a staff account opened the storefront sign-in")
        raise HTTPException(403, STAFF_USE_OPERATOR)
    target = body.get("returnTo")
    return_to = _safe_return_to(target if isinstance(target, str) else None) or "/"
    response = _response({"status": "signed_in", "returnTo": return_to})
    _set_session_cookies(response, surface=surface, access_token=access_token,
                         id_token=tokens.get("IdToken"), refresh_token=tokens.get("RefreshToken"))
    _clear_sign_in_method_cookie(response, surface)
    response.delete_cookie(CSRF_COOKIE, path="/api/auth/password", secure=True, httponly=True, samesite="strict")
    return response


@router.post("/workshop-sign-in")
async def workshop_sign_in(
    request: Request, service: CognitoAuthService = Depends(get_cognito_auth_service),
):
    """Sign one provisioned shopper in with one click. A workshop convenience.

    The browser sends a shopper's username and nothing else: a body carrying a
    password is refused outright. The password is read from the provisioning
    secret on the server, the sign-in is the same ``USER_PASSWORD_AUTH`` call a
    typed password makes, and the token is verified before it becomes a cookie.
    The verified token must name the requested user and must not carry the
    operator group, so no chip can produce another shopper's scope or a staff
    session.
    """
    body = await _payload(request, ("username",))
    if "password" in body:
        raise HTTPException(400, "invalid_input")
    username = body["username"].casefold()
    if username not in WORKSHOP_SHOPPERS:
        raise HTTPException(403, "workshop_user_not_allowed")
    password = _shopper_password(username)
    parameters = {"USERNAME": username, "PASSWORD": password}
    secret_hash = _secret_hash(username)
    if secret_hash:
        parameters["SECRET_HASH"] = secret_hash
    result = await _call("initiate_auth", ClientId=_client_id(),
                         AuthFlow="USER_PASSWORD_AUTH", AuthParameters=parameters)
    tokens = result.get("AuthenticationResult") or {}
    access_token = tokens.get("AccessToken")
    if result.get("ChallengeName") or not access_token:
        logger.warning("Workshop sign-in for %s returned no access token", username)
        raise HTTPException(502, "auth_unavailable")
    try:
        user = await service.validate_jwt(access_token)
    except HTTPException as exc:
        cause = exc.__cause__ or exc.__context__ or exc
        logger.warning("Workshop sign-in verification failed: %s", type(cause).__name__)
        raise HTTPException(503 if exc.status_code == 503 else 502, "auth_unavailable") from None
    if str(getattr(user, "username", "") or "").casefold() != username:
        logger.warning("Workshop sign-in for %s verified as another user", username)
        raise HTTPException(502, "auth_unavailable")
    if OPERATOR_GROUP in tuple(getattr(user, "groups", ()) or ()):
        logger.warning("Workshop sign-in refused: %s is in %s", username, OPERATOR_GROUP)
        raise HTTPException(403, "workshop_user_not_allowed")
    # Switching shopper signs the previous one out: only once the new session
    # is verified, so a refused or failed switch leaves the previous one intact.
    # Only the shopper's token: a staff session in the same browser stays.
    await revoke_refresh_token(request, SHOPPER_SURFACE)
    target = body.get("returnTo")
    return_to = _safe_return_to(target if isinstance(target, str) else None) or "/"
    response = _response({
        "status": "signed_in", "returnTo": return_to,
        "username": username, "signInMethod": SIGN_IN_METHOD_WORKSHOP,
    })
    _set_session_cookies(response, surface=SHOPPER_SURFACE, access_token=access_token,
                         id_token=tokens.get("IdToken"), refresh_token=tokens.get("RefreshToken"))
    _set_sign_in_method_cookie(response, SHOPPER_SURFACE, SIGN_IN_METHOD_WORKSHOP)
    response.delete_cookie(CSRF_COOKIE, path="/api/auth/password", secure=True, httponly=True, samesite="strict")
    return response


@router.post("/forgot")
async def forgot(request: Request):
    body = await _payload(request, ("username",))
    params = {"ClientId": _client_id(), "Username": body["username"]}
    secret_hash = _secret_hash(body["username"])
    if secret_hash:
        params["SecretHash"] = secret_hash
    await _call("forgot_password", **params)
    return _response({"status": "recovery_requested"})


@router.post("/reset")
async def reset(request: Request):
    body = await _payload(request, ("username", "password", "code"))
    params = {"ClientId": _client_id(), "Username": body["username"],
              "Password": body["password"], "ConfirmationCode": body["code"]}
    secret_hash = _secret_hash(body["username"])
    if secret_hash:
        params["SecretHash"] = secret_hash
    await _call("confirm_forgot_password", **params)
    return _response({"status": "password_reset"})
