#!/usr/bin/env python3
"""Run Lab 4's five boundaries against a deployed workshop account.

Runs the existing return/RLS matrix once, rejects an unsigned request at the
Gateway, then issues two ONE-CENT workshop credits as the operator. One has a
benign reason; the other has a synthetic email canary. Replaying the second
key must not issue another credit. No human approval is claimed for this CLI
path. Never run against customer/production commerce data.

No simulation lane: unavailable services, unrecognized suppression responses,
missing SQL evidence, and classifier misses remain NOT PROVED. The immutable
observations are CLI readings, not provider policy decision logs.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))
sys.path.insert(0, str(ROOT / "pellier" / "backend"))

from output_guardrail import ACTION, POLICY_NAME, policy as output_policy
from services.governance_boundaries import assess, summarize
from services.workshop_run import current_run_id
from services.gateway_errors import gateway_error_text, read_gateway_error_response

CUSTOMER = "CUST-JESSICA"
CANARY = "Synthetic workshop contact: learner@example.com"
BENIGN_REASON = "Workshop output-safety positive control"


def policy_configuration(control, gateway_id: str, engine_id: str) -> dict:
    gateway = control.get_gateway(gatewayIdentifier=gateway_id)
    attachment = gateway.get("policyEngineConfiguration") or {}
    if gateway.get("authorizerType") != "CUSTOM_JWT":
        raise RuntimeError("The workshop Gateway must authenticate Cognito JWTs")
    if attachment.get("mode") != "ENFORCE" or str(attachment.get("arn", "")).rsplit("/", 1)[-1] != engine_id:
        raise RuntimeError("Gateway must enforce the configured policy engine")
    found = None
    params = {"policyEngineId": engine_id}
    while True:
        page = control.list_policies(**params)
        for entry in page.get("policies", []):
            if entry.get("name") == POLICY_NAME:
                found = control.get_policy(policyEngineId=engine_id, policyId=entry["policyId"])
        if not page.get("nextToken"):
            break
        params["nextToken"] = page["nextToken"]
    if not found or found.get("enforcementMode") != "ACTIVE":
        raise RuntimeError("Deploy the ACTIVE managed output policy before running this proof")
    definition = found.get("definition") or {}
    # Guardrails use the general PolicyStatement union arm; legacy Cedar-only
    # policies retain the cedar arm. Both must match the reviewed bytes.
    statement = (definition.get("policy") or definition.get("cedar") or {}).get("statement", "")
    expected = output_policy(gateway["gatewayArn"])["statement"]
    if "".join(statement.split()) != "".join(expected.split()):
        raise RuntimeError("Deployed output policy differs from the reviewed policy")
    return {"gatewayMode": "ENFORCE", "authorizerType": "CUSTOM_JWT", "policyId": found["policyId"],
            "definitionHash": hashlib.sha256(statement.encode()).hexdigest()}


def error_text(exc: BaseException) -> str:
    return gateway_error_text(exc)


def suppression_reported(message: str, policy_id: str) -> bool:
    """Require explicit output suppression AND the configured policy identity.

    Do not interpret a generic 403, isError, timeout, missing payload, or an
    ordinary request-policy rejection as output suppression. New provider
    envelopes require an explicit adapter update after rehearsal.
    """
    text = message.lower()
    explicit_phase = (("output" in text or "response" in text) and "suppress" in text) or text.startswith("output blocked by policy:")
    return bool(policy_id and policy_id.lower() in text and explicit_phase)


async def invoke(gateway_url: str, token: str, tool: str, arguments: dict, policy_id: str) -> dict:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(10, read=90), follow_redirects=False,
            event_hooks={"response": [read_gateway_error_response]},
        ) as client:
            async with streamable_http_client(gateway_url, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments)
        wire = result.model_dump(mode="json")
        serialized = json.dumps(wire)
        # Only an error envelope can establish suppression; tool content that
        # happens to discuss a guardrail never does.
        suppressed = bool(wire.get("isError") and suppression_reported(serialized, policy_id))
        return {"output": "SUPPRESSED" if suppressed else "UNKNOWN" if wire.get("isError") else "RETURNED",
                "canaryReturned": "learner@example.com" in serialized,
                "responseHash": hashlib.sha256(serialized.encode()).hexdigest()}
    except Exception as exc:
        text = error_text(exc)
        return {"output": "SUPPRESSED" if suppression_reported(text, policy_id) else "UNKNOWN",
                "canaryReturned": "learner@example.com" in text,
                "errorType": type(exc).__name__}


def database_snapshot(conn, *, key: str, tool: str, reason: str, product_id: int | None = None) -> dict:
    """Count the exact operation; join through its result to the domain record."""
    arguments = {"customer_id": CUSTOMER, "reason": reason,
                 **({"product_id": product_id} if tool == "initiate_return" else {"amount_cents": 1})}
    request_hash = hashlib.sha256(json.dumps(
        {"operation": tool, "arguments": arguments}, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    domain_join = (
        "JOIN pellier.returns d ON d.id::text = w.result->>'return_id' "
        "AND d.product_id::text = %(product)s"
        if tool == "initiate_return" else
        "JOIN pellier.store_credits d ON d.credit_id::text = w.result->>'credit_id' AND d.amount_cents = 1"
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "(SELECT count(*) FROM pellier.tool_audit WHERE tool=%(tool)s AND args->>'idempotency_key'=%(key)s "
            " AND args->>'customer_id'=%(customer)s AND args->>'reason'=%(reason)s), "
            "(SELECT count(*) FROM pellier.write_operations WHERE idempotency_key=%(key)s), "
            "(SELECT count(*) FROM pellier.write_operations WHERE idempotency_key=%(key)s AND operation=%(tool)s "
            " AND completed_at IS NOT NULL AND result->>'status'='success'), "
            "(SELECT count(*) FROM pellier.write_operations w " + domain_join +
            " WHERE w.idempotency_key=%(key)s AND w.operation=%(tool)s AND w.completed_at IS NOT NULL "
            " AND w.result->>'status'='success' AND d.customer_id=%(customer)s AND d.reason=%(reason)s), "
            "(SELECT count(*) FROM pellier.inventory_ledger WHERE idempotency_key=%(key)s), "
            "(SELECT result FROM pellier.tool_audit WHERE tool=%(tool)s AND args->>'idempotency_key'=%(key)s "
            " AND args->>'customer_id'=%(customer)s AND args->>'reason'=%(reason)s ORDER BY audit_id DESC LIMIT 1), "
            "(SELECT count(*) FROM pellier.write_operations WHERE idempotency_key=%(key)s "
            " AND operation=%(tool)s AND request_hash=%(request_hash)s AND result IS NULL AND completed_at IS NULL)",
            {"key": key, "tool": tool, "customer": CUSTOMER, "reason": reason,
             "product": str(product_id) if product_id is not None else "", "request_hash": request_hash},
        )
        row = cur.fetchone()
    result = row[5] or {}
    if isinstance(result, str):
        result = json.loads(result)
    return {"queried": True, **dict(zip(
        ("executionRows", "writeRows", "committedRows", "domainRows", "ledgerRows"), row[:5])),
        "pendingClaimRows": row[6],
        "businessRejected": result.get("status") == "error" and "did not order" in str(result.get("message", "")),
        "idempotentReplay": result.get("idempotent_replay") is True}


def persist(conn, *, run_id: str, case: str, key: str, tool: str, principal: str | None, observation: dict) -> dict:
    invocation_id = f"{run_id}-{case}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pellier.governance_boundary_observations "
            "(proof_run_id,case_name,invocation_id,operation_key,tool,verified_username,observation,workshop_run_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING observation_id,created_at",
            (run_id, case, invocation_id, key, tool, principal, json.dumps(observation),
             current_run_id()),
        )
        identifier, created_at = cur.fetchone()
    conn.commit()
    return {"observationId": identifier, "proofRunId": run_id, "caseName": case,
            "invocationId": invocation_id, "operationKey": key, "tool": tool,
            "verifiedUsername": principal, "observation": observation, "createdAt": created_at.isoformat()}


def output_controls_passed(rows: list[dict]) -> bool:
    by_case = {r["caseName"]: r for r in rows}
    try:
        benign = by_case["benign-output"]["observation"]
        first = by_case["suppressed-output"]["observation"]
        replay = by_case["suppressed-replay"]["observation"]
        return bool(
            benign["output"] == "RETURNED" and assess(benign)["outcome"] == "committed"
            and by_case["suppressed-output"]["operationKey"] == by_case["suppressed-replay"]["operationKey"]
            and all(value["output"] == "SUPPRESSED" and value["canaryReturned"] is False
                    and assess(value)["outcome"] == "output_suppressed" for value in (first, replay))
            and first["database"]["executionRows"] == 1
            and replay["database"]["executionRows"] == 2
            and replay["database"]["idempotentReplay"] is True
        )
    except (KeyError, TypeError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, help="Sanitized evidence bundle destination")
    args = parser.parse_args(argv)
    Path(args.json).expanduser().parent.mkdir(parents=True, exist_ok=True)
    args.json = str(Path(args.json).expanduser())
    import boto3
    import httpx
    from botocore.config import Config
    import gateway_initiate_return as gateway

    gateway._load_env()
    url = gateway._require("AGENTCORE_GATEWAY_URL")
    arn = gateway._require("AGENTCORE_GATEWAY_ARN")
    engine_id = gateway._require("AGENTCORE_POLICY_ENGINE_ID")
    control = boto3.client("bedrock-agentcore-control", region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
                           config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}))
    before = policy_configuration(control, arn.rsplit("/", 1)[-1], engine_id)
    run_id = f"boundaries-{uuid.uuid4().hex}"
    rows = []

    def record(case, key, tool, principal, observation):
        with gateway._db_connect() as conn:
            row = persist(conn, run_id=run_id, case=case, key=key, tool=tool, principal=principal, observation=observation)
        rows.append(row)
        print(f"{case}: {assess(observation)['outcome']}")
        # Save partial evidence on every completed attempt, including failures.
        Path(args.json).write_text(json.dumps({"runId": run_id, "passed": False, "rows": rows}, indent=2))

    # No token and no invented identity. A 401 from this exact Gateway is an
    # authentication observation, never a policy decision.
    auth_key = f"{run_id}-anonymous"
    with gateway._db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('pellier.governance_boundary_observations')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("Apply migration 055 before running this proof")
        try:
            response = httpx.post(url, json={"jsonrpc": "2.0", "id": auth_key, "method": "tools/call",
                "params": {"name": "pellier-concierge-experience-target___initiate_return", "arguments": {
                    "customer_id": CUSTOMER, "product_id": 1, "reason": "damaged", "idempotency_key": auth_key}}},
                headers={"Accept": "application/json, text/event-stream"}, timeout=30, follow_redirects=False)
            status = response.status_code
        except httpx.HTTPError:
            status = None
        evidence = database_snapshot(conn, key=auth_key, tool="initiate_return", reason="damaged", product_id=1)
    record("authentication", auth_key, "initiate_return", None, {
        "authentication": "REJECTED" if status == 401 else "UNKNOWN",
        "authorization": "NOT_EVALUATED" if status == 401 else "UNKNOWN",
        "output": "UNKNOWN", "httpStatus": status, "database": evidence})

    # Preserve the authored Cedar and absence-query exercises. This command
    # consumes exactly the same return matrix, never another return per case.
    with tempfile.TemporaryDirectory() as directory:
        legacy_file = Path(directory) / "identity.json"
        process = subprocess.run([sys.executable, str(ROOT / "scripts/prove_identity_boundary.py"),
                                  "--json", str(legacy_file)], check=False)
        if not legacy_file.exists():
            raise RuntimeError("Identity proof did not produce its evidence bundle")
        identity = json.loads(legacy_file.read_text())
    for case in identity["cases"]:
        key = case["idempotency_key"]
        with gateway._db_connect() as conn:
            evidence = database_snapshot(conn, key=key, tool="initiate_return", reason="damaged",
                                         product_id=case.get("product_id") or identity["product_id"])
        observed = case["observed_outcome"]
        record(case["kind"], key, "initiate_return", case["username"] if observed in ("allow", "deny") else None, {
            "authentication": "VERIFIED" if observed in ("allow", "deny") else "UNKNOWN",
            "authorization": observed.upper() if observed in ("allow", "deny") else "UNKNOWN",
            "output": "RETURNED" if observed == "allow" else "UNKNOWN",
            "businessRejected": evidence["businessRejected"], "database": evidence,
            "gatewayConfiguration": before})

    if process.returncode != 0 or not identity["passed"]:
        record("run-checks", run_id, "issue_credit", None, {"runChecks": {
            "identityProofPassed": False, "configurationUnchanged": False, "outputControlsPassed": False,
        }})
        Path(args.json).write_text(json.dumps({"runId": run_id, "passed": False, "identity": identity, "rows": rows}, indent=2))
        print("NOT PROVED: return/RLS controls failed; credit probes were not run.")
        return 1

    token = gateway._token_from_cognito("operator")
    principal = gateway._verified_identity(token)["verified_username"]
    credit_key = f"{run_id}-suppressed-credit"
    for name, reason, key in (("benign-output", BENIGN_REASON, f"{run_id}-benign-credit"),
                              ("suppressed-output", CANARY, credit_key),
                              ("suppressed-replay", CANARY, credit_key)):
        result = asyncio.run(invoke(url, token, ACTION, {
            "customer_id": CUSTOMER, "amount_cents": 1, "reason": reason, "idempotency_key": key,
        }, before["policyId"]))
        with gateway._db_connect() as conn:
            evidence = database_snapshot(conn, key=key, tool="issue_credit", reason=reason)
        # An execution under an enforcing Gateway establishes admission; an
        # error alone does not. The query independently establishes its effect.
        record(name, key, "issue_credit", principal, {
            "authentication": "VERIFIED", "authorization": "ALLOW" if evidence["executionRows"] else "UNKNOWN",
            **result, "database": evidence, "gatewayConfiguration": before})
    after = policy_configuration(control, arn.rsplit("/", 1)[-1], engine_id)
    output_controls = output_controls_passed(rows)
    record("run-checks", run_id, "issue_credit", None, {"runChecks": {
        "identityProofPassed": process.returncode == 0 and identity["passed"],
        "configurationUnchanged": before == after, "outputControlsPassed": bool(output_controls),
    }})
    readings = summarize(rows)
    passed = readings["runs"][0]["complete"]
    bundle = {"runId": run_id, "passed": passed, "identity": identity, "rows": rows,
              "configurationUnchanged": before == after, "outputControlsPassed": output_controls,
              "source": readings["source"]}
    Path(args.json).write_text(json.dumps(bundle, indent=2))
    print("PROVED" if passed else "NOT PROVED")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # SDK errors may contain token-bearing request details. The type is
        # safe; leave detailed diagnosis to explicit service/configuration checks.
        print(f"NOT PROVED: {type(exc).__name__}. Check deployment, identity, and database prerequisites.", file=sys.stderr)
        raise SystemExit(3)
