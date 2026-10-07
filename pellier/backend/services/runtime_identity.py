"""Resolve the managed shopper from a verified Cognito access token.

Runtime is directly callable by authenticated users. Payload fields are therefore
claims made by the caller, even when FastAPI normally supplies them. They never
establish the identity used by a tool or an audit record.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

import jwt

_COGNITO_ISSUER = re.compile(
    r"https://cognito-idp\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/[A-Za-z0-9_-]+"
)


class RuntimeIdentityError(ValueError):
    """A safe error code; never include the token or its claims in the message."""


@dataclass(frozen=True)
class RuntimeIdentity:
    subject: str
    customer_id: str


class RuntimeIdentityVerifier:
    def __init__(self, issuer: str, client_id: str) -> None:
        if not _COGNITO_ISSUER.fullmatch(issuer) or not client_id:
            raise RuntimeIdentityError("auth_not_configured")
        self.issuer = issuer
        self.client_id = client_id
        # PyJWKClient caches the JWKS and refreshes on an unknown signing kid.
        # Keep an explicit timeout and verify every token's expiry on every call.
        self.jwks = jwt.PyJWKClient(issuer + "/.well-known/jwks.json", timeout=5)

    def verify(self, token: str, payload: Mapping[str, Any]) -> RuntimeIdentity:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], issuer=self.issuer, leeway=5,
                options={"verify_aud": False,
                         "require": ["exp", "iss", "sub", "client_id", "token_use"]},
            )
        except jwt.PyJWKClientConnectionError as exc:
            raise RuntimeIdentityError("auth_unavailable") from exc
        except jwt.PyJWTError as exc:
            raise RuntimeIdentityError("authentication_failed") from exc
        if claims.get("token_use") != "access" or claims.get("client_id") != self.client_id:
            raise RuntimeIdentityError("authentication_failed")
        subject = claims.get("sub")
        customer = claims.get("custom:customer_id")
        if not isinstance(subject, str) or not subject.strip():
            raise RuntimeIdentityError("authentication_failed")
        if not isinstance(customer, str) or not re.fullmatch(r"CUST-[A-Z0-9-]{1,40}", customer):
            raise RuntimeIdentityError("customer_identity_unmapped")
        for name, verified in (("user_id", subject), ("customer_id", customer)):
            if payload.get(name) not in (None, "", verified):
                raise RuntimeIdentityError("customer_scope_mismatch")
        return RuntimeIdentity(subject=subject, customer_id=customer)


@lru_cache(maxsize=1)
def _verifier() -> RuntimeIdentityVerifier:
    return RuntimeIdentityVerifier(
        os.environ.get("PELLIER_COGNITO_ISSUER", ""),
        os.environ.get("PELLIER_COGNITO_CLIENT_ID", ""),
    )


def verified_runtime_identity(token: str, payload: Mapping[str, Any]) -> RuntimeIdentity:
    return _verifier().verify(token, payload)
