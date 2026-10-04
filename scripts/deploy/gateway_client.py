"""Shared helpers for scripts that call the deployed Gateway as a Cognito user.

Environment loading, Cognito token minting for one named test principal, and
the classifier that tells a managed Policy DENY apart from every other
failure. ``probe_gateway_tool.py`` is the generic probe built on these; the
customer-claim and memory scripts reuse the environment and token helpers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env() -> None:
    for env_path in (_repo_root() / ".env", _repo_root() / "pellier" / "backend" / ".env"):
        if not env_path.is_file():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            # Explicit environment selects the deployment being proved. A
            # local .env must not silently redirect it to an older Gateway.
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _secret_hash(username: str, client_id: str, client_secret: str) -> str:
    digest = hmac.new(
        client_secret.encode("utf-8"),
        msg=f"{username}{client_id}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def select_credential(users: list[dict[str, Any]], requested: str) -> dict[str, Any]:
    """Pick one Cognito credential by username.

    Resolution is by name, never by array index. Index selection silently
    authenticated whoever happened to be first in the secret, which made the
    identity of a governed call an accident of provisioning order, the exact
    thing Lab 4 asks a participant to reason about.

    ``requested`` is matched case-insensitively. An empty request keeps the
    historical behaviour of taking the first entry, so existing callers that do
    not care which principal they use are unaffected.

    Raises SystemExit for an unknown username, and for a secret that lists the
    same username twice: a duplicate makes "which principal signed this call"
    unanswerable, and answering it wrong is worse than refusing.
    """
    named = [u for u in users if str(u.get("username", "")).strip()]
    if not named:
        raise SystemExit("Cognito test credential secret has no usable users array.")

    seen: dict[str, int] = {}
    for user in named:
        key = str(user["username"]).strip().lower()
        seen[key] = seen.get(key, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    if duplicates:
        raise SystemExit(
            "Cognito test credential secret lists a username more than once: "
            f"{', '.join(duplicates)}. Every principal must be unambiguous."
        )

    wanted = requested.strip().lower()
    if not wanted:
        return named[0]

    for user in named:
        if str(user["username"]).strip().lower() == wanted:
            return user

    available = ", ".join(sorted(seen)) or "(none)"
    raise SystemExit(
        f"No Cognito user named {requested!r} in the credential secret. "
        f"Available: {available}."
    )


def _token_from_cognito(requested_user: str = "") -> str:
    """Mint a real Cognito access token for one named principal.

    The access token's identity claim is ``username`` (lowercased). It is NOT
    ``cognito:username``, which is on the ID token; the Gateway validates the
    access token. AgentCore Policy exposes the token's claims as principal
    tags, which is what the baseline permits and the Lab 4 rule compare.
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    pool_id = os.environ.get("COGNITO_POOL_ID") or os.environ.get("COGNITO_POOL")
    client_id = os.environ.get("COGNITO_CLIENT_ID") or os.environ.get("COGNITO_CLIENT")
    creds_secret_arn = _require("COGNITO_TEST_CREDENTIALS_SECRET_ARN")
    if not pool_id or not client_id:
        raise SystemExit("Missing Cognito pool/client env vars.")

    import boto3

    sm = boto3.client("secretsmanager", region_name=region)
    creds_raw = sm.get_secret_value(SecretId=creds_secret_arn).get("SecretString", "")
    creds = json.loads(creds_raw or "{}")
    users = creds.get("users") or []
    if not users:
        raise SystemExit("Cognito test credential secret has no users array.")
    credential = select_credential(users, requested_user)
    username = str(credential.get("username", "")).strip()
    password = credential.get("password", "")
    if not username or not password:
        raise SystemExit("Cognito test credential secret is missing username/password.")

    auth_params = {"USERNAME": username, "PASSWORD": password}
    client_secret_arn = os.environ.get("COGNITO_CLIENT_SECRET_ARN", "").strip()
    if client_secret_arn:
        secret_raw = sm.get_secret_value(SecretId=client_secret_arn).get("SecretString", "")
        secret_payload = json.loads(secret_raw) if secret_raw and secret_raw.startswith("{") else {}
        client_secret = secret_payload.get("client_secret") or secret_raw
        if client_secret:
            auth_params["SECRET_HASH"] = _secret_hash(username, client_id, client_secret)

    cognito = boto3.client("cognito-idp", region_name=region)
    auth = cognito.admin_initiate_auth(
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters=auth_params,
    )
    token = auth.get("AuthenticationResult", {}).get("AccessToken", "")
    if not token:
        raise SystemExit("Cognito did not return an access token.")
    return token


