"""Pellier-owned password UI backed by Cognito's public authentication APIs.

Credentials are transient request data. No tokens or Cognito challenge sessions
are returned to JavaScript. A browser-bound signed CSRF nonce protects all three
POSTs; only independently verified JWTs become existing secure session cookies.
Additional authentication challenges continue through the hosted sign-in flow.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from services.cognito_auth import CognitoAuthService, get_cognito_auth_service
from routes.auth import (
    _build_state, _client_id, _safe_return_to, _set_just_signed_in_cookie,
    _set_session_cookies, _verify_state,
)

router = APIRouter(prefix="/api/auth/password", tags=["auth"])
CSRF_COOKIE = "password_csrf"
logger = logging.getLogger(__name__)


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


@router.get("/csrf")
async def csrf() -> JSONResponse:
    _client_id()
    nonce = _build_state()
    response = _response({"csrfToken": nonce})
    response.set_cookie(CSRF_COOKIE, nonce, max_age=300, httponly=True,
                        secure=True, samesite="strict", path="/api/auth/password")
    return response


@router.post("/sign-in")
async def sign_in(request: Request, service: CognitoAuthService = Depends(get_cognito_auth_service)):
    body = await _payload(request, ("username", "password"))
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
        await service.validate_jwt(access_token)
    except HTTPException as exc:
        # Keep the provider/verifier failure diagnosable without logging the
        # credentials, returned JWT, claims, or an exception's message.
        cause = exc.__cause__ or exc.__context__ or exc
        logger.warning("Cognito sign-in verification failed: %s", type(cause).__name__)
        status = 503 if exc.status_code == 503 else 502
        raise HTTPException(status, "auth_unavailable") from None
    target = body.get("returnTo")
    return_to = _safe_return_to(target if isinstance(target, str) else None) or "/"
    response = _response({"status": "signed_in", "returnTo": return_to})
    _set_session_cookies(response, access_token=access_token,
                         id_token=tokens.get("IdToken"), refresh_token=tokens.get("RefreshToken"))
    _set_just_signed_in_cookie(response)
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
