#!/usr/bin/env python3
"""Invoke Pellier initiate_return through AgentCore Gateway.

This is a deterministic workshop helper for the Cedar exercise. It does not
ask a model to decide whether to call the tool: it calls the Gateway MCP tool
directly with a real Cognito bearer token. A Gateway/Cedar DENY raises before
the Lambda target executes, so no ``pellier.tool_audit`` row is written.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import runpy
import os
import sys
from pathlib import Path
from typing import Any

import anyio
import boto3
import httpx
import psycopg
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


DEFAULT_TOOL_NAME = "pellier-concierge-experience-target___initiate_return"


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
            os.environ[key.strip()] = value.strip().strip("'\"")


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
    identity of a governed call an accident of provisioning order — the exact
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
    ``cognito:username`` — that claim is on the ID token, and the Gateway
    validates the access token. AgentCore Policy exposes the claim as a
    principal tag, which is what the Lab 4 Cedar rule compares against the
    tool's ``customer_id`` input.
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    pool_id = os.environ.get("COGNITO_POOL_ID") or os.environ.get("COGNITO_POOL")
    client_id = os.environ.get("COGNITO_CLIENT_ID") or os.environ.get("COGNITO_CLIENT")
    creds_secret_arn = _require("COGNITO_TEST_CREDENTIALS_SECRET_ARN")
    if not pool_id or not client_id:
        raise SystemExit("Missing Cognito pool/client env vars.")

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


def _db_connect():
    return psycopg.connect(
        host=_require("DB_HOST"),
        port=os.environ.get("DB_PORT", "5432"),
        user=_require("DB_USER"),
        password=_require("DB_PASSWORD"),
        dbname=_require("DB_NAME"),
    )


def _idempotency_key(args: argparse.Namespace) -> str:
    """Return the invocation key shared by Gateway, Lambda, and audit proof."""
    return args.idempotency_key or args.session_id


def _audit_high_water(args: argparse.Namespace) -> int:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(max(audit_id), 0) "
                "FROM pellier.tool_audit "
                "WHERE tool = 'initiate_return' "
                "  AND caller = 'gateway' "
                "  AND args->>'customer_id' = %s "
                "  AND args->>'product_id' = %s "
                "  AND args->>'reason' = %s "
                "  AND args->>'idempotency_key' = %s",
                (
                    args.customer_id,
                    str(args.product_id),
                    args.reason,
                    _idempotency_key(args),
                ),
            )
            return int(cur.fetchone()[0] or 0)


def _latest_matching_audit(args: argparse.Namespace, after_audit_id: int) -> int | None:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT audit_id "
                "FROM pellier.tool_audit "
                "WHERE tool = 'initiate_return' "
                "  AND caller = 'gateway' "
                "  AND args->>'customer_id' = %s "
                "  AND args->>'product_id' = %s "
                "  AND args->>'reason' = %s "
                "  AND args->>'idempotency_key' = %s "
                "  AND audit_id > %s "
                "ORDER BY audit_id DESC LIMIT 1",
                (
                    args.customer_id,
                    str(args.product_id),
                    args.reason,
                    _idempotency_key(args),
                    after_audit_id,
                ),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None


def _record_receipt(
    args: argparse.Namespace,
    payload: dict[str, Any],
    before_audit_id: int,
    identity: dict[str, str],
) -> None:
    audit_id = _latest_matching_audit(args, before_audit_id)
    if payload["outcome"] == "allow" and audit_id is None:
        raise RuntimeError("Gateway call ALLOWed but no matching tool_audit row was found.")
    if payload["outcome"] == "deny" and audit_id is not None:
        raise RuntimeError(f"Gateway call DENYed but tool_audit row {audit_id} was written.")

    receipt_args = {
        "customer_id": args.customer_id,
        "product_id": int(args.product_id),
        "reason": args.reason,
        "idempotency_key": _idempotency_key(args),
        "tool_audit_high_water_before": before_audit_id,
        "tool_audit_row_after_call": audit_id,
        "absence_verified": payload["outcome"] == "deny" and audit_id is None,
    }
    run_helpers = runpy.run_path(str(_repo_root() / "pellier/backend/services/workshop_run.py"))
    workshop_run_id = run_helpers["current_run_id"]()
    if workshop_run_id and not run_helpers["is_valid_run_id"](workshop_run_id):
        raise ValueError("Invalid workshop run id")
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('pellier.run_id', %s, true)", (workshop_run_id or "",))
            cur.execute(
                """
                INSERT INTO pellier.governed_receipts
                    (audit_id, session_id, principal_id, principal_label,
                     tool, caller, decision, args, policy_engine_id,
                     policy_name, token_fingerprint_sha256, verified_subject,
                     verified_username, issuer, client_id, identity_source,
                     created_at)
                VALUES
                    (%s, %s, %s, %s, 'initiate_return', 'gateway',
                     %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, now())
                RETURNING receipt_id
                """,
                (
                    audit_id,
                    args.session_id,
                    identity["principal_id"],
                    identity["principal_label"],
                    payload["outcome"].upper(),
                    json.dumps(receipt_args, sort_keys=True),
                    os.environ.get("AGENTCORE_POLICY_ENGINE_ID", ""),
                    args.policy_name,
                    identity["token_fingerprint_sha256"],
                    identity["verified_subject"],
                    identity["verified_username"],
                    identity["issuer"],
                    identity["client_id"],
                    identity["identity_source"],
                ),
            )
            receipt_id = int(cur.fetchone()[0])
        conn.commit()
    payload["recorded_receipt_id"] = receipt_id
    payload["recorded_receipt_session_id"] = args.session_id
    payload["tool_audit_high_water_before"] = before_audit_id
    payload["tool_audit_row_after_call"] = audit_id
    payload["verified_identity"] = {
        key: identity[key]
        for key in (
            "verified_subject",
            "verified_username",
            "issuer",
            "client_id",
            "token_fingerprint_sha256",
            "identity_source",
        )
    }


async def _call_gateway(args: argparse.Namespace, token: str) -> dict[str, Any]:
    gateway_url = args.gateway_url or _require("AGENTCORE_GATEWAY_URL")
    tool_args = {
        "customer_id": args.customer_id,
        "product_id": int(args.product_id),
        "reason": args.reason,
        "idempotency_key": _idempotency_key(args),
    }
    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            gateway_url,
            http_client=http_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(args.tool_name, tool_args)
                return {
                    "outcome": "allow",
                    "tool": args.tool_name,
                    "arguments": tool_args,
                    "result": _jsonable(result),
                }


def _exception_summary(exc: BaseException) -> str:
    children = getattr(exc, "exceptions", None)
    if children:
        return "; ".join(_exception_summary(child) for child in children)[:700]
    return str(exc)[:700]


def _is_authorization_denial(exc: BaseException) -> bool:
    """Return True only for Gateway/Cedar authorization failures.

    The workshop proof depends on distinguishing a managed Policy DENY from
    transport, auth, or tool-name failures. Treating every exception as DENY
    would make a broken Gateway look like a successful policy exercise.
    """
    children = getattr(exc, "exceptions", None)
    if children:
        return any(_is_authorization_denial(child) for child in children)

    haystack = f"{exc.__class__.__name__}: {exc}".lower()
    if "suppress" in haystack and ("output" in haystack or "response" in haystack):
        return False
    denial_markers = (
        "authorizeactionexception",
        # Verbatim GA Gateway deny lead-in (box-verified 2026-06-12):
        # "Tool call not allowed due to policy enforcement [Policy evaluation
        # denied due to <policy>-...]". Matched explicitly so the deny still
        # classifies even if the bracketed detail is truncated.
        "not allowed due to policy",
        "policy enforcement",
        "policy evaluation denied",
    )
    # Deliberately NOT matched: generic AccessDenied/Unauthorized/Forbidden.
    # Those can describe IAM, JWT, or target failures and must surface as
    # outcome "error", never a fake Cedar DENY proof.
    return any(marker in haystack for marker in denial_markers)


def main() -> int:
    parser = argparse.ArgumentParser(description="Invoke initiate_return through AgentCore Gateway.")
    # Canonical customer id, never a display name or Storefront persona alias.
    # Lab 4 anchors on Jessica's Operator case and separately authenticated
    # Cognito principal.
    parser.add_argument("--customer-id", default="CUST-JESSICA")
    parser.add_argument("--product-id", type=int, required=True)
    parser.add_argument("--reason", default="damaged")
    parser.add_argument("--expect", choices=("allow", "deny"), default="allow")
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--tool-name", default=DEFAULT_TOOL_NAME)
    parser.add_argument(
        "--record-receipt",
        action="store_true",
        help="Record a governed_receipts row for the Gateway decision and absence check.",
    )
    parser.add_argument("--session-id", default="gateway-identity-proof")
    parser.add_argument(
        "--idempotency-key",
        default="",
        help="Stable write key; defaults to the receipt session id.",
    )
    parser.add_argument("--policy-name", default="workshop_identity_match_forbid")
    parser.add_argument(
        "--user",
        default="",
        metavar="USERNAME",
        help=(
            "Cognito username to authenticate as (marco, anna, theo, jessica). This is "
            "the security PRINCIPAL, not a storefront persona: it selects whose "
            "verified JWT signs the call, which is what Cedar and Row-Level "
            "Security evaluate. Resolved by name from the credential secret; an "
            "unknown name is refused. Ignored when PELLIER_TOKEN is already set, "
            "since that token already names its own principal."
        ),
    )
    args = parser.parse_args()

    _load_env()
    # The two identity sources are mutually exclusive, and supplying both is a
    # hard error rather than a precedence rule.
    #
    # Ignoring --user because an inherited PELLIER_TOKEN happened to be exported
    # is the worst available behaviour for this script: the operator believes
    # they tested Theo, the receipt records Marco, and the transcript looks like
    # a successful proof. An identity-source ambiguity must never resolve
    # silently in a tool whose entire output is an identity claim.
    preset_token = os.environ.get("PELLIER_TOKEN", "").strip()
    if preset_token and args.user:
        raise SystemExit(
            "Refusing to guess the principal: --user "
            f"{args.user!r} and PELLIER_TOKEN both name an identity.\n"
            "  Use one:\n"
            f"    --user {args.user}          mint a fresh token for that Cognito user\n"
            "    unset PELLIER_TOKEN     then re-run with --user\n"
            "    (or drop --user)        to use the token already in the environment"
        )
    token = preset_token or _token_from_cognito(args.user)
    identity = _verified_identity(token)
    before_audit_id = _audit_high_water(args) if args.record_receipt else 0

    try:
        payload = anyio.run(_call_gateway, args, token)
    except Exception as exc:
        if not _is_authorization_denial(exc):
            payload = {
                "outcome": "error",
                "tool": args.tool_name,
                "arguments": {
                    "customer_id": args.customer_id,
                    "product_id": int(args.product_id),
                    "reason": args.reason,
                },
                "error_type": exc.__class__.__name__,
                "error": _exception_summary(exc),
                "gateway_rail": True,
                "tool_executed": None,
                "cedar_denial": False,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 2
        payload = {
            "outcome": "deny",
            "tool": args.tool_name,
            "arguments": {
                "customer_id": args.customer_id,
                "product_id": int(args.product_id),
                "reason": args.reason,
            },
            "error_type": exc.__class__.__name__,
            "error": _exception_summary(exc),
            "gateway_rail": True,
            "tool_executed": False,
            "cedar_denial": True,
        }

    if args.record_receipt:
        _record_receipt(args, payload, before_audit_id, identity)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["outcome"] == args.expect else 2


if __name__ == "__main__":
    raise SystemExit(main())
