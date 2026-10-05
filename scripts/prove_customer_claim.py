#!/usr/bin/env python3
"""Prove the customer claim contract on the live pool and, optionally, the Gateway.

The claim contract has three parts, and each is proved from the token or the
service rather than from configuration:

1. Every mapped shopper's ACCESS token carries ``custom:customer_id`` equal to
   the customer whose ``pellier.customers.cognito_username`` is their username.
2. A refreshed access token carries the same claim, so a session that outlives
   the first token does not silently lose its identity binding.
3. A user with no customer receives no claim. With ``--probe-unmapped`` a
   throwaway user is created for this and deleted again in ``finally``.

With ``--gateway`` the script also calls the claim-scoped read on the Gateway
as the owner, as a mismatched customer, and as the unmapped probe user, and
classifies each outcome with the same denial classifier the governed write
proof uses. That part is meaningful only after the claim-scoped policies are
deployed; before that every call is permitted and the script says so.

Exit status is non-zero when any assertion fails. Tokens are never printed.

    pellier/backend/.venv/bin/python scripts/prove_customer_claim.py --probe-unmapped --gateway
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import string
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
sys.path.insert(0, str(REPO / "scripts"))

from gateway_client import (  # noqa: E402
    _load_env,
    _require,
    _secret_hash,
    select_credential,
)

CLAIM = "custom:customer_id"


def _region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def decode_claims(token: str) -> Dict[str, Any]:
    """Read the payload of a JWT without verifying it.

    Verification is the Gateway's job and is exercised by the Gateway probes;
    here the question is only what the pool put in the token it signed.
    """
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _auth_params(username: str, password: str, client_id: str, sm: Any) -> Dict[str, str]:
    params = {"USERNAME": username, "PASSWORD": password}
    client_secret_arn = os.environ.get("COGNITO_CLIENT_SECRET_ARN", "").strip()
    if client_secret_arn:
        raw = sm.get_secret_value(SecretId=client_secret_arn).get("SecretString", "")
        payload = json.loads(raw) if raw and raw.startswith("{") else {}
        client_secret = payload.get("client_secret") or raw
        if client_secret:
            params["SECRET_HASH"] = _secret_hash(username, client_id, client_secret)
    return params


def sign_in(idp: Any, sm: Any, pool_id: str, client_id: str, username: str, password: str) -> Dict[str, str]:
    result = idp.admin_initiate_auth(
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters=_auth_params(username, password, client_id, sm),
    )["AuthenticationResult"]
    return {"access": result["AccessToken"], "refresh": result.get("RefreshToken", "")}


def refresh(idp: Any, sm: Any, pool_id: str, client_id: str, username: str, refresh_token: str) -> str:
    params: Dict[str, str] = {"REFRESH_TOKEN": refresh_token}
    client_secret_arn = os.environ.get("COGNITO_CLIENT_SECRET_ARN", "").strip()
    if client_secret_arn:
        raw = sm.get_secret_value(SecretId=client_secret_arn).get("SecretString", "")
        payload = json.loads(raw) if raw and raw.startswith("{") else {}
        client_secret = payload.get("client_secret") or raw
        if client_secret:
            params["SECRET_HASH"] = _secret_hash(username, client_id, client_secret)
    result = idp.admin_initiate_auth(
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="REFRESH_TOKEN_AUTH",
        AuthParameters=params,
    )["AuthenticationResult"]
    return result["AccessToken"]


def expected_mapping(region: str) -> Dict[str, str]:
    """Username -> customer from the column row-level security reads."""
    rds = boto3.client("rds-data", region_name=region)
    secret_arn = os.environ.get("DB_SECRET_ARN") or os.environ.get("SECRET_ARN") or ""
    response = rds.execute_statement(
        resourceArn=_require("DB_CLUSTER_ARN"),
        secretArn=secret_arn,
        database=os.environ.get("DB_NAME") or os.environ.get("DATABASE") or "postgres",
        sql="SELECT cognito_username, id FROM pellier.customers",
    )
    return {
        record[0].get("stringValue", "").casefold(): record[1].get("stringValue", "")
        for record in response.get("records", [])
    }


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Pr0be-" + "".join(secrets.choice(alphabet) for _ in range(20)) + "!"


def create_probe_user(idp: Any, pool_id: str) -> Tuple[str, str]:
    username = f"claimprobe-{uuid.uuid4().hex[:10]}"
    password = _password()
    idp.admin_create_user(UserPoolId=pool_id, Username=username, MessageAction="SUPPRESS")
    idp.admin_set_user_password(UserPoolId=pool_id, Username=username, Password=password, Permanent=True)
    return username, password


async def _gateway_catalog(gateway_url: str, token: str) -> List[str]:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(30.0, read=120.0),
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(gateway_url, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return sorted(tool.name for tool in (await session.list_tools()).tools)


def _scoped_read_tool(catalog: List[str]) -> Optional[str]:
    for name in catalog:
        if name.endswith("___get_orders"):
            return name
    return None


def _gateway_outcome(gateway_url: str, token: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """One call through ``gateway_policy_probe``, classified ``allow``, ``deny`` or ``error``.

    Only a raised Cedar denial is ``deny``; a 401, a transport failure or a
    result the tool marked as an error is ``error``.
    """
    import anyio
    from gateway_policy_probe import _call_tool, classify_call

    call, failure = None, None
    try:
        call = anyio.run(_call_tool, gateway_url, token, tool, args)
    except Exception as exc:  # noqa: BLE001 - every failure shape is classified
        failure = exc
    return classify_call(call, failure)


def gateway_probes(
    gateway_url: str,
    tokens: Dict[str, str],
    customers: Dict[str, str],
    unmapped_token: str,
) -> List[Dict[str, Any]]:
    import anyio

    owners = sorted(customers)
    if not owners:
        return []
    owner = owners[0]
    other = customers[owners[1]] if len(owners) > 1 else "CUST-NOBODY"
    tool = _scoped_read_tool(anyio.run(_gateway_catalog, gateway_url, tokens[owner]))
    if tool is None:
        return [{"case": "catalog", "outcome": "error", "detail": "no customer-scoped read on the Gateway"}]
    cases = [
        ("owner", tokens[owner], {"customer_id": customers[owner]}, {"allow", "error"}),
        ("mismatched", tokens[owner], {"customer_id": other}, {"deny"}),
    ]
    if unmapped_token:
        cases.append(("unmapped", unmapped_token, {"customer_id": customers[owner]}, {"deny"}))
    results = []
    for case, token, args, expected in cases:
        outcome = _gateway_outcome(gateway_url, token, tool, args)
        results.append({
            "case": case,
            "tool": tool,
            "arguments": args,
            "outcome": outcome["outcome"],
            "passed": outcome["outcome"] in expected,
            "expected": sorted(expected),
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-unmapped", action="store_true", help="Create and delete a throwaway unmapped user")
    parser.add_argument("--gateway", action="store_true", help="Also probe the claim-scoped read on the Gateway")
    args = parser.parse_args()
    _load_env()
    region = _region()
    pool_id = _require("COGNITO_POOL_ID")
    client_id = _require("COGNITO_CLIENT_ID")
    idp = boto3.client("cognito-idp", region_name=region)
    sm = boto3.client("secretsmanager", region_name=region)

    creds = json.loads(sm.get_secret_value(SecretId=_require("COGNITO_TEST_CREDENTIALS_SECRET_ARN"))["SecretString"])
    users = creds.get("users") or []
    mapping = expected_mapping(region)
    report: Dict[str, Any] = {"pool": pool_id, "claim": CLAIM, "shoppers": [], "unmapped": None, "gateway": []}
    failures: List[str] = []
    tokens: Dict[str, str] = {}
    customers: Dict[str, str] = {}

    for credential in users:
        username = str(credential.get("username", "")).strip()
        password = credential.get("password", "")
        if not username or not password:
            continue
        credential = select_credential(users, username)
        session = sign_in(idp, sm, pool_id, client_id, username, password)
        claims = decode_claims(session["access"])
        sub = claims.get("sub", "")
        expected = mapping.get(username.casefold())
        issued = claims.get(CLAIM)
        refreshed = decode_claims(refresh(idp, sm, pool_id, client_id, username, session["refresh"])).get(CLAIM) if session["refresh"] else None
        row = {
            "username": username,
            "subject": sub[:8] + "…",
            "expected": expected,
            "issued": issued,
            "afterRefresh": refreshed,
            "tokenUse": claims.get("token_use"),
            "passed": bool(expected) and issued == expected and refreshed == expected and isinstance(issued, str),
        }
        report["shoppers"].append(row)
        if not row["passed"]:
            failures.append(f"{username}: expected {expected!r}, issued {issued!r}, after refresh {refreshed!r}")
        tokens[username] = session["access"]
        if expected:
            customers[username] = expected

    unmapped_token = ""
    probe_user: Optional[str] = None
    try:
        if args.probe_unmapped:
            probe_user, probe_password = create_probe_user(idp, pool_id)
            session = sign_in(idp, sm, pool_id, client_id, probe_user, probe_password)
            claims = decode_claims(session["access"])
            unmapped_token = session["access"]
            report["unmapped"] = {
                "username": probe_user,
                "issued": claims.get(CLAIM),
                "passed": CLAIM not in claims,
            }
            if CLAIM in claims:
                failures.append(f"unmapped user {probe_user} received {claims.get(CLAIM)!r}")
        if args.gateway:
            report["gateway"] = gateway_probes(_require("AGENTCORE_GATEWAY_URL"), tokens, customers, unmapped_token)
            for probe in report["gateway"]:
                if not probe.get("passed"):
                    failures.append(f"gateway {probe.get('case')}: {probe.get('outcome')} not in {probe.get('expected')}")
    finally:
        if probe_user:
            idp.admin_delete_user(UserPoolId=pool_id, Username=probe_user)

    report["failures"] = failures
    print(json.dumps(report, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