def _exception_summary(exc: BaseException) -> str:
    children = getattr(exc, "exceptions", None)
    if children:
        return "; ".join(_exception_summary(child) for child in children)[:700]
    return str(exc)[:700]


# Verbatim GA Gateway deny lead-in (box-verified 2026-06-12): "Tool call not
# allowed due to policy enforcement [Policy evaluation denied due to
# <policy>-...]". Matched explicitly so the deny still classifies even if the
# bracketed detail is truncated. Deliberately NOT matched: generic
# AccessDenied/Unauthorized/Forbidden. Those can describe IAM, JWT, or target
# failures and must surface as outcome "error", never a fake Cedar DENY proof.
POLICY_DENIAL_MARKERS = (
    "authorizeactionexception",
    "not allowed due to policy",
    "policy enforcement",
    "policy evaluation denied",
)


def is_policy_denial_text(text: str) -> bool:
    """True only when ``text`` carries the Gateway's Cedar denial shape.

    The one classifier the Lab 3 and Lab 4 probes, the provisioning proof and
    the receipt validator share, so a 401 or a transport failure reads the
    same everywhere: not a policy decision.
    """
    haystack = str(text or "").lower()
    if "suppress" in haystack and ("output" in haystack or "response" in haystack):
        return False
    return any(marker in haystack for marker in POLICY_DENIAL_MARKERS)


def _is_authorization_denial(exc: BaseException) -> bool:
    """Return True only for Gateway/Cedar authorization failures.

    The workshop proof depends on distinguishing a managed Policy DENY from
    transport, auth, or tool-name failures. Treating every exception as DENY
    would make a broken Gateway look like a successful policy exercise.
    """
    children = getattr(exc, "exceptions", None)
    if children:
        return any(_is_authorization_denial(child) for child in children)
    return is_policy_denial_text(f"{exc.__class__.__name__}: {exc}")


def _decode_access_token_claims(token: str) -> dict[str, Any]:
    """Decode claims only after Cognito has validated this exact access token."""
    try:
        _header, payload, _signature = token.split(".")
        padded = payload + ("=" * (-len(payload) % 4))
        claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Cognito accepted a malformed access token payload.") from exc
    if not isinstance(claims, dict):
        raise RuntimeError("Cognito access token payload is not a JSON object.")
    return claims


def _verified_identity(token: str) -> dict[str, str]:
    """Bind receipt identity to the exact bearer token accepted by Cognito."""
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    pool_id = os.environ.get("COGNITO_POOL_ID") or os.environ.get("COGNITO_POOL")
    client_id = os.environ.get("COGNITO_CLIENT_ID") or os.environ.get("COGNITO_CLIENT")
    if not pool_id or not client_id:
        raise RuntimeError("Missing Cognito pool/client env vars for receipt verification.")

    import boto3

    cognito = boto3.client("cognito-idp", region_name=region)
    user = cognito.get_user(AccessToken=token)
    claims = _decode_access_token_claims(token)
    attributes = {
        str(item.get("Name", "")): str(item.get("Value", ""))
        for item in user.get("UserAttributes", [])
    }

    expected_issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    subject = str(claims.get("sub") or "")
    claim_username = str(
        claims.get("username") or claims.get("cognito:username") or ""
    )
    verified_username = str(user.get("Username") or "")
    checks = {
        "token_use": claims.get("token_use") == "access",
        "issuer": hmac.compare_digest(str(claims.get("iss") or ""), expected_issuer),
        "client_id": hmac.compare_digest(str(claims.get("client_id") or ""), client_id),
        "subject": bool(subject) and hmac.compare_digest(subject, attributes.get("sub", "")),
        "username": bool(claim_username)
        and hmac.compare_digest(claim_username, verified_username),
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise RuntimeError(
            "Cognito bearer identity did not match required claims: "
            + ", ".join(failed)
        )

    return {
        "principal_id": subject,
        "principal_label": f"{verified_username} (Cognito JWT)",
        "verified_subject": subject,
        "verified_username": verified_username,
        "issuer": expected_issuer,
        "client_id": client_id,
        "token_fingerprint_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "identity_source": "cognito",
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value
