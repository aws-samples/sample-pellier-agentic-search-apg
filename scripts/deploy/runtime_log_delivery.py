"""Initialize ADOT destinations in a protected AgentCore Runtime log group.

Bootstrap creates the log group before the first invocation to protect its
payloads. An existing group is not proof that the service's streams or X-Ray
delivery policy were initialized. Complete that setup before invoking Runtime.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable


STATEMENT_ID = "PellierRuntimeXRayDelivery"
STREAMS = ("runtime-logs", "spans")


def _runtime_parts(runtime_arn: str) -> tuple[str, str, str, str]:
    match = re.fullmatch(
        r"arn:([^:]+):bedrock-agentcore:([a-z0-9-]+):(\d{12}):runtime/"
        r"([A-Za-z0-9_]+-[A-Za-z0-9]+)", runtime_arn,
    )
    if not match:
        raise ValueError("Runtime log delivery requires an AgentCore Runtime ARN")
    return match.groups()


def runtime_telemetry_environment(runtime_arn: str) -> dict[str, str]:
    """Make the ADOT destination explicit, including for CodeZip runtimes."""
    _, _, _, identifier = _runtime_parts(runtime_arn)
    group = f"/aws/bedrock-agentcore/runtimes/{identifier}-DEFAULT"
    return {
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": f"x-aws-log-group={group},x-aws-log-stream=spans",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS": (
            f"x-aws-log-group={group},x-aws-log-stream=runtime-logs,"
            "x-aws-metric-namespace=bedrock-agentcore"
        ),
    }


def ensure_runtime_log_delivery(
    logs: Any,
    runtime_arn: str,
    *,
    on_checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    partition, region, account, identifier = _runtime_parts(runtime_arn)
    group = f"/aws/bedrock-agentcore/runtimes/{identifier}-DEFAULT"
    group_arn = f"arn:{partition}:logs:{region}:{account}:log-group:{group}"
    statement = {
        "Sid": STATEMENT_ID,
        "Effect": "Allow",
        "Principal": {"Service": "xray.amazonaws.com"},
        "Action": "logs:PutLogEvents",
        "Resource": group_arn + ":log-stream:spans",
        "Condition": {
            "StringEquals": {"aws:SourceAccount": account},
            "ArnLike": {"aws:SourceArn": f"arn:{partition}:xray:{region}:{account}:*"},
        },
    }
    existing = []
    for page in logs.get_paginator("describe_resource_policies").paginate(
        resourceArn=group_arn, policyScope="RESOURCE",
    ):
        existing.extend(page.get("resourcePolicies", []))
    if len(existing) > 1:
        raise RuntimeError("Runtime log group has multiple resource policies")
    previous = existing[0] if existing else None
    document = json.loads(previous["policyDocument"]) if previous else {
        "Version": "2012-10-17", "Statement": [],
    }
    if not isinstance(document, dict):
        raise RuntimeError("Runtime log group has an invalid resource policy")
    statements = document.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list) or any(not isinstance(s, dict) for s in statements):
        raise RuntimeError("Runtime log group has invalid policy statements")
    owned = [s for s in statements if s.get("Sid") == STATEMENT_ID]
    if owned and owned != [statement]:
        raise RuntimeError("Runtime trace delivery statement has changed externally")
    changed = not owned
    if changed:
        document["Statement"] = [*statements, statement]
    policy_document = json.dumps(document, separators=(",", ":"))
    receipt = {
        "streams": list(STREAMS),
        "resource_arn": group_arn,
        "policy_document": policy_document,
        "cleanup": {
            "policy_changed": changed,
            "policy_created": previous is None,
            "previous_policy_document": previous["policyDocument"] if previous else None,
        },
    }
    if previous:
        if not previous.get("revisionId"):
            raise RuntimeError("Runtime resource policy is missing its revision ID")
        receipt["revision_id"] = previous["revisionId"]
    if on_checkpoint:
        on_checkpoint(receipt)

    for stream in STREAMS:
        try:
            logs.create_log_stream(logGroupName=group, logStreamName=stream)
        except logs.exceptions.ResourceAlreadyExistsException:
            pass
    if changed:
        request = {
            "resourceArn": group_arn,
            "policyDocument": policy_document,
        }
        if previous:
            request["expectedRevisionId"] = previous["revisionId"]
        response = logs.put_resource_policy(**request)
        receipt["revision_id"] = response["revisionId"]
        if on_checkpoint:
            on_checkpoint(receipt)
    return receipt
